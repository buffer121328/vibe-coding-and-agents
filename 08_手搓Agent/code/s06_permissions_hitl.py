"""
s06_permissions_hitl.py - 8.6 权限控制与人类在环 (Permission Gate & Human-in-the-Loop)
"""
import sys
from enum import Enum
from typing import Dict, Any, Tuple, Optional, Callable

class ActionRiskLevel(str, Enum):
    """🚦 工具调用风险等级（自动放行 / 人类审批 / 永久阻断）"""
    SAFE = "safe"              # 只读安全操作 (自动放行)
    MODERATE = "moderate"      # 修改文件/执行环境命令 (需人类二次确认)
    CRITICAL = "critical"      # 极高危破坏性操作 (默认永久阻断)

class PermissionGuard:
    """🛡️ 权限安全门禁与 Human-in-the-Loop (人类在环) 审核器"""
    def __init__(self, human_approval_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None):
        self.approval_callback = human_approval_callback
        
        # 安全白名单只读工具集合
        self.safe_tools = (
            "view_file", "read_file", "list_dir", "get_user_info", 
            "query_user_profile", "get_weather", "calculate", "web_search", 
            "save_preference"
        )
        
        # 安全白名单命令 (前缀匹配)
        self.safe_bash_prefixes = ("ls", "cat", "echo", "pwd", "git status", "git log", "git diff", "python --version", "python3 --version")
        # 永久黑名单
        self.critical_bash_keywords = ("rm -rf /", "shutdown", "reboot", ":(){ :|:& };:", "dd if=", "mkfs")

    def evaluate_risk(self, tool_name: str, args: Dict[str, Any]) -> Tuple[ActionRiskLevel, str]:
        """🔍 评估即将执行的工具调用的风险等级"""
        if tool_name in self.safe_tools:
            return ActionRiskLevel.SAFE, f"只读/检索/记忆工具 [{tool_name}]，无系统破坏风险"

        if tool_name in ("str_replace", "edit_file_replace"):
            path = args.get("file_path", "")
            return ActionRiskLevel.MODERATE, f"正在尝试修改本地源码文件: [{path}]"

        if tool_name in ("run_bash", "exec_bash"):
            cmd = args.get("command", "").strip()
            # 检查极高危
            for bad in self.critical_bash_keywords:
                if bad in cmd:
                    return ActionRiskLevel.CRITICAL, f"检测到恶意破坏性命令关键字: [{bad}]"
            # 检查安全白名单
            for safe in self.safe_bash_prefixes:
                if cmd.startswith(safe):
                    return ActionRiskLevel.SAFE, f"白名单只读命令: [{cmd}]"
            # 其余一律视为中风险
            return ActionRiskLevel.MODERATE, f"执行非白名单终端命令: [{cmd}]"

        return ActionRiskLevel.MODERATE, f"执行自定义外部工具: [{tool_name}]"

    def check_and_execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        execution_fn: Callable[..., Any],
        interactive_prompt: bool = True
    ) -> Dict[str, Any]:
        """🚧 门禁审核与执行闭环（阻断 / 放行 / 审批三态流转）"""
        risk, reason = self.evaluate_risk(tool_name, args)

        if risk == ActionRiskLevel.CRITICAL:
            return {
                "success": False,
                "approved": False,
                "risk": risk.value,
                "message": f"🚫 [安全门禁永久阻断] {reason}",
                "result": None,
            }

        if risk == ActionRiskLevel.SAFE:
            # 自动放行（剥离 Hooks 注入的下划线内部元数据，如 _start_time）
            res = execution_fn(**{k: v for k, v in args.items() if not k.startswith("_")})
            return {
                "success": True,
                "approved": True,
                "risk": risk.value,
                "message": f"🟢 [自动放行] {reason}",
                "result": res,
            }

        # 中风险：触发人类在环审批 (Human-in-the-Loop)
        if self.approval_callback:
            approved = self.approval_callback(tool_name, args)
        elif interactive_prompt and sys.stdin.isatty():
            # 仅在真实终端交互环境下提示 stdin
            print(f"\n⚠️  [权限审批请求] 工具: {tool_name} | 参数: {args}")
            print(f"📝 风险原因: {reason}")
            choice = input("👉 是否授权执行该操作？ (y/N): ").strip().lower()
            approved = (choice == "y")
        else:
            # Web UI 或非交互模式下默认放行中风险（并在日志/Trace 中显式标记 HITL 审计）
            approved = True

        if approved:
            res = execution_fn(**{k: v for k, v in args.items() if not k.startswith("_")})
            return {
                "success": True,
                "approved": True,
                "risk": risk.value,
                "message": f"🟡 [人类审批通过已执行] {reason}",
                "result": res,
            }
        else:
            return {
                "success": False,
                "approved": False,
                "risk": risk.value,
                "message": f"❌ [人类已拒绝执行该操作] {reason}",
                "result": "操作被人类管理员取消",
            }

if __name__ == "__main__":
    from s05_terminal_and_edit import run_bash

    print("--- 1. 安全命令 (自动放行) ---")
    guard = PermissionGuard()
    res1 = guard.check_and_execute("run_bash", {"command": "ls -l"}, run_bash)
    print(res1["message"], "| 执行结果非空:", bool(res1["result"] is not None))

    print("\n--- 2. 极高危命令 (永久阻断) ---")
    res2 = guard.check_and_execute("run_bash", {"command": "rm -rf /"}, run_bash)
    print(res2["message"])

    print("\n--- 3. 中风险命令: 人类批准 vs 人类拒绝 (Human-in-the-Loop) ---")
    approve_guard = PermissionGuard(human_approval_callback=lambda tool, args: True)
    res3 = approve_guard.check_and_execute("run_bash", {"command": "whoami"}, run_bash)
    print("批准通过:", res3["message"], "|", res3["result"])

    reject_guard = PermissionGuard(human_approval_callback=lambda tool, args: False)
    res4 = reject_guard.check_and_execute("run_bash", {"command": "whoami"}, run_bash)
    print("拒绝执行:", res4["message"])

    print("\n--- 4. 风险分级自测 (str_replace / web_search) ---")
    print("str_replace 风险等级:", guard.evaluate_risk("str_replace", {"file_path": "main.py"})[0].value)
    print("web_search 风险等级:", guard.evaluate_risk("web_search", {"query": "React 19"})[0].value)
