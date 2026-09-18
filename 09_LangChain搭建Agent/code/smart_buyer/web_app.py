"""
SmartBuyer Web 工作台
=====================

一个独立的 Gradio 前端：把终端版 SmartBuyer 的问诊、工具调用链、
结构化报告和成本统计放进同一个可视化工作台。

启动：
    cd 09_LangChain搭建Agent/code
    uv run python -m smart_buyer.web_app

前端不复制 Agent 逻辑，只调用 ``SmartBuyerAgent``，因此课程版、CLI 和
Web 工作台共用同一套护栏、RAG、MCP 工具与会话记忆。
"""

from __future__ import annotations

import ast
import html
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
from uuid import uuid4

import gradio as gr
from dotenv import load_dotenv

load_dotenv()


# -----------------------------------------------------------------------------
# 运行时状态：模型初始化很慢，而且未配置 Key 时不应该在页面启动阶段报错。
# -----------------------------------------------------------------------------
_AGENTS: dict[bool, Any] = {}
_AGENT_LOCK = threading.Lock()
_WEB_SESSION_HISTORY: dict[str, list[dict[str, str]]] = {}
_WEB_SESSION_PROCESS: dict[str, dict[str, Any]] = {}
_WEB_SESSION_REPORTS: dict[str, dict[str, Any]] = {}
_STATE_FILE = Path(__file__).with_name(".web_sessions.json")
_SESSION_TITLES = {
    "web-shopper": "数码选购咨询",
    "laptop-compare": "轻薄本对比",
}
_SESSION_DESCRIPTIONS = {
    "web-shopper": "描述预算、用途和不能接受的点，参谋会边查边答。",
    "laptop-compare": "继续查看轻薄本参数、差评和真实使用成本。",
}
_DEFAULT_SESSION_CHOICES = (
    ("数码选购咨询\n刚刚 · 当前会话", "web-shopper"),
    ("轻薄本对比\n昨天 · 4 条消息", "laptop-compare"),
)
_SESSION_CHOICES = list(_DEFAULT_SESSION_CHOICES)
_PHASE_LABELS = {
    "idle": "待命",
    "thinking": "正在思考",
    "tool": "正在查证",
    "writing": "正在回复",
    "done": "已完成",
    "error": "调用失败",
}
_TOOL_ZH = {
    "search_product_reviews_and_complaints": "全网差评搜索",
    "calculate_specs_and_budget": "性价比测算",
    "query_hardware_traps": "避坑宝典",
    "query_price_history": "历史价格",
    "query_official_specs": "官方参数",
    "estimate_trade_in": "以旧换新估价",
    "query_delivery_time": "物流时效",
    "query_after_sales": "售后政策",
}
_ARG_ZH = {
    "query_keyword": "关键词",
    "formula": "算式",
    "category_or_term": "品类",
    "product": "产品",
    "old_device": "旧机",
    "condition": "成色",
    "warehouse": "仓库",
    "region": "地区",
    "brand": "品牌",
}


def _in_pytest() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


def _serialize_process(result: dict[str, Any] | None, phase: str = "done") -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for item in (result or {}).get("intermediate_steps") or []:
        if isinstance(item, dict):
            steps.append(
                {
                    "tool": item.get("tool", ""),
                    "tool_input": item.get("tool_input", {}),
                    "observation": item.get("observation", ""),
                }
            )
            continue
        action, observation = item
        steps.append(
            {
                "tool": getattr(action, "tool", ""),
                "tool_input": getattr(action, "tool_input", {}),
                "observation": observation,
            }
        )
    return {
        "intermediate_steps": steps,
        "total_tokens": (result or {}).get("total_tokens") or 0,
        "phase": (result or {}).get("phase") or phase,
    }


def _pairs_from_process(result: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    pairs: list[tuple[Any, Any]] = []
    for item in (result or {}).get("intermediate_steps") or []:
        if isinstance(item, dict):
            pairs.append(
                (
                    SimpleNamespace(tool=item.get("tool", ""), tool_input=item.get("tool_input", {})),
                    item.get("observation", ""),
                )
            )
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            pairs.append((item[0], item[1]))
    return pairs


def _demo_laptop_report() -> dict[str, Any]:
    return {
        "category_summary": "5000 元档、写代码优先的轻薄本",
        "budget_evaluation": "这个预算刚好能买到 32G 内存和高色域屏，再往下压就会碰到板载内存和低色域。",
        "overall_value_score": 84,
        "recommended_products": [
            {
                "brand_and_model": "ThinkBook 14+ 锐龙版",
                "price_range": "¥4899–5299",
                "key_specs": "R7-8845H / 32G 双通道 / 1TB / 2.5K 120Hz 100%sRGB / 约 1.4kg",
                "standout_pros": ["内存可加到 64G", "屏幕色准适合长时间写代码", "键盘键程更适合码字"],
                "fatal_cons": ["官方标配可能混到低亮度屏，下单要认准 100%sRGB"],
            },
            {
                "brand_and_model": "小新 Pro 14 锐龙版",
                "price_range": "¥4699–4999",
                "key_specs": "R7-8745H / 32G LPDDR5x / 1TB / 2.8K 120Hz / 约 1.46kg",
                "standout_pros": ["同价位屏幕更细腻", "续航口碑更好", "轻一些，适合背去教室"],
                "fatal_cons": ["内存焊死，两年后多开 Docker 会吃紧"],
            },
        ],
        "trap_warnings": [
            "先认屏幕：45% NTSC 低色域常被写成高清屏，必须看到 100% sRGB 或 DCI-P3。",
            "16G 板载内存两年后会卡，写代码优先 32G，能插槽扩展更好。",
            "同一型号可能有高低配混用，下单核对内存、色域和充电接口。",
        ],
        "final_verdict": "写代码选 ThinkBook 14+ 的 32G 高色域版；更在意续航和重量再看小新 Pro 14，但要接受内存焊死。",
    }


def _demo_laptop_history() -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": "预算 5000 左右，买一台适合大学生写代码的轻薄本，要求续航长、不要太重，避开低色域和板载内存。",
        },
        {
            "role": "assistant",
            "content": "5000 这个价位，写代码优先看三件事：32G 内存、100% sRGB 屏幕、重量压在 1.5kg 附近。我对比了 ThinkBook 14+ 和小新 Pro 14：前者内存能加、键盘更适合码字；后者更轻、续航更好，但内存焊死。现在两台都在四千九上下，属于能买的价。",
        },
        {
            "role": "user",
            "content": "那两台怎么选？低色域版本怎么认出来？",
        },
        {
            "role": "assistant",
            "content": "认低色域就看参数页有没有写 100% sRGB / DCI-P3，只写高清屏、72% NTSC 以下都要避开。如果你会长期开 IDE 和虚拟机，选 ThinkBook 14+ 的 32G 高色域版；宿舍搬来搬去、更在意续航，再考虑小新 Pro 14，并接受内存不能加。右边有昨天整理好的研究过程和决策报告。",
        },
    ]


