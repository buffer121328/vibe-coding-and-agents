"""
app_s13.py - 8.13 Mini-Agent 独立可视化工作台（轻量专注版）
与 app.py 全景工作台互补：本页只做一件事——ChatGPT 风格多轮对话 + 实时状态时间线 + 流式打字机输出。
依赖仅 gradio + s01 + s11 + s13，端口 7861（与 app.py 的 7860 错开，可同时运行）。
"""
import queue
import threading
import time
from types import SimpleNamespace
from typing import Dict, List, Any, Optional

import gradio as gr
from dotenv import load_dotenv

from s01_env_setup import ZhipuGLMClient
from s11_session import SessionStore
from s13_mini_agent import MiniAgent, polish_markdown

load_dotenv()

global_client = ZhipuGLMClient()
session_store = SessionStore(storage_dir="sessions")

# ========== 🎨 样式：网页版对话产品式工作台 ==========
custom_css = r"""
:root {
    --app-bg: #f7f7f8;
    --panel: #ffffff;
    --panel-muted: #f3f4f6;
    --line: #e5e7eb;
    --line-strong: #d1d5db;
    --ink: #18181b;
    --muted: #71717a;
    --brand: #7c3aed;
    --brand-dark: #6d28d9;
    --brand-soft: #f3e8ff;
    --success: #10b981;
}

html, body, .gradio-container {
    background: var(--app-bg) !important;
}

.gradio-container {
    max-width: none !important;
    width: 100% !important;
    min-height: 100vh !important;
    margin: 0 !important;
    padding: 0 !important;
    color: var(--ink) !important;
    font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif !important;
}

footer { display: none !important; }

#mini-agent-shell {
    min-height: 100vh !important;
    gap: 0 !important;
    align-items: stretch !important;
}

/* 左侧：像网页聊天产品的会话抽屉 */
#session-sidebar {
    flex: 0 0 270px !important;
    min-width: 270px !important;
    max-width: 270px !important;
    min-height: 100vh !important;
    padding: 16px 14px !important;
    gap: 14px !important;
    background: #f0f0f2 !important;
    border-right: 1px solid var(--line) !important;
}

.brand-lockup {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 4px 5px 10px;
}

.brand-mark {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    flex: 0 0 36px;
    border-radius: 11px;
    color: white;
    font-size: 18px;
    background: linear-gradient(145deg, #8b5cf6, #5b21b6);
    box-shadow: 0 7px 18px rgba(109, 40, 217, .22);
}

.brand-title { font-weight: 760; font-size: 14px; letter-spacing: -.01em; }
.brand-subtitle { margin-top: 1px; color: var(--muted); font-size: 11px; }

#new-session-btn {
    min-height: 44px !important;
    justify-content: flex-start !important;
    border: 1px solid var(--line-strong) !important;
    border-radius: 12px !important;
    background: white !important;
    color: var(--ink) !important;
    font-weight: 650 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, .04) !important;
}

#new-session-btn:hover {
    border-color: #a78bfa !important;
    background: #faf5ff !important;
    transform: translateY(-1px);
}

.sidebar-label {
    margin: 2px 5px -8px;
    color: #52525b;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
}

#session-picker, #session-picker > .block {
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}

#session-picker .wrap {
    border-color: var(--line) !important;
    border-radius: 12px !important;
    background: rgba(255, 255, 255, .72) !important;
}

#refresh-sessions-btn {
    min-height: 38px !important;
    border: 0 !important;
    background: transparent !important;
    color: #52525b !important;
    justify-content: flex-start !important;
    box-shadow: none !important;
}

#refresh-sessions-btn:hover { background: rgba(255, 255, 255, .72) !important; }

.sidebar-tip {
    margin-top: auto;
    padding: 12px;
    border: 1px solid #ddd6fe;
    border-radius: 14px;
    background: rgba(245, 243, 255, .9);
    color: #5b21b6;
    font-size: 11.5px;
    line-height: 1.55;
}

.sidebar-tip strong { display: block; margin-bottom: 3px; color: #4c1d95; }

/* 中央：对话主舞台 */
#conversation-main {
    min-width: 0 !important;
    min-height: 100vh !important;
    background: var(--panel) !important;
    gap: 0 !important;
}

.conversation-topbar {
    display: flex;
    min-height: 64px;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 11px 22px;
    border-bottom: 1px solid var(--line);
    background: rgba(255, 255, 255, .92);
    backdrop-filter: blur(14px);
}

.model-name { color: var(--ink); font-size: 15px; font-weight: 720; }
.model-meta { margin-top: 2px; color: var(--muted); font-size: 11.5px; }

.online-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 10px;
    border: 1px solid var(--line);
    border-radius: 999px;
    color: #52525b;
    background: #fafafa;
    font-size: 11.5px;
    font-weight: 600;
    white-space: nowrap;
}

.online-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--success);
    box-shadow: 0 0 0 4px rgba(16, 185, 129, .12);
}

#chat-window {
    height: calc(100vh - 260px) !important;
    min-height: 360px !important;
    max-height: none !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: white !important;
    box-shadow: none !important;
}

#chat-window .wrapper,
#chat-window .bubble-wrap {
    height: 100% !important;
    background: white !important;
}

#chat-window .top-panel { display: none !important; }

#chat-window .bubble-wrap {
    padding: 28px max(5vw, 28px) 24px !important;
    gap: 22px !important;
}

#chat-window .placeholder-content {
    height: 100% !important;
    display: grid !important;
    place-items: center !important;
    color: var(--muted) !important;
    text-align: center !important;
}

#chat-window .placeholder-content::before {
    content: "✦";
    display: grid;
    place-items: center;
    width: 50px;
    height: 50px;
    margin: 0 auto 12px;
    border-radius: 16px;
    color: white;
    font-size: 24px;
    background: linear-gradient(145deg, #8b5cf6, #5b21b6);
    box-shadow: 0 12px 28px rgba(109, 40, 217, .18);
}

#chat-window .placeholder-content::after {
    content: "今天想一起完成什么？\A 直接提问，或者从下方的示例开始。";
    display: block;
    white-space: pre;
    color: #71717a;
    font-size: 14px;
    line-height: 1.7;
}

#chat-window .message-row { max-width: 820px !important; margin-inline: auto !important; }
#chat-window .bot-row { padding-right: 11% !important; }
#chat-window .user-row { padding-left: 16% !important; }

#chat-window .message-row .message {
    border: 0 !important;
    box-shadow: none !important;
    font-size: 14px !important;
    line-height: 1.72 !important;
}

#chat-window .user-row .message {
    border-radius: 18px 18px 5px 18px !important;
    background: #f0f0f2 !important;
    color: #27272a !important;
}

#chat-window .bot-row .message { background: transparent !important; color: var(--ink) !important; }

#chat-window .bot-row .flex-wrap::before {
    content: "✦";
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    margin-right: 10px;
    flex: 0 0 28px;
    border-radius: 9px;
    color: white;
    font-size: 14px;
    background: linear-gradient(145deg, #8b5cf6, #6d28d9);
}

#chat-window .bot-row .flex-wrap { align-items: flex-start !important; }
#chat-window .message-buttons { opacity: 0; transition: opacity .16s ease; }
#chat-window .message-wrap:hover .message-buttons { opacity: 1; }

#prompt-dock {
    width: min(860px, calc(100% - 40px)) !important;
    margin: 0 auto !important;
    padding: 2px 0 15px !important;
    gap: 10px !important;
}

#suggestion-row {
    display: grid !important;
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    gap: 8px !important;
}

#suggestion-row button {
    min-width: 0 !important;
    min-height: 36px !important;
    padding: 7px 10px !important;
    overflow: hidden !important;
    border: 1px solid var(--line) !important;
    border-radius: 11px !important;
    color: #52525b !important;
    background: white !important;
    font-size: 11.5px !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, .025) !important;
}

#suggestion-row button:hover {
    border-color: #c4b5fd !important;
    color: #6d28d9 !important;
    background: #faf5ff !important;
}

#message-composer {
    border: 1px solid var(--line-strong) !important;
    border-radius: 18px !important;
    background: white !important;
    box-shadow: 0 8px 26px rgba(24, 24, 27, .08), 0 1px 3px rgba(24, 24, 27, .05) !important;
    overflow: hidden !important;
}

#message-composer textarea {
    min-height: 54px !important;
    padding: 16px 56px 12px 17px !important;
    color: var(--ink) !important;
    font-size: 14px !important;
    line-height: 1.5 !important;
    background: white !important;
}

#message-composer button {
    border-radius: 11px !important;
    background: var(--ink) !important;
    color: white !important;
}

.composer-footnote {
    color: #a1a1aa;
    font-size: 10.5px;
    text-align: center;
}

/* 右侧：将 Agent 内部过程收进可扫读的检查器 */
#inspector-panel {
    flex: 0 0 330px !important;
    min-width: 300px !important;
    max-width: 360px !important;
    min-height: 100vh !important;
    padding: 18px 16px !important;
    gap: 13px !important;
    border-left: 1px solid var(--line) !important;
    background: #fafafa !important;
}

.inspector-heading { padding: 1px 2px 3px; }
.inspector-title { color: var(--ink); font-size: 13px; font-weight: 750; }
.inspector-copy { margin-top: 3px; color: var(--muted); font-size: 11px; line-height: 1.45; }

.status-badge {
    display: flex;
    align-items: center;
    gap: 9px;
    min-height: 42px;
    padding: 9px 12px;
    border: 1px solid #ddd6fe;
    border-radius: 12px;
    color: #5b21b6;
    background: #f5f3ff;
    font-size: 12px;
    font-weight: 680;
}

.status-badge::before {
    content: "";
    width: 8px;
    height: 8px;
    flex: 0 0 8px;
    border-radius: 50%;
    background: #8b5cf6;
    box-shadow: 0 0 0 4px rgba(139, 92, 246, .12);
}

.status-badge.is-done {
    border-color: #a7f3d0;
    color: #047857;
    background: #ecfdf5;
}

.status-badge.is-done::before { background: #10b981; box-shadow: 0 0 0 4px rgba(16, 185, 129, .12); }
.status-badge.is-error { border-color: #fecaca; color: #b91c1c; background: #fef2f2; }
.status-badge.is-error::before { background: #ef4444; box-shadow: 0 0 0 4px rgba(239, 68, 68, .12); }

#timeline-card {
    height: calc(100vh - 370px) !important;
    min-height: 250px !important;
    overflow: auto !important;
    padding: 10px 11px !important;
    border: 1px solid var(--line) !important;
    border-radius: 14px !important;
    background: white !important;
    font-size: 11.5px !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, .025) !important;
}

#timeline-card table { display: table !important; width: 100% !important; margin: 0 !important; }
#timeline-card th, #timeline-card td { padding: 8px 6px !important; border-color: #f0f0f2 !important; }
#timeline-card th { color: var(--muted) !important; font-size: 10px !important; text-transform: uppercase; }
#timeline-card code { white-space: normal !important; word-break: break-word !important; }

#settings-accordion, #trace-accordion {
    border: 1px solid var(--line) !important;
    border-radius: 14px !important;
    background: white !important;
    overflow: hidden !important;
}

#settings-accordion .label-wrap, #trace-accordion .label-wrap { font-size: 12px !important; }
.option-grid { gap: 8px !important; }
.option-grid > .block { padding: 8px !important; border: 0 !important; background: #fafafa !important; }
#memory-permission { padding: 8px 2px 2px !important; }

@media (max-width: 1120px) {
    #session-sidebar { flex-basis: 230px !important; min-width: 230px !important; max-width: 230px !important; }
    #inspector-panel { flex-basis: 285px !important; min-width: 285px !important; }
    #chat-window .bubble-wrap { padding-inline: 22px !important; }
}

@media (max-width: 900px) {
    #mini-agent-shell { flex-direction: column !important; }
    #session-sidebar, #inspector-panel {
        flex: none !important;
        min-width: 100% !important;
        max-width: none !important;
        min-height: 0 !important;
        border: 0 !important;
    }
    #session-sidebar {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        padding: 10px 12px !important;
        border-bottom: 1px solid var(--line) !important;
    }
    .brand-lockup, .sidebar-label, .sidebar-tip { display: none !important; }
    #new-session-btn { flex: 0 0 150px !important; }
    #session-sidebar > .form { flex: 1 1 0 !important; min-width: 0 !important; }
    #session-picker { flex: 1 1 auto !important; min-width: 0 !important; }
    #refresh-sessions-btn { display: none !important; }
    #conversation-main { min-height: 660px !important; }
    #chat-window { height: 470px !important; }
    #inspector-panel { padding: 16px !important; border-top: 1px solid var(--line) !important; }
    #timeline-card { height: auto !important; max-height: 360px !important; }
}

@media (max-width: 620px) {
    #session-sidebar { justify-content: center !important; }
    #session-sidebar > .form { display: none !important; }
    .conversation-topbar { padding-inline: 15px; }
    .model-meta { display: none; }
    #chat-window { min-height: 360px !important; height: 56vh !important; }
    #chat-window .bubble-wrap { padding: 18px 12px !important; }
    #chat-window .bot-row, #chat-window .user-row { padding: 0 !important; }
    #prompt-dock { width: calc(100% - 20px) !important; }
    #suggestion-row { display: flex !important; overflow-x: auto !important; }
    #suggestion-row button { min-width: 210px !important; }
}
"""

