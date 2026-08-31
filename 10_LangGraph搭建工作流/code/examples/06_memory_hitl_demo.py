"""06 Memory 与 Human-in-the-loop —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/06_Memory与Human-in-the-loop.md
运行：python 06_memory_hitl_demo.py   （无需任何 API Key）

工作台入口：build_graph() / build_guarded() 返回编译后的图（普通版 / 带刹车版），
供 ../workbench 直接 import 复用；每次调用都创建全新 MemorySaver，互不串台。
"""
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver


class State(TypedDict):
    messages: Annotated[list, add_messages]


def propose(state: State):
    """实习生节点：提出要执行敏感操作"""
    return {"messages": [("assistant", "我想调用『清空购物车』工具，请求审批。")]}


def sensitive_tool(state: State):
    """敏感操作节点：在 interrupt_before 名单里，必须老板签字才能进"""
    return {"messages": [("assistant", "敏感操作已执行：购物车已清空。")]}


def _builder():
    builder = StateGraph(State)
    builder.add_node("propose", propose)
    builder.add_node("sensitive_tool", sensitive_tool)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", "sensitive_tool")
    builder.add_edge("sensitive_tool", END)
    return builder


def build_graph():
    """演示一：只挂 Checkpointer 的普通版（每次全新存档，防状态串台）"""
    return _builder().compile(checkpointer=MemorySaver())


def build_guarded():
    """演示二：interrupt_before 敏感操作拦截版"""
    return _builder().compile(checkpointer=MemorySaver(), interrupt_before=["sensitive_tool"])


def main():
    # ============ 演示一：Checkpointer 短期记忆（跨调用记住同一会话） ============
    graph = build_graph()
    config = {"configurable": {"thread_id": "user_zhangsan_123"}}

    graph.invoke({"messages": [("user", "帮我清空购物车")]}, config)
    # 只要 thread_id 不变，第二次调用能接上之前的话茬（这里模拟：直接追问）
    snap = graph.get_state(config)
    print("== 演示一：短期记忆 ==")
    print("存档中的最后一条消息：", snap.values["messages"][-1].content)

    # ============ 演示二：interrupt_before 敏感操作拦截 ============
    guarded = build_guarded()
    config2 = {"configurable": {"thread_id": "user_lisi_456"}}

    guarded.invoke({"messages": [("user", "帮我清空购物车")]}, config2)
    state_now = guarded.get_state(config2)
    print("\n== 演示二：HITL 拦截 ==")
    print("程序停在了：", state_now.next, "（等待老板签字）")

    # 老板同意：不传新消息，直接传 None，图从存档继续跑（stream 是惰性的，记得消费它）
    for _ in guarded.stream(None, config2):
        pass
    state_after = guarded.get_state(config2)
    print("批准后执行完毕，最后一条消息：", state_after.values["messages"][-1].content)


if __name__ == "__main__":
    main()
