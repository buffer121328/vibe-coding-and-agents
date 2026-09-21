"""conversations.py —— 会话柜：问答写进磁盘，刷新还在；工牌之间互相看不见。

蒸馏来源：完整版 ``PostgreSQLQAHistoryRepository``（create / list / get / record / delete / feedback）。
对应教程：11.13（服务化：服务端才是历史的权威来源，浏览器 localStorage 只能记“打开哪一柜”）。

完整版用 PostgreSQL + 租户 + JWT 用户。Lite 用 SQLite 落在 ``runtime/conversations.sqlite``，
思想必须同构：

1. **服务端权威**：刷新、换浏览器、重启进程，只要库文件还在，会话就在。
2. **工牌隔离**：list / get / delete / 写消息都带 ``user_id``。IT 员工打不开财务负责人的柜子。
3. **软删除**：柜子标记 deleted，正文抹成空字符串——不是物理 DROP，审计还能看见“曾经有过”。
4. **先问后写**：问答主链路失败不写半条消息；成功后同一把锁里写入 user + assistant + run。

浏览器只许记住 ``user_id`` 和当前 ``conversation_id`` 指针。指针指错（换了工牌、柜子被删），
前端必须当没选中，重新拉属于这张工牌的列表——**指针不是权限**。
"""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .. import config
from ..core.identity import Actor, resolve_actor
from ..core.labels import intent_text
from ..core.quality import mask_pii


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    intent TEXT NOT NULL DEFAULT '',
    routes TEXT NOT NULL DEFAULT '',
    warn TEXT NOT NULL DEFAULT '',
    citations TEXT NOT NULL DEFAULT '[]',
    contexts TEXT NOT NULL DEFAULT '[]',
    queries TEXT NOT NULL DEFAULT '[]',
    evidence TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    rating TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, run_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_conv_owner
    ON conversations (tenant_id, user_id, deleted_at, updated_at, id);
CREATE INDEX IF NOT EXISTS idx_msg_conv
    ON messages (tenant_id, conversation_id, sequence);
CREATE INDEX IF NOT EXISTS idx_run_conv
    ON runs (tenant_id, conversation_id, created_at);
"""

ALLOWED_ROLES = {"user", "assistant"}
ALLOWED_RATINGS = {"up", "down", "issue"}
ALLOWED_STATUS = {"active", "deleted"}
TITLE_MAX = 120
NOTE_MAX = 1000
CONTENT_MAX = 20000
PAGE_MAX = 100


class ConversationError(LookupError):
    """柜子不存在、不属于这张工牌、或已经软删除。对外不暴露库表细节。"""


class ConversationConflict(ValueError):
    """入参不合法：空标题、未知评分、游标损坏。"""


def _now() -> datetime:
    """当前时刻，带 UTC 时区。

    柜子列表按 ``updated_at`` 排序、游标按它翻页，时间戳必须能直接比大小，
    所以一律回 aware 对象，绝不用裸 ``datetime.now()``：裸值一旦混进来，
    排序会在"有没有时区"上出错，而且错得很安静。
    """
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    """把时间对象存成 UTC ISO 字符串——库里所有时间列的统一写法。

    ``moment`` 是要格式化的时间；没带时区的按 UTC 解释，再统一转成 UTC 输出，
    与 ``_parse_iso`` 正好配成一对，保证"存进去什么样、读出来什么样"。
    返回可直接塞进 TEXT 列的字符串。
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    """把库里读出来的 ISO 字符串还原成 aware 时间对象。

    ``value`` 是 ``_iso`` 写进去的那种字符串。老记录可能不带时区，一律按 UTC 补齐——
    补成当地时间会让同一行的排序随部署机器的时区漂移。返回 UTC 的 aware ``datetime``。
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def encode_cursor(updated_at: str, conversation_id: str) -> str:
    """把（更新时间, 柜子号）打成不透明游标。完整版同款：客户端不许自己拼时间。

    ``updated_at`` 是上一页最后一条的更新时间，``conversation_id`` 是它的柜子号——
    两个一起才能唯一定位翻页起点（同一时刻可能有多条，只给时间会漏或重）。
    做成 base64 不透明串是为了让客户端**别去解读**它：翻页只认服务端发的游标，
    前端一旦自己拼时间，就等于在客户端复制了一份排序规则，规则改了就悄悄分叉。
    返回可原样回传的游标字符串（去掉了 base64 的 ``=`` 填充，省得在 URL 里被转义）。
    """
    raw = json.dumps([updated_at, conversation_id], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, str]:
    """解析游标。损坏就当入参错误，不要 500。

    ``value`` 是 ``encode_cursor`` 发出去、又被原样传回来的那串。解不开（被截断、
    被手改、传了空串）一律抛 ``ConversationConflict``：游标是外部输入，坏了属于
    "你参数不对"，让它变成 500 只会让人以为服务端崩了。返回
    ``(更新时间, 柜子号)``，时间已还原成 aware ``datetime``。
    """
    try:
        padding = "=" * (-len(value) % 4)
        timestamp, conversation_id = json.loads(base64.urlsafe_b64decode(value + padding))
        return _parse_iso(str(timestamp)), str(conversation_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ConversationConflict("会话游标无效") from exc


def make_id(prefix: str) -> str:
    """生成带前缀的主键，形如 ``conv_3f9a…``。

    ``prefix`` 是实体类别（``conv`` / ``msg`` / ``run`` / ``feedback``）。前缀不是装饰：
    日志里扫一眼就知道这串 id 指的是柜子还是消息，前端也能按前缀分流，
    免得拿到一个 id 还要回查一张表才知道它是什么。返回 ``前缀_32位十六进制`` 的新 id。
    """
    return f"{prefix}_{uuid4().hex}"


def default_title(question: str) -> str:
    """用第一句问当柜子名。空问不能开柜——否则刷新后一排「未命名」。

    ``question`` 是用户原问题；换行和多余空白会先压成单个空格（问句可能从多行输入框来，
    带一串换行会让列表页排版炸掉），再截到 ``TITLE_MAX``。问句为空或只有空白时抛
    ``ConversationConflict``：空标题的柜子在后端没法认、在前端没法点，不如当场拒掉。
    返回可直接入库的标题。
    """
    text = " ".join((question or "").split())
    if not text:
        raise ConversationConflict("空问题不能开新会话")
    return text[:TITLE_MAX]


def _ensure_runs_columns(conn: sqlite3.Connection) -> None:
    """给老库补 ``runs.evidence`` 列。新建库走 ``SCHEMA_SQL``，这一步是空操作。

    ``conn`` 是已经打开的 SQLite 连接。``CREATE TABLE IF NOT EXISTS`` 不会给已有表加列，
    课堂上一份 ``runtime/conversations.sqlite`` 可能是修这个字段之前建的——不补的话，
    后面 ``INSERT`` 会炸在 "no such column: evidence"，刷新轨迹抽屉也就跟着挂。
    已有列时 ``ALTER TABLE`` 会报 duplicate column，吃掉即可。
    """
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN evidence TEXT NOT NULL DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass


def _json_dump(value: Any) -> str:
    """把结构化数据压成紧凑 JSON 存进 TEXT 列。

    ``value`` 是任意可序列化的东西（引用、上下文摘要、查询列表）。不用默认分隔符，
    是因为那些空格白占库体积，而这份 JSON 只有程序读、没人肉眼看。
    返回不带多余空白的 JSON 字符串。
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str, fallback: Any) -> Any:
    """从 TEXT 列读回结构化数据，坏值退回 ``fallback`` 而不是抛异常。

    ``value`` 是列里的原始字符串（可能是空串或历史坏行），``fallback`` 是解析不出来时
    该给的东西。读取路径上不该为一行坏 JSON 让整个会话详情打不开——老记录的列可能是空串，
    也可能被降级写入写坏，退回空列表/空字典比 500 有用得多。返回解析结果或 ``fallback``。
    """
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


