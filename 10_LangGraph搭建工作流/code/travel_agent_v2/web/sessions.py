"""会话目录：每个账号一份对话列表。

图的对话存档由 Checkpointer（db/checkpoints.sqlite）负责；这里管的是**目录**——
这条 thread 属于谁、叫什么名字、什么时候动过、聊了几轮。

分成两张表是有意的：
- Checkpointer 的表由 LangGraph 自己写，结构不归我们管；
- 会话标题、归属、时间这些是产品字段，得自己存，才能做「我的会话」列表、改名、删除。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from web import store

DEFAULT_TITLE = "新对话"
TITLE_LIMIT = 18


def _now() -> str:
    """会话目录的时间戳，精确到微秒。

    只精确到秒的时候，同一秒里「新建 → 切换 → 删」会全部打平，
    排序只能靠 rowid 兜底；而「当前会话是谁」正是靠这个排序解析的
    （见 runtime.resolve_desk），打平就会挑错人。带微秒最省事。
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def _row(row) -> dict:
    """把会话行整成统一 dict。

    :param row: sqlite3.Row
    :return: dict
    """
    return {
        "thread_id": row["thread_id"],
        "title": row["title"],
        "turns": row["turns"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create(owner: str, username: str = "", title: str = DEFAULT_TITLE) -> dict:
    """建一条会话（顺手清掉这个账号上一条「没聊过也没改过名」的空草稿）。

    :param owner: 归属旅客档案号
    :param username: 建它的人
    :param title: 初始标题
    :return: 新会话 dict
    """
    thread_id = str(uuid.uuid4())
    now = _now()
    conn = store.connect()
    try:
        conn.execute(
            "INSERT INTO sessions (thread_id, owner, username, title, turns, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 0, ?, ?)",
            (thread_id, owner, username, title or DEFAULT_TITLE, now, now),
        )
        # 空草稿不留：连点「新对话」时，顺手把上一条**没聊过也没改过名**的会话清掉。
        # 判据是 turns = 0 且标题还是默认值——聊过一句、或用户亲手改过名的，都算有主，留着。
        conn.execute(
            "DELETE FROM sessions WHERE owner = ? AND thread_id != ? AND turns = 0 AND title = ?",
            (owner, thread_id, DEFAULT_TITLE),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM sessions WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    finally:
        conn.close()
    return _row(row)


def list_for(owner: str) -> list[dict]:
    """按最近使用时间倒序。

    时间戳精确到微秒之后，同一秒建多条也能分出先后；rowid 只作为完全相同
    时间戳（同一微秒）时的兜底，保证顺序不会随机漂移。
    """
    conn = store.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE owner = ?"
            " ORDER BY updated_at DESC, rowid DESC",
            (owner,),
        ).fetchall()
    finally:
        conn.close()
    return [_row(row) for row in rows]


def get(thread_id: str, owner: str) -> dict | None:
    """取一条会话（校验归属）。

    :param thread_id: 会话 id
    :param owner: 期望的归属者
    :return: dict 或 None
    """
    conn = store.connect()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE thread_id = ? AND owner = ?", (thread_id, owner)
        ).fetchone()
    finally:
        conn.close()
    return _row(row) if row else None


def rename(thread_id: str, owner: str, title: str) -> bool:
    """改名。

    注意**不动 updated_at**：那个字段是「最近使用时间」，也是「当前会话」的解析依据
    （runtime.resolve_desk 取最近用过的那条）。改个名字不该把用户的当前会话换掉。
    """
    clean = (title or "").strip()[:40]
    if not clean:
        return False
    conn = store.connect()
    try:
        cur = conn.execute(
            "UPDATE sessions SET title = ? WHERE thread_id = ? AND owner = ?",
            (clean, thread_id, owner),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def remove(thread_id: str, owner: str) -> bool:
    """删一条会话目录项。

    :param thread_id: 会话 id
    :param owner: 归属者
    :return: 是否删掉
    """
    conn = store.connect()
    try:
        cur = conn.execute(
            "DELETE FROM sessions WHERE thread_id = ? AND owner = ?", (thread_id, owner)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def touch(thread_id: str, turns: int | None = None) -> None:
    """一次对话之后更新「最近使用时间」和轮数。"""
    conn = store.connect()
    try:
        if turns is None:
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE thread_id = ?", (_now(), thread_id)
            )
        else:
            conn.execute(
                "UPDATE sessions SET updated_at = ?, turns = ? WHERE thread_id = ?",
                (_now(), int(turns), thread_id),
            )
        conn.commit()
    finally:
        conn.close()


def auto_title(thread_id: str, owner: str, first_message: str) -> str | None:
    """第一次发言时用那句话给会话起名，之后不再覆盖（用户改过名要保留）。"""
    text = " ".join((first_message or "").split())
    if not text:
        return None
    title = text[:TITLE_LIMIT] + ("…" if len(text) > TITLE_LIMIT else "")
    conn = store.connect()
    try:
        row = conn.execute(
            "SELECT title FROM sessions WHERE thread_id = ? AND owner = ?",
            (thread_id, owner),
        ).fetchone()
        if not row or row["title"] != DEFAULT_TITLE:
            return None
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE thread_id = ?",
            (title, _now(), thread_id),
        )
        conn.commit()
    finally:
        conn.close()
    return title


def exists(thread_id: str, owner: str) -> bool:
    """这条会话是否属于他（解析「当前会话」时校验用）。

    :param thread_id: 会话 id
    :param owner: 归属者
    :return: bool
    """
    return get(thread_id, owner) is not None


def latest_for(owner: str) -> dict | None:
    """他最近动过的那条会话（没有就返回 None）。

    :param owner: 归属者
    :return: dict 或 None
    """
    items = list_for(owner)
    return items[0] if items else None


def ensure_for(owner: str, username: str = "") -> dict:
    """没有会话就建一个；有就返回最近那个。"""
    found = latest_for(owner)
    return found or create(owner, username)
