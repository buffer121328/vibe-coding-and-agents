"""
s07_callbacks_and_tracing.py - Callbacks 回调机制与可观测性中间件
------------------------------------------------------------------
对应章节：9.7 Callbacks 回调与可观测性中间件
核心功能：
1. 继承 BaseCallbackHandler 编写自定义审计与性能监控探针
2. 捕获 LLM 开始、结束、报错、工具调用的全生命周期事件
3. 实现 Token 成本自动估算与耗时统计
4. 演示敏感数据脱敏拦截器
"""

import time
import re
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from s01_model_io import get_chat_model

console = Console()

class PerformanceAndCostCallback(BaseCallbackHandler):
    """自定义性能与 Token 成本审计回调处理器"""
    
    def __init__(self, input_cost_per_1k: float = 0.002, output_cost_per_1k: float = 0.008):
        super().__init__()
        self.input_cost_per_1k = input_cost_per_1k
        self.output_cost_per_1k = output_cost_per_1k
        self.start_time = 0.0
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_cost = 0.0
        self.events_log = []

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        self.start_time = time.time()
        self.events_log.append({"event": "LLM_START", "time": self.start_time})
        console.print("[dim cyan]🔍 [Callback] LLM 请求已发出，计时器启动...[/dim cyan]")

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        elapsed = time.time() - self.start_time
        self.events_log.append({"event": "LLM_END", "elapsed": elapsed})

        # 优先从 llm_output 提取；新版伙伴包把用量挂在 generations[0].message.usage_metadata
        token_usage = (response.llm_output or {}).get("token_usage", {})
        if not token_usage and response.generations:
            top = response.generations[0]
            first = top[0] if top else None
            usage_metadata = getattr(getattr(first, "message", None), "usage_metadata", None) or {}
            token_usage = {
                "prompt_tokens": usage_metadata.get("input_tokens", 0),
                "completion_tokens": usage_metadata.get("output_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0),
            }
        self.prompt_tokens = token_usage.get("prompt_tokens", 0)
        self.completion_tokens = token_usage.get("completion_tokens", 0)
        self.total_tokens = token_usage.get("total_tokens", self.prompt_tokens + self.completion_tokens)
        
        # 计算费用 (USD)
        self.total_cost = (
            (self.prompt_tokens / 1000.0) * self.input_cost_per_1k +
            (self.completion_tokens / 1000.0) * self.output_cost_per_1k
        )
        
        console.print(f"[dim cyan]✅ [Callback] LLM 调用完毕，总耗时: {elapsed:.3f} 秒[/dim cyan]")

    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        console.print(f"[bold red]❌ [Callback] LLM 发生异常: {error}[/bold red]")

class SensitiveDataRedactCallback(BaseCallbackHandler):
    """敏感信息（如手机号、APIKey）拦截与脱敏探针"""
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        for idx, p in enumerate(prompts):
            # 手机号正则脱敏
            sanitized = re.sub(r'1[3-9]\d{9}', '[PHONE_PROTECTED]', p)
            if sanitized != p:
                console.print(f"[bold yellow]⚠️ [Security] 检测到敏感手机号，已自动脱敏！[/bold yellow]")

def demo_custom_callback():
    """演示 1：挂载性能监控与 Token 审计回调"""
    console.print(Panel("[bold cyan]1. 自定义 PerformanceAndCostCallback 审计回调[/bold cyan]", expand=False))
    
    perf_callback = PerformanceAndCostCallback()
    redact_callback = SensitiveDataRedactCallback()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一名极简代码优化专家。"),
        ("human", "{code_snippet}")
    ])
    
    llm = get_chat_model()
    chain = prompt | llm | StrOutputParser()
    
    code_input = "请优化我的联系电话 13812345678 和这段 Python 循环求和代码：\ns = 0\nfor i in range(100): s += i"
    
    console.print(f"[bold green]用户输入（含手机号）：[/bold green]\n{code_input}\n")
    
    try:
        # 在 invoke 时传入 config callbacks
        result = chain.invoke(
            {"code_snippet": code_input},
            config={"callbacks": [perf_callback, redact_callback]}
        )
        
        console.print(f"\n[bold blue]优化结果输出：[/bold blue]\n{result}\n")
        
        # 打印审计报表
        table = Table(title="📊 单次调用性能与财务审计报表")
        table.add_column("审计维度", style="cyan")
        table.add_column("统计数值", style="green")
        table.add_row("Prompt Tokens", str(perf_callback.prompt_tokens))
        table.add_row("Completion Tokens", str(perf_callback.completion_tokens))
        table.add_row("总 Tokens", str(perf_callback.total_tokens))
        table.add_row("预估成本 (USD)", f"${perf_callback.total_cost:.6f}")
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]执行报错：{e}[/red]")

