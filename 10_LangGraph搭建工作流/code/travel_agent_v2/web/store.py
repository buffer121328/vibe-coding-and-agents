"""应用自己的库：账号、会话目录、审计流水。

为什么不跟业务数据放一起：`infra/biz_db.py` 的 `update_dates()` 每次启动都会用种子库
（`db/travel2.sqlite`）覆盖业务库（`db/travel_new.sqlite`）。任何存在业务库里的
应用数据都会被抹掉——注册的账号、会话列表、审批流水都不能放那儿。

所以这里单独开一个 `db/app.sqlite`，它不参与种子重建，重启后数据还在。

两个路径都从 `infra/paths.py` 拿（全仓唯一的路径出处），包括 `TRIP_DESK_DB_DIR`
那个测试开关——以前本模块和 `memory/store.py` 各解析了一遍同样的环境变量。
"""
from __future__ import annotations

import os
import sqlite3
import threading

from infra.paths import APP_DB, CHECKPOINT_DB, STATE_DB_DIR

# 应用库、存档库的路径在 infra/paths.py；这里只引用，不再自己拼。
# web/orders.py 里有一条备注专门说：业务库路径别用 STATE_DB_DIR，它会被测试挪走。

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    passenger_id  TEXT NOT NULL,
    display_name  TEXT,
    email         TEXT,                                -- 注册时填的邮箱，用于收验证码
    email_verified INTEGER NOT NULL DEFAULT 0,
    role          TEXT NOT NULL DEFAULT 'passenger',   -- passenger | ops
    login_fails   INTEGER NOT NULL DEFAULT 0,          -- 连续密码错误次数，够了就要图形验证码
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;

-- 邮箱验证码：只存哈希，不存明文
CREATE TABLE IF NOT EXISTS email_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL,
    purpose    TEXT NOT NULL,                          -- register | login | reset
    code_hash  TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_codes_email ON email_codes(email, purpose, used);

CREATE TABLE IF NOT EXISTS sessions (
    thread_id  TEXT PRIMARY KEY,
    owner      TEXT NOT NULL,                          -- 绑定的旅客档案号
    username   TEXT,
    title      TEXT NOT NULL DEFAULT '新对话',
    turns      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_owner ON sessions(owner, updated_at DESC);

CREATE TABLE IF NOT EXISTS audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    at           TEXT NOT NULL,
    actor        TEXT,                                 -- 登录名
    passenger_id TEXT,
    thread_id    TEXT,
    action       TEXT NOT NULL,                        -- login / approve / book ...
    target       TEXT,                                 -- 工具名或订单号
    detail       TEXT,                                 -- JSON 字符串
    result       TEXT NOT NULL DEFAULT 'ok'            -- ok | denied | error
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit(at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit(actor, at DESC);

-- 订单与库存分开存是刻意的：
--   库存（hotels / car_rentals / trip_recommendations）在业务库，每次启动从种子库重建，
--   属于「可重置的演示数据」；订单属于用户资产，必须留在应用库，重启不能丢。
-- 启动时 orders.sync_inventory() 会把已确认订单回写到库存的 booked 标记上。
CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    passenger_id TEXT NOT NULL,
    username     TEXT,
    kind         TEXT NOT NULL,                        -- flight | hotel | car | spot
    ref          TEXT NOT NULL,                        -- 库存行标识（唯一键的一部分）
    title        TEXT NOT NULL,
    location     TEXT,
    start_date   TEXT,
    end_date     TEXT,
    amount       INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'confirmed',     -- confirmed | cancelled
    thread_id    TEXT,
    detail       TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (passenger_id, kind, ref)
);
CREATE INDEX IF NOT EXISTS idx_orders_owner ON orders(passenger_id, start_date);
"""

_LOCK = threading.Lock()


def connect() -> sqlite3.Connection:
    """开应用库连接（账号 / 会话目录 / 订单 / 审计都在这）。

    :return: sqlite3 连接（row_factory=Row）
    """
    os.makedirs(STATE_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(APP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# 老库升级用：列名 -> 建列语句。加字段时往这里追一条，别去改已有表的定义。
USER_COLUMNS = {
    "email": "ALTER TABLE users ADD COLUMN email TEXT",
    "email_verified": "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0",
    "login_fails": "ALTER TABLE users ADD COLUMN login_fails INTEGER NOT NULL DEFAULT 0",
}


def migrate(conn: sqlite3.Connection) -> list[str]:
    """把老库补齐到当前表结构。已经有的列跳过，返回这次补了哪些。"""
    added = []
    have = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    for column, ddl in USER_COLUMNS.items():
        if column not in have:
            conn.execute(ddl)
            added.append(column)
    if "email" in added:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL"
        )
    return added


def ensure_schema() -> None:
    """建表 + 补列；重复调用无副作用（`connect()` 自己会建目录）。"""
    with _LOCK:
        conn = connect()
        try:
            conn.executescript(SCHEMA)
            migrate(conn)
            conn.commit()
        finally:
            conn.close()