@dataclass
class Conversation:
    """一格柜子的名片。正文在 messages 里，不塞进列表接口。

    ``id`` 是柜子号；``user_id`` 是柜主工牌；``title`` 是显示名（第一句问或用户改过的名字）；
    ``status`` 取 ``active`` / ``deleted``；表里另有 ``deleted_at`` 记删除时刻，名片上不带它——
    前端只需要知道这格柜子还在不在。``created_at`` 与 ``updated_at`` 是 UTC ISO 字符串，
    后者既是列表排序键也是游标的一部分；``tenant_id`` 是租户标识，Lite 只有一个租户，
    但字段照留，好让按租户过滤的条件不会在某次重构里被顺手删掉。
    """

    id: str
    user_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    tenant_id: str = config.TENANT_ID

    def as_dict(self) -> dict[str, Any]:
        """摊平成列表接口直接能吐的字典。

        这里是名片原样导出，不裁剪也不补正文——列表接口只该背名片，正文留给
        "打开柜子"那个接口，否则一屏 20 格柜子就是 20 份正文。
        """
        return asdict(self)


@dataclass
class Message:
    """一条气泡。助手气泡的 payload 带着引用、路由、状态，刷新后证据抽屉还能还原。

    ``id`` 是消息号；``conversation_id`` 说明它属于哪格柜子；``sequence`` 是格内序号
    （从 1 递增，问与答各占一号，按它排序就是对话顺序）；``role`` 只取 ``user`` /
    ``assistant``；``content`` 是正文；``created_at`` 是 UTC ISO 字符串；
    ``payload`` 是助手气泡的附加档案（引用、上下文摘要、warn 等），用户气泡恒为空字典。
    """

    id: str
    conversation_id: str
    sequence: int
    role: str
    content: str
    created_at: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """摊平气泡，并把 ``payload`` 里的字段提到顶层。

        提上来而不是嵌一层，是为了对齐完整版的响应形状：前端读 ``citations`` / ``routes``
        不必先判断自己手上这条是"历史消息"还是"刚生成的消息"。同名键以 ``payload`` 为准。
        """
        data = asdict(self)
        data.update(self.payload or {})
        return data


@dataclass
class RunRecord:
    """一次问答的体检单：状态、三路路由、引用、喂给模型的上下文摘要。

    ``id`` 是这次问答的记录号（反馈要挂在它上面）；``conversation_id`` / ``user_id``
    说明它属于哪格柜子、哪张工牌；``question`` 是原问题；``status`` 是最终结论
    （``ok`` / ``refuse``）；``intent`` 是意图键，``routes`` 是走通的检索通道；
    ``warn`` 是累计提示（落盘前已脱敏）；``citations`` / ``contexts`` / ``queries``
    在入库时压成了 JSON，``_row_run`` 读出来已经还原成列表；``evidence`` 是证据资格
    结论（同样压成 JSON）——轨迹面板刷新后要靠它还原「资料够不够答」，不能拿
    ``status``（``ok`` / ``refuse``）去顶替；``created_at`` 是 UTC ISO 字符串。
    """

    id: str
    conversation_id: str
    user_id: str
    question: str
    status: str
    intent: str
    routes: str
    warn: str
    citations: list[Any]
    contexts: list[Any]
    queries: list[Any]
    evidence: dict[str, Any]
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        """摊平成轨迹面板与导出用的字典；三个列表字段出库时就解好了 JSON，这里不再动。"""
        return asdict(self)


