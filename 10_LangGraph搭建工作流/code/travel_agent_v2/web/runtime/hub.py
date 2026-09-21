"""图单例与进程内状态：把「这台机器正在值班的那张图」管起来。

只有这里知道怎么把图编译出来、存档落在哪、节点时间线存在哪。
只读投影、快照、推进都从这里取 `GRAPH` 与 `trace`，谁也不许自己 build 一张图。
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime
from typing import TYPE_CHECKING

from langgraph.checkpoint.sqlite import SqliteSaver

# 组合根在 main.py：它才是唯一知道「怎么把 agent / tools / memory / infra 装成一张图」的地方
from main import build_graph
from infra.biz_db import update_dates
from web import orders, store
from web.auth import ensure_schema
from web.present.labels import NODE_LABELS

if TYPE_CHECKING:                       # 只给类型注解用：identity 反过来依赖本模块
    from web.runtime.identity import Desk


PASSENGER_ID = "3442 587242"


TRACE_LIMIT = 48


SKIP_NODES = {"__start__", "__end__"}

# 图与存档在 init() 里才赋值：外面一律用 hub.GRAPH / hub.CHECKPOINTER 访问，
# 别 `from ... import GRAPH`——那样在 import 期抓到的是 None，init 之后也传不过来。
GRAPH = None
CHECKPOINTER = None

RUN_LOCK = threading.Lock()   # 一次只推进一轮：LangGraph 的 stream 不适合并发喂同一个 thread
BUSY = False                  # 同上，只用 is_busy() / set_busy()，别 import 值
TRACES: dict[str, list[dict]] = {}


def is_busy() -> bool:
    """这台工作台此刻有没有一轮推进在跑（前端拿它显示「正在执行」）。"""
    return BUSY


def set_busy(flag: bool) -> None:
    """标记「一轮推进开始 / 结束」。

    :param flag: True 表示开始推进，False 表示收工
    """
    global BUSY
    BUSY = bool(flag)


def init() -> None:
    """启动时编译总图、建账号表、接上持久化存档。测试要先打好假模型补丁再 import web.app。"""
    global GRAPH, CHECKPOINTER
    if GRAPH is not None:
        return
    update_dates()
    store.ensure_schema()
    ensure_schema()                      # 账号表（在 db/app.sqlite）
    CHECKPOINTER = _checkpointer()
    GRAPH = build_graph(CHECKPOINTER)
    # 库存是每次启动重建的，订单不是；把订单回写到库存标记上，两边才一致
    orders.sync_inventory()
    orders.ensure_flight_orders(PASSENGER_ID)


def _checkpointer():
    """对话存档落到 db/checkpoints.sqlite：重启服务后历史还在。

    连接必须 check_same_thread=False —— FastAPI 的线程池会在不同线程里调用图。
    单 worker 纪律下这把连接是唯一的写入口，所以够用；多副本要换 Postgres。
    """
    conn = sqlite3.connect(store.CHECKPOINT_DB, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def model_name() -> str:
    """当前配置的模型名（页面上「模型」那一枚 chip 用它）。

    :return: 环境变量里的模型名，取不到给个默认
    """
    return os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")


def api_key_configured() -> bool:
    """有没有配真正的模型 Key（没配就是「未配 Key」演示模式）。

    :return: bool
    """
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and key not in {"your-api-key-here", "sk-xxxx"}


def _push_trace(desk: Desk, node: str, namespace=()) -> None:
    """往节点时间线里记一笔（进程内，每人每条会话一份）。

    :param desk: 这次请求的身份（用它的 thread_id 分桶）
    :param node: 节点名
    :param namespace: 子图命名空间（子图里的节点带上它，界面上标「子图」）
    """
    items = TRACES.setdefault(desk.thread_id, [])
    items.append(
        {
            "node": node,
            "label": NODE_LABELS.get(node, node),
            "namespace": [str(x) for x in (namespace or ())],
            "at": datetime.now().strftime("%H:%M:%S"),
        }
    )
    if len(items) > TRACE_LIMIT:
        del items[: len(items) - TRACE_LIMIT]


def _trace(desk: Desk) -> list[dict]:
    """读这条会话的节点时间线（最近 TRACE_LIMIT 条）。

    :param desk: 这次请求的身份
    :return: [{node, label, namespace, at}]
    """
    return list(TRACES.get(desk.thread_id, []))
