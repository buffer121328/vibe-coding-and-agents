"""05 图的可视化与流式调试 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/05_图的可视化与流式调试.md
运行：python 05_streaming_debug_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    query: str
    answer: str


def search(state: State):
    print(">>> 进入 search，收到输入：", state["query"])
    result = f"关于「{state['query']}」的模拟搜索结果"
    print(">>> search 返回：", result)
    return {"answer": result}


def reply(state: State):
    return {"answer": f"最终回答：{state['answer']}"}


def build_graph():
    """装配并编译本节演示图（命令行与工作台共用同一份）"""
    builder = StateGraph(State)
    builder.add_node("search", search)
    builder.add_node("reply", reply)
    builder.add_edge(START, "search")
    builder.add_edge("search", "reply")
    builder.add_edge("reply", END)
    return builder.compile()


app = build_graph()


def main():
    # 1. 可视化：零依赖打印 Mermaid 源码（可粘贴到 https://mermaid.live 查看）
    print("======== Mermaid 源码 ========")
    print(app.get_graph().draw_mermaid())

    # 2. 流式观察：每跑完一个节点，就吐出一次状态更新（updates 模式只含增量）
    print("======== stream_mode='updates' ========")
    for event in app.stream({"query": "LangGraph 是什么"}, stream_mode="updates"):
        for node_name, update in event.items():
            print(f"节点 {node_name} 更新了：{update}")


if __name__ == "__main__":
    main()
