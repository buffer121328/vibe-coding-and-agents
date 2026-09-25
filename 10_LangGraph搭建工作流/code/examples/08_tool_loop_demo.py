"""08 工具调用循环与预构建组件 —— 最小可运行示例
对应文档：10_LangGraph搭建工作流/08_工具调用循环与预构建组件.md
运行：python 08_tool_loop_demo.py          （无需任何 API Key：用 langchain-core 内置假模型模拟 LLM）
      python 08_tool_loop_demo.py --real   （换成真模型：先 uv sync --extra real，再按 .env.example 填 OPENAI_*）

演示完整的 ReAct 闭环：模型 → 工具 → 模型。
假模型按剧本先发出 tool_calls，ToolNode 执行后把 ToolMessage 塞回，
模型再根据工具结果给出最终答复。

工作台入口：build_graph() 返回编译后的图，供 ../workbench 直接 import 复用。
每次调用都创建全新剧本模型，保证多次运行互不串台。
"""
import sys

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition


FLIGHT_CATALOG = {
    "东京": [
        "CA-1801 08:40 ￥1280 准点率 92%",
        "NH-955 13:15 ￥1560 准点率 95%",
        "MU-523 19:05 ￥990 准点率 88%",
    ],
    "大阪": [
        "CZ-385 09:20 ￥880",
        "HO-1337 16:40 ￥1120",
    ],
}


@tool
def search_flights(destination: str) -> str:
    """查询指定目的地的航班列表，返回班次、时刻与价格。"""
    flights = FLIGHT_CATALOG.get(destination)
    if not flights:
        return f"{destination} 暂无直飞，需要中转。可尝试相邻枢纽。"
    return f"{destination} 有 {len(flights)} 个航班：" + " / ".join(flights)


def make_scripted_llm() -> FakeMessagesListChatModel:
    """假模型工厂：按剧本依次返回两条 AIMessage。

    第一条带 tool_calls，触发 tools_condition 走向 ToolNode；
    第二条是看到工具结果之后的最终回答。
    真模型见下面的 make_real_llm()：换掉的只有这一个对象，图的其余部分一字不改。
    """
    return FakeMessagesListChatModel(responses=[
        AIMessage(
            content="我先查一下东京的航班时刻和价格。",
            tool_calls=[{
                "name": "search_flights",
                "args": {"destination": "东京"},
                "id": "call_1",
            }],
        ),
        AIMessage(
            content=(
                "为您查到东京的 3 个航班。最便宜的是 MU-523（19:05，￥990），"
                "准点率最高的是 NH-955。需要帮您锁定哪一班？"
            )
        ),
    ])


def make_real_llm():
    """真模型：OpenAI 兼容端点，读 .env 里的 OPENAI_API_KEY / OPENAI_MODEL_NAME / OPENAI_API_BASE。

    langchain-openai 和 python-dotenv 不在默认依赖里（默认零 Key），要先 `uv sync --extra real`。
    """
    import os

    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI

    load_dotenv()
    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL_NAME"],
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_API_BASE"],
        temperature=0,
    )
    return llm.bind_tools([search_flights])


def build_graph(llm=None):
    """装配并编译本节演示图。

    ``llm`` 不传就在工厂内新建剧本模型（防多次运行串台）；传入的是已经 bind_tools 过的真模型。
    """
    model = llm or make_scripted_llm()

    def call_model(state: MessagesState):
        """模型节点收到的是整份 State，必须先取出 messages 再调用。"""
        return {"messages": [model.invoke(state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("assistant", call_model)
    builder.add_node("tools", ToolNode([search_flights], handle_tool_errors=True))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", tools_condition)
    builder.add_edge("tools", "assistant")
    return builder.compile()


graph = build_graph()


def main():
    app = build_graph(make_real_llm()) if "--real" in sys.argv else graph
    result = app.invoke({"messages": [("user", "帮我查一下去东京的航班")]})
    print("== 消息流水线（Human → AI.tool_calls → Tool → AI）==")
    for msg in result["messages"]:
        extra = ""
        if getattr(msg, "tool_calls", None):
            extra = f"  tool_calls={msg.tool_calls}"
        print(f"[{msg.__class__.__name__}] {getattr(msg, 'content', '')}{extra}")


if __name__ == "__main__":
    main()
