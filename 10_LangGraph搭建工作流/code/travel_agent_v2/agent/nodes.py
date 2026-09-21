"""图上的小零件：入口节点工厂 + 出图。

放在 agent 层而不是基础设施层：这两个函数都**认识 State 的形状**（入口节点要往
`dialog_state` 压栈、要补一条带 tool_call_id 的 ToolMessage），换图就得跟着改，
所以它们是智能体的一部分，不是通用工具。
"""
from __future__ import annotations

from typing import Callable

from langchain_core.messages import ToolMessage

from infra.logging import log


def create_entry_node(assistant_name: str, new_dialog_state: str) -> Callable:
    """造一个「专员入口节点」。

    主助理用 handoff 工具点名之后，控制权先落到这个入口节点：它替专员回一条
    ToolMessage（把 tool_call 对上账，历史里不留悬空调用），并把专员名压进
    `dialog_state` 栈——之后用户再说话，`route_to_workflow` 就能把话送回这位专员。

    :param assistant_name: 专员的名字（写进系统口吻的提示里，用户看不到这些名字）
    :param new_dialog_state: 要压进 dialog_state 栈的状态名（就是图里的节点名）
    :return: 一个符合 LangGraph 节点签名的函数，接收 state、返回状态增量
    """

    def entry_node(state: dict) -> dict:
        """入口节点本体。

        :param state: 当前状态，`messages[-1]` 是主助理那条带 handoff tool_call 的消息
        :return: {"messages": [补齐的 ToolMessage], "dialog_state": 新状态名}
        """
        # 取最后一条消息里的工具调用 ID：ToolMessage 必须和它配对，否则消息序列不合法
        tool_call_id = state["messages"][-1].tool_calls[0]["id"]

        return {
            "messages": [
                ToolMessage(
                    content=f"现在助手是{assistant_name}。请回顾上述主助理与用户之间的对话。"
                            f"用户的意图尚未满足。使用提供的工具协助用户。记住，您是{assistant_name}，"
                            "并且预订、更新或其他操作未完成，直到成功调用了适当的工具。"
                            "如果用户改变主意或需要帮助进行其他任务，请调用CompleteOrEscalate函数让主要的主助理接管。"
                            "不要提及你是谁——仅作为助理的代理。",
                    tool_call_id=tool_call_id,
                )
            ],
            "dialog_state": new_dialog_state,
        }

    return entry_node


def draw_graph(graph, file_name: str) -> None:
    """把编译好的图导成一张 mermaid PNG（调试用，不是运行期依赖）。

    :param graph: `compile()` 之后的图对象
    :param file_name: 输出文件名（如 "graph4.png"），相对当前工作目录
    """
    try:
        mermaid_code = graph.get_graph().draw_mermaid_png()
        with open(file_name, "wb") as f:
            f.write(mermaid_code)
    except Exception as e:      # noqa: BLE001 —— 画图要额外依赖，画不出来不该影响主流程
        log.exception(e)
