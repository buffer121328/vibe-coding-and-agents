"""
s07_hooks_lifecycle.py - 8.7 Hooks 生命周期机制 (AOP 切面拦截、参数脱敏与审计)
"""
import time
import re
from typing import Callable, List, Dict, Any, Optional

class HookManager:
    """🪝 Agent 全生命周期钩子管理中心 (AOP 面向切面扩展)"""
    def __init__(self):
        self.pre_tool_hooks: List[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]] = []
        self.post_tool_hooks: List[Callable[[str, Dict[str, Any], Any], Any]] = []
        self.on_error_hooks: List[Callable[[str, Dict[str, Any], Exception], None]] = []

    def register_pre_tool(self, hook: Callable):
        """📥 注册前置钩子（参数预检 / 加工）"""
        self.pre_tool_hooks.append(hook)

    def register_post_tool(self, hook: Callable):
        """📤 注册后置钩子（脱敏 / 加工结果）"""
        self.post_tool_hooks.append(hook)

    def register_on_error(self, hook: Callable):
        """🚨 注册异常钩子（OnError 兜底）"""
        self.on_error_hooks.append(hook)

    def run_pre_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """🔧 运行前置钩子（可修改参数或预检）"""
        current_args = dict(args)
        for hook in self.pre_tool_hooks:
            res = hook(tool_name, current_args)
            if isinstance(res, dict):
                current_args = res
        return current_args

    def run_post_tool(self, tool_name: str, args: Dict[str, Any], result: Any) -> Any:
        """🧹 运行后置钩子（可清洗脱敏或加工结果）"""
        current_result = result
        for hook in self.post_tool_hooks:
            current_result = hook(tool_name, args, current_result)
        return current_result

    def run_on_error(self, tool_name: str, args: Dict[str, Any], error: Exception):
        """🚨 运行异常钩子（OnError 审计兜底）"""
        for hook in self.on_error_hooks:
            hook(tool_name, args, error)

# ================= 常用开箱即用 Hooks 实现 =================

def timing_pre_hook(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """⏱️ 耗时统计前置标记"""
    args["_start_time"] = time.time()
    return args

def timing_post_hook(tool_name: str, args: Dict[str, Any], result: Any) -> Any:
    """⏱️ 耗时统计后置输出（追加耗时注释）"""
    start_time = args.pop("_start_time", None)
    if start_time:
        duration_ms = (time.time() - start_time) * 1000
        # 如果是字符串结果，追加耗时注释
        if isinstance(result, str):
            return f"{result}\n⏱️ [耗时统计: {duration_ms:.2f}ms]"
    return result

def sensitive_masking_post_hook(tool_name: str, args: Dict[str, Any], result: Any) -> Any:
    """🔒 敏感信息自动脱敏钩子 (保护 APIKey / 密码)"""
    if not isinstance(result, str):
        return result
    
    # 替换形如 sk-xxxx, glm-xxxx, password=xxx 等
    masked = re.sub(r"(sk-[a-zA-Z0-9]{8})[a-zA-Z0-9]+", r"\1****", result)
    masked = re.sub(r"(glm-[a-zA-Z0-9]{8})[a-zA-Z0-9-]+", r"\1****", masked)
    masked = re.sub(r"(password\s*[:=]\s*)\S+", r"\1******", masked, flags=re.IGNORECASE)
    return masked

def create_default_hook_manager() -> HookManager:
    """🏭 工厂方法：快速创建挂载了标准切面的 Hook 管理器"""
    hm = HookManager()
    hm.register_pre_tool(timing_pre_hook)
    hm.register_post_tool(timing_post_hook)
    hm.register_post_tool(sensitive_masking_post_hook)
    return hm

if __name__ == "__main__":
    hm = create_default_hook_manager()
    
    def fake_fetch_config(service_name: str) -> str:
        time.sleep(0.05)
        return f"配置信息: 服务={service_name}, 密钥=sk-abcdef1234567890xyz, endpoint=glm-20250225123456-abcde"

    print("--- 1. 完整钩子链路自测 (计时 + 脱敏) ---")
    tool = "fake_fetch_config"
    raw_args = {"service_name": "AuthService"}
    processed_args = hm.run_pre_tool(tool, raw_args)
    res = fake_fetch_config(**{k: v for k, v in processed_args.items() if not k.startswith("_")})
    final_output = hm.run_post_tool(tool, processed_args, res)
    print("脱敏与耗时加工后的输出:\n", final_output)

    print("\n--- 2. 敏感信息脱敏边界自测 ---")
    print("password 脱敏:", sensitive_masking_post_hook("t", {}, "连接串 password=mySecret123 已就绪"))
    print("sk-key 脱敏:", sensitive_masking_post_hook("t", {}, "使用 sk-abcdef1234567890xyz 连接"))
    print("非字符串结果不处理:", sensitive_masking_post_hook("t", {}, {"secret": "sk-abcdef1234567890xyz"}))

    print("\n--- 3. OnError 异常钩子自测 ---")
    hm.register_on_error(lambda name, args, err: print(f"   [审计] 工具 [{name}] 抛错: {type(err).__name__}: {err}"))
    try:
        raise ValueError("模拟工具运行时异常")
    except ValueError as e:
        hm.run_on_error("fake_fetch_config", raw_args, e)
