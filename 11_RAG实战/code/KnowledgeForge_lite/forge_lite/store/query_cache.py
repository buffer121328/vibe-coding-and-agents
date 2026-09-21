"""query_cache.py —— 课堂版精确缓存：同一张工牌、同一句问、同一份索引，才许复用。

蒸馏来源：完整版 QA 的 exact cache（语义缓存 Lite 砍掉，避免课堂上「好像命中了其实是别人的答案」）。
对应教程：11.13。缓存键必须带 ``user_id`` 和 ``INDEX_SCHEMA``：

- 不带工牌：人事可能吃到财务负责人缓存里的薪酬带宽；
- 不带 schema：重建索引后仍吐旧切块号，角标跳到已删的块。

语义相似命中完整版会弹确认。Lite 只做原文哈希，命中就复用，不命中就走完整链路。
评测 ``persist=False`` 的问答默认不写缓存，避免黄金集把演示缓存刷脏。
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config
from ..core.identity import Actor, resolve_actor
from ..core.quality import mask_pii


def cache_path() -> Path:
    """缓存的正式落盘位置：``runtime/query_cache.jsonl``（放运行时目录，不入库）。"""
    return config.RUNTIME_DIR / "query_cache.jsonl"


def _now() -> str:
    """当前 UTC 时刻的 ISO 字符串，只用来记"这条缓存什么时候写的"。"""
    return datetime.now(timezone.utc).isoformat()


def normalize_question(question: str) -> str:
    """把 ``question`` 归一化成缓存键用的形状：连续空白（含换行）压成单个空格，并去掉首尾。

    不归一化的话，"出差住一晚能报多少？" 和它在输入框里被多敲了一个空格或换行，
    会被当成两个问题各存一份缓存——课堂演示时看起来就是"缓存没命中"。
    """
    return " ".join((question or "").split())


def cache_key(user_id: str, question: str, schema: str | None = None) -> str:
    """算缓存键，返回 24 位十六进制摘要。

    ``user_id`` 是工牌（先过 ``resolve_actor``，别名写法要能落到同一张工牌上）；
    ``question`` 是原问句（内部会归一化）；``schema`` 是索引 schema，不传就取当前
    ``INDEX_SCHEMA``。

    工牌和 schema 都必须进键：少了工牌，人事可能吃到财务负责人缓存里的薪酬带宽；
    少了 schema，重建索引后仍会吐出旧切块号，角标会跳到已删的块上。
    """
    actor = resolve_actor(user_id)
    payload = "|".join([
        actor.user_id,
        schema or config.INDEX_SCHEMA,
        normalize_question(question),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass
class CacheHit:
    """一条缓存：上次过完门禁的那一问一答。

    ``key`` 是缓存键（工牌 + 问句 + schema 的摘要）；``user_id`` 是提问的工牌；
    ``question`` 是归一化后的问句；``answer`` 是答案正文（写入前已过 ``mask_pii``）；
    ``status`` 是这一跑的结局；``citations`` 是引用角标列表；``routes`` 是召回路由串；
    ``created_at`` 是写入时刻；``schema`` 是当时的索引 schema——读取时要拿它和当前值
    比对，对不上就作废。
    """

    key: str
    user_id: str
    question: str
    answer: str
    status: str
    citations: list[Any]
    routes: str
    created_at: str
    schema: str

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典，既用于写 JSONL 行，也用于体检模块统计。"""
        return asdict(self)


