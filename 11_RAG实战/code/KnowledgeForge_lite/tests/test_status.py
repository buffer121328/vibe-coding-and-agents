"""运行时体检测试：空库、旧 schema、只有种子图谱、账本统计。全离线。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite import config  # noqa: E402
from forge_lite.store.audit import AuditLog  # noqa: E402
from forge_lite.store.conversations import ConversationStore  # noqa: E402
from forge_lite.store.query_cache import QueryCache  # noqa: E402
from forge_lite.service.status import (  # noqa: E402
    build_report,
    inspect_conversations,
    inspect_index,
    inspect_ledger,
    render_report,
)


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class IndexSectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_index_is_flagged(self):
        section = inspect_index(self.root / "chunks.json", self.root / "docstore.json")
        self.assertTrue(section.empty)
        self.assertEqual(section.chunks_total, 0)

    def test_counts_and_schema_mix(self):
        _write(self.root / "docstore.json", {
            "员工差旅管理制度.md": {"hash": "aaaaaaaa1111", "schema": config.INDEX_SCHEMA},
            "旧文档.md": {"hash": "bbbbbbbb2222", "schema": "acl-v1"},
        })
        _write(self.root / "chunks.json", [
            {"source": "员工差旅管理制度.md", "chunk_index": 0, "text": "甲"},
            {"source": "员工差旅管理制度.md", "chunk_index": 1, "text": "乙"},
            {"source": "产品FAQ.md", "chunk_index": 0, "text": "丙"},
        ])
        section = inspect_index(self.root / "chunks.json", self.root / "docstore.json")
        self.assertEqual(section.docstore_entries, 2)
        self.assertEqual(section.chunks_total, 3)
        self.assertEqual(section.chunks_by_source["员工差旅管理制度.md"], 2)
        self.assertTrue(section.schema_stale)
        self.assertEqual(len(section.documents), 2)

    def test_all_current_schema_is_not_stale(self):
        _write(self.root / "docstore.json", {
            "a.md": {"hash": "x", "schema": config.INDEX_SCHEMA},
        })
        section = inspect_index(self.root / "chunks.json", self.root / "docstore.json")
        self.assertFalse(section.schema_stale)

    def test_legacy_plain_string_entry_counts(self):
        _write(self.root / "docstore.json", {"a.md": "deadbeef"})
        section = inspect_index(self.root / "chunks.json", self.root / "docstore.json")
        self.assertEqual(section.schema_counts.get("（旧格式）"), 1)
        self.assertFalse(section.schema_stale)

    def test_corrupt_docstore_is_treated_as_empty(self):
        path = self.root / "docstore.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        section = inspect_index(self.root / "chunks.json", path)
        self.assertEqual(section.docstore_entries, 0)


class ConversationSectionTests(unittest.TestCase):
    def test_counts_are_per_badge(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStore(Path(tmp) / "c.sqlite")
            store.record_answer("it_staff", "问题一", {"answer": "答", "status": "ok"})
            store.record_answer("it_staff", "问题二", {"answer": "答", "status": "ok"})
            store.record_answer("hr_staff", "问题三", {"answer": "答", "status": "ok"})
            section = inspect_conversations(store)
            store.close()
        self.assertEqual(section.per_badge["it_staff"], 2)
        self.assertEqual(section.per_badge["hr_staff"], 1)
        self.assertEqual(section.per_badge["admin"], 0)
        self.assertEqual(section.total, 3)


class LedgerSectionTests(unittest.TestCase):
    def test_audit_and_cache_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(Path(tmp) / "audit.jsonl")
            audit.record("ask", "it_staff", question="住宿上限？")
            audit.record("ask", "it_staff", question="报销时限？")
            audit.record("list_catalog", "hr_staff")
            cache = QueryCache(Path(tmp) / "cache.jsonl")
            cache.put("it_staff", "住宿上限？", {"answer": "甲", "status": "ok"})
            section = inspect_ledger(audit, cache)
        self.assertEqual(section.audit_events, 3)
        self.assertEqual(section.audit_actions["ask"], 2)
        self.assertEqual(section.cache_entries, 1)
        self.assertEqual(list(section.cache_schemas.values()), [1])


class ReportTests(unittest.TestCase):
    def _report(self, **over):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = ConversationStore(root / "c.sqlite")
            report = build_report(
                chunks_path=root / "chunks.json",
                docstore_path=root / "docstore.json",
                store=store,
                audit=AuditLog(root / "audit.jsonl"),
                cache=QueryCache(root / "cache.jsonl"),
                **over,
            )
            store.close()
            return report

    def test_empty_runtime_gives_actionable_notes(self):
        report = self._report()
        self.assertFalse(report.healthy)
        joined = " ".join(report.notes)
        self.assertIn("01_ingest", joined)
        self.assertIn("会话柜还是空的", joined)

    def test_report_serializes(self):
        report = self._report()
        data = report.as_dict()
        self.assertIn("index", data)
        self.assertIn("graph", data)
        self.assertIn("healthy", data)

    def test_rendered_report_has_all_sections(self):
        text = render_report(self._report())
        for marker in ("[索引]", "[图谱]", "[会话]", "[账本]", "结论："):
            self.assertIn(marker, text)

    def test_healthy_when_index_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "docstore.json", {"a.md": {"hash": "x", "schema": config.INDEX_SCHEMA}})
            _write(root / "chunks.json", [{"source": "a.md", "chunk_index": 0, "text": "甲"}])
            store = ConversationStore(root / "c.sqlite")
            store.record_answer("it_staff", "问", {"answer": "答", "status": "ok"})
            report = build_report(
                chunks_path=root / "chunks.json",
                docstore_path=root / "docstore.json",
                store=store,
                audit=AuditLog(root / "audit.jsonl"),
                cache=QueryCache(root / "cache.jsonl"),
            )
            store.close()
        self.assertTrue(report.healthy)
        self.assertIn("体检通过", render_report(report))


if __name__ == "__main__":
    unittest.main()
