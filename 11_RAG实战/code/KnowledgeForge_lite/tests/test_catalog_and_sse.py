"""目录 ACL 与 SSE 协议：预览走同一把工牌，引用必须先于正文。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.data.acl_matrix import EXPECTED_MATRIX, assert_expected, hidden_sources, visible_sources  # noqa: E402
from forge_lite.data.catalog import (  # noqa: E402
    get_chunk,
    highlight_span,
    list_documents,
    parse_doc_id,
    visible_chunks,
)
from forge_lite.answer.classroom import PROMPTS, prompts_for  # noqa: E402
from forge_lite.core.sseutil import (  # noqa: E402
    SSEProtocolError,
    assert_safe_order,
    join_deltas,
    last_done,
    parse_stream,
    stream_answer,
)


CHUNKS = [
    {"source": "员工差旅管理制度.md", "chunk_index": 0, "text": "住宿上限 500 元",
     "department": "company", "sensitivity": "public", "acl": "employee"},
    {"source": "运维故障案例.md", "chunk_index": 0, "text": "打印机 E3 取出卡纸",
     "department": "it", "sensitivity": "department", "acl": "employee"},
    {"source": "财务薪酬密级.md", "chunk_index": 0, "text": "P6 年薪 35 万至 45 万",
     "department": "finance", "sensitivity": "restricted", "acl": "restricted"},
]


class AclMatrixTests(unittest.TestCase):
    def test_expected_matrix_still_holds(self):
        self.assertEqual(assert_expected(EXPECTED_MATRIX), [])

    def test_hr_cannot_preview_pay_band(self):
        self.assertIsNone(get_chunk("财务薪酬密级.md", 0, "hr_staff", CHUNKS))
        self.assertIsNone(get_chunk("运维故障案例.md", 0, "hr_staff", CHUNKS))
        names = [card.source for card in list_documents("hr_staff", CHUNKS).documents]
        self.assertNotIn("财务薪酬密级.md", names)
        self.assertIn("员工差旅管理制度.md", names)

    def test_finance_head_can_preview_pay_band(self):
        preview = get_chunk("财务薪酬密级.md", 0, "finance_head", CHUNKS)
        self.assertIsNotNone(preview)
        self.assertIn("35 万", preview.text)

    def test_hidden_count_explains_empty_catalog(self):
        snapshot = list_documents("hr_staff", CHUNKS)
        self.assertGreaterEqual(snapshot.hidden_count, 1)
        self.assertEqual(set(visible_sources("it_staff")) - set(hidden_sources("it_staff")),
                         set(visible_sources("it_staff")))

    def test_parse_doc_id(self):
        self.assertEqual(parse_doc_id("员工差旅管理制度.md#2"), ("员工差旅管理制度.md", 2))
        self.assertIsNone(parse_doc_id("没有井号"))
        self.assertEqual(highlight_span("abcdef", "cd")["hit"], "cd")

    def test_visible_chunks_uses_same_authorize(self):
        it_seen = {item["source"] for item in visible_chunks("it_staff", CHUNKS)}
        self.assertIn("运维故障案例.md", it_seen)
        self.assertNotIn("财务薪酬密级.md", it_seen)


class SseProtocolTests(unittest.TestCase):
    def test_citations_before_body_and_done_last(self):
        frames = parse_stream("".join(stream_answer(
            "住宿上限 500 元 [1]。",
            [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
            {"status": "ok", "conversation_id": "conv_1"},
            size=8,
        )))
        assert_safe_order(frames)
        self.assertEqual(frames[0].event, "citations")
        self.assertEqual(join_deltas(frames), "住宿上限 500 元 [1]。")
        self.assertEqual(last_done(frames)["conversation_id"], "conv_1")

    def test_done_without_citations_is_protocol_error(self):
        with self.assertRaises(SSEProtocolError):
            assert_safe_order(parse_stream("event: done\ndata: {\"status\":\"ok\"}\n\n"))

    def test_body_before_citations_is_protocol_error(self):
        blob = "data: {\"delta\":\"先漏出来\"}\n\nevent: citations\ndata: []\n\nevent: done\ndata: {\"status\":\"ok\"}\n\n"
        with self.assertRaises(SSEProtocolError):
            assert_safe_order(parse_stream(blob))


class ClassroomPromptTests(unittest.TestCase):
    def test_pay_band_pair_exists(self):
        ids = {item.id for item in PROMPTS}
        self.assertIn("pay-band-it", ids)
        self.assertIn("pay-band-finance", ids)
        it_prompts = [item for item in prompts_for("it_staff") if item["id"] == "pay-band-it"]
        self.assertEqual(it_prompts[0]["expect"], "refuse")

    def test_every_prompt_has_a_badge(self):
        for item in PROMPTS:
            self.assertTrue(item.user_id)
            self.assertTrue(item.question)
            self.assertIn(item.expect, {"answer", "refuse"})


if __name__ == "__main__":
    unittest.main()


class ConsoleEventTests(unittest.TestCase):
    """控制台长任务的事件名要登记在协议里，前端才敢按名字分支。"""

    def test_case_and_summary_events_are_allowed(self):
        from forge_lite.core.sseutil import format_frame, parse_stream
        blob = (format_frame({"type": "case", "case_id": "a"}, event="case")
                + format_frame({"type": "summary", "total": 1}, event="summary"))
        frames = parse_stream(blob)
        self.assertEqual([frame.event for frame in frames], ["case", "summary"])
        self.assertEqual(frames[0].data["case_id"], "a")

    def test_unknown_event_still_rejected(self):
        from forge_lite.core.sseutil import SSEProtocolError, format_frame
        with self.assertRaises(SSEProtocolError):
            format_frame({"x": 1}, event="teleport")
