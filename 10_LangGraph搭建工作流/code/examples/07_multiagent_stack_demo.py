"""07 MultiAgent 分层架构 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/07_MultiAgent分层架构.md
运行：python 07_multiagent_stack_demo.py   （无需任何 API Key）

用规则路由模拟前台主助理：识别到「机票」就压栈转交给航班专员，
专员办完弹栈交还。完整复刻 dialog_state 状态栈的压栈 / 弹栈。

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
"""
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


def update_dialog_stack(left: list[str], right: str | None) -> list[str]:
    """自定义 reducer：right 为 None 不变；'pop' 弹栈；否则压栈。

    注意：invoke 时不要显式传 dialog_state（会被 reducer 当成一次更新）。
    """
    if right is None:
        return left
    if right == "pop":
        return left[:-1]
    return left + [right]


class State(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str              # 主助理当前决策：flight=转交 / done=收官
    dialog_state: Annotated[list[str], update_dialog_stack]


FLIGHT_DEMO = {
    "flight_no": "CA-1801",
    "route": "北京 → 东京",
    "depart": "2026-09-01 08:40",
    "price": 1280,
}


def primary_assistant(state: State):
    """主助理：识别意图并决定是否转交。真实项目由 LLM 调用转交工具。"""
    msgs = state["messages"]
    if state.get("intent") == "done" or (msgs[-1].type != "human"):
        return {
            "messages": [
                (
                    "assistant",
                    "您好，机票的事已办妥。如果还要改酒店或租车，直接说即可，我会再转给对应专员。",
                )
            ],
            "intent": "done",
        }
    last = msgs[-1].content
    if "机票" in last or "航班" in last:
        return {
            "messages": [
                (
                    "assistant",
                    "这是航班业务，我把对话转交给航班专员，并在 dialog_state 里压入 flight。",
                )
            ],
            "intent": "flight",
            "dialog_state": "flight",
        }
    return {
        "messages": [
            ("assistant", "您好，我是前台主助理。订机票、改酒店或退租车，直接告诉我要办哪一件。")
        ],
        "intent": "done",
    }


def enter_flight(state: State):
    """入口节点：专员接单时先在交接本上留痕，方便调试时看到压栈已经生效。"""
    return {
        "messages": [
            (
                "assistant",
                f"[航班专员] 已接单。当前 dialog_state={state.get('dialog_state')}。"
                f"将按 {FLIGHT_DEMO['route']} 查询可订航班。",
            )
        ]
    }


def flight_agent(state: State):
    """子助理干活，干完把栈顶弹出，控制权交还主助理。"""
    demo = FLIGHT_DEMO
    return {
        "messages": [
            (
                "assistant",
                f"[航班专员] 已查到 {demo['flight_no']} {demo['route']}，"
                f"{demo['depart']} 起飞，￥{demo['price']}。任务完成，dialog_state 弹栈。",
            )
        ],
        "dialog_state": "pop",
        "intent": "done",
    }


def route_to_workflow(state: State) -> str:
    """总调度：主助理说转交就去部门，否则结束本轮等待用户下一句话。"""
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
    builder.add_edge("flight_agent", "primary_assistant")
    return builder.compile()


graph = build_graph()


def main():
    result = graph.invoke({"messages": [("user", "帮我订一张去东京的机票")]})
    for msg in result["messages"]:
        print(f"{msg.type}: {msg.content}")
    print("最终 dialog_state（应为空栈）：", result.get("dialog_state", []))


if __name__ == "__main__":
    main()
