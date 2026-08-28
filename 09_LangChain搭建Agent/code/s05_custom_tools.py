"""
s05_custom_tools.py - 自定义工具生态与参数校验
------------------------------------------------------------------
对应章节：9.5 自定义工具生态与参数校验
核心功能：
1. 使用 @tool 装饰器快速定义 Python 工具
2. 使用 Pydantic args_schema 进行严格参数校验与约束
3. 掌握 Docstring 作为 AI 意图理解契约（Prompt as Interface）
4. 使用 llm.bind_tools() 进行底层工具绑定与 tool_calls 触发解析
"""

import json
from typing import List, Dict
from pydantic import BaseModel, Field
from langchain_core.tools import tool, StructuredTool
from rich.console import Console
from rich.panel import Panel
from s01_model_io import get_chat_model_primary

console = Console()

# 1. 基础轻量工具定义
@tool
def get_stock_price(ticker: str) -> str:
    """获取指定股票代码的实时市场最新价格与涨跌幅。
    
    Args:
        ticker: 股票代码，例如 'NVDA'、'AAPL'、'600519'
    """
    mock_data = {
        "NVDA": "英伟达 (NVDA) 当前价格: $128.50, 今日涨跌: +3.8%",
        "AAPL": "苹果 (AAPL) 当前价格: $224.30, 今日涨跌: -0.5%",
        "600519": "贵州茅台 (600519) 当前价格: ¥1420.00, 今日涨跌: +1.2%"
    }
    return mock_data.get(ticker.upper(), f"未查询到股票代码 {ticker} 的最新行情数据。")

# 2. 复杂多参数与 Pydantic 校验工具
class LoanCalculatorInput(BaseModel):
    principal: float = Field(description="贷款总本金金额，单位：万元", gt=0)
    years: int = Field(description="贷款年限，例如 10、20、30", ge=1, le=30)
    annual_rate: float = Field(description="年化利率百分比，例如 3.5 代表 3.5%", ge=0.1, le=20.0)

@tool(args_schema=LoanCalculatorInput)
def calculate_equal_monthly_loan(principal: float, years: int, annual_rate: float) -> str:
    """计算等额本息贷款的每月还款额与总利息支出。
    
    用于精准金融测算，禁止大模型自行心算产生幻觉。
    """
    total_months = years * 12
    monthly_rate = (annual_rate / 100) / 12
    principal_yuan = principal * 10000
    
    # 等额本息月供公式: [P * r * (1+r)^n] / [(1+r)^n - 1]
    monthly_payment = (principal_yuan * monthly_rate * ((1 + monthly_rate) ** total_months)) / (
        ((1 + monthly_rate) ** total_months) - 1
    )
    total_repayment = monthly_payment * total_months
    total_interest = total_repayment - principal_yuan
    
    return (
        f"【贷款测算结果】本金: {principal} 万元, 年限: {years} 年, 年利率: {annual_rate}%\n"
        f"• 每月还款额 (等额本息): ¥{monthly_payment:.2f} 元\n"
        f"• 累计还款总额: ¥{total_repayment/10000:.2f} 万元\n"
        f"• 累计支付利息: ¥{total_interest/10000:.2f} 万元"
    )

def demo_inspect_tools():
    """演示 1：探秘工具的底层 JSON Schema 签名"""
    console.print(Panel("[bold cyan]1. 检查 @tool 生成的 JSON Schema 协议[/bold cyan]", expand=False))
    
    console.print(f"[bold green]工具名称：[/bold green]{get_stock_price.name}")
    console.print(f"[bold green]工具描述：[/bold green]{get_stock_price.description}")
    console.print(f"[bold green]参数 Schema：[/bold green]")
    console.print(json.dumps(get_stock_price.args, indent=2, ensure_ascii=False))
    
    console.print("-" * 30)
    console.print(f"[bold green]高级工具 Schema (LoanCalculatorInput)：[/bold green]")
    console.print(json.dumps(calculate_equal_monthly_loan.args, indent=2, ensure_ascii=False))

def demo_model_tool_binding():
    """演示 2：模型绑定工具与 tool_calls 触发"""
    console.print(Panel("[bold cyan]2. llm.bind_tools() 底层机制与工具调用拦截[/bold cyan]", expand=False))
    
    tools = [get_stock_price, calculate_equal_monthly_loan]
    llm = get_chat_model_primary()
    
    # 绑定工具
    llm_with_tools = llm.bind_tools(tools)
    
    query = "请帮我查一下 NVDA 现在的股价，另外如果我想贷 100 万买房，按 30 年 3.2% 利率计算，每个月要还多少钱？"
    console.print(f"[bold green]用户复合提问：[/bold green]{query}\n")
    
    try:
        ai_msg = llm_with_tools.invoke(query)
        console.print(f"[bold blue]模型响应内容 (思考或回答)：[/bold blue]{ai_msg.content}")
        console.print(f"[bold yellow]模型决定调用的工具清单 (tool_calls)：[/bold yellow]")
        
        tool_map = {t.name: t for t in tools}
        
        for tc in ai_msg.tool_calls:
            func_name = tc["name"]
            func_args = tc["args"]
            call_id = tc["id"]
            console.print(f"👉 命中工具: [bold cyan]{func_name}[/bold cyan], 参数: {func_args}")
            
            # 真实执行工具
            target_tool = tool_map.get(func_name)
            if target_tool:
                tool_output = target_tool.invoke(func_args)
                console.print(f"   [dim]工具执行返回：{tool_output}[/dim]")
                
    except Exception as e:
        console.print(f"[red]工具绑定调用报错：{e}[/red]")

def demo_tool_extras():
    """演示 3：工具 extras —— 一份工具定义，多厂商专属参数（1.2 新特性）"""
    console.print(Panel("[bold cyan]3. 工具 extras：厂商专属参数挂载[/bold cyan]", expand=False))

    @tool(extras={
        "openai": {"parallel_tool_calls": False},      # OpenAI：禁用并行工具调用
        "anthropic": {"tool_choice_type": "auto"},     # Anthropic：工具选择策略
    })
    def get_weather(city: str) -> str:
        """查询指定城市天气。

        Args:
            city: 城市名称
        """
        return f"{city}: 晴 22°C"

    console.print("[dim]不同厂商对工具执行方式的配置各不相同，把厂商专属参数挂在 extras 上，切换厂商时无需改动工具本体。[/dim]")
    console.print(f"[bold green]工具名称：[/bold green]{get_weather.name}")
    console.print(f"[bold green]挂载的 extras：[/bold green]")
    console.print(json.dumps(get_weather.extras, indent=2, ensure_ascii=False))
    console.print(f"[dim]工具仍按标准 Schema 绑定给模型：[/dim]{list(get_weather.args.keys())}")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 自定义工具生态与参数校验演示[/bold magenta]\n")
    demo_inspect_tools()
    console.print("-" * 50)
    demo_model_tool_binding()
    console.print("-" * 50)
    demo_tool_extras()
