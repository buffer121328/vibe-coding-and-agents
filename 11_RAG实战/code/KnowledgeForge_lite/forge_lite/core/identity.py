"""identity.py —— 教学版 RBAC：角色 + 部门，检索前先裁可见范围。

蒸馏来源：完整版 domain 身份契约 + 检索层 visible_department_ids。
对应教程：11.13（多租户 ACL：谁能搜到什么，在打分前就决定）。

完整版用 JWT + PostgreSQL 当身份事实来源；Lite 用四名写死的演示用户。
思想必须同构，实现可以简：

- ``company_admin``：可见部门 = None，表示不过滤（管理员开上帝视角）；
- 其他人：只能看见「本公司公开文档 + 本部门文档」；
- ``restricted`` 密级：普通员工看不见，部门负责人和管理员可以。

千万别先检索再丢弃——那是把机密当过场字幕放了一遍。正确顺序是：
**先按工牌裁库，再打分，再融合。**
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


# 文档目录：入库时打在每一块上的部门 / 密级。完整版存在 PostgreSQL catalog。
DOC_POLICY: dict[str, dict[str, str]] = {
    "员工差旅管理制度.md": {"department": "company", "sensitivity": "public", "acl": "employee"},
    "产品FAQ.md": {"department": "company", "sensitivity": "public", "acl": "employee"},
    "运维故障案例.md": {"department": "it", "sensitivity": "department", "acl": "employee"},
    "信息安全红线.md": {"department": "company", "sensitivity": "public", "acl": "employee"},
    "财务薪酬密级.md": {"department": "finance", "sensitivity": "restricted", "acl": "restricted"},
    # 诱饵：人人可见的公开制度。证据资格如果拿「元」当住宿特征词，
    # 这篇里的 200 元会和差旅 500 元互相判成冲突——所以它必须进表，
    # 不能靠「未知文件=公司公开」这条兜底悄悄混进候选池。
    "办公用品领用制度.md": {"department": "company", "sensitivity": "public", "acl": "employee"},
}


def catalog_of(source_name: str) -> dict[str, str]:
    """按文件名取目录元数据；未知文件默认公司公开（放开，不是收紧）。

    ``source_name`` 是切块的来源文件名，带目录路径也没关系——只取最后一段，因为
    语料里的 ``source`` 有时是 ``docs/员工差旅管理制度.md``，拿全路径去查表会全落空。
    认不出来的按"公司公开、员工可见"兜底——这是**默认放开**，不是收紧。
    课堂上传一篇新文件不该凭空消失；但放开的代价是：语料里有、表里没有的文档
    会对几乎所有工牌可见。所以 ``tests/test_identity_rules.py`` 会扫 ``data/docs/``，
    制度文件没进表就当场红掉（投毒 HTML 除外，它走隔离，不进这张表）。

    返回一份**拷贝**的 ``{"department", "sensitivity", "acl"}``：调用方常要往上补字段，
    直接给 ``DOC_POLICY`` 里的原字典会被就地改脏，污染后续所有请求。
    """
    name = (source_name or "").split("/")[-1]
    return dict(DOC_POLICY.get(name, {
        "department": "company",
        "sensitivity": "public",
        "acl": "employee",
    }))


@dataclass(frozen=True)
class Actor:
    """一次问答的提问人。完整版从 JWT 解析；Lite 从演示工牌里取。

    ``user_id`` 是工牌 id，也是 ``USERS`` 里的键；``display_name`` 是页面上显示的名字；
    ``role`` 是角色，取 ``company_admin`` / ``department_head`` / ``employee`` 之一，
    只有 ``company_admin`` 能拿到"不过滤"的可见范围；``department`` 是所属部门，
    取 ``company`` / ``finance`` / ``it`` / ``hr`` 之一，``company`` 表示全公司都能看。

    frozen 是有意的：身份对象会被一路传进检索、目录、预览，中途若被谁改一个字段，
    权限判断就跟着变，事后完全查不出是谁动的手。
    """

    user_id: str
    display_name: str
    role: str            # company_admin / department_head / employee
    department: str      # company / finance / it / hr

    def visible_department_ids(self) -> tuple[str, ...] | None:
        """与完整版同语义：None = 不过滤；元组 = 只准这些部门（含空元组=什么都看不见）。

        规则两条：管理员返回 None（上帝视角）；其余人只能看见"本公司公开 + 本部门"，
        所以普通员工拿到的是 ``(本部门, "company")`` 而 ``company`` 部门的人只拿到
        ``("company",)``——查重不影响结果，但读代码时意图更清楚。

        返回元组而不是集合：它是"可见范围"的权威表述，后面要进缓存键和日志，
        有序且不可变才不会出现两次相同请求比出不同结果的怪事。
        """
        if self.role == "company_admin":
            return None
        if self.department == "company":
            return ("company",)
        return (self.department, "company")


USERS: dict[str, Actor] = {
    "admin": Actor("admin", "公司管理员", "company_admin", "company"),
    "finance_head": Actor("finance_head", "财务负责人", "department_head", "finance"),
    "it_staff": Actor("it_staff", "IT 员工", "employee", "it"),
    "hr_staff": Actor("hr_staff", "人事员工", "employee", "hr"),
}

DEFAULT_USER_ID = "it_staff"


def resolve_actor(user_id: str | Actor | None = None) -> Actor:
    """把 user_id 解析成 Actor；不认识的工牌回落到 IT 员工（最小可见范围之一）。

    ``user_id`` 可以是 ``Actor`` 对象（原样返回）、工牌 id 字符串，或 None（用
    ``DEFAULT_USER_ID``）。空白字符串也算没传——表单里提交一个空格是最常见的输入事故，
    不该让它变成"查无此人"的随机分支。

    返回 ``USERS`` 里的 ``Actor``。**回落目标是有讲究的**：伪造 id 拿到的是 IT 员工
    的可见范围，而不是管理员。这道闸门不负责认证（认证在 ``accounts`` 那侧），
    它保证的是"无论如何都不会因为认不出身份而给出超出权限的视野"。
    """
    if isinstance(user_id, Actor):
        return user_id
    key = (user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID
    return USERS.get(key, USERS[DEFAULT_USER_ID])


def can_see(actor: Actor, chunk: Mapping) -> bool:
    """检索层 ACL：块能不能进候选池。必须在 BM25 / 向量 / 图谱打分之前调用。

    ``actor`` 是提问人（``Actor`` 实例）；``chunk`` 是待判的切块字典，读它的
    ``department`` 与 ``sensitivity`` 两个字段，缺失时分别按 ``company``、``public``
    兜底（旧索引没有这两列的补法是"按最宽处理"还是"按最严处理"是个取舍：
    这里配合 ``catalog._stamp_policy`` 在入库侧补齐，运行侧只做最后一道判断）。

    返回 True 表示这块可以进候选池。两道门：部门在可见范围内，且 ``restricted``
    密级不对普通员工开放——密级只挡员工，部门负责人和管理员照常能看，课堂上可以
    拿同一块密级资料演示"换个工牌就搜得到"。
    """
    visible = actor.visible_department_ids()
    department = str(chunk.get("department") or "company")
    sensitivity = str(chunk.get("sensitivity") or "public")
    if visible is None:
        return True
    if department not in visible:
        return False
    if sensitivity == "restricted" and actor.role == "employee":
        return False
    return True


def authorize_chunks(chunks: list[dict], actor: Actor | str | None) -> list[dict]:
    """先裁可见范围，再交给打分器。空列表是合法结果：不是报错，是没权限。

    ``chunks`` 是候选切块列表，``actor`` 可以是 ``Actor``、工牌 id 或 None（交给
    ``resolve_actor`` 解析）。返回其中 ``can_see`` 为真的那些，相对顺序不变——
    检索、目录列表、角标跳原文都走它，所以任何一处漏调都会变成侧信道
    （搜不到、却在证据抽屉里读得到）。“检索后再丢弃”是错的：那等于把机密
    当过一次场字幕，日志、缓存、trace 里都留下了痕迹。
    """
    person = resolve_actor(actor)
    return [chunk for chunk in chunks if can_see(person, chunk)]
