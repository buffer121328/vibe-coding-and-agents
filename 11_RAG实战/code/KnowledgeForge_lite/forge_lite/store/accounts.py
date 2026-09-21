"""accounts.py —— 账号与会话：注册、登录、登出。

蒸馏来源：完整版 ``auth/user_service.py`` + ``auth/jwt_service.py`` + ``api/routers/auth.py``。
对应教程：11.13（多租户：身份是权限的起点）。

完整版用 JWT + PostgreSQL + 令牌黑名单。Lite 用**服务端会话表**——不是偷懒，
而是这件事上更简单的做法恰好更安全：

- 口令用 ``pbkdf2_hmac`` 加盐迭代（标准库，不引依赖），逐条比对时用 ``compare_digest``；
- 会话是**一串随机 token 存在库里的记录**，不是自包含的签名票据。
  所以"登出"就是删掉那一行——立刻失效，不用维护黑名单；
- cookie 只装 token，``HttpOnly`` + ``SameSite=Lax``，页面脚本读不到。

**不预置任何账号**：库建出来是空的，谁用谁注册。预置默认口令的账号（哪怕只在文档里
写着）等于给系统留一把人人都知道的钥匙，而课堂又不需要它——注册表里就能直接挑角色，
四种身份都开得出来。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import config

PBKDF2_ROUNDS = 200_000
SESSION_DAYS = 14

# 注册时可选的身份——**就是 identity.USERS 的四张工牌，一个不多一个不少**。
#
# 为什么是"身份"而不是分开的"角色 + 部门"两个下拉：权限由 (角色, 部门) 这一对决定，
# 而工牌空间里只有四种组合。让用户自由拼 3×4 = 12 种，其中 8 种在工牌表里查不到，
# 只能回落——曾经就踩过：选「公司管理员 + IT」（IT 还是部门下拉的默认值）会回落到
# IT 员工的工牌，于是这个"管理员"进不去知识文档和评测治理。
# 与其在回落处打补丁，不如让表单根本拼不出不存在的组合。
IDENTITIES: dict[str, dict[str, str]] = {
    "admin": {"label": "公司管理员", "role": "company_admin", "department": "company",
              "blurb": "不过滤部门。知识文档和评测治理都能进。"},
    "finance_head": {"label": "财务负责人", "role": "department_head", "department": "finance",
                     "blurb": "看得见财务密级文档；看不见 IT 的故障单。"},
    "it_staff": {"label": "IT 员工", "role": "employee", "department": "it",
                 "blurb": "看得见 IT 故障单；看不见财务密级。"},
    "hr_staff": {"label": "人事员工", "role": "employee", "department": "hr",
                 "blurb": "只看得见公开文档；IT 和财务的都看不见。"},
}

DEPARTMENTS = {"company": "公司", "finance": "财务", "it": "IT", "hr": "人事"}


class AccountError(ValueError):
    """注册/登录失败。

    消息直接给页面看，所以写成人话，不裹技术细节、不带字段名。
    """


@dataclass(frozen=True)
class Account:
    """一个登录账号。它是权限的起点：``role`` 决定看得见哪些部门。

    ``username`` 登录名（主键）；``display_name`` 页面上显示的名字；
    ``role`` 角色（company_admin / department_head / employee）；
    ``department`` 所属部门。两者由注册时选的身份决定，不单独传。
    """

    username: str
    display_name: str
    role: str
    department: str

    @property
    def badge_id(self) -> str:
        """这个账号对应哪张演示工牌（``identity.USERS`` 里的 key）。

        登录后工牌架的初始选中项就是它——身份来自账号，不是页面上的开关。
        注册时只能从 ``IDENTITIES`` 的四张牌里挑，所以角色的每一对 (role, department)
        都必在表内，这里不需要回落（以前有回落，正是那个回落把管理员降成了 IT 员工）。
        """
        for key, spec in IDENTITIES.items():
            if spec["role"] == self.role and spec["department"] == self.department:
                return key
        # 兜底只可能在"账号不是注册出来的"情况下触发（手工改库），退回最小可见范围
        return "it_staff"

    @property
    def role_label(self) -> str:
        """角色的中文名，用来填顶栏。查不到就原样返回角色键。"""
        return {"company_admin": "公司管理员", "department_head": "部门负责人",
                "employee": "员工"}.get(self.role, self.role)

    @property
    def department_label(self) -> str:
        """部门的中文名。查不到就原样返回部门键。"""
        return DEPARTMENTS.get(self.department, self.department)

    def as_dict(self) -> dict[str, Any]:
        """给前端的扁平的字典：账号 + 角色的中文名 + 对应哪张工牌。"""
        return {
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "role_label": self.role_label,
            "department": self.department,
            "department_label": self.department_label,
            "badge_id": self.badge_id,
        }


def db_path() -> Path:
    """账号库的位置：``runtime/accounts.sqlite``，跟着其它运行产物一起不入库。"""
    return config.RUNTIME_DIR / "accounts.sqlite"


def _connect(path: Path | None = None) -> sqlite3.Connection:
    """开一个 SQLite 连接并建好目录。

    ``path`` 是库文件路径；不传就用 ``db_path()``。测试会传临时路径，
    所以每个公开函数都留了这个口子——避免测试去碰真实的运行产物。
    """
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path | None = None) -> None:
    """建表（幂等）。账号表存身份，会话表存"谁在登录状态"。

    ``path`` 是库文件路径，不传用默认库；建表用 ``IF NOT EXISTS``，重复调用无副作用。
    """
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                username      TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name  TEXT NOT NULL,
                role          TEXT NOT NULL,
                department    TEXT NOT NULL,
                created_at    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            """
        )


# ── 口令 ────────────────────────────────────────────────────────


