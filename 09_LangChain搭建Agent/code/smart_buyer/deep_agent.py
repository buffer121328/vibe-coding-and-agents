"""
SmartBuyer · deep_agent.py —— deepagents 深度版（Phase 2 + Phase 4）
====================================================================
课程出身：9.13 收官实战的演进版（演进路线 Phase 2/4，见项目 README）。

核心升级（对照课程版 main.py）：
1. 【Phase 2】create_deep_agent 整车厂：在 9.7/9.11 学过的 AgentMiddleware 体系上，
   预装虚拟文件系统 / 任务规划 / 子代理委派 / 长期记忆 / 技能库五件套；
2. 【Phase 2】三个专项子代理（SubAgent dict）：差评侦察员 / 参数测算师 / 避坑审核员，
   主参谋经 task() 派单，各自在隔离上下文里干活，只交回最终报告（上下文隔离）；
3. 【Phase 2】报告写入虚拟文件系统 /reports/*.md，子代理产出的中间过程不再污染主对话；
4. 【Phase 4】/memories/ 路由到 StoreBackend：顾客档案跨会话沉淀，按 user_id namespace 隔离
   （同一套 Store 机制对应课程 9.6 的"长期记忆"）；
5. 【Phase 4】FilesystemPermission 权限网：只允许写 /reports/ 与 /memories/，
   其余路径写入直接拒绝（最小权限原则）。

运行（在 code/ 目录下，需 .env 配置模型 Key）：
    uv run python -m smart_buyer.deep_agent
"""

import os

from dotenv import load_dotenv
load_dotenv()

from langchain_core.tools import tool
from langgraph.store.memory import InMemoryStore
from rich.console import Console
from rich.panel import Panel

from deepagents import create_deep_agent, FilesystemPermission
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.types import TracePolicy, omit_payload

# 复用课程版 main.py 的自包含零件（模型工厂 + 三大工具）——单一事实来源
from smart_buyer.main import (
    get_chat_model_primary,
    search_product_reviews_and_complaints,
    calculate_specs_and_budget,
    query_hardware_traps,
    PerformanceAndCostCallback,
)

# 【Phase 3 闭环】MCP 行情工具：与课程版 main.py 共享同一数据源（内置演示服务器）
from smart_buyer.mcp_tools import build_mcp_tools

_MCP_TOOLS, _MCP_ERRORS = build_mcp_tools(urls=[])
_MCP = {t.name: t for t in _MCP_TOOLS}   # 按名取用：子代理各领所需

console = Console()


# ==============================================================================
# 0. 【Phase 4】可观测层：Token 账单 + LangSmith 链路追踪（可选启用）
# ==============================================================================
def trace_policy() -> TracePolicy:
    """深度任务中间过程很长（子代理多轮对话），追踪里默认不打码；
    若接入 LangSmith 且担心敏感内容上云，改为 TracePolicy(process_outputs=omit_payload)
    即可让各中间件钩子的输出在追踪里整段丢弃（课程 9.11 的 TracePolicy 姿势）。"""
    return TracePolicy()


def cost_callback() -> PerformanceAndCostCallback:
    """每次 invoke 建一个新的黑匣子账单回调（9.7 零件复用）。"""
    return PerformanceAndCostCallback()


def langsmith_enabled() -> bool:
    """是否接通 LangSmith 全链路观测（1.4 原生集成，零代码）：
    设置 LANGSMITH_TRACING=true + LANGSMITH_API_KEY 后，子代理/工具/中间件的
    每一跳都会自动上报；未配置时本函数仅返回 False，不影响运行。"""
    return os.getenv("LANGSMITH_TRACING", "").lower() == "true"


