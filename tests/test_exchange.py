import tempfile
import unittest
from pathlib import Path

from exchange import Exchange


class ExchangeFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Exchange(Path(self.temp.name) / "exchange.db")
        self.service.catalog.register("flow", "机构甲", "甲地", "restricted", [("count", "通行计数", "integer", False)], "2026-11-01")
        self.service.catalog.ingest("item-1", "flow", {"count": 8}, "2026-11-02")
        self.service.grants.issue("g-1", "flow", "机构乙", "运行协调", "2026-12-31", "2026-11-03")
        self.service.policies.set("甲地", "restricted", "运行协调", "allow", "2026-11-03", "机构甲")
        self.revision = self.service.products.assemble("report", "通行观察", ["item-1"], "2026-11-04", "机构甲")

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_delivery_keeps_revision_and_request_identity(self):
        desk = self.service.delivery
        receipt = desk.send("d-1", "report", self.revision, "机构乙", "运行协调", "2026-11-05")
        self.assertEqual(receipt["product_revision"], self.revision)
        self.assertEqual(receipt, desk.send("d-1", "report", self.revision, "机构乙", "运行协调", "2026-11-05"))
        with self.assertRaises(ValueError):
            desk.send("d-1", "report", self.revision, "其他机构", "运行协调", "2026-11-05")

    def test_grant_and_policy_gate_delivery(self):
        with self.assertRaises(PermissionError):
            self.service.delivery.send("d-2", "report", self.revision, "陌生机构", "运行协调", "2026-11-05")
        self.service.policies.set("甲地", "restricted", "运行协调", "deny", "2026-11-06", "机构甲")
        with self.assertRaises(PermissionError):
            self.service.delivery.send("d-3", "report", self.revision, "机构乙", "运行协调", "2026-11-07")
        self.assertTrue(self.service.history("report"))

    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):
            self.service.catalog.ingest("item-2", "flow", {"unknown": 9}, "2026-11-03")


if __name__ == "__main__":
    unittest.main()
