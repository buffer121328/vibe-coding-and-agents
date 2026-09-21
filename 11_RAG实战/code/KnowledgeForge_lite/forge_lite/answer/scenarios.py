"""scenarios.py —— 课堂剧本：每一条都是「该看见什么行为」，给空状态和测试共用。

蒸馏来源：完整版 evaluation 黄金集 + QA 权限对照。
对应教程：11.15。聊天页「试一试」和离线测试读同一份，避免页面示范一套、门禁考另一套。

每条剧本只断言**不调模型也能核对**的纪律：工牌可见性、改写护栏、证据资格、会话隔离。
生成质量交给 Ragas 0.4 三个指标，不在这里用假答案凑数。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..data.acl_matrix import hidden_sources, visible_sources
from ..core.identity import resolve_actor


@dataclass(frozen=True)
class Scenario:
    """一条课堂剧本：一个问题 + 一张工牌 + 该看见的行为。

    ``id`` 是剧本代号，页面深链和测试都用它定位；``question`` 是原样发给问答链路的
    问题文本；``user_id`` 是用哪张工牌跑（权限判据全在这里）；``expect`` 是该看见的
    结局，只有 ``answer`` / ``refuse`` / ``isolated`` / ``persist`` 四种，前两种走问答，
    后两种分别核对会话隔离与刷新落盘；``lesson`` 是讲给学生听的一句话——这条剧本在演
    什么；``check`` 是可以不调模型就核对的断言（多数是文档可见性）；``tags`` 是分类标签，
    页面拿它做筛选。

    冻结（``frozen=True``）是有意的：剧本是课堂标准答案的一部分，被谁顺手改一个字段，
    演示结果就跟板书对不上了。
    """

    id: str
    question: str
    user_id: str
    expect: str  # answer / refuse / isolated / persist
    lesson: str
    check: str
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """摊成给页面用的字典，并**当场算出**该工牌的可见/不可见文档清单。

        可见性不存字段而在这里现算：它是权限矩阵的函数，存下来就得跟着矩阵一起维护，
        迟早会不同步——现算的代价只是读一次目录元数据。
        """
        actor = resolve_actor(self.user_id)
        return {
            **asdict(self),
            "tags": list(self.tags),
            "actor_name": actor.display_name,
            "visible_docs": visible_sources(self.user_id),
            "hidden_docs": hidden_sources(self.user_id),
        }


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("travel-cap", "去上海出差住一晚能报多少？", "it_staff", "answer",
             "库内事实：差旅住宿上限应能从公开制度召回。",
             "可见文档含员工差旅管理制度.md", ("事实", "差旅")),
    Scenario("travel-deadline", "差旅报销单要在返回后几天内提交？", "it_staff", "answer",
             "数字题：改写不得丢掉 5 个工作日。",
             "原问题必须留在 queries[0]", ("事实", "改写")),
    Scenario("travel-cap-hr", "去上海出差住一晚能报多少？", "hr_staff", "answer",
             "公司公开文档，人事也该能答。",
             "人事可见差旅制度", ("事实", "ACL")),
    Scenario("printer-e3-it", "打印机显示 E3 怎么处理？", "it_staff", "answer",
             "部门文档：IT 看得到运维故障单。",
             "IT 可见运维故障案例.md", ("流程", "IT")),
    Scenario("printer-e3-hr", "打印机显示 E3 怎么处理？", "hr_staff", "refuse",
             "人事看不见 IT 部门文档，检索层就裁掉。",
             "人事不可见运维故障案例.md", ("ACL", "IT")),
    Scenario("printer-e3-finance", "打印机显示 E3 怎么处理？", "finance_head", "refuse",
             "财务负责人同样不在 IT 部门。",
             "财务不可见运维故障案例.md", ("ACL", "IT")),
    Scenario("printer-e3-admin", "打印机显示 E3 怎么处理？", "admin", "answer",
             "管理员不过滤部门。",
             "管理员可见运维故障案例.md", ("ACL", "管理员")),
    Scenario("faq-quota", "Forge 免费版每月有多少次问答额度？", "hr_staff", "answer",
             "FAQ 是公司公开文档。",
             "人事可见产品FAQ.md", ("事实", "FAQ")),
    Scenario("bonus-refuse", "公司年终奖一般发几个月工资？", "it_staff", "refuse",
             "库外拒答：投毒 HTML 已被隔离。",
             "任何工牌都不应把年终奖当资料", ("拒答", "投毒")),
    Scenario("pay-it", "P6 薪酬带宽是多少？", "it_staff", "refuse",
             "密级文档：普通员工在打分前被裁掉。",
             "IT 不可见财务薪酬密级.md", ("ACL", "薪酬")),
    Scenario("pay-hr", "P6 薪酬带宽是多少？", "hr_staff", "refuse",
             "人事同样是 employee，看不见 restricted。",
             "人事不可见财务薪酬密级.md", ("ACL", "薪酬")),
    Scenario("pay-finance", "P6 薪酬带宽是多少？", "finance_head", "answer",
             "部门负责人可见 restricted。",
             "财务可见财务薪酬密级.md", ("ACL", "薪酬")),
    Scenario("pay-admin", "P6 薪酬带宽是多少？", "admin", "answer",
             "管理员不过滤。None 不是空元组。",
             "管理员可见财务薪酬密级.md", ("ACL", "管理员")),
    Scenario("security-hr", "把客户名单发到私人邮箱可以吗？", "hr_staff", "answer",
             "安全红线是公司公开文档。",
             "人事可见信息安全红线.md", ("安全", "公开")),
    Scenario("colloquial", "出差回来晚了一天，钱最晚啥时候能到手？", "it_staff", "answer",
             "口语改写仍应命中报销时限。",
             "原问题保留，不替换成模型改写", ("改写", "差旅")),
    Scenario("session-isolation", "IT 的会话人事打不开", "hr_staff", "isolated",
             "会话按工牌隔离，指针不是权限。",
             "list_conversations(hr) 不含 it 的 conv_id", ("会话", "ACL")),
    Scenario("session-persist", "刷新后会话还在", "it_staff", "persist",
             "服务端权威：SQLite 落盘，刷新从服务器拉。",
             "关闭再打开 ConversationStore，消息条数不变", ("会话",)),
)


def by_id(scenario_id: str) -> Scenario:
    """按 ``scenario_id`` 取剧本，返回 ``Scenario``；找不到抛 ``KeyError``。

    找不到就抛，而不是回 ``None``：调用方（页面深链、测试）拿到 None 还得再判一次，
    而"这条剧本不存在"本身就是该报出来的错。
    """
    for item in SCENARIOS:
        if item.id == scenario_id:
            return item
    raise KeyError(scenario_id)


def for_badge(user_id: str) -> list[Scenario]:
    """取 ``user_id`` 这张工牌名下的剧本，按定义顺序返回。

    工牌先过一次 ``resolve_actor`` 再比：页面传进来的可能是别名或大小写不同的写法，
    直接用原串比会漏掉本该出现的剧本。
    """
    actor = resolve_actor(user_id)
    return [item for item in SCENARIOS if item.user_id == actor.user_id]


def visibility_check(scenario: Scenario) -> tuple[bool, str]:
    """不调模型：只核对这条剧本 ``scenario`` 对工牌可见性的断言。

    返回 ``(是否通过, 说明)``——第二个元素直接拿去显示，所以它写的是剧本自己的
    ``check`` 原文，测试失败时一眼能看到"考的是哪一句"。

    必须先看「不可见」，再看「可见」——「不可见」四个字里套着「可见」，
    用 ``"可见" in text`` 会把拒答题判反。
    """
    visible = set(visible_sources(scenario.user_id))
    hidden = set(hidden_sources(scenario.user_id))
    documents = (
        "运维故障案例.md",
        "财务薪酬密级.md",
        "员工差旅管理制度.md",
        "产品FAQ.md",
        "信息安全红线.md",
    )
    for filename in documents:
        if filename not in scenario.check and not (
            filename == "员工差旅管理制度.md" and "差旅制度" in scenario.check
        ):
            continue
        if "不可见" in scenario.check:
            return filename in hidden, scenario.check
        if "可见" in scenario.check:
            return filename in visible, scenario.check
    return True, "本条不考文档可见性"
