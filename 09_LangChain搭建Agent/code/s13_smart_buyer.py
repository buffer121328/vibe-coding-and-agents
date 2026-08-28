"""
s13_smart_buyer.py - 综合实战：SmartBuyer AI 智能数码选购与避坑决策参谋（全链路融会贯通版）
------------------------------------------------------------------
对应章节：9.13 综合实战：AI 智能数码选购与避坑决策 Agent

本脚本是第九章的"整机交付"：把 9.1~9.12 装进工具箱的全部零件一次装配到位——
1. 【9.1】统一模型工厂 get_chat_model_primary（一键换模型，业务代码零改动）
2. 【9.4】Pydantic 强类型《数码选购决策与避坑报告》（with_structured_output）
3. 【9.5】@tool 自定义工具生态：差评搜索 / 性价比测算 / 避坑宝典检索
4. 【9.6】LangGraph Checkpointer 线程级会话记忆（thread_id 隔离多轮咨询）
5. 【9.7】PerformanceAndCostCallback Token 成本审计（黑匣子账单）
6. 【9.8】langchain-chroma 内置数码避坑知识库（零配置 Built-in RAG）
7. 【9.9】create_agent 现代架构（1.x 标准姿势，告别 AgentExecutor）
8. 【9.10】上下文工程：@dynamic_prompt 动态系统提示 + Store 长期画像注入
9. 【9.11】自定义中间件：调用日志 / 模型调用次数限流 / 自动重试
10.【9.12】生产级护栏：黑名单拦截 + PII 脱敏（纵深防御装配栈）
"""

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Dict, Any

from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma                        # ✅ 独立伙伴包
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_agent                  # 【9.9】1.x 标准 Agent
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from langgraph.checkpoint.memory import MemorySaver        # 与 InMemorySaver 是同一个类的两个名字
from langgraph.store.memory import InMemoryStore
from rich.console import Console
from rich.panel import Panel

from s01_model_io import get_chat_model_primary              # 【9.1】统一模型工厂
from s07_callbacks_and_tracing import PerformanceAndCostCallback  # 【9.7】Token 审计
from s11_custom_middleware import LoggingMiddleware, CallCounterMiddleware, retry_model  # 【9.11】
from s12_guardrails_and_testing import ContentFilterMiddleware  # 【9.12】确定性护栏

console = Console()

# ==============================================================================
# 1. 【9.4】Pydantic 结构化选购决策报告 Schema
# ==============================================================================
class RecommendedProduct(BaseModel):
    brand_and_model: str = Field(description="品牌与具体型号，例如：'联想小新 Pro16 2024 / 锐龙版'")
    price_range: str = Field(description="参考价格区间，例如：'¥4999 - ¥5299'")
    key_specs: str = Field(description="核心配置概括，如：'R7-8845H / 32G / 1TB / 2.5K 120Hz 屏'")
    standout_pros: List[str] = Field(description="核心亮点与优势 (2-3项)")
    fatal_cons: List[str] = Field(description="致命缺点与真实吐槽 (1-2项)")

class ShoppingDecisionReport(BaseModel):
    category_summary: str = Field(description="选购品类与需求总结 (50字以内)")
    budget_evaluation: str = Field(description="预算合理性与当前市场行情评估")
    recommended_products: List[RecommendedProduct] = Field(description="精选 Top 2~3 款最值得买的机型列表")
    trap_warnings: List[str] = Field(description="该品类选购时必须警惕的偷工减料与营销陷阱 (2-4条)")
    overall_value_score: int = Field(description="当前品类在该预算下的性价比满意度评分 (0-100)", ge=0, le=100)
    final_verdict: str = Field(description="首席决策官一锤定音的购买决策建议 (100字以内)")

