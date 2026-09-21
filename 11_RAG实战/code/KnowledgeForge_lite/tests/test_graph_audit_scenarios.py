"""图谱邻接、审计账、课堂剧本：都不调模型。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.store.audit import AuditLog  # noqa: E402
from forge_lite.service.graph_view import list_entities, neighborhood  # noqa: E402
from forge_lite.answer.scenarios import SCENARIOS, visibility_check  # noqa: E402


class GraphViewTests(unittest.TestCase):
    def test_it_cannot_see_pay_band_edges(self):
        it_view = neighborhood("P6薪酬带宽", "it_staff")
        finance_view = neighborhood("P6薪酬带宽", "finance_head")
        self.assertEqual(it_view.edges, [])
        self.assertTrue(finance_view.edges)
        self.assertTrue(all("财务薪酬密级.md" in edge.source for edge in finance_view.edges))

    def test_travel_entity_visible_to_hr(self):
        view = neighborhood("一线城市住宿标准", "hr_staff")
        self.assertTrue(view.edges)
        entities = list_entities("hr_staff")
        self.assertTrue(any("住宿" in name or "Forge" in name or "锁屏" in name for name in entities))
        self.assertFalse(any("P6" in name or "薪酬" in name for name in entities))


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = AuditLog(Path(self.tmp.name) / "audit.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_employee_cannot_read_admin_ledger(self):
        self.log.record("ask", "admin", question="P6 薪酬带宽是多少？", status="ok")
        self.log.record("ask", "it_staff", question="住宿上限？", status="ok")
        it_rows = self.log.for_actor("it_staff")
        self.assertEqual({row["user_id"] for row in it_rows}, {"it_staff"})
        admin_rows = self.log.for_actor("admin")
        self.assertGreaterEqual(len(admin_rows), 2)
        sensitive = self.log.sensitive_asks("admin")
        self.assertTrue(any("薪酬" in (row.get("question") or "") for row in sensitive))

    def test_masks_phone_on_write(self):
        event = self.log.record("ask", "it_staff", question="电话 13812345678")
        self.assertNotIn("13812345678", event.question)
        line = Path(self.log.path).read_text(encoding="utf-8").strip().splitlines()[-1]
        self.assertNotIn("13812345678", json.loads(line)["question"])


class ScenarioCatalogTests(unittest.TestCase):
    def test_every_visibility_scenario_matches_acl_matrix(self):
        failures = []
        for item in SCENARIOS:
            ok, reason = visibility_check(item)
            if not ok:
                failures.append(f"{item.id}: {reason}")
        self.assertEqual(failures, [])

    def test_pay_band_pair_still_opposite(self):
        it_ok, _ = visibility_check(next(item for item in SCENARIOS if item.id == "pay-it"))
        finance_ok, _ = visibility_check(next(item for item in SCENARIOS if item.id == "pay-finance"))
        self.assertTrue(it_ok)
        self.assertTrue(finance_ok)
        self.assertEqual(next(item for item in SCENARIOS if item.id == "pay-it").expect, "refuse")
        self.assertEqual(next(item for item in SCENARIOS if item.id == "pay-finance").expect, "answer")


if __name__ == "__main__":
    unittest.main()
