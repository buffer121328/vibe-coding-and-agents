"""contracts.py —— HTTP / SSE / 会话柜共用的字段名。前后端对照这一份，不要各写各的。

蒸馏来源：完整版 ``frontend/src/types`` + ``api/routers/qa``。
对应教程：11.13。完整版靠 TypeScript 接口卡前后端；Lite 用这份清单做课堂契约：
改字段先改这里，测试按这里断言，页面按这里读。
"""

from __future__ import annotations

from typing import Any, Mapping


# 问答 SSE done 帧必须带的键。缺了前端证据抽屉会空，刷新后也还原不了。
ASK_DONE_KEYS = (
    "status",
    "citations",
    "warn",
    "routes",
    "intent",
    "actor",
    "actor_id",
    "conversation_id",
    "run_id",
    "history_saved",
    "response_status",
    "response_label",
    "evidence",
    "route_chips",
    "contexts",
    "queries",
)

# 会话列表一张名片。正文不在这里，避免列表接口把整段答案拖下来。
CONVERSATION_CARD_KEYS = (
    "id",
    "user_id",
    "title",
    "status",
    "created_at",
    "updated_at",
    "tenant_id",
)

MESSAGE_KEYS = (
    "id",
    "conversation_id",
    "sequence",
    "role",
    "content",
    "created_at",
    "payload",
)

CITATION_KEYS = ("marker", "doc_id")

ACTOR_KEYS = ("user_id", "name", "role", "department")

EVIDENCE_KEYS = (
    "state",
    "response_status",
    "reason_codes",
    "evaluated_ids",
    "supporting_ids",
    "missing_information",
    "coverage",
    "policy_version",
    "allows_generation",
)

# 控制台 DOM id。页面测试按这份对，JS 也按这份取。改 id 必须三处一起改。
DOM_IDS = {
    # 壳层
    "sider_toggle": "sider-toggle",
    "nav_open": "nav-open",
    "scrim": "scrim",
    "page_name": "page-name",
    "crumb_page": "crumb-page",
    "badge_rack": "badge-rack",
    # 账号（登录/登出）
    "account_avatar": "account-avatar",
    "account_name": "account-name",
    "account_meta": "account-meta",
    "account_menu": "account-menu",
    "account_logout": "account-logout",
    # 导航（与完整版 navigation.ts 同构）
    "nav_qa": "nav-qa",
    "nav_docs": "nav-docs",
    "nav_eval": "nav-eval",
    "view_qa": "view-qa",
    "view_docs": "view-docs",
    "view_eval": "view-eval",
    # 智能问答
    "drawers": "drawers",
    "transcript": "transcript",
    "ask_form": "ask-form",
    "question": "q",
    "ask_btn": "ask-btn",
    "new_conv": "new-conv",
    "export_conv": "export-conv",
    "tab_catalog": "tab-catalog",
    "tab_chunk": "tab-chunk",
    "tab_trace": "tab-trace",
    "evidence_body": "evidence-body",
    "status": "status",
    # 知识文档
    "docs_refresh": "docs-refresh",
    "docs_tab_list": "docs-tab-list",
    "docs_tab_upload": "docs-tab-upload",
    "docs_panel_list": "docs-panel-list",
    "docs_panel_upload": "docs-panel-upload",
    "docs_summary": "docs-summary",
    "docs_file": "docs-file",
    "docs_upload": "docs-upload",
    "docs_table": "docs-table",
    "docs_locked": "docs-locked",
    # 切块实验台（后端 preview_chunk_plan）
    "lab_source": "lab-source",
    "lab_text": "lab-text",
    "lab_size": "lab-size",
    "lab_overlap": "lab-overlap",
    "lab_apply": "lab-apply",
    "lab_reset": "lab-reset",
    "lab_message": "lab-message",
    "lab_stats": "lab-stats",
    "lab_chunks": "lab-chunks",
    # 评测治理
    "eval_summary": "eval-summary",
    "eval_run": "eval-run",
    "eval_ragas": "eval-ragas",
    "eval_refresh": "eval-refresh",
    "eval_table": "eval-table",
    "eval_reports": "eval-reports",
    "eval_locked": "eval-locked",
    "eval_ragas_panel": "eval-ragas-panel",
}

# 轨迹面板的字段。前端只读这些，不自己算路由。
TRACE_KEYS = (
    "question",
    "queries",
    "intent_label",
    "status_label",
    "response_status",
    "route_labels",
    "sources",
    "lanes",
    "steps",
    "evidence",
    "warn",
    "run_id",
    "conversation_id",
)

# 三路召回的名次行：轨迹面板画「哪几路召回了它、主路第几名」。
LANE_KEYS = ("doc_id", "marker", "fused_rank", "route_rank", "primary", "lanes", "why")

API_PATHS = {
    "health": "/health",
    "whoami": "/whoami",
    "ask": "/ask",
    "conversations": "/api/conversations",
    "catalog": "/api/catalog",
    "chunks": "/api/chunks",
    "audit": "/api/audit",
    "graph": "/api/graph",
    "prompts": "/classroom/prompts",
    "export": "/api/conversations/{conversation_id}/export",
    "trace": "/api/runs/{run_id}/trace",
    "static_css": "/static/workbench.css",
    "static_js": "/static/workbench.js",
}


def missing_keys(payload: Mapping[str, Any], required: tuple[str, ...]) -> list[str]:
    """列 ``payload`` 里缺了哪些 ``required`` 键，键都在就返回空列表。

    ``payload`` 是待检查的字典（SSE 帧、接口响应、会话记录都行），``required`` 是
    上面那几份契约清单里的一条。返回顺序跟着 ``required`` 走，不跟着 ``payload``——
    报错时字段按契约里的书写顺序排，一眼能看出是哪一段没凑齐。

    只查「有没有这个键」，不查值是否为空：值可以是 ``""`` / ``None`` / 空列表，
    它们各有各的语义（比如 ``warn`` 为空恰恰代表没告警）。返回值而不是抛异常，
    是为了让调用方能先收齐所有缺口再一次性报告。
    """
    return [key for key in required if key not in payload]


def require_keys(payload: Mapping[str, Any], required: tuple[str, ...], label: str) -> None:
    """同 ``missing_keys``，但把「缺字段」升级成异常，给测试当断言用。

    ``payload`` 是待检查的字典，``required`` 是契约清单，``label`` 是这份载荷的
    中文名（如「问答 done 帧」），只用来拼错误消息——测试失败时要让人知道是**哪一份**
    契约漏了字段，光看键名认不出。缺字段时抛 ``ValueError``，消息形如
    ``xxx 缺字段：a, b``；一个都不缺就正常返回 ``None``。
    """
    absent = missing_keys(payload, required)
    if absent:
        raise ValueError(f"{label} 缺字段：{', '.join(absent)}")