# ==============================================================================
# 2. 【9.8】内置开箱即用的数码防坑知识库 (Zero-Setup Built-in RAG)
# ==============================================================================
BUILTIN_HARDWARE_KNOWLEDGE = [
    Document(
        page_content="""
        【笔记本电脑选购核心避坑准则】
        1. 内存陷阱：千万注意"板载不可扩展内存（LPDDR）"，如果是 16G 且焊死在主板上，程序员多开 Docker 和 IDE 两年后必卡死，首选 32G 或支持双插槽扩展的机型。
        2. 屏幕陷阱：警惕 45% NTSC 低色域屏幕（通常宣传为"高清屏"但色彩极差泛白），必须认准 100% sRGB 或 100% DCI-P3 高色域，低亮度频闪需具备 DC 调光。
        3. 接口缩水：有些轻量本标配 Type-C 接口但仅支持 USB 2.0 传输协议或不支持 PD 快充，务必认准全功能 Type-C 或雷电4/USB4。
        """,
        metadata={"category": "Laptop", "topic": "笔记本避坑"}
    ),
    Document(
        page_content="""
        【手机与平板选购核心避坑准则】
        1. 芯片等级：买手机首先看处理器架构与能效比，远离曾经发热严重的翻车火龙处理器。
        2. 内存与闪存：建议 256GB 起步，闪存类型优先 UFS 3.1 / UFS 4.0，拒绝落后的 eMMC 5.1。
        3. 屏幕护眼：关注高频 PWM 调光（如 2160Hz / 3840Hz 以上）或类 DC 调光，避免低频频闪导致视力疲劳。
        """,
        metadata={"category": "Phone", "topic": "手机避坑"}
    ),
    Document(
        page_content="""
        【降噪耳机与数码配件避坑准则】
        1. 降噪耳机：宣传"通话降噪（ENC）"不等于"主动降噪（ANC）"，只有具备主动降噪才能消除地铁飞机噪音。
        2. 蓝牙协议：优先支持 LDAC、LHDC 或 aptX 无损传输协议，苹果生态用户认准 AAC。
        3. 显示器：警惕"假 4K"或低刷新率，程序员与设计办公优先 IPS 面板，游戏优先 Fast-IPS 或 OLED。
        """,
        metadata={"category": "Accessories", "topic": "配件避坑"}
    )
]

def init_hardware_rag():
    """初始化数码硬件知识库向量检索（9.8 标准链路：切块 → 向量入库 → retriever）"""
    splitter = RecursiveCharacterTextSplitter(chunk_size=160, chunk_overlap=20)
    splits = splitter.split_documents(BUILTIN_HARDWARE_KNOWLEDGE)

    api_key = os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
    model = os.getenv("EMBEDDING_MODEL", "")
    embeddings = OpenAIEmbeddings(
        api_key=api_key or "sk-dummy",
        base_url=api_base,
        model=model
    )
    try:
        return Chroma.from_documents(splits, embeddings, collection_name="smart_buyer_kb")
    except Exception as e:
        console.print(f"[dim]数码知识库初始化（模拟兼容模式）：{e}[/dim]")
        return None

GLOBAL_BUYER_KB = init_hardware_rag()

# ==============================================================================
# 3. 【9.5】Agent 选购决策工具集（Docstring = 写给模型的工具说明书）
# ==============================================================================
@tool
def search_product_reviews_and_complaints(query_keyword: str) -> str:
    """全网实时搜索指定数码产品的真实用户评测、真实差评与翻车吐槽。

    Args:
        query_keyword: 搜索关键词，例如 '联想小新 Pro16 真实缺点 吐槽 贴吧 评测'
    """
    try:
        try:
            from ddgs import DDGS                     # duckduckgo-search 新包名
        except ImportError:
            from duckduckgo_search import DDGS        # 旧包名兜底
        with DDGS() as ddgs:
            results = list(ddgs.text(f"{query_keyword} 真实缺点 评测 吐槽", max_results=3))
            if not results:
                return f"未检索到关于 '{query_keyword}' 的即时社区评价。"

            snippets = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                link = r.get("href", "")
                snippets.append(f"• [{title}]({link})\n  {body}")
            return "\n\n".join(snippets)
    except Exception as e:
        return (
            f"【社区评测汇总 (模拟)】针对 '{query_keyword}'：真实用户反馈整体性能释放激进，日常办公流畅；"
            f"主要槽点集中在原装电源适配器较重、高负载下风扇噪音明显、以及部分批次键盘键程偏软。"
        )

@tool
def calculate_specs_and_budget(formula: str) -> str:
    """精确计算价格优惠幅度、每元性能比、功耗释放比与预算剩余额度。

    Args:
        formula: 数学运算表达式，如 '5299 - 400'、'4999 / 32' (每G内存成本)
    """
    try:
        result = eval(formula, {"__builtins__": {}}, {})
        return f"测算结果: {result}"
    except Exception as e:
        return f"测算异常: {e}"

@tool
def query_hardware_traps(category_or_term: str) -> str:
    """查询内置的数码硬件避坑宝典，识别参数偷工减料与虚假营销话术。

    可用于检索屏幕色域陷阱、板载内存焊接陷阱、伪主动降噪、假4K等黑话。
    """
    if GLOBAL_BUYER_KB is None:
        return "【内置避坑宝典】屏幕必须认准 100% sRGB/DCI-P3 色域；轻薄本尽量选 32G 内存防止板载焊死无法升级；降噪耳机必须认准 ANC 主动降噪。"
    try:
        retriever = GLOBAL_BUYER_KB.as_retriever(search_kwargs={"k": 2})
        docs = retriever.invoke(category_or_term)
        return "\n\n".join([f"【避坑指南 - {d.metadata.get('topic')}】\n{d.page_content.strip()}" for d in docs])
    except Exception as e:
        return f"避坑知识库检索异常: {e}"

