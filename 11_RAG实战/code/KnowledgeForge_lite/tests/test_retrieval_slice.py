"""检索切片测试：分词、RRF 加权、首尾编排、装箱、可解释。全部离线、不联网。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.core.quality import (  # noqa: E402
    SOURCE_WEIGHTS,
    deduplicate_contexts,
    explain_retrieval,
    order_contexts,
    pack_contexts,
    reciprocal_rank_fusion,
)
from forge_lite.retrieve.search import _chunk_key, _pack_hits, _tokenize, rrf_fuse  # noqa: E402


class TokenizerTests(unittest.TestCase):
    """切词有两套路：jieba 主路、二元组兜底。两条都要能切出「词」。"""

    def test_chinese_yields_words_on_both_paths(self):
        """不管是 jieba 还是兜底的二元组，「住宿」「标准」都必须切得出来。

        这条是索引侧与查询侧同一把刀的底线：两边切法不一致时词面对不上，
        检索会静默变差——不报错，只是召回少了。
        """
        from forge_lite.retrieve import search as retrieval
        for ready in (False, True):
            with self.subTest(jieba=ready):
                original = retrieval._JIEBA_READY
                retrieval._JIEBA_READY = ready
                try:
                    tokens = _tokenize("住宿标准")
                finally:
                    retrieval._JIEBA_READY = original
                self.assertIn("住宿", tokens)
                self.assertIn("标准", tokens)

    def test_latin_words_survive(self):
        tokens = _tokenize("打印机 E3 报错，检查 paper jam")
        self.assertIn("E3", tokens)
        self.assertIn("paper", tokens)
        self.assertIn("jam", tokens)

    def test_single_chinese_char_still_tokenizes(self):
        tokens = _tokenize("元")
        self.assertEqual(tokens, ["元"])

    def test_punctuation_is_dropped(self):
        """标点不能进索引：jieba 会把「，」「。」也当 token 吐出来，
        它们没有词面信息，留在索引里只是把小语料的 IDF 搅浑。"""
        tokens = _tokenize("住宿，标准。：500 元！")
        for mark in ("，", "。", "：", "！"):
            with self.subTest(mark=mark):
                self.assertNotIn(mark, tokens)
        self.assertIn("500", tokens)
        self.assertIn("元", tokens)

    def test_bigram_fallback_keeps_function_words_out_of_dictionary(self):
        """兜底路径不查词典，中文只能靠二元组近似——它必然切不出三字词，
        但任何两字词都在里面（这是它敢当兜底的底气）。"""
        from forge_lite.retrieve.search import _bigram_tokens
        tokens = _bigram_tokens("上海出差")
        self.assertIn("上海", tokens)
        self.assertIn("出差", tokens)
        self.assertEqual(len("".join(tokens)), 6)   # 上海+海出+出差


class PackThenOrderTests(unittest.TestCase):
    """装箱与编排的先后顺序——这个顺序错了会静默丢掉最该看的那块资料。

    评测抓到的真 bug：``order_contexts`` 为了对抗 lost-in-the-middle 把榜眼放到列表
    最末，而 ``_pack_hits`` 是按预算从尾部截断的。先编排再装箱时，"预算不够"砍掉的
    第一个正是那个被特意安排到结尾的第二名——它连模型的面都没见到。
    正确顺序是**先按相关度装箱（决定谁进得来），再对装进来的做首尾编排（决定怎么摆）**。
    """

    def test_second_best_sits_last_after_ordering(self):
        """order_contexts 本身的行为：榜眼占结尾。这条不变，变的是调用它的时机。"""
        ordered = order_contexts([("best", 1.0), ("second", 0.9), ("c", 0.3), ("d", 0.2)])
        self.assertEqual(ordered[0], "best")
        self.assertEqual(ordered[-1], "second")

    def test_budget_cut_must_not_eat_the_second_best(self):
        """把「先编排再装箱」和「先装箱再编排」摆在一起比，差别就是这个 bug。"""
        from forge_lite.retrieve.search import _pack_hits

        scored = [("#0", 1.0), ("#1", 0.9), ("#2", 0.3), ("#3", 0.2)]
        texts = {"#0": "甲" * 40, "#1": "乙" * 40, "#2": "丙" * 40, "#3": "丁" * 40}

        def hits_in(order):
            return [{"source": key, "chunk_index": 0, "text": texts[key]} for key in order]

        # 错序：先编排（榜眼被挪到末尾），再按 100 字预算装箱
        wrong = [h["source"] for h in _pack_hits(hits_in(order_contexts(scored)), 100)]
        self.assertNotIn("#1", wrong, "错序确实会丢掉榜眼——这条记录的就是那个 bug")

        # 对序：先按相关度装箱，再编排。榜眼留得住。
        packed = _pack_hits(hits_in([key for key, _ in sorted(scored, key=lambda kv: -kv[1])]), 100)
        kept = {h["source"] for h in packed}
        final = [key for key in order_contexts([(k, s) for k, s in scored if k in kept])]
        self.assertIn("#1", final, "预算只够两块时，留下的必须是相关度最高的那两块")


class FusionTests(unittest.TestCase):
    def test_weighted_rrf_lets_graph_win_on_ties(self):
        weights = [SOURCE_WEIGHTS["bm25"], SOURCE_WEIGHTS["vector"], SOURCE_WEIGHTS["graph"]]
        fused = rrf_fuse([["a"], ["b"], ["b"]], weights=weights)
        self.assertEqual(fused[0], "b")

    def test_unweighted_rrf_breaks_ties_by_id(self):
        fused = reciprocal_rank_fusion([["b"], ["a"]], rank_constant=60)
        self.assertEqual([item[0] for item in fused], ["a", "b"])

    def test_rank_constant_must_be_non_negative(self):
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([["a"]], rank_constant=-1)

    def test_weights_length_must_match(self):
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([["a"], ["b"]], weights=[1.0])

    def test_missing_id_ranks_lower_than_first_place(self):
        fused = dict(reciprocal_rank_fusion([["first", "second"]], rank_constant=60))
        self.assertGreater(fused["first"], fused["second"])


class ChunkKeyTests(unittest.TestCase):
    def test_key_is_source_hash_index(self):
        self.assertEqual(_chunk_key({"source": "a.md", "chunk_index": 2}), "a.md#2")

    def test_pack_hits_drops_duplicates_and_respects_budget(self):
        hits = [
            {"text": "甲" * 10, "source": "a.md", "chunk_index": 0},
            {"text": "甲" * 10, "source": "a.md", "chunk_index": 1},
            {"text": "乙" * 50, "source": "b.md", "chunk_index": 0},
        ]
        packed = _pack_hits(hits, max_chars=30)
        texts = [hit["text"] for hit in packed]
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0], "甲" * 10)

    def test_pack_hits_keeps_first_even_over_budget(self):
        hits = [{"text": "长" * 100, "source": "a.md", "chunk_index": 0}]
        self.assertEqual(len(_pack_hits(hits, max_chars=10)), 1)


class OrderAndDedupeTests(unittest.TestCase):
    def test_best_and_second_best_end_up_at_ends(self):
        ordered = order_contexts([("a", 0.9), ("b", 0.8), ("c", 0.7), ("d", 0.1)])
        self.assertEqual(ordered[0], "a")
        self.assertEqual(ordered[-1], "b")

    def test_order_of_two_keeps_rank(self):
        self.assertEqual(order_contexts([("x", 1.0), ("y", 0.5)]), ["x", "y"])

    def test_dedupe_keeps_first_of_near_duplicates(self):
        kept = deduplicate_contexts(["住宿上限 500 元", "住宿上限 500 元!", "报销五天内"])
        self.assertEqual(kept[0], "住宿上限 500 元")
        self.assertEqual(len(kept), 2)

    def test_dedupe_threshold_guard(self):
        with self.assertRaises(ValueError):
            deduplicate_contexts(["a"], threshold=1.5)

    def test_pack_contexts_skips_what_does_not_fit(self):
        packed = pack_contexts(["甲" * 30, "乙" * 30, "丙" * 10], max_chars=45)
        self.assertEqual(packed, ["甲" * 30, "丙" * 10])

    def test_explain_retrieval_marks_scores_incomparable(self):
        rows = explain_retrieval([{"id": "a.md#0", "route": "graph", "rank": 1, "fused_rank": 2}])
        self.assertIn("graph", rows[0]["why"])
        self.assertFalse(rows[0]["is_confidence_comparable"])
        self.assertEqual(rows[0]["id"], "a.md#0")


if __name__ == "__main__":
    unittest.main()
