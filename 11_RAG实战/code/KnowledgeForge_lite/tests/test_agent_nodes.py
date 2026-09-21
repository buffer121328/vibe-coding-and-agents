"""自省闭环节点：预算熔断、分级拒答、引用回炉、复检兜底。生成模型全部用替身。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite import llm as llm_mod
from forge_lite.answer import agent as agent_mod  # noqa: E402
from forge_lite.retrieve.citation import REFUSAL, Source  # noqa: E402
from forge_lite.core.quality import RunBudget  # noqa: E402


def _source(key="员工差旅管理制度.md#0"):
    return Source(doc_id=key, text="一线城市住宿标准为每人每天不超过 500 元。", why="被 bm25 召回")


def _state(**over):
    base = {
        "question": "去上海出差住一晚能报多少？",
        "queries": ["去上海出差住一晚能报多少？"],
        "sources": [_source()],
        "answer": "",
        "citations": [],
        "attempts": 0,
        "budget": RunBudget(),
        "status": "ok",
        "warn": "",
        "user_id": "it_staff",
        "intent": "factoid",
        "routes": "bm25+dense",
        "evidence": {},
    }
    base.update(over)
    return base


class FakeStructured:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def invoke(self, _prompt, *_args, **_kwargs):
        self.calls += 1
        return self.value


class FakeLLM:
    """按 schema 分派的替身：Grade / FaithCheck 各给一个固定回答。"""

    def __init__(self, grade=None, faith=None, content="答案 [1]。"):
        self.grade = FakeStructured(grade) if grade is not None else None
        self.faith = FakeStructured(faith) if faith is not None else None
        self.content = content
        self.invokes = 0

    def with_structured_output(self, schema):
        if schema is agent_mod.Grade:
            return self.grade
        return self.faith

    def invoke(self, *_args, **_kwargs):
        self.invokes += 1

        class Resp:
            content = self.content

        return Resp()


class RetrieveBudgetTests(unittest.TestCase):
    def test_exhausted_budget_refuses_without_search(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("预算用尽后不该再检索")

        with patch.object(agent_mod, "hybrid_search", boom):
            result = agent_mod.n_retrieve(_state(budget=RunBudget(max_retrievals=0)))
        self.assertEqual(result["status"], "refuse")
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["answer"], REFUSAL)

    def test_graph_degradation_is_written_into_warn(self):
        hits = [{
            "source": "员工差旅管理制度.md", "chunk_index": 0,
            "text": "一线城市住宿标准为每人每天不超过 500 元。",
            "route": "bm25+dense", "why": "被 bm25 召回", "degraded": "graph_unavailable",
        }]
        with patch.object(agent_mod, "hybrid_search", lambda *_a, **_k: hits):
            result = agent_mod.n_retrieve(_state())
        self.assertIn("图谱", result["warn"])
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0].doc_id, "员工差旅管理制度.md#0")
        self.assertTrue(result["evidence"])


class GradeTests(unittest.TestCase):
    def test_evidence_disqualification_refuses_without_calling_llm(self):
        fake = FakeLLM(grade=type("G", (), {"relevant": True, "reason": ""})())
        with patch.object(llm_mod, "get_llm", lambda: fake):
            result = agent_mod.n_grade(_state(evidence={
                "response_status": "insufficient_evidence",
                "allows_generation": False,
                "reason_codes": ["zero_results"],
                "missing_information": [{"field": "x", "description": "缺少住宿金额记录"}],
            }))
        self.assertEqual(result["status"], "refuse")
        self.assertIn("证据资格", result["warn"])
        self.assertIn("缺少住宿金额记录", result["warn"])
        self.assertEqual(fake.grade.calls, 0)

    def test_empty_sources_short_circuit(self):
        result = agent_mod.n_grade(_state(sources=[], evidence={}))
        self.assertEqual(result["status"], "refuse")

    def test_irrelevant_grade_refuses(self):
        fake = FakeLLM(grade=type("G", (), {"relevant": False, "reason": "没写"} )())
        with patch.object(llm_mod, "get_llm", lambda: fake):
            result = agent_mod.n_grade(_state())
        self.assertEqual(result["status"], "refuse")
        self.assertEqual(fake.grade.calls, 1)

    def test_qualified_evidence_skips_llm_veto(self):
        """资格已经放行时，模型再说「不相关」也不能把该答的题拦下来。"""
        fake = FakeLLM(grade=type("G", (), {"relevant": False, "reason": "看起来不像"})())
        with patch.object(llm_mod, "get_llm", lambda: fake):
            result = agent_mod.n_grade(_state(evidence={
                "response_status": "answered",
                "allows_generation": True,
                "reason_codes": ["direct_support"],
            }))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(fake.grade.calls, 0)


class CheckTests(unittest.TestCase):
    def test_ghost_citation_triggers_one_regen(self):
        result = agent_mod.n_check(_state(answer="住宿 500 元 [9]。"))
        self.assertEqual(result["status"], "regen")
        self.assertEqual(result["attempts"], 1)

    def test_ghost_citation_without_budget_refuses(self):
        result = agent_mod.n_check(_state(answer="住宿 500 元 [9]。", budget=RunBudget(max_rewrites=0)))
        self.assertEqual(result["status"], "refuse")

    def test_good_answer_builds_citations(self):
        result = agent_mod.n_check(_state(answer="一线城市住宿上限 500 元 [1]。"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["citations"][0]["doc_id"], "员工差旅管理制度.md#0")

    def test_资料不足_prefix_becomes_refusal(self):
        result = agent_mod.n_check(_state(answer="【资料不足】"))
        self.assertEqual(result["status"], "refuse")
        self.assertEqual(result["answer"], REFUSAL)


class VerifyTests(unittest.TestCase):
    def test_refusal_passes_through(self):
        state = _state(status="refuse")
        self.assertIs(agent_mod.n_verify(state), state)

    def test_unfaithful_answer_gets_one_regen_then_refuses(self):
        fake = FakeLLM(faith=type("F", (), {"faithful": False, "bad_spans": ["编的句子"]})())
        proof = {"answer": "一线城市住宿上限 500 元 [1]。", "citations": [{"marker": "[1]", "doc_id": "a.md#0"}]}
        with patch.object(llm_mod, "get_llm", lambda: fake):
            regen = agent_mod.n_verify(_state(**proof))
            stopped = agent_mod.n_verify(_state(budget=RunBudget(max_rewrites=0), **proof))
        self.assertEqual(regen["status"], "regen")
        self.assertIn("编的句子", regen["warn"])
        self.assertEqual(stopped["status"], "refuse")

    def test_faithful_answer_finishes(self):
        fake = FakeLLM(faith=type("F", (), {"faithful": True, "bad_spans": []})())
        proof = {"answer": "一线城市住宿上限 500 元 [1]。", "citations": [{"marker": "[1]", "doc_id": "a.md#0"}]}
        with patch.object(llm_mod, "get_llm", lambda: fake):
            result = agent_mod.n_verify(_state(**proof))
        self.assertEqual(result["status"], "ok")


class RewriteNodeTests(unittest.TestCase):
    def test_multi_hop_signal_adds_warning_only(self):
        state = _state(question="比较一线和二线标准，同时说明报销时限，以及适用人群范围如何界定？")
        with patch.object(agent_mod, "expand_queries", lambda question, llm: [question]):
            result = agent_mod.n_rewrite(state)
        self.assertIn("多跳", result["warn"])
        self.assertEqual(result["queries"], [state["question"]])

    def test_rewrite_disabled_keeps_question_only(self):
        from forge_lite import config
        original = config.ENABLE_REWRITE
        config.ENABLE_REWRITE = False
        try:
            with patch.object(agent_mod, "expand_queries", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该调用"))):
                result = agent_mod.n_rewrite(_state())
        finally:
            config.ENABLE_REWRITE = original
        self.assertEqual(result["queries"], ["去上海出差住一晚能报多少？"])
        self.assertEqual(result["intent"], "factoid")


class RouteTableTests(unittest.TestCase):
    def test_grade_routes(self):
        self.assertEqual(agent_mod.route_after_grade({"status": "ok"}), "generate")
        self.assertEqual(agent_mod.route_after_grade({"status": "refuse"}), "end")

    def test_check_routes(self):
        self.assertEqual(agent_mod.route_after_check({"status": "ok"}), "verify")
        self.assertEqual(agent_mod.route_after_check({"status": "regen"}), "generate")
        self.assertEqual(agent_mod.route_after_check({"status": "refuse"}), "end")

    def test_verify_routes(self):
        self.assertEqual(agent_mod.route_after_verify({"status": "regen"}), "generate")
        self.assertEqual(agent_mod.route_after_verify({"status": "ok"}), "end")


if __name__ == "__main__":
    unittest.main()


class RouteUnionTests(unittest.TestCase):
    """路由徽章取「单条通道」的并集，不是把组合串整串去重。"""

    def test_combined_route_strings_do_not_duplicate(self):
        hits = [
            {"source": "a.md", "chunk_index": 0, "text": "甲", "route": "bm25+dense",
             "why": "w", "degraded": None},
            {"source": "b.md", "chunk_index": 0, "text": "乙", "route": "bm25+dense+graph",
             "why": "w", "degraded": None},
        ]
        with patch.object(agent_mod, "hybrid_search", lambda *_a, **_k: hits):
            result = agent_mod.n_retrieve(_state())
        self.assertEqual(result["routes"], "bm25+dense+graph")

    def test_single_lane_route_stays_clean(self):
        hits = [{"source": "a.md", "chunk_index": 0, "text": "甲", "route": "graph",
                 "why": "w", "degraded": None}]
        with patch.object(agent_mod, "hybrid_search", lambda *_a, **_k: hits):
            result = agent_mod.n_retrieve(_state())
        self.assertEqual(result["routes"], "graph")
