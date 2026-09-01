import sys
import unittest
from datetime import date
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from rag_quality import (  # noqa: E402
    CacheScope,
    IndexManifest,
    RunBudget,
    SourceVersion,
    choose_current_sources,
    citation_metrics,
    deduplicate_contexts,
    percentile,
    reciprocal_rank_fusion,
    retrieval_metrics,
)


class RetrievalTests(unittest.TestCase):
    def test_retrieval_metrics_separate_recall_and_ranking(self):
        result = retrieval_metrics(["noise", "gold_b", "gold_a"], {"gold_a", "gold_b"}, 3)
        self.assertEqual(result["hit_rate_at_k"], 1.0)
        self.assertEqual(result["recall_at_k"], 1.0)
        self.assertAlmostEqual(result["precision_at_k"], 2 / 3)
        self.assertEqual(result["mrr"], 0.5)
        self.assertLess(result["ndcg_at_k"], 1.0)

    def test_rrf_deduplicates_within_one_ranking(self):
        fused = reciprocal_rank_fusion([["a", "a", "b"], ["b", "a"]], rank_constant=60)
        self.assertEqual([item[0] for item in fused], ["a", "b"])

    def test_context_deduplication(self):
        texts = ["住宿 标准 500 元", "住宿 标准 500 元", "报销 五天内提交"]
        self.assertEqual(len(deduplicate_contexts(texts)), 2)


class GroundingTests(unittest.TestCase):
    def test_citation_gate_detects_missing_and_ghost_citations(self):
        result = citation_metrics("住宿上限为 500 元 [1]。报销须在五天内提交。另见 [9]。", 2)
        self.assertEqual(result["invalid_source_ids"], [9])
        self.assertLess(result["citation_completeness"], 1.0)
        self.assertFalse(result["format_passed"])

    def test_newer_authoritative_source_wins(self):
        chosen = choose_current_sources([
            SourceVersion("old", "住宿标准", date(2025, 1, 1), authority=10),
            SourceVersion("draft", "住宿标准", date(2027, 1, 1), authority=1),
            SourceVersion("new", "住宿标准", date(2026, 7, 1), authority=10),
        ])
        self.assertEqual(chosen["住宿标准"].source_id, "new")


class ProductionTests(unittest.TestCase):
    def test_cache_key_changes_with_acl_or_snapshot(self):
        base = CacheScope("acme", "acl-a", "kb-v1", "model-a", "p1", "r1")
        acl_changed = CacheScope("acme", "acl-b", "kb-v1", "model-a", "p1", "r1")
        kb_changed = CacheScope("acme", "acl-a", "kb-v2", "model-a", "p1", "r1")
        self.assertNotEqual(base.key("年假多少天"), acl_changed.key("年假多少天"))
        self.assertNotEqual(base.key("年假多少天"), kb_changed.key("年假多少天"))

    def test_agent_budget_stops_loop(self):
        budget = RunBudget(max_retrievals=1)
        self.assertTrue(budget.consume("retrieval"))
        self.assertFalse(budget.consume("retrieval"))

    def test_index_requires_gate_and_can_rollback(self):
        manifest = IndexManifest("kb-v1")
        manifest.stage("kb-v2")
        with self.assertRaises(RuntimeError):
            manifest.promote(False)
        self.assertEqual(manifest.promote(True), "kb-v2")
        self.assertEqual(manifest.rollback(), "kb-v1")

    def test_percentile(self):
        self.assertEqual(percentile([10, 20, 30], 50), 20)
        self.assertGreater(percentile([10, 20, 30, 100], 95), 30)


if __name__ == "__main__":
    unittest.main()