# ==============================================================================
# 1. 【Phase 4】多用户存储：Store + CompositeBackend 按 user_id 路由
# ==============================================================================
def build_multi_user_backend(user_id: str = "guest"):
    """构造按用户隔离的后端：
    - /memories/<user_id>/... → StoreBackend（按 user_id 建 namespace，跨会话持久）
    - 其余路径（含 /reports/）→ StateBackend（会话级虚拟盘，演示零落盘副作用）
    生产环境把 InMemoryStore 换成 LangGraph Server 自动供给的 Store 即可。
    """
    store = InMemoryStore()
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            f"/memories/{user_id}/": StoreBackend(
                namespace=lambda rt: ("smart-buyer", user_id),  # 按 user_id 隔离
                store=store,
            ),
        },
    )
    return backend, store


# ==============================================================================
# 2. 【Phase 4】最小权限网：只允许写 /reports/ 与 /memories/，其余拒绝
# ==============================================================================
BUYER_PERMISSIONS = [
    FilesystemPermission(
        operations=["write"],
        paths=["/reports/**", "/memories/**"],
        mode="allow",
    ),
    FilesystemPermission(
        operations=["write"],
        paths=["/**"],
        mode="deny",
    ),
]


# ==============================================================================
# 3. 【Phase 2】三个专项子代理：主参谋派单，各管一摊
# ==============================================================================
def build_subagents():
    """三个 SubAgent dict（deepagents 0.7 字段实测：name/description/system_prompt/
    tools/model/middleware/interrupt_on/skills/permissions/response_format/mode）"""

    review_scout = {
        "name": "review-scout",
        "description": "差评侦察员：全网搜索指定产品的真实用户差评、翻车案例与吐槽",
        "system_prompt": (
            "你是差评侦察员。收到产品名后，用 search_product_reviews_and_complaints 工具"
            "搜索该产品的真实缺点与用户吐槽，把发现整理成要点清单（每条一句话，标注可信度）。"
            "完成后把清单写入 /reports/reviews.md，并在最终回复里给出 3 条最致命的槽点摘要。"
        ),
        "tools": [search_product_reviews_and_complaints],
        # isolated（默认）：只看到任务描述，全新开局——脏活累活的中间消息不污染主参谋
    }

    spec_analyst = {
        "name": "spec-analyst",
        "description": "参数测算师：精确计算价格、优惠、每元性能比与预算余量（严禁心算）；结合历史价格与以旧换新估价给出入手时机建议",
        "system_prompt": (
            "你是参数测算师。收到价格/配置任务后：\n"
            "1. 必须调用 calculate_specs_and_budget 工具完成所有算术（绝不心算）；\n"
            "2. 用 query_price_history 查历史价格判断当前是否好价；\n"
            "3. 用户有旧机时用 estimate_trade_in 估算抵扣，给出真实入手成本；\n"
            "4. 把测算过程与结论写入 /reports/specs.md，最终回复只给结论表格。"
        ),
        "tools": [calculate_specs_and_budget,
                  _MCP["query_price_history"], _MCP["estimate_trade_in"]],
    }

    trap_auditor = {
        "name": "trap-auditor",
        "description": "避坑审核员：检索内置避坑宝典 + 官方参数核对，审查推荐方案里的偷工减料与营销话术",
        "system_prompt": (
            "你是避坑审核员。收到品类/关键词后：\n"
            "1. 调用 query_hardware_traps 检索避坑宝典；\n"
            "2. 用 query_official_specs 拉官方参数，对照检查商家宣传是否缩水"
            "（重点：内存是否板载焊死、屏幕色域、接口规格）；\n"
            "3. 顺带用 query_after_sales 核对保修政策是否坑人；\n"
            "4. 把审核意见写入 /reports/traps.md，最终回复列出必须写进购买决策的避坑警告。"
        ),
        "tools": [query_hardware_traps,
                  _MCP["query_official_specs"], _MCP["query_after_sales"]],
    }

    logistics_advisor = {
        "name": "logistics-advisor",
        "description": "物流售后顾问：按收货地区与渠道估算送达时效，急用党/售后敏感型用户的决策依据",
        "system_prompt": (
            "你是物流售后顾问。收到收货地区与渠道偏好后，调用 query_delivery_time 与 "
            "query_after_sales，把时效对比与售后风险写入 /reports/logistics.md，"
            "最终回复给出一句话建议（哪个渠道/时机下单最合适）。"
        ),
        "tools": [_MCP["query_delivery_time"], _MCP["query_after_sales"]],
    }

    return [review_scout, spec_analyst, trap_auditor, logistics_advisor]


