"""graph_view.py —— 图谱邻接预览：给证据抽屉看「这实体连着谁」。

蒸馏来源：完整版前端 3D 图谱的课堂平面版。
对应教程：11.7。Lite 不画 Three.js，但第三路召回用的那张图，课堂必须能翻。

规矩和检索同一把：

- 先按工牌裁可见文档，再从可见三元组里取邻接；
- 财务密级上的「P6薪酬带宽」对 IT 员工不存在——不是图坏了，是工牌裁过；
- 节点身份仍是 ``文件名#切块号``，点开就走 ``catalog.get_chunk``，不另造幽灵块。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..data.catalog import load_chunks, parse_doc_id, visible_chunks
from ..core.identity import Actor, can_see, catalog_of, resolve_actor
from ..data.knowledge_graph import _triples_from_store


@dataclass
class GraphEdge:
    """图里的一条边：头实体、关系、尾实体，加上它出自哪篇文档。

    ``head`` / ``relation`` / ``tail`` 是三元组的三段（如"张三 - 属于 - 财务部"）；
    ``source`` 是这条边的来源文件名；``chunk_key`` 是拼好的 ``文件名#切块号``，
    点开就走 ``catalog.get_chunk`` 拿原文，不另造幽灵块。
    """

    head: str
    relation: str
    tail: str
    source: str
    chunk_key: str = ""

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典给前端；字段少且无嵌套，直接 ``asdict``。"""
        return asdict(self)


@dataclass
class Neighborhood:
    """某个实体在这张工牌下的一跳邻接。

    ``entity`` 是被查的实体名；``edges`` 是保留下来的边（最多 ``limit`` 条）；
    ``hidden`` 是因为工牌看不见而被裁掉的边数——它必须显示出来：抽屉里"连着的边很少"
    有两种可能，图本来就稀，或者被工牌裁过，这个数字负责把两者分开。
    """

    entity: str
    edges: list[GraphEdge]
    hidden: int

    def as_dict(self) -> dict[str, Any]:
        """摊成给前端的字典，顺手补一个 ``visible``（即 ``edges`` 的条数）。

        页面要同时显示"看得见几条、挡掉几条"，让它自己数一遍容易和 ``hidden`` 对不上账。
        """
        return {
            "entity": self.entity,
            "edges": [item.as_dict() for item in self.edges],
            "hidden": self.hidden,
            "visible": len(self.edges),
        }


def _policy_chunk(source: str) -> dict[str, str]:
    """按 ``source`` 造一个最小切块，只为过权限那一把尺子。

    三元组只带文件名。可见性按目录元数据裁，不依赖切块账本是否已入库——
    否则一篇文档刚被隔离，它的边就会因为"查不到切块"而漏网。
    """
    policy = catalog_of(source)
    return {
        "source": source,
        "department": policy["department"],
        "sensitivity": policy["sensitivity"],
        "acl": policy["acl"],
    }


def _authorized_triples(user_id: str | Actor | None) -> tuple[list[dict], int]:
    """``user_id`` 是工牌（用户 id 或 ``Actor``，None 也能解析成默认工牌）。

    返回 ``(看得见的三元组, 被裁掉的条数)``。裁掉的条数一路带到页面上，
    让"图很稀"和"被权限挡了"两种观感分得开。
    """
    triples = _triples_from_store()   # 图存储 + 种子垫底，已去重
    actor = resolve_actor(user_id)
    kept, hidden = [], 0
    for triple in triples:
        source = str(triple.get("source") or "")
        if source and not can_see(actor, _policy_chunk(source)):
            hidden += 1
            continue
        kept.append(triple)
    return kept, hidden


