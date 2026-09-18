"""
s09_modern_agent.py - LangChain 1.4 Agent 现代架构与智能体闭环
------------------------------------------------------------------
对应章节：9.9 Agent 现代架构与 create_agent
核心功能：
1. 掌握 1.4 标准 Agent 入口 create_agent（替代 0.3 的 AgentExecutor）
2. 装配计算器、汇率转换、天气预报等多模工具
3. 通过 messages 消息流水线审计 Agent 的推理与工具调用链
4. 流式捕获 Agent 的思考与工具调用事件
5. （1.4 时代新增）deepagents 深度智能体 create_deep_agent 演示位
"""

import math
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langchain.agents import create_agent          # 1.4 标准 Agent 工厂
from langchain.agents.middleware import ModelRetryMiddleware   # 1.1+ 官方预置中间件
from rich.console import Console
from rich.panel import Panel
from s01_model_io import get_chat_model_primary

console = Console()

# 1. 定义 Agent 可调用的工具库（create_agent 也接受普通 Python 函数）
@tool
def calculate_expression(expression: str) -> str:
    """数学表达式求值计算器。支持加减乘除、乘方、三角函数、对数等精确运算。

    Args:
        expression: 数学表达式字符串，如 '125 * 38.5 / (1 + 0.05)**3'
    """
    try:
        # 安全受限环境计算
        allowed_names = {
            k: v for k, v in math.__dict__.items() if not k.startswith("__")
        }
        allowed_names.update({"abs": abs, "round": round, "min": min, "max": max})
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return f"计算结果: {result}"
    except Exception as e:
        return f"表达式求值错误: {e}"

@tool
def query_weather(city: str) -> str:
    """查询城市天气。注意：本工具返回的是教学用模拟数据，并非真实气象台数据，
    且仅支持 北京、上海、深圳、杭州 四个演示城市。用户询问其他城市时，
    请如实告知"天气为模拟数据，仅支持这四个城市"，绝不要编造其他城市的天气。

    Args:
        city: 城市名称，仅支持 '北京'、'上海'、'深圳'、'杭州'
    """
    mock_weather_db = {
        "北京": "北京今天多云转晴，气温 18°C ~ 28°C，西南风 2 级，空气质量优，适合户外活动。",
        "上海": "上海今天小雨，气温 22°C ~ 26°C，湿度 85%，建议出门带伞。",
        "深圳": "深圳今天晴天，气温 26°C ~ 33°C，紫外线强烈，注意防晒补水。",
        "杭州": "杭州今天微风习习，气温 20°C ~ 29°C，西湖风景宜人。"
    }
    if city not in mock_weather_db:
        return (f"⚠️ 查询失败：本工具是教学演示用的模拟天气数据，仅支持 北京 / 上海 / 深圳 / 杭州 "
                f"四个城市，暂未收录 '{city}'（无真实气象数据）。请如实告知用户这一限制，"
                f"并建议改查这四个城市之一，不要编造 '{city}' 的天气。")
    return f"【模拟数据】{mock_weather_db[city]}"

@tool
def currency_converter(amount: float, from_currency: str, to_currency: str) -> str:
    """实时外汇汇率换算工具。

    Args:
        amount: 金额数量
        from_currency: 原始货币代码，如 'USD'、'CNY'、'EUR'、'JPY'
        to_currency: 目标货币代码，如 'CNY'、'USD'
    """
    rates_to_cny = {
        "USD": 7.25,
        "EUR": 7.85,
        "JPY": 0.048,
        "CNY": 1.0
    }
    from_curr = from_currency.upper()
    to_curr = to_currency.upper()

    if from_curr not in rates_to_cny or to_curr not in rates_to_cny:
        return f"不支持的货币转换：{from_curr} ➔ {to_curr}"

    # 转换为 CNY 中介，再转为目标货币
    amount_in_cny = amount * rates_to_cny[from_curr]
    target_amount = amount_in_cny / rates_to_cny[to_curr]

    return f"{amount} {from_curr} = {target_amount:.2f} {to_curr} (参考汇率 1 {from_curr} = {rates_to_cny[from_curr]} CNY)"