# ==============================================================================
# 4. 深度版总装：create_deep_agent
# ==============================================================================
BASE_PROMPT = (
    "你是【SmartBuyer 深度版】——顶级数码硬件评测专家兼消费避坑顾问。\n"
    "你的使命：帮用户在预算内挑出最强性价比的数码产品，撕开营销话术，绝不让用户当冤大头。\n\n"
    "工作方式（多智能体协作）：\n"
    "1. 拆解用户需求后，用 task() 把专项活派给子代理：差评侦察（review-scout）、"
    "参数测算与入手时机（spec-analyst）、避坑与官方参数审核（trap-auditor）、"
    "物流售后顾问（logistics-advisor）；\n"
    "2. 汇总各报告（/reports/ 下）后，亲自撰写最终《选购决策与避坑报告》，"
    "写入 /reports/final_report.md；\n"
    "3. 把本次咨询学到的顾客偏好（预算区间、品牌偏好、沟通风格）沉淀到顾客记忆目录；\n"
    "4. 最终回复用户：推荐 2~3 款具体型号（优点 + 致命槽点）+ 是否好价 + 避坑警告 + 一锤定音建议。"
)


def build_deep_agent(user_id: str = "guest", model=None):
    """装配深度版 SmartBuyer（deepagents 整车厂）"""
    backend, store = build_multi_user_backend(user_id)
    agent = create_deep_agent(
        model=model or get_chat_model_primary(temperature=0.2),
        tools=[],                              # 主参谋自己不带工具，专项活全部外包子代理
        system_prompt=BASE_PROMPT,
        subagents=build_subagents(),
        backend=backend,
        permissions=BUYER_PERMISSIONS,
        memory=[f"/memories/{user_id}/MEMORY.md"],   # 【Phase 4】长期记忆文件（无则子代理首聊后创建）
    )
    return agent, store


# ==============================================================================
# 5. CLI 试车
# ==============================================================================
if __name__ == "__main__":
    console.print(Panel("[bold magenta]🛍️ SmartBuyer 深度版（deepagents 五件套）点火试车[/bold magenta]", expand=False))
    agent, store = build_deep_agent(user_id="user-veteran")

    demand = ("预算 5000 左右买轻薄本，写代码用、偶尔看视频，要求续航长。"
              "请派差评侦察员搜真实槽点、测算师算每元性能比、审核员查避坑宝典，最后给我决策报告。")
    console.print(f"[bold green]用户需求：[/bold green]{demand}\n")

    try:
        cb = cost_callback()
        result = agent.invoke(
            {"messages": [("user", demand)]},
            config={"recursion_limit": 60,          # 深度任务步数多，放宽递归上限
                    "callbacks": [cb]},
        )
        final = result["messages"][-1]
        console.print("\n[bold blue]💡 深度版最终答复：[/bold blue]")
        console.print(str(getattr(final, "content", final))[:1500])
        console.print(f"\n[dim]📊 Token 账单：{cb.total_tokens} tokens，成本估算 ${cb.total_cost:.6f}"
                      f"｜LangSmith 观测：{'已接通' if langsmith_enabled() else '未启用（设 LANGSMITH_TRACING=true 开启）'}[/dim]")

        files = result.get("files") or {}
        if isinstance(files, dict):
            console.print(f"\n[dim]📁 虚拟文件系统现存文件：{sorted(files.keys())}[/dim]")
    except Exception as e:
        console.print(f"[red]深度版试车失败：{e}[/red]")
        console.print("[dim]提示：需要 .env 配置可用模型 Key；子代理多轮调用耗时较长属正常。[/dim]")