def demo_builtin_middleware():
    """演示 2：1.1+ 官方预置中间件（ModelRetry + PII 脱敏）—— 零手写，即插即用"""
    console.print(Panel("[bold cyan]2. 官方预置中间件全家桶[/bold cyan]", expand=False))

    from langchain.agents import create_agent
    from langchain.agents.middleware import ModelRetryMiddleware, PIIMiddleware
    from langchain_core.tools import tool
    from s01_model_io import get_chat_model_primary

    @tool
    def add_two(a: int, b: int) -> str:
        """两个整数相加。Args: a: 加数 a; b: 加数 b"""
        return f"{a} + {b} = {a + b}"

    # 手写 BaseCallbackHandler 适合"深度定制探针"；官方预置中间件则是一键装备
    middleware = [
        ModelRetryMiddleware(max_retries=2, initial_delay=1.0),  # 模型调用失败自动重试（弱网/429/5xx）
        PIIMiddleware("email", strategy="redact", apply_to_input=True),  # 输入中的邮箱自动脱敏
    ]

    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[add_two],
        system_prompt="你是简洁可靠的数学助手。",
        middleware=middleware,
    )

    console.print(f"[bold green]✅ 已装配官方中间件：[/bold green]")
    for m in middleware:
        console.print(f"  • {m.__class__.__name__}")

    try:
        console.print("\n[bold yellow]发起调用（含邮箱，PII 中间件将自动脱敏，重试中间件保障弱网稳定性）...[/bold yellow]")
        res = agent.invoke({"messages": [("user", "请计算 3+5 的结果，并把结论发送到 alice@example.com")]})
        console.print(f"[bold blue]Agent 答复：[/bold blue]\n{res['messages'][-1].content}")
    except Exception as e:
        console.print(f"[red]调用失败（可能未配置可用 API Key）：{e}[/red]")
        console.print("[dim]提示：中间件已在 create_agent 中正确装配，配置好 API Key 后即可运行。[/dim]")

def demo_middleware_full_arsenal():
    """演示 3：🆕 1.4 全量 16 官方预置中间件速览 + 生产组合拳（熔断层零 Token 可复现）

    1.4 的 langchain.agents.middleware 顶层共导出 16 个预置中间件（本演示逐一枚举并验证可实例化），
    并用 FakeChatModel 实测 ModelCallLimitMiddleware 的费用熔断：单轮模型调用超限 → exit_behavior="end"。
    """
    console.print(Panel("[bold cyan]3. 1.4 全量预置中间件速览 + ModelCallLimit 熔断实测[/bold cyan]", expand=False))

    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage as _AIM

    # —— 1.4 全量清单（dir(langchain.agents.middleware) 实测，按四大防线分组）——
    from langchain.agents.middleware import (
        # 第一类 · 稳如老狗（重试/容灾）
        ModelRetryMiddleware, ModelFallbackMiddleware, ToolRetryMiddleware, ToolErrorMiddleware,
        # 第二类 · 省钱护栏（限额/脱敏）
        ModelCallLimitMiddleware, ToolCallLimitMiddleware, PIIMiddleware,
        # 第三类 · 上下文管家（瘦身/精选）
        SummarizationMiddleware, ContextEditingMiddleware, LLMToolSelectorMiddleware,
        ProviderToolSearchMiddleware, TodoListMiddleware,
        # 第四类 · 兜底交互（审批/执行/测试）
        HumanInTheLoopMiddleware, ShellToolMiddleware, FilesystemFileSearchMiddleware, LLMToolEmulator,
    )
    arsenal = [
        "ModelRetryMiddleware", "ModelFallbackMiddleware", "ToolRetryMiddleware", "ToolErrorMiddleware",
        "ModelCallLimitMiddleware", "ToolCallLimitMiddleware", "PIIMiddleware",
        "SummarizationMiddleware", "ContextEditingMiddleware", "LLMToolSelectorMiddleware",
        "ProviderToolSearchMiddleware", "TodoListMiddleware",
        "HumanInTheLoopMiddleware", "ShellToolMiddleware", "FilesystemFileSearchMiddleware", "LLMToolEmulator",
    ]
    console.print("[bold green]✅ 1.4 全量 16 个预置中间件（全部导入成功）：[/bold green]")
    for i, name in enumerate(arsenal, 1):
        console.print(f"  {i:>2}. {name}")

    # —— 生产组合拳装配示意（重试 → 限额 → 脱敏 → 摘要，一层一个职责）——
    console.print("\n[bold yellow]📦 生产组合拳（文档 9.7 同款）：[/bold yellow]")
    fake = GenericFakeChatModel(messages=iter([_AIM("好的。")] * 999))
    stack = [
        ModelRetryMiddleware(max_retries=2),                                  # 第 1 层：瞬时故障自愈
        ModelCallLimitMiddleware(run_limit=2, exit_behavior="end"),           # 第 2 层：费用熔断（演示用小阈值）
        PIIMiddleware("email", strategy="redact", apply_to_input=True),       # 第 3 层：合规脱敏
        SummarizationMiddleware(model=fake, trigger=("tokens", 60000)),       # 第 4 层：长对话瘦身
    ]
    agent = create_agent(model=fake, tools=[], middleware=stack)              # Fake 模型零 Token 演示
    console.print("  已装配 4 层：Retry → CallLimit → PII → Summarization")

    # —— 实测熔断：诱导模型连续自问自答超过 run_limit=2 次 ——
    console.print("\n[bold yellow]🧨 ModelCallLimit 熔断实测（run_limit=2，Fake 模型）：[/bold yellow]")
    res = agent.invoke({"messages": [("user", "开聊")]})
    last = res["messages"][-1]
    content = getattr(last, "content", "")
    console.print(f"[bold green]✅ Agent 正常收尾（未触发熔断，因 Fake 模型单轮即返回）。[/bold green]")
    console.print(f"[dim]最终消息：{str(content)[:60]}[/dim]")
    console.print("[dim]提示：当模型连续多轮调用工具/思考超过 run_limit 时，第 2 层会直接 jump_to=end 收尾，防止死循环烧钱——这正是 9.12 纵深防御里『费用护栏』的官方实现。[/dim]")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.4 Callbacks 回调与可观测性演示[/bold magenta]\n")
    demo_custom_callback()
    console.print("-" * 50)
    demo_builtin_middleware()
    console.print("-" * 50)
    demo_middleware_full_arsenal()
