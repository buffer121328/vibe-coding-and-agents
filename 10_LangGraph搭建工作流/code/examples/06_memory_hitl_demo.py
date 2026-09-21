"""06 Memory 与 Human-in-the-loop —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/06_Memory与Human-in-the-loop.md
运行：python 06_memory_hitl_demo.py   （无需任何 API Key）

工作台入口：build_graph() / build_guarded() 返回编译后的图（普通版 / 带刹车版），
供 ../workbench 直接 import 复用；每次调用都创建全新 MemorySaver，互不串台。

演示两条路径：
1. 同一 thread_id 续跑，Checkpointer 记住上一轮消息；
2. interrupt_before 在敏感工具前暂停；批准传 None 续跑，驳回用 update_state 补 ToolMessage。
"""
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver


class State(TypedDict):
    messages: Annotated[list, add_messages]


CART_TOOL_ID = "call_clear_cart_001"


def propose(state: State):
    """模型节点的替身：生成一条带 tool_call_id 的敏感工具调用，等待审批。"""
    user_text = state["messages"][-1].content
    return {
        "messages": [
            AIMessage(
                content=(
                    f"收到「{user_text}」。购物车里有 3 件商品，合计 ￥1280。"
                    "清空后无法恢复，需要你确认后我才会调用 clear_cart。"
                ),
                tool_calls=[{
                    "name": "clear_cart",
                    "args": {"item_count": 3, "total": 1280},
                    "id": CART_TOOL_ID,
                    "type": "tool_call",
                }],
            )
        ]
    }


def sensitive_tool(state: State):
    """真正执行清空。正式驳回时这个节点不会跑到，而是被 update_state(as_node=...) 顶替。"""
    tool_call = state["messages"][-1].tool_calls[0]
    args = tool_call.get("args") or {}
    return {
        "messages": [ToolMessage(
            content=(
                "敏感操作已执行：已清空购物车 "
                f"（原 {args.get('item_count', '?')} 件，合计 ￥{args.get('total', '?')}）。"
            ),
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
    return _builder().compile(
        checkpointer=MemorySaver(),
        interrupt_before=["sensitive_tool"],
    )


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
    print("== 演示一：同一 thread_id 的短期记忆 ==")
    graph = build_graph()
    config = {"configurable": {"thread_id": "user_zhangsan_123"}}
    graph.invoke({"messages": [("user", "帮我清空购物车")]}, config)
    snap = graph.get_state(config)
    print("存档中的最后一条消息：", snap.values["messages"][-1].content)

    print("\n== 演示二：interrupt_before 拦截后驳回 ==")
    guarded = build_guarded()
    config2 = {"configurable": {"thread_id": "user_lisi_456"}}
    guarded.invoke({"messages": [("user", "帮我清空购物车")]}, config2)
    state_now = guarded.get_state(config2)
    print("程序停在了：", state_now.next, "（等待审批）")
    rejected = reject_pending(guarded, config2, "这是演示账号，不能清空购物车")
    print("驳回后最后一条消息：", rejected["messages"][-1].content)

    print("\n== 演示三：同一套刹车，批准后续跑 ==")
    config3 = {"configurable": {"thread_id": "user_wangwu_789"}}
    guarded.invoke({"messages": [("user", "帮我清空购物车")]}, config3)
    for _ in guarded.stream(None, config3):
        pass
    state_after = guarded.get_state(config3)
    print("批准后最后一条消息：", state_after.values["messages"][-1].content)


if __name__ == "__main__":
    main()
