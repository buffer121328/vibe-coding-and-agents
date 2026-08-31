"""02 State 图的构建与运行 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/02_State图的构建与运行.md
运行：python 02_state_graph_demo.py   （无需任何 API Key）

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
"""
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


# 1. 定义状态：大家的“公共交接本”
class State(TypedDict):
    # add_messages 让新消息追加而不是覆盖
    messages: Annotated[list, add_messages]


# 2. 定义节点：具体的打工人（读取状态 -> 处理 -> 返回要更新的部分）
def greeter(state: State):
    return {"messages": [("assistant", "你好！我是打招呼节点。")]}


def echo(state: State):
    last = state["messages"][-1].content
    return {"messages": [("assistant", f"我收到了你说的话：{last}")]}


# 3. 把节点连起来：画路线图
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
    # 4. 运行：stream 逐步吐出每个节点产生的新状态
    for event in graph.stream({"messages": [("user", "你好，今天天气怎么样？")]}):
        print("------- 节点完成 -------")
        print(event)


if __name__ == "__main__":
    main()