class QueryCache:
    """JSONL 精确缓存。键是工牌 + 问句 + 索引 schema，值是上次过门禁的答案。

    ``path`` 是缓存文件位置（不传走 ``cache_path()``）。进程内有一份内存镜像
    （``_memo``），落盘仍是 append 一行一条的 JSONL：写不阻塞读，坏了也只坏一行。

    为什么不只用内存：课上要演示"重启服务后缓存还在"；为什么不只用磁盘：
    每次问答都去读一遍文件，是拿磁盘延迟换一点内存。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        """``path`` 是缓存文件位置，不传走 ``cache_path()``。"""
        self.path = Path(path) if path else cache_path()
        self._lock = threading.Lock()
        self._memo: dict[str, CacheHit] = {}
        self._loaded = False

    def _load(self) -> None:
        """把 JSONL 一次性读进内存镜像，只做一次（``_loaded`` 记住）。

        坏行直接跳过：缓存写坏一行不该让整个服务读不出任何缓存，
        反正这一行对应的问答会重新走一遍完整链路。
        """
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            hit = CacheHit(
                key=str(row.get("key") or ""),
                user_id=str(row.get("user_id") or ""),
                question=str(row.get("question") or ""),
                answer=str(row.get("answer") or ""),
                status=str(row.get("status") or ""),
                citations=list(row.get("citations") or []),
                routes=str(row.get("routes") or ""),
                created_at=str(row.get("created_at") or ""),
                schema=str(row.get("schema") or ""),
            )
            if hit.key:
                self._memo[hit.key] = hit

    def get(self, user_id: str | Actor | None, question: str) -> CacheHit | None:
        """取缓存：``user_id`` 是工牌，``question`` 是原问句（内部归一化）。

        命中返回 ``CacheHit``，不命中（或键对不上）返回 ``None``——不抛异常，
        因为"没缓存"是最常见的情况，走完整链路就行。

        查得到之后还要**再核两遍**：工牌与 schema 有一项对不上就当作没命中。
        键本身已经含这两项，这里是第二道锁——缓存文件可能被手改过，
        也可能从别的库拷过来，宁可多比一次也不要把别人的答案端出去。
        """
        actor = resolve_actor(user_id)
        key = cache_key(actor.user_id, question)
        with self._lock:
            self._load()
            hit = self._memo.get(key)
        if hit is None:
            return None
        if hit.user_id != actor.user_id:
            return None
        if hit.schema != config.INDEX_SCHEMA:
            return None
        return hit

    def put(self, user_id: str | Actor | None, question: str, result: dict[str, Any]) -> CacheHit:
        """写缓存，返回落盘的那条 ``CacheHit``。

        ``user_id`` 是工牌，``question`` 是原问句（归一化后为空会抛 ``ValueError``——
        空问题进缓存，等于给以后任何空输入都准备了一个答案）；``result`` 是问答结果
        字典，只挑 ``answer`` / ``status`` / ``citations`` / ``routes`` 四项落盘，
        ``answer`` 先过 ``mask_pii``。

        先 append 再更新内存镜像：磁盘那行写成功了才算这条缓存存在，
        反过来（先改内存再写盘）一旦写盘失败，本次进程会以为自己有缓存。
        """
        actor = resolve_actor(user_id)
        text = normalize_question(question)
        if not text:
            raise ValueError("空问题不能进缓存")
        hit = CacheHit(
            key=cache_key(actor.user_id, text),
            user_id=actor.user_id,
            question=text,
            answer=mask_pii(str(result.get("answer") or "")),
            status=str(result.get("status") or ""),
            citations=list(result.get("citations") or []),
            routes=str(result.get("routes") or ""),
            created_at=_now(),
            schema=config.INDEX_SCHEMA,
        )
        line = json.dumps(hit.as_dict(), ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._load()
            self._memo[hit.key] = hit
        return hit

    def read_all(self) -> list[CacheHit]:
        """只读全量条目。体检模块用它统计 schema 分布，不暴露给接口。"""
        with self._lock:
            self._load()
            return list(self._memo.values())

    def drop_schema(self, schema: str | None = None) -> int:
        """索引 schema 变了，旧缓存整批作废，返回丢掉的条数。

        ``schema`` 是**要保留**的 schema，不传就取当前 ``INDEX_SCHEMA``——
        注意语义是"留谁"而不是"删谁"：重建索引后调用一次，留下的正好是新口径的缓存。
        整文件重写而不是追加墓碑行，是因为清完还要继续跑，文件里留一堆死行只会拖慢下次加载。
        """
        target = schema or config.INDEX_SCHEMA
        with self._lock:
            self._load()
            kept = {key: hit for key, hit in self._memo.items() if hit.schema == target}
            dropped = len(self._memo) - len(kept)
            self._memo = kept
            lines = [json.dumps(hit.as_dict(), ensure_ascii=False) for hit in kept.values()]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return dropped


_CACHE: QueryCache | None = None
_LOCK = threading.Lock()


def get_cache(path: str | Path | None = None) -> QueryCache:
    """取缓存实例：``path`` 不传就返回进程级单例，传了就现开一个独立的。

    单例是为了让问答链路和体检面板看同一份内存镜像；测试和临时目录要各用各的，
    就传 ``path`` 拿一个不受单例影响的实例（常见做法是配 ``reset_cache_for_tests``）。
    """
    if path is not None:
        return QueryCache(path)
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            _CACHE = QueryCache()
        return _CACHE


def reset_cache_for_tests() -> None:
    """把进程级单例丢掉，让下一次 ``get_cache()`` 重新开一个（测试的 setUp 里调）。"""
    global _CACHE
    with _LOCK:
        _CACHE = None
