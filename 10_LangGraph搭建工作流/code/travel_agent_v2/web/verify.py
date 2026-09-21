"""邮箱验证码：签发、校验、限流。

存的是验证码的**哈希**而不是明文——万一库被看到，也不能直接拿来登录。
和其他应用表一样放在 `db/app.sqlite`（见 web/store.py），不跟会重建的业务库混。

三道闸：
- 同一邮箱同一用途 60 秒内只能发一次（防连点）；
- 10 分钟过期；
- 最多试 5 次，试完作废（防暴力猜 6 位数字）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

from web import store

LENGTH = 6
TTL = 600                 # 10 分钟
RESEND_COOLDOWN = 60      # 同一邮箱 60 秒内不重复发
MAX_ATTEMPTS = 5
PEPPER = os.getenv("TRIP_DESK_SECRET") or "trip-desk-dev-secret"

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

PURPOSES = {"register", "login", "reset"}


def normalize(email: str) -> str:
    """把邮箱规整成统一形状（去空格、转小写）——库里只存规整后的。

    :param email: 原始输入
    :return: 规整后的邮箱
    """
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    """粗校验邮箱格式（正则，不求完备；真正的验证靠那封信）。

    :param email: 邮箱
    :return: bool
    """
    text = normalize(email)
    return bool(text) and len(text) <= 120 and bool(EMAIL_RE.match(text))


def _hash(email: str, code: str) -> str:
    """把邮箱揉进哈希，避免两个邮箱用同一个验证码时哈希相同。"""
    raw = f"{normalize(email)}|{code}|{PEPPER}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _now() -> int:
    """当前时间戳（验证码记录用）。

    :return: float 秒
    """
    return int(time.time())


def _sweep(conn: sqlite3.Connection) -> None:
    """清掉过期的验证码记录。

    :param conn: 应用库连接
    :return: 无
    """
    conn.execute("DELETE FROM email_codes WHERE expires_at < ?", (_now() - 3600,))


def can_send(email: str, purpose: str = "register") -> tuple[bool, int]:
    """能不能发？返回 (是否可以, 还要等几秒)。"""
    conn = store.connect()
    try:
        row = conn.execute(
            "SELECT created_at FROM email_codes WHERE email = ? AND purpose = ?"
            " ORDER BY id DESC LIMIT 1",
            (normalize(email), purpose),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return True, 0
    wait = RESEND_COOLDOWN - (_now() - int(row["created_at"]))
    return (wait <= 0), max(0, wait)


def issue(email: str, purpose: str = "register") -> str:
    """签发一个验证码，返回明文（只在这一刻拿得到，之后库里只有哈希）。"""
    if purpose not in PURPOSES:
        raise ValueError("未知的验证码用途")
    addr = normalize(email)
    if not valid_email(addr):
        raise ValueError("邮箱格式不对")

    code = f"{secrets.randbelow(1_000_000):06d}"
    now = _now()
    conn = store.connect()
    try:
        _sweep(conn)
        # 同一邮箱同一用途只保留最新一条：旧的自动作废
        conn.execute(
            "UPDATE email_codes SET used = 1 WHERE email = ? AND purpose = ? AND used = 0",
            (addr, purpose),
        )
        conn.execute(
            "INSERT INTO email_codes (email, purpose, code_hash, expires_at, attempts, used, created_at)"
            " VALUES (?, ?, ?, ?, 0, 0, ?)",
            (addr, purpose, _hash(addr, code), now + TTL, now),
        )
        conn.commit()
    finally:
        conn.close()
    return code


def verify(email: str, code: str, purpose: str = "register") -> tuple[bool, str]:
    """校验验证码。返回 (是否通过, 失败原因)。"""
    addr = normalize(email)
    text = (code or "").strip()
    if not valid_email(addr) or not text:
        return False, "邮箱或验证码为空"

    conn = store.connect()
    try:
        row = conn.execute(
            "SELECT * FROM email_codes WHERE email = ? AND purpose = ? AND used = 0"
            " ORDER BY id DESC LIMIT 1",
            (addr, purpose),
        ).fetchone()
        if not row:
            return False, "请先获取验证码"
        if int(row["expires_at"]) < _now():
            conn.execute("UPDATE email_codes SET used = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            return False, "验证码已过期，请重新获取"
        if int(row["attempts"]) >= MAX_ATTEMPTS:
            conn.execute("UPDATE email_codes SET used = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            return False, "试错次数过多，请重新获取"

        ok = hmac.compare_digest(row["code_hash"], _hash(addr, text))
        if ok:
            conn.execute("UPDATE email_codes SET used = 1 WHERE id = ?", (row["id"],))
        else:
            conn.execute(
                "UPDATE email_codes SET attempts = attempts + 1 WHERE id = ?", (row["id"],)
            )
        conn.commit()
    finally:
        conn.close()
    return (True, "") if ok else (False, "验证码不正确")
