import operator
import sqlite3
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from langgraph.types import Command, RetryPolicy, Send, interrupt

from agent.specialists import update_flight_runnable, update_flight_sensitive_tools, update_flight_safe_tools, \
    book_car_rental_runnable, book_car_rental_safe_tools, book_car_rental_sensitive_tools, book_hotel_runnable, \
    book_hotel_safe_tools, book_hotel_sensitive_tools, book_excursion_runnable, book_excursion_safe_tools, \
    book_excursion_sensitive_tools
from agent.primary import DeskAssistant
from agent.models import CompleteOrEscalate
from agent.nodes import create_entry_node
from agent.state import State
from tools.node import create_tool_node_with_fallback
from tools.cars import search_car_rentals
from tools.excursions import search_trip_recommendations
from tools.flights import search_flights
from tools.hotels import search_hotels


def create_sensitive_approval_gate(domain: str, approved_node: str, return_node: str):
    """为敏感工具池创建动态审批节点。

    节点先把工具名、参数和 tool_call_id 打成 JSON 数据包交给 `interrupt()`。
    - 批准：Command 跳到真正的 ToolNode；
    - 驳回：为每个工具调用补齐匹配的 ToolMessage，再回业务助理重新规划。

    这样敏感工具只会在明确批准后执行，也不会留下“AI 发了 tool_call、历史里却没有
    ToolMessage”的残缺消息。
    """
    def approval_gate(state: State) -> Command:
        """审批闸门节点（闭包，一个语义域一个）。

        把这一跳要执行的敏感工具打包丢给 `interrupt()`，等人签字：

        :param state: 当前状态；`messages[-1]` 是专员那条要执行写操作的 AI 消息
        :return: 批准则 `Command(goto=<真正的工具节点>)`；驳回则补齐每个 tool_call
                 对应的 ToolMessage 再回专员重规划——历史里不留「有调用没回执」的残缺
        """
        tool_calls = state["messages"][-1].tool_calls
        decision = interrupt({
            "kind": "tool_approval",
            "domain": domain,
            "tool_calls": [
                {"id": call["id"], "name": call["name"], "args": call.get("args", {})}
                for call in tool_calls
            ],
        })
        approved = decision if isinstance(decision, bool) else bool(decision.get("approved"))
        if approved:
            return Command(goto=approved_node)

        reason = "用户拒绝了该操作"
        if isinstance(decision, dict) and decision.get("reason"):
            reason = str(decision["reason"])
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"工具调用被用户拒绝。原因：{reason}。请根据意见重新规划。",
                        tool_call_id=call["id"],
                    )
                    for call in tool_calls
                ]
            },
            goto=return_node,
        )

    return approval_gate


# ==================== 专员装配：一张注册表 + 一个工厂 ====================
#
# 四个专员（机票 / 酒店 / 租车 / 门票）是**同一张图**：入口节点 → 业务助理 →
# （安全工具 | 审批闸门 → 敏感工具）→ 回到业务助理。差别只有名字、提示词、工具池，
# 以及一个结构开关：平铺在父图里，还是独立 compile() 成真子图（第 12 节要对比这两条路）。
#
# 所以装配写一遍就够了。以前是四段复制粘贴，加一个专员要改六处名字。
SPECIALISTS: dict[str, dict] = {
    "update_flight": {
        "key": "update_flight",
        "entry_title": "Flight Updates & Booking Assistant",
        "runnable": update_flight_runnable,
        "safe": update_flight_safe_tools,
        "sensitive": update_flight_sensitive_tools,
        "domain": "航班退改签",
        "subgraph": False,
    },
    "book_hotel": {
        "key": "book_hotel",
        "entry_title": "酒店预订助理",
        "runnable": book_hotel_runnable,
        "safe": book_hotel_safe_tools,
        "sensitive": book_hotel_sensitive_tools,
        "domain": "酒店预订与变更",
        "subgraph": False,
    },
    "book_car_rental": {
        "key": "book_car_rental",
        "entry_title": "Car Rental Assistant",
        "runnable": book_car_rental_runnable,
        "safe": book_car_rental_safe_tools,
        "sensitive": book_car_rental_sensitive_tools,
        "domain": "租车预订与变更",
        "subgraph": True,          # 唯一一个真子图（独立编译，中断向上穿透）
    },
    "book_excursion": {
        "key": "book_excursion",
        "entry_title": "旅行推荐助理",
        "runnable": book_excursion_runnable,
        "safe": book_excursion_safe_tools,
        "sensitive": book_excursion_sensitive_tools,
        "domain": "景点门票与游览",
        "subgraph": False,
    },
}


