"""03 条件路由与动态决策 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/03_条件路由与动态决策.md
运行：python 03_conditional_routing_demo.py   （无需任何 API Key）

真实项目里 classify 节点换成 LLM 结构化输出即可；
本示例用规则版“分诊台”演示条件路由的全部机制。

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
"""
from typing import Literal, TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    input: str      # 用户原始输入
    category: str   # 分诊结果


def classify(state: State):
    """分诊台：判断意图并写入 State（真实项目换成 LLM 分类）"""
    text = state["input"]
    if "翻译" in text:
        cat = "translate"
    elif "总结" in text:
        cat = "summarize"
    else:
        cat = "chat"
    print(f">>> 分诊台判定：{cat}")
    return {"category": cat}


def handle(state: State):
    """各科室：这里用同一个函数占位，真实项目各写各的处理逻辑"""
    return {"input": f"[{state['category']}] 已处理：{state['input']}"}


def route(state: State) -> Literal["translate_node", "summarize_node", "chat_node"]:
    """路由函数：只读字段、返回节点名（保持只读 + 纯函数）"""
    return {
        "translate": "translate_node",
        "summarize": "summarize_node",
        "chat": "chat_node",
    }[state["category"]]


def build_graph():
    """装配并编译本节演示图（命令行与工作台共用同一份）"""
    builder = StateGraph(State)
    builder.add_node("classify", classify)
    builder.add_node("translate_node", handle)
    builder.add_node("summarize_node", handle)
    builder.add_node("chat_node", handle)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route)  # 十字路口的指路牌
    for name in ["translate", "summarize", "chat"]:
        builder.add_edge(f"{name}_node", END)
    return builder.compile()


graph = build_graph()


def main():
    for question in ["帮我把这段话翻译成英文", "帮我总结这篇文章", "今天天气不错"]:
        result = graph.invoke({"input": question, "category": ""})
        print("   ->", result["input"], "\n")


if __name__ == "__main__":
    main()
