"""检索轨迹与会话导出：字段齐全、脱敏、只导自己的柜子。不调模型。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.store.conversations import ConversationError, ConversationStore  # noqa: E402
from forge_lite.service.export import build_export, render_json, render_markdown, safe_filename  # noqa: E402
from forge_lite.retrieve.trace import build_trace, coverage_note, render_trace_markdown, summarize_routes  # noqa: E402


PAYLOAD = {
    "question": "去上海出差住一晚能报多少？",
    "queries": ["去上海出差住一晚能报多少？", "出差 上海 住宿 住宿费"],
    "intent": "factoid",
    "status": "ok",
    "routes": "bm25+dense+graph",
    "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
    "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
    "evidence": {
        "response_status": "answered",
        "allows_generation": True,
        "reason_codes": ["direct_support"],
        "coverage": 0.82,
        "missing_information": [],
    },
    "warn": "",
    "run_id": "run_demo",
    "conversation_id": "conv_demo",
    "attempts": 0,
}


class TraceTests(unittest.TestCase):
    def test_trace_exposes_every_panel_field(self):
        trace = build_trace(PAYLOAD).as_dict()
        self.assertEqual(trace["queries"][0], PAYLOAD["question"])
        self.assertEqual(trace["routes"], ["bm25", "dense", "graph"])
        self.assertEqual(trace["route_labels"], ["关键词", "向量", "图谱"])
        self.assertEqual(trace["status_label"], "已回答")
        self.assertTrue(trace["evidence"]["allows_generation"])
        self.assertEqual(trace["sources"][0]["marker"], "[1]")
        self.assertEqual(trace["run_id"], "run_demo")

    def test_steps_include_rewrite_evidence_budget(self):
        lanes = [step["lane"] for step in build_trace(PAYLOAD).as_dict()["steps"]]
        self.assertIn("rewrite", lanes)
        self.assertIn("evidence", lanes)
        self.assertIn("budget", lanes)

    def test_refusal_explains_why(self):
        payload = dict(PAYLOAD)
        payload["status"] = "refuse"
        payload["routes"] = ""
        payload["evidence"] = {
            "response_status": "insufficient_evidence",
            "allows_generation": False,
            "reason_codes": ["zero_results"],
        }
        trace = build_trace(payload)
        note = coverage_note(trace)
        self.assertIn("不够", note)
        self.assertIn("zero_results", note)
        self.assertEqual(summarize_routes(trace), "无召回")

    def test_markdown_tables_render(self):
        text = render_trace_markdown(build_trace(PAYLOAD))
        self.assertIn("| 环节 | 说明 |", text)
        self.assertIn("员工差旅管理制度.md#0", text)
        self.assertIn("检索用的查询", text)

    def test_empty_payload_does_not_crash(self):
        trace = build_trace({}).as_dict()
        self.assertEqual(trace["question"], "")
        self.assertEqual(trace["sources"], [])
        self.assertTrue(trace["steps"])

    def test_pipeline_ok_is_not_shown_as_evidence_code(self):
        """运行结局是 ok / refuse，资格码才是 answered / insufficient_evidence。
        轨迹接口曾经把 record.status 原样塞进 evidence.response_status，
        抽屉就会画出「证据 ok」这种内部切口。"""
        trace = build_trace({
            "question": "住宿上限？",
            "status": "ok",
            "evidence": {"response_status": "ok"},
        }).as_dict()
        self.assertEqual(trace["response_status"], "answered")
        self.assertEqual(trace["evidence_label"], "已回答")
        self.assertTrue(trace["evidence"]["allows_generation"])

    def test_pipeline_refuse_is_not_shown_as_evidence_code(self):
        trace = build_trace({
            "question": "年终奖？",
            "status": "refuse",
            "evidence": {"response_status": "refuse"},
        }).as_dict()
        self.assertEqual(trace["response_status"], "insufficient_evidence")
        self.assertEqual(trace["evidence_label"], "证据不足")
        self.assertFalse(trace["evidence"]["allows_generation"])


class ExportHelperTests(unittest.TestCase):
    def test_safe_filename_strips_unsafe_characters(self):
        self.assertEqual(safe_filename('差旅/报销:上限?<x>'), "差旅报销上限x")

    def test_safe_filename_falls_back_when_empty(self):
        self.assertEqual(safe_filename("///"), "conversation")
        self.assertEqual(safe_filename(""), "conversation")

    def test_safe_filename_truncates(self):
        self.assertLessEqual(len(safe_filename("问" * 100)), 40)


class ExportBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.tmp.name) / "c.sqlite")
        self.conv_id, self.run_id = self.store.record_answer(
            "it_staff",
            "去上海出差住一晚能报多少？",
            {
                "answer": "一线城市住宿上限 500 元 [1]。",
                "status": "ok",
                "intent": "factoid",
                "routes": "bm25+dense+graph",
                "warn": "联系 13812345678 核实",
                "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
                "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
                "queries": ["去上海出差住一晚能报多少？"],
                "actor": {"user_id": "it_staff", "name": "IT 员工", "role": "employee", "department": "it"},
            },
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_markdown_export_contains_question_answer_and_citation(self):
        bundle = build_export(self.store, self.conv_id, "it_staff", fmt="md")
        self.assertTrue(bundle.filename.endswith(".md"))
        self.assertIn("去上海出差住一晚能报多少？", bundle.content)
        self.assertIn("500 元", bundle.content)
        self.assertIn("`员工差旅管理制度.md#0`", bundle.content)

    def test_export_masks_pii(self):
        bundle = build_export(self.store, self.conv_id, "it_staff")
        self.assertNotIn("13812345678", bundle.content)

    def test_json_export_parses_and_masks(self):
        bundle = build_export(self.store, self.conv_id, "it_staff", fmt="json")
        data = json.loads(bundle.content)
        self.assertEqual(data["conversation"]["id"], self.conv_id)
        self.assertNotIn("13812345678", bundle.content)

    def test_other_badge_cannot_export(self):
        with self.assertRaises(ConversationError):
            build_export(self.store, self.conv_id, "hr_staff")

    def test_render_json_matches_bundle(self):
        detail = self.store.get_conversation(self.conv_id, "it_staff")
        self.assertEqual(json.loads(render_json(detail))["conversation"]["id"], self.conv_id)

    def test_markdown_of_empty_cabinet_is_honest(self):
        empty = self.store.create_conversation("it_staff", title="空柜子")
        text = render_markdown(self.store.get_conversation(empty.id, "it_staff"))
        self.assertIn("还没有消息", text)


class RunDetailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.tmp.name) / "c.sqlite")
        self.conv_id, self.run_id = self.store.record_answer("it_staff", "打印机 E3？", {
            "answer": "取出卡纸 [1]。", "status": "ok", "routes": "bm25+graph",
            "citations": [{"marker": "[1]", "doc_id": "运维故障案例.md#0"}],
            "contexts": ["关闭电源取出卡纸"], "queries": ["打印机 E3？"], "warn": "",
        })

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_get_run_returns_record(self):
        run = self.store.get_run(self.run_id, "it_staff")
        self.assertEqual(run.question, "打印机 E3？")
        self.assertEqual(run.routes, "bm25+graph")

    def test_latest_run_points_at_last_answer(self):
        self.store.record_answer("it_staff", "第二问", {
            "answer": "答二 [1]。", "status": "ok", "routes": "dense",
            "citations": [], "contexts": [], "queries": ["第二问"], "warn": "",
        }, conversation_id=self.conv_id)
        latest = self.store.latest_run(self.conv_id, "it_staff")
        self.assertEqual(latest.question, "第二问")

    def test_other_badge_cannot_read_run(self):
        with self.assertRaises(ConversationError):
            self.store.get_run(self.run_id, "hr_staff")


if __name__ == "__main__":
    unittest.main()


class LaneRankTests(unittest.TestCase):
    """三路召回名次：检索明细落盘 → 轨迹面板可复现，刷新后不重跑检索。"""

    DETAILS = [
        {"doc_id": "员工差旅管理制度.md#0", "route": "graph+bm25+dense", "route_rank": 1,
         "fused_rank": 1, "why": "被 graph 召回（该路第 1 名），融合后第 1 名"},
        {"doc_id": "产品FAQ.md#0", "route": "dense", "route_rank": 2,
         "fused_rank": 2, "why": "被 dense 召回（该路第 2 名），融合后第 2 名"},
    ]

    def test_lanes_expose_primary_rank_only(self):
        trace = build_trace({"question": "住宿上限？", "source_details": self.DETAILS}).as_dict()
        rows = trace["lanes"]
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["primary"], "graph")
        self.assertEqual(first["fused_rank"], 1)
        ids = [lane["id"] for lane in first["lanes"]]
        self.assertEqual(ids, ["graph", "bm25", "dense"])
        primary = next(lane for lane in first["lanes"] if lane["id"] == "graph")
        others = [lane for lane in first["lanes"] if lane["id"] != "graph"]
        self.assertEqual(primary["rank"], 1)
        self.assertTrue(all(lane["rank"] is None for lane in others))

    def test_lanes_sorted_by_fused_rank(self):
        trace = build_trace({"question": "q", "source_details": list(reversed(self.DETAILS))}).as_dict()
        self.assertEqual([row["fused_rank"] for row in trace["lanes"]], [1, 2])

    def test_run_record_persists_lane_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStore(Path(tmp) / "c.sqlite")
            conv_id, run_id = store.record_answer("it_staff", "住宿上限？", {
                "answer": "上限 500 元 [1]。", "status": "ok", "routes": "graph+bm25+dense",
                "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
                "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
                "source_details": self.DETAILS,
                "queries": ["住宿上限？"], "warn": "",
            })
            run = store.get_run(run_id, "it_staff")
            store.close()
        self.assertEqual(run.contexts[0]["route"], "graph+bm25+dense")
        self.assertEqual(run.contexts[0]["route_rank"], 1)
        trace = build_trace({"question": run.question, "source_details": run.contexts,
                             "routes": run.routes}).as_dict()
        self.assertEqual(trace["lanes"][0]["primary"], "graph")

    def test_old_records_without_details_still_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStore(Path(tmp) / "c.sqlite")
            _, run_id = store.record_answer("it_staff", "老记录", {
                "answer": "答 [1]。", "status": "ok", "routes": "bm25",
                "citations": [{"marker": "[1]", "doc_id": "a.md#0"}],
                "contexts": ["片段"], "queries": ["老记录"], "warn": "",
            })
            run = store.get_run(run_id, "it_staff")
            store.close()
        trace = build_trace({"question": run.question, "source_details": run.contexts}).as_dict()
        self.assertTrue(trace["lanes"])
        self.assertEqual(trace["lanes"][0]["lanes"], [])

    def test_markdown_export_includes_lane_table(self):
        text = render_trace_markdown(build_trace({"question": "q", "lanes": [
            {"fused_rank": 1, "doc_id": "a.md#0", "primary": "graph",
             "lanes": [{"id": "graph", "label": "图谱", "rank": 1}]},
        ]}))
        self.assertIn("| 融合名次 | 出处 | 各路召回 |", text)
        self.assertIn("图谱 第 1 名", text)


class TraceRoundTripTests(unittest.TestCase):
    """轨迹导出与再渲染：存下来的轨迹要能原样重建，不靠重跑检索。"""

    def test_exported_trace_renders_again(self):
        source = build_trace({
            "question": "住宿上限？",
            "queries": ["住宿上限？", "住宿 上限"],
            "status": "ok",
            "routes": "graph+bm25",
            "source_details": [{
                "doc_id": "员工差旅管理制度.md#0", "route": "graph+bm25",
                "route_rank": 1, "fused_rank": 1, "why": "被 graph 召回",
            }],
        })
        dumped = source.as_dict()
        again = build_trace(dumped).as_dict()
        self.assertEqual(again["lanes"], dumped["lanes"])
        self.assertEqual(again["queries"], dumped["queries"])
        self.assertIn("图谱 第 1 名", render_trace_markdown(again))


class StoredIntentLabelTests(unittest.TestCase):
    """会话柜里的助手消息要带中文意图标签——刷新后不退回英文键名。"""

    def test_run_record_keeps_intent_label(self):
        from forge_lite.core.labels import intent_text
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStore(Path(tmp) / "c.sqlite")
            conv_id, _ = store.record_answer("it_staff", "打印机 E3 怎么处理？", {
                "answer": "取出卡纸 [1]。", "status": "ok", "intent": "procedural",
                "intent_label": intent_text("procedural"),
                "routes": "bm25", "citations": [], "contexts": [], "queries": ["q"], "warn": "",
            })
            detail = store.get_conversation(conv_id, "it_staff")
            store.close()
        payload = detail.messages[1].payload
        self.assertEqual(payload["intent_label"], "流程")
