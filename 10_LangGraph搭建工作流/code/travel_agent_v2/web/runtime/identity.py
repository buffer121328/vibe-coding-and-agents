"""一次请求的身份：谁在用、在哪条会话上。

最上游的那一块。别的什么都不做——不碰图、不查库、不拼快照，只回答一个问题：
「这个请求该被当成谁、落在哪条对话上」。答案是一个不可变的 `Desk`，随请求传下去。
"""
from __future__ import annotations

from dataclasses import dataclass

from web import sessions
from web.runtime.hub import PASSENGER_ID


@dataclass(frozen=True)
class Desk:
    """一次请求的身份：谁在用、在哪条会话上。

    以前这些是进程级全局（一个 SESSION 字典），两个人同时用就会串台：
    A 的请求把 passenger_id / thread_id 写成 B 的，A 的下一句就落进 B 的档案。
    现在它是随请求传下来的值——api 层从 JWT 解出乘客、解析会话，再一路传给
    runtime 的每个函数；图那边本来就是无状态的（身份走 configurable）。
    """

    passenger_id: str
    thread_id: str = ""
    username: str = ""
    role: str = "passenger"

    @property
    def actor(self) -> str:
        """这人的登录名（写审计用；没登录名时返回空串）。

        :return: username 或 ""
        """
        return self.username or ""

    @property
    def namespace(self) -> tuple[str, ...]:
        """长期记忆（Store）里这个人的抽屉。"""
        return (f"pref_{self.passenger_id}",)

    @property
    def config(self) -> dict:
        """交给图的 RunnableConfig：图只认这里的身份，不认模块全局。"""
        return {
            "configurable": {
                "passenger_id": self.passenger_id,
                "thread_id": self.thread_id,
            }
        }


BOOT_DESK = Desk(passenger_id=PASSENGER_ID)


def resolve_desk(
    passenger_id: str,
    *,
    username: str = "",
    role: str = "passenger",
    thread_hint: str = "",
) -> Desk:
    """按请求解析「现在是谁、在哪条会话上」。

    「当前会话」不再存在进程里，所以它得有个来源，按优先级：
    1. 客户端带的 thread（多标签页各聊各的，前提是那条还属于他本人）；
    2. 否则用他最近动过的那条（切换会话、新建会话都会把 updated_at 顶到最前）；
    3. 都没有就开一条新的（新账号第一次进来）。
    """
    thread = ""
    if thread_hint and sessions.exists(thread_hint, passenger_id):
        thread = thread_hint
    else:
        latest = sessions.latest_for(passenger_id)
        thread = (
            latest["thread_id"]
            if latest
            else sessions.create(passenger_id, username)["thread_id"]
        )
    return Desk(passenger_id=passenger_id, thread_id=thread, username=username, role=role)
