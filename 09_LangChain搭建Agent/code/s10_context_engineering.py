"""
s10_context_engineering.py - 上下文工程与动态上下文注入
------------------------------------------------------------------
对应章节：9.10 上下文工程 Context Engineering
核心功能：
1. 动态 System Prompt：按会话长度自适应（@dynamic_prompt）
2. 动态工具选择：按认证状态/会话阶段裁剪工具（wrap_model_call + request.override）
3. 长期画像注入：Store + Runtime Context 双剑合璧（context_schema + store）
"""
from dataclasses import dataclass
from typing import Callable

from langchain.agents import create_agent
from langchain.agents.middleware import (
    dynamic_prompt,
    wrap_model_call,
    ModelRequest,
    ModelResponse,
)
from langchain.messages import HumanMessage
from langgraph.store.memory import InMemoryStore
from rich.console import Console
from rich.panel import Panel

from s01_model_io import get_chat_model_primary

console = Console()

# ---------------------------------------------------------------------------
# 1. 动态 System Prompt：按会话长度自适应
# ---------------------------------------------------------------------------
@dynamic_prompt
def state_aware_prompt(request: ModelRequest) -> str:
    """每次模型调用前动态生成系统提示。request.messages = request.state["messages"]。"""
    message_count = len(request.messages)
    base = "你是一位贴心助手。"
    if message_count > 10:
        base += "\n这是一段很长的对话，请尽量简洁回答。"
    return base


# ---------------------------------------------------------------------------
# 2. 动态工具选择：按认证状态裁剪可用工具
# ---------------------------------------------------------------------------
@wrap_model_call
def state_based_tools(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    """未认证时只开放 public_ 前缀的安全工具；已认证才放行敏感工具。"""
    state = request.state
    is_authenticated = state.get("authenticated", False)
    if not is_authenticated:
        request = request.override(
            tools=[t for t in request.tools if t.name.startswith("public_")]
        )
    return handler(request)


# ---------------------------------------------------------------------------
# 3. 长期画像注入：Store + Runtime Context
# ---------------------------------------------------------------------------
@dataclass
class Context:
    """运行期静态配置：会话级、固定不变的上下文。"""
    user_id: str


@dynamic_prompt
def store_aware_prompt(request: ModelRequest) -> str:
    """读 Runtime Context 拿 user_id，读 Store 拿用户偏好，动态改写系统提示。"""
    user_id = request.runtime.context.user_id
    prefs = request.runtime.store.get(("preferences",), user_id)
    base = "你是一位贴心助手。"
    if prefs:
        style = prefs.value.get("communication_style", "balanced")
        base += f"\n用户偏好 {style} 风格的回复。"
    return base


def demo_dynamic_prompt():
    """演示 1：动态 System Prompt —— 短对话 vs 长对话，动态注入不同指令后真实调用"""
    console.print(Panel("[bold cyan]1. 动态 System Prompt（@dynamic_prompt）[/bold cyan]", expand=False))
    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[],
        middleware=[state_aware_prompt],
    )

    short_msgs = [HumanMessage(content="只回复两个字：收到")]
    long_msgs = ([HumanMessage(content=f"历史占位消息 {i}，请忽略本条内容。") for i in range(12)]
                 + [HumanMessage(content="用一句话介绍 LangChain。")])
    console.print(f"[dim]场景 A：短对话（{len(short_msgs)} 条消息）→ @dynamic_prompt 生成的人设不含「简洁」指令[/dim]")
    res_a = agent.invoke({"messages": short_msgs})
    console.print(f"[green]模型回复 A：{res_a['messages'][-1].content[:60]}[/green]")

    console.print(f"[dim]场景 B：长对话（{len(long_msgs)} 条消息）→ 消息数 > 10，人设自动追加「请简洁回答」[/dim]")
    res_b = agent.invoke({"messages": long_msgs})
    console.print(f"[green]模型回复 B：{res_b['messages'][-1].content[:80]}[/green]")
    console.print("[dim]同一份中间件，两次调用注入的 System Prompt 不同——上下文在每次模型调用前动态组装。[/dim]")


