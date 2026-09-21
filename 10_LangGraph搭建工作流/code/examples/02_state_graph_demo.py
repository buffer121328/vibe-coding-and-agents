"""02 State 图的构建与运行 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/02_State图的构建与运行.md
运行：python 02_state_graph_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。

这一节只演示三件事：
1. State 是所有节点共用的交接本；
2. 节点只返回“想更新的字段”，由 add_messages 追加，而不是整本覆盖；
3. START → 节点 → 节点 → END 是最普通的直连轨道。
"""
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


class State(TypedDict):
    # add_messages：新消息追加到列表末尾；同 id 的消息则按 id 覆盖。
    # 如果去掉这个 Annotated，第二次写入 messages 会把第一次的对话整页抹掉。
    messages: Annotated[list, add_messages]


def greeter(state: State):
    """入口接待：读到用户第一句话，先回一条固定开场。"""
    user_text = state["messages"][-1].content
    return {
        "messages": [
            (
                "assistant",
                f"你好！我是打招呼节点。已经记下你说的「{user_text}」，接下来交给回声节点。",
            )
        ]
    }


def echo(state: State):
    """回声节点：从完整历史里取出用户原话，再追加一条确认。"""
    user_lines = [m.content for m in state["messages"] if m.type == "human"]
    original = user_lines[-1] if user_lines else "(没有找到用户消息)"
    return {
        "messages": [
            (
                "assistant",
                f"回声节点看到完整交接本里共 {len(state['messages'])} 条消息。"
                f"你最初说的是：「{original}」。",
            )
        ]
    }


def build_graph():
    """装配并编译本节演示图（命令行与工作台共用同一份）"""
    builder = StateGraph(State)
    builder.add_node("greeter", greeter)
    builder.add_node("echo", echo)
    builder.add_edge(START, "greeter")
    builder.add_edge("greeter", "echo")
    builder.add_edge("echo", END)
    return builder.compile()


graph = build_graph()


def main():
    print("== stream：每走完一个节点，就打印一次增量 ==")
    for event in graph.stream({"messages": [("user", "你好，今天天气怎么样？")]}):
        print("------- 节点完成 -------")
        print(event)

    print("\n== invoke：一次性拿到完整交接本 ==")
    result = graph.invoke({"messages": [("user", "帮我记一下：下周去杭州")]})
    for msg in result["messages"]:
        print(f"[{msg.type}] {msg.content}")


if __name__ == "__main__":
    main()
