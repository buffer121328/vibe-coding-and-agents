import uuid

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_store
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.store.base import BaseStore
from langgraph.types import Command, RetryPolicy

from agent.primary import DeskAssistant, assistant_runnable, primary_assistant_tools
from agent.models import ToFlightBookingAssistant, ToBookCarRental, ToHotelBookingAssistant, \
    ToBookExcursion, ToMultiQuote
from agent.graph import build_flight_graph, builder_hotel_graph, build_car_subgraph, \
    build_multi_quote_subgraph, builder_excursion_graph
from memory.store import store
from tools.flights import fetch_user_flight_information
from infra.logging import log
from agent.state import State
from infra.biz_db import update_dates
from tools.node import create_tool_node_with_fallback, _print_event


def _profile_text(config: RunnableConfig, store_: BaseStore | None = None) -> str:
    """从 Store 里读这名旅客的会员档案，拼成几行字。

    命名空间和 tools/preferences.py 用的是同一套（一人一个抽屉），所以模型
    自动读到的和它自己调 recall_preferences 拿到的，是同一份东西。
    读不到就算了——档案读失败不该拦住对话。

    参数:
        config: 这次请求的配置，靠它拿 passenger_id。
        store_: 长期记忆。节点里不传，默认走 get_store() 从运行时上下文取；
            离开图的上下文（CLI、测试）可以显式传进来，用同一份逻辑验证。
    """
    try:
        store_ = store_ or get_store()
        pid = (config.get("configurable") or {}).get("passenger_id") or ""
        if store_ is None or not pid:
            return ""
        items = store_.search((f"pref_{pid}",))
        return "\n".join(f"- {item.key}: {item.value.get('value')}" for item in items)
    except Exception:      # noqa: BLE001 —— 读档案失败不影响这一轮对话
        log.exception("读取会员档案失败")
        return ""


def build_graph(checkpointer=None):
    """装配总图：主助理 + 四个业务助理（其中租车为真子图）+ 并行比价子图。

    - Checkpointer：会话内存档（动态 HITL 靠它），生产环境换 PostgresSaver；
    - Store：跨会话的长期记忆（用户偏好档案），自动透传给所有子图与工具。
    """
    builder = StateGraph(State)

    # 新增：fetch_user_info节点首先运行，这意味着我们的助手可以在不采取任何行动的情况下看到用户的航班信息
    def get_user_info(state: State, config: RunnableConfig):
        """
        获取用户的航班信息，并把他的会员档案一并交给模型。

        档案以前只有模型主动调 recall_preferences 才读得到——模型想不起来，
        偏好就白存了。这里每轮开局顺手读一遍：个性化变成结构性的（和航班信息
        一起写在提示词里），不赌模型自觉，还省掉一次工具往返。

        参数:
            state (State): 当前状态字典。
            config (RunnableConfig): 里面带着这次请求的 passenger_id。
        返回:
            dict: 包含用户信息的新状态字典。
        """
        flights = fetch_user_flight_information.invoke({})
        profile = _profile_text(config)
        info = f"{flights}\n\n会员档案（用户自己说过的长期偏好）：\n{profile}" if profile else flights
        return {"user_info": info}

    # 该节点是幂等的只读查询，挂自动重试是安全的（真实项目里保护的是不稳定的远程接口）
    builder.add_node(
        'fetch_user_info', get_user_info,
        retry_policy=RetryPolicy(max_attempts=3, retry_on=(TimeoutError,)),
    )
    builder.add_edge(START, 'fetch_user_info')

    # 添加 业务助理 的工作流：机票 / 酒店为平铺结构
    builder = build_flight_graph(builder)
    builder = builder_hotel_graph(builder)
    # 租车助理为“真子图”：独立编译后作为单个节点接入，内部结构对外封装（见 12 节）
    builder.add_node('book_car_rental', build_car_subgraph())
    builder.add_edge('book_car_rental', 'leave_skill')   # 子图收工 -> 弹栈交还主助理
    builder = builder_excursion_graph(builder)

    # 多业务并行比价子图：Send 同时扇出四路查询（见 04 节）
    builder.add_node('multi_quote', build_multi_quote_subgraph())
    builder.add_edge('multi_quote', 'leave_skill')

    # 添加主助理
    builder.add_node('primary_assistant', DeskAssistant(assistant_runnable))
    builder.add_node(
        "primary_assistant_tools", create_tool_node_with_fallback(primary_assistant_tools)  # 主助理工具节点，包含各种工具
    )


    def route_primary_assistant(state: dict):
        """
        根据当前状态 判断路由到 子助手节点。
        :param state: 当前对话状态字典
        :return: 下一步应跳转到的节点名
        """
        route = tools_condition(state)  # 判断下一步的方向
        if route == END:
            return END  # 如果结束条件满足，则返回END
        tool_calls = state["messages"][-1].tool_calls  # 获取最后一条消息中的工具调用
        if tool_calls:
            if tool_calls[0]["name"] == ToFlightBookingAssistant.__name__:
                return "enter_update_flight"  # 跳转至航班预订入口节点
            elif tool_calls[0]["name"] == ToBookCarRental.__name__:
                return "book_car_rental"  # 直达租车子图（入口节点在子图内部）
            elif tool_calls[0]["name"] == ToHotelBookingAssistant.__name__:
                return "enter_book_hotel"  # 跳转至酒店预订入口节点
            elif tool_calls[0]["name"] == ToBookExcursion.__name__:
                return "enter_book_excursion"  # 跳转至游览预订入口节点
            elif tool_calls[0]["name"] == ToMultiQuote.__name__:
                return "multi_quote"  # 进入多业务并行比价子图
            return "primary_assistant_tools"  # 否则跳转至主助理工具节点
        raise ValueError("无效的路由")  # 如果没有找到合适的工具调用，抛出异常


    builder.add_conditional_edges(
        'primary_assistant',
        route_primary_assistant,
        [
            "enter_update_flight",  # 航班 子助手的入口节点
            "book_car_rental",  # 租车 子助手（真子图节点）
            "enter_book_hotel",   # 酒店 子助手的入口节点
            "enter_book_excursion",   # 旅游景点 子助手的入口节点
            "multi_quote",   # 并行比价 子图
            "primary_assistant_tools",  # 主助手的工具： 全网搜索工具，查询企业政策的工具
            END,
        ]
    )

    builder.add_edge('primary_assistant_tools', 'primary_assistant')


    # 每个委托的工作流可以直接响应用户。当用户响应时，我们希望返回到当前激活的工作流
    def route_to_workflow(state: dict) -> str:
        """
        如果我们在一个委托的状态中，直接路由到相应的助理。
        :param state: 当前对话状态字典
        :return: 应跳转到的节点名
        """
        dialog_state = state.get("dialog_state")
        if not dialog_state:
            return "primary_assistant"  # 如果没有对话状态，返回主助理
        return dialog_state[-1]  # 返回最后一个对话状态


    builder.add_conditional_edges("fetch_user_info", route_to_workflow)  # 根据获取用户信息进行路由

    return builder.compile(
        # CLI（python main.py）没传存档就用内存版，关掉就没了；
        # 浏览器工作台走 web/runtime/hub.py，会把 SqliteSaver 传进来。
        checkpointer=checkpointer or MemorySaver(),
        store=store,  # 长期记忆：自动透传给所有子图与 InjectedStore 工具
    )


