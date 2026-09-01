"""
s06_permissions_hitl.py - 8.6 权限控制与人类在环 (Permission Gate & Human-in-the-Loop)
"""
import shlex
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
            "query_user_profile", "get_weather", "calculate", "web_search"
        )
        
        # 只允许不带 Shell 控制符的精确只读命令。cat/echo 不在其中：前者可能读密钥，后者可配合重定向写文件。
        self.shell_control_chars = (";", "|", "&", ">", "<", "`", "$", "\n", "\r")
        self.critical_bash_keywords = (
            "rm -rf", "shutdown", "reboot", ":(){ :|:& };:", "dd if=", "mkfs",
            "chmod -r", "chown -r", ">/dev/", "> /dev/",
        )

    @staticmethod
    def _is_safe_read_only_argv(argv: Tuple[str, ...]) -> bool:
        """只放行不会指定外部路径、加载脚本或组合子命令的少量参数。"""
        if argv in (("pwd",), ("python", "--version"), ("python3", "--version")):
            return True
        if argv and argv[0] == "ls":
            return all(arg.startswith("-") and set(arg[1:]) <= set("alh1") for arg in argv[1:])
        if argv[:2] == ("git", "status"):
            return all(arg in {"--short", "--branch", "--porcelain", "--porcelain=v1"} for arg in argv[2:])
        if argv[:2] == ("git", "log"):
            allowed = {"--oneline", "--decorate", "--no-decorate", "--graph", "--all"}
            return all(arg in allowed or (arg.startswith("-n") and arg[2:].isdigit())
                       or (arg.startswith("--max-count=") and arg.split("=", 1)[1].isdigit())
                       for arg in argv[2:])
        if argv[:2] == ("git", "diff"):
            allowed = {"--stat", "--name-only", "--name-status", "--cached", "--staged", "--check"}
            return all(arg in allowed for arg in argv[2:])
        return False

    def _classify_bash(self, command: str) -> Tuple[ActionRiskLevel, str]:
        """解析命令后分级，避免 `startswith('ls')` 把 `ls; dangerous` 错当成只读。"""
        command = command.strip()
        lowered = command.lower()
        if not command:
            return ActionRiskLevel.MODERATE, "终端命令为空，无法确认意图"
        for bad in self.critical_bash_keywords:
            if bad in lowered:
                return ActionRiskLevel.CRITICAL, f"检测到高危命令片段: [{bad}]"
        if any(char in command for char in self.shell_control_chars):
            return ActionRiskLevel.MODERATE, "命令包含管道、重定向或多命令控制符，必须人工确认"
        try:
            argv = tuple(shlex.split(command))
        except ValueError as exc:
            return ActionRiskLevel.MODERATE, f"命令语法无法安全解析: {exc}"
        if self._is_safe_read_only_argv(argv):
            return ActionRiskLevel.SAFE, f"精确匹配只读白名单命令: [{command}]"
        return ActionRiskLevel.MODERATE, f"执行非白名单终端命令: [{command}]"

    def evaluate_risk(self, tool_name: str, args: Dict[str, Any]) -> Tuple[ActionRiskLevel, str]:
        """🔍 评估即将执行的工具调用的风险等级"""
        if tool_name in self.safe_tools:
            return ActionRiskLevel.SAFE, f"只读/检索工具 [{tool_name}]，无系统写入动作"

        if tool_name in ("str_replace", "edit_file_replace"):
            path = args.get("file_path", "")
            return ActionRiskLevel.MODERATE, f"正在尝试修改本地源码文件: [{path}]"

        if tool_name in ("run_bash", "exec_bash"):
            return self._classify_bash(str(args.get("command", "")))

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
        approval_source = ""
        if self.approval_callback:
            try:
                approved = bool(self.approval_callback(tool_name, args))
                approval_source = "审批回调"
            except Exception:
                approved = False
                approval_source = "审批回调异常，按拒绝处理"
        elif interactive_prompt and sys.stdin.isatty():
            # 仅在真实终端交互环境下提示 stdin
            print(f"\n⚠️  [权限审批请求] 工具: {tool_name} | 参数: {args}")
            print(f"📝 风险原因: {reason}")
            choice = input("👉 是否授权执行该操作？ (y/N): ").strip().lower()
            approved = (choice == "y")
            approval_source = "终端人工审批"
        else:
            # Fail closed：没有明确的人类批准就不执行，Web UI 必须传 approval_callback。
            approved = False
            approval_source = "非交互环境未获得明确批准"

        if approved:
            res = execution_fn(**{k: v for k, v in args.items() if not k.startswith("_")})
            return {
                "success": True,
                "approved": True,
                "risk": risk.value,
                "message": f"🟡 [{approval_source}通过，已执行] {reason}",
                "result": res,
            }
        else:
            return {
                "success": False,
                "approved": False,
                "risk": risk.value,
                "message": f"❌ [{approval_source}，未执行] {reason}",
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