# ==============================================================================
# 4. 【9.10】上下文工程：Runtime Context + Store 长期画像 → 动态系统提示
# ==============================================================================
@dataclass
class BuyerContext:
    """运行期静态配置（会话级、固定不变）。不传时 runtime.context 为 None，需兜底。"""
    user_id: str = "guest"

# 【9.6】Store 长期记忆：预置两位老客户的选购偏好画像（跨会话持久）
def init_buyer_store() -> InMemoryStore:
    store = InMemoryStore()
    store.put(("buyers",), "user-veteran", {
        "communication_style": "极简直接，只要结论和参数表",
        "focus": "性价比与扩展性",
    })
    store.put(("buyers",), "user-rookie", {
        "communication_style": "手把手科普，多打比方、解释术语",
        "focus": "预算敏感、怕踩坑",
    })
    return store

@dynamic_prompt
def smart_buyer_dynamic_prompt(request: ModelRequest) -> str:
    """每次模型调用前动态拼装系统提示：基础人设 + Store 长期画像 + 会话长度自适应。

    读取链路（9.10 三数据源）：
    - request.runtime.context  → Runtime Context（本次请求的固定配置 user_id）
    - request.runtime.store    → Store（跨会话长期画像）
    - request.messages         → State（当前会话消息列表，判断是否该"长话短说"）
    """
    # 1) 基础人设：SmartBuyer 的使命与工作原则（不传 context 时优雅降级为游客画像）
    ctx = request.runtime.context
    user_id = getattr(ctx, "user_id", None) if ctx else None
    system = (
        "你是由 Vibe Coding 研发的顶级数码硬件评测专家兼消费避坑顾问 ——【SmartBuyer 选购参谋】。\n"
        "你的使命是帮助用户在预算范围内挑出最强性价比的数码产品，撕开厂商营销话术，绝不让用户当\"冤大头\"！\n\n"
        "你拥有三大专业工具：\n"
        "1. 【避坑宝典】优先检索内置硬件知识库，识别屏幕/内存/接口偷工减料陷阱；\n"
        "2. 【全网差评搜索】调用联网搜索真实用户翻车案例和缺点；\n"
        "3. 【性价比测算器】遇到价格计算、优惠测算时严禁心算，必须调用测算器。\n\n"
        "工作原则：\n"
        "- 推荐 2~3 款具体品牌型号，必须同时给出真实优点与致命槽点（拒绝恰饭）；\n"
        "- 标明避坑要点；\n"
        "- 态度中立客观，敢于说真话！"
    )

    # 2) Store 长期画像注入：这位顾客"是谁"，决定你怎么说话
    if user_id and request.runtime.store is not None:
        prefs = request.runtime.store.get(("buyers",), user_id)
        if prefs:
            style = prefs.value.get("communication_style", "")
            focus = prefs.value.get("focus", "")
            if style:
                system += f"\n\n【顾客画像】沟通风格：{style}；关注点：{focus}。请按此风格调整你的表达。"

    # 3) 会话长度自适应：聊了很久就长话短说（State 短期记忆感知）
    if len(request.messages) > 10:
        system += "\n\n【会话提示】这是一段较长的咨询，请尽量简洁直接地给出结论。"
    return system