def _demo_laptop_process() -> dict[str, Any]:
    return {
        "intermediate_steps": [
            {
                "tool": "query_hardware_traps",
                "tool_input": {"category_or_term": "低色域屏幕 板载内存"},
                "observation": "轻薄本最常见的坑是 45% NTSC 低色域，以及 LPDDR 焊死内存两年后不够用。",
            },
            {
                "tool": "search_product_reviews_and_complaints",
                "tool_input": {"query_keyword": "小新 Pro14 低色域 板载内存"},
                "observation": "差评集中在内存焊死、个别批次屏幕偏暗，码字党更在意键盘键程。",
            },
            {
                "tool": "query_official_specs",
                "tool_input": {"product": "ThinkBook 14+"},
                "observation": "高色域版约 1.4kg，双通道内存可加到 64G，确认 100%sRGB 后再下单。",
            },
            {
                "tool": "query_price_history",
                "tool_input": {"product": "ThinkBook 14+"},
                "observation": "当前四千九上下，比前一波活动高一点，但仍在可入手区间。",
            },
        ],
        "total_tokens": 1860,
        "phase": "done",
    }


def get_agent(use_mcp: bool):
    """按 MCP 开关缓存 Agent；首次发送问题时才初始化模型。"""
    from .main import SmartBuyerAgent

    with _AGENT_LOCK:
        if use_mcp not in _AGENTS:
            _AGENTS[use_mcp] = SmartBuyerAgent(use_mcp=use_mcp)
        return _AGENTS[use_mcp]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\x1b", "")


def _normalize_session_id(value: Any) -> str:
    return _clean_text(value).strip() or "web-shopper"


def _copy_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    return [dict(message) for message in (history or [])]


def _session_history(session_id: str) -> list[dict[str, str]]:
    if session_id in _WEB_SESSION_HISTORY:
        return _copy_history(_WEB_SESSION_HISTORY[session_id])
    return [{"role": "assistant", "content": welcome_message()}]


def _last_user_message(history: list[dict[str, str]] | None) -> str:
    for message in reversed(history or []):
        if message.get("role") == "user" and _clean_text(message.get("content")).strip():
            return _clean_text(message.get("content")).strip()
    return ""


def welcome_message() -> str:
    return (
        "你好，我是 SmartBuyer。直接说预算、品类、使用场景和不能接受的点，"
        "我会查参数、看差评、算真实成本，再给出带避坑提醒的建议。"
    )


def session_title_html(session_id: str, live: str = "在线") -> str:
    session_id = _normalize_session_id(session_id)
    title = html.escape(_SESSION_TITLES.get(session_id, "新建会话"))
    description = html.escape(
        _SESSION_DESCRIPTIONS.get(session_id, "描述预算、用途和顾虑，Agent 会逐步帮你查证。")
    )
    live_class = "busy" if live not in {"在线", "待命"} else ""
    return (
        '<div class="chat-title"><div>'
        f"<h1>{title}</h1><p>{description}</p>"
        f'</div><span class="live-tag {live_class}">{html.escape(live)}</span></div>'
    )


def session_meta_html(session_id: str) -> str:
    session_id = _normalize_session_id(session_id)
    title = html.escape(_SESSION_TITLES.get(session_id, "新建会话"))
    return (
        '<div class="session-meta"><span>当前会话</span>'
        f"<strong>{title}</strong><code>{html.escape(session_id)}</code></div>"
    )


def _parse_tool_input(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items() if re.fullmatch(r"[a-z_]+", str(key) or "")}
    text = _clean_text(raw).strip()
    if not text:
        return {}
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(text)
            if isinstance(data, dict):
                return _parse_tool_input(data)
        except Exception:
            pass
    pairs = dict(re.findall(r'"([a-z_]+)"\s*:\s*"([^"]*)"', text))
    if pairs:
        return pairs
    if text.startswith("{") or text.startswith("["):
        return {}
    return {"查询": text}


def zh_tool_name(name: Any) -> str:
    key = _clean_text(name).strip()
    if key in _TOOL_ZH:
        return _TOOL_ZH[key]
    if re.fullmatch(r"[a-z0-9_]+", key or ""):
        return "其他查证"
    return key or "工具调用"


def zh_tool_query(raw: Any) -> str:
    parts: list[str] = []
    for key, value in _parse_tool_input(raw).items():
        text = _clean_text(value).strip()
        if not text:
            continue
        label = _ARG_ZH.get(str(key))
        parts.append(f"{label} {text}" if label else text)
    line = " · ".join(parts)
    return line[:42] + "…" if len(line) > 42 else line


def zh_tool_summary(observation: Any) -> str:
    text = _clean_text(observation)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"【[^】]*】", "", text)
    text = re.sub(r"[`*_#]+", "", text)
    lines = [re.sub(r"^[\s>\-\d.、]+", "", line).strip() for line in text.splitlines()]
    summary = " ".join(line for line in lines if line)
    summary = re.sub(r"\s+", " ", summary).strip()
    sentence = re.split(r"[。！？]", summary, maxsplit=1)[0].strip()
    if sentence:
        summary = sentence if sentence.endswith(("。", "！", "？", "…")) else sentence + "。"
    if len(summary) > 48:
        summary = summary[:48].rstrip("，,;；。 ") + "…"
    return summary


def format_steps(result: dict[str, Any] | None, phase: str = "idle") -> str:
    """把工具链收成中文时间线，不把英文函数名和原始返回整段甩出来。"""
    steps = _pairs_from_process(result)
    if not steps:
        if phase in {"thinking", "tool", "writing"}:
            return (
                '<div class="trace-empty live"><span class="trace-dot pulse"></span>'
                "正在分析需求，准备查证参数和真实评价。</div>"
            )
        return (
            '<div class="trace-empty"><span class="trace-dot"></span>'
            "发送需求后，研究过程会显示在这里。</div>"
        )

    cards: list[str] = []
    for index, (action, observation) in enumerate(steps, start=1):
        name = html.escape(zh_tool_name(getattr(action, "tool", "")))
        query = html.escape(zh_tool_query(getattr(action, "tool_input", {})))
        summary = html.escape(zh_tool_summary(observation))
        running = not _clean_text(observation).strip()
        status = "进行中" if running else "已完成"
        status_class = "running" if running else ""
        query_html = f'<p class="trace-query">{query}</p>' if query else ""
        if running:
            summary_html = f'<p class="trace-summary">{summary or "正在调用，请稍候…"}</p>'
        elif summary:
            summary_html = f'<p class="trace-summary">{summary}</p>'
        else:
            summary_html = ""
        cards.append(
            f'<article class="trace-card {"is-running" if running else ""}">'
            f'<div class="trace-card-head"><span class="trace-index">{index:02d}</span>'
            f'<strong>{name}</strong><span class="trace-status {status_class}">{status}</span></div>'
            f"{query_html}{summary_html}</article>"
        )
    return "".join(cards)


def render_process(result: dict[str, Any] | None = None, phase: str = "idle") -> str:
    result = result or {}
    steps = result.get("intermediate_steps") or []
    tokens = result.get("total_tokens") or 0
    phase_text = _PHASE_LABELS.get(phase, "待命")
    chips: list[str] = [f"<span>{html.escape(phase_text)}</span>"]
    if steps:
        chips.insert(0, f"<span>查了 {len(steps)} 步</span>")
    if tokens:
        chips.append(f"<span>用量 {int(tokens)}</span>")
    strip = f'<div class="trace-strip">{"".join(chips)}</div>' if phase != "idle" or steps else ""
    return f"{strip}{format_steps(result, phase)}"