custom_theme = gr.themes.Soft(
    primary_hue="violet",
    secondary_hue="zinc",
    neutral_hue="zinc",
    radius_size="lg",
)

# 事件类型 → 状态徽章文案（运行中态）与时间线 emoji
EVENT_LABELS: Dict[str, Dict[str, str]] = {
    "agent_start":     {"emoji": "🚀", "label": "开始处理"},
    "deep_think":      {"emoji": "🧠", "label": "深度思考规划"},
    "llm_call":        {"emoji": "🤔", "label": "模型思考中"},
    "tool_call":       {"emoji": "⚙️", "label": "调用工具"},
    "tool_result":     {"emoji": "✅", "label": "工具返回"},
    "permission_gate": {"emoji": "🛡️", "label": "权限门禁"},
    "compact":         {"emoji": "🗜️", "label": "上下文压缩"},
    "error":           {"emoji": "❌", "label": "错误"},
    "finish":          {"emoji": "🏁", "label": "完成"},
}

_TIMELINE_PLACEHOLDER = "*发送消息后，这里将实时滚动显示 Agent 的每一步动作...*"


def _status_html(text: str, state: str = "working") -> str:
    """统一渲染右侧运行状态，避免组件更新后丢失徽章样式"""
    state_class = {
        "done": "is-done",
        "error": "is-error",
    }.get(state, "")
    return f'<div class="status-badge {state_class}">{text}</div>'


