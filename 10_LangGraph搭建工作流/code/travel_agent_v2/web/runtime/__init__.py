"""运行时：把 HTTP 请求翻成「一次会话语义」的动作，再把结果拼成快照。

这一包是接口层的内核，按**数据流向**拆成小文件，谁都不许越界：

| 文件 | 管什么 | 依赖方向 |
| :--- | :--- | :--- |
| `identity.py` | 一次请求的身份：谁在用、在哪条会话上（`Desk`） | 最上游，只依赖会话目录 |
| `hub.py` | 图单例、存档连接、进程内状态（节点时间线、忙闲） | 只依赖 agent / infra |
| `turns.py` | 图里的消息 → 前端要的「轮次 / 历史」 | 依赖 hub |
| `inspect.py` | `interrupt()` 数据包 → 人能读的挂起信息 | 依赖 hub + orders |
| `reads.py` | 只读投影：行程、看板、卡片、偏好、订单、审计、会话列表 | 依赖 hub / turns + 展示层 |
| `snapshot.py` | 把上面几样拼成一份快照 | 依赖全部只读件 |
| `turn.py` | 写路径：一次推进（发言 / 批准 / 驳回）+ 收尾记账 | 依赖 hub / turns / inspect |
| `stream.py` | 节点级 SSE：把一次推进拆成可推的事件 | 依赖 turn / hub |
| `sessions_ops.py` | 身份与会话的写操作（登录 / 退出 / 新建 / 切换 / 改名 / 删除） | 依赖 identity / snapshot |
| `__init__.py` | 门面：`web.api` 只认这里导出的名字 | —— |

**为什么拆包**：原来这是一个 1280 行的 `runtime.py`，读的人要在「会话解析、只读投影、
SSE 拼装」之间反复跳。现在按上表分开，每个文件一个职责，改哪块看哪个文件。
"""
from __future__ import annotations

from web.runtime.identity import BOOT_DESK, Desk, resolve_desk
from web.runtime import hub
from web.runtime.hub import (
    PASSENGER_ID,
    TRACES,
    init,
    model_name,
    api_key_configured,
)


def __getattr__(name: str):
    """`GRAPH` / `CHECKPOINTER` 走属性转发，不在 import 期就把值绑走。

    这两样是 `init()` 里才赋值的：若这里 `from ... import GRAPH`，模块导入时抓到的是
    None，之后 init() 换了新对象也传不过来（调用方拿到的永远是那个 None）。
    """
    if name in {"GRAPH", "CHECKPOINTER"}:
        return getattr(hub, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from web.runtime.reads import (
    audit_view,
    explore_cities,
    orders_view,
    sessions_view,
)
from web.runtime.sessions_ops import (
    delete_session,
    login_passenger,
    logout_passenger,
    new_session,
    open_session,
    rename_session,
)
from web.runtime.snapshot import snapshot
from web.runtime.stream import iter_approve, iter_chat, iter_reject
from web.runtime.turn import approve, chat_turn, reject

__all__ = [
    # 身份
    "Desk",
    "BOOT_DESK",
    "resolve_desk",
    # 图与进程内状态
    "GRAPH",
    "TRACES",
    "PASSENGER_ID",
    "init",
    "model_name",
    "api_key_configured",
    # 只读投影
    "sessions_view",
    "orders_view",
    "audit_view",
    "explore_cities",
    # 快照
    "snapshot",
    # 写路径
    "chat_turn",
    "approve",
    "reject",
    # SSE
    "iter_chat",
    "iter_approve",
    "iter_reject",
    # 身份与会话的写操作
    "login_passenger",
    "logout_passenger",
    "new_session",
    "open_session",
    "rename_session",
    "delete_session",
]