def report_to_html(report: Any) -> str:
    """渲染 ShoppingDecisionReport，避免把报告变成一屏 JSON。"""
    if report is None:
        return (
            '<div class="report-empty">'
            "<p>这份会话还没有收成报告。</p>"
            "<p>聊完一轮后，用下面的按钮把建议钉在这里，切换会话也不会丢。</p>"
            "</div>"
        )
    data = report.model_dump() if hasattr(report, "model_dump") else dict(report)
    score = int(data.get("overall_value_score", 0))
    rank_labels = ("首选", "备选", "也可以看")
    product_cards = []
    for index, product in enumerate(data.get("recommended_products") or []):
        rank = rank_labels[index] if index < len(rank_labels) else f"方案 {index + 1}"
        pros = "".join(f"<li>{html.escape(_clean_text(item))}</li>" for item in product.get("standout_pros", []))
        cons = "".join(f"<li>{html.escape(_clean_text(item))}</li>" for item in product.get("fatal_cons", []))
        product_cards.append(
            '<article class="product-card">'
            '<div class="product-top">'
            f'<span class="product-rank">{rank}</span>'
            f'<h4>{html.escape(_clean_text(product.get("brand_and_model")))}</h4>'
            f'<span class="price">{html.escape(_clean_text(product.get("price_range")))}</span>'
            "</div>"
            f'<p class="specs">{html.escape(_clean_text(product.get("key_specs")))}</p>'
            '<div class="pros-cons">'
            f'<section><h5>亮点</h5><ul>{pros}</ul></section>'
            f'<section><h5>槽点</h5><ul>{cons}</ul></section>'
            "</div></article>"
        )
    traps = "".join(f"<li>{html.escape(_clean_text(item))}</li>" for item in data.get("trap_warnings", []))
    return (
        '<div class="report-shell">'
        '<header class="report-lead">'
        f'<h3>{html.escape(_clean_text(data.get("category_summary")))}</h3>'
        f'<p>{html.escape(_clean_text(data.get("budget_evaluation")))}</p>'
        f'<p class="report-score">性价比 <b>{score}</b><span>/100</span></p>'
        "</header>"
        '<section class="report-section">'
        "<h4>可以买的机型</h4>"
        + ("".join(product_cards) or '<div class="report-empty">模型未返回推荐机型。</div>')
        + "</section>"
        '<section class="report-section trap-section"><h4>下单前核对</h4>'
        f'<ul class="trap-list">{traps or "<li>暂无额外提醒。</li>"}</ul></section>'
        '<section class="verdict"><h4>拍板</h4><p>'
        f'{html.escape(_clean_text(data.get("final_verdict")))}</p></section></div>'
    )


def seed_demo_sessions() -> None:
    """侧栏「轻薄本对比」是带档案的示例会话：对话、研究过程、报告一起恢复。"""
    report = _demo_laptop_report()
    _WEB_SESSION_HISTORY.setdefault("laptop-compare", _demo_laptop_history())
    _WEB_SESSION_PROCESS.setdefault("laptop-compare", _demo_laptop_process())
    _WEB_SESSION_REPORTS.setdefault(
        "laptop-compare",
        {
            "html": report_to_html(report),
            "json": report,
            "status": '<span class="status-ok">● 昨天已整理成决策报告</span>',
            "demand": _demo_laptop_history()[0]["content"],
        },
    )


def _load_workspace() -> None:
    seed_demo_sessions()
    if _in_pytest() or not _STATE_FILE.exists():
        return
    try:
        payload = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for session_id, bundle in (payload.get("sessions") or {}).items():
        if not session_id:
            continue
        if bundle.get("history") is not None:
            _WEB_SESSION_HISTORY[session_id] = list(bundle["history"])
        if bundle.get("process"):
            _WEB_SESSION_PROCESS[session_id] = bundle["process"]
        if bundle.get("report"):
            packed = dict(bundle["report"])
            if packed.get("json") and not packed.get("html"):
                packed["html"] = report_to_html(packed["json"])
            _WEB_SESSION_REPORTS[session_id] = packed
        if bundle.get("title"):
            _SESSION_TITLES[session_id] = bundle["title"]
        if bundle.get("description"):
            _SESSION_DESCRIPTIONS[session_id] = bundle["description"]
        if session_id not in {value for _, value in _SESSION_CHOICES}:
            label = bundle.get("label") or _SESSION_TITLES.get(session_id, session_id)
            _SESSION_CHOICES.append((label, session_id))


