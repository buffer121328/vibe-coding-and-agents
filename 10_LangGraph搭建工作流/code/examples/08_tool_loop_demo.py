"""08 工具调用循环与预构建组件 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/08_工具调用循环与预构建组件.md
运行：python 08_tool_loop_demo.py   （无需任何 API Key：用 langchain-core 内置假模型模拟 LLM）

演示完整的 ReAct 闭环：模型 -> 工具 -> 模型。

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
每次调用都创建全新剧本模型，保证多次运行互不串台。
"""
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition


@tool
def search_flights(destination: str) -> str:
    """查询指定目的地的航班"""
    return f"{destination} 有 3 个航班：CA-1801 / CA-1802 / MU-5137"


def make_scripted_llm() -> FakeMessagesListChatModel:
    """假模型工厂：按剧本依次返回两条 AIMessage（工作台每次运行领一张新剧本）。
    真实项目里换成 ChatOpenAI(...).bind_tools([...]) 即可，图的其余部分一字不改。"""
    return FakeMessagesListChatModel(responses=[
        AIMessage(
            content="",
            tool_calls=[{"name": "search_flights", "args": {"destination": "东京"}, "id": "call_1"}],
        ),
        AIMessage(content="为您查到东京的 3 个航班，需要帮您预订哪一个？"),
    ])


def build_graph():
    """装配并编译本节演示图；剧本模型在工厂内创建，防多次运行串台"""
    scripted_llm = make_scripted_llm()

    def call_model(state: MessagesState):
        """专家节点：模型收到的是整个 State，所以包一层只把消息列表喂给它"""
        return {"messages": [scripted_llm.invoke(state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("assistant", call_model)                        # 1. 专家节点
    builder.add_node("tools", ToolNode([search_flights]))            # 2. 跑腿助理节点
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", tools_condition)      # 3. 指路牌
    builder.add_edge("tools", "assistant")                           # 结果递回去，形成闭环
    return builder.compile()


graph = build_graph()


def main():
    result = graph.invoke({"messages": [("user", "帮我查一下去东京的航班")]})
    for msg in result["messages"]:
        print(f"[{msg.__class__.__name__}] {getattr(msg, 'content', '') or msg.tool_calls}")


if __name__ == "__main__":
    main()
