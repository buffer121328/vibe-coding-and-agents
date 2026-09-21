"""改写护栏表驱动测试：原问题必须在、意图分类、顿号拆主题、失败回退。不调模型。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.core.rewrite import (  # noqa: E402
    classify_intent_local,
    expand_queries,
    merge_queries,
    rewrite_query_local,
    should_decompose,
)


class MergeGuardTests(unittest.TestCase):
    def test_original_always_first(self):
        merged = merge_queries("原问题", ["改写一", "改写二"])
        self.assertEqual(merged[0], "原问题")

    def test_duplicates_are_removed(self):
        merged = merge_queries("同一句", ["同一句", "同一句"])
        self.assertEqual(merged, ["同一句"])

    def test_blank_rewrites_are_skipped(self):
        merged = merge_queries("问题", ["", "   "])
        self.assertEqual(merged, ["问题"])

    def test_limit_truncates_tail(self):
        merged = merge_queries("问题", ["a", "b", "c", "d", "e"], limit=3)
        self.assertEqual(len(merged), 3)

    def test_empty_original_falls_back_to_itself(self):
        self.assertEqual(merge_queries("", []), [""])


class IntentTableTests(unittest.TestCase):
    CASES = (
        ("这个和那个有什么区别？", "comparative"),
        ("打印机 E3 怎么处理？", "procedural"),
        ("报销流程是怎样的？", "procedural"),
        ("为什么要五天之内交？", "analytical"),
        ("有哪些安全红线？", "exploratory"),
        ("住宿上限是多少？", "factoid"),
    )

    def test_intent_table(self):
        for question, expected in self.CASES:
            with self.subTest(question=question):
                self.assertEqual(classify_intent_local(question), expected)


class RewriteRulesTests(unittest.TestCase):
    def test_original_stays_first_after_rewrite(self):
        result = rewrite_query_local("出差回来晚了一天，钱最晚啥时候能到手？")
        self.assertEqual(result["queries"][0], "出差回来晚了一天，钱最晚啥时候能到手？")

    def test_entities_are_extracted(self):
        result = rewrite_query_local("P6 薪酬带宽是多少？")
        self.assertTrue(any("P6" in item for item in result["entities"]))

    def test_enumerated_topics_split_into_subqueries(self):
        result = rewrite_query_local("招聘、培训和绩效考核分别有什么制度要求？")
        queries = result["queries"]
        self.assertTrue(any(query.startswith("招聘") for query in queries[1:]))
        self.assertTrue(any(query.endswith("制度要求") for query in queries[1:]))

    def test_rewrite_never_exceeds_four_queries(self):
        result = rewrite_query_local("甲、乙、丙、丁、戊、己分别有什么要求？")
        self.assertLessEqual(len(result["queries"]), 4)

    def test_queries_are_unique(self):
        result = rewrite_query_local("差旅 差旅 差旅")
        self.assertEqual(len(result["queries"]), len(set(result["queries"])))


class DecomposeSignalTests(unittest.TestCase):
    def test_short_plain_question_is_not_multi_hop(self):
        self.assertFalse(should_decompose("住宿上限是多少？"))

    def test_long_or_connector_heavy_question_is_flagged(self):
        self.assertTrue(should_decompose("比较一线和二线城市标准，同时说明报销时限，以及适用人群"))


class ExpandFallbackTests(unittest.TestCase):
    def test_without_llm_uses_local_rules_only(self):
        queries = expand_queries("住宿上限？", llm=None)
        self.assertEqual(queries[0], "住宿上限？")

    def test_broken_llm_falls_back_to_local(self):
        class Broken:
            def invoke(self, *_args, **_kwargs):
                raise RuntimeError("endpoint down")

        queries = expand_queries("住宿上限？", llm=Broken())
        self.assertEqual(queries[0], "住宿上限？")
        self.assertTrue(queries)

    def test_llm_extra_is_appended_after_original(self):
        class Fake:
            def invoke(self, *_args, **_kwargs):
                class Resp:
                    content = "企业差旅住宿报销标准上限查询"
                return Resp()

        queries = expand_queries("住一晚能报多少？", llm=Fake())
        self.assertEqual(queries[0], "住一晚能报多少？")
        self.assertIn("企业差旅住宿报销标准上限查询", queries)


if __name__ == "__main__":
    unittest.main()
