"""评测契约：黄金集形状、Ragas 0.4 官方字段、缺依赖时的诚实降级。不调真模型。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.answer import evaluate as eval_mod  # noqa: E402


class GoldenSetTests(unittest.TestCase):
    def test_every_case_has_reference_and_badge(self):
        for case in eval_mod.GOLDEN_SET:
            with self.subTest(question=case["question"]):
                self.assertTrue(case["question"])
                self.assertTrue(case["reference"])
                self.assertIn(case["user_id"], {"it_staff", "hr_staff", "finance_head", "admin"})

    def test_refusal_cases_explain_expected_behavior(self):
        refusals = [case for case in eval_mod.GOLDEN_SET if "拒答" in case["reference"]]
        self.assertGreaterEqual(len(refusals), 2)
        for case in refusals:
            self.assertIn("应当拒答", case["reference"])

    def test_covers_both_public_and_department_docs(self):
        questions = " ".join(case["question"] for case in eval_mod.GOLDEN_SET)
        self.assertIn("住宿", questions)
        self.assertIn("E3", questions)
        self.assertIn("额度", questions)
        self.assertIn("薪酬", questions)


class SampleFieldTests(unittest.TestCase):
    def test_samples_use_ragas_04_field_names(self):
        fake_payload = {
            "answer": "一线城市住宿上限 500 元 [1]。",
            "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
            "status": "ok",
        }
        with patch.object(eval_mod, "ask", lambda question, user_id=None, persist=True: fake_payload):
            rows = eval_mod.collect_samples()
        self.assertEqual(len(rows), len(eval_mod.GOLDEN_SET))
        for row in rows:
            self.assertEqual(
                set(row) >= {"user_input", "retrieved_contexts", "response", "reference"},
                True,
            )
            self.assertIsInstance(row["retrieved_contexts"], list)

    def test_empty_retrieval_is_marked_not_silently_dropped(self):
        fake_payload = {"answer": "拒答", "contexts": [], "status": "refuse"}
        with patch.object(eval_mod, "ask", lambda question, user_id=None, persist=True: fake_payload):
            rows = eval_mod.collect_samples(eval_mod.GOLDEN_SET[:1])
        self.assertEqual(rows[0]["retrieved_contexts"], ["（无检索结果）"])

    def test_evaluate_never_persists_golden_questions(self):
        """evaluate() 跑黄金集时不能往会话柜写——用替身 ragas 模块进到函数体里断言。"""
        import types

        seen = {}

        def spy(question, user_id=None, persist=True, **kwargs):
            seen["persist"] = persist
            return {"answer": "x", "contexts": [], "status": "refuse"}

        fake_collections = types.ModuleType("ragas.metrics.collections")
        for name in ("Faithfulness", "ContextRecall", "AnswerRelevancy"):
            setattr(fake_collections, name, type(name, (), {"__init__": lambda self, **kw: None}))

        def close_and_empty(coro):
            try:
                coro.close()
            except Exception:
                pass
            return []

        with patch.dict(sys.modules, {"ragas.metrics.collections": fake_collections}), \
                patch.object(eval_mod, "ask", spy), \
                patch.object(eval_mod.asyncio, "run", close_and_empty):
            eval_mod.evaluate()
        self.assertIn("persist", seen)
        self.assertFalse(seen["persist"])


class DependencyGuardTests(unittest.TestCase):
    def test_missing_ragas_prints_install_hint_instead_of_crashing(self):
        import builtins
        real_import = builtins.__import__

        def guard(name, *args, **kwargs):
            if name.startswith("ragas"):
                raise ImportError("no ragas")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", guard):
            self.assertIsNone(eval_mod.evaluate())

    def test_alias_keeps_legacy_script_name_working(self):
        self.assertIs(eval_mod.ragas_evaluate, eval_mod.evaluate)

    def test_judge_factory_receives_thinking_kwargs(self):
        """裁判跟问答同一把旋钮：llm_factory 必须带上 extra_body，否则 Ragas 仍会开思考。"""
        seen: dict = {}

        class Dummy:
            def __init__(self, **kwargs):
                pass

        def spy_factory(*args, **kwargs):
            seen.update(kwargs)
            return Dummy()

        eval_mod._patch_vertexai()
        with patch("ragas.llms.llm_factory", spy_factory), \
                patch("ragas.embeddings.base.embedding_factory", lambda *a, **k: Dummy()), \
                patch("ragas.metrics.collections.Faithfulness", Dummy), \
                patch("ragas.metrics.collections.ContextRecall", Dummy), \
                patch("ragas.metrics.collections.AnswerRelevancy", Dummy), \
                patch.object(eval_mod, "_judge_clients", return_value=(object(), object())):
            eval_mod._build_judges()
        self.assertEqual(seen.get("extra_body"), {"thinking": {"type": "disabled"}})
        self.assertEqual(seen.get("max_tokens"), eval_mod.config.JUDGE_MAX_TOKENS)


if __name__ == "__main__":
    unittest.main()