def _add_specialist(builder: StateGraph, spec: dict) -> StateGraph:
    """把一名专员接进图里（子图与平铺共用这一段）。

    两种形态的差别只有两处，都在下面标了：
    - 子图自己带 START 边，收工时回到 END（由父图的 leave_skill 弹栈）；
    - 平铺的专员直接回 leave_skill。
    """
    key, safe, sensitive = spec["key"], spec["safe"], spec["sensitive"]

    builder.add_node(f"enter_{key}", create_entry_node(spec["entry_title"], key))
    builder.add_node(key, DeskAssistant(spec["runnable"]))
    builder.add_node(f"{key}_safe_tools", create_tool_node_with_fallback(safe))
    builder.add_node(f"{key}_sensitive_tools", create_tool_node_with_fallback(sensitive))
    builder.add_node(
        f"{key}_approval",
        create_sensitive_approval_gate(
            spec["domain"],
            approved_node=f"{key}_sensitive_tools",
            return_node=key,
        ),
    )
    if spec["subgraph"]:
        builder.add_edge(START, f"enter_{key}")     # 子图自己的入口
    builder.add_edge(f"enter_{key}", key)

    def route_specialist(state: dict) -> str:
        """业务助理下一步去哪：交还主助理 / 查安全工具 / 先过审批闸门。"""
        if tools_condition(state) == END:
            return END
        tool_calls = state["messages"][-1].tool_calls
        if any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls):
            # 平铺：回主助理；子图：收工回 END，由父图的 leave_skill 接手
            return END if spec["subgraph"] else "leave_skill"
        safe_names = [t.name for t in safe]
        if all(tc["name"] in safe_names for tc in tool_calls):
            return f"{key}_safe_tools"
        return f"{key}_approval"

    builder.add_conditional_edges(
        key,
        route_specialist,
        [f"{key}_safe_tools", f"{key}_approval", END if spec["subgraph"] else "leave_skill", END],
    )
    builder.add_edge(f"{key}_safe_tools", key)
    builder.add_edge(f"{key}_sensitive_tools", key)
    return builder


def build_flight_graph(builder: StateGraph) -> StateGraph:
    """航班专员 + 四个平铺专员共用的「交还主助理」出口。"""
    builder = _add_specialist(builder, SPECIALISTS["update_flight"])

    # 此节点将用于所有平铺子助理的退出（装一次，其余三个共用）
    def pop_dialog_state(state: dict) -> dict:
        """
        弹出对话栈并返回主助理。
        这使得完整的图可以明确跟踪对话流，并根据需要委托控制给特定的子图。
        :param state: 当前对话状态字典
        :return: 包含新的对话状态和消息的字典
        """
        messages = []
        if state["messages"][-1].tool_calls:
            # 注意：目前不处理LLM同时执行多个工具调用的情况
            messages.append(
                ToolMessage(
                    content="正在恢复与主助理的对话。请回顾之前的对话并根据需要协助用户。",
                    tool_call_id=state["messages"][-1].tool_calls[0]["id"],
                )
            )
        return {
            "dialog_state": "pop",  # 更新对话状态为弹出
            "messages": messages,  # 返回消息列表
        }

    builder.add_node("leave_skill", pop_dialog_state)
    builder.add_edge("leave_skill", "primary_assistant")
    return builder


