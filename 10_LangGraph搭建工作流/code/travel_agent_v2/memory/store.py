"""长期记忆（Store）：跨线程的用户偏好档案。

对应文档：第 10 章 10_长期记忆与TimeTravel.md
Store 与 Checkpointer 的分工：
- Checkpointer（`web/runtime/hub.py` 里的 SqliteSaver）= 单次会话内的存档；
- Store（本文件）= 跨会话共享的「会员档案」，换个 thread_id 也能翻到。

实现换过一次：原先是 `InMemoryStore`（进程内存，重启即失忆，只够演示）；
现在落 `db/preferences.sqlite`，重启后「记住靠窗」还是记得住。
接口完全一样——`put / get / search`，所以工具（tools/preferences.py）一行都没改。
再多的人、再大的量，换成 PostgresStore 也是同一个接口。
"""
from __future__ import annotations

import os
import sqlite3

from langgraph.store.sqlite import SqliteStore

# 库路径与那个测试开关（TRIP_DESK_DB_DIR）都在 infra/paths.py，本文件不再自己解析。
from infra.paths import PREFERENCES_DB, STATE_DB_DIR

os.makedirs(STATE_DB_DIR, exist_ok=True)

# check_same_thread=False：FastAPI 的线程池会在不同线程里读它（和 Checkpointer 同理）
_conn = sqlite3.connect(PREFERENCES_DB, check_same_thread=False)
store = SqliteStore(_conn)
store.setup()
# setup() 建表之后会留下一个没提交的事务，紧接着读就会撞上
# 「cannot start a transaction within a transaction」——补一句 commit。
_conn.commit()

# 演示用预置档案：让 recall_preferences 首次调用就有内容。
# 只在**没有**的时候写一次——落盘之后每次启动都覆盖，就等于把用户改过的档案擦掉。
# 真实项目中档案由模型在对话中调用 save_preference 工具逐步写入。
for _key, _value in (("seat_preference", "靠窗"), ("membership_no", "FF-88001")):
    if store.get(("pref_3442 587242",), _key) is None:
        store.put(("pref_3442 587242",), _key, {"value": _value})