def main():
    # 每次测试的时候：保证数据库是全新的，保证，时间也是最近的时间
    """终端对话入口：起一张图，循环读输入、打印回答、处理挂起。

    浏览器那条路走 `web/app.py`；这个函数是给「不想开浏览器」的时候用的。

    :return: 无
    """
    update_dates()

    graph = build_graph()
    # 想看流程图：from agent.nodes import draw_graph; draw_graph(graph, "graph4.png")

    session_id = str(uuid.uuid4())

    # 配置参数，包含乘客ID和线程ID
    config = {
        "configurable": {
            # passenger_id用于我们的航班工具，以获取用户的航班信息
            "passenger_id": "3442 587242",
            # 检查点由session_id访问
            "thread_id": session_id,
        }
    }

    _printed = set()  # set集合，避免重复打印

    # 执行工作流
    while True:
        question = input('用户：')
        if question.lower() in ['q', 'exit', 'quit']:
            print('对话结束，拜拜！')
            break
        else:
            events = graph.stream({'messages': ('user', question)}, config, stream_mode='values')
            # 打印消息
            for event in events:
                _print_event(event, _printed)

            current_state = graph.get_state(config)
            if current_state.next:
                user_input = input(
                    "您是否批准上述操作？输入'y'继续；否则，请说明您请求的更改。\n"
                )
                if user_input.strip().lower() == "y":
                    # 把结构化批准结果送回 interrupt()，敏感工具随后才会执行。
                    events = graph.stream(
                        Command(resume={"approved": True}),
                        config,
                        stream_mode='values',
                    )
                    # 打印消息
                    for event in events:
                        _print_event(event, _printed)
                else:
                    # interrupt() 内的审批节点会为每个 tool_call 补齐拒绝回执并让助理重规划。
                    result = graph.stream(
                        Command(resume={"approved": False, "reason": user_input}),
                        config,
                        stream_mode='values',
                    )
                    # 打印事件详情
                    for event in result:
                        _print_event(event, _printed)


if __name__ == "__main__":
    main()
