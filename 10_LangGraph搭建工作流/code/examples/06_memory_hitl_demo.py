"""06 Memory 与 Human-in-the-loop —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/06_Memory与Human-in-the-loop.md
运行：python 06_memory_hitl_demo.py   （无需任何 API Key）

工作台入口：build_graph() / build_guarded() 返回编译后的图（普通版 / 带刹车版），
供 ../workbench 直接 import 复用；每次调用都创建全新 MemorySaver，互不串台。
"""
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver


class State(TypedDict):
    messages: Annotated[list, add_messages]


def propose(state: State):
    """实习生节点：生成一条带 tool_call_id 的敏感工具调用请求。"""
    return {
        "messages": [
            AIMessage(
                content="我准备清空购物车，请审批。",
                tool_calls=[{
                    "name": "clear_cart",
                    "args": {},
                    "id": "call_clear_cart_001",
                    "type": "tool_call",
                }],
            )
        ]
    }


def sensitive_tool(state: State):
    """敏感操作节点：执行后必须用匹配的 tool_call_id 回一条 ToolMessage。"""
    tool_call = state["messages"][-1].tool_calls[0]
    return {
        "messages": [ToolMessage(
            content="敏感操作已执行：购物车已清空。",
            tool_call_id=tool_call["id"],
        )]
    }


def summarize(state: State):
    """把批准或驳回的工具回执整理成用户能看懂的最终答复。"""
    result = state["messages"][-1].content
    return {"messages": [("assistant", f"审批流程结束：{result}")]}


def _builder():
    builder = StateGraph(State)
    builder.add_node("propose", propose)
    builder.add_node("sensitive_tool", sensitive_tool)
    builder.add_node("summarize", summarize)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", "sensitive_tool")
    builder.add_edge("sensitive_tool", "summarize")
    builder.add_edge("summarize", END)
    return builder


def build_graph():
    """演示一：只挂 Checkpointer 的普通版（每次全新存档，防状态串台）"""
    return _builder().compile(checkpointer=MemorySaver())


def build_guarded():
    """演示二：静态 interrupt_before 拦截版（用于理解存档与恢复）。"""
    return _builder().compile(checkpointer=MemorySaver(), interrupt_before=["sensitive_tool"])


def reject_pending(graph, config: dict, reason: str):
    """正式驳回：补齐 ToolMessage，伪装成敏感工具节点已返回，再从下一节点继续。

    `update_state(..., as_node="sensitive_tool")` 不会执行真正的敏感节点；它只是告诉
    LangGraph：“把这条拒绝回执当成 sensitive_tool 的输出”。这样 AIMessage 中的每个
    tool_call 都有配对的 ToolMessage，消息历史保持合法。
    """
    snap = graph.get_state(config)
    tool_calls = snap.values["messages"][-1].tool_calls
    rejections = [
        ToolMessage(
            content=f"工具调用被用户拒绝。原因：{reason}",
            tool_call_id=call["id"],
        )
        for call in tool_calls
    ]
    fork_config = graph.update_state(
        config,
        {"messages": rejections},
        as_node="sensitive_tool",
    )
    return graph.invoke(None, fork_config)


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

    # 老板不同意：用 update_state 写入匹配 tool_call_id 的拒绝回执，跳过真正工具节点。
    rejected = reject_pending(guarded, config2, "这是演示账号，不能清空购物车")
    print("驳回后最后一条消息：", rejected["messages"][-1].content)

    # 再开一个线程演示批准：不传新消息，直接传 None，从同一个存档继续。
    config3 = {"configurable": {"thread_id": "user_wangwu_789"}}
    guarded.invoke({"messages": [("user", "帮我清空购物车")]}, config3)
    for _ in guarded.stream(None, config3):
        pass
    state_after = guarded.get_state(config3)
    print("批准后执行完毕，最后一条消息：", state_after.values["messages"][-1].content)


if __name__ == "__main__":
    main()