def build_modern_agent():
    """构建 1.4 标准 Tool Calling Agent（无需 AgentExecutor / agent_scratchpad）"""
    tools = [calculate_expression, query_weather, currency_converter]
    llm = get_chat_model_primary(temperature=0.2)

    # 1.1+：system_prompt 除了字符串，还可直接传 SystemMessage 实例（更利于程序化组合）
    system_prompt = SystemMessage(
        content="""你是一位精通多领域的超级智能私人助理。
你有权调用外部工具来获取数据。遇到任何涉及数学算术、天气、汇率计算的问题时，请严格调用对应的工具，绝不自行盲猜！
特别提醒：query_weather 返回的是教学用模拟数据（仅覆盖北京/上海/深圳/杭州四个城市），并非真实气象数据。
向用户汇报天气时必须注明"模拟数据"；若用户查询其他城市，要如实说明工具只支持这四个模拟城市，绝不要编造其他城市的天气。
汇率工具返回的也是教学用参考汇率，汇报时请注明"参考汇率"。
在完成所有必要工具调用后，请用清晰礼貌的语言给用户汇总最终答案。"""
    )

    # 1.1+：官方预置 ModelRetryMiddleware —— 模型调用失败自动重试（弱网 / 429 / 瞬时 5xx）
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[ModelRetryMiddleware(max_retries=2)],
    )
    return agent

def demo_agent_execution():
    """演示智能体自主多步推理与工具链调用"""
    console.print(Panel("[bold cyan]1. 运行 1.4 标准 create_agent[/bold cyan]", expand=False))

    agent = build_modern_agent()

    complex_query = (
        "我打算明天去上海旅游 3 天，请帮我查一下上海的天气。"
        "另外我想预定一家每晚 180 美元的酒店，住 3 晚总共需要多少人民币？"
    )

    console.print(f"[bold green]用户复合指令：[/bold green]\n{complex_query}\n")

    try:
        response = agent.invoke({"messages": [("user", complex_query)]})

        console.print("\n" + "=" * 50)
        console.print("[bold magenta]🔍 Agent 推理与行动过程审计 (messages 流水线)：[/bold magenta]")
        for msg in response["messages"]:
            if msg.type == "ai" and msg.tool_calls:
                for tc in msg.tool_calls:
                    console.print(f"🧠 思考：调用工具 [bold cyan]{tc['name']}[/bold cyan]，参数 {tc['args']}")
            elif msg.type == "tool":
                console.print(f"⚙️ 工具返回: [dim]{msg.content}[/dim]")
            elif msg.type == "ai":
                console.print(f"💬 AI: {msg.content}")

        console.print("\n" + "=" * 50)
        console.print(f"[bold blue]🎉 最终汇总答复：[/bold blue]\n{response['messages'][-1].content}")

    except Exception as e:
        console.print(f"[red]Agent 运行报错：{e}[/red]")

class FinalAnswer(BaseModel):
    """强制结构化最终答复的 Pydantic Schema（1.1+ 的 response_format 用法）"""
    summary: str = Field(description="对用户问题的最终中文总结")
    key_points: list[str] = Field(description="3~5 条关键要点")
    used_tools: list[str] = Field(description="本次调用过的工具名列表")

