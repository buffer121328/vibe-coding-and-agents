"""
s04_structured_output.py - 结构化输出与容错解析
------------------------------------------------------------------
对应章节：9.4 结构化输出与容错解析
核心功能：
1. 使用 Pydantic 定义强类型数据模型
2. 掌握现代 with_structured_output() 标准接口
3. 使用 JsonOutputParser 与 Prompt 注入机制
4. 解析复杂非结构化文本，提取标准化企业/人物画像
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from rich.console import Console
from rich.panel import Panel
from s01_model_io import get_chat_model_primary

console = Console()

# 1. 定义 Pydantic 数据实体模型
class KeyMetric(BaseModel):
    name: str = Field(description="指标名称，如营收、净利润、MAU")
    value: str = Field(description="指标数值，如 120 亿元、+35%")
    evaluation: str = Field(description="针对该指标的评价：超预期/符合预期/不及预期")

class FinancialReportAnalysis(BaseModel):
    company_name: str = Field(description="企业名称")
    report_period: str = Field(description="财报周期，例如 2025 年 Q3、2024 全年")
    core_summary: str = Field(description="核心结论与摘要，不超过 100 字")
    sentiment_score: int = Field(description="情绪综合评分，区间 0 到 100", ge=0, le=100)
    key_metrics: List[KeyMetric] = Field(description="核心财务与业务指标列表")
    risk_factors: List[str] = Field(description="面临的主要风险清单")
    rating: str = Field(description="投资或综合评级：买入/增持/中性/减持/卖出")

def demo_with_structured_output():
    """演示 1：现代 with_structured_output() 一键结构化"""
    console.print(Panel("[bold cyan]1. 现代 with_structured_output() 强类型提取[/bold cyan]", expand=False))
    
    llm = get_chat_model_primary()
    # 绑定结构化模型
    structured_llm = llm.with_structured_output(FinancialReportAnalysis)
    
    unstructured_text = """
    【TechStar 2025年第三季度财报公布】
    TechStar 智能科技今日公布最新三季度业绩：本季度实现总营业收入 158.6 亿元，同比增长 28.5%，大幅超出市场预期的 140 亿元；
    其中云计算与 AI 业务营收占比达 42%，成为第一大支柱。净利润为 24.1 亿元，同比增长 12%，表现稳健符合预期。
    然而，公司海外业务受到汇率波动和地缘供应链限制，海外增速放缓至 5%；同时研发投入由于大模型训练增加 45%，给短期毛利带来一定压力。
    综合来看，管理层对 AI 全年商业化落地充满信心，券商多数给出'买入'评级。
    """
    
    console.print(f"[bold green]输入非结构化新闻文本：[/bold green]\n{unstructured_text.strip()}\n")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一名资深金融研报分析师，请从给定文本中提取标准财报分析结构。"),
        ("human", "{text}")
    ])
    
    chain = prompt | structured_llm
    
    try:
        result: FinancialReportAnalysis = chain.invoke({"text": unstructured_text})
        console.print("[bold green]✅ 成功提取为 Pydantic 结构化对象：[/bold green]")
        console.print(f"• 企业名称: [bold blue]{result.company_name}[/bold blue]")
        console.print(f"• 财报周期: {result.report_period}")
        console.print(f"• 核心摘要: {result.core_summary}")
        console.print(f"• 情绪得分: [bold yellow]{result.sentiment_score}/100[/bold yellow]")
        console.print(f"• 综合评级: [bold red]{result.rating}[/bold red]")
        console.print("\n• 关键指标明细:")
        for m in result.key_metrics:
            console.print(f"   - {m.name}: {m.value} ({m.evaluation})")
        console.print("\n• 风险清单:")
        for r in result.risk_factors:
            console.print(f"   - {r}")
            
    except Exception as e:
        console.print(f"[red]结构化提取失败：{e}[/red]")

def demo_json_output_parser():
    """演示 2：JsonOutputParser 配合 Prompt 指令生成标准 JSON"""
    console.print(Panel("[bold cyan]2. JsonOutputParser 与 Format Instructions[/bold cyan]", expand=False))
    
    class SimpleUser(BaseModel):
        username: str = Field(description="用户昵称")
        age: int = Field(description="年龄")
        skills: List[str] = Field(description="技能列表")
        
    parser = JsonOutputParser(pydantic_object=SimpleUser)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "提取用户信息并严格输出 JSON 格式。\n{format_instructions}"),
        ("human", "{input_text}")
    ])
    
    llm = get_chat_model_primary()
    chain = prompt | llm | parser
    
    try:
        res = chain.invoke({
            "format_instructions": parser.get_format_instructions(),
            "input_text": "张三今年 28 岁，精通 Python、Docker、Kubernetes 和 LangChain 开发。"
        })
        console.print(f"[bold green]JSON 解析结果字典：[/bold green]{res}")
        console.print(f"[dim]解析类型：{type(res)}[/dim]")
    except Exception as e:
        console.print(f"[red]JSON 解析失败：{e}[/red]")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x 结构化输出与容错解析演示[/bold magenta]\n")
    demo_with_structured_output()
    console.print("-" * 50)
    demo_json_output_parser()
