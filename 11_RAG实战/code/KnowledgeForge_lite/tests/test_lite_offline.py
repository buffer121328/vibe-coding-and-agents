"""KnowledgeForge Lite 离线门禁：不调模型、不访问网络。

覆盖总装里从 11.2 / 11.5 / 11.6 / 11.8 / 11.9 / 11.12 / 11.13 搬进来的纯函数。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.retrieve.citation import check_citations  # noqa: E402
from forge_lite.data.ingest import clean_text, context_header, _trust_of  # noqa: E402
from forge_lite.core.quality import (  # noqa: E402
    SOURCE_WEIGHTS,
    RunBudget,
    citation_metrics,
    explain_retrieval,
    mask_pii,
    order_contexts,
    pack_contexts,
    reciprocal_rank_fusion,
    retrieval_metrics,
    scan_poisoning,
)
from forge_lite.core.identity import authorize_chunks, can_see, resolve_actor  # noqa: E402
from forge_lite.data.knowledge_graph import graph_hits  # noqa: E402
from forge_lite.core.rewrite import (  # noqa: E402
    classify_intent_local,
    expand_queries,
    merge_queries,
    rewrite_query_local,
    should_decompose,
)
from forge_lite.answer.agent import route_after_check, route_after_grade, route_after_verify  # noqa: E402


class IngestBasicsTests(unittest.TestCase):
    def test_clean_text_keeps_markdown_page_headings(self):
        raw = "## 第 1 页：年假资格\n正式员工入职满一年后享有 5 天带薪年假。\n第 38 页\n"
        cleaned = clean_text(raw)
        self.assertIn("## 第 1 页：年假资格", cleaned)
        self.assertNotIn("第 38 页", cleaned)

    def test_context_header_uses_stem(self):
        self.assertEqual(context_header("员工差旅管理制度.md"), "《员工差旅管理制度》")

    def test_html_injection_sample_is_external(self):
        html = ROOT / "data" / "docs" / "外部网页快照_含注入样本.html"
        self.assertTrue(html.exists())
        self.assertEqual(_trust_of(html), "external")
        text = html.read_text(encoding="utf-8")
        signals = scan_poisoning(text, trust_level="external")
        self.assertTrue(any("指令句式" in s for s in signals))
        self.assertTrue(any("低信任来源" in s for s in signals))


class RetrievalBasicsTests(unittest.TestCase):
    def test_rrf_deduplicates_within_one_ranking(self):
        fused = reciprocal_rank_fusion([["a", "a", "b"], ["b", "a"]], rank_constant=60)
        self.assertEqual([item[0] for item in fused], ["a", "b"])

    def test_context_ordering_puts_best_at_both_ends(self):
        ordered = order_contexts([("a", 0.9), ("b", 0.8), ("c", 0.5), ("d", 0.2)])
        self.assertEqual(ordered, ["a", "d", "c", "b"])
        self.assertEqual(order_contexts([]), [])
        self.assertEqual(order_contexts([("only", 0.1)]), ["only"])

    def test_pack_contexts_drops_near_duplicates(self):
        packed = pack_contexts(
            ["一线城市住宿上限 500 元。", "一线城市住宿上限 500 元。", "报销须在五天内提交。"],
            max_chars=40,
        )
        self.assertEqual(len(packed), 2)

    def test_explain_retrieval_does_not_mutate_input(self):
        hits = [{"id": "x", "route": "bm25", "score": 0.8, "rank": 2}]
        explained = explain_retrieval(hits)
        self.assertIn("bm25", explained[0]["why"])
        self.assertFalse(explained[0]["is_confidence_comparable"])
        self.assertNotIn("why", hits[0])


class RewriteBasicsTests(unittest.TestCase):
    def test_rewrite_keeps_original_first(self):
        original = "比较 2025 和 2026 标准，同时说明新版何时生效"
        merged = merge_queries(original, ["住宿标准", "住宿标准"])
        self.assertEqual(merged[0], original)
        self.assertEqual(len(merged), 2)
        self.assertTrue(should_decompose(original))

    def test_expand_without_llm_uses_local_rules(self):
        queries = expand_queries("住宿上限？", llm=None)
        self.assertEqual(queries[0], "住宿上限？")
        self.assertGreaterEqual(len(queries), 1)

    def test_local_rewrite_splits_enumerated_topics(self):
        rewritten = rewrite_query_local("招聘、培训和绩效考核分别有什么制度要求？")
        self.assertEqual(rewritten["queries"][0], "招聘、培训和绩效考核分别有什么制度要求？")
        self.assertTrue(any(q.startswith("招聘") for q in rewritten["queries"][1:]))
        self.assertEqual(classify_intent_local("打印机 E3 怎么处理？"), "procedural")


class CitationAndBudgetTests(unittest.TestCase):
    def test_lite_project_checks_citation_completeness(self):
        self.assertEqual(check_citations("住宿上限 500 元 [1]。", 1), (True, [1]))
        self.assertEqual(check_citations("住宿上限 500 元 [1]。报销五天内提交。", 1)[0], False)

    def test_citation_metrics_catch_ghosts(self):
        result = citation_metrics("住宿上限为 500 元 [1]。报销须在五天内提交。另见 [9]。", 2)
        self.assertEqual(result["invalid_source_ids"], [9])
        self.assertFalse(result["format_passed"])

    def test_agent_budget_stops_loop(self):
        budget = RunBudget(max_rewrites=1)
        self.assertTrue(budget.consume("rewrite"))
        self.assertFalse(budget.consume("rewrite"))

    def test_lite_routes_skip_generation_when_refused(self):
        self.assertEqual(route_after_grade({"status": "refuse"}), "end")
        self.assertEqual(route_after_check({"status": "refuse"}), "end")
        self.assertEqual(route_after_check({"status": "regen"}), "generate")
        self.assertEqual(route_after_verify({"status": "ok"}), "end")

    def test_mask_pii_hides_identifiers(self):
        masked = mask_pii("电话 13812345678，邮箱 ops@example.com")
        self.assertNotIn("13812345678", masked)
        self.assertNotIn("ops@example.com", masked)


class SeedDocsTests(unittest.TestCase):
    def test_seed_docs_still_contain_gold_numbers(self):
        travel = (ROOT / "data" / "docs" / "员工差旅管理制度.md").read_text(encoding="utf-8")
        faq = (ROOT / "data" / "docs" / "产品FAQ.md").read_text(encoding="utf-8")
        ops = (ROOT / "data" / "docs" / "运维故障案例.md").read_text(encoding="utf-8")
        self.assertIn("500 元", travel)
        self.assertIn("5 个工作日", travel)
        self.assertIn("100 次问答", faq)
        self.assertIn("E3", ops)
        self.assertNotIn("年终奖", travel + faq + ops)
        pay = (ROOT / "data" / "docs" / "财务薪酬密级.md").read_text(encoding="utf-8")
        self.assertIn("35 万至 45 万元", pay)

    def test_ingest_quarantines_injection_html(self):
        """投毒 HTML 不得进入 BM25 语料（隔离 = 不进检索，不是删源文件）。"""
        from forge_lite import config
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime = tmp_path / "runtime"
            docs = tmp_path / "docs"
            docs.mkdir()
            (docs / "员工差旅管理制度.md").write_text(
                (ROOT / "data" / "docs" / "员工差旅管理制度.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (docs / "外部网页快照_含注入样本.html").write_text(
                (ROOT / "data" / "docs" / "外部网页快照_含注入样本.html").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            old_docs, old_runtime = config.DOCS_DIR, config.RUNTIME_DIR
            old_chroma, old_chunks, old_store = config.CHROMA_DIR, config.CHUNKS_JSON, config.DOCSTORE_JSON
            config.DOCS_DIR = docs
            config.RUNTIME_DIR = runtime
            config.CHROMA_DIR = runtime / "chroma"
            config.CHUNKS_JSON = runtime / "chunks.json"
            config.DOCSTORE_JSON = runtime / "docstore.json"
            try:
                from forge_lite.data.ingest import _iter_source_files, _read_source, _trust_of, clean_text
                from forge_lite.core.quality import scan_poisoning
                indexed, quarantined = [], 0
                for path in _iter_source_files(docs):
                    text = clean_text(_read_source(path))
                    signals = scan_poisoning(text, trust_level=_trust_of(path))
                    if signals:
                        quarantined += 1
                        continue
                    indexed.append(path.name)
                self.assertEqual(quarantined, 1)
                self.assertEqual(indexed, ["员工差旅管理制度.md"])
            finally:
                config.DOCS_DIR = old_docs
                config.RUNTIME_DIR = old_runtime
                config.CHROMA_DIR = old_chroma
                config.CHUNKS_JSON = old_chunks
                config.DOCSTORE_JSON = old_store


class AclAndGraphTests(unittest.TestCase):
    def _chunks(self):
        return [
            {"source": "员工差旅管理制度.md", "chunk_index": 0, "text": "一线城市住宿标准上限为每人每天500元",
             "department": "company", "sensitivity": "public", "acl": "employee"},
            {"source": "运维故障案例.md", "chunk_index": 0, "text": "打印机E3处理方法是关闭电源取出卡纸",
             "department": "it", "sensitivity": "department", "acl": "employee"},
            {"source": "财务薪酬密级.md", "chunk_index": 0, "text": "P6薪酬带宽年薪为35万至45万元",
             "department": "finance", "sensitivity": "restricted", "acl": "restricted"},
        ]

    def test_employee_cannot_see_restricted_or_other_department(self):
        hr = resolve_actor("hr_staff")
        visible = authorize_chunks(self._chunks(), hr)
        self.assertEqual([c["source"] for c in visible], ["员工差旅管理制度.md"])
        self.assertFalse(can_see(resolve_actor("it_staff"), self._chunks()[2]))

    def test_finance_head_sees_restricted_pay_band(self):
        names = [c["source"] for c in authorize_chunks(self._chunks(), "finance_head")]
        self.assertIn("财务薪酬密级.md", names)
        self.assertNotIn("运维故障案例.md", names)

    def test_admin_sees_everything(self):
        admin = resolve_actor("admin")
        self.assertIsNone(admin.visible_department_ids())
        self.assertEqual(len(authorize_chunks(self._chunks(), admin)), 3)

    def test_graph_hits_map_back_to_source_chunks(self):
        hits = graph_hits(["一线城市住宿标准"], self._chunks(), limit=3)
        self.assertTrue(hits)
        self.assertTrue(all("source" in hit and "chunk_index" in hit for hit in hits))
        self.assertIn("员工差旅管理制度.md", {hit["source"] for hit in hits})

    def test_graph_hits_respect_already_authorized_pool(self):
        hr_visible = authorize_chunks(self._chunks(), "hr_staff")
        hits = graph_hits(["P6薪酬带宽"], hr_visible, limit=3)
        self.assertEqual(hits, [])

    def test_rrf_weights_prefer_graph_on_tied_ranks(self):
        fused = reciprocal_rank_fusion(
            [["pay"], ["stay"], ["pay"]],
            rank_constant=60,
            weights=[SOURCE_WEIGHTS["bm25"], SOURCE_WEIGHTS["vector"], SOURCE_WEIGHTS["graph"]],
        )
        self.assertEqual(fused[0][0], "pay")


class RetrievalMetricsTests(unittest.TestCase):
    def test_hit_and_recall_on_file_names(self):
        result = retrieval_metrics(
            ["员工差旅管理制度.md", "产品FAQ.md"],
            ["员工差旅管理制度.md"],
            k=2,
        )
        self.assertEqual(result["hit_rate_at_k"], 1.0)
        self.assertEqual(result["recall_at_k"], 1.0)


if __name__ == "__main__":
    unittest.main()
