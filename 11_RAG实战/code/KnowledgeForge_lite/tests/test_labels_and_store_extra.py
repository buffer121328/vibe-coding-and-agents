"""文案契约与会话柜补测：状态词全覆盖、分页夹取、过期清理、导出全量。全离线。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.core import labels  # noqa: E402
from forge_lite.contracts import (  # noqa: E402
    ACTOR_KEYS,
    ASK_DONE_KEYS,
    CITATION_KEYS,
    CONVERSATION_CARD_KEYS,
    EVIDENCE_KEYS,
    MESSAGE_KEYS,
    TRACE_KEYS,
    missing_keys,
    require_keys,
)
from forge_lite.store.conversations import (  # noqa: E402
    ConversationConflict,
    ConversationError,
    ConversationStore,
    pointer_belongs,
)
from forge_lite.core.evidence import (  # noqa: E402
    STATUS_ANSWERED,
    STATUS_CLARIFY,
    STATUS_CONFLICT,
    STATUS_INSUFFICIENT,
    STATUS_PARTIAL,
    STATUS_REVIEW,
    STATUS_UNAVAILABLE,
)


def _answer(text="一线城市住宿上限 500 元 [1]。", **over):
    payload = {
        "answer": text,
        "status": "ok",
        "intent": "factoid",
        "routes": "bm25+dense",
        "warn": "",
        "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
        "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
        "queries": ["住宿上限？"],
    }
    payload.update(over)
    return payload


class LabelsTests(unittest.TestCase):
    def test_every_evidence_status_has_chinese_label(self):
        for status in (STATUS_ANSWERED, STATUS_PARTIAL, STATUS_INSUFFICIENT,
                       STATUS_CLARIFY, STATUS_CONFLICT, STATUS_REVIEW, STATUS_UNAVAILABLE):
            with self.subTest(status=status):
                text = labels.status_text(status)
                self.assertTrue(text)
                self.assertNotEqual(text, status)

    def test_agent_statuses_have_labels(self):
        for status in ("ok", "refuse", "regen"):
            self.assertNotEqual(labels.status_text(status), status)

    def test_route_and_intent_labels(self):
        self.assertEqual(labels.route_text("graph"), "图谱")
        self.assertEqual(labels.intent_text("procedural"), "流程")

    def test_unknown_key_falls_back_to_itself(self):
        self.assertEqual(labels.status_text("mystery"), "mystery")
        self.assertEqual(labels.route_text("cross_encoder"), "cross_encoder")

    def test_workbench_copy_is_present(self):
        for text in (labels.APP_NAME, labels.RAIL_TITLE, labels.EMPTY_BODY,
                     labels.EVIDENCE_HINT, labels.COMPOSER_PLACEHOLDER):
            self.assertTrue(str(text).strip())


class ContractHelperTests(unittest.TestCase):
    def test_missing_keys_detects_absent_fields(self):
        self.assertEqual(missing_keys({"a": 1}, ("a", "b")), ["b"])
        self.assertEqual(missing_keys({"a": 1, "b": 2}, ("a", "b")), [])

    def test_require_keys_raises_with_label(self):
        with self.assertRaises(ValueError) as ctx:
            require_keys({"a": 1}, ("a", "z"), "测试载荷")
        self.assertIn("测试载荷", str(ctx.exception))

    def test_done_and_trace_keys_overlap_where_expected(self):
        done = set(ASK_DONE_KEYS)
        for key in ("status", "citations", "routes", "conversation_id", "run_id"):
            self.assertIn(key, done)
        self.assertTrue(set(TRACE_KEYS) - {"question"})
        self.assertTrue(CONVERSATION_CARD_KEYS)
        self.assertTrue(MESSAGE_KEYS)
        self.assertTrue(CITATION_KEYS)
        self.assertTrue(ACTOR_KEYS)
        self.assertTrue(EVIDENCE_KEYS)


class StoreExtraTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.tmp.name) / "c.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_limit_is_clamped_to_page_max(self):
        for index in range(3):
            self.store.record_answer("admin", f"问 {index}", _answer())
        page = self.store.list_conversations("admin", limit=9999)
        self.assertEqual(len(page.items), 3)
        self.assertIsNone(page.next_cursor)

    def test_zero_limit_still_returns_one(self):
        self.store.record_answer("admin", "问", _answer())
        page = self.store.list_conversations("admin", limit=0)
        self.assertEqual(len(page.items), 1)

    def test_newest_conversation_sorts_first(self):
        first, _ = self.store.record_answer("admin", "第一问", _answer())
        second, _ = self.store.record_answer("admin", "第二问", _answer())
        page = self.store.list_conversations("admin")
        self.assertEqual(page.items[0].id, second)

    def test_feedback_update_overwrites_previous_rating(self):
        _, run_id = self.store.record_answer("it_staff", "问", _answer())
        self.store.upsert_feedback(run_id, "it_staff", "up", "第一次")
        saved = self.store.upsert_feedback(run_id, "it_staff", "issue", "改主意了")
        self.assertEqual(saved["rating"], "issue")
        current = self.store.get_feedback(run_id, "it_staff")
        self.assertEqual(current["note"], "改主意了")

    def test_feedback_absent_is_none(self):
        _, run_id = self.store.record_answer("it_staff", "问", _answer())
        self.assertIsNone(self.store.get_feedback(run_id, "it_staff"))

    def test_cleanup_expired_removes_only_old_rows(self):
        fresh, _ = self.store.record_answer("it_staff", "新问", _answer())
        old, _ = self.store.record_answer("hr_staff", "旧问", _answer())
        conn = self.store._connect()
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?",
                     ("2020-01-01T00:00:00+00:00", old))
        removed = self.store.cleanup_expired(retention_days=30)
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.list_conversations("it_staff").items[0].id, fresh)
        self.assertEqual(self.store.list_conversations("hr_staff").items, [])

    def test_cleanup_requires_positive_days(self):
        with self.assertRaises(ConversationConflict):
            self.store.cleanup_expired(retention_days=0)

    def test_export_owner_returns_full_cabinets_only(self):
        self.store.record_answer("it_staff", "住宿上限？", _answer())
        self.store.record_answer("hr_staff", "别的柜子", _answer())
        dumped = self.store.export_owner("it_staff")
        self.assertEqual(len(dumped), 1)
        self.assertEqual(dumped[0]["conversation"]["user_id"], "it_staff")
        self.assertEqual(len(dumped[0]["messages"]), 2)

    def test_rename_foreign_conversation_rejected(self):
        conv_id, _ = self.store.record_answer("it_staff", "问", _answer())
        with self.assertRaises(ConversationError):
            self.store.rename_conversation(conv_id, "hr_staff", "抢改名")

    def test_appending_after_delete_is_rejected(self):
        conv_id, _ = self.store.record_answer("it_staff", "问", _answer())
        self.store.delete_conversation(conv_id, "it_staff")
        with self.assertRaises(ConversationError):
            self.store.record_answer("it_staff", "再问", _answer(), conversation_id=conv_id)

    def test_pointer_helpers_ignore_deleted(self):
        kept, _ = self.store.record_answer("it_staff", "留着", _answer())
        gone, _ = self.store.record_answer("it_staff", "删掉", _answer())
        self.store.delete_conversation(gone, "it_staff")
        page = self.store.list_conversations("it_staff")
        self.assertEqual(pointer_belongs(kept, page.items), kept)
        self.assertIsNone(pointer_belongs(gone, page.items))

    def test_sequence_keeps_increasing(self):
        conv_id, _ = self.store.record_answer("it_staff", "第一问", _answer())
        self.store.record_answer("it_staff", "第二问", _answer(), conversation_id=conv_id)
        self.store.record_answer("it_staff", "第三问", _answer(), conversation_id=conv_id)
        detail = self.store.get_conversation(conv_id, "it_staff")
        self.assertEqual([msg.sequence for msg in detail.messages], [1, 2, 3, 4, 5, 6])

    def test_title_comes_from_first_question(self):
        conv_id, _ = self.store.record_answer("it_staff", "去上海出差住一晚能报多少？", _answer())
        detail = self.store.get_conversation(conv_id, "it_staff")
        self.assertEqual(detail.conversation.title, "去上海出差住一晚能报多少？")

    def test_placeholder_title_is_replaced_by_first_question(self):
        conv = self.store.create_conversation("it_staff", title="新会话")
        self.store.record_answer("it_staff", "真正的第一问", _answer(), conversation_id=conv.id)
        detail = self.store.get_conversation(conv.id, "it_staff")
        self.assertEqual(detail.conversation.title, "真正的第一问")

    def test_long_question_title_is_truncated(self):
        conv_id, _ = self.store.record_answer("it_staff", "问" * 300, _answer())
        detail = self.store.get_conversation(conv_id, "it_staff")
        self.assertLessEqual(len(detail.conversation.title), 120)


if __name__ == "__main__":
    unittest.main()


class ChatEndpointPairingTests(unittest.TestCase):
    """模型与端点必须成对：配错只会得到「模型不支持」这类误导性报错。"""

    def test_mimo_model_pulls_mimo_endpoint(self):
        from forge_lite.config import resolve_chat_endpoint
        base, key = resolve_chat_endpoint(
            None, None, "mimo-v2.5-pro",
            None, None,
            "https://ark.example/v3", "ark-key",
            "https://mimo.example/v1", "mimo-key",
        )
        self.assertEqual(base, "https://mimo.example/v1")
        self.assertEqual(key, "mimo-key")

    def test_generic_model_keeps_generic_endpoint(self):
        from forge_lite.config import resolve_chat_endpoint
        base, key = resolve_chat_endpoint(
            None, "gpt-4o-mini", "mimo-v2.5-pro",
            None, None,
            "https://ark.example/v3", "ark-key",
            "https://mimo.example/v1", "mimo-key",
        )
        self.assertEqual(base, "https://ark.example/v3")
        self.assertEqual(key, "ark-key")

    def test_explicit_forge_override_wins(self):
        from forge_lite.config import resolve_chat_endpoint
        base, key = resolve_chat_endpoint(
            "my-model", None, "mimo-v2.5-pro",
            "https://custom.example/v1", "custom-key",
            "https://ark.example/v3", "ark-key",
            "https://mimo.example/v1", "mimo-key",
        )
        self.assertEqual(base, "https://custom.example/v1")
        self.assertEqual(key, "custom-key")

    def test_nothing_configured_falls_back_to_empty(self):
        from forge_lite.config import resolve_chat_endpoint
        self.assertEqual(resolve_chat_endpoint(None, None, None, None, None, None, None, None, None),
                         ("", ""))

    def test_live_config_has_paired_values(self):
        from forge_lite import config
        if config.CHAT_MODEL and config.CHAT_API_BASE:
            # 成对解析后不该再出现「MiMo 模型 + 方舟端点」这种交叉
            if config.CHAT_MODEL.lower().startswith("mimo"):
                self.assertNotIn("volces", config.CHAT_API_BASE)


class ThinkingModeTests(unittest.TestCase):
    """MiMo 隐性思考：课堂默认关，请求体必须带完整版同款 extra_body。"""

    def test_classroom_default_disables_thinking(self):
        from forge_lite import config
        self.assertEqual(config.THINKING_MODE, "disabled")
        self.assertEqual(
            config.thinking_extra_body(),
            {"extra_body": {"thinking": {"type": "disabled"}}},
        )

    def test_default_mode_omits_the_field(self):
        from forge_lite import config
        with patch.object(config, "THINKING_MODE", "default"):
            self.assertEqual(config.thinking_extra_body(), {})

    def test_chat_client_receives_thinking_kwargs(self):
        """问答客户端必须把关思考的 extra_body 交给 ChatOpenAI，不能只写在文档里。"""
        import forge_lite.llm as llm_mod

        captured: dict = {}

        class FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        previous = llm_mod._llm
        try:
            llm_mod._llm = None
            with patch("langchain_openai.ChatOpenAI", FakeChat):
                llm_mod.get_llm()
            self.assertEqual(captured.get("extra_body"), {"thinking": {"type": "disabled"}})
        finally:
            llm_mod._llm = previous if previous is not None else None
