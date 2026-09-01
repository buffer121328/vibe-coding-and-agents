import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from s05_terminal_and_edit import str_replace, view_file
from s06_permissions_hitl import ActionRiskLevel, PermissionGuard
from s10_subagents import DeepResearchPipeline
from s12_observability import EvalCase, EvalSuite, TokenCostAudit
from s13_mini_agent import WebSearch


class PermissionGuardTests(unittest.TestCase):
    def test_exact_read_only_command_is_safe(self):
        risk, _ = PermissionGuard().evaluate_risk("run_bash", {"command": "git status --short"})
        self.assertEqual(risk, ActionRiskLevel.SAFE)

    def test_shell_control_operator_requires_approval(self):
        risk, _ = PermissionGuard().evaluate_risk("run_bash", {"command": "ls; touch changed"})
        self.assertEqual(risk, ActionRiskLevel.MODERATE)

    def test_read_only_command_cannot_target_outside_path(self):
        guard = PermissionGuard()
        ls_risk, _ = guard.evaluate_risk("run_bash", {"command": "ls /"})
        diff_risk, _ = guard.evaluate_risk(
            "run_bash", {"command": "git diff --no-index /etc/passwd /dev/null"}
        )
        self.assertEqual(ls_risk, ActionRiskLevel.MODERATE)
        self.assertEqual(diff_risk, ActionRiskLevel.MODERATE)

    def test_noninteractive_moderate_action_fails_closed(self):
        called = False

        def execute(**_kwargs):
            nonlocal called
            called = True

        result = PermissionGuard().check_and_execute(
            "run_bash", {"command": "whoami"}, execute, interactive_prompt=False
        )
        self.assertFalse(result["approved"])
        self.assertFalse(called)

    def test_explicit_callback_can_approve(self):
        result = PermissionGuard(lambda _tool, _args: True).check_and_execute(
            "run_bash", {"command": "whoami"}, lambda **_kwargs: "ok", interactive_prompt=False
        )
        self.assertTrue(result["approved"])
        self.assertEqual(result["result"], "ok")


class WorkspaceBoundaryTests(unittest.TestCase):
    def test_read_and_edit_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            secret = Path(outside, "secret.txt")
            secret.write_text("secret", encoding="utf-8")
            self.assertIn("超出工作区", view_file(str(secret), workspace_root=root))
            ok, message, _ = str_replace(str(secret), "secret", "changed", workspace_root=root)
            self.assertFalse(ok)
            self.assertIn("超出工作区", message)
            self.assertEqual(secret.read_text(encoding="utf-8"), "secret")

    def test_edit_inside_workspace_still_works(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "demo.txt")
            target.write_text("before", encoding="utf-8")
            ok, _, diff = str_replace("demo.txt", "before", "after", workspace_root=root)
            self.assertTrue(ok)
            self.assertIn("+after", diff)
            self.assertEqual(target.read_text(encoding="utf-8"), "after")


class SearchTruthfulnessTests(unittest.TestCase):
    def test_network_failure_returns_explicit_error(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("offline")):
            result = WebSearch().search("任意主题")
        self.assertTrue(result.startswith("❌ 搜索失败"))
        self.assertIn("不会生成虚假兜底内容", result)
        self.assertNotIn("前端技术生态", result)


class EvaluationTests(unittest.TestCase):
    def test_unverified_task_has_no_success_rate(self):
        suite = EvalSuite(client=None, tasks=["开放问题"], trials=1)
        report = suite.run_eval(lambda _bus, _task: "✅ 我自称完成了")
        self.assertIsNone(report["tasks"]["开放问题"]["success_rate"])
        self.assertIsNone(report["summary"]["overall_success_rate"])

    def test_validator_checks_result_not_claim(self):
        case = EvalCase("算术", "2+2", lambda output: "4" in output)
        suite = EvalSuite(client=None, tasks=[case], trials=1)
        report = suite.run_eval(lambda _bus, _task: "✅ 已完成，但答案是 5")
        self.assertEqual(report["tasks"]["算术"]["success_rate"], 0.0)

    def test_cost_is_unknown_without_explicit_price(self):
        audit = TokenCostAudit()
        audit.record_usage("some-model", 100, 50)
        self.assertIn("未配置当前官方价格", audit.summary())


class ResearchEvidenceTests(unittest.TestCase):
    def test_pipeline_records_search_evidence(self):
        class FakeResponse:
            def __init__(self, content):
                self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]

        class FakeClient:
            def chat(self, messages, **_kwargs):
                if "查询词" in messages[0]["content"]:
                    return FakeResponse("official agent docs")
                return FakeResponse("基于输入证据的分析")

        pipeline = DeepResearchPipeline(
            FakeClient(), search_provider=lambda query: f"https://example.com/docs\n{query} 的来源"
        )
        report = pipeline.execute_research("Agent 工程")
        self.assertIn("https://example.com/docs", report["evidence"])
        self.assertIn("证据收集", [item["stage"] for item in report["timeline"]])


if __name__ == "__main__":
    unittest.main()
