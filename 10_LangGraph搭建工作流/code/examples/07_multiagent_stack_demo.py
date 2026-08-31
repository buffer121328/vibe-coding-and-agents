"""07 MultiAgent 分层架构 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/07_MultiAgent分层架构.md
运行：python 07_multiagent_stack_demo.py   （无需任何 API Key）

用规则路由模拟“大堂经理”，完整复刻 dialog_state 状态栈的压栈/弹栈机制。

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
"""
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


def update_dialog_stack(left: list[str], right: str | None) -> list[str]:
    """自定义 reducer：right 为 None 不变；'pop' 弹栈；否则压栈。
    注意：invoke 时不要显式传 dialog_state（会被 reducer 当成一次更新）"""
    if right is None:
        return left
    if right == "pop":
        return left[:-1]
    return left + [right]


class State(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str              # 大堂经理的当前决策：flight=转交 / done=收官
    dialog_state: Annotated[list[str], update_dialog_stack]


def primary_assistant(state: State):
    """大堂经理：识别意图决定转交（真实项目由 LLM 调转交工具）"""
    msgs = state["messages"]
    if state.get("intent") == "done" or (msgs[-1].type != "human"):
        # 子助理刚交还控制权：接住话茬，等用户下一步指示
        return {"messages": [("assistant", "您好，机票的事已办妥，还有其他需要吗？")],
                "intent": "done"}
    if "机票" in msgs[-1].content:
        return {"messages": [("assistant", "正在为您转接航班助理...")],
                "intent": "flight", "dialog_state": "flight"}   # 压栈
    return {"messages": [("assistant", "您好，我是大堂经理，有什么可以帮您？")],
            "intent": "done"}


def enter_flight(state: State):
    """入口节点：像新同事接单时先在交接本上签名"""
    return {"messages": [("assistant", "[航班助理] 已接单，dialog_state 压栈为 flight")]}


def flight_agent(state: State):
    """子助理干活，干完交还主助理（dialog_state 弹栈）"""
    return {
        "messages": [("assistant", "[航班助理] 机票已查好，任务完成，交还主助理。")],
        "dialog_state": "pop",
        "intent": "done",
    }


def route_to_workflow(state: State) -> str:
    """总调度：经理说转交就去部门，否则收官（等用户下一句话）"""
    return "enter_flight" if state.get("intent") == "flight" else END


def build_graph():
    """装配并编译本节演示图（命令行与工作台共用同一份）"""
    builder = StateGraph(State)
    builder.add_node("primary_assistant", primary_assistant)
    builder.add_node("enter_flight", enter_flight)
    builder.add_node("flight_agent", flight_agent)
    builder.add_edge(START, "primary_assistant")
    builder.add_conditional_edges("primary_assistant", route_to_workflow)
    builder.add_edge("enter_flight", "flight_agent")
    builder.add_edge("flight_agent", "primary_assistant")   # leave_skill：回到主助理
    return builder.compile()


graph = build_graph()


def main():
    result = graph.invoke({"messages": [("user", "帮我订一张去东京的机票")]})
    for msg in result["messages"]:
        print(f"{msg.type}: {msg.content}")
    print("最终 dialog_state（应为空栈）：", result.get("dialog_state", []))


if __name__ == "__main__":
    main()