@dataclass
class ConversationPage:
    """一页柜子列表：``items`` 是本页的名片，``next_cursor`` 是翻下一页的凭据。

    ``next_cursor`` 为 None 表示已经翻到底——前端据此收起"加载更多"，不必靠
    "这页是不是空的"去猜，而刚取满一整页时那种猜法必然出错。
    """

    items: list[Conversation]
    next_cursor: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """按接口形状序列化：``items`` 逐个转字典，``next_cursor`` 原样带出（可为 None）。"""
        return {"items": [item.as_dict() for item in self.items], "next_cursor": self.next_cursor}


@dataclass
class ConversationDetail:
    """打开一格柜子的全套内容：``conversation`` 是名片，``messages`` 是气泡时间线，
    ``runs`` 是这格柜子里的问答体检单（轨迹面板靠它还原，不用重跑检索）。

    三份分开放而不是拼成一个列表，是因为前端要按类型分别渲染：名片做标题栏、
    气泡按 role 左右分栏、run 行喂给轨迹页——混在一起就得靠字段嗅探去猜类型。
    """

    conversation: Conversation
    messages: list[Message]
    runs: list[RunRecord]

    def as_dict(self) -> dict[str, Any]:
        """把名片、气泡、run 行三份分别转字典，键名即前端约定的三个字段名。"""
        return {
            "conversation": self.conversation.as_dict(),
            "messages": [item.as_dict() for item in self.messages],
            "runs": [item.as_dict() for item in self.runs],
        }


