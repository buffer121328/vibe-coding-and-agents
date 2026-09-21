"""用户偏好工具：让主助理具备“记住 / 回忆”长期偏好的能力。

对应文档：第 10 章 10_长期记忆与TimeTravel.md
两个工具都不直接接触 Store 实例——store 由 LangGraph 在编译时挂到图上，
运行时通过 InjectedStore 注解自动注入；passenger_id 则从 RunnableConfig 读取。
"""
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore


def _namespace(config: RunnableConfig) -> tuple:
    """每个乘客一个档案抽屉：("pref_<passenger_id>",)"""
    passenger_id = config["configurable"]["passenger_id"]
    return (f"pref_{passenger_id}",)


@tool
def save_preference(
    key: str,
    value: str,
    store: Annotated[BaseStore, InjectedStore],
    config: RunnableConfig,
) -> str:
    """记住用户的长期偏好（如座位偏好、常旅客号、房型喜好）。
    当用户表达"记住我喜欢……"这类长期有效的偏好时调用此工具。"""
    store.put(_namespace(config), key, {"value": value})
    return f"已记住您的偏好：{key} = {value}"


@tool
def recall_preferences(
    store: Annotated[BaseStore, InjectedStore],
    config: RunnableConfig,
) -> str:
    """回忆用户的长期偏好档案。
    在为用户做推荐或预订之前调用，以提供个性化服务。"""
    items = store.search(_namespace(config))
    if not items:
        return "（暂无该用户的偏好档案）"
    return "；".join(f"{i.key} = {i.value['value']}" for i in items)
