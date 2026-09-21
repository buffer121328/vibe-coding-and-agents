"""精确缓存测试：键带工牌和 schema，越权与陈旧都命中不了。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite import config  # noqa: E402
from forge_lite.store.query_cache import QueryCache, cache_key, normalize_question  # noqa: E402


def _result(answer="一线城市住宿上限 500 元 [1]。", **extra):
    payload = {
        "answer": answer,
        "status": "ok",
        "routes": "bm25+dense",
        "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
    }
    payload.update(extra)
    return payload


class CacheKeyTests(unittest.TestCase):
    def test_key_differs_by_user(self):
        self.assertNotEqual(
            cache_key("it_staff", "住宿上限？"),
            cache_key("finance_head", "住宿上限？"),
        )

    def test_key_differs_by_schema(self):
        self.assertNotEqual(
            cache_key("it_staff", "住宿上限？", schema="acl-v1"),
            cache_key("it_staff", "住宿上限？", schema="acl-v2"),
        )

    def test_key_is_stable_for_same_input(self):
        self.assertEqual(cache_key("it_staff", "住宿上限？"), cache_key("it_staff", "住宿上限？"))

    def test_normalize_collapses_whitespace(self):
        self.assertEqual(normalize_question("住宿   上限？\n"), "住宿 上限？")


class QueryCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = QueryCache(Path(self.tmp.name) / "cache.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_put_then_get_roundtrip(self):
        self.cache.put("it_staff", "住宿上限？", _result())
        hit = self.cache.get("it_staff", "住宿上限？")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.status, "ok")
        self.assertEqual(hit.schema, config.INDEX_SCHEMA)

    def test_answer_is_masked_before_storing(self):
        self.cache.put("it_staff", "电话题", _result(answer="联系 13812345678 处理 [1]。"))
        hit = self.cache.get("it_staff", "电话题")
        self.assertNotIn("13812345678", hit.answer)

    def test_other_badge_cannot_read_cache(self):
        self.cache.put("finance_head", "P6 薪酬带宽是多少？", _result(answer="35 万至 45 万元 [1]。"))
        self.assertIsNone(self.cache.get("it_staff", "P6 薪酬带宽是多少？"))

    def test_schema_bump_invalidates_hit(self):
        self.cache.put("it_staff", "住宿上限？", _result())
        original = config.INDEX_SCHEMA
        config.INDEX_SCHEMA = "acl-v99"
        try:
            self.assertIsNone(self.cache.get("it_staff", "住宿上限？"))
        finally:
            config.INDEX_SCHEMA = original

    def test_drop_schema_removes_stale_rows(self):
        self.cache.put("it_staff", "甲", _result())
        dropped = self.cache.drop_schema("acl-v1")
        self.assertEqual(dropped, 1)
        self.assertIsNone(self.cache.get("it_staff", "甲"))

    def test_empty_question_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cache.put("it_staff", "   ", _result())

    def test_new_instance_reloads_from_disk(self):
        self.cache.put("it_staff", "住宿上限？", _result())
        again = QueryCache(self.cache.path)
        self.assertIsNotNone(again.get("it_staff", "住宿上限？"))


if __name__ == "__main__":
    unittest.main()