def _chunk_key(triple: dict, visible: list[dict]) -> str:
    """给一条三元组 ``triple`` 找它在 ``visible``（可见切块）里的出处块号。

    三元组本身不记块号，只能在同源切块里找哪一块的正文提到过头/尾实体；
    都找不到就退回 ``#0``——退到第一块是"这篇里就有这条关系"，比给个空字符串强，
    点开仍能落到原文。
    """
    source = str(triple.get("source") or "")
    if not source:
        return ""
    head = str(triple.get("head") or "")
    tail = str(triple.get("tail") or "")
    for chunk in visible:
        if str(chunk.get("source")) != source:
            continue
        text = str(chunk.get("text") or "")
        if head in text or tail in text:
            return f"{source}#{chunk.get('chunk_index', 0)}"
    return f"{source}#0"


def neighborhood(entity: str, user_id: str | Actor | None, limit: int = 12) -> Neighborhood:
    """某实体在这张工牌下的一跳邻接。空实体返回空图，不报错。

    ``entity`` 是实体名（前后空白先 strip，空串直接返回空图而不是抛异常——页面上
    点到一个空名字不值得让整个抽屉报错）；``user_id`` 是工牌，裁边用它；
    ``limit`` 是**边数**上限，不是实体数上限，够满一屏即可，多了页面也读不完。

    命中的判据是宽松包含：实体名等于头尾、或出现在头尾里都算，因为抽取出来的实体
    常带前后缀（"财务部" vs "财务部经理"），严格相等会让该连的边连不上。
    """
    name = (entity or "").strip()
    actor = resolve_actor(user_id)
    if not name:
        return Neighborhood("", [], 0)
    triples, hidden = _authorized_triples(actor)
    visible = visible_chunks(actor, load_chunks() or None)
    edges: list[GraphEdge] = []
    for triple in triples:
        head = str(triple.get("head") or "")
        tail = str(triple.get("tail") or "")
        if name not in (head, tail) and name not in head and name not in tail:
            continue
        edges.append(GraphEdge(
            head=head,
            relation=str(triple.get("relation") or ""),
            tail=tail,
            source=str(triple.get("source") or ""),
            chunk_key=_chunk_key(triple, visible),
        ))
        if len(edges) >= limit:
            break
    return Neighborhood(name, edges, hidden)


def list_entities(user_id: str | Actor | None, limit: int = 40) -> list[str]:
    """这张工牌看得见的实体名，给证据抽屉做检索入口。

    ``user_id`` 是工牌，先裁三元组再收名字——名字本身就是信息，看不见的文档
    不该通过"出现过哪些实体"漏出去；``limit`` 是名字个数上限，够满一屏即可。
    返回按首次出现顺序去重的名字列表。
    """
    triples, _ = _authorized_triples(user_id)
    names: list[str] = []
    seen: set[str] = set()
    for triple in triples:
        for key in ("head", "tail"):
            value = str(triple.get(key) or "").strip()
            if value and value not in seen:
                seen.add(value)
                names.append(value)
            if len(names) >= limit:
                return names
    return names


def edge_from_doc_id(doc_id: str, user_id: str | Actor | None) -> list[GraphEdge]:
    """从切块号反查相关三元组：点角标时证据抽屉可同时展开邻接。

    ``doc_id`` 是 ``文件名#切块号`` 形式的身份串，解析不出来（没有 ``#`` 或格式不对）
    就返回空列表——角标可能来自老记录，不该让抽屉因此报错；``user_id`` 是工牌，
    反查同样要过权限，否则角标会变成绕过 ACL 的后门。

    返回该文档的全部可见边（按切块号反查，不看实体名）。
    """
    parsed = parse_doc_id(doc_id)
    if parsed is None:
        return []
    source, _index = parsed
    triples, _ = _authorized_triples(user_id)
    visible = visible_chunks(user_id, load_chunks() or None)
    return [
        GraphEdge(
            head=str(item.get("head") or ""),
            relation=str(item.get("relation") or ""),
            tail=str(item.get("tail") or ""),
            source=str(item.get("source") or ""),
            chunk_key=_chunk_key(item, visible),
        )
        for item in triples
        if str(item.get("source") or "") == source
    ]
