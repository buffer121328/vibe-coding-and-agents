"""03 条件路由与动态决策 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/03_条件路由与动态决策.md
运行：python 03_conditional_routing_demo.py   （无需任何 API Key）

真实项目里 classify 节点换成 LLM 结构化输出即可；
本示例用规则版分类器演示条件路由的全部机制：先写入 category，再由只读路由函数指路。

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
"""
from typing import Literal, TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    input: str       # 用户原始输入
    category: str    # 分类结果：translate / summarize / chat


HANDLERS = {
    "translate": {
        "title": "翻译专员",
        "output": "EN: Hello, world — (demo translation of the original request)",
    },
    "summarize": {
        "title": "摘要专员",
        "output": "摘要：用户希望压缩一段文字的要点，本节点返回三句话以内的提纲。",
    },
    "chat": {
        "title": "闲聊专员",
        "output": "收到。这不像翻译或摘要请求，我按普通对话回应即可。",
    },
}


def classify(state: State):
    """分类节点：把意图写进 State。路由函数稍后只读这个字段，不再重新解析原文。"""
    text = state["input"]
    if any(key in text for key in ("翻译", "译成", "英文", "translate")):
        cat = "translate"
    elif any(key in text for key in ("总结", "摘要", "概括", "summarize")):
        cat = "summarize"
    else:
        cat = "chat"
    print(f">>> 分类节点判定：{cat}  | 原文：{text}")
    return {"category": cat}


def handle_translate(state: State):
    spec = HANDLERS["translate"]
    return {
        "input": f"[{spec['title']}] 原文「{state['input']}」→ {spec['output']}"
    }


def handle_summarize(state: State):
    spec = HANDLERS["summarize"]
    return {
        "input": f"[{spec['title']}] 针对「{state['input']}」→ {spec['output']}"
    }


def handle_chat(state: State):
    spec = HANDLERS["chat"]
    return {
        "input": f"[{spec['title']}] {spec['output']}（用户说：{state['input']}）"
    }


def route(state: State) -> Literal["translate_node", "summarize_node", "chat_node"]:
    """路由函数：只读 category，返回节点名。保持纯函数，方便单测。"""
    mapping = {
        "translate": "translate_node",
        "summarize": "summarize_node",
        "chat": "chat_node",
    }
    # 未知标签落到闲聊，避免条件边指向不存在的节点。
    return mapping.get(state["category"], "chat_node")


def build_graph():
    """装配并编译本节演示图（命令行与工作台共用同一份）"""
    builder = StateGraph(State)
    builder.add_node("classify", classify)
    builder.add_node("translate_node", handle_translate)
    builder.add_node("summarize_node", handle_summarize)
    builder.add_node("chat_node", handle_chat)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route)
    for name in ["translate", "summarize", "chat"]:
        builder.add_edge(f"{name}_node", END)
    return builder.compile()


graph = build_graph()


def main():
    samples = [
        "帮我把这段话翻译成英文：你好，世界",
        "帮我总结这篇文章的三个要点",
        "今天天气不错，聊聊周末去哪玩",
    ]
    for question in samples:
        result = graph.invoke({"input": question, "category": ""})
        print("   ->", result["input"], "\n")


if __name__ == "__main__":
    main()
