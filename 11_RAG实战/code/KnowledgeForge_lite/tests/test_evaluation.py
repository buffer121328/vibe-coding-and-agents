"""评测区服务层：行为判定、检索命中、报告落档。生成模型一律用替身。"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite import config  # noqa: E402
from forge_lite.answer import evaluation as ev  # noqa: E402


def fake_ask(question, user_id=None, persist=True, **kwargs):
    """替身：按问题内容给不同结局，覆盖作答 / 拒答两条路。"""
    table = {
        "住宿上限是多少？": {
            "status": "ok", "answer": "上限 500 元 [1]。", "routes": "bm25+dense",
            "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
            "response_status": "answered", "warn": "", "contexts": ["一线城市住宿标准 500 元"],
        },
        "年终奖几月？": {
            "status": "refuse", "answer": "抱歉，知识库中暂无可靠依据回答这个问题，已为你转人工。",
            "routes": "", "citations": [], "response_status": "insufficient_evidence",
            "warn": "证据资格：证据不足", "contexts": [],
        },
        "E3 怎么处理？": {
            "status": "ok", "answer": "取出卡纸 [1]。", "routes": "bm25",
            "citations": [{"marker": "[1]", "doc_id": "产品FAQ.md#0"}],
            "response_status": "answered", "warn": "", "contexts": ["FAQ"],
        },
    }
    return dict(table.get(question, {"status": "refuse", "answer": "", "citations": [], "routes": ""}))


ANSWER_CASE = {"id": "cap", "question": "住宿上限是多少？", "expect": "answer",
               "expected_docs": ["员工差旅管理制度.md"], "reference": "500 元",
               "user_id": "it_staff"}
REFUSE_CASE = {"id": "bonus", "question": "年终奖几月？", "expect": "refuse",
               "expected_docs": [], "reference": "应拒答", "user_id": "it_staff"}
WRONG_DOC_CASE = {"id": "e3", "question": "E3 怎么处理？", "expect": "answer",
                  "expected_docs": ["运维故障案例.md"], "reference": "取卡纸",
                  "user_id": "it_staff"}


class RunCaseTests(unittest.TestCase):
    def test_answer_case_with_hit_passes(self):
        result = ev.run_case(ANSWER_CASE, ask_fn=fake_ask)
        self.assertTrue(result.behavior_ok)
        self.assertEqual(result.hit, 1.0)
        self.assertTrue(result.passed)
        self.assertIn("符合预期", result.reason)

    def test_refuse_case_passes_without_any_hit(self):
        result = ev.run_case(REFUSE_CASE, ask_fn=fake_ask)
        self.assertTrue(result.behavior_ok)
        self.assertEqual(result.expected_docs, [])
        self.assertTrue(result.passed)
        self.assertEqual(result.status, "refuse")

    def test_expected_answer_but_refused_fails_with_reason(self):
        case = dict(ANSWER_CASE, question="不存在的问法")
        result = ev.run_case(case, ask_fn=fake_ask)
        self.assertFalse(result.behavior_ok)
        self.assertFalse(result.passed)
        self.assertIn("期望作答", result.reason)

    def test_expected_refusal_but_answered_fails(self):
        case = dict(REFUSE_CASE, question="住宿上限是多少？")
        result = ev.run_case(case, ask_fn=fake_ask)
        self.assertFalse(result.behavior_ok)
        self.assertIn("期望拒答", result.reason)

    def test_answered_but_wrong_doc_fails_on_hit(self):
        result = ev.run_case(WRONG_DOC_CASE, ask_fn=fake_ask)
        self.assertTrue(result.behavior_ok)
        self.assertEqual(result.hit, 0.0)
        self.assertFalse(result.passed)
        self.assertIn("未召回期望文档", result.reason)

    def test_latency_and_preview_recorded(self):
        result = ev.run_case(ANSWER_CASE, ask_fn=fake_ask)
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertIn("500 元", result.answer_preview)
        self.assertEqual(result.cited_docs, ["员工差旅管理制度.md"])

    def test_behavior_only_pass_when_no_expected_docs(self):
        case = {"id": "free", "question": "住宿上限是多少？", "expect": "answer",
                "expected_docs": [], "reference": "x", "user_id": "hr_staff"}
        result = ev.run_case(case, ask_fn=fake_ask)
        self.assertTrue(result.passed)


class GateCliTests(unittest.TestCase):
    def test_run_gate_passes_when_behavior_and_hits_match(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = ev.run_gate([ANSWER_CASE, REFUSE_CASE], ask_fn=fake_ask)
        self.assertTrue(ok)
        text = buf.getvalue()
        self.assertIn("门禁层", text)
        self.assertIn("不调裁判", text)
        self.assertIn("04_ragas_eval.py", text)

    def test_run_gate_fails_when_expected_doc_is_missing(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = ev.run_gate([WRONG_DOC_CASE], ask_fn=fake_ask)
        self.assertFalse(ok)
        self.assertIn("未召回期望文档", buf.getvalue())


class SummarizeTests(unittest.TestCase):
    def _results(self):
        return [ev.run_case(case, ask_fn=fake_ask) for case in (ANSWER_CASE, REFUSE_CASE, WRONG_DOC_CASE)]

    def test_rates_and_gate(self):
        summary = ev.summarize(self._results())
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["passed"], 2)
        self.assertAlmostEqual(summary["pass_rate"], 2 / 3)
        self.assertEqual(summary["behavior_rate"], 1.0)
        self.assertAlmostEqual(summary["hit_rate"], 0.5)   # 两条有期望文档，命中一条
        self.assertFalse(summary["passed_gate"])           # 2/3 < 0.8
        self.assertEqual(summary["gate"], config.PASS_RATE_GATE)

    def test_empty_summary_is_safe(self):
        summary = ev.summarize([])
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["pass_rate"], 0.0)
        self.assertEqual(summary["avg_latency_ms"], 0)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name) / "runtime"
        self.patch = patch.object(config, "RUNTIME_DIR", self.runtime)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_save_then_list_then_load(self):
        results = [ev.run_case(case, ask_fn=fake_ask) for case in (ANSWER_CASE, REFUSE_CASE)]
        report = ev.save_report(results, note="课堂演练")
        self.assertTrue(report["path"].startswith("eval-"))
        self.assertTrue((ev.reports_dir() / report["path"]).exists())

        rows = ev.list_reports(limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total"], 2)
        self.assertEqual(rows[0]["passed"], 2)
        self.assertEqual(rows[0]["note"], "课堂演练")

        loaded = ev.load_report(report["path"])
        self.assertEqual(len(loaded["cases"]), 2)
        self.assertEqual(loaded["cases"][0]["question"], ANSWER_CASE["question"])

    def test_load_rejects_path_traversal(self):
        for name in ("../secret.json", "eval-../x.json", "notes.json"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    ev.load_report(name)

    def test_missing_report_raises(self):
        with self.assertRaises(FileNotFoundError):
            ev.load_report("eval-19700101-000000.json")

    def test_list_is_empty_without_dir(self):
        self.assertEqual(ev.list_reports(), [])


class CasesIndexTests(unittest.TestCase):
    def test_cases_carry_expectation_and_badge(self):
        rows = ev.cases_index()
        self.assertGreaterEqual(len(rows), 6)
        for row in rows:
            with self.subTest(case=row["id"]):
                self.assertIn(row["expect"], {"answer", "refuse"})
                self.assertTrue(row["actor_name"])
                if row["expect"] == "refuse":
                    self.assertEqual(row["expected_docs"], [])
                else:
                    self.assertTrue(row["expected_docs"])

    def test_every_case_has_unique_id(self):
        ids = [row["id"] for row in ev.cases_index()]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