def _save_workspace() -> None:
    if _in_pytest():
        return
    sessions: dict[str, Any] = {}
    keys = set(_WEB_SESSION_HISTORY) | set(_WEB_SESSION_PROCESS) | set(_WEB_SESSION_REPORTS)
    for session_id in keys:
        label = next((text for text, value in _SESSION_CHOICES if value == session_id), None)
        sessions[session_id] = {
            "history": _WEB_SESSION_HISTORY.get(session_id, []),
            "process": _WEB_SESSION_PROCESS.get(session_id, {}),
            "report": _WEB_SESSION_REPORTS.get(session_id, {}),
            "title": _SESSION_TITLES.get(session_id),
            "description": _SESSION_DESCRIPTIONS.get(session_id),
            "label": label,
        }
    try:
        _STATE_FILE.write_text(json.dumps({"sessions": sessions}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _remember_process(session_id: str, result: dict[str, Any] | None, phase: str = "done", persist: bool = True) -> None:
    _WEB_SESSION_PROCESS[session_id] = _serialize_process(result, phase)
    if persist:
        _save_workspace()


def _remember_report(session_id: str, html_doc: str, payload: dict[str, Any], status: str, demand: str) -> None:
    _WEB_SESSION_REPORTS[session_id] = {
        "html": html_doc,
        "json": payload,
        "status": status,
        "demand": demand,
    }
    _save_workspace()


def _session_process_html(session_id: str) -> str:
    packed = _WEB_SESSION_PROCESS.get(session_id)
    if not packed or not packed.get("intermediate_steps"):
        return render_process(phase="idle")
    return render_process(packed, packed.get("phase") or "done")


def _session_status_html(session_id: str) -> str:
    title = html.escape(_SESSION_TITLES.get(session_id, session_id))
    if _WEB_SESSION_PROCESS.get(session_id, {}).get("intermediate_steps"):
        return f'<span class="status-ok">● 已切换到「{title}」，研究过程一并恢复</span>'
    return f'<span class="status-ok">● 已切换到「{title}」</span>'


def _session_report_views(session_id: str) -> tuple[str, dict[str, Any], str, str]:
    packed = _WEB_SESSION_REPORTS.get(session_id) or {}
    return (
        packed.get("html") or report_to_html(None),
        packed.get("json") or {},
        packed.get("status") or '<div class="trace-empty">这个会话还没有决策报告。</div>',
        packed.get("demand") or _last_user_message(_WEB_SESSION_HISTORY.get(session_id)),
    )


def help_html() -> str:
    return """
    <div class="pane-copy">
      <ol class="help-steps">
        <li><b>先报预算</b>，别只丢一句「求推荐」。</li>
        <li><b>说清品类和场景</b>：写代码、通勤降噪、出差轻薄。</li>
        <li><b>把不能接受的点讲出来</b>：太重、低色域、板载内存。</li>
        <li><b>有旧机就提以旧换新</b>，参谋会算真实入手价。</li>
      </ol>
      <div class="help-card"><h3>页面怎么用</h3>
        <p>中间是对话。发送后会立刻看到你的话，回复按字往外冒。</p>
        <p>右边默认是「研究过程」：看参谋调了哪些工具，不是聊天主界面。</p>
        <p>「决策报告」把这轮咨询收成可保存的建议卡片。</p>
      </div>
    </div>
    """


def show_right_view(view: str, tab: str = "trace"):
    """左栏入口只切换右栏页面，中间对话保持不动。"""
    return (
        gr.update(visible=view == "workspace"),
        gr.update(visible=view == "settings"),
        gr.update(visible=view == "help"),
        gr.update(selected=tab),
    )


def _iter_agent_events(agent: Any, message: str, session_id: str, user_id: str) -> Iterable[dict[str, Any]]:
    if hasattr(agent, "iter_chat_events"):
        yield from agent.iter_chat_events(message, session_id=session_id, user_id=user_id)
        return
    result = agent.chat_recommend(message, session_id=session_id, user_id=user_id)
    yield {**result, "phase": "done", "done": True}


def ask_agent(message: str, history: list[dict[str, str]] | None, user_id: str, session_id: str, use_mcp: bool):
    """先立刻画出用户消息，再流式追加参谋回复。"""
    session_id = _normalize_session_id(session_id)
    history = _copy_history(history)
    message = (message or "").strip()
    if not message:
        yield history, render_process(phase="idle"), "等待输入", "", session_id
        return

    user_id = (user_id or "guest").strip() or "guest"
    history = history + [{"role": "user", "content": message}]
    yield history, render_process(phase="thinking"), '<span class="status-ok">● 正在分析需求</span>', "", session_id

    history = history + [{"role": "assistant", "content": "正在分析你的需求…"}]
    yield history, render_process(phase="thinking"), '<span class="status-ok">● 正在分析需求</span>', "", session_id

    try:
        result = {"intermediate_steps": [], "total_tokens": 0, "cost_usd": 0.0, "phase": "thinking"}
        for result in _iter_agent_events(get_agent(bool(use_mcp)), message, session_id, user_id):
            phase = result.get("phase") or "writing"
            text = _clean_text(result.get("output")).strip()
            if result.get("done"):
                text = text or "模型没有返回文字，请重试。"
            elif not text:
                text = "正在查证参数和真实评价…" if phase == "tool" else "正在分析你的需求…"
            caret = "" if result.get("done") else "▍"
            history[-1] = {"role": "assistant", "content": text + caret}
            if result.get("done"):
                status = (
                    f'<span class="status-ok">● 已完成</span>'
                    f'<span class="status-meta">{result.get("total_tokens", 0)} tokens · '
                    f'${result.get("cost_usd", 0.0):.5f}</span>'
                )
            elif phase == "tool":
                status = '<span class="status-ok">● 正在查证工具结果</span>'
            else:
                status = '<span class="status-ok">● 正在回复</span>'
            _WEB_SESSION_HISTORY[session_id] = _copy_history(history)
            _remember_process(session_id, result, phase, persist=bool(result.get("done")))
            yield history, render_process(result, phase), status, "", session_id
        _WEB_SESSION_HISTORY[session_id] = _copy_history(history)
        _save_workspace()
    except Exception as exc:  # 页面内给出可行动的配置提示
        error = _clean_text(exc)
        hint = "请检查 code/.env 中的 API Key、Base URL 和模型名。"
        if "API" in error or "api" in error or "401" in error or "404" in error:
            error = f"{error}\n\n{hint}"
        history[-1] = {"role": "assistant", "content": f"暂时无法完成这轮问诊：\n\n{error}"}
        _WEB_SESSION_HISTORY[session_id] = _copy_history(history)
        _save_workspace()
        yield (
            history,
            f'<div class="trace-error">{html.escape(error)}</div>',
            '<span class="status-bad">● 调用失败</span>',
            "",
            session_id,
        )


def make_report(demand: str, use_mcp: bool, history: list[dict[str, str]] | None = None, session_id: str | None = None):
    session_id = _normalize_session_id(session_id) if session_id else ""
    demand = (demand or "").strip() or _last_user_message(history)
    if not demand:
        empty = (
            report_to_html(None),
            {},
            '<div class="trace-empty">先在对话里说清购买需求，或在上方补一句。</div>',
        )
        if session_id:
            _remember_report(session_id, empty[0], empty[1], empty[2], "")
        return empty
    try:
        report = get_agent(bool(use_mcp)).generate_structured_report(demand)
        views = (
            report_to_html(report),
            report.model_dump(),
            '<div class="status-ok">● 报告已生成，切换会话后仍会留在这一边。</div>',
        )
        if session_id:
            _remember_report(session_id, views[0], views[1], views[2], demand)
        return views
    except Exception as exc:
        message = _clean_text(exc)
        failed = (
            report_to_html(None),
            {},
            f'<div class="trace-error">生成失败：{html.escape(message)}<br>请检查模型配置后重试。</div>',
        )
        return failed


def make_report_and_open(demand: str, use_mcp: bool, history: list[dict[str, str]] | None = None, session_id: str | None = None):
    report_html, report_json, report_status = make_report(demand, use_mcp, history, session_id)
    return report_html, report_json, report_status, gr.update(selected="report")


def select_session(session_id: str):
    """切换左侧会话，并恢复该会话的对话、研究过程和决策报告。"""
    session_id = _normalize_session_id(session_id)
    report_html, report_json, report_status, report_demand = _session_report_views(session_id)
    return (
        _session_history(session_id),
        _session_process_html(session_id),
        _session_status_html(session_id),
        "",
        session_id,
        session_title_html(session_id),
        session_meta_html(session_id),
        report_html,
        report_json,
        report_status,
        report_demand,
    )


def start_new_session():
    """创建独立会话，并同步到左侧最近会话列表。"""
    short_code = uuid4().hex[:8]
    session_id = f"web-{datetime.now().strftime('%m%d')}-{short_code}"
    _SESSION_TITLES[session_id] = "新建选购咨询"
    _SESSION_DESCRIPTIONS[session_id] = "这是一个全新的上下文，不会混入之前会话的消息。"
    _WEB_SESSION_HISTORY[session_id] = []
    _WEB_SESSION_PROCESS.pop(session_id, None)
    _WEB_SESSION_REPORTS.pop(session_id, None)
    _SESSION_CHOICES.insert(0, (f"新建选购咨询 · {short_code[:4].upper()}\n刚刚 · 空白会话", session_id))
    _save_workspace()
    empty_report = _session_report_views(session_id)
    return (
        [],
        render_process(phase="idle"),
        '<span class="status-ok">● 已创建新的空白会话</span>',
        "",
        gr.update(choices=list(_SESSION_CHOICES), value=session_id),
        session_title_html(session_id),
        session_id,
        session_meta_html(session_id),
        *empty_report,
    )


def clear_chat(session_id: str):
    session_id = _normalize_session_id(session_id)
    _WEB_SESSION_HISTORY[session_id] = []
    _WEB_SESSION_PROCESS.pop(session_id, None)
    _WEB_SESSION_REPORTS.pop(session_id, None)
    _save_workspace()
    return (
        [],
        render_process(phase="idle"),
        '<span class="status-ok">● 已清空本轮对话</span>',
        "",
        *_session_report_views(session_id),
    )


CSS = r"""
:root{
  --canvas:#f3f5f8;
  --surface:#ffffff;
  --surface-alt:#f7f9fb;
  --ink:#17202a;
  --muted:#66737f;
  --faint:#98a3ad;
  --border:#e4e8ed;
  --navy:#1e3a52;
  --blue:#2f6fed;
  --blue-soft:#edf3ff;
  --coral:#df765f;
  --green:#25845a;
  --shadow:0 8px 24px #17202a0d;
}
*{box-sizing:border-box}
html,body,.gradio-container{
  margin:0!important;
  background:var(--canvas)!important;
  color:var(--ink)!important;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif!important;
}
::selection{background:#2f6fed33;color:inherit}
.sidebar,.chatbox,.context-tabs .tabitem{scrollbar-width:thin;scrollbar-color:#c5d0da transparent}
.gradio-container,.main.fillable{width:100%!important;max-width:none!important;padding:0!important}
.app-shell{min-height:100vh!important;gap:0!important;width:100%!important}
.command-bar{
  height:56px;padding:0 22px;display:flex;align-items:center;justify-content:space-between;
  background:var(--surface);border-bottom:1px solid var(--border);
}
.brand-lockup,.side-brand{display:flex;align-items:center;gap:10px}
.brand-mark,.side-logo{
  width:30px;height:30px;display:grid;place-items:center;border-radius:9px;
  background:var(--navy);color:#fff;font-size:15px;
}
.brand-lockup b,.side-brand b{font-size:15px;letter-spacing:-.02em;font-weight:700}
.brand-lockup small,.side-brand small{display:block;color:#5c6b78;font-size:12px;letter-spacing:.01em;margin-top:2px}
.command-meta{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:12px}
.workspace-state{display:flex;align-items:center;gap:6px}
.workspace-state i{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block}
.agent-layout{
  display:grid!important;
  grid-template-columns:260px minmax(0,1fr) 360px!important;
  width:100%!important;height:calc(100vh - 56px)!important;min-height:0!important;gap:0!important;
}
.sidebar,.main-column,.context-column{min-width:0!important;max-width:none!important;height:100%!important}
.sidebar{
  display:flex!important;flex-direction:column!important;gap:0!important;
  background:#dfe6ee!important;border-right:1px solid #cfd8e1!important;
  padding:18px 12px 10px!important;overflow:hidden!important;
}
.sidebar>*{flex:0 0 auto!important;min-height:0!important;margin:0!important}
.sidebar>.session-picker{flex:1 1 auto!important;min-height:0!important;overflow:auto!important}
.side-brand{padding:2px 8px 18px;gap:12px}
.side-brand b{font-size:16px;letter-spacing:-.02em;color:var(--ink)}
.side-brand small{font-size:12px;letter-spacing:.01em;color:#4d5d6a;margin-top:3px}
.brand-mark,.side-logo{width:36px;height:36px;border-radius:11px;font-size:16px}
.new-session{
  width:100%;min-height:44px!important;height:44px!important;max-height:44px!important;flex:0 0 44px!important;
  background:var(--navy)!important;color:#fff!important;
  border:0!important;border-radius:12px!important;font-size:14px!important;font-weight:650!important;
  box-shadow:0 6px 14px #1e3a5224;
}
.new-session:hover{filter:brightness(1.08)}
.side-label{margin:18px 8px 8px;color:#3f5160;font-size:12px;font-weight:700;letter-spacing:.01em}
.session-picker{margin:0!important;background:transparent!important;border:0!important;padding:0!important;flex:1 1 auto!important;min-height:0!important;overflow:auto!important}
.session-picker>label,.session-picker [data-testid="block-info"]{display:none!important}
.session-picker .wrap{gap:4px!important;display:flex!important;flex-direction:column!important}
.session-picker label{
  display:block!important;min-height:56px!important;align-items:flex-start!important;
  padding:10px 12px 10px 14px!important;border:0!important;border-radius:12px!important;
  background:transparent!important;box-shadow:none!important;color:var(--ink)!important;cursor:pointer!important;
  position:relative!important;
}
.session-picker label:hover{background:#f3f7fb!important}
.session-picker label:has(input:checked),.session-picker label.selected{
  background:#fff!important;color:#143044!important;
  box-shadow:inset 3px 0 0 var(--navy),0 2px 8px #17202a12!important;
}
.session-picker label:focus-within{outline:2px solid var(--blue);outline-offset:2px}
.session-picker input[type="radio"]{
  appearance:none!important;-webkit-appearance:none!important;clip:rect(0 0 0 0)!important;
  width:1px!important;height:1px!important;min-width:0!important;margin:0!important;padding:0!important;
  position:absolute!important;opacity:0!important;pointer-events:none!important;border:0!important;
}
.session-picker span{
  display:block!important;white-space:normal!important;font-size:14px!important;font-weight:650!important;
  line-height:1.35!important;color:#143044!important;
}
.session-picker .sess-title{display:block;font-size:14px;font-weight:650;color:#143044;line-height:1.35}
.session-picker .sess-meta{display:block;margin-top:4px;font-size:12px;font-weight:500;font-style:normal;color:#5b6c79;line-height:1.3}
.session-picker label:has(input:checked) .sess-title,.session-picker label.selected .sess-title{color:#143044}
.side-dock{
  margin-top:auto!important;flex:0 0 auto!important;padding:10px 0 4px!important;
  border-top:1px solid #cfd8e1!important;background:transparent!important;
  gap:2px!important;
}
.side-dock .side-label{margin:4px 8px 6px}
.side-nav-btn{
  width:100%!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;
  gap:10px!important;background:transparent!important;border:0!important;box-shadow:none!important;
  color:#143044!important;border-radius:10px!important;min-height:42px!important;
  font-size:14px!important;font-weight:650!important;padding:0 12px!important;
}
.side-nav-btn::before{
  content:"";width:18px;height:18px;flex:none;background:#143044;
  -webkit-mask:center / contain no-repeat;mask:center / contain no-repeat;
}
.nav-settings::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cpath d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.2.63.2 1.3 0 1.93H21a2 2 0 1 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15z'/%3E%3C/svg%3E");mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cpath d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.2.63.2 1.3 0 1.93H21a2 2 0 1 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15z'/%3E%3C/svg%3E")}
.nav-help::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Cpath d='M9.1 9a3 3 0 1 1 5.8 1c0 2-3 2.2-3 4'/%3E%3Ccircle cx='12' cy='17' r='.8' fill='black' stroke='none'/%3E%3C/svg%3E");mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Cpath d='M9.1 9a3 3 0 1 1 5.8 1c0 2-3 2.2-3 4'/%3E%3Ccircle cx='12' cy='17' r='.8' fill='black' stroke='none'/%3E%3C/svg%3E")}
.side-nav-btn:hover{background:#f3f7fb!important}
.side-nav-btn:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.main-column{padding:16px 18px 16px!important;overflow:hidden!important}
.chat-workspace{
  height:100%!important;min-height:0!important;display:flex!important;flex-direction:column!important;
  background:var(--surface)!important;border:1px solid var(--border)!important;border-radius:14px!important;
  box-shadow:var(--shadow)!important;overflow:hidden!important;
}
.chat-title{display:flex;justify-content:space-between;align-items:flex-start;padding:18px 22px;border-bottom:1px solid var(--border)}
.chat-title h1{font-size:16px;margin:0 0 4px;color:var(--ink)}
.chat-title p{font-size:12px;color:var(--muted);margin:0;line-height:1.5}
.live-tag{color:var(--green)!important;font-size:11px!important;font-weight:650}
.live-tag:before{content:"●";margin-right:5px}
.live-tag.busy{color:var(--blue)!important}
.chatbox{flex:1 1 0!important;min-height:140px!important;overflow:auto!important;padding:16px 18px 8px!important;border:0!important;background:transparent!important}
.chatbox .message,.chatbox .md,.chatbox p{font-size:15px!important;line-height:1.65!important}
#smartbuyer-chat .bubble-wrap,.chatbox .bubble-wrap{
  max-width:none!important;width:100%!important;background:transparent!important;border:0!important;
  border-radius:0!important;box-shadow:none!important;color:inherit!important;padding:4px 4px 8px!important;
}
#smartbuyer-chat .message-wrap,.chatbox .message-wrap{width:100%!important;max-width:none!important}
#smartbuyer-chat .message-row,.chatbox .message-row{
  display:flex!important;width:100%!important;max-width:none!important;margin:8px 0!important;
}
#smartbuyer-chat .message-row.bot-row,.chatbox .bot-row{
  justify-content:flex-start!important;margin-right:auto!important;padding-right:16%!important;padding-left:0!important;
}
#smartbuyer-chat .message-row.user-row,.chatbox .user-row{
  justify-content:flex-end!important;margin-left:auto!important;margin-right:0!important;
  padding-left:16%!important;padding-right:0!important;
}
#smartbuyer-chat .user-row .flex-wrap,#smartbuyer-chat .bot-row .flex-wrap{
  width:auto!important;max-width:100%!important;margin:0!important;
}
#smartbuyer-chat .message.bot,#smartbuyer-chat [data-testid="bot"]{
  background:#f4f6f8!important;border:1px solid #e6ebf0!important;color:var(--ink)!important;
  border-radius:16px 16px 16px 4px!important;box-shadow:none!important;
}
#smartbuyer-chat [data-testid="bot"],#smartbuyer-chat .message.bot [data-testid="bot"],
#smartbuyer-chat .message.bot .message-content,#smartbuyer-chat .message.bot .md,#smartbuyer-chat .message.bot p{
  background:transparent!important;color:var(--ink)!important;max-width:none!important;margin:0!important;box-shadow:none!important;border:0!important;
}
#smartbuyer-chat .message.user{
  margin-left:auto!important;margin-right:0!important;width:fit-content!important;max-width:100%!important;
  background:#143044!important;color:#f7fafc!important;border:0!important;
  border-radius:16px 16px 4px 16px!important;box-shadow:0 8px 18px #1430442e;
  padding:10px 14px!important;
}
#smartbuyer-chat .message.user [data-testid="user"],
#smartbuyer-chat .message.user .message-content,#smartbuyer-chat .message.user .md,
#smartbuyer-chat .message.user p,#smartbuyer-chat .message.user span{
  background:transparent!important;color:#f7fafc!important;-webkit-text-fill-color:#f7fafc!important;
  max-width:none!important;width:auto!important;margin:0!important;padding:0!important;
  box-shadow:none!important;border:0!important;border-radius:0!important;
  font-size:15px!important;line-height:1.7!important;font-weight:500!important;letter-spacing:.01em!important;
}
#smartbuyer-chat .message.user ::selection{background:#ffffff33;color:#fff}
.composer{
  flex:none!important;position:relative!important;margin:8px 16px 10px!important;padding:10px 12px 8px!important;
  border:1px solid #d5dee6!important;border-radius:14px!important;background:#fff!important;
  box-shadow:0 4px 14px #17202a08;--input-border-width:0px;--input-border-color:transparent;
}
.composer:focus-within{
  border:1px solid #d5dee6!important;box-shadow:0 4px 14px #17202a08!important;
}
.composer .styler,.composer .form,.composer .block,.composer .input-container,.composer label,
.composer .wrap,.composer .scroll-hide,.composer [data-testid="textbox"],.composer .show_textbox_border{
  background:transparent!important;border:0!important;box-shadow:none!important;outline:none!important;
}
.composer textarea{
  min-height:56px!important;max-height:120px!important;padding:4px 2px 8px!important;
  border:0!important;box-shadow:none!important;outline:none!important;background:transparent!important;font-size:14px!important;
  resize:none!important;
}
.composer textarea:focus,.composer .show_textbox_border:focus,.composer .show_textbox_border:focus-within,
.composer .input-container:focus-within,.composer *:focus,.composer *:focus-visible{
  outline:none!important;box-shadow:none!important;border:0!important;border-color:transparent!important;
}
.composer-row{align-items:center!important;justify-content:flex-end!important;gap:8px!important;margin-top:2px;background:transparent!important}
.chat-workspace .icon-button,button[aria-label="清空对话"]{display:none!important}
.gradio-container footer,.built-with{display:none!important}
.icon-btn{min-width:36px!important;width:36px!important;height:36px!important;padding:0!important;border-radius:10px!important;font-size:16px!important}
.clear-btn{border:1px solid var(--border)!important;background:var(--surface-alt)!important;color:var(--muted)!important}
.send-btn{background:var(--blue)!important;color:#fff!important;border:0!important}
.quick-row{flex:none!important;gap:8px!important;padding:0 18px 14px!important;align-items:center!important}
.quick-label{font-size:11px!important;color:var(--faint)!important}
.quick-row button{
  background:var(--surface-alt)!important;border:1px solid var(--border)!important;color:#586675!important;
  border-radius:999px!important;font-size:12px!important;min-height:30px!important;padding:0 12px!important;
}
.context-column{padding:16px 16px 16px 0!important;overflow:hidden!important}
.right-pane{
  height:100%!important;min-height:0!important;background:var(--surface)!important;border:1px solid var(--border)!important;
  border-radius:14px!important;box-shadow:var(--shadow)!important;overflow:hidden!important;display:flex!important;flex-direction:column!important;
}
.context-tabs{height:100%!important;min-height:0!important;overflow:hidden!important;background:transparent!important;border:0!important;box-shadow:none!important}
.context-tabs .tabitem{height:calc(100% - 46px)!important;overflow-y:auto!important;padding:0!important}
.context-heading,.pane-head{padding:18px 18px 14px;border-bottom:1px solid var(--border)}
.context-heading h2,.pane-head h2{font-size:15px;margin:0 0 6px}
.context-heading p,.pane-head p,.pane-copy p{font-size:12px;color:var(--muted);line-height:1.65;margin:0}
.inspector-content,.pane-body{padding:16px 18px 20px}
.trace-strip{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.trace-strip span{background:var(--surface-alt);border:1px solid var(--border);border-radius:999px;padding:4px 10px;font-size:11px;color:var(--muted)}
.report-view{padding:4px 18px 8px}
.report-empty{color:var(--muted);font-size:13px;line-height:1.65;padding:8px 0}
.trace-empty{color:var(--muted);font-size:13px;line-height:1.6;padding:12px 0}
.trace-empty.live{color:var(--blue)}
.trace-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#c5cdd5;margin-right:8px}
.trace-dot.pulse{background:var(--blue);animation:pulse 1.2s ease-in-out infinite}
.trace-card{border:1px solid #edf0f3;border-radius:12px;padding:12px;margin-bottom:10px;background:#fff}
.trace-card.is-running{border-color:#d9e6ff;background:#f8fbff}
.trace-card-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.trace-index{background:var(--blue-soft);color:var(--blue);border-radius:6px;font-size:10px;font-weight:700;padding:2px 6px}
.trace-status{margin-left:auto;color:var(--green);font-size:11px}
.trace-status.running{color:var(--blue)}
.trace-query{margin:0 0 4px;font-size:12px;color:var(--ink)!important}
.trace-summary{margin:0;font-size:12px;color:var(--muted)!important;line-height:1.55}
.status-meta{color:var(--muted);font-size:12px;line-height:1.6;margin:0}
.ghost-btn,.back-btn{
  width:100%!important;background:var(--surface-alt)!important;border:1px solid var(--border)!important;
  color:var(--ink)!important;border-radius:10px!important;min-height:36px!important;
}
.report-btn{background:var(--blue)!important;color:#fff!important;border:0!important;border-radius:10px!important;min-height:40px!important}
.report-input{margin:0 0 10px!important}
.report-input textarea{background:var(--surface-alt)!important;border-color:#d7dee6!important;min-height:64px!important;font-size:13px!important}
.report-shell{display:flex;flex-direction:column;gap:16px}
.report-lead h3{margin:0 0 6px;font-size:16px;line-height:1.4;color:var(--ink)}
.report-lead p{margin:0;font-size:13px;line-height:1.65;color:#4d5d6a}
.report-score{margin-top:10px!important;color:#143044!important;font-size:13px!important}
.report-score b{font-size:22px;letter-spacing:-.03em;margin:0 2px 0 6px}
.report-score span{color:#5b6c79;font-size:12px}
.report-section h4,.verdict h4{margin:0 0 10px;font-size:13px;font-weight:700;color:#143044}
.product-card{border:1px solid var(--border);border-radius:12px;padding:14px;margin:0 0 10px;background:#fff}
.product-card:last-child{margin-bottom:0}
.product-top{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px}
.product-rank{background:#edf3ff;color:var(--blue);border-radius:6px;padding:2px 7px;font-size:11px;font-weight:700}
.product-top h4{flex:1 1 100%;margin:0;font-size:14px;line-height:1.4}
.price{margin-left:auto;color:var(--blue);font-weight:700;font-size:13px;white-space:nowrap}
.specs{margin:8px 0 0;font-size:12px;line-height:1.55;color:#4d5d6a}
.pros-cons{display:flex;flex-direction:column;gap:10px;margin-top:12px}
.pros-cons h5{margin:0 0 6px;font-size:12px;font-weight:700}
.pros-cons section:first-child h5{color:var(--green)}
.pros-cons section:last-child h5{color:var(--coral)}
.pros-cons ul,.trap-list{margin:0;padding-left:16px;font-size:12px;line-height:1.6;color:var(--ink)}
.pros-cons li,.trap-list li{margin:0 0 4px}
.trap-section{background:#fff8ed;border:1px solid #f0e2cf;border-radius:12px;padding:14px}
.verdict{background:#f7f9fb;border:1px solid #ead7cf;border-radius:12px;padding:14px}
.verdict p{margin:0;font-size:13px;line-height:1.7;color:var(--ink)}
.json-panel{margin-top:12px!important}
.settings-stack{gap:12px!important}
.session-meta{background:var(--surface-alt);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:12px}
.session-meta span{display:block;color:var(--faint);font-size:10px;letter-spacing:.06em}
.session-meta strong{display:block;margin:6px 0 4px}
.session-meta code{font-size:11px;color:var(--muted)}
.help-steps{margin:0;padding-left:18px;color:var(--ink);font-size:13px;line-height:1.7}
.help-steps li{margin:0 0 8px}
.help-card{margin-top:16px;background:var(--surface-alt);border:1px solid var(--border);border-radius:12px;padding:14px}
.help-card h3{margin:0 0 8px;font-size:13px}
.status-ok{color:var(--green);font-size:12px}
.status-bad{color:var(--coral);font-size:12px}
.trace-error{color:var(--coral);font-size:12px;line-height:1.6}
.footer{display:none!important}
@keyframes pulse{50%{opacity:.35}}
@media(max-width:1100px){
  .agent-layout{grid-template-columns:200px minmax(0,1fr) 320px!important}
}
@media(max-width:860px){
  .agent-layout{display:flex!important;flex-direction:column!important;height:auto!important}
  .sidebar{display:none!important}
  .main-column,.context-column{height:auto!important;padding:12px!important;overflow:visible!important}
  .chat-workspace,.right-pane,.context-tabs,.context-tabs .tabitem{height:auto!important;min-height:420px!important}
}
"""

THEME = gr.themes.Soft(primary_hue="blue", secondary_hue="slate", neutral_hue="slate", radius_size="md")


def build_demo() -> gr.Blocks:
    """三栏 Agent 工作台：会话、对话、上下文。"""
    with gr.Blocks(title="SmartBuyer · 决策工作台", fill_width=True, fill_height=True) as demo:
        with gr.Column(elem_classes=["app-shell"]):
            gr.HTML(
                '<header class="command-bar"><div class="brand-lockup"><span class="brand-mark">✦</span>'
                "<div><b>SmartBuyer</b><small>私人选购参谋</small></div></div>"
                '<div class="command-meta"><span class="workspace-state"><i></i> 服务正常</span></div></header>'
            )
            with gr.Row(elem_classes=["agent-layout"], equal_height=True):
                with gr.Column(scale=1, min_width=220, elem_classes=["sidebar"]):
                    gr.HTML(
                        '<div class="side-brand"><span class="side-logo">✦</span>'
                        "<div><b>SmartBuyer</b><small>选购参谋</small></div></div>"
                    )
                    new_session = gr.Button("＋  新建会话", elem_classes=["new-session"])
                    gr.HTML('<div class="side-label">最近会话</div>')
                    recent_sessions = gr.Radio(
                        choices=_SESSION_CHOICES,
                        value="web-shopper",
                        label="最近会话",
                        show_label=False,
                        container=False,
                        interactive=True,
                        elem_classes=["session-picker"],
                    )
                    with gr.Column(elem_classes=["side-dock"]):
                        gr.HTML('<div class="side-label">工作区</div>')
                        settings_btn = gr.Button("设置", elem_classes=["side-nav-btn", "nav-settings"])
                        help_btn = gr.Button("使用帮助", elem_classes=["side-nav-btn", "nav-help"])
                with gr.Column(scale=5, elem_classes=["main-column"]):
                    with gr.Column(elem_classes=["conversation-panel", "chat-workspace"]):
                        chat_title = gr.HTML(session_title_html("web-shopper"))
                        chatbot = gr.Chatbot(
                            value=[{"role": "assistant", "content": welcome_message()}],
                            show_label=False,
                            elem_id="smartbuyer-chat",
                            elem_classes=["chatbox"],
                            layout="bubble",
                            group_consecutive_messages=False,
                            buttons=[],
                            placeholder="新会话还是空的。先说预算、品类和不能接受的点。",
                        )
                        with gr.Group(elem_classes=["composer"]):
                            message = gr.Textbox(
                                label="消息",
                                show_label=False,
                                lines=2,
                                max_lines=6,
                                container=False,
                                buttons=[],
                                placeholder="输入消息… 例如：预算 5000，想买一台适合写代码和出差的轻薄本。",
                            )
                            with gr.Row(elem_classes=["composer-row"]):
                                clear = gr.Button("↺", elem_id="clear-chat-button", elem_classes=["icon-btn", "clear-btn"], size="sm", scale=0, min_width=36)
                                send = gr.Button("➤", variant="primary", elem_id="send-chat-button", elem_classes=["icon-btn", "send-btn"], size="sm", scale=0, min_width=36)
                        with gr.Row(elem_classes=["quick-row"]):
                            gr.HTML('<span class="quick-label">快捷提问</span>')
                            sample_a = gr.Button("轻薄本", size="sm")
                            sample_b = gr.Button("降噪耳机", size="sm")
                            sample_c = gr.Button("以旧换新", size="sm")
                with gr.Column(scale=3, min_width=320, elem_classes=["context-column"]):
                    with gr.Column(visible=True, elem_classes=["right-pane"]) as view_workspace:
                        with gr.Tabs(elem_classes=["context-tabs"], selected="trace") as workspace_tabs:
                            with gr.Tab("研究过程", id="trace"):
                                gr.HTML('<div class="context-heading"><h2>研究过程</h2><p>这里只看参谋查了什么，不拿来填表。对话仍在中间进行。</p></div>')
                                with gr.Column(elem_classes=["inspector-content"]):
                                    trace = gr.HTML(render_process(phase="idle"), elem_classes=["trace-wrap"])
                                    status = gr.HTML('<span class="status-ok">● 等待你的第一个问题</span>')
                                    report_from_chat = gr.Button("把本轮咨询整理成决策报告", elem_classes=["ghost-btn"])
                            with gr.Tab("决策报告", id="report"):
                                gr.HTML('<div class="context-heading"><h2>决策报告</h2><p>每个会话各留一份。切走再回来，报告还在这边。</p></div>')
                                report_html = gr.HTML(report_to_html(None), elem_classes=["report-view"])
                                report_status = gr.HTML('<div class="trace-empty">这个会话还没有决策报告。</div>')
                                report_demand = gr.Textbox(label="改写需求", show_label=False, lines=2, elem_classes=["report-input"], placeholder="可留空，直接用刚才的对话；也可以在这里改写需求。")
                                report_btn = gr.Button("生成报告", variant="primary", elem_classes=["report-btn"])
                                with gr.Accordion("查看原始数据", open=False, elem_classes=["json-panel"]):
                                    report_json = gr.JSON(value={}, show_label=False)
                    with gr.Column(visible=False, elem_classes=["right-pane"]) as view_settings:
                        gr.HTML('<div class="pane-head"><h2>会话设置</h2><p>这些选项不影响聊天主界面，只决定参谋怎么记你、用哪些工具。</p></div>')
                        with gr.Column(elem_classes=["pane-body", "settings-stack"]):
                            session_meta = gr.HTML(session_meta_html("web-shopper"))
                            user_id = gr.Textbox(
                                value="guest",
                                label="用户画像 ID",
                                info="游客默认；填 user-veteran 更直接，填 user-rookie 会手把手讲。",
                            )
                            session_id = gr.State("web-shopper")
                            use_mcp = gr.Checkbox(value=True, label="启用实时行情与售后工具")
                            back_from_settings = gr.Button("返回研究过程", elem_classes=["back-btn"])
                    with gr.Column(visible=False, elem_classes=["right-pane"]) as view_help:
                        gr.HTML('<div class="pane-head"><h2>使用帮助</h2><p>把参谋当成懂行的朋友：你把约束说清楚，它负责去查、去算、去避坑。</p></div>')
                        with gr.Column(elem_classes=["pane-body"]):
                            gr.HTML(help_html())
                            back_from_help = gr.Button("返回研究过程", elem_classes=["back-btn"])

        right_views = [view_workspace, view_settings, view_help, workspace_tabs]
        report_outputs = [report_html, report_json, report_status, report_demand]
        new_session.click(
            start_new_session,
            outputs=[chatbot, trace, status, message, recent_sessions, chat_title, session_id, session_meta, *report_outputs],
        ).then(lambda: show_right_view("workspace"), outputs=right_views)
        recent_sessions.change(
            select_session,
            inputs=recent_sessions,
            outputs=[chatbot, trace, status, message, session_id, chat_title, session_meta, *report_outputs],
        ).then(lambda: show_right_view("workspace"), outputs=right_views)
        settings_btn.click(lambda: show_right_view("settings"), outputs=right_views)
        help_btn.click(lambda: show_right_view("help"), outputs=right_views)
        back_from_settings.click(lambda: show_right_view("workspace"), outputs=right_views)
        back_from_help.click(lambda: show_right_view("workspace"), outputs=right_views)
        send.click(lambda: show_right_view("workspace"), outputs=right_views).then(
            ask_agent, [message, chatbot, user_id, session_id, use_mcp], [chatbot, trace, status, message, session_id]
        )
        message.submit(lambda: show_right_view("workspace"), outputs=right_views).then(
            ask_agent, [message, chatbot, user_id, session_id, use_mcp], [chatbot, trace, status, message, session_id]
        )
        clear.click(clear_chat, inputs=session_id, outputs=[chatbot, trace, status, message, *report_outputs])
        sample_a.click(lambda: "预算 5000 左右，买一台适合大学生写代码的轻薄本，要求续航长、不要太重，避开低色域和板载内存。", outputs=message)
        sample_b.click(lambda: "预算 1000 左右，想买一副通勤用降噪耳机，比较在意降噪、通话和佩戴舒适度，有哪些坑？", outputs=message)
        sample_c.click(lambda: "我有一台九成新的 iPhone 15，想换一台预算 4500 左右的轻薄本，帮我算算以旧换新后是否划算。", outputs=message)
        report_from_chat.click(
            make_report_and_open,
            [report_demand, use_mcp, chatbot, session_id],
            [report_html, report_json, report_status, workspace_tabs],
        )
        report_btn.click(make_report, [report_demand, use_mcp, chatbot, session_id], [report_html, report_json, report_status])
        demo.load(
            None,
            js="""() => {
                const labels = {
                    '#clear-chat-button': '清空当前会话',
                    '#send-chat-button': '发送消息'
                };
                for (const [selector, label] of Object.entries(labels)) {
                    const button = document.querySelector(selector);
                    if (button) {
                        button.setAttribute('aria-label', label);
                        button.setAttribute('title', label);
                    }
                }
                const splitSessions = () => {
                    document.querySelectorAll('.session-picker label > span').forEach((span) => {
                        if (span.querySelector('.sess-title')) return;
                        const raw = (span.textContent || '').trim();
                        if (!raw) return;
                        const parts = raw.split(/\\n+/);
                        const title = parts[0] || raw;
                        const meta = parts.slice(1).join(' · ');
                        span.replaceChildren();
                        const strong = document.createElement('strong');
                        strong.className = 'sess-title';
                        strong.textContent = title;
                        span.appendChild(strong);
                        if (meta) {
                            const em = document.createElement('em');
                            em.className = 'sess-meta';
                            em.textContent = meta;
                            span.appendChild(em);
                        }
                    });
                };
                splitSessions();
                const picker = document.querySelector('.session-picker');
                if (picker) new MutationObserver(splitSessions).observe(picker, { childList: true, subtree: true });
            }""",
        )
    return demo


_load_workspace()


if __name__ == "__main__":
    port = int(os.getenv("SMARTBUYER_PORT", "7861"))
    build_demo().launch(server_name="127.0.0.1", server_port=port, share=False, theme=THEME, css=CSS)
