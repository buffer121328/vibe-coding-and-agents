import sys
import unittest
from pathlib import Path

import numpy as np

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(CODE_DIR / "KnowledgeForge_lite"))

import s02_data_pipeline as s02  # noqa: E402
import s05_hybrid_retrieval as s05  # noqa: E402
import s06_query_rewrite as s06  # noqa: E402
import s07_graphrag as s07  # noqa: E402
import s11_colbert_sparse as s11  # noqa: E402
import s14_multimodal_rag as s14  # noqa: E402
from forge_lite.citation import check_citations as lite_check_citations  # noqa: E402


class SectionCodeTests(unittest.TestCase):
    def test_generated_corpus_has_versions_trust_and_stable_ids(self):
        docs = s02.build_test_corpus()
        self.assertGreaterEqual(len(docs), 7)
        self.assertIn("deprecated", {doc.metadata["status"] for doc in docs})
        self.assertIn("quarantine", {doc.metadata["status"] for doc in docs})
        self.assertEqual(len({doc.metadata["chunk_id"] for doc in docs}), len(docs))
        self.assertGreater(s02.corpus_quality_report(docs)["mean_chars"], 50)

    def test_mmr_prefers_a_different_second_context(self):
        query = np.array([1.0, 0.0])
        candidates = np.array([[1.0, 0.0], [0.999, 0.001], [0.7, 0.7]])
        candidates /= np.linalg.norm(candidates, axis=1, keepdims=True)
        self.assertEqual(s05.mmr_select(query, candidates, 2, diversity=0.7), [0, 2])

    def test_rewrite_keeps_original_and_detects_multihop(self):
        original = "比较 2025 和 2026 标准，同时说明新版何时生效"
        merged = s06.merge_queries(original, ["住宿标准", "住宿标准"])
        self.assertEqual(merged[0], original)
        self.assertEqual(len(merged), 2)
        self.assertTrue(s06.should_decompose(original))

    def test_graph_search_routing(self):
        self.assertEqual(s07.choose_graph_search("整体架构分成哪几部分？"), "global")
        self.assertEqual(s07.choose_graph_search("谁依赖结算系统？"), "local")
        self.assertEqual(s07.choose_graph_search("住宿标准是多少？"), "basic")

    def test_colbert_uses_sum_not_mean(self):
        query = np.eye(2)
        document = np.eye(2)
        self.assertEqual(s11.colbert_maxsim(query, document), 2.0)

    def test_multimodal_guards(self):
        chunks = s14.build_time_windows([
            {"start": 0, "end": 30, "text": "甲", "confidence": 0.9},
            {"start": 30, "end": 50, "text": "乙", "confidence": 0.7},
            {"start": 50, "end": 70, "text": "丙", "confidence": 0.8},
        ], window_sec=45)
        self.assertEqual(chunks[0]["text"], "甲乙")
        self.assertEqual(chunks[0]["min_confidence"], 0.7)
        self.assertEqual(chunks[1]["text"], "乙丙")
        with self.assertRaises(PermissionError):
            s14.validate_table_operation("DROP TABLE payroll")

    def test_lite_project_checks_citation_completeness(self):
        self.assertEqual(lite_check_citations("住宿上限 500 元 [1]。", 1), (True, [1]))
        self.assertEqual(lite_check_citations("住宿上限 500 元 [1]。报销五天内提交。", 1)[0], False)


if __name__ == "__main__":
    unittest.main()
