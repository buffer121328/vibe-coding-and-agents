"""审计流水：谁、什么时候、对谁、干了什么、结果如何。

工作台是「会改库存的东西」，所以要留下痕迹。这里记三类事件：
- 身份：登录、退出、注册、令牌过期被拦；
- 审批：批准或驳回了哪个敏感工具（带参数）；
- 订单：订了、退了、改了什么。

表在 `db/app.sqlite`（见 web/store.py），不跟业务数据混，重建种子库不会冲掉。
"""
from __future__ import annotations

import json
from datetime import datetime

from web import store

# 动作名用固定字符串，前端和查询才好按它分组统计
LOGIN = "login"
LOGOUT = "logout"
REGISTER = "register"
APPROVE = "approve"
REJECT = "reject"
BOOK = "book"
CANCEL = "cancel"
UPDATE = "update"
SESSION_NEW = "session_new"
SESSION_OPEN = "session_open"
SESSION_RENAME = "session_rename"
SESSION_DELETE = "session_delete"

OK = "ok"
DENIED = "denied"
ERROR = "error"


def _now() -> str:
    """当前时间戳（流水的时间列）。

    :return: 'YYYY-MM-DD HH:MM:SS'
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write(
    action: str,
    *,
    actor: str = "",
    passenger_id: str = "",
    thread_id: str = "",
    target: str = "",
    detail=None,
    result: str = OK,
) -> None:
    """记一条流水。审计失败不能拖垮业务请求，所以这里吞掉异常。"""
    payload = ""
    if detail is not None:
        try:
            payload = json.dumps(detail, ensure_ascii=False, default=str)[:2000]
        except (TypeError, ValueError):
            payload = str(detail)[:2000]
    try:
        conn = store.connect()
        try:
            conn.execute(
                "INSERT INTO audit (at, actor, passenger_id, thread_id, action, target, detail, result)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), actor, passenger_id, thread_id, action, target, payload, result),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:      # noqa: BLE001 —— 审计不能影响主流程
        pass


def recent(limit: int = 60, actor: str = "", action: str = "") -> list[dict]:
    """最近流水；给某个账号或某个动作过滤，运维面板用。"""
    sql = "SELECT * FROM audit WHERE 1=1"
    params: list = []
    if actor:
        sql += " AND actor = ?"
        params.append(actor)
    if action:
        sql += " AND action = ?"
        params.append(action)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    conn = store.connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        detail = row["detail"]
        try:
            detail = json.loads(detail) if detail else None
        except (TypeError, ValueError):
            pass
        out.append(
            {
                "id": row["id"],
                "at": row["at"],
                "actor": row["actor"],
                "passenger_id": row["passenger_id"],
                "thread_id": row["thread_id"],
                "action": row["action"],
                "target": row["target"],
                "detail": detail,
                "result": row["result"],
            }
        )
    return out


def summary() -> dict:
    """按动作统计条数，运维面板顶部那排数字用。"""
    conn = store.connect()
    try:
        rows = conn.execute(
            "SELECT action, result, COUNT(*) AS n FROM audit GROUP BY action, result"
        ).fetchall()
        totals = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    finally:
        conn.close()
    by_action: dict[str, int] = {}
    failures = 0
    for row in rows:
        by_action[row["action"]] = by_action.get(row["action"], 0) + row["n"]
        if row["result"] != OK:
            failures += row["n"]
    return {"total": totals, "by_action": by_action, "failures": failures}
