"""12 子图与多智能体全谱 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/12_子图与多智能体全谱.md
运行：python 12_subgraphs_demo.py   （无需任何 API Key）

演示真子图：独立编译的子图作为父图节点 + 共享状态键透传 + xray 透视。

工作台入口：build_graph() 返回编译后的父图，供 ../workbench 直接 import 复用。
"""
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


# ---------- 子图：航班部门（有自己的完整内部流程） ----------
class FlightState(TypedDict):
    messages: Annotated[list, add_messages]   # 同名键与父图自动透传
    ticket: str


def book_flight(state: FlightState):
    return {"ticket": "CA-1801", "messages": [("assistant", "[子图] 已出票 CA-1801")]}


def build_flight_subgraph():
    """子图：先独立编译（命令行与工作台共用）"""
    return (
        StateGraph(FlightState)
        .add_node("book_flight", book_flight)
        .add_edge(START, "book_flight")
        .add_edge("book_flight", END)
        .compile()          # 先独立编译
    )


# ---------- 父图：主助理 + 把子图整个当一个节点 ----------
class ParentState(TypedDict):
    messages: Annotated[list, add_messages]
    ticket: str


def primary(state: ParentState):
    return {"messages": [("assistant", "[父图] 识别到订票意图，委派给航班部门子图。")]}


def report(state: ParentState):
    return {"messages": [("assistant", f"[父图] 收到子图结果：{state['ticket']}，汇报完毕。")]}


def build_graph():
    """装配并编译父图（把编译后的子图整个当一个节点接入）"""
    parent_builder = StateGraph(ParentState)
    parent_builder.add_node("primary", primary)
    parent_builder.add_node("flight_department", build_flight_subgraph())   # 编译后的图 = 节点
    parent_builder.add_node("report", report)
    parent_builder.add_edge(START, "primary")
    parent_builder.add_edge("primary", "flight_department")
    parent_builder.add_edge("flight_department", "report")
    parent_builder.add_edge("report", END)
    return parent_builder.compile()


graph = build_graph()


def main():
    result = graph.invoke({"messages": [("user", "帮我订机票")], "ticket": ""})
    print("== 子图嵌套执行 ==")
    for msg in result["messages"]:
        print(msg.content)

    # 父图看不到子图的私有内部，但能看到共享键 ticket
    print("父图视角的共享键 ticket：", result["ticket"])

    # 用 xray 透视子图内部结构（对比 xray=False 只能看到一个黑盒节点）
    print("\n== xray=False（默认，子图是黑盒） ==")
    print(" -> ".join(n.name for n in graph.get_graph().nodes.values()))
    print("== xray=True（透视子图内部） ==")
    print(" -> ".join(n.name for n in graph.get_graph(xray=True).nodes.values()))


if __name__ == "__main__":
    main()
