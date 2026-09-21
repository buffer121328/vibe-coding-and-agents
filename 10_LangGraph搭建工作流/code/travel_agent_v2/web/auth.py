"""登录认证：账号密码 + JWT 会话。

标准做法，不是比喻：
- 用户在 `users` 表里，密码只存 PBKDF2-HMAC-SHA256 的哈希和盐，明文永不落库；
- 校验用 `hmac.compare_digest` 常量时间比较，避免计时侧信道；
- 通过后签发 HS256 的 JWT，塞在 HttpOnly Cookie 里，12 小时过期；
- JWT 是无状态的，服务端不存会话，所以「退出登录」要把这次的 `jti`
  记进吊销名单，校验时先查名单。教学版放进程内存，生产要换 Redis。

每个账号绑定一个 `passenger_id`，决定它读谁的航段、对话和偏好档案。

密钥从 `TRIP_DESK_SECRET` 读；没配就用开发默认值，启动日志里会提醒。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid

import jwt
from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from web import store, verify

COOKIE_NAME = "trip_desk"
TOKEN_TTL = 60 * 60 * 12
ALGORITHM = "HS256"
ISSUER = "trip-assistant"
DEV_SECRET = "trip-desk-dev-secret-change-me-before-you-ship"
PBKDF2_ROUNDS = 260_000
MIN_PASSWORD = 6

# 演示账号：绑到库里真实存在的旅客档案，方便一进来就有航段可看。
DEMO_ACCOUNTS = (
    {"username": "alice", "password": "alice123", "passenger_id": "3442 587242",
     "email": "alice@example.com", "route": "北京 ↔ 成都"},
    {"username": "bob", "password": "bob123", "passenger_id": "0000 000343",
     "email": "bob@example.com", "route": "上海 ↔ 三亚"},
    {"username": "carol", "password": "carol123", "passenger_id": "0001 998571",
     "email": "carol@example.com", "route": "广州 ↔ 西安"},
    # 运营账号必须有自己的档案号：会话目录 / Store / 机票都按 passenger_id 隔离，
    # 和 carol 合住会把「两个登录名」讲成「两个人」，数据层其实是一份。
    {"username": "ops", "password": "ops12345", "passenger_id": "0002 445566",
     "email": "ops@example.com", "route": "杭州 ↔ 青岛（运营视图：可看全部订单与审计）", "role": "ops"},
)

# 密码连错几次之后，登录页就要出图形验证码
CAPTCHA_AFTER_FAILS = 3

OPEN_PATHS = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}

REVOKED: dict[str, int] = {}
REVOKED_LOCK = threading.Lock()


# ---------- 密钥与令牌 ----------

def secret() -> str:
    """取签名密钥：优先环境变量，缺了就退回开发默认值并提醒。

    :return: 字节串密钥
    """
    return (os.getenv("TRIP_DESK_SECRET") or "").strip() or DEV_SECRET


def using_dev_secret() -> bool:
    """是不是在用开发默认密钥（启动时打一行提醒用）。

    :return: bool
    """
    return secret() == DEV_SECRET


def _sweep_revoked() -> None:
    """清掉已经过期的吊销记录（否则名单只增不减）。

    :return: 无
    """
    now = int(time.time())
    for key in [k for k, exp in REVOKED.items() if exp < now]:
        REVOKED.pop(key, None)


def revoke(jti: str, exp: int) -> None:
    """把一枚令牌的 jti 记进吊销名单——JWT 无状态，退出登录只能这样补。

    :param jti: 令牌唯一 id
    :param exp: 令牌原定过期时间（到了就可以从名单里清掉）
    """
    with REVOKED_LOCK:
        _sweep_revoked()
        REVOKED[jti] = int(exp)


def is_revoked(jti: str | None) -> bool:
    """这枚令牌是否已被吊销。

    :param jti: 令牌唯一 id
    :return: bool
    """
    if not jti:
        return True
    with REVOKED_LOCK:
        _sweep_revoked()
        return jti in REVOKED


def mint_token(user: dict) -> tuple[str, dict]:
    """给这个用户签一枚 HS256 JWT（payload 里带 passenger_id 与 role）。

    :param user: 账号行（dict）
    :return: (token, claims) 二元组
    """
    now = int(time.time())
    claims = {
        "sub": user["username"],
        "uid": user["id"],
        "name": user.get("display_name") or user["username"],
        "email": user.get("email") or "",
        "role": user.get("role") or "passenger",
        "passenger_id": user["passenger_id"],
        "iss": ISSUER,
        "iat": now,
        "exp": now + TOKEN_TTL,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, secret(), algorithm=ALGORITHM), claims


def decode_token(token: str | None) -> dict | None:
    """校验签名、算法、签发方、有效期和吊销状态。任何一步不过都当没登录。"""
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            secret(),
            algorithms=[ALGORITHM],          # 写死算法：否则 alg=none 就能伪造令牌
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError:
        return None
    if is_revoked(claims.get("jti")):
        return None
    return claims


# ---------- 账号表 ----------

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """口令加盐哈希（PBKDF2-HMAC-SHA256，明文不落库）。

    :param password: 明文口令
    :param salt: 盐（hex）
    :return: 哈希（hex）
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS
    )
    return salt, digest.hex()