# ==============================================================================
# 5. 【9.9 + 9.10~9.12】SmartBuyer 核心智能体：整机总装
# ==============================================================================
class SmartBuyerAgent:
    """AI 智能数码选购与避坑决策智能体（create_agent + 全栈中间件装配）"""

    def __init__(self):
        self.tools = [search_product_reviews_and_complaints, calculate_specs_and_budget, query_hardware_traps]
        self.llm = get_chat_model_primary(temperature=0.2)          # 【9.1】统一模型工厂
        self.checkpointer = MemorySaver()                           # 【9.6】线程级短期记忆（生产换 SqliteSaver）
        self.store = init_buyer_store()                             # 【9.6】跨会话长期画像
        self.setup_agent()

    def setup_agent(self):
        """整机总装：create_agent 一行装配 + 三层中间件纵深栈（由外到内）"""
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,                                       # 【9.5】工具生态
            middleware=[
                # —— 第 1 层【9.12】生产级护栏（纵深防御的入口）——
                ContentFilterMiddleware(banned_keywords=["hack", "exploit", "malware", "刷单"]),
                # —— 第 2 层【9.11】可观测与治理：日志 / 限流 / 重试 ——
                LoggingMiddleware(),
                CallCounterMiddleware(),      # 模型调用超 10 次自动熔断，防止费用失控
                retry_model,                  # 模型调用失败自动重试 3 次
                # —— 第 3 层【9.10】上下文工程：动态系统提示（放在最内层，最后定稿"剧本"）——
                smart_buyer_dynamic_prompt,
            ],
            checkpointer=self.checkpointer,   # thread_id 自动隔离多轮会话记忆
            store=self.store,                 # 跨会话长期画像，供 dynamic_prompt 读取
            context_schema=BuyerContext,      # 声明运行期上下文 Schema（user_id）
        )

    def chat_recommend(self, user_query: str, session_id: str = "default_shopper",
                       user_id: str | None = None) -> Dict[str, Any]:
        """多轮交互式选购问诊（thread_id = session_id 自动记忆；context 注入顾客身份）"""
        callback = PerformanceAndCostCallback()                  # 【9.7】黑匣子账单

        invoke_kwargs: Dict[str, Any] = {
            "config": {"configurable": {"thread_id": session_id}, "callbacks": [callback]}
        }
        if user_id:
            invoke_kwargs["context"] = BuyerContext(user_id=user_id)

        response = self.agent.invoke({"messages": [("user", user_query)]}, **invoke_kwargs)

        # 从 messages 消息流水线还原工具调用链（替代旧版 intermediate_steps）
        steps: List[Any] = []
        for msg in response["messages"]:
            if msg.type == "ai" and msg.tool_calls:
                for tc in msg.tool_calls:
                    # 使用 SimpleNamespace 兼容 app.py 的 act.tool / act.tool_input 访问方式
                    act = SimpleNamespace(tool=tc["name"], tool_input=tc["args"])
                    steps.append((act, ""))
            elif msg.type == "tool" and steps:
                steps[-1] = (steps[-1][0], msg.content)

        return {
            "output": response["messages"][-1].content,
            "intermediate_steps": steps,
            "total_tokens": callback.total_tokens,
            "cost_usd": callback.total_cost
        }

    def generate_structured_report(self, user_demand: str) -> ShoppingDecisionReport:
        """【9.4 + 9.3】一键生成标准化 Pydantic 选购决策矩阵报表（LCEL 管道：prompt | structured_llm）"""
        structured_llm = self.llm.with_structured_output(ShoppingDecisionReport)

        prompt = ChatPromptTemplate.from_template("""作为顶级数码硬件选购智库首席分析师，请根据用户的预算与需求，输出一份标准化的 Pydantic 选购决策报表。

【用户需求与预算】：
{demand}

请输出包含品类总结、预算评估、Top 2~3 推荐机型（含亮点与致命槽点）、避坑指南、性价比打分与最终拍板建议的结构。""")

        chain = prompt | structured_llm                          # 【9.3】LCEL 管道符编排
        return chain.invoke({"demand": user_demand})

# ==============================================================================
# 6. 终端 CLI 运行体验（整机点火试车）
# ==============================================================================
if __name__ == "__main__":
    console.print(Panel("[bold magenta]🛍️ SmartBuyer 综合实战：9.1~9.12 全零件整机交付[/bold magenta]", expand=False))
    buyer = SmartBuyerAgent()

    demand = "预算 5000 左右，买什么轻薄本适合大一计算机系学生写代码、偶尔看视频，要求续航长一点，不要太重。"
    console.print(f"[bold green]用户选购需求：[/bold green]{demand}\n")

    # 老客户 user-veteran：Store 画像注入 → 参谋会用"极简直接"风格说话
    result = buyer.chat_recommend(demand, session_id="cli_shopper", user_id="user-veteran")

    console.print("\n" + "=" * 50)
    console.print(f"[bold blue]💡 SmartBuyer 决策分析：[/bold blue]\n{result['output']}")
    console.print(f"\n[dim]Token 消耗: {result['total_tokens']} | 成本估算: ${result['cost_usd']:.6f}[/dim]")

    console.print("\n" + "=" * 50)
    console.print("[bold yellow]📑 测试一键生成结构化选购决策矩阵 (Pydantic)：[/bold yellow]")
    try:
        report = buyer.generate_structured_report(demand)
        console.print(f"• 品类需求: [bold cyan]{report.category_summary}[/bold cyan]")
        console.print(f"• 预算评估: {report.budget_evaluation}")
        console.print(f"• 性价比得分: [bold green]{report.overall_value_score}/100[/bold green]")
        console.print("\n• 推荐机型清单:")
        for p in report.recommended_products:
            console.print(f"  👉 [bold yellow]{p.brand_and_model}[/bold yellow] ({p.price_range})")
            console.print(f"     配置: {p.key_specs}")
            console.print(f"     亮点: {', '.join(p.standout_pros)}")
            console.print(f"     致命槽点: [red]{', '.join(p.fatal_cons)}[/red]")
        console.print(f"\n• 避坑警告: {', '.join(report.trap_warnings)}")
        console.print(f"\n• 最终拍板建议: [bold blue]{report.final_verdict}[/bold blue]")
    except Exception as e:
        console.print(f"[red]结构化报告生成报错：{e}[/red]")