def demo_dynamic_tools():
    """演示 2：动态工具选择 —— 未认证只开放 public_ 工具，真实调用验证 tool_calls"""
    console.print(Panel("[bold cyan]2. 动态工具选择（wrap_model_call + override）[/bold cyan]", expand=False))

    from langchain_core.tools import tool

    @tool
    def public_search(query: str) -> str:
        """公开搜索工具。"""
        return f"公开搜索结果：{query}"

    @tool
    def private_search(query: str) -> str:
        """私有搜索工具（需认证）。"""
        return f"私有搜索结果：{query}"

    agent = create_agent(
        model=get_chat_model_primary(temperature=0),
        tools=[public_search, private_search],
        middleware=[state_based_tools],
    )

    console.print("[dim]场景 A：authenticated=False → 模型只看得到 public_search（private_search 被裁掉）[/dim]")
    res_a = agent.invoke({
        "messages": [HumanMessage(content="请调用搜索工具查询 '季度营收'，必须调用一个搜索工具。")],
        "authenticated": False,
    })
    for m in res_a["messages"]:
        for tc in (getattr(m, "tool_calls", None) or []):
            console.print(f"[green]模型 tool_calls：{tc['name']}({tc['args']})[/green]")
    names_a = [tc["name"] for m in res_a["messages"] for tc in (getattr(m, "tool_calls", None) or [])]
    console.print(f"[green]实际被调用的工具：{names_a or '（无）'} → 只可能是 public_search ✓[/green]")

    console.print("[dim]场景 B：authenticated=True → 敏感工具放行（模型可见 2 个工具）[/dim]")
    res_b = agent.invoke({
        "messages": [HumanMessage(content="请调用私有搜索工具查询 '核心客户名单'。")],
        "authenticated": True,
    })
    names_b = [tc["name"] for m in res_b["messages"] for tc in (getattr(m, "tool_calls", None) or [])]
    console.print(f"[green]实际被调用的工具：{names_b or '（模型直接回答，但 private_search 已可见）'}[/green]")
    console.print("[dim]工具清单不是写死的：中间件在每次模型调用前按状态动态裁剪/放行。[/dim]")


def demo_store_injection():
    """演示 3：长期画像注入 —— Store 里的偏好被拼进 System Prompt，真实调用验证说话风格"""
    console.print(Panel("[bold cyan]3. 长期画像注入（context_schema + store）[/bold cyan]", expand=False))

    store = InMemoryStore()
    store.put(("preferences",), "user-123", {"communication_style": "简洁直接"})

    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[],
        middleware=[store_aware_prompt],
        context_schema=Context,   # 声明运行期上下文的 Schema
        store=store,              # 挂载长期记忆 Store
    )

    console.print("[dim]场景 A：老用户 user-123（Store 画像：简洁直接风格）[/dim]")
    res_a = agent.invoke(
        {"messages": [HumanMessage(content="介绍一下什么是向量数据库。")]},
        context=Context(user_id="user-123"),
    )
    console.print(f"[green]老用户得到的回复：{res_a['messages'][-1].content[:90]}[/green]")

    console.print("[dim]场景 B：新用户 user-new（Store 无画像 → 通用风格）[/dim]")
    res_b = agent.invoke(
        {"messages": [HumanMessage(content="介绍一下什么是向量数据库。")]},
        context=Context(user_id="user-new"),
    )
    console.print(f"[green]新用户得到的回复：{res_b['messages'][-1].content[:90]}[/green]")
    console.print("[dim]Runtime Context 定位「是谁」，Store 决定「记得什么」——画像每轮动态注入人设。[/dim]")


if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 上下文工程与动态上下文注入演示[/bold magenta]\n")
    demo_dynamic_prompt()
    console.print("-" * 50)
    demo_dynamic_tools()
    console.print("-" * 50)
    demo_store_injection()
