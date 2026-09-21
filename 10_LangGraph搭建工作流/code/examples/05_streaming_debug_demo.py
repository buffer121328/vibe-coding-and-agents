"""05 图的可视化与流式调试 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/05_图的可视化与流式调试.md
运行：python 05_streaming_debug_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。

对照两种 stream_mode：
- updates：每个节点只吐自己写入的增量
- values ：每个超步结束后吐完整 State
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    query: str
    answer: str


FACTS = {
    "langgraph": (
        "LangGraph 是 LangChain 官方的有状态编排运行时："
        "节点干活、边决定下一步，Checkpointer 负责存档。"
    ),
    "checkpoint": (
        "Checkpointer 在每个超步结束时拍快照。"
        "同一 thread_id 可以续聊、暂停审批、崩溃后从断点继续。"
    ),
    "interrupt": (
        "interrupt() 在节点内部按条件暂停，并把 JSON 数据包交给人类审批，"
        "再用 Command(resume=...) 恢复。"
    ),
}


def search(state: State):
    print(">>> 进入 search，收到输入：", state["query"])
    q = state["query"].lower()
    hit = next((text for key, text in FACTS.items() if key in q), None)
    if hit is None:
        hit = f"知识库暂无「{state['query']}」的专条，返回一条兜底说明：它是工作流编排相关概念。"
    print(">>> search 返回：", hit)
    return {"answer": hit}


def reply(state: State):
    """把检索结果包成用户能看的最终回答。values 模式下可以观察 answer 如何被覆盖。"""
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
    print("======== Mermaid 源码（可粘贴到 https://mermaid.live） ========")
    print(app.get_graph().draw_mermaid())

    payload = {"query": "LangGraph 是什么", "answer": ""}

    print("======== stream_mode='updates'（只看增量） ========")
    for event in app.stream(payload, stream_mode="updates"):
        for node_name, update in event.items():
            print(f"节点 {node_name} 更新了：{update}")

    print("\n======== stream_mode='values'（每步完整快照） ========")
    for snap in app.stream(payload, stream_mode="values"):
        print(snap)


if __name__ == "__main__":
    main()
