import tempfile
import unittest
from pathlib import Path

from exchange import Exchange


class CorrectionPropagationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Exchange(Path(self.temp.name) / "exchange.db")
        svc = self.service
        # 主管部门作为公告来源，目录条目按景区登记。
        svc.catalog.register(
            "bureau", "地方主管部门", "甲地", "public",
            [("listed", "摘牌状态", "text", False), ("reason", "依据", "text", False)],
            "2026-11-01",
        )
        svc.grants.issue("g-1", "bureau", "合作机构甲", "资料协作", "2026-12-31", "2026-11-01")
        svc.policies.set("甲地", "public", "资料协作", "allow", "2026-11-01", "地方主管部门")

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def _publish_initial(self):
        svc = self.service
        areas = [{"scenic_area": "云山景区", "listed": "摘牌", "reason": "初版公告"}]
        svc.announcements.publish("ann-1", "notice-2026-09", "bureau", areas, "2026-11-02", "地方主管部门")
        svc.catalog.ingest(
            "asset-yunshan-v1", "bureau",
            {"listed": "摘牌", "reason": "初版公告"}, "2026-11-02",
            scenic_area="云山景区", basis_announcement_id="ann-1",
        )
        revision = svc.products.assemble("dossier-yunshan", "云山摘牌资料", ["asset-yunshan-v1"],
                                         "2026-11-03", "资料室")
        receipt = svc.delivery.send("d-old", "dossier-yunshan", revision, "合作机构甲",
                                    "资料协作", "2026-11-04")
        return receipt

    def test_correction_chain_keeps_old_version_and_marks_affected_scope(self):
        svc = self.service
        self._publish_initial()

        # 主管部门发布更正：云山景区移出摘牌名单。
        corrected = [{"scenic_area": "云山景区", "listed": "保留", "reason": "名单更正"}]
        svc.announcements.correct("ann-2", "notice-2026-09", "bureau", "ann-1",
                                  corrected, "2026-11-10", "地方主管部门")
        svc.catalog.ingest(
            "asset-yunshan-v2", "bureau",
            {"listed": "保留", "reason": "名单更正"}, "2026-11-10",
            scenic_area="云山景区", basis_announcement_id="ann-2",
        )

        # 旧公告与旧条目原样保留，但已不再有效；当前可核实版本指向新条目。
        self.assertFalse(svc.announcements.is_effective("ann-1"))
        self.assertTrue(svc.announcements.is_effective("ann-2"))
        self.assertEqual(svc.announcements.current_asset("云山景区")["id"], "asset-yunshan-v2")

        # 旧回执仍可说明当时依据，并提示受影响范围。
        explanation = svc.announcements.explain_delivery("d-old")
        self.assertEqual(explanation["items"][0]["basis_announcement_id"], "ann-1")
        self.assertEqual(explanation["items"][0]["status"], "stale")
        self.assertEqual(explanation["affected_areas"], ["云山景区"])

        # 待重新确认：可按景区、按领取方查明。
        pending = svc.announcements.pending_reconfirmations(scenic_area="云山景区")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["recipient"], "合作机构甲")
        self.assertEqual(pending[0]["current_asset_id"], "asset-yunshan-v2")
        self.assertEqual(
            svc.announcements.pending_reconfirmations(recipient="合作机构甲"), pending
        )
        self.assertEqual(svc.announcements.pending_reconfirmations(recipient="无人领取"), [])

    def test_new_claim_only_obtains_current_verifiable_version(self):
        svc = self.service
        self._publish_initial()
        corrected = [{"scenic_area": "云山景区", "listed": "保留", "reason": "名单更正"}]
        svc.announcements.correct("ann-2", "notice-2026-09", "bureau", "ann-1",
                                  corrected, "2026-11-10", "地方主管部门")
        svc.catalog.ingest(
            "asset-yunshan-v2", "bureau",
            {"listed": "保留", "reason": "名单更正"}, "2026-11-10",
            scenic_area="云山景区", basis_announcement_id="ann-2",
        )

        # 含旧条目的产品修订无法再被新领取，回执中给出 stale-announcement 原因。
        with self.assertRaises(PermissionError) as blocked:
            svc.delivery.send("d-stale", "dossier-yunshan", 1, "合作机构甲",
                              "资料协作", "2026-11-11")
        reasons = blocked.exception.args[0]
        self.assertIn("stale-announcement", {reason["reason"] for reason in reasons})

        # 用当前条目重新编排后可以正常领取，且新回执固化新的依据快照。
        revision = svc.products.assemble("dossier-yunshan", "云山摘牌资料",
                                         ["asset-yunshan-v2"], "2026-11-12", "资料室")
        receipt = svc.delivery.send("d-new", "dossier-yunshan", revision, "合作机构甲",
                                    "资料协作", "2026-11-13")
        self.assertEqual(receipt["product_revision"], revision)
        import json
        snapshot = json.loads(receipt["basis_snapshot"])
        self.assertEqual(snapshot[0]["basis_announcement_id"], "ann-2")

        # 新领取覆盖同一景区的当前条目后，待重新确认清单随之消除。
        self.assertEqual(svc.announcements.pending_reconfirmations(scenic_area="云山景区"), [])

    def test_withdrawing_correction_does_not_rewind_messages(self):
        svc = self.service
        self._publish_initial()
        corrected = [{"scenic_area": "云山景区", "listed": "保留", "reason": "名单更正"}]
        svc.announcements.correct("ann-2", "notice-2026-09", "bureau", "ann-1",
                                  corrected, "2026-11-10", "地方主管部门")
        svc.catalog.ingest(
            "asset-yunshan-v2", "bureau",
            {"listed": "保留", "reason": "名单更正"}, "2026-11-10",
            scenic_area="云山景区", basis_announcement_id="ann-2",
        )

        # 撤回更正：只追加一条撤回记录，旧公告、更正公告和各自条目都还在。
        svc.announcements.withdraw("ann-3", "notice-2026-09", "bureau",
                                   "ann-2", "2026-11-15", "地方主管部门")
        versions = svc.announcements.versions("notice-2026-09")
        self.assertEqual([v["kind"] for v in versions], ["publish", "correction", "withdrawal"])
        self.assertTrue(svc.announcements.is_effective("ann-1"))
        self.assertFalse(svc.announcements.is_effective("ann-2"))

        # 当前可核实版本由整条链重新折叠得出，而不是删除或倒放最后一条消息。
        self.assertEqual(svc.announcements.current_asset("云山景区")["id"], "asset-yunshan-v1")

        # 撤回后：基于更正条目的新领取被拒，最初的回执重新与当前版本一致，
        # 待重新确认清单自动清空——状态完全派生自链，没有任何回写动作。
        revision2 = svc.products.assemble("dossier-yunshan", "云山摘牌资料",
                                          ["asset-yunshan-v2"], "2026-11-16", "资料室")
        with self.assertRaises(PermissionError):
            svc.delivery.send("d-after-withdraw", "dossier-yunshan", revision2,
                              "合作机构甲", "资料协作", "2026-11-16")
        explanation = svc.announcements.explain_delivery("d-old")
        self.assertEqual(explanation["items"][0]["status"], "current")
        self.assertEqual(svc.announcements.pending_reconfirmations(scenic_area="云山景区"), [])

        # 审计轨迹保留全部三次公告动作，顺序不可变。
        actions = [entry["action"] for entry in svc.history("notice-2026-09")]
        self.assertEqual(actions, ["announcement.publish", "announcement.correct", "announcement.withdraw"])

    def test_pending_reconfirmations_tracked_per_recipient(self):
        svc = self.service
        svc.grants.issue("g-2", "bureau", "合作机构乙", "资料协作", "2026-12-31", "2026-11-01")
        self._publish_initial()
        # 第二家领取方也领取了同一旧版本。
        svc.delivery.send("d-old-b", "dossier-yunshan", 1, "合作机构乙",
                          "资料协作", "2026-11-05")
        corrected = [{"scenic_area": "云山景区", "listed": "保留", "reason": "名单更正"}]
        svc.announcements.correct("ann-2", "notice-2026-09", "bureau", "ann-1",
                                  corrected, "2026-11-10", "地方主管部门")
        svc.catalog.ingest(
            "asset-yunshan-v2", "bureau",
            {"listed": "保留", "reason": "名单更正"}, "2026-11-10",
            scenic_area="云山景区", basis_announcement_id="ann-2",
        )

        pending_all = svc.announcements.pending_reconfirmations()
        self.assertEqual({row["recipient"] for row in pending_all},
                         {"合作机构甲", "合作机构乙"})
        self.assertEqual(
            svc.announcements.pending_reconfirmations(recipient="合作机构乙")[0]["delivery_id"],
            "d-old-b",
        )

        # 只有机构甲领取了当前版本：机构甲的待办消解，机构乙仍待重新确认。
        revision = svc.products.assemble("dossier-yunshan", "云山摘牌资料",
                                         ["asset-yunshan-v2"], "2026-11-12", "资料室")
        svc.delivery.send("d-new-a", "dossier-yunshan", revision, "合作机构甲",
                          "资料协作", "2026-11-13")
        remaining = svc.announcements.pending_reconfirmations(scenic_area="云山景区")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["recipient"], "合作机构乙")

    def test_relation_validation(self):
        svc = self.service
        areas = [{"scenic_area": "云山景区", "listed": "摘牌", "reason": "初版公告"}]
        svc.announcements.publish("ann-1", "notice-x", "bureau", areas,
                                  "2026-11-02", "地方主管部门")
        # 更正必须指向同系列内已存在的版本。
        with self.assertRaises(ValueError):
            svc.announcements.correct("ann-bad", "notice-x", "bureau", "missing",
                                      areas, "2026-11-03", "地方主管部门")
        # 撤回只能针对更正公告，不能针对首发公告。
        with self.assertRaises(ValueError):
            svc.announcements.withdraw("ann-w", "notice-x", "bureau",
                                       "ann-1", "2026-11-04", "地方主管部门")
        # 撤回不携带目录条目。
        svc.announcements.correct("ann-2", "notice-x", "bureau", "ann-1",
                                  areas, "2026-11-05", "地方主管部门")
        with self.assertRaises(ValueError):
            svc.announcements._issue(
                "ann-w3", "notice-x", "withdrawal", "bureau", "2026-11-06",
                "地方主管部门", areas, "ann-2", "withdraws",
            )


if __name__ == "__main__":
    unittest.main()
