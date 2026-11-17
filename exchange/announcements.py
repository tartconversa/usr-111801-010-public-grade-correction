"""公告版本链与更正传播。

公告的每次发布、更正、撤回都是一条不可修改的追加记录，版本之间的依据关系
保存在 announcement_relations 中。当前效力由整条链折叠推导，而不是回写或
删除旧记录：撤回一份更正后，被撤回的更正仍然存在，只是不再计入有效集合。
"""

import hashlib
import json

from .audit import write


def _canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                      ) if payload is not None else None


class Announcements:
    def __init__(self, connection):
        self.connection = connection

    # ------------------------------------------------------------------ 登记
    def _next_seq(self, notice_id):
        row = self.connection.execute(
            "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM announcements WHERE notice_id=?",
            (notice_id,),
        ).fetchone()
        return row["seq"]

    def _issue(self, announcement_id, notice_id, kind, source_id, at, actor,
               areas, related_id, relation):
        source = self.connection.execute(
            "SELECT owner FROM sources WHERE id=?", (source_id,)
        ).fetchone()
        if source is None:
            raise KeyError(source_id)
        if kind == "withdrawal":
            if areas:
                raise ValueError("撤回公告不携带目录条目")
            payload, digest = None, None
            if related_id is None or relation != "withdraws":
                raise ValueError("撤回必须指明被撤回的更正公告")
        else:
            if not areas:
                raise ValueError("公告缺少景区目录条目")
            seen = set()
            for area in areas:
                name = area.get("scenic_area")
                if not name or name in seen:
                    raise ValueError("景区条目缺失或重复")
                seen.add(name)
            payload = _canonical(areas)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            if kind == "correction":
                if related_id is None or relation != "corrects":
                    raise ValueError("更正必须指明被更正的公告版本")
            elif related_id is not None:
                raise ValueError("首发公告不能建立更正关系")
        if related_id is not None:
            related = self.connection.execute(
                "SELECT id,notice_id FROM announcements WHERE id=?", (related_id,)
            ).fetchone()
            if related is None:
                raise ValueError("被引用的公告版本不存在")
            if related["notice_id"] != notice_id:
                raise ValueError("更正关系只能建立在同一公告系列内")
        if self.connection.execute(
            "SELECT 1 FROM announcements WHERE id=?", (announcement_id,)
        ).fetchone():
            raise ValueError("公告编号已存在")
        seq = self._next_seq(notice_id)
        with self.connection:
            self.connection.execute(
                "INSERT INTO announcements(id,notice_id,seq,source_id,kind,published_at,payload,digest) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (announcement_id, notice_id, seq, source_id, kind, at, payload, digest),
            )
            if related_id is not None:
                self.connection.execute(
                    "INSERT INTO announcement_relations(announcement_id,related_id,relation) VALUES(?,?,?)",
                    (announcement_id, related_id, relation),
                )
            write(
                self.connection, at, actor,
                {"publish": "announcement.publish",
                 "correction": "announcement.correct",
                 "withdrawal": "announcement.withdraw"}[kind],
                notice_id,
                {"announcement": announcement_id, "seq": seq, "relation": relation,
                 "related": related_id, "areas": [a["scenic_area"] for a in (areas or [])]},
            )
        return seq

    def publish(self, announcement_id, notice_id, source_id, areas, at, actor):
        """首发公告：为每个景区登记当前可核实的目录条目。"""
        return self._issue(announcement_id, notice_id, "publish", source_id, at,
                           actor, areas, None, None)

    def correct(self, announcement_id, notice_id, source_id, corrected_id, areas, at, actor):
        """更正公告：携带新的目录条目，并指向被更正的版本。"""
        return self._issue(announcement_id, notice_id, "correction", source_id, at,
                           actor, areas, corrected_id, "corrects")

    def withdraw(self, announcement_id, notice_id, source_id, corrected_id, at, actor):
        """撤回一份更正：只追加撤回记录，不删除也不复活任何旧条目。"""
        target = self.connection.execute(
            "SELECT kind FROM announcements WHERE id=?", (corrected_id,)
        ).fetchone()
        if target is None:
            raise ValueError("被撤回的公告版本不存在")
        if target["kind"] != "correction":
            raise ValueError("只能撤回更正公告")
        return self._issue(announcement_id, notice_id, "withdrawal", source_id, at,
                           actor, None, corrected_id, "withdraws")

    # ------------------------------------------------------------------ 效力
    def versions(self, notice_id):
        rows = self.connection.execute(
            "SELECT * FROM announcements WHERE notice_id=? ORDER BY seq", (notice_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def effective_announcements(self, notice_id):
        """沿公告链折叠出当前有效版本集合。

        被后续更正取代的版本、以及被撤回的更正都不属于有效集合；撤回本身
        没有目录条目。撤回的效果通过“忽略被撤回的更正”自然恢复更早的有效
        版本，全程不需要倒放或改写任何记录。
        """
        versions = self.versions(notice_id)
        relations = {
            row["announcement_id"]: (row["related_id"], row["relation"])
            for row in self.connection.execute(
                "SELECT announcement_id,related_id,relation FROM announcement_relations"
            )
        }
        withdrawn = {
            related_id
            for version in versions
            if (relation := relations.get(version["id"])) is not None
            and relation[1] == "withdraws"
            for related_id in [relation[0]]
        }
        # 只有未被撤回的更正才能取代旧版本；撤回更正后，旧版本自动恢复效力，
        # 不需要改写或倒放任何记录。
        superseded = {
            relation[0]
            for version in versions
            if version["id"] not in withdrawn
            and (relation := relations.get(version["id"])) is not None
            and relation[1] == "corrects"
        }
        return [
            version for version in versions
            if version["id"] not in superseded
            and version["id"] not in withdrawn
            and version["kind"] != "withdrawal"
        ]

    def is_effective(self, announcement_id):
        row = self.connection.execute(
            "SELECT notice_id FROM announcements WHERE id=?", (announcement_id,)
        ).fetchone()
        if row is None:
            raise KeyError(announcement_id)
        return any(
            version["id"] == announcement_id
            for version in self.effective_announcements(row["notice_id"])
        )

    def current_announcement(self, scenic_area):
        """某景区当前可核实条目所依据的有效公告。"""
        candidates = self.connection.execute(
            "SELECT DISTINCT a.notice_id FROM assets t "
            "JOIN announcements a ON a.id=t.basis_announcement_id "
            "WHERE t.scenic_area=?",
            (scenic_area,),
        ).fetchall()
        best = None
        for row in candidates:
            for version in self.effective_announcements(row["notice_id"]):
                if version["payload"] is None:
                    continue
                areas = json.loads(version["payload"])
                if not any(area["scenic_area"] == scenic_area for area in areas):
                    continue
                if best is None or (version["notice_id"], version["seq"]) > (best["notice_id"], best["seq"]):
                    best = version
        return best

    def current_asset(self, scenic_area):
        """某景区当前可核实的目录条目资产；无有效公告时返回 None。"""
        version = self.current_announcement(scenic_area)
        if version is None:
            return None
        row = self.connection.execute(
            "SELECT * FROM assets WHERE scenic_area=? AND basis_announcement_id=? "
            "ORDER BY id LIMIT 1",
            (scenic_area, version["id"]),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------ 影响面查询
    def explain_delivery(self, delivery_id):
        """说明一份已发出回执当时的依据，并逐项提示当前受影响范围。"""
        delivery = self.connection.execute(
            "SELECT * FROM deliveries WHERE id=?", (delivery_id,)
        ).fetchone()
        if delivery is None:
            raise KeyError(delivery_id)
        basis = json.loads(delivery["basis_snapshot"]) if delivery["basis_snapshot"] else []
        items = []
        for entry in basis:
            area = entry["scenic_area"]
            current = self.current_asset(area) if area else None
            if entry["basis_announcement_id"] is None:
                status = "non-announcement"
            elif self.is_effective(entry["basis_announcement_id"]) and (
                current is None or current["id"] == entry["asset_id"]
            ):
                status = "current"
            else:
                status = "stale"
            items.append({
                "scenic_area": area,
                "asset_id": entry["asset_id"],
                "basis_announcement_id": entry["basis_announcement_id"],
                "basis_digest": entry.get("digest"),
                "delivered_at": delivery["created_at"],
                "status": status,
                "current_asset_id": current["id"] if current else None,
            })
        return {
            "delivery_id": delivery_id,
            "recipient": delivery["recipient"],
            "purpose": delivery["purpose"],
            "product_id": delivery["product_id"],
            "product_revision": delivery["product_revision"],
            "items": items,
            "affected_areas": [item["scenic_area"] for item in items if item["status"] == "stale"],
        }

    def pending_reconfirmations(self, scenic_area=None, recipient=None):
        """按景区和领取方查明仍待重新确认的数据。

        判定规则（全部由历史回执与当前公告链派生，不另存状态）：
        回执中的公告依据条目一旦不再是该景区的当前可核实条目即为受影响；
        若该领取方之后已领取过包含同一景区当前条目的回执，则视为已重新确认。
        """
        query = (
            "SELECT d.* FROM deliveries d JOIN product_inputs p "
            "ON p.product_id=d.product_id AND p.product_revision=d.product_revision "
            "JOIN assets a ON a.id=p.asset_id "
            "WHERE a.basis_announcement_id IS NOT NULL"
        )
        args = []
        if recipient is not None:
            query += " AND d.recipient=?"
            args.append(recipient)
        if scenic_area is not None:
            query += " AND a.scenic_area=?"
            args.append(scenic_area)
        deliveries = {row["id"]: row for row in self.connection.execute(query, args)}
        results = []
        for delivery_id, delivery in deliveries.items():
            explanation = self.explain_delivery(delivery_id)
            for item in explanation["items"]:
                if item["scenic_area"] is None or item["status"] != "stale":
                    continue
                if scenic_area is not None and item["scenic_area"] != scenic_area:
                    continue
                refreshed = self.connection.execute(
                    "SELECT 1 FROM deliveries d2 JOIN product_inputs p2 "
                    "ON p2.product_id=d2.product_id AND p2.product_revision=d2.product_revision "
                    "JOIN assets a2 ON a2.id=p2.asset_id "
                    "WHERE d2.recipient=? AND a2.scenic_area=? AND a2.id=? "
                    "AND d2.created_at>=? LIMIT 1",
                    (delivery["recipient"], item["scenic_area"],
                     item["current_asset_id"], delivery["created_at"]),
                ).fetchone()
                if refreshed:
                    continue
                results.append({
                    "scenic_area": item["scenic_area"],
                    "recipient": delivery["recipient"],
                    "delivery_id": delivery_id,
                    "product_id": delivery["product_id"],
                    "product_revision": delivery["product_revision"],
                    "stale_asset_id": item["asset_id"],
                    "current_asset_id": item["current_asset_id"],
                    "basis_announcement_id": item["basis_announcement_id"],
                })
        results.sort(key=lambda row: (row["scenic_area"], row["recipient"], row["delivery_id"]))
        return results
