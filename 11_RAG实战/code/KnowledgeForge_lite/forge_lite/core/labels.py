"""labels.py —— 工作台用的中文文案。页面、接口、测试读同一份，避免各写各的。

对应教程：11.13。完整版把文案散在 React 组件里；Lite 收成一份，
改「已拒答」三个字不会出现 SSE 一个说法、抽屉另一个说法。
"""

from __future__ import annotations

from .evidence import STATUS_ANSWERED, STATUS_CLARIFY, STATUS_CONFLICT, STATUS_INSUFFICIENT, STATUS_PARTIAL, STATUS_REVIEW, STATUS_UNAVAILABLE


APP_NAME = "KnowledgeForge Lite"
APP_TAGLINE = "问一句制度问题，看答案带出处；换工牌，看权限在哪一层生效。"
BADGE_LABEL = "工牌"
RAIL_TITLE = "会话柜"
NEW_CONVERSATION = "新开一格"
ASK = "提问"
COMPOSER_PLACEHOLDER = "问一句制度，例如：出差住一晚能报多少？"
EMPTY_TITLE = "从一个空会话开始"
EMPTY_BODY = "会话在服务器上，刷新不丢。表里是课堂剧本：点问题直接跑，右侧写清该看见什么。"
EVIDENCE_TITLE = "证据抽屉"
EVIDENCE_HINT = "点答案里的朱砂角标，这里打开对应切块；看不见的文档不会出现——权限在打分前就裁过了。"
NO_DRAWERS = "还没有会话。问一句就会新开一格。"
DELETE = "删除"
THINKING = "正在过门禁…"
YOU = "你"
ASSISTANT = "助手"
TABS = (("catalog", "目录"), ("chunk", "出处"), ("trace", "轨迹"))

STATUS_LABELS = {
    STATUS_ANSWERED: "已回答",
    STATUS_PARTIAL: "部分回答",
    STATUS_INSUFFICIENT: "证据不足",
    STATUS_CLARIFY: "需要补充",
    STATUS_CONFLICT: "证据冲突",
    STATUS_REVIEW: "转人工",
    STATUS_UNAVAILABLE: "来源暂不可用",
    "ok": "已回答",
    "refuse": "已拒答",
    "regen": "重试中",
}

ROUTE_LABELS = {
    "bm25": "关键词",
    "dense": "向量",
    "vector": "向量",
    "graph": "图谱",
    "hybrid": "融合",
}

ROLE_LABELS = {
    "company_admin": "公司管理员",
    "department_head": "部门负责人",
    "employee": "员工",
}

DEPARTMENT_LABELS = {
    "company": "公司",
    "finance": "财务",
    "it": "IT",
    "hr": "人事",
}

SENSITIVITY_LABELS = {
    "public": "公开",
    "department": "部门",
    "restricted": "密级",
}

INTENT_LABELS = {
    "factoid": "事实",
    "procedural": "流程",
    "analytical": "原因",
    "comparative": "对比",
    "exploratory": "探索",
}


def status_text(status: str) -> str:
    """把结局代号 ``status`` 翻成中文文案；表里没有的代号原样返回。

    原样返回而不是显示"未知"：新代号漏登记时，页面上会直接出现那个代号，
    写代码的人一眼就知道该往 ``STATUS_LABELS`` 里补哪一条。
    """
    return STATUS_LABELS.get(status, status)


def route_text(route: str) -> str:
    """把召回路线代号 ``route``（``bm25`` / ``dense`` / ``graph`` …）翻成中文。"""
    return ROUTE_LABELS.get(route, route)


def intent_text(intent: str) -> str:
    """把意图代号 ``intent``（``factoid`` / ``procedural`` …）翻成中文。"""
    return INTENT_LABELS.get(intent, intent)