def _one_line(text: str, limit: int = 90) -> str:
    """把多行文本压成单行并截断，用于时间线展示"""
    flat = " ".join(str(text).split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def _fmt_event_line(idx: int, event: Dict[str, Any]) -> str:
    """把一条事件字典格式化为时间线中的一行 Markdown"""
    meta = EVENT_LABELS.get(event.get("event_type", ""), {"emoji": "🔔", "label": "事件"})
    et, tool = event.get("event_type", ""), event.get("tool_name", "")
    if et == "tool_call":
        body = f"**{tool}** → `{_one_line(event.get('content', ''), 70)}`"
    elif et == "tool_result":
        body = f"**{tool}** ← `{_one_line(event.get('content', ''), 50)}`"
    elif et == "llm_call":
        body = f"思考推演（耗时 {event.get('latency_ms', 0):.0f}ms）"
    elif et == "finish":
        body = "回答已生成"
    else:
        body = _one_line(event.get("content", ""))
    return f"| {idx} | {meta['emoji']} **{meta['label']}** | {body} |"


def _render_timeline(timeline) -> str:
    """把时间线行列表拼成一张 Markdown 表格字符串（gr.Markdown 只接受字符串）"""
    if isinstance(timeline, str):
        return timeline if timeline.strip() else _TIMELINE_PLACEHOLDER
    if not timeline:
        return _TIMELINE_PLACEHOLDER
    header = "| # | 状态 | 详情 |\n| :--- | :--- | :--- |"
    return header + "\n" + "\n".join(timeline)


def _normalize_timeline(timeline) -> List[str]:
    """把上一轮渲染后的表格字符串还原为行列表，实现跨轮累计编号"""
    if isinstance(timeline, list):
        return timeline
    if isinstance(timeline, str) and timeline.startswith("| # |"):
        return [line for line in timeline.split("\n")[2:] if line.strip()]
    return []


def _session_choices() -> List[str]:
    """生成会话下拉选项：最新在前，带标题与消息数"""
    labels = []
    for s in session_store.list_sessions():
        labels.append(f"{s['title'][:24]}（{s['message_count']}条 · {s['session_id'][:8]}）")
    return labels


def _session_id_from_label(label: str) -> Optional[str]:
    """从下拉选项文本中解析 session_id 前 8 位，再映射回完整 ID"""
    import os
    if not label:
        return None
    prefix = label.split("·")[-1].rstrip("）)").strip()
    for fname in os.listdir("sessions"):
        if fname.endswith(".json") and fname.startswith(prefix):
            return fname[:-5]
    return None


# ========== 🔄 后台线程 + 队列：流式 delta 与事件实时搬运用 ==========
def _run_agent_stream(agent: MiniAgent, question: str, deep: bool,
                      active_skills: List[str], event_q: "queue.Queue") -> None:
    """在后台线程执行 agent.chat_stream()：正文 delta 与最终结果都推入队列"""

    def on_event(event) -> None:
        event_q.put({"__event__": event.to_dict()})

    agent.bus.subscribe("*", on_event)
    try:
        gen = agent.chat_stream(question, deep_think=deep, active_skills=active_skills)
        while True:
            try:
                delta = next(gen)
                if isinstance(delta, str):
                    event_q.put({"__delta__": delta})
            except StopIteration as e:
                event_q.put({"__done__": e.value})
                return
    except Exception as exc:
        event_q.put({"__error__": f"{type(exc).__name__}: {exc}"})


def chat_turn(user_msg, chat_history, agent_inst, opts, skills, allow_memory, timeline):
    """单轮流式对话生成器：气泡逐字增长 + 时间线实时滚动

    yields: (chatbot, 输入框, agent_state, 状态徽章, 时间线, trace_json)
    """
    if not user_msg or not user_msg.strip():
        yield chat_history, "", agent_inst, _status_html("请先输入一条消息", "error"), _render_timeline(timeline), gr.update()
        return

    if agent_inst is None:
        agent_inst = MiniAgent(global_client, session_store=session_store)
    # 每轮重新绑定最小权限回调，取消勾选后授权立即失效（与 app.py 同款）
    agent_inst.guard.approval_callback = (
        lambda tool_name, _args: bool(allow_memory) and tool_name == "save_preference"
    )

    chat_history = chat_history or []
    chat_history.append({"role": "user", "content": user_msg})
    chat_history.append({"role": "assistant", "content": "⏳ *(Agent 正在分析意图与调度推演...)*"})
    yield chat_history, "", agent_inst, _status_html("已接收任务，正在理解你的意图"), _render_timeline(timeline), gr.update()

    opts = opts or []
    skills = skills or []
    deep = "🧠 深度思考" in opts
    if deep:
        chat_history[-1]["content"] = "🧠 *(正在进行深度思考与前置规划推演...)*"
        yield chat_history, "", agent_inst, _status_html("深度思考与前置规划中"), _render_timeline(timeline), gr.update()

    if "🔍 强制联网搜索" in opts:
        if not any(m.get("content", "").startswith("用户要求你优先调用 web_search") for m in agent_inst.messages):
            agent_inst.messages.append({
                "role": "system",
                "content": "用户要求你优先调用 web_search 联网检索后再回答。请在获取到搜索结果后直接总结输出最终答案，不要重复搜索。",
            })

    timeline = _normalize_timeline(timeline)
    timeline.append(f"| {len(timeline) + 1} | 🚀 **开始处理** | {_one_line(user_msg, 60)} |")

    # 后台线程执行流式对话 + 队列接收 delta 与事件
    event_q: "queue.Queue" = queue.Queue()
    worker = threading.Thread(
        target=_run_agent_stream, args=(agent_inst, user_msg, deep, skills, event_q), daemon=True
    )
    worker.start()

    streamed: List[str] = []   # 已流式收到的正文增量
    result, error = None, None
    while result is None and error is None:
        try:
            msg = event_q.get(timeout=0.2)
        except queue.Empty:
            yield chat_history, "", agent_inst, gr.update(), _render_timeline(timeline), gr.update()
            continue

        if "__delta__" in msg:
            # 逐字增长：只在气泡尾部拼增量（首次替换掉占位气泡）
            streamed.append(msg["__delta__"])
            chat_history[-1]["content"] = "".join(streamed)
            yield chat_history, "", agent_inst, _status_html("正在生成回答…"), _render_timeline(timeline), gr.update()
            continue
        if "__event__" in msg:
            event = msg["__event__"]
            meta = EVENT_LABELS.get(event.get("event_type", ""))
            if not meta:
                continue
            timeline.append(_fmt_event_line(len(timeline) + 1, event))
            badge = meta["label"]
            if event.get("event_type") == "tool_call":
                badge = f"正在调用 {event.get('tool_name', '')}…"
            if not streamed:
                chat_history[-1]["content"] = f"⏳ *({badge})*"
            yield chat_history, "", agent_inst, _status_html(badge), _render_timeline(timeline), gr.update()
            continue
        if "__done__" in msg:
            result = msg["__done__"]
            break
        if "__error__" in msg:
            error = msg["__error__"]
            break

    if error:
        chat_history[-1]["content"] = f"❌ *({error})*"
        yield chat_history, "", agent_inst, _status_html("运行出错，请检查配置", "error"), _render_timeline(timeline), []
        return

    # 用润色后的完整答案替换流式拼接结果（修正标题空格/围栏配对），并附 usage 徽章
    ans = polish_markdown(result["final_answer"])
    usage_badge = result.get("usage_badge", "")
    if usage_badge:
        ans = (
            f"{ans}\n\n---\n"
            f"<div style='font-size:11px; color:#475569; font-family:ui-monospace, Menlo, monospace; "
            f"background:#f8fafc; padding:4px 9px; border-radius:6px; border:1px solid #e2e8f0; "
            f"display:inline-block; margin-top:4px;'>{usage_badge}</div>"
        )
    chat_history[-1]["content"] = ans
    yield chat_history, "", agent_inst, _status_html("回答已完成", "done"), _render_timeline(timeline), result["trace"]


def new_session():
    """🆕 新建会话：全新 Agent 实例（旧会话已自动存档），时间线清空"""
    return [], "", MiniAgent(global_client, session_store=session_store), _status_html("新会话已就绪"), _TIMELINE_PLACEHOLDER, []


def load_session(label, allow_memory):
    """📂 切换/加载历史会话：从 SessionStore 恢复消息为对话气泡"""
    sid = _session_id_from_label(label)
    if not sid:
        return [], "", None, _status_html("未找到这个会话", "error"), _TIMELINE_PLACEHOLDER, []
    node = session_store.load(sid)
    if node is None:
        return [], "", None, _status_html("会话存档读取失败", "error"), _TIMELINE_PLACEHOLDER, []

    agent = MiniAgent(global_client, session_store=session_store, session_id=node.session_id)
    history = []
    for m in node.messages:
        role = m.get("role")
        content = m.get("content")
        if not content:
            continue
        if role == "user":
            history.append({"role": "user", "content": str(content)})
        elif role == "assistant":
            history.append({"role": "assistant", "content": polish_markdown(str(content))})
    return (history, "", agent, _status_html(f"已恢复「{node.title[:20]}」，共 {len(node.messages)} 条消息", "done"),
            _TIMELINE_PLACEHOLDER, [])


def refresh_sessions():
    """🔄 刷新会话下拉列表"""
    return gr.update(choices=_session_choices())


# ========== 🖼️ 页面布局 ==========
with gr.Blocks(
    title="Mini-Agent · 智能对话",
    fill_width=True,
    fill_height=True,
) as demo:
    # 注意：Gradio 6 会对 State 初始值做 deepcopy，而 MiniAgent 内含 OpenAI 客户端不可复制，
    # 因此这里必须存 None，由 chat_turn 在首轮回调中懒创建。
    state_agent = gr.State(None)

    with gr.Row(elem_id="mini-agent-shell"):
        # ── 左：会话与存档 ──
        with gr.Column(elem_id="session-sidebar"):
            gr.HTML("""
            <div class="brand-lockup">
                <div class="brand-mark">✦</div>
                <div>
                    <div class="brand-title">Mini-Agent</div>
                    <div class="brand-subtitle">第八章 · 综合实战</div>
                </div>
            </div>
            """)
            new_btn = gr.Button("＋  新建对话", elem_id="new-session-btn")
            gr.HTML('<div class="sidebar-label">历史对话</div>')
            session_dd = gr.Dropdown(
                label="选择一条存档",
                choices=_session_choices(),
                value=None,
                interactive=True,
                show_label=False,
                container=False,
                elem_id="session-picker",
            )
            refresh_btn = gr.Button("↻  刷新会话列表", size="sm", elem_id="refresh-sessions-btn")
            gr.HTML("""
            <div class="sidebar-tip">
                <strong>💡 对话会自动存档</strong>
                可以随时切换历史会话；Agent 会带着对话上下文继续工作。
            </div>
            """)

        # ── 中：网页版对话主区 ──
        with gr.Column(scale=1, elem_id="conversation-main"):
            gr.HTML("""
            <div class="conversation-topbar">
                <div>
                    <div class="model-name">Mini-Agent <span style="color:#a1a1aa">⌤</span></div>
                    <div class="model-meta">GLM 主力模型 · 工具调用 · 上下文记忆</div>
                </div>
                <div class="online-pill"><span class="online-dot"></span>服务已就绪</div>
            </div>
            """)
            chatbot = gr.Chatbot(
                label="智能体多轮对话",
                show_label=False,
                height="calc(100vh - 260px)",
                elem_id="chat-window",
            )

            with gr.Column(elem_id="prompt-dock"):
                with gr.Row(elem_id="suggestion-row"):
                    p1 = gr.Button("🌐 搜索前端新趋势", size="sm")
                    p2 = gr.Button("💾 记住我的技术偏好", size="sm")
                    p3 = gr.Button("✨ 根据偏好写接口", size="sm")
                msg_input = gr.Textbox(
                    placeholder="给 Mini-Agent 发消息…",
                    lines=1,
                    max_lines=5,
                    show_label=False,
                    container=False,
                    submit_btn="↑",
                    elem_id="message-composer",
                )
                gr.HTML('<div class="composer-footnote">Mini-Agent 也可能犯错，重要结果请务必核对</div>')

        # ── 右：运行过程与高级设置 ──
        with gr.Column(elem_id="inspector-panel"):
            gr.HTML("""
            <div class="inspector-heading">
                <div class="inspector-title">运行过程</div>
                <div class="inspector-copy">像查外卖轨迹一样，实时看到 Agent 正在思考、调工具还是等权限。</div>
            </div>
            """)
            status_badge = gr.HTML(_status_html("待命中"))
            timeline_md = gr.Markdown(value=_TIMELINE_PLACEHOLDER, elem_id="timeline-card")
            with gr.Accordion("⚙️ 对话设置", open=False, elem_id="settings-accordion"):
                with gr.Row(elem_classes=["option-grid"]):
                    opts = gr.CheckboxGroup(
                        label="增强模式",
                        choices=["🧠 深度思考", "🔍 强制联网搜索"],
                        value=["🧠 深度思考"],
                    )
                    skills = gr.CheckboxGroup(
                        label="技能挂载",
                        choices=["git_expert", "python_cleaner"],
                        value=[],
                    )
                allow_memory = gr.Checkbox(
                    label="允许本轮保存个人偏好",
                    info="仅放行 save_preference，不授权终端或代码编辑",
                    value=False,
                    elem_id="memory-permission",
                )
            with gr.Accordion("🔍 原始 Trace 审计记录", open=False, elem_id="trace-accordion"):
                trace_json = gr.JSON(label="决策链路与权限事件", show_label=False)

    # 预设快捷提示词（填入输入框，用户确认后发送）
    p1.click(lambda: "2026年最新的主流前端框架有哪些新趋势？请联网核实", outputs=[msg_input])
    p2.click(lambda: "请记住我的偏好：我的全栈技术栈首选是 Python + FastAPI + TailwindCSS", outputs=[msg_input])
    p3.click(lambda: "我之前跟你说过的技术栈偏好是什么？请帮我写一个用户注册接口", outputs=[msg_input])

    msg_input.submit(
        chat_turn,
        inputs=[msg_input, chatbot, state_agent, opts, skills, allow_memory, timeline_md],
        outputs=[chatbot, msg_input, state_agent, status_badge, timeline_md, trace_json],
    )
    new_btn.click(
        new_session,
        outputs=[chatbot, msg_input, state_agent, status_badge, timeline_md, trace_json],
    )
    session_dd.select(
        load_session,
        inputs=[session_dd, allow_memory],
        outputs=[chatbot, msg_input, state_agent, status_badge, timeline_md, trace_json],
    )
    refresh_btn.click(refresh_sessions, outputs=[session_dd])


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7861,
        theme=custom_theme,
        css=custom_css,
    )
