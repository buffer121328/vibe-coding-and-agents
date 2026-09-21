"""09 工作流设计模式 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/09_工作流设计模式.md
运行：python 09_workflow_patterns_demo.py   （无需任何 API Key）

演示三大模式：
- Routing：先分类再进专员；
- Orchestrator-Worker：Send 按语言数量动态派发；
- Evaluator-Optimizer：改稿循环带重写上限保险丝。

工作台入口：build_routing_graph() / build_map_graph() / build_eo_graph()
分别返回三大模式的编译图，供 ../workbench 直接 import 复用。
"""
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send


# ============ 模式一：Routing 路由 ============
class RouteState(TypedDict):
    question: str
    answer: str


PRICE_FAQ = {
    "标准版": "99 元 / 月，含 1 个工作区",
    "专业版": "199 元 / 月，含 5 个工作区与优先支持",
}


def classify(state: RouteState):
    q = state["question"]
    if any(key in q for key in ("多少钱", "价格", "收费", "套餐")):
        cat = "价格"
    else:
        cat = "退款"
    return {"answer": f"[分类:{cat}] "}


def pricing(state: RouteState):
    detail = "；".join(f"{k} {v}" for k, v in PRICE_FAQ.items())
    return {"answer": state["answer"] + f"走定价专员：{detail}。"}


def refund(state: RouteState):
    return {
        "answer": state["answer"] + "走退款专员：未使用额度 7 天内可全额退，已开票需先作废发票。"
    }


def route_by_topic(state: RouteState) -> str:
    return "pricing" if "分类:价格" in state["answer"] else "refund"


def build_routing_graph():
    """模式一 Routing：编译图（命令行与工作台共用）"""
    return (
        StateGraph(RouteState)
        .add_node("classify", classify)
        .add_node("pricing", pricing)
        .add_node("refund", refund)
        .add_edge(START, "classify")
        .add_conditional_edges("classify", route_by_topic)
        .add_edge("pricing", END)
        .add_edge("refund", END)
        .compile()
    )


# ============ 模式二：Orchestrator-Worker（Send 动态派发） ============
class BossState(TypedDict):
    langs: list
    results: Annotated[list, operator.add]


TRANSLATIONS = {
    "英": "Hello, fellow travellers — welcome aboard.",
    "日": "こんにちは、旅行者の皆さん。",
    "法": "Bonjour aux voyageurs.",
    "德": "Hallo an alle Reisenden.",
    "西": "Hola a todos los viajeros.",
}


def boss(state: BossState):
    """主管节点：只负责确认任务清单（真实项目这里会让模型拆 langs）。"""
    print(f">>> boss 收到语言清单：{state['langs']}")
    return {"langs": state["langs"]}


def worker(state: dict):
    """工人节点：每个 Send 实例只看到自己的 lang。"""
    lang = state["lang"]
    text = TRANSLATIONS.get(lang, f"（暂无 {lang} 文案，返回占位翻译）")
    return {"results": [f"{lang}文：{text}"]}


def merge(state: BossState):
    body = "；".join(state["results"])
    return {"results": [f"汇总（{len(state['results'])} 路工人）-> {body}"]}


def dispatch(state: BossState):
    """Send 路由函数（不是节点）：按语言数量动态派发 N 个工人。"""
    return [Send("translate", {"lang": lang}) for lang in state["langs"]]


def build_map_graph():
    """模式二 Orchestrator-Worker：编译图（命令行与工作台共用）"""
    return (
        StateGraph(BossState)
        .add_node("boss", boss)
        .add_node("translate", worker)
        .add_node("merge", merge)
        .add_edge(START, "boss")
        .add_conditional_edges("boss", dispatch)
        .add_edge("translate", "merge")
        .add_edge("merge", END)
        .compile()
    )


# ============ 模式三：Evaluator-Optimizer（带重写上限） ============
class EssayState(TypedDict):
    draft: str
    score: int
    revision: int


DRAFTS = {
    1: "第1版草稿：只写了结论，缺少数据和引用。",
    2: "第2版草稿：补了两组对比数据，但仍缺反例。",
    3: "第3版草稿：补上反例与来源，达到发布线。",
}


def writer(state: EssayState):
    n = state.get("revision", 0) + 1
    return {"draft": DRAFTS.get(n, f"第{n}版草稿"), "revision": n}


def evaluator(state: EssayState):
    """评估器：真实项目用 LLM 结构化输出打分，这里用规则模拟分数爬升。"""
    score = min(100, state["revision"] * 40)
    return {"score": score}


def route_after_eval(state: EssayState) -> str:
    if state["revision"] >= 3:
        return "force_pass"
    return "rewrite" if state["score"] < 90 else "pass"


def build_eo_graph():
    """模式三 Evaluator-Optimizer：编译图（命令行与工作台共用）"""
    return (
        StateGraph(EssayState)
        .add_node("writer", writer)
        .add_node("evaluator", evaluator)
        .add_edge(START, "writer")
        .add_edge("writer", "evaluator")
        .add_conditional_edges(
            "evaluator",
            route_after_eval,
            {"rewrite": "writer", "pass": END, "force_pass": END},
        )
        .compile()
    )


def main():
    print("== Routing ==")
    print(build_routing_graph().invoke({"question": "这个东西多少钱？", "answer": ""})["answer"])
    print(build_routing_graph().invoke({"question": "用了三天能退款吗？", "answer": ""})["answer"])

    print("\n== Orchestrator-Worker ==")
    print(build_map_graph().invoke({"langs": ["英", "日", "法"], "results": []})["results"][-1])

    print("\n== Evaluator-Optimizer ==")
    result = build_eo_graph().invoke({"draft": "", "score": 0, "revision": 0})
    print(f"最终：{result['draft']}（分数 {result['score']}，共改 {result['revision']} 版）")


if __name__ == "__main__":
    main()