def demo_structured_response():
    """演示 2：response_format —— 整个 Agent 的最终答复强制符合 Pydantic Schema"""
    console.print(Panel("[bold cyan]2. response_format 强制结构化最终答复[/bold cyan]", expand=False))

    agent = create_agent(
        model=get_chat_model_primary(temperature=0.2),
        tools=[calculate_expression],
        system_prompt="你是严谨可靠的数学助理。",
        response_format=FinalAnswer,   # 1.1+：对话结束的最终答复自动强转为该 Schema
    )

    console.print("[dim]场景：对话结束后自动生成标准报表/单据（而非单次 LLM 调用）[/dim]")
    try:
        res = agent.invoke({"messages": [("user", "请帮我算一下 125 乘以 38.5 再除以 1.05 的平方的结果")]})
        final_msg = res["messages"][-1]
        console.print("[bold green]✅ Agent 最终答复（已符合 FinalAnswer Schema）：[/bold green]")
        console.print(final_msg.content)
        console.print(f"[dim]工具调用链：[bold]{[tc['name'] for m in res['messages'] if getattr(m, 'tool_calls', None) for tc in m.tool_calls]}[/bold][/dim]")
    except Exception as e:
        console.print(f"[red]结构化答复失败（可能未配置可用 API Key）：{e}[/red]")

def demo_stream_v3():
    """演示 3：1.3 新一代 v3 流式协议 —— 更细粒度的 Agent 级事件流"""
    console.print(Panel("[bold cyan]3. v3 流式协议 astream_events(version='v3')[/bold cyan]", expand=False))

    import asyncio

    async def run():
        agent = build_modern_agent()
        # 注意：CompiledStateGraph 的 astream_events 返回协程，需先 await 拿到异步迭代器
        async for event in await agent.astream_events(
            {"messages": [("user", "用一句话介绍上海天气查询的结果。")]},
            version="v3",
        ):
            kind = event.get("event", "")
            if "on_chat_model_stream" in kind:
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None and getattr(chunk, "content", None):
                    print(chunk.content, end="", flush=True)
            elif kind in ("on_agent_start", "on_agent_end"):
                console.print(f"\n[dim]Agent 事件：{kind}[/dim]")

    try:
        asyncio.run(run())
        print()
    except Exception as e:
        console.print(f"[red]v3 流式演示失败（可能未配置可用 API Key）：{e}[/red]")

def demo_deep_agent():
    """演示 4（1.4 时代新增）：deepagents 深度智能体 —— create_agent 的"整车厂"版

    deepagents 在同一套 AgentMiddleware 体系上预装了：
    虚拟文件系统（ls/read_file/write_file/edit_file/glob/grep）+ 任务规划（write_todos）
    + 子代理委派（task）+ 长期记忆（MemoryMiddleware）+ 技能库（SkillsMiddleware）。
    这里用默认 StateBackend（文件存于 LangGraph 状态，零副作用）做安全演示。
    未安装 deepagents 时自动跳过，不影响其余演示。
    """
    console.print(Panel("[bold cyan]4. deepagents 深度智能体 create_deep_agent（9.9 新增）[/bold cyan]", expand=False))
    try:
        from deepagents import create_deep_agent
    except ImportError:
        console.print("[yellow]⚠️ 未安装 deepagents（pip install deepagents），本演示跳过。[/yellow]")
        return

    agent = create_deep_agent(
        model=get_chat_model_primary(),
        tools=[query_weather],                     # 你的领域工具
        system_prompt="你是深度研究员，先规划任务，再逐步执行并把结果写入虚拟文件系统。",
    )
    try:
        res = agent.invoke(
            {"messages": [("user", "查询北京和上海的天气，把对比结论写入 /report/weather.md")]},
            config={"recursion_limit": 40},        # 深度任务步数更多，放宽递归上限
        )
        final = res["messages"][-1]
        console.print("[bold green]✅ 深度智能体最终答复：[/bold green]")
        console.print(getattr(final, "content", final))
        files = res.get("files") or {}
        if isinstance(files, dict):
            console.print(f"[dim]虚拟文件系统现存文件：{list(files.keys())}[/dim]")
    except Exception as e:
        console.print(f"[red]deepagents 演示失败（可能未配置可用 API Key）：{e}[/red]")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.4 Agent 现代架构与智能体闭环演示[/bold magenta]\n")
    demo_agent_execution()
    console.print("-" * 50)
    demo_structured_response()
    console.print("-" * 50)
    demo_stream_v3()
    console.print("-" * 50)
    demo_deep_agent()