def verify_password(password: str, salt: str, expected: str) -> bool:
    """比对口令：用 `hmac.compare_digest` 做定长比较，避免时序侧信道。

    :param password: 用户输入
    :param salt: 库里存的盐
    :param expected: 库里存的哈希
    :return: bool
    """
    _, actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def _connect() -> sqlite3.Connection:
    """账号存在应用库里（db/app.sqlite），不会被种子数据覆盖。"""
    return store.connect()


def ensure_schema() -> None:
    """建账号表并补上演示账号；重复调用无副作用。

    演示账号已经存在时，仍把 passenger_id / role / email 对齐到 DEMO_ACCOUNTS：
    以前 ops 和 carol 合住一份档案，只改常量不会改已经落库的那一行。
    """
    store.ensure_schema()
    conn = _connect()
    try:
        for demo in DEMO_ACCOUNTS:
            row = conn.execute(
                "SELECT id, passenger_id, role, email FROM users WHERE username = ?",
                (demo["username"],),
            ).fetchone()
            if row:
                wanted_role = demo.get("role", "passenger")
                wanted_email = demo.get("email")
                if (
                    row["passenger_id"] != demo["passenger_id"]
                    or (row["role"] or "passenger") != wanted_role
                    or (row["email"] or "") != (wanted_email or "")
                ):
                    conn.execute(
                        "UPDATE users SET passenger_id = ?, role = ?, email = ? WHERE id = ?",
                        (demo["passenger_id"], wanted_role, wanted_email, row["id"]),
                    )
                continue
            salt, digest = hash_password(demo["password"])
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, passenger_id, display_name,"
                " email, email_verified, role) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                (demo["username"], digest, salt, demo["passenger_id"], demo["username"],
                 demo.get("email"), demo.get("role", "passenger")),
            )
        conn.commit()
    finally:
        conn.close()


def _user_row(row: sqlite3.Row) -> dict:
    """把查询行整成统一形状的用户 dict。

    :param row: sqlite3.Row
    :return: dict 或 None
    """
    return {
        "id": row["id"],
        "username": row["username"],
        "passenger_id": row["passenger_id"],
        "display_name": row["display_name"] or row["username"],
        "email": row["email"] or "",
        "role": row["role"] or "passenger",
    }


def normalize_account(account: str) -> str:
    """登录框里可能填用户名，也可能填邮箱，统一小写去空格。"""
    return (account or "").strip().lower()


def find_user(account: str) -> dict | None:
    """按用户名或邮箱找账号。登录框一个字段两种都收。"""
    text = normalize_account(account)
    if not text:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR (email IS NOT NULL AND email = ?)"
            " LIMIT 1",
            (text, text),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return dict(row) if row else None


def authenticate(account: str, password: str) -> dict | None:
    """账号密码校验。账号不存在和密码错误返回同一个 None，不泄露哪个错了。"""
    if not normalize_account(account) or not password:
        return None
    row = find_user(account)
    if not row:
        return None
    if not verify_password(password, row["salt"], row["password_hash"]):
        note_login_failure(row["username"])
        return None
    clear_login_failures(row["username"])
    return _user_row_by_id(row["id"])


