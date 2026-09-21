"""acl_matrix.py —— 工牌 × 文档的可见性矩阵。目录页和课堂测验共用这一份。

对应教程：11.13。完整版把可见范围藏在 PostgreSQL 策略里；Lite 把矩阵摊开，
课堂能拿笔把格子填完。**先填这张表，再谈检索分数**——分数再高，格子是空的也搜不到。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..core.identity import DOC_POLICY, USERS, Actor, authorize_chunks, catalog_of, resolve_actor


@dataclass(frozen=True)
class Cell:
    """矩阵里的一格：谁 × 哪篇文档 → 看不看得见、为什么。

    ``user_id`` 是工牌 id；``source`` 是来源文件名；``visible`` 是结论（True 表示
    这张工牌看得到这篇）；``reason`` 是一句中文理由，取的是裁定时**先命中的那一条**
    规则——课堂上要讲的正是"为什么是这条"。

    冻结（``frozen=True``）：矩阵是标准答案，格子在生成之后不该被改。
    """

    user_id: str
    source: str
    visible: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        """摊成扁平字典，字段名即列名，页面拿它直接排一行。"""
        return {
            "user_id": self.user_id,
            "source": self.source,
            "visible": self.visible,
            "reason": self.reason,
        }


def _reason(actor: Actor, source: str) -> tuple[bool, str]:
    """算 ``actor`` 对文档 ``source`` 的可见性与理由，返回 ``(结论, 中文理由)``。

    理由按判定的先后顺序返回：先算权限尺子的结论，再依次看"是不是管理员"
    "部门对不对得上""密级卡不卡"——返回的是**第一条命中**的规则，所以课堂
    解释某格为什么是 False 时，拿到的就是真正起作用的那条，不是笼统的一句"被裁了"。
    """
    policy = catalog_of(source)
    chunk = {
        "source": source,
        "department": policy["department"],
        "sensitivity": policy["sensitivity"],
        "acl": policy["acl"],
    }
    visible = bool(authorize_chunks([chunk], actor))
    if actor.role == "company_admin":
        return True, "管理员不过滤部门"
    if policy["department"] not in (actor.visible_department_ids() or ()):
        return False, f"{actor.display_name} 看不到 {policy['department']} 部门文档"
    if policy["sensitivity"] == "restricted" and actor.role == "employee":
        return False, "普通员工看不到 restricted 密级"
    if visible:
        return True, f"{actor.display_name} 可见 {policy['department']}/{policy['sensitivity']}"
    return False, "工牌裁掉"


def corpus_sources(path: str | Path | None = None) -> list[str]:
    """索引里真实存在的文档清单（去重、按名字排）。

    ``path`` 是切块 JSON 的路径，不传就用 ``config.CHUNKS_JSON``；测试传临时文件。

    **这是"格子里该铺哪些文档"的唯一事实来源**。以前这里默认走写死的 ``DOC_POLICY``，
    而文档页走的是真实切块账——于是同一页面上，工牌卡说管理员"可见 N 篇"、
    目录接口说"可见 N+1 篇"（差的是一篇不在 POLICY 里、按默认规则人人可见的新文档）。
    同一个数字从两处算，迟早会对不上；现在都从语料来。
    """
    from .catalog import load_chunks

    return sorted({str(chunk["source"]) for chunk in load_chunks(path)})


def iter_cells(user_ids: Iterable[str] | None = None, sources: Iterable[str] | None = None) -> list[Cell]:
    """把矩阵铺成格子列表，顺序是"先按人、再按文档"。

    ``user_ids`` 是要算的工牌集合，不传取全部 ``USERS``；
    ``sources`` 是要算的文档集合，不传取**索引里真实存在的文档**（``corpus_sources``）——
    不是写死的策略表。传参是为了让测试能只算关心的几格，也为了页面按需切一片出来。

    返回 ``Cell`` 列表；顺序固定，于是同一份输入每次铺出来的格子排列一致，
    页面上的表格不会今天一个样明天一个样。
    """
    people = [resolve_actor(uid) for uid in (user_ids or USERS)]
    docs = list(sources) if sources is not None else corpus_sources()
    cells = []
    for actor in people:
        for source in docs:
            visible, reason = _reason(actor, source)
            cells.append(Cell(actor.user_id, source, visible, reason))
    return cells


def matrix(user_ids: Iterable[str] | None = None, sources: Iterable[str] | None = None) -> dict[str, dict[str, bool]]:
    """只取结论的矩阵：``工牌 → {文件名: 看不看得见}``（理由请走 ``iter_cells``）。

    ``user_ids`` 是工牌集合，``sources`` 是文档集合，都不传就取全部。
    返回值只有布尔值，适合直接印在板书或丢给断言比对。
    """
    table: dict[str, dict[str, bool]] = {}
    for cell in iter_cells(user_ids, sources):
        table.setdefault(cell.user_id, {})[cell.source] = cell.visible
    return table


def visible_sources(user_id: str | Actor) -> list[str]:
    """``user_id`` 这张工牌**看得见**的文档清单，顺序同 ``iter_cells``。"""
    actor = resolve_actor(user_id)
    return [cell.source for cell in iter_cells([actor.user_id]) if cell.visible]


def hidden_sources(user_id: str | Actor) -> list[str]:
    """``user_id`` 这张工牌**看不见**的文档清单；两者互补，合起来是全部文档。"""
    actor = resolve_actor(user_id)
    return [cell.source for cell in iter_cells([actor.user_id]) if not cell.visible]


def explain(user_id: str | Actor, source: str) -> str:
    """给单格判定配一句中文理由，供页面悬停显示：``user_id`` 是工牌，``source`` 是文件名。"""
    actor = resolve_actor(user_id)
    _, reason = _reason(actor, source)
    return reason


def assert_expected(expected: dict[str, dict[str, bool]]) -> list[str]:
    """课堂测验：传入期望矩阵，返回不一致的格子。空列表 = 全对。

    ``expected`` 的形状是 ``工牌 → {文件名: 期望的可见性}``，行与列都从它自己推出来，
    所以改测验题不用动这个函数。返回的每条是给人看的一句话（谁 × 哪篇：期望 vs 实际），
    直接打印就能念给学生听。
    """
    actual = matrix(expected.keys(), next(iter(expected.values())).keys() if expected else [])
    mismatches = []
    for user_id, row in expected.items():
        for source, should in row.items():
            got = actual.get(user_id, {}).get(source)
            if got != should:
                mismatches.append(f"{user_id} × {source}：期望 {should}，实际 {got}")
    return mismatches


# 课堂标准答案。改 DOC_POLICY 时必须同步改这里，否则测试会叫。
EXPECTED_MATRIX: dict[str, dict[str, bool]] = {
    "it_staff": {
        "员工差旅管理制度.md": True,
        "产品FAQ.md": True,
        "运维故障案例.md": True,
        "信息安全红线.md": True,
        "财务薪酬密级.md": False,
        "办公用品领用制度.md": True,
    },
    "hr_staff": {
        "员工差旅管理制度.md": True,
        "产品FAQ.md": True,
        "运维故障案例.md": False,
        "信息安全红线.md": True,
        "财务薪酬密级.md": False,
        "办公用品领用制度.md": True,
    },
    "finance_head": {
        "员工差旅管理制度.md": True,
        "产品FAQ.md": True,
        "运维故障案例.md": False,
        "信息安全红线.md": True,
        "财务薪酬密级.md": True,
        "办公用品领用制度.md": True,
    },
    "admin": {
        "员工差旅管理制度.md": True,
        "产品FAQ.md": True,
        "运维故障案例.md": True,
        "信息安全红线.md": True,
        "财务薪酬密级.md": True,
        "办公用品领用制度.md": True,
    },
}
