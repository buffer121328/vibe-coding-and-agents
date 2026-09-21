"""classroom.py —— 空状态和演示按钮用的课堂剧本，不调模型。

蒸馏来源：完整版评测集 + 前端空状态引导。
对应教程：11.15。聊天页右侧「试一试」不是装饰，每一条都对应一个该看见的行为：
带引用作答、口语改写仍命中、库外拒答、越权拒答、换工牌就能看见。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..data.acl_matrix import hidden_sources, visible_sources
from ..core.identity import USERS, resolve_actor
from ..core.labels import DEPARTMENT_LABELS, ROLE_LABELS


@dataclass(frozen=True)
class DemoPrompt:
    """空状态「试一试」里的一条，连同它「该看见什么」的课堂讲解。

    七个字段一半给界面、一半给讲课：

    - ``id`` 是这条剧本的稳定编号（如 ``pay-band-it``），测试和前端都按它挑条目，
      所以加密钥、改文案可以，编号不能随手改；
    - ``question`` 是原样填进输入框的问句——它同时是对照实验的自变量，
      同一个问题配不同 ``user_id`` 才有比较意义；
    - ``user_id`` 是这条剧本指定用哪张工牌提问（见 ``identity.USERS``）；
    - ``expect`` 是预期走向，只有 ``answer``（应当作答）和 ``refuse``（应当拒答）
      两个取值，前端按它配颜色、测试按它做断言；
    - ``lesson`` 是这条剧本想讲的原理（为什么它被裁掉 / 为什么它非答不可）；
    - ``hint`` 是留给老师的观察重点，比 ``lesson`` 更具体（该出现哪个角标、
      哪个字段该长什么样），课堂上照着念就行；
    - ``tags`` 是给检索和分组用的短标签（``事实`` / ``ACL`` / ``改写``……），
      默认空元组，可以不写。

    之所以是 frozen：剧本是课堂讲义，讲课时一边翻一边被谁改掉一个字段，
    对照实验的前提就没了。
    """

    id: str
    question: str
    user_id: str
    expect: str  # answer / refuse
    lesson: str
    hint: str
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """摊平成前端直接吃的字典：七个字段原样，外加三项现算的可见范围。

        ``tags`` 会从元组转成列表（JSON 没有元组，``asdict`` 吐出来的元组在传输里
        会变成数组或直接报错，不如在这里就转掉）；``actor_name`` 是工牌的中文名，
        由 ``user_id`` 经 ``resolve_actor`` 解出来，免得前端自己维护一份工牌对照表；
        ``visible_docs`` / ``hidden_docs`` 是这张工牌看得见、看不见的文档清单，
        用来在卡片上印「可见 N 篇 / 裁掉 M 篇」——先看清权限再选身份。
        """
        actor = resolve_actor(self.user_id)
        return {
            **asdict(self),
            "tags": list(self.tags),
            "actor_name": actor.display_name,
            "visible_docs": visible_sources(self.user_id),
            "hidden_docs": hidden_sources(self.user_id),
        }


PROMPTS: tuple[DemoPrompt, ...] = (
    DemoPrompt(
        "travel-cap",
        "去上海出差住一晚能报多少？",
        "it_staff",
        "answer",
        "库内事实题：三路召回后应引用《员工差旅管理制度》。",
        "一线城市住宿上限 500 元，答案里应出现 [n] 角标。",
        ("事实", "差旅"),
    ),
    DemoPrompt(
        "travel-deadline",
        "差旅报销单要在返回后几天内提交？",
        "it_staff",
        "answer",
        "数字题：改写不得把「5 个工作日」改丢。",
        "原问题必须保留在 queries[0]。",
        ("事实", "差旅", "改写"),
    ),
    DemoPrompt(
        "printer-e3",
        "打印机显示 E3 怎么处理？",
        "it_staff",
        "answer",
        "部门文档：IT 员工看得到运维故障单。",
        "人事工牌问同一句应当拒答。",
        ("流程", "IT"),
    ),
    DemoPrompt(
        "printer-e3-hr",
        "打印机显示 E3 怎么处理？",
        "hr_staff",
        "refuse",
        "越权对照：人事看不见 IT 部门文档，检索层就裁掉。",
        "不要先搜再丢——人事的候选池里根本不该有故障单。",
        ("ACL", "IT"),
    ),
    DemoPrompt(
        "faq-quota",
        "Forge 免费版每月有多少次问答额度？",
        "hr_staff",
        "answer",
        "公司公开文档：人事和 IT 都该能答。",
        "FAQ 是 company/public，所有工牌可见。",
        ("事实", "FAQ"),
    ),
    DemoPrompt(
        "bonus-refuse",
        "公司年终奖一般发几个月工资？",
        "it_staff",
        "refuse",
        "库外拒答：投毒 HTML 已被隔离，不许编造。",
        "正确答案是「资料不足」，不是「18 个月」。",
        ("拒答", "投毒"),
    ),
    DemoPrompt(
        "pay-band-it",
        "P6 薪酬带宽是多少？",
        "it_staff",
        "refuse",
        "密级文档：普通员工工牌在打分前被裁掉。",
        "同一句换 finance_head 才能引用《财务薪酬密级》。",
        ("ACL", "薪酬"),
    ),
    DemoPrompt(
        "pay-band-finance",
        "P6 薪酬带宽是多少？",
        "finance_head",
        "answer",
        "部门负责人可见 restricted。",
        "答案应引用财务密级文档，而不是「我估计」。",
        ("ACL", "薪酬"),
    ),
    DemoPrompt(
        "pay-band-admin",
        "P6 薪酬带宽是多少？",
        "admin",
        "answer",
        "管理员不过滤部门。",
        "visible_department_ids 为 None 表示不过滤，不是空元组。",
        ("ACL", "管理员"),
    ),
    DemoPrompt(
        "colloquial-reimburse",
        "出差回来晚了一天，钱最晚啥时候能到手？",
        "it_staff",
        "answer",
        "口语改写：本地规则保留原问题，再补制度检索腔。",
        "应仍命中报销时限，而不是答『晚了一天扣钱』。",
        ("改写", "差旅"),
    ),
    DemoPrompt(
        "security-line",
        "把客户名单发到私人邮箱可以吗？",
        "hr_staff",
        "answer",
        "安全红线是公司公开文档，人事可见。",
        "应引用《信息安全红线》，不要靠模型常识发挥。",
        ("安全", "公开"),
    ),
    DemoPrompt(
        "decompose-hint",
        "比较一线和二线城市住宿标准，同时说明报销最晚什么时候交。",
        "it_staff",
        "answer",
        "多跳信号：教学版仍单轮检索，只在 warn 里提示。",
        "should_decompose 为真不代表会拆成子图。",
        ("改写", "多跳"),
    ),
)


def prompts_for(user_id: str) -> list[dict[str, object]]:
    """取 ``user_id`` 这张工牌该看到的剧本清单，每条已摊平成前端友好的字典。

    ``user_id`` 是工牌 id，认不出来会回落到 IT 员工（见 ``resolve_actor``）。
    返回顺序是有讲究的：先本工牌自己的题，再跟在后面的是「换工牌才有意义」的对照题
    （同一句换别人问，结论正好相反）。后半段不能按工牌过滤掉——课上要讲的正是
    「这题你答不了，换张工牌就能答」，少了对照组就讲不成。两段都走 ``as_dict``，
    所以每条都自带可见 / 裁掉文档清单。
    """
    actor = resolve_actor(user_id)
    items = [item.as_dict() for item in PROMPTS if item.user_id == actor.user_id]
    # 也带上「换工牌才有意义」的对照题，方便空状态讲课
    others = [item.as_dict() for item in PROMPTS if item.user_id != actor.user_id]
    return items + others


def badge_cards() -> list[dict[str, object]]:
    """工牌卡：名字、角色、部门都带中文标签，前端按原样显示，不自己映射。

    卡片上必须有「可见 N 篇 / 裁掉 M 篇」——课堂上先看清权限，再选身份。
    """
    cards = []
    for actor in USERS.values():
        cards.append({
            "user_id": actor.user_id,
            "name": actor.display_name,
            "role": actor.role,
            "role_label": ROLE_LABELS.get(actor.role, actor.role),
            "department": actor.department,
            "department_label": DEPARTMENT_LABELS.get(actor.department, actor.department),
            "visible_docs": visible_sources(actor.user_id),
            "hidden_docs": hidden_sources(actor.user_id),
            "blurb": {
                "it_staff": "默认工牌。公司公开 + IT 部门。",
                "hr_staff": "人事。看不见故障单和薪酬密级。",
                "finance_head": "财务负责人。看得见薪酬带宽。",
                "admin": "管理员。不过滤部门。",
            }.get(actor.user_id, ""),
        })
    return cards


EMPTY_COPY = {
    "title": "从一个空会话开始",
    "body": "刷新不会丢会话——会话存在服务器上。换工牌会换一排会话，IT 打不开财务的。",
    "actions": [
        "问一句差旅住宿上限，看角标能不能点开原文。",
        "用 IT 工牌问 P6 薪酬，应当拒答。",
        "换成财务负责人再问同一句，应当引用密级文档。",
    ],
}