def build_car_subgraph():
    """租车专员的「真子图」（对应第 12 节）：独立编译，内部审批中断向上穿透。

    与其他三个平铺在父图里的专员不同，父图只看到 `book_car_rental` 一个节点，
    子图内部走到 END 后由父图的 leave_skill 边负责弹栈交还主助理。
    """
    builder = StateGraph(State)
    builder = _add_specialist(builder, SPECIALISTS["book_car_rental"])
    # 动态 interrupt() 在审批节点内部触发；父图的 Checkpointer 会自动透传给子图。
    return builder.compile()


def builder_hotel_graph(builder: StateGraph) -> StateGraph:
    """酒店专员（平铺）。"""
    return _add_specialist(builder, SPECIALISTS["book_hotel"])


def builder_excursion_graph(builder: StateGraph) -> StateGraph:
    """景点门票专员（平铺）。"""
    return _add_specialist(builder, SPECIALISTS["book_excursion"])


# ==================== 多业务并行比价子图（对应第 04 节 Send） ====================

class QuoteState(TypedDict):
    """比价子图的私有状态：messages 与父图共享，quotes 仅在子图内部流动。"""
    messages: Annotated[list[AnyMessage], add_messages]
    quotes: Annotated[list, operator.add]   # 各路查询结果用加法 reducer 汇聚


# 参与比价的业务线：名称 -> 对应的只读查询工具
QUOTE_BUSINESSES = {
    "机票": search_flights,
    "酒店": search_hotels,
    "租车": search_car_rentals,
    "游览": search_trip_recommendations,
}


def _peek(row: dict) -> str:
    """从查询结果里挑一个人类可读的字段做示例展示"""
    for key in ("name", "airline", "trip_name", "location"):
        if key in row and row[key]:
            return str(row[key])
    return str(row)[:40]


def quote_worker(state: dict) -> dict:
    """Send 派发的并行实例：每个实例只看到自己的私有状态 {"biz": ...}。

    这里是只读查询（幂等），所以放心挂自动重试；
    敏感的“写”操作节点千万不要挂重试，避免重复下单。
    """
    biz = state["biz"]
    rows = QUOTE_BUSINESSES[biz].invoke({})
    sample = f"，例如「{_peek(rows[0])}」" if rows else ""
    return {"quotes": [{"biz": biz, "count": len(rows), "sample": sample}]}


def dispatch_quotes(state: QuoteState) -> list[Send]:
    """Send 路由函数（不是节点）：按业务线数量动态派发 N 个并行实例"""
    return [Send("quote_worker", {"biz": biz}) for biz in QUOTE_BUSINESSES]


def aggregate_quotes(state: QuoteState) -> dict:
    """汇合屏障之后的汇总节点：把四路报价整理成一段话回给用户"""
    lines = [f"{q['biz']} {q['count']} 条{q['sample']}" for q in state["quotes"]]
    summary = "已同时查完四类行情：" + "；".join(lines) + "。需要深入了解哪一类？"
    return {"messages": [AIMessage(content=summary)]}


def build_multi_quote_subgraph():
    """多业务并行比价子图：用 Send 动态扇出四路查询（Map），再在 aggregate 汇总（Reduce）。"""
    builder = StateGraph(QuoteState)
    builder.add_node("entry", lambda state: {})   # 占位入口：真正的动态派发在下面的条件边
    # worker 是幂等的只读查询，挂自动重试是安全的；真实项目里 RetryPolicy 保护的是
    # 远程 API 的偶发超时/限流这类瞬时故障（见第 11 节）
    builder.add_node(
        "quote_worker",
        quote_worker,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=(TimeoutError, sqlite3.OperationalError)),
    )
    builder.add_node("aggregate", aggregate_quotes)
    builder.add_edge(START, "entry")
    builder.add_conditional_edges("entry", dispatch_quotes)
    builder.add_edge("quote_worker", "aggregate")   # 隐式屏障：等所有实例完成
    builder.add_edge("aggregate", END)
    return builder.compile()
