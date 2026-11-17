import argparse
import json

from .service import Exchange


def show(title, value):
    print(f"==== {title} ====")
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    print()


def main():
    parser = argparse.ArgumentParser(description="景区资料本地协作演练")
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    service = Exchange(args.database)
    try:
        # 1. 主管部门登记公告来源，合作机构持有使用许可。
        service.catalog.register(
            "bureau", "地方主管部门", "甲地", "public",
            [("listed", "摘牌状态", "text", False), ("reason", "依据", "text", False)],
            "2026-11-01",
        )
        service.grants.issue("g-1", "bureau", "合作机构甲", "资料协作", "2026-12-31", "2026-11-01")
        service.policies.set("甲地", "public", "资料协作", "allow", "2026-11-01", "地方主管部门")

        # 2. 首发摘牌公告，按景区登记目录条目并交付给合作机构。
        service.announcements.publish(
            "ann-1", "notice-2026-09", "bureau",
            [{"scenic_area": "云山景区", "listed": "摘牌", "reason": "初版公告"},
             {"scenic_area": "碧水景区", "listed": "摘牌", "reason": "初版公告"}],
            "2026-11-02", "地方主管部门",
        )
        service.catalog.ingest("asset-yunshan-v1", "bureau",
                               {"listed": "摘牌", "reason": "初版公告"}, "2026-11-02",
                               scenic_area="云山景区", basis_announcement_id="ann-1")
        service.catalog.ingest("asset-bishui-v1", "bureau",
                               {"listed": "摘牌", "reason": "初版公告"}, "2026-11-02",
                               scenic_area="碧水景区", basis_announcement_id="ann-1")
        revision_v1 = service.products.assemble(
            "dossier", "摘牌名单资料", ["asset-yunshan-v1", "asset-bishui-v1"],
            "2026-11-03", "资料室")
        service.delivery.send("d-1", "dossier", revision_v1, "合作机构甲", "资料协作", "2026-11-04")

        # 3. 主管部门更正名单：云山景区移出摘牌范围，追加更正公告与新条目。
        service.announcements.correct(
            "ann-2", "notice-2026-09", "bureau", "ann-1",
            [{"scenic_area": "云山景区", "listed": "保留", "reason": "名单更正"},
             {"scenic_area": "碧水景区", "listed": "摘牌", "reason": "名单更正"}],
            "2026-11-10", "地方主管部门",
        )
        service.catalog.ingest("asset-yunshan-v2", "bureau",
                               {"listed": "保留", "reason": "名单更正"}, "2026-11-10",
                               scenic_area="云山景区", basis_announcement_id="ann-2")
        service.catalog.ingest("asset-bishui-v2", "bureau",
                               {"listed": "摘牌", "reason": "名单更正"}, "2026-11-10",
                               scenic_area="碧水景区", basis_announcement_id="ann-2")
        show("旧回执 d-1 当时依据与受影响范围",
             service.announcements.explain_delivery("d-1"))
        show("按景区查明待重新确认",
             service.announcements.pending_reconfirmations(scenic_area="云山景区"))

        # 4. 含旧条目的产品不能再被新领取。
        try:
            service.delivery.send("d-stale", "dossier", revision_v1, "合作机构甲",
                                  "资料协作", "2026-11-11")
        except PermissionError as error:
            show("旧版本新领取被拒绝", error.args[0])

        # 5. 用当前可核实条目重新编排并交付，待重新确认清单随之消除。
        revision_v2 = service.products.assemble(
            "dossier", "摘牌名单资料", ["asset-yunshan-v2", "asset-bishui-v2"],
            "2026-11-12", "资料室")
        show("重新确认后的新回执",
             service.delivery.send("d-2", "dossier", revision_v2, "合作机构甲",
                                   "资料协作", "2026-11-13"))
        show("重新确认后剩余待办", service.announcements.pending_reconfirmations())

        # 6. 更正被再次撤回：只追加撤回记录，状态由公告链重新折叠。
        service.announcements.withdraw("ann-3", "notice-2026-09", "bureau",
                                       "ann-2", "2026-11-15", "地方主管部门")
        show("撤回后的当前可核实条目",
             {"云山景区": service.announcements.current_asset("云山景区")["id"],
              "碧水景区": service.announcements.current_asset("碧水景区")["id"]})
        show("撤回后公告链审计轨迹", service.history("notice-2026-09"))
    finally:
        service.close()


if __name__ == "__main__":
    main()
