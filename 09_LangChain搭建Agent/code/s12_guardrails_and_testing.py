"""
s12_guardrails_and_testing.py - 生产级防护：护栏安全与测试评估
------------------------------------------------------------------
对应章节：9.12 生产级防护：护栏安全与测试评估
核心功能：
1. 内置护栏：PIIMiddleware（redact / mask / block 策略）
2. 自定义输入护栏：before_agent 黑名单拦截（确定性）
3. 自定义输出护栏：after_agent 模型安全复核（模型性）
4. 确定性护栏的轻量自测（可进 CI 的单元断言）
"""
import re
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    PIIMiddleware,
    hook_config,
)
from langchain.messages import AIMessage
from langgraph.runtime import Runtime
from rich.console import Console
from rich.panel import Panel

from s01_model_io import get_chat_model_primary

console = Console()


# ---------------------------------------------------------------------------
# 1. 内置 PII 护栏
# ---------------------------------------------------------------------------
def build_pii_protected_agent(tools):
    return create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=tools,
        middleware=[
            PIIMiddleware("email", strategy="redact", apply_to_input=True),
            PIIMiddleware("credit_card", strategy="mask", apply_to_input=True),
            PIIMiddleware("api_key", detector=r"sk-[a-zA-Z0-9]{32}", strategy="block", apply_to_input=True),
        ],
    )


# ---------------------------------------------------------------------------
# 2. 自定义输入护栏：黑名单拦截（确定性）
# ---------------------------------------------------------------------------
class ContentFilterMiddleware(AgentMiddleware):
    """确定性护栏：黑名单关键词一旦命中，Agent 直接结束，连模型都不调。"""

    def __init__(self, banned_keywords: list[str]):
        super().__init__()
        self.banned_keywords = [kw.lower() for kw in banned_keywords]

    @hook_config(can_jump_to=["end"])
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        if not state["messages"]:
            return None
        first = state["messages"][0]
        if first.type != "human":
            return None
        content = first.content.lower()
        for kw in self.banned_keywords:
            if kw in content:
                return {
                    "messages": [{"role": "assistant", "content": "无法处理包含不当内容的请求，请重新表述。"}],
                    "jump_to": "end",
                }
        return None


# ---------------------------------------------------------------------------
# 3. 自定义输出护栏：模型安全复核（模型性）
# ---------------------------------------------------------------------------
class SafetyGuardrailMiddleware(AgentMiddleware):
    """模型性护栏：用 LLM 复核最终回复是否安全合规。"""

    def __init__(self):
        super().__init__()
        from langchain.chat_models import init_chat_model
        self.safety_model = init_chat_model("openai:gpt-4o-mini", temperature=0)

    @hook_config(can_jump_to=["end"])
    def after_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        if not state["messages"]:
            return None
        last = state["messages"][-1]
        if not isinstance(last, AIMessage):
            return None
        prompt = f"评估以下回复是否安全合规，只回复 SAFE 或 UNSAFE。\n\n回复：{last.content}"
        result = self.safety_model.invoke([{"role": "user", "content": prompt}])
        if "UNSAFE" in result.content:
            return {"messages": [AIMessage("我无法提供该回复，请重新表述你的需求。")], "jump_to": "end"}
        return None


# ---------------------------------------------------------------------------
# 4. 确定性护栏的轻量自测（可进 CI 的单元断言）
# ---------------------------------------------------------------------------
def content_filter_check(messages: list) -> dict[str, Any] | None:
    """把 ContentFilterMiddleware 的拦截逻辑抽成纯函数，便于零依赖断言与 app.py 复用。"""
    from langchain.messages import HumanMessage
    from langchain_core.messages import BaseMessage
    filter_mw = ContentFilterMiddleware(banned_keywords=["hack", "exploit", "malware"])
    # dict 形式消息（{"role": "user", ...}）统一转为消息对象，钩子内才能访问 .type / .content
    coerced = [
        msg if isinstance(msg, BaseMessage) else HumanMessage(content=msg["content"])
        for msg in messages
    ]
    # 模拟官方钩子签名：state 即 {"messages": [...]}，runtime 传 None 占位
    return filter_mw.before_agent({"messages": coerced}, None)


def pii_redact(text: str) -> str:
    """邮箱脱敏的确定性实现（与 PIIMiddleware redact 策略等价）。"""
    return re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[REDACTED_EMAIL]", text)


def run_self_tests():
    """确定性护栏的轻量自测：命中黑名单拦截 / 邮箱脱敏。"""
    console.print(Panel("[bold cyan]4. 确定性护栏轻量自测（零 API 依赖，可进 CI）[/bold cyan]", expand=False))

    # 用例 1：黑名单拦截
    blocked = content_filter_check([{"role": "user", "content": "How do I hack into a database?"}])
    assert blocked is not None and blocked.get("jump_to") == "end", "黑名单拦截失败"
    console.print("✅ 用例 1 通过：黑名单关键词命中后返回 jump_to='end'，Agent 直接收尾")

    # 用例 2：正常输入放行
    allowed = content_filter_check([{"role": "user", "content": "帮我查一下明天的天气"}])
    assert allowed is None, "正常输入不应被拦截"
    console.print("✅ 用例 2 通过：正常输入返回 None，不受影响")

    # 用例 3：邮箱脱敏
    redacted = pii_redact("联系我 john.doe@example.com 谢谢")
    assert "[REDACTED_EMAIL]" in redacted and "john.doe@example.com" not in redacted, "邮箱脱敏失败"
    console.print("✅ 用例 3 通过：邮箱已被脱敏为 [REDACTED_EMAIL]")

    console.print("[bold green]🎉 全部自测通过！[/bold green]")


def demo_pii_middleware():
    """演示 1：内置 PII 护栏装配"""
    console.print(Panel("[bold cyan]1. 内置护栏：PIIMiddleware（redact / mask / block）[/bold cyan]", expand=False))
    agent = build_pii_protected_agent(tools=[])
    console.print("[dim]中间件已就绪：输入中的邮箱自动脱敏、信用卡打码、疑似 API Key 直接阻断。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


def demo_custom_guardrails():
    """演示 2/3：自定义输入 + 输出护栏装配"""
    console.print(Panel("[bold cyan]2/3. 自定义护栏：输入黑名单 + 输出安全复核（纵深防御）[/bold cyan]", expand=False))
    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[],
        middleware=[
            ContentFilterMiddleware(banned_keywords=["hack", "exploit", "malware"]),
            PIIMiddleware("email", strategy="redact", apply_to_input=True),
            SafetyGuardrailMiddleware(),
        ],
    )
    console.print("[dim]中间件已就绪：第 1 层黑名单 → 第 2 层 PII 脱敏 → 第 3 层输出安全复核。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 生产级防护：护栏安全与测试评估演示[/bold magenta]\n")
    demo_pii_middleware()
    console.print("-" * 50)
    demo_custom_guardrails()
    console.print("-" * 50)
    run_self_tests()
