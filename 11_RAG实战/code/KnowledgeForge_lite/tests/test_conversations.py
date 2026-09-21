"""会话柜离线门禁：刷新不丢、工牌隔离、软删除、指针不是权限。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.store.conversations import (  # noqa: E402
    ConversationConflict,
    ConversationError,
    ConversationStore,
    decode_cursor,
    default_title,
    encode_cursor,
    pointer_belongs,
)


def _result(answer="一线城市住宿上限 500 元 [1]。", status="ok", **extra):
    payload = {
        "answer": answer,
        "status": status,
        "intent": "factoid",
        "routes": "bm25+dense+graph",
        "warn": "",
        "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
        "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
        "queries": ["去上海出差住一晚能报多少？"],
        "actor": {"user_id": extra.pop("user_id", "it_staff"), "name": "IT 员工",
                  "role": "employee", "department": "it"},
    }
    payload.update(extra)
    return payload


class ConversationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(Path(self.tmp.name) / "conversations.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_record_creates_cabinet_and_survives_reopen(self):
        conv_id, run_id = self.store.record_answer("it_staff", "住宿上限？", _result())
        self.assertTrue(conv_id.startswith("conv_"))
        self.assertTrue(run_id.startswith("run_"))
        path = self.store.path
        self.store.close()
        again = ConversationStore(path)
        page = again.list_conversations("it_staff")
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].title, "住宿上限？")
        detail = again.get_conversation(conv_id, "it_staff")
        self.assertEqual(len(detail.messages), 2)
        self.assertEqual(detail.messages[0].role, "user")
        self.assertEqual(detail.messages[1].role, "assistant")
        self.assertEqual(detail.messages[1].payload["run_id"], run_id)
        again.close()

    def test_evidence_survives_reopen(self):
        """资格结论跟运行结局是两套词，刷新轨迹抽屉必须还能读到 answered，不能退化成 ok。"""
        evidence = {
            "response_status": "answered",
            "allows_generation": True,
            "reason_codes": ["direct_support"],
            "coverage": 0.82,
        }
        _, run_id = self.store.record_answer(
            "it_staff", "住宿上限？",
            _result(evidence=evidence, response_status="answered", response_label="已回答"),
        )
        path = self.store.path
        self.store.close()
        again = ConversationStore(path)
        run = again.get_run(run_id, "it_staff")
        self.assertEqual(run.evidence["response_status"], "answered")
        self.assertTrue(run.evidence["allows_generation"])
        detail = again.get_conversation(run.conversation_id, "it_staff")
        self.assertEqual(detail.messages[1].payload["response_status"], "answered")
        self.assertEqual(detail.messages[1].payload["response_label"], "已回答")
        again.close()

    def test_old_sqlite_without_evidence_column_is_migrated(self):
        """课堂上一份修字段之前建的库，打开时要自动补列，不能炸在 no such column。"""
        import sqlite3

        path = Path(self.tmp.name) / "legacy.sqlite"
        conn = sqlite3.connect(str(path))
        conn.executescript(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
                title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
            );
            CREATE TABLE messages (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                sequence INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE runs (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL,
                intent TEXT NOT NULL DEFAULT '', routes TEXT NOT NULL DEFAULT '',
                warn TEXT NOT NULL DEFAULT '', citations TEXT NOT NULL DEFAULT '[]',
                contexts TEXT NOT NULL DEFAULT '[]', queries TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE feedback (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT NOT NULL,
                user_id TEXT NOT NULL, rating TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE (tenant_id, run_id, user_id)
            );
            """
        )
        conn.close()
        store = ConversationStore(path)
        _, run_id = store.record_answer(
            "it_staff", "住宿上限？",
            _result(evidence={"response_status": "answered", "allows_generation": True}),
        )
        run = store.get_run(run_id, "it_staff")
        self.assertEqual(run.evidence["response_status"], "answered")
        store.close()

    def test_owner_isolation(self):
        conv_id, _ = self.store.record_answer("it_staff", "打印机 E3？", _result(user_id="it_staff"))
        page = self.store.list_conversations("hr_staff")
        self.assertEqual(page.items, [])
        with self.assertRaises(ConversationError):
            self.store.get_conversation(conv_id, "hr_staff")
        with self.assertRaises(ConversationError):
            self.store.delete_conversation(conv_id, "finance_head")

    def test_append_keeps_same_cabinet(self):
        conv_id, _ = self.store.record_answer("it_staff", "第一问", _result())
        again, _ = self.store.record_answer("it_staff", "第二问", _result(), conversation_id=conv_id)
        self.assertEqual(conv_id, again)
        detail = self.store.get_conversation(conv_id, "it_staff")
        self.assertEqual([msg.role for msg in detail.messages], ["user", "assistant", "user", "assistant"])
        self.assertEqual(detail.messages[2].content, "第二问")

    def test_foreign_conversation_id_is_not_hijackable(self):
        conv_id, _ = self.store.record_answer("it_staff", "IT 的柜子", _result())
        with self.assertRaises(ConversationError):
            self.store.record_answer("hr_staff", "想写进别人柜子", _result(user_id="hr_staff"),
                                     conversation_id=conv_id)

    def test_soft_delete_blanks_content(self):
        conv_id, run_id = self.store.record_answer("it_staff", "要删的问", _result())
        deleted = self.store.delete_conversation(conv_id, "it_staff")
        self.assertIn(run_id, deleted)
        self.assertEqual(self.store.list_conversations("it_staff").items, [])
        with self.assertRaises(ConversationError):
            self.store.get_conversation(conv_id, "it_staff")

    def test_rename_and_empty_title_rejected(self):
        conv_id, _ = self.store.record_answer("it_staff", "原标题问句", _result())
        renamed = self.store.rename_conversation(conv_id, "it_staff", "差旅上限")
        self.assertEqual(renamed.title, "差旅上限")
        with self.assertRaises(ConversationConflict):
            self.store.rename_conversation(conv_id, "it_staff", "   ")

    def test_feedback_only_on_own_run(self):
        _, run_id = self.store.record_answer("it_staff", "住宿上限？", _result())
        saved = self.store.upsert_feedback(run_id, "it_staff", "up", "有用")
        self.assertEqual(saved["rating"], "up")
        with self.assertRaises(ConversationError):
            self.store.upsert_feedback(run_id, "hr_staff", "down")
        with self.assertRaises(ConversationConflict):
            self.store.upsert_feedback(run_id, "it_staff", "love")

    def test_empty_question_rejected(self):
        with self.assertRaises(ConversationConflict):
            self.store.record_answer("it_staff", "   ", _result())
        with self.assertRaises(ConversationConflict):
            default_title("")

    def test_cursor_roundtrip_and_pagination(self):
        ids = []
        for index in range(3):
            conv_id, _ = self.store.record_answer("admin", f"问题 {index}", _result(user_id="admin"))
            ids.append(conv_id)
        page1 = self.store.list_conversations("admin", limit=2)
        self.assertEqual(len(page1.items), 2)
        self.assertTrue(page1.next_cursor)
        stamp, conv_id = decode_cursor(page1.next_cursor)
        self.assertEqual(encode_cursor(page1.items[-1].updated_at, page1.items[-1].id), page1.next_cursor)
        self.assertEqual(conv_id, page1.items[-1].id)
        page2 = self.store.list_conversations("admin", limit=2, cursor=page1.next_cursor)
        self.assertEqual(len(page2.items), 1)
        with self.assertRaises(ConversationConflict):
            decode_cursor("%%%")

    def test_pointer_belongs(self):
        conv_id, _ = self.store.record_answer("it_staff", "指针题", _result())
        page = self.store.list_conversations("it_staff")
        self.assertEqual(pointer_belongs(conv_id, page.items), conv_id)
        self.assertIsNone(pointer_belongs("conv_ghost", page.items))
        self.assertIsNone(pointer_belongs("", page.items))

    def test_masks_pii_in_warn(self):
        conv_id, _ = self.store.record_answer(
            "it_staff", "电话题",
            _result(warn="联系 13812345678 或 ops@example.com"),
        )
        detail = self.store.get_conversation(conv_id, "it_staff")
        warn = detail.messages[1].payload["warn"]
        self.assertNotIn("13812345678", warn)
        self.assertNotIn("ops@example.com", warn)


if __name__ == "__main__":
    unittest.main()
