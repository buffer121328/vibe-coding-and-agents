"""
s11_custom_middleware.py - 自定义中间件与生命周期钩子
------------------------------------------------------------------
对应章节：9.11 自定义中间件与生命周期钩子
核心功能：
1. Node-style 钩子：before_model 消息上限熔断 + after_model 日志
2. Wrap-style 钩子：wrap_model_call 自动重试
3. 类式中间件：AgentMiddleware 子类（同步 + 异步双实现）
4. 自定义状态 Schema：state_schema 让中间件拥有“记忆”（调用次数限流）
"""
from typing import Any, Callable

from langchain.agents import create_agent
from langchain.agents.middleware import (
    before_model,
    after_model,
    wrap_model_call,
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain.messages import AIMessage
from langgraph.runtime import Runtime
from typing_extensions import NotRequired
from rich.console import Console
from rich.panel import Panel

from s01_model_io import get_chat_model_primary

console = Console()


# ---------------------------------------------------------------------------
# 1. Node-style：消息上限熔断 + 响应日志（装饰器式）
# ---------------------------------------------------------------------------
@before_model(can_jump_to=["end"])            # 声明本钩子有权“跳到 end”提前结束
def check_message_limit(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    if len(state["messages"]) >= 50:
        return {                                # 返回 dict 即持久更新状态 + 跳转
            "messages": [AIMessage("对话已达上限，请开启新会话。")],
            "jump_to": "end",
        }
    return None                                 # 返回 None 表示不干预


@after_model
def log_response(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    console.print(f"[dim]📝 模型返回：{state['messages'][-1].content}[/dim]")
    return None


# ---------------------------------------------------------------------------
# 2. Wrap-style：模型调用自动重试
# ---------------------------------------------------------------------------
@wrap_model_call
def retry_model(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    for attempt in range(3):
        try:
            return handler(request)
        except Exception as e:
            if attempt == 2:
                raise
            console.print(f"[yellow]🔁 第 {attempt + 1}/3 次重试，错误：{e}[/yellow]")


# ---------------------------------------------------------------------------
# 3. 类式中间件：同步 + 异步双实现
# ---------------------------------------------------------------------------
class LoggingMiddleware(AgentMiddleware):
    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        console.print(f"[dim]🔍 即将调用模型，当前消息数：{len(state['messages'])}[/dim]")
        return None

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        console.print(f"[dim]✅ 模型返回：{state['messages'][-1].content}[/dim]")
        return None

    # 异步版本（astream 场景自动走这里）
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self.before_model(state, runtime)


# ---------------------------------------------------------------------------
# 4. 自定义状态 Schema：调用次数限流（防止费用失控）
# ---------------------------------------------------------------------------
class CounterState(AgentState):
    model_call_count: NotRequired[int]


class CallCounterMiddleware(AgentMiddleware):
    state_schema = CounterState                 # 挂载自定义状态

    def before_model(self, state: CounterState, runtime) -> dict[str, Any] | None:
        if state.get("model_call_count", 0) > 10:
            return {"jump_to": "end"}           # 超限直接收尾
        return None

    def after_model(self, state: CounterState, runtime) -> dict[str, Any] | None:
        return {"model_call_count": state.get("model_call_count", 0) + 1}


def demo_node_style():
    """演示 1：Node-style 装饰器钩子"""
    console.print(Panel("[bold cyan]1. Node-style 钩子（@before_model / @after_model）[/bold cyan]", expand=False))
    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[],
        middleware=[check_message_limit, log_response],
    )
    console.print("[dim]中间件已就绪：50 条消息上限熔断 + 响应日志。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


def demo_wrap_style():
    """演示 2：Wrap-style 自动重试"""
    console.print(Panel("[bold cyan]2. Wrap-style 钩子（@wrap_model_call 重试）[/bold cyan]", expand=False))
    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[],
        middleware=[retry_model],
    )
    console.print("[dim]中间件已就绪：模型调用失败自动重试 3 次。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


def demo_class_middleware():
    """演示 3：类式中间件 + 自定义状态 Schema"""
    console.print(Panel("[bold cyan]3. 类式中间件 + 自定义状态 Schema（调用次数限流）[/bold cyan]", expand=False))
    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[],
        middleware=[LoggingMiddleware(), CallCounterMiddleware()],
    )
    console.print("[dim]中间件已就绪：日志 + 超过 10 次模型调用自动收尾。[/dim]")
    console.print("[yellow]（真实调用需配置 .env，此处仅展示装配方式）[/yellow]")


if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 自定义中间件与生命周期钩子演示[/bold magenta]\n")
    demo_node_style()
    console.print("-" * 50)
    demo_wrap_style()
    console.print("-" * 50)
    demo_class_middleware()