def hash_password(password: str, *, rounds: int = PBKDF2_ROUNDS) -> str:
    """把明文口令变成可入库的摘要串。

    ``password`` 是明文口令，长度校验由调用方（``register``）负责。
    ``rounds`` 是 PBKDF2 迭代轮数，默认 20 万；测试会调小，否则每次注册都要等一秒。
    返回 ``pbkdf2_sha256$轮数$盐$摘要``：盐随口令现生成，所以同一个口令两次入库结果不同。
    """
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """核对口令。

    ``password`` 是这次输入的明文；``stored`` 是库里那条 ``pbkdf2_sha256$...`` 串。
    用 ``compare_digest`` 而不是 ``==``：等时比较，不靠耗时泄露对了几位。
    摘要串格式不对（旧格式、被改坏）一律当不通过，不抛异常。
    """
    try:
        algorithm, rounds, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def _check_credentials(username: str, password: str) -> tuple[str, str]:
    """注册时的字段校验，规则只写在这里，接口层不再重复一遍。

    ``username`` 要求 3–24 个字符、只含字母数字下划线短横线——挡住空名和奇怪字符；
    ``password`` 至少 6 位。返回清洗后的 ``(用户名, 口令)``，校验不过抛 ``AccountError``。
    """
    name = (username or "").strip()
    if not (3 <= len(name) <= 24):
        raise AccountError("用户名要 3–24 个字符。")
    if not all(char.isalnum() or char in "_-" for char in name):
        raise AccountError("用户名只能用字母、数字、下划线和短横线。")
    if len(password or "") < 6:
        raise AccountError("密码至少 6 位。")
    return name, password


# ── 账号 ────────────────────────────────────────────────────────


def _row_to_account(row: sqlite3.Row) -> Account:
    """把 ``accounts`` 表的一行转成 ``Account``。

    ``row`` 是 sqlite3 的行对象，需要含 username / display_name / role / department 四列。
    """
    return Account(row["username"], row["display_name"], row["role"], row["department"])


def register(username: str, password: str, display_name: str = "",
             identity: str = "it_staff", path: Path | None = None) -> Account:
    """注册一个账号。身份从 ``IDENTITIES`` 的四张工牌里挑一张。

    ``username`` 登录名，3–24 字符；``password`` 至少 6 位；
    ``display_name`` 页面上显示的名字，留空就用用户名；
    ``identity`` 是工牌 id（``admin`` / ``finance_head`` / ``it_staff`` / ``hr_staff``），
    角色与部门由它决定——不给调用方分开传的机会，就不会拼出工牌表里不存在的组合；
    ``path`` 是库文件路径（测试用）。
    用户名重复、字段不合法都抛 ``AccountError``，消息直接给页面看。
    """
    name, password = _check_credentials(username, password)
    spec = IDENTITIES.get(identity)
    if spec is None:
        raise AccountError("请选择一种身份。")
    role, dept = spec["role"], spec["department"]
    label = (display_name or "").strip() or name
    if len(label) > 24:
        raise AccountError("显示名最长 24 个字符。")

    init_db(path)
    with _connect(path) as conn:
        if conn.execute("SELECT 1 FROM accounts WHERE username = ?", (name,)).fetchone():
            raise AccountError(f"用户名「{name}」已经有人用了。")
        conn.execute(
            "INSERT INTO accounts (username, password_hash, display_name, role, department, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, hash_password(password), label, role, dept, time.time()),
        )
    return Account(name, label, role, dept)


def authenticate(username: str, password: str, path: Path | None = None) -> Account | None:
    """核对用户名口令，对了返回账号，不对返回 ``None``。

    查不到用户和口令错都返回 ``None``——不区分这两种情况，
    否则登录接口就成了"这个用户名存不存在"的探测器。
    ``username`` / ``password`` 是表单值；``path`` 是库文件路径（测试用）。
    """
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM accounts WHERE username = ?",
                           ((username or "").strip(),)).fetchone()
    if not row or not verify_password(password or "", row["password_hash"]):
        return None
    return _row_to_account(row)


# ── 会话 ────────────────────────────────────────────────────────


def create_session(username: str, path: Path | None = None, days: int = SESSION_DAYS) -> str:
    """给某个账号开一个会话，返回要写进 cookie 的 token。

    ``username`` 是账号名；``path`` 是库文件路径（测试用）；
    ``days`` 是有效期天数，默认 14 天。
    token 是 ``secrets.token_urlsafe(32)`` 现生成的，库里存的是它本身——
    所以登出只要删这一行，不用维护黑名单。
    """
    init_db(path)
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _connect(path) as conn:
        conn.execute("INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (token, username, now, now + days * 86400))
    return token


def read_session(token: str, path: Path | None = None) -> Account | None:
    """凭 token 取账号，取不到返回 ``None``。

    ``token`` 是 cookie 里那串；``path`` 是库文件路径（测试用）。
    过期就地把那一行删掉——过期记录堆在库里没人看，等于没写过期时间。
    """
    if not token:
        return None
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row:
            return None
        if float(row["expires_at"]) < time.time():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        account = conn.execute("SELECT * FROM accounts WHERE username = ?", (row["username"],)).fetchone()
    return _row_to_account(account) if account else None


def drop_session(token: str, path: Path | None = None) -> None:
    """登出：删掉这一个会话。

    ``token`` 是要作废的那串（空值直接返回）；``path`` 是库文件路径（测试用）。
    只删自己这一条，别的设备还登着就继续登着。
    """
    if not token:
        return
    with _connect(path) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def purge_expired(path: Path | None = None) -> int:
    """清掉所有过期会话，返回删了几条。

    ``path`` 是库文件路径（测试用）。读会话时会顺手删自己那一条，
    这个函数是给运维用的整表清理。
    """
    with _connect(path) as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    return cursor.rowcount
