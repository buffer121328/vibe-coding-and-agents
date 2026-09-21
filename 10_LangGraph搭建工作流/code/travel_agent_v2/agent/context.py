"""送进模型的上下文窗口：只给最近一段，存档里保持全量。

**存什么和送什么是两件事。** Checkpointer 里的对话存档是完整的——TimeTravel、
审计、订单对账都靠它；但没必要每次都把几十轮历史塞进模型：慢、贵，聊久了还会顶到
上下文上限。这个模块只管「送什么」。

策略很朴素：只保留最近的 N 条消息，并且**从一条人类发言开始**。从人类发言切是关键，
切在别处会把「工具调用 / 工具回执」拆散，模型看到孤儿 ToolMessage 会报错或胡说。

> 为什么不用 LangChain 的 `trim_messages`：它按 token 预算裁，预算不够满足
> `start_on="human"` 时**会返回空列表**——模型拿到空消息等于当场失忆（实测过，
> 一个只剩工具消息的长尾就能触发）。这里要的是一个有下界的窗口：宁可多给几条，
> 也绝不把上下文清空。
"""
from __future__ import annotations

# 窗口大小按「消息条数」算，不引 tiktoken：教学项目不需要精确 token 数，
# 条数上限足够挡住无界增长，行为也好预测。
MODEL_WINDOW = 24


def window(messages: list, limit: int = MODEL_WINDOW) -> list:
    """裁出要喂给模型的那一段（永远是原列表的一个连续切片，且不为空）。

    :param messages: 完整历史（来自 State["messages"]）
    :param limit: 最多保留多少条
    :return: 从某条人类发言开始、到最新一条为止的切片
    """
    if not messages:
        return list(messages)
    if len(messages) <= limit:
        return list(messages)

    tail = list(messages[-limit:])
    for idx, msg in enumerate(tail):
        if getattr(msg, "type", "") == "human":
            return tail[idx:]

    # 尾巴这一段里没有人类发言（比如一连串工具循环）：往前找最近的一条，
    # 从那里切开——工具调用和它的回执才能成对出现。
    for idx in range(len(messages) - limit - 1, -1, -1):
        if getattr(messages[idx], "type", "") == "human":
            return list(messages[idx:])

    # 整段历史里一句人话都没有（理论上不会发生）：原样给最近的 N 条
    return tail