class ConversationStore:
    """SQLite 会话柜。完整版是 PostgreSQL；Lite 换柜子不换规矩。

    ``path`` 是库文件位置，不传走 ``config.CONVERSATIONS_DB``；``tenant_id`` 是租户标识，
    不传走 ``config.TENANT_ID``——Lite 只有一个租户，但每行照样写它，好让"按租户过滤"
    这个条件不会在某次重构里被顺手删掉。连接懒建（``_conn`` 先为 None），
    全程由 ``_lock`` 串起来：SSE 推送线程和请求线程会同时来读写，SQLite 的单连接
    必须自己排好队，不能指望驱动替你管。
    """

    def __init__(self, path: str | Path | None = None, tenant_id: str | None = None) -> None:
        """记住库文件位置与租户，备好锁；此时数据库文件还没建。

        ``path`` 传了就另开一份库（测试的临时库靠它互相隔离），``tenant_id`` 同理。
        用 ``RLock`` 而不是普通 ``Lock``：有些公开方法会调另一个公开方法
        （比如导出一格一格地打开柜子），同一线程得能重复进锁。
        """
        self.path = Path(path) if path else config.CONVERSATIONS_DB
        self.tenant_id = tenant_id or config.TENANT_ID
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        """懒建并缓存连接：建目录、开 WAL、设超时，只在第一次真正读写时执行。

        ``check_same_thread=False`` 是必须的：连接由 ``_lock`` 统一保护，而用它的线程
        不止一个（请求线程 + SSE 推送）。WAL 让读不被写阻塞，``busy_timeout`` 给并发写
        留出等待窗口而不是立刻甩一句 database is locked。返回缓存的连接，已建过就复用。
        """
        if self._conn is not None:
            return self._conn
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(SCHEMA_SQL)
        _ensure_runs_columns(conn)
        self._conn = conn
        return conn

    def close(self) -> None:
        """关掉连接并清掉缓存，库文件不动，下次调用会重连。

        测试夹具和进程收尾用它释放文件句柄；把 ``_conn`` 置回 None 是为了让这个实例
        还能继续用——关掉之后再发一次查询，不该炸在"操作已关闭的连接"上。
        """
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _owner(self, user_id: str | Actor | None) -> Actor:
        """把外部传进来的身份统一解析成 ``Actor``。

        ``user_id`` 可能是 id 字符串、``Actor``，也可能是 None（走默认工牌）。
        每个公开方法开头都先过这一道，好过在每个方法里各写一遍类型判断：身份解析
        散着写，早晚有一处漏掉，而漏掉的那处就是越权口子。返回解析好的 ``Actor``。
        """
        return resolve_actor(user_id)

    def _row_conversation(self, row: sqlite3.Row) -> Conversation:
        """数据库行 → ``Conversation`` 名片。

        ``row`` 是一条 ``conversations`` 行。``tenant_id`` 也照行里的值取，而不是回填
        ``self.tenant_id``：将来真做跨租户的管理视图时，这里不会张冠李戴。
        """
        return Conversation(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tenant_id=row["tenant_id"],
        )

    def _row_message(self, row: sqlite3.Row) -> Message:
        """数据库行 → ``Message`` 气泡。

        ``row`` 是一条 ``messages`` 行。``sequence`` 显式转 int：SQLite 是弱类型，
        列里到底存过什么类型只有运行时才知道，而排序时字符串会给出 10 排在 2 前面这种结果。
        ``payload`` 解析失败退回空字典，至少让气泡正文还能显示。
        """
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            sequence=int(row["sequence"]),
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            payload=_json_load(row["payload"], {}),
        )

    def _row_run(self, row: sqlite3.Row) -> RunRecord:
        """数据库行 → ``RunRecord`` 体检单。

        ``row`` 是一条 ``runs`` 行。四个 JSON 列（``citations`` / ``contexts`` /
        ``queries`` / ``evidence``）在这里一次解析完，后面用的人不必各自记得解。
        老记录里可能是空串或缺列，解析失败一律退回空容器——轨迹面板宁可缺一块，
        也不该整页打不开。``evidence`` 用 ``keys()`` 探测列在不在：补列之前的老库
        读出来没有这个键，不能拿 ``row["evidence"]`` 去炸。
        """
        evidence_raw = row["evidence"] if "evidence" in row.keys() else "{}"
        return RunRecord(
            id=row["id"],
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            question=row["question"],
            status=row["status"],
            intent=row["intent"] or "",
            routes=row["routes"] or "",
            warn=row["warn"] or "",
            citations=_json_load(row["citations"], []),
            contexts=_json_load(row["contexts"], []),
            queries=_json_load(row["queries"], []),
            evidence=_json_load(evidence_raw, {}),
            created_at=row["created_at"],
        )

    def create_conversation(
        self,
        user_id: str | Actor | None,
        title: str = "",
    ) -> Conversation:
        """开一格空柜子。标题可空，等第一问再改成问句。

        ``user_id`` 是柜主工牌（id / ``Actor`` / None），决定这柜子归谁；
        ``title`` 是可选的初始名字，空白或没传就记成「新会话」——这个占位串会在
        ``record_answer`` 里被第一句问顶掉。传进来的标题会压平空白并截到 ``TITLE_MAX``。
        返回刚建好的 ``Conversation``（含生成的 id 与时间戳）。
        """
        actor = self._owner(user_id)
        now = _iso(_now())
        label = " ".join((title or "").split())[:TITLE_MAX] or "新会话"
        record = Conversation(
            id=make_id("conv"),
            user_id=actor.user_id,
            title=label,
            status="active",
            created_at=now,
            updated_at=now,
            tenant_id=self.tenant_id,
        )
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO conversations "
                "(id, tenant_id, user_id, title, status, created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (record.id, record.tenant_id, record.user_id, record.title,
                 record.status, record.created_at, record.updated_at),
            )
        return record

    def list_conversations(
        self,
        user_id: str | Actor | None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> ConversationPage:
        """只列出这张工牌、未删除的柜子。倒序：刚问过的排最前。

        ``user_id`` 是查列表的工牌——过滤条件里锁死它，翻页翻得再深也翻不出别人的柜子；
        ``limit`` 是每页条数，会被夹到 1..``PAGE_MAX``（内部分页总有上限，放行 1000
        只会让前端拿到一坨）；``cursor`` 是上一页回传的游标，不传就从头开始。

        翻页走 keyset（``updated_at`` + ``id`` 双键）而不是 OFFSET：课堂演示里同时有人
        提问时，OFFSET 会被新增记录顶得整页后移、出现重复或漏项，而 keyset 锚在具体的行上，
        前面插入多少条都不影响下一页。查询多取一条只为探 ``has_more``——
        只看"这页有没有取满"会在刚好取满时多吐一个空页。返回 ``ConversationPage``；
        ``cursor`` 损坏时抛 ``ConversationConflict``。
        """
        actor = self._owner(user_id)
        bounded = min(max(int(limit), 1), PAGE_MAX)
        params: list[Any] = [self.tenant_id, actor.user_id]
        where = "tenant_id = ? AND user_id = ? AND deleted_at IS NULL"
        if cursor:
            updated_at, conversation_id = decode_cursor(cursor)
            where += " AND (updated_at < ? OR (updated_at = ? AND id < ?))"
            stamp = _iso(updated_at)
            params.extend([stamp, stamp, conversation_id])
        sql = (
            f"SELECT * FROM conversations WHERE {where} "
            "ORDER BY updated_at DESC, id DESC LIMIT ?"
        )
        params.append(bounded + 1)
        with self._lock:
            rows = self._connect().execute(sql, params).fetchall()
        has_more = len(rows) > bounded
        items = [self._row_conversation(row) for row in rows[:bounded]]
        next_cursor = encode_cursor(items[-1].updated_at, items[-1].id) if has_more and items else None
        return ConversationPage(items=items, next_cursor=next_cursor)

    def get_conversation(
        self,
        conversation_id: str,
        user_id: str | Actor | None,
    ) -> ConversationDetail:
        """打开一格属于自己的柜子。别人的、删掉的，一律当不存在。

        ``conversation_id`` 是要打开的柜子号，``user_id`` 是开柜的工牌。归属条件直接写进
        WHERE，于是"不是自己的柜子"和"压根不存在的柜子"走同一个分支、报同一句
        「会话不存在」——**不泄露存在性**：若两者话术不同，拿 id 撞库就能问出
        公司里有没有这格柜子。``deleted_at IS NULL`` 把软删除的也归进同一句话术。

        返回 ``ConversationDetail``（名片 + 气泡 + run 行）；柜子不存在或不属于这张工牌时
        抛 ``ConversationError``。
        """
        actor = self._owner(user_id)
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ? AND tenant_id = ? "
                "AND user_id = ? AND deleted_at IS NULL",
                (conversation_id, self.tenant_id, actor.user_id),
            ).fetchone()
            if row is None:
                raise ConversationError("会话不存在")
            messages = conn.execute(
                "SELECT * FROM messages WHERE tenant_id = ? AND conversation_id = ? "
                "ORDER BY sequence ASC",
                (self.tenant_id, conversation_id),
            ).fetchall()
            runs = conn.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND conversation_id = ? "
                "AND user_id = ? ORDER BY created_at ASC",
                (self.tenant_id, conversation_id, actor.user_id),
            ).fetchall()
        return ConversationDetail(
            conversation=self._row_conversation(row),
            messages=[self._row_message(item) for item in messages],
            runs=[self._row_run(item) for item in runs],
        )

    def rename_conversation(
        self,
        conversation_id: str,
        user_id: str | Actor | None,
        title: str,
    ) -> Conversation:
        """改柜子名，顺带把 ``updated_at`` 顶到最前——改过名也算"刚动过"。

        ``conversation_id`` 是要改的柜子，``user_id`` 是操作人（必须是柜主），
        ``title`` 是新名字，会压平空白并截到 ``TITLE_MAX``。标题为空或全空白时抛
        ``ConversationConflict``（名字是列表页上唯一的识别物，不能空着）。

        归属校验靠 UPDATE 的 ``rowcount`` 判定，而不是"先查再写"：两次查询之间
        柜子可能被别处删掉，那样就会写回一个已经不在的柜子。
        返回更新后的 ``Conversation``；柜子不存在或不属于这张工牌时抛 ``ConversationError``。
        """
        actor = self._owner(user_id)
        label = " ".join((title or "").split())[:TITLE_MAX]
        if not label:
            raise ConversationConflict("会话标题不能为空")
        now = _iso(_now())
        with self._lock:
            conn = self._connect()
            cur = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? "
                "WHERE id = ? AND tenant_id = ? AND user_id = ? AND deleted_at IS NULL",
                (label, now, conversation_id, self.tenant_id, actor.user_id),
            )
            if cur.rowcount != 1:
                raise ConversationError("会话不存在")
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return self._row_conversation(row)

    def delete_conversation(
        self,
        conversation_id: str,
        user_id: str | Actor | None,
    ) -> list[str]:
        """软删除：柜子消失，正文抹空。返回被牵连的 run_id，方便前端丢掉反馈按钮。

        ``conversation_id`` 是要删的柜子，``user_id`` 是操作人（必须柜主，非柜主与不存在
        一样抛 ``ConversationError``——同样的不泄露存在性）。抹掉的是气泡正文与 payload、
        run 的问题与引用上下文，行本身和 ``status='deleted'`` 标记留着：审计上还看得见
        "这里曾经有过一格柜子"，物理 DROP 做不到这一点。先取 run_id 再抹正文，
        否则删除动作一执行，那串 id 就再也查不着了。返回这格柜子的 run_id 列表。
        """
        actor = self._owner(user_id)
        now = _iso(_now())
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT id FROM conversations WHERE id = ? AND tenant_id = ? "
                "AND user_id = ? AND deleted_at IS NULL",
                (conversation_id, self.tenant_id, actor.user_id),
            ).fetchone()
            if row is None:
                raise ConversationError("会话不存在")
            run_ids = [
                item["id"]
                for item in conn.execute(
                    "SELECT id FROM runs WHERE tenant_id = ? AND conversation_id = ?",
                    (self.tenant_id, conversation_id),
                ).fetchall()
            ]
            conn.execute(
                "UPDATE conversations SET status = 'deleted', deleted_at = ?, updated_at = ? "
                "WHERE id = ? AND tenant_id = ?",
                (now, now, conversation_id, self.tenant_id),
            )
            conn.execute(
                "UPDATE messages SET content = '', payload = '{}' "
                "WHERE tenant_id = ? AND conversation_id = ?",
                (self.tenant_id, conversation_id),
            )
            conn.execute(
                "UPDATE runs SET warn = '', citations = '[]', contexts = '[]', question = '', evidence = '{}' "
                "WHERE tenant_id = ? AND conversation_id = ?",
                (self.tenant_id, conversation_id),
            )
        return run_ids

    def _require_owned(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
        user_id: str,
    ) -> sqlite3.Row:
        """在调用方的事务里校验柜子归属，拿到就返回该行，否则抛 ``ConversationError``。

        ``conn`` 是已经在事务里的连接（所以校验收到的结论和随后的写入同生共死，
        不会出现"校验通过之后柜子被人删了"的窗口）；``conversation_id`` 是目标柜子；
        ``user_id`` 是柜主 id——这里只收解析好的字符串，身份解析由调用方负责。
        返回 ``conversations`` 行，供调用方接着读标题。
        """
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ? AND tenant_id = ? "
            "AND user_id = ? AND deleted_at IS NULL",
            (conversation_id, self.tenant_id, user_id),
        ).fetchone()
        if row is None:
            raise ConversationError("会话不存在")
        return row

    def record_answer(
        self,
        user_id: str | Actor | None,
        question: str,
        result: dict[str, Any],
        conversation_id: str | None = None,
    ) -> tuple[str, str]:
        """把一问一答写进柜子。没有柜子就新开一格，标题取问句前 120 字。

        ``user_id`` 是提问人工牌（也是柜主）；``question`` 是原问题，压平空白后截到
        ``CONTENT_MAX``；``result`` 是 ``agent.ask`` 返回的那份扁平字典，引用、路由、
        warn、意图、上下文摘要全从它里面取；``conversation_id`` 是续聊的柜子号，
        不传（或传了个不属于这张工牌的号——调用方先查过归属才传）就新开一格。

        完整版在同一事务里写 messages + runs + sources。Lite 把引用和上下文摘要
        折进 run 行和助手消息的 payload——课堂体量，规矩一样：先校验归属再落盘。
        写入走显式事务：用户气泡、助手气泡、run 行、柜子时间戳要么全成、要么全不成，
        半条消息比没有消息更难解释；``warn`` 和反馈备注一样先过 ``mask_pii``。

        返回 ``(conversation_id, run_id)``；``question`` 为空白时抛 ``ConversationConflict``，
        ``conversation_id`` 不属于这张工牌时抛 ``ConversationError``。
        """
        actor = self._owner(user_id)
        text = " ".join((question or "").split())
        if not text:
            raise ConversationConflict("空问题不能写入会话")
        answer = str(result.get("answer") or "")[:CONTENT_MAX]
        now = _iso(_now())
        run_id = make_id("run")
        citations = result.get("citations") or []
        contexts = _summarize_contexts(result)
        intent = str(result.get("intent") or "")
        evidence = dict(result.get("evidence") or {})
        response_status = str(result.get("response_status") or evidence.get("response_status") or "")
        payload = {
            "run_id": run_id,
            "status": result.get("status") or "",
            "intent": intent,
            # 中文标签一起落盘：前端照原样显示，不去猜英文键名
            "intent_label": result.get("intent_label") or intent_text(intent),
            "routes": result.get("routes") or "",
            "warn": mask_pii(str(result.get("warn") or "")),
            "citations": citations,
            "contexts": contexts,
            "queries": result.get("queries") or [text],
            "evidence": evidence,
            "response_status": response_status,
            "response_label": str(result.get("response_label") or ""),
            "actor": result.get("actor") or {
                "user_id": actor.user_id,
                "name": actor.display_name,
                "role": actor.role,
                "department": actor.department,
            },
        }
        with self._lock:
            conn = self._connect()
            conn.execute("BEGIN")
            try:
                if conversation_id:
                    owned = self._require_owned(conn, conversation_id, actor.user_id)
                    title = owned["title"]
                    if title in {"", "新会话"}:
                        title = default_title(text)
                else:
                    conversation_id = make_id("conv")
                    title = default_title(text)
                    conn.execute(
                        "INSERT INTO conversations "
                        "(id, tenant_id, user_id, title, status, created_at, updated_at, deleted_at) "
                        "VALUES (?, ?, ?, ?, 'active', ?, ?, NULL)",
                        (conversation_id, self.tenant_id, actor.user_id, title, now, now),
                    )
                last = conn.execute(
                    "SELECT MAX(sequence) AS seq FROM messages "
                    "WHERE tenant_id = ? AND conversation_id = ?",
                    (self.tenant_id, conversation_id),
                ).fetchone()
                sequence = int(last["seq"] or 0)
                user_msg = make_id("msg")
                assistant_msg = make_id("msg")
                conn.execute(
                    "INSERT INTO messages "
                    "(id, tenant_id, conversation_id, sequence, role, content, created_at, payload) "
                    "VALUES (?, ?, ?, ?, 'user', ?, ?, '{}')",
                    (user_msg, self.tenant_id, conversation_id, sequence + 1, text[:CONTENT_MAX], now),
                )
                conn.execute(
                    "INSERT INTO messages "
                    "(id, tenant_id, conversation_id, sequence, role, content, created_at, payload) "
                    "VALUES (?, ?, ?, ?, 'assistant', ?, ?, ?)",
                    (assistant_msg, self.tenant_id, conversation_id, sequence + 2,
                     answer, now, _json_dump(payload)),
                )
                conn.execute(
                    "INSERT INTO runs "
                    "(id, tenant_id, conversation_id, user_id, question, status, intent, routes, "
                    "warn, citations, contexts, queries, evidence, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id, self.tenant_id, conversation_id, actor.user_id, text[:CONTENT_MAX],
                        str(result.get("status") or ""),
                        str(result.get("intent") or ""),
                        str(result.get("routes") or ""),
                        payload["warn"],
                        _json_dump(citations),
                        _json_dump(contexts),
                        _json_dump(payload["queries"]),
                        _json_dump(evidence),
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? "
                    "WHERE id = ? AND tenant_id = ?",
                    (title, now, conversation_id, self.tenant_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return conversation_id, run_id

    def upsert_feedback(
        self,
        run_id: str,
        user_id: str | Actor | None,
        rating: str,
        note: str = "",
    ) -> dict[str, Any]:
        """点赞 / 点踩 / 报问题。只能评自己工牌跑出来的 run。

        ``run_id`` 是被评的那次问答，``user_id`` 是评价人工牌——先把 run 的归属查一遍，
        不是自己的和不存在的一律报「问答记录不存在」。``rating`` 只认 ``up`` / ``down``
        / ``issue``（``ALLOWED_RATINGS``），写别的抛 ``ConversationConflict``；
        ``note`` 是可选的文字说明，截到 ``NOTE_MAX`` 并过 ``mask_pii``——用户很爱在这里
        贴手机号，而这份记录是要进导出的。

        一个人对同一条 run 只留一份评价（库里也有唯一约束兜底，这里按"先查再改/插"实现）：
        改主意是替换，不是叠加。返回 ``{feedback_id, qa_run_id, rating, note}``。
        """
        actor = self._owner(user_id)
        if rating not in ALLOWED_RATINGS:
            raise ConversationConflict("反馈只能是 up / down / issue")
        clipped = mask_pii((note or "")[:NOTE_MAX])
        now = _iso(_now())
        with self._lock:
            conn = self._connect()
            owned = conn.execute(
                "SELECT id FROM runs WHERE id = ? AND tenant_id = ? AND user_id = ?",
                (run_id, self.tenant_id, actor.user_id),
            ).fetchone()
            if owned is None:
                raise ConversationError("问答记录不存在")
            existing = conn.execute(
                "SELECT id FROM feedback WHERE tenant_id = ? AND run_id = ? AND user_id = ?",
                (self.tenant_id, run_id, actor.user_id),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE feedback SET rating = ?, note = ?, updated_at = ? WHERE id = ?",
                    (rating, clipped, now, existing["id"]),
                )
                feedback_id = existing["id"]
            else:
                feedback_id = make_id("feedback")
                conn.execute(
                    "INSERT INTO feedback "
                    "(id, tenant_id, run_id, user_id, rating, note, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (feedback_id, self.tenant_id, run_id, actor.user_id, rating, clipped, now, now),
                )
        return {
            "feedback_id": feedback_id,
            "qa_run_id": run_id,
            "rating": rating,
            "note": clipped,
        }

    def get_run(self, run_id: str, user_id: str | Actor | None) -> RunRecord:
        """取一条属于自己的运行记录。轨迹面板和导出都用它。

        ``run_id`` 是那条记录，``user_id`` 是查询人工牌——归属条件写进 WHERE，
        不是自己的就当不存在（同样不泄露存在性）。返回 ``RunRecord``；
        查不到时抛 ``ConversationError`` 而不是返回 None：调用方拿到 None 一定会忘了判空。
        """
        actor = self._owner(user_id)
        with self._lock:
            row = self._connect().execute(
                "SELECT * FROM runs WHERE id = ? AND tenant_id = ? AND user_id = ?",
                (run_id, self.tenant_id, actor.user_id),
            ).fetchone()
        if row is None:
            raise ConversationError("问答记录不存在")
        return self._row_run(row)

    def latest_run(self, conversation_id: str, user_id: str | Actor | None) -> RunRecord | None:
        """一格柜子最近一次问答。刷新后证据抽屉靠它还原轨迹。

        ``conversation_id`` 是要看的柜子，``user_id`` 是查询人工牌（同样按归属过滤）。
        返回最新那条 ``RunRecord``；这格柜子还没跑过问答时返回 None——新开的空柜子
        本来就是这种状态，不是错误，所以这里用 None 而不是抛异常。
        """
        actor = self._owner(user_id)
        with self._lock:
            row = self._connect().execute(
                "SELECT * FROM runs WHERE conversation_id = ? AND tenant_id = ? "
                "AND user_id = ? ORDER BY created_at DESC LIMIT 1",
                (conversation_id, self.tenant_id, actor.user_id),
            ).fetchone()
        return self._row_run(row) if row is not None else None

    def get_feedback(self, run_id: str, user_id: str | Actor | None) -> dict[str, Any] | None:
        """查自己对某条 run 投过的票。``run_id`` 是目标问答，``user_id`` 是查询人工牌。

        返回 ``{feedback_id, qa_run_id, rating, note}``；没投过票时返回 None 而不是空字典——
        页面靠 None 判断"要不要把拇指点亮"，空字典会被当成"投过票但字段都是空的"。
        """
        actor = self._owner(user_id)
        with self._lock:
            row = self._connect().execute(
                "SELECT * FROM feedback WHERE tenant_id = ? AND run_id = ? AND user_id = ?",
                (self.tenant_id, run_id, actor.user_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "feedback_id": row["id"],
            "qa_run_id": row["run_id"],
            "rating": row["rating"],
            "note": row["note"],
        }

    def cleanup_expired(self, retention_days: int) -> int:
        """课堂演示用的过期清理：超过 N 天没更新的柜子软删除。

        ``retention_days`` 是保留天数，必须大于 0，否则抛 ``ConversationConflict``——
        传 0 看着像"立刻清空"，更可能却是把配置读成了空值，这种乌龙一旦静默执行就是全库清空。
        清理走 ``delete_conversation``（软删除）而不是 DROP，行与审计痕迹都留着。
        逐条捕获 ``ConversationError`` 继续跑：并发删除抢走的那条不该让整轮清理停住。
        返回实际删掉的柜子数。
        """
        if retention_days <= 0:
            raise ConversationConflict("保留天数必须大于 0")
        cutoff = _iso(_now() - timedelta(days=retention_days))
        with self._lock:
            rows = self._connect().execute(
                "SELECT id, user_id FROM conversations "
                "WHERE tenant_id = ? AND updated_at < ? AND deleted_at IS NULL",
                (self.tenant_id, cutoff),
            ).fetchall()
        count = 0
        for row in rows:
            try:
                self.delete_conversation(row["id"], row["user_id"])
                count += 1
            except ConversationError:
                continue
        return count

    def count_for(self, user_id: str | Actor | None) -> int:
        """数这张工牌名下还有几格未删除的柜子。

        ``user_id`` 是工牌（id / ``Actor`` / None）。返回整数条数，一格都没有时返回 0
        而不是 None——调用方多半拿它做配额或空状态判断，多一层判空只是负担。
        """
        actor = self._owner(user_id)
        with self._lock:
            row = self._connect().execute(
                "SELECT COUNT(*) AS n FROM conversations "
                "WHERE tenant_id = ? AND user_id = ? AND deleted_at IS NULL",
                (self.tenant_id, actor.user_id),
            ).fetchone()
        return int(row["n"] if row else 0)

    def export_owner(self, user_id: str | Actor | None) -> list[dict[str, Any]]:
        """把这张工牌的柜子导出成 JSON 友好结构，方便课堂作业对照。

        ``user_id`` 是导出的工牌；只导属于它的、没被软删除的柜子，一页上限 ``PAGE_MAX`` 格。
        逐格调 ``get_conversation`` 而不是自己拼 SQL，是为了让导出和"打开柜子"共用同一套
        归属校验——两处各写一遍，早晚有一处会松掉。返回列表，每项是一格柜子的完整字典
        （名片 + 气泡 + run 行）。
        """
        page = self.list_conversations(user_id, limit=PAGE_MAX)
        dumped = []
        for item in page.items:
            dumped.append(self.get_conversation(item.id, user_id).as_dict())
        return dumped


_DEFAULT_STORE: ConversationStore | None = None
_DEFAULT_LOCK = threading.Lock()


def get_store(path: str | Path | None = None) -> ConversationStore:
    """进程内单例。测试传入临时路径时另开实例，不污染课堂 runtime。

    ``path`` 传了就直接新建一个 ``ConversationStore`` 返回，既不入单例也不覆盖默认那份——
    测试和临时实验要的就是"别打扰别人"。返回缓存或新建的 ``ConversationStore``；
    加锁是为了并发首调时也只建一个（两个单例同时开同一个 SQLite 文件会互相踩）。
    """
    if path is not None:
        return ConversationStore(path)
    global _DEFAULT_STORE
    with _DEFAULT_LOCK:
        if _DEFAULT_STORE is None:
            _DEFAULT_STORE = ConversationStore()
        return _DEFAULT_STORE


def reset_store_for_tests() -> None:
    """测试夹具：丢掉进程单例，避免用例互相踩库。"""
    global _DEFAULT_STORE
    with _DEFAULT_LOCK:
        if _DEFAULT_STORE is not None:
            _DEFAULT_STORE.close()
            _DEFAULT_STORE = None


def _summarize_contexts(result: dict[str, Any]) -> list[dict[str, Any]]:
    """落盘给前端点角标、画轨迹。完整版有独立 sources 表；Lite 折进 JSON。

    ``source_details``（检索明细）优先：带着每一路的名次和"为什么召回"，
    刷新后重建轨迹面板全靠它。没有明细（老记录 / 评测路径）就退回引用+片段。
    ``result`` 是 ``agent.ask`` 的返回值；片段按 500 字截断，落盘只留角标跳转需要的最小快照——
    整段原文再存一份既撑库体积，又和检索结果构成两份会各自失真的副本。
    返回可直接 ``json.dumps`` 的列表，每项含 ``doc_id`` / ``marker`` / ``snippet``。
    """
    citations = result.get("citations") or []
    contexts = result.get("contexts") or []
    details = result.get("source_details") or []
    packed: list[dict[str, Any]] = []
    if details:
        for index, item in enumerate(details):
            if not isinstance(item, dict):
                continue
            snippet = str(contexts[index])[:500] if index < len(contexts) else ""
            packed.append({
                "doc_id": item.get("doc_id") or "",
                "marker": f"[{index + 1}]",
                "snippet": snippet,
                "route": item.get("route") or "",
                "route_rank": item.get("route_rank") or 0,
                "fused_rank": item.get("fused_rank") or index + 1,
                "why": item.get("why") or "",
            })
        return packed
    if citations:
        for index, citation in enumerate(citations):
            snippet = ""
            if index < len(contexts):
                snippet = str(contexts[index])[:500]
            packed.append({
                "doc_id": citation.get("doc_id") or citation.get("source") or "",
                "marker": citation.get("marker") or f"[{index + 1}]",
                "snippet": snippet,
            })
        return packed
    for index, text in enumerate(contexts):
        packed.append({"doc_id": "", "marker": f"[{index + 1}]", "snippet": str(text)[:500]})
    return packed


def pointer_belongs(pointer: str | None, items: Iterable[Conversation]) -> str | None:
    """前端 localStorage 里的柜子号，必须能在当前工牌的列表里找到。找不到就当没选。

    ``pointer`` 是前端记着的柜子号（可能为 None 或空串），``items`` 是当前工牌这一页的
    柜子名片。返回可用的柜子号，或 None。

    为什么非要回来对一遍：指针不是权限。换张工牌、柜子被删或被人转移，localStorage 里
    那个 id 都还在，但已经不归你了——照着它去拉详情只会一路报错；在列表里对不上就
    当没选中、重新拉这张工牌的列表，用户看到的是"回到列表"而不是一个莫名其妙的错误。
    """
    if not pointer:
        return None
    allowed = {item.id for item in items}
    return pointer if pointer in allowed else None
