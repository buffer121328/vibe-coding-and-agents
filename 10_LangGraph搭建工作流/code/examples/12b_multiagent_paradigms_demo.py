"""12b 当前多智能体分类下的三种重点实现 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/12_子图与多智能体全谱.md 第 2~3 节
运行：python 12b_multiagent_paradigms_demo.py   （无需任何 API Key）

三种实现各建一张图（真实项目由 LLM 做决策，这里用规则模拟）：
- Router 路由分流：分类后交给对应专员
- Subagents（Supervisor 教学变体）：主管循环派活收活，专家各管一摊，最后汇总
- Custom workflow：Planner → Executor → Reviewer，不通过打回重做（带重试上限）

当前官方完整分类还包括 Handoffs 与 Skills；它们的差异与上下文工程见正文。
"""
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END


# ============ 范式一：Router 路由分流 ============
class RouteState(TypedDict):
    question: str
    kind: str          # 分类结论：sql / rag / code
    answer: str


def reception(state: RouteState):
    """分类台：真实项目用廉价 LLM 做分类，这里按关键词模拟。"""
    q = state["question"]
    if any(key in q for key in ("数据库", "SQL", "订单量", "统计")):
        cat = "sql"
    elif any(key in q for key in ("文档", "知识库", "制度", "手册")):
        cat = "rag"
    else:
        cat = "code"
    return {"kind": cat, "answer": f"[分类:{cat}] "}


def sql_agent(state: RouteState):
    return {
        "answer": state["answer"] + "SQL 专员：连接订单库，上月已支付订单 1,284 笔，合计 ￥2,176,000。"
    }


def rag_agent(state: RouteState):
    return {
        "answer": state["answer"] + "RAG 专员：命中《差旅管理办法》第 4.2 节与 FAQ-17，已整理成可引用答案。"
    }


def code_agent(state: RouteState):
    return {
        "answer": state["answer"] + "Code 专员：已生成分页查询片段，并在本地用样例数据跑通自测。"
    }


def route_by_kind(state: RouteState) -> str:
    """读分类结论决定去哪个专员。未知标签落到 code，避免指向不存在的节点。"""
    return state["kind"] if state["kind"] in {"sql", "rag", "code"} else "code"


def build_router_graph():
    """范式一 Router：编译图（命令行与工作台共用）"""
    return (
        StateGraph(RouteState)
        .add_node("reception", reception)
        .add_node("sql_agent", sql_agent)
        .add_node("rag_agent", rag_agent)
        .add_node("code_agent", code_agent)
        .add_edge(START, "reception")
        .add_conditional_edges(
            "reception",
            route_by_kind,
            {"sql": "sql_agent", "rag": "rag_agent", "code": "code_agent"},
        )
        .add_edge("sql_agent", END)
        .add_edge("rag_agent", END)
        .add_edge("code_agent", END)
        .compile()
    )


# ============ 实现二：Subagents（Supervisor 教学变体） ============
class SupState(TypedDict):
    task: str
    cursor: int
    reports: Annotated[list, operator.add]
    final: str


def supervisor(state: SupState):
    """主管：真实项目由 LLM 决定下一步派给谁，这里只做中转站。"""
    return {}


def route_supervisor(state: SupState) -> str:
    """派活逻辑：游标没派完就派下一个专家，派完收总。"""
    workers = ["researcher", "writer"]
    return workers[state["cursor"]] if state["cursor"] < len(workers) else "aggregator"


def researcher(state: SupState):
    return {
        "reports": ["[调研] 竞品定价 99/199 两档，用户最关心退款时效与发票"],
        "cursor": state["cursor"] + 1,
    }


def writer(state: SupState):
    return {
        "reports": ["[写作] 已按调研结论写出行业报告初稿，含价格对照表与风险提示"],
        "cursor": state["cursor"] + 1,
    }


def aggregator(state: SupState):
    return {"final": "最终报告 <- " + " + ".join(state["reports"])}


def build_supervisor_graph():
    """Subagents/Supervisor：用显式节点循环展示集中调度（命令行与工作台共用）。"""
    return (
        StateGraph(SupState)
        .add_node("supervisor", supervisor)
        .add_node("researcher", researcher)
        .add_node("writer", writer)
        .add_node("aggregator", aggregator)
        .add_edge(START, "supervisor")
        .add_conditional_edges(
            "supervisor",
            route_supervisor,
            {
                "researcher": "researcher",
                "writer": "writer",
                "aggregator": "aggregator",
            },
        )
        .add_edge("researcher", "supervisor")
        .add_edge("writer", "supervisor")
        .add_edge("aggregator", END)
        .compile()
    )


# ============ 实现三：Custom workflow（Planner-Executor-Reviewer） ============
class PerState(TypedDict):
    requirement: str
    plan: str
    draft: str
    verdict: str
    revision: int


IMPLEMENTATIONS = {
    1: "第1版：只有页面骨架，缺少筛选和导出。",
    2: "第2版：补上日期筛选与 CSV 导出，仍缺权限校验。",
    3: "第3版：补上角色权限与空数据兜底，达到发布线。",
}


def planner(state: PerState):
    return {
        "plan": "1.列出指标  -> 2.写查询  -> 3.做看板  -> 4.补权限",
        "revision": 0,
    }


def executor(state: PerState):
    n = state["revision"] + 1
    return {"draft": IMPLEMENTATIONS.get(n, f"第{n}版实现"), "revision": n}


MAX_REVISION = 3


def reviewer(state: PerState):
    """评审员：真实项目用 LLM 结构化输出（verdict + comment），这里用规则模拟。"""
    if state["revision"] >= MAX_REVISION:
        return {"verdict": "pass"}
    return {"verdict": "pass" if state["revision"] >= 2 else "needs_fix"}


def route_after_review(state: PerState) -> str:
    return END if state["verdict"] == "pass" else "executor"


def build_per_graph():
    """Custom workflow：Planner-Executor-Reviewer 编译图。"""
    return (
        StateGraph(PerState)
        .add_node("planner", planner)
        .add_node("executor", executor)
        .add_node("reviewer", reviewer)
        .add_edge(START, "planner")
        .add_edge("planner", "executor")
        .add_edge("executor", "reviewer")
        .add_conditional_edges(
            "reviewer",
            route_after_review,
            {"executor": "executor", END: END},
        )
        .compile()
    )


def main():
    print("== Router 路由分流 ==")
    print(build_router_graph().invoke(
        {"question": "帮我查一下上个月的数据库订单量", "kind": "", "answer": ""})["answer"])

    print("\n== Subagents（Supervisor 教学变体）==")
    print(build_supervisor_graph().invoke(
        {"task": "写一份行业调研报告", "cursor": 0, "reports": [], "final": ""})["final"])

    print("\n== Custom workflow：Planner-Executor-Reviewer ==")
    result = build_per_graph().invoke(
        {"requirement": "做一个数据看板", "plan": "", "draft": "", "verdict": "", "revision": 0})
    print(f"计划：{result['plan']}")
    print(f"交付：{result['draft']}（共执行 {result['revision']} 版，评审结论 {result['verdict']}）")


if __name__ == "__main__":
    main()
