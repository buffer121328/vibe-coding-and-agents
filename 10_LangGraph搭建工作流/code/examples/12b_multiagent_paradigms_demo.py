"""12b 多智能体三大实战范式 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/12_子图与多智能体全谱.md 第 3 节
运行：python 12b_multiagent_paradigms_demo.py   （无需任何 API Key）

三大范式各建一张图（真实项目由 LLM 做决策，这里用规则模拟，图的机制完全一致）：
- Router 路由分流：分诊台先把问题分类，再交给对应专员
- Supervisor 主管派活：主管循环派活收活，专家各管一摊，最后汇总
- Planner-Executor-Reviewer：规划 → 执行 → 评审，不通过打回重做（带重试上限保险丝）
"""
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END


# ============ 范式一：Router 路由分流 ============
class RouteState(TypedDict):
    question: str
    kind: str          # 分诊结论：sql / rag / code
    answer: str


def reception(state: RouteState):
    """分诊台：真实项目用廉价 LLM 做分类，这里按关键词模拟"""
    q = state["question"]
    cat = "sql" if "数据库" in q else ("rag" if "文档" in q or "知识库" in q else "code")
    return {"kind": cat, "answer": f"[分诊:{cat}] "}


def sql_agent(state: RouteState):
    return {"answer": state["answer"] + "SQL 专员：连接订单库，查询结果已返回。"}


def rag_agent(state: RouteState):
    return {"answer": state["answer"] + "RAG 专员：命中知识库 3 篇文档，已整理成答案。"}


def code_agent(state: RouteState):
    return {"answer": state["answer"] + "Code 专员：代码片段已生成并跑通自测。"}


def route_by_kind(state: RouteState) -> str:
    """读分诊结论决定去哪个专员（ Conditional Edge 的标准用法）"""
    return state["kind"]


def build_router_graph():
    """范式一 Router：编译图（命令行与工作台共用）"""
    return (
        StateGraph(RouteState)
        .add_node("reception", reception)
        .add_node("sql_agent", sql_agent)
        .add_node("rag_agent", rag_agent)
        .add_node("code_agent", code_agent)
        .add_edge(START, "reception")
        .add_conditional_edges("reception", route_by_kind,
                               {"sql": "sql_agent", "rag": "rag_agent", "code": "code_agent"})
        .add_edge("sql_agent", END)
        .add_edge("rag_agent", END)
        .add_edge("code_agent", END)
        .compile()
    )


# ============ 范式二：Supervisor 主管派活 ============
class SupState(TypedDict):
    task: str
    cursor: int                                # 派活进度游标
    reports: Annotated[list, operator.add]     # 各专家交回的活
    final: str


def supervisor(state: SupState):
    """主管：真实项目由 LLM 决定下一步派给谁，这里只做中转站"""
    return {}


def route_supervisor(state: SupState) -> str:
    """派活逻辑：游标没派完就派下一个专家，派完收总"""
    workers = ["researcher", "writer"]
    return workers[state["cursor"]] if state["cursor"] < len(workers) else "aggregator"


def researcher(state: SupState):
    return {"reports": ["[调研工] 竞品与市场数据已备齐"], "cursor": state["cursor"] + 1}


def writer(state: SupState):
    return {"reports": ["[写作工] 行业报告初稿已完成"], "cursor": state["cursor"] + 1}


def aggregator(state: SupState):
    return {"final": "最终报告 <- " + " + ".join(state["reports"])}


def build_supervisor_graph():
    """范式二 Supervisor：编译图（命令行与工作台共用）"""
    return (
        StateGraph(SupState)
        .add_node("supervisor", supervisor)
        .add_node("researcher", researcher)
        .add_node("writer", writer)
        .add_node("aggregator", aggregator)
        .add_edge(START, "supervisor")
        .add_conditional_edges("supervisor", route_supervisor,
                               {"researcher": "researcher", "writer": "writer",
                                "aggregator": "aggregator"})
        .add_edge("researcher", "supervisor")   # 干完活交回主管，由主管决定下一步
        .add_edge("writer", "supervisor")
        .add_edge("aggregator", END)
        .compile()
    )


# ============ 范式三：Planner-Executor-Reviewer ============
class PerState(TypedDict):
    requirement: str
    plan: str
    draft: str
    verdict: str
    revision: int


def planner(state: PerState):
    """规划师：把需求拆成步骤清单"""
    return {"plan": "1.查资料 -> 2.写实现 -> 3.自查", "revision": 0}


def executor(state: PerState):
    """执行者：按计划产出一版实现"""
    n = state["revision"] + 1
    return {"draft": f"第{n}版实现", "revision": n}


MAX_REVISION = 3


def reviewer(state: PerState):
    """评审员：真实项目用 LLM 结构化输出（verdict + comment），这里用规则模拟"""
    if state["revision"] >= MAX_REVISION:
        # 保险丝：重试达到上限强制放行，防止执行者被无限打回
        return {"verdict": "pass"}
    return {"verdict": "pass" if state["revision"] >= 2 else "needs_fix"}


def route_after_review(state: PerState) -> str:
    return END if state["verdict"] == "pass" else "executor"


def build_per_graph():
    """范式三 Planner-Executor-Reviewer：编译图（命令行与工作台共用）"""
    return (
        StateGraph(PerState)
        .add_node("planner", planner)
        .add_node("executor", executor)
        .add_node("reviewer", reviewer)
        .add_edge(START, "planner")
        .add_edge("planner", "executor")
        .add_edge("executor", "reviewer")
        .add_conditional_edges("reviewer", route_after_review,
                               {"executor": "executor", END: END})
        .compile()
    )


def main():
    print("== Router 路由分流 ==")
    print(build_router_graph().invoke(
        {"question": "帮我查一下上个月的数据库订单量", "kind": "", "answer": ""})["answer"])

    print("\n== Supervisor 主管派活 ==")
    print(build_supervisor_graph().invoke(
        {"task": "写一份行业调研报告", "cursor": 0, "reports": [], "final": ""})["final"])

    print("\n== Planner-Executor-Reviewer ==")
    result = build_per_graph().invoke(
        {"requirement": "做一个数据看板", "plan": "", "draft": "", "verdict": "", "revision": 0})
    print(f"计划：{result['plan']}")
    print(f"交付：{result['draft']}（共执行 {result['revision']} 版，评审结论 {result['verdict']}）")


if __name__ == "__main__":
    main()