def _user_row_by_id(user_id: int) -> dict:
    """按主键取用户。

    :param user_id: 用户主键
    :return: dict 或 None
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    return _user_row(row)


def captcha_required(account: str) -> bool:
    """这个账号连续错太多次了吗？是的话登录页要出图形验证码。"""
    row = find_user(account)
    if not row:
        return False
    return int(row.get("login_fails") or 0) >= CAPTCHA_AFTER_FAILS


def note_login_failure(username: str) -> None:
    """记一次登录失败（连错 3 次就要补图形验证码）。

    :param username: 账号名
    :return: 累计失败次数
    """
    conn = _connect()
    try:
        conn.execute("UPDATE users SET login_fails = login_fails + 1 WHERE username = ?", (username,))
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def clear_login_failures(username: str) -> None:
    """登录成功后把失败计数清零。

    :param username: 账号名
    :return: 无
    """
    conn = _connect()
    try:
        conn.execute("UPDATE users SET login_fails = 0 WHERE username = ?", (username,))
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def validate_new_user(username: str, password: str, passenger_id: str, email: str = "") -> tuple[str, str, str]:
    """把注册要校验的都校验一遍，返回 (用户名, 邮箱, 档案号)。

    单独抽出来是为了**先把能便宜判掉的错误判掉，再去消费图形验证码**：
    否则密码太短之类的低级错误会把题烧掉，用户得重新看图。
    （邮箱码恢复之后，这里同样先判便宜错误，再去消费邮箱码——否则用户得重新收一次信。）
    """
    name = (username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,24}", name):
        raise ValueError("用户名只能用小写字母、数字和下划线，长度 3–24")
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"密码至少 {MIN_PASSWORD} 位")
    addr = verify.normalize(email)
    if not verify.valid_email(addr):
        raise ValueError("请填一个有效的邮箱地址")
    pid = (passenger_id or "").strip()
    if not pid:
        raise ValueError("请选择要绑定的旅客档案")
    if not _passenger_exists(pid):
        raise ValueError("旅客档案不存在，请从列表里选")

    conn = _connect()
    try:
        if conn.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone():
            raise ValueError("这个用户名已经注册过了")
        if conn.execute(
            "SELECT id FROM users WHERE email IS NOT NULL AND email = ?", (addr,)
        ).fetchone():
            raise ValueError("这个邮箱已经注册过了，直接登录或换个邮箱")
    finally:
        conn.close()
    return name, addr, pid


def create_user(
    username: str,
    password: str,
    passenger_id: str,
    email: str = "",
    display_name: str = "",
) -> dict:
    """建账号：校验过的字段才落库，口令走哈希。

    :param username: 用户名
    :param password: 明文口令
    :param passenger_id: 绑定的旅客档案号
    :param email: 邮箱（登录也能用它）
    :param display_name: 显示名（缺省用用户名）
    :return: 用户 dict；重复则抛 ValueError
    """
    name, addr, pid = validate_new_user(username, password, passenger_id, email)
    conn = _connect()
    try:
        salt, digest = hash_password(password)
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, passenger_id, display_name,"
            " email, email_verified) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (name, digest, salt, pid, (display_name or name).strip(), addr),
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("这个用户名已经注册过了") from exc
    finally:
        conn.close()
    return {
        "id": user_id,
        "username": name,
        "passenger_id": pid,
        "display_name": display_name or name,
        "email": addr,
        "role": "passenger",
    }


from infra.biz_db import BUSINESS_DB


def _passenger_exists(passenger_id: str) -> bool:
    """档案是否存在要去业务库查（应用库里没有行程数据）。"""
    if not os.path.exists(BUSINESS_DB):
        return False
    conn = sqlite3.connect(BUSINESS_DB)
    try:
        row = conn.execute(
            "SELECT 1 FROM tickets WHERE passenger_id = ? LIMIT 1", (passenger_id,)
        ).fetchone()
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return bool(row)


def known_passengers() -> list[dict]:
    """注册时可选绑定的旅客档案（四份真实航段：alice / bob / carol / ops）。"""
    return [
        {
            "passenger_id": item["passenger_id"],
            "route": item["route"],
            "username": item["username"],
            "email": item.get("email", ""),
        }
        for item in DEMO_ACCOUNTS
    ]


# ---------- Cookie 与会话 ----------

def issue_cookie(response: Response, user: dict) -> dict:
    """把令牌写进 HttpOnly Cookie（SameSite=Lax，前端 JS 读不到）。

    :param response: FastAPI 响应对象
    :param user: 账号行
    :return: 无
    """
    token, claims = mint_token(user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_TTL,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return claims


def clear_cookie(response: Response, claims: dict | None = None) -> None:
    """退出登录时清 Cookie，并把这枚令牌吊销。

    :param response: FastAPI 响应对象
    :param claims: 当前令牌声明（可能为 None）
    :return: 无
    """
    if claims:
        revoke(str(claims.get("jti") or ""), int(claims.get("exp") or time.time()))
    response.delete_cookie(COOKIE_NAME, path="/")


def current_session(request: Request) -> dict | None:
    """从 Cookie 里解出「现在是谁」；没登录或令牌已吊销返回 None。

    :param request: 带 Cookie 的请求
    :return: claims dict 或 None
    """
    return decode_token(request.cookies.get(COOKIE_NAME))


def require_session(request: Request) -> dict:
    """同上，但没登录直接抛 401（受保护接口用）。

    :param request: 带 Cookie 的请求
    :return: claims dict
    """
    claims = current_session(request)
    if not claims:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    return claims


def public_identity(claims: dict | None) -> dict:
    """把内部 claims 收成前端能看的身份字段（不带敏感信息）。

    :param claims: 令牌声明；None 表示未登录
    :return: {"authed": bool, "username": ..., "passenger_id": ..., "role": ...}
    """
    if not claims:
        return {"authed": False, "username": None, "passenger_id": None}
    return {
        "authed": True,
        "username": claims.get("sub"),
        "display_name": claims.get("name") or claims.get("sub"),
        "passenger_id": claims.get("passenger_id"),
        "email": claims.get("email") or "",
        "role": claims.get("role") or "passenger",
    }


class AuthGate(BaseHTTPMiddleware):
    """受保护的接口默认要登录；页面、静态资源和登录相关接口放行。"""

    async def dispatch(self, request: Request, call_next):
        """鉴权中间件：白名单（页面、静态资源、登录相关）放行，其余 `/api/*` 一律要登录。

        :param request: 进来的请求
        :param call_next: 下游处理链
        :return: 响应；未登录时 401
        """
        path = request.url.path
        if (
            path in OPEN_PATHS
            or path.startswith("/static/")
            or path.startswith("/api/auth")
        ):
            return await call_next(request)
        if path.startswith("/api/") and current_session(request) is None:
            return Response(
                content='{"detail": "未登录或会话已过期"}',
                status_code=401,
                media_type="application/json",
            )
        return await call_next(request)
