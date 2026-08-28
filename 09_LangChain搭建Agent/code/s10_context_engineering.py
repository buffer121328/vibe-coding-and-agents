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
    """演示 1：动态 System Prompt"""
    console.print(Panel("[bold cyan]1. 动态 System Prompt（@dynamic_prompt）[/bold cyan]", expand=False))
    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[],
        middleware=[state_aware_prompt],
    )
    console.print("[dim]中间件已就绪：消息超过 10 条时会自动追加“请简洁回答”。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


def demo_dynamic_tools():
    """演示 2：动态工具选择"""
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
        model=get_chat_model_primary(temperature=0.2),
        tools=[public_search, private_search],
        middleware=[state_based_tools],
    )
    console.print("[dim]中间件已就绪：未认证（authenticated=False）时只开放 public_search。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


def demo_store_injection():
    """演示 3：长期画像注入（Store + Runtime Context）"""
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
    console.print("[dim]中间件已就绪：每次调用都会读取 user-123 的偏好并注入系统提示。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 上下文工程与动态上下文注入演示[/bold magenta]\n")
    demo_dynamic_prompt()
    console.print("-" * 50)
    demo_dynamic_tools()
    console.print("-" * 50)
    demo_store_injection()
