"""
app.py - LangGraph 图工作台（第十章 14 关可视化演示）
------------------------------------------------------------------
可视化对象：../examples/ 下 02~14 节的 14 个分节参考示例（真实 LangGraph 图，零 API Key）。
每一关把「发生了什么」透出来：
- 🗺 图结构：House 风格 SVG（assets/ 预渲染）+ 节点徽章行，跑完一个节点点亮一个
- 🔍 过程透视终端：stream_mode="updates" 逐节点打印状态增量，拒绝黑盒
- 📦 State 快照：运行结束后的完整状态 JSON
设计原则：教学透明 —— 课本示例原码在跑，工作台只是把它点亮。
启动：.venv/bin/python app.py   访问：http://127.0.0.1:7860
"""

import json
import html
import os
import re
import sys
import time
import uuid
from pathlib import Path

import gradio as gr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "examples"))

from langchain_core.messages import BaseMessage  # noqa: E402
from langgraph.types import Command  # noqa: E402

import importlib

ex02 = importlib.import_module("02_state_graph_demo")
ex03 = importlib.import_module("03_conditional_routing_demo")
ex04 = importlib.import_module("04_parallel_send_demo")
ex05 = importlib.import_module("05_streaming_debug_demo")
ex06 = importlib.import_module("06_memory_hitl_demo")
ex07 = importlib.import_module("07_multiagent_stack_demo")
ex08 = importlib.import_module("08_tool_loop_demo")
ex09 = importlib.import_module("09_workflow_patterns_demo")
ex10 = importlib.import_module("10_memory_timetravel_demo")
ex11 = importlib.import_module("11_durable_execution_demo")
ex12 = importlib.import_module("12_subgraphs_demo")
ex12b = importlib.import_module("12b_multiagent_paradigms_demo")
ex13 = importlib.import_module("13_hitl_interrupt_demo")
ex14 = importlib.import_module("14_functional_api_demo")

ASSETS = HERE / "assets"
ANIMATION_DELAY = max(0.0, float(os.getenv("WORKBENCH_ANIMATION_DELAY", "0.55")))

# ==============================================================================
# 通用工具：节点点亮徽章 / SVG 内高亮 / 过程透视格式化
# ==============================================================================

def now():
    import time
    return time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"


def load_svg(name: str) -> str:
    """读预渲染 SVG；保留主题变量，只移除固定尺寸，由容器统一控制画布。"""
    svg = (ASSETS / f"{name}.svg").read_text(encoding="utf-8")
    # 原 SVG 已有一个保存 House 主题 CSS 变量的 style 属性。不能再注入第二个
    # style，否则浏览器会丢掉 --bg/--fg 等变量，节点退化成黑块。
    svg = re.sub(r'\swidth="\d+(?:\.\d+)?"\sheight="\d+(?:\.\d+)?"', "", svg, count=1)
    return f'<div class="graph-frame"><div class="graph-canvas">{svg}</div></div>'


def machine_card_html(route_names: list[str], current_names: set[str],
                      trace: list[str] | None = None) -> str:
    """状态机透视卡片：节点卡片 + 箭头，每个节点下方挂「提交后的 State 摘要」徽标。

    trace 与 route_names 对齐：trace[i] 是第 i 个节点提交状态增量后公共交接本的
    一句话摘要。正在执行的节点尚无增量，徽标显示「读取 State」；这样箭头之间
    能看到 State 如何沿边生长（循环图可见 revision 爬升、Send 并行可见报价累积）。
    卡片里没有逐帧文案、也没有循环动画：节点执行中保持静止，只有当新节点
    进入路径或提交增量时才变化，因此不会跟着每一帧闪烁。
    done 保留重复节点，循环图会显示 writer → evaluator → writer 的卡片链。"""
    if not route_names:
        flow = '<span class="machine-empty">尚未进入 START —— 点击运行后，State 会沿着边一站站传递</span>'
    else:
        parts = []
        for i, name in enumerate(route_names):
            label = {"__start__": "START", "__end__": "END"}.get(name, name)
            cls = "mnode cur" if name in current_names else "mnode done"
            if name in ("__start__", "__end__"):
                cls += " boundary"
            brief = (trace[i] if trace and i < len(trace) and trace[i] else None)
            if name in current_names:
                state_cell = '<span class="mstate reading">读取 State…</span>'
            elif brief:
                state_cell = f'<span class="mstate" title="{html.escape(brief)}">{html.escape(brief)}</span>'
            else:
                state_cell = '<span class="mstate pending">待提交</span>'
            parts.append(f'<span class="mcell"><span class="{cls}">{html.escape(label)}</span>{state_cell}</span>')
            if i < len(route_names) - 1:
                arrow = "cur" if route_names[i + 1] in current_names else "done"
                parts.append(f'<span class="marrow {arrow}">→</span>')
        flow = "".join(parts)
    return (
        '<div class="machine-card">'
        '<div class="machine-head"><b>🔬 状态机透视</b>'
        '<span>State 不属于某个节点，它沿着边在节点间传递</span></div>'
        f'<div class="machine-flow">{flow}</div></div>'
    )


def chips_html(node_names: list[str], done: list[str], current: str | list[str] | None,
               skipped: bool = False, state: dict | None = None,
               trace: list[str] | None = None) -> str:
    """节点点亮徽章行：done=已完成（绿✓），current=正在跑（琥珀●），其余灰。
    skipped=True 表示本次运行触发了条件边未走的支路（灰显并标 ✂）"""
    current_names = {current} if isinstance(current, str) else set(current or [])
    parts = []
    completed = []
    for name in done:
        if name not in ("__start__", "__end__") and name not in completed:
            completed.append(name)
    for n in node_names:
        label = {"__start__": "START", "__end__": "END"}.get(n, n)
        if n in current_names:
            cls, mark = "chip cur", "●"
        elif n in done:
            cls, mark = "chip done", "✓"
        else:
            cls, mark = "chip", "·"
        parts.append(f'<span class="{cls}">{mark} {label}</span>')
    if current_names:
        current_label = " + ".join({"__start__": "START", "__end__": "END"}.get(n, n) for n in sorted(current_names))
        status_cls = "running"
        status_text = f'<b>正在执行</b><span class="current-node">{current_label}</span><span>第 {len(done) + 1} 步</span>'
    elif completed:
        status_cls = "settled"
        status_text = f'<b>状态已更新</b><span>完成 {len(completed)} 个节点</span>'
    else:
        status_cls = "idle"
        status_text = '<b>等待运行</b><span>点击操作按钮观察节点推进</span>'
    status = (f'<div class="run-status {status_cls}"><span class="status-dot"></span>'
              f'<span class="status-copy">{status_text}</span><span class="stream-badge">LIVE STREAM</span></div>')
    if state is None:
        state_line = "State 摘要：尚未运行。下方 JSON 是完整公共交接本。"
    else:
        state_line = f"State 摘要：{state_brief(state)}"
    state_box = f'<div class="state-peek"><b>📦 当前 State</b><span>{html.escape(state_line)}</span></div>'

    # 状态机透视：只由「路径 + 状态增量」驱动。done 保留重复节点，循环图会明确显示
    # writer → evaluator → writer 的卡片链，每个节点下挂提交后的 State 摘要徽标。
    route_names = list(done)
    route_names.extend(sorted(current_names))
    machine = machine_card_html(route_names, current_names, trace)
    return status + machine + state_box + '<div class="chip-row">' + "".join(parts) + "</div>"


def highlight_svg(svg_html: str, done: list[str], current: str | list[str] | None) -> str:
    """给 SVG 节点与到达该节点的边添加当前/完成状态。"""
    current_names = {current} if isinstance(current, str) else set(current or [])
    def _cls(m):
        nid = m.group(1)
        if nid in current_names:
            return f'{m.group(0)} data-lit="cur"'
        if nid in done:
            return f'{m.group(0)} data-lit="done"'
        return m.group(0)
    svg_html = re.sub(r'<g class="node" data-id="([^"]+)"', _cls, svg_html)

    def _edge_cls(m):
        target = m.group(2)
        if target in current_names:
            return f'{m.group(0)} data-lit="cur"'
        if target in done:
            return f'{m.group(0)} data-lit="done"'
        return m.group(0)

    return re.sub(
        r'<polyline class="edge" data-from="([^"]+)" data-to="([^"]+)"',
        _edge_cls,
        svg_html,
    )


def msg_brief(m) -> str:
    """把消息对象压成一行终端摘要"""
    if isinstance(m, BaseMessage):
        kind = m.__class__.__name__.replace("Message", "")
        content = str(getattr(m, "content", "")) or json.dumps(getattr(m, "tool_calls", []), ensure_ascii=False)
        return f"{kind}: {content[:110]}"
    return str(m)[:110]


def state_brief(state: dict) -> str:
    """把当前状态压成一句话，给初学者看一眼就懂。"""
    if not state:
        return "空状态"
    parts = []
    messages = state.get("messages")
    if isinstance(messages, list):
        parts.append(f"messages={len(messages)} 条")
        if messages:
            parts.append(f"最后消息={msg_brief(messages[-1])}")
    for key, value in state.items():
        if key == "messages":
            continue
        if isinstance(value, list):
            parts.append(f"{key}={len(value)} 项")
        elif isinstance(value, dict):
            parts.append(f"{key}=对象")
        else:
            parts.append(f"{key}={str(value)[:24]}")
        if len(parts) >= 3:
            break
    return "｜".join(parts) if parts else "空状态"


def fmt_update(update: dict) -> str:
    """单个节点状态增量 -> 终端可读文本"""
    lines = []
    for k, v in update.items():
        if k == "messages" and isinstance(v, list):
            for m in v:
                lines.append(f"      messages +「{msg_brief(m)}」")
        else:
            text = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v
            lines.append(f"      {k} = {text[:150]}")
    return "\n".join(lines) if lines else "      （无状态变更）"


# 跨回调会话状态（挂起图的续跑句柄；Gradio 回调间共享）
_t06 = {"graph": None, "config": None}
_rescue_state = {"graph": None, "config": None}
_t13 = {"graph": None, "config": None, "resume_history": []}
_t14 = {"flow": None, "config": None}

GRAPH_SVG = {
    "02": "02-diagram", "03": "03-diagram", "04": "04-diagram", "05": "05-diagram",
    "06": "06-diagram", "07": "07-diagram", "08": "08-diagram",
    "09": "09-routing-diagram", "10": "10-diagram", "11": "11-diagram",
    "12": "12-diagram", "13": "13-diagram", "14": "14-diagram",
}

# ==============================================================================
# 关卡运行逻辑：每个 runner 返回（或 yield）
# （点亮徽章 HTML, 图 SVG HTML, State 快照 JSON, 终端文本, 附加更新 dict）
# 附加更新的键与各关 outputs 对齐；无需附加更新时给 {}
# ==============================================================================

def node_order(graph) -> list[str]:
    """图对象 -> 展示顺序的节点名列表（START 在最前，END 收尾）"""
    names = [n.name for n in graph.get_graph().nodes.values()]
    order = [n for n in names if n not in ("__start__", "__end__")]
    return ["__start__"] + order + ["__end__"]


def run_stream_updates(graph, inputs, config=None, done_prefix=None):
    """通用逐节点流式：每个节点先展示「执行中」，再展示「已完成」。

    yield (done 列表, 当前节点, 终端行列表, 累积 State, 状态摘要轨迹 trace)。
    trace 与 done 对齐：trace[i] 是第 i 个节点提交增量后 State 的一句话摘要，
    供状态机透视卡片在每个节点下方显示「交接本沿边生长」的过程。
    无 Checkpointer 的图也能取全量状态：在客户端把各节点增量累积进 final；
    也把 __interrupt__ 事件转成一条终端行供展示。"""
    done = list(done_prefix or [])
    lines = [f"[{now()}] ▶ 进入 START 入口，图准备开始流转"]
    final: dict = {}
    trace: list[str] = []
    interrupted = False

    def _accumulate(update: dict):
        for k, v in (update or {}).items():
            if k == "messages":
                final.setdefault("messages", [])
                final["messages"] = final["messages"] + list(v)
            elif k == "dialog_state":
                if v == "pop":
                    final["dialog_state"] = (final.get("dialog_state") or [])[:-1]
                elif v is not None:
                    final["dialog_state"] = (final.get("dialog_state") or []) + [v]
            elif isinstance(v, list) and isinstance(final.get(k), list):
                final[k] = final[k] + list(v)
            else:
                final[k] = v

    yield list(done), "__start__", [*lines, f"[{now()}] 状态速览：{state_brief(final)}"], dict(final), list(trace)
    if "__start__" not in done:
        done.append("__start__")
        trace.append("初始 State 进入图")

    for event in graph.stream(inputs, config or {}, stream_mode="updates"):
        for node_name, update in event.items():
            if node_name == "__interrupt__":
                interrupted = True
                pkt = getattr(update[0], "value", None) if isinstance(update, tuple) and update else None
                lines.append(f"[{now()}] ⏸ interrupt() 挂起，待审批数据包：{json.dumps(pkt, ensure_ascii=False) if pkt else update}")
                continue
            if node_name in ("__start__", "__end__"):
                continue
            running_lines = list(lines) + [f"[{now()}] ● 正在执行节点 {node_name}…"]
            yield list(done), node_name, running_lines, dict(final), list(trace)
            if ANIMATION_DELAY:
                time.sleep(ANIMATION_DELAY)

            _accumulate(update)
            done.append(node_name)
            trace.append(state_brief(final))
            lines.append(f"[{now()}] ✓ 节点 {node_name} 完成，状态更新：\n{fmt_update(update or {})}")
            lines.append(f"[{now()}] 状态速览：{state_brief(final)}")
            yield list(done), None, list(lines), dict(final), list(trace)
            if ANIMATION_DELAY:
                time.sleep(ANIMATION_DELAY * 0.35)
    if interrupted:
        lines.append(f"[{now()}] ⏸ 图仍停在当前节点，尚未到达 END；等待 Command(resume=...) 后续跑")
        yield list(done), None, list(lines), dict(final), list(trace)
        return

    lines.append(f"[{now()}] ● 正在进入 END 出口，图准备收尾…")
    lines.append(f"[{now()}] 状态速览：{state_brief(final)}")
    yield list(done), "__end__", list(lines), dict(final), list(trace)
    if ANIMATION_DELAY:
        time.sleep(ANIMATION_DELAY)

    lines.append(f"[{now()}] ✓ 抵达 END 出口，图运行完成")
    final_done = list(done)
    if "__end__" not in final_done:
        final_done.append("__end__")
    yield final_done, None, list(lines), dict(final), list(trace)


# ==============================================================================
# UI
# ==============================================================================

custom_css = """
/* ===== 设计令牌：第十章「图工作台」—— 延续 09 章 indigo 实验台体系 ===== */
body { background:#f4f6f8; }
.gradio-container {
    --paper:#f4f6f8; --card:#ffffff; --line:#dfe4e8;
    --ink:#17202a; --chain:#0f766e; --spark:#c2413b; --amber:#d97706; --mint:#059669; --muted:#66717d;
    --mono:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", Roboto, sans-serif;
    max-width: min(1480px, 96vw) !important;
    margin: 0 auto !important;
    color: var(--ink);
    background: var(--paper);
    overflow-x: clip;
}
.gradio-container ::-webkit-scrollbar { width:8px; height:8px; }
.gradio-container ::-webkit-scrollbar-track { background:transparent; }
.gradio-container ::-webkit-scrollbar-thumb { background:#b9c2c9; border-radius:8px; }
.gradio-container textarea, .gradio-container input[type="text"],
.gradio-container input[type="number"] { border-radius: 12px !important; }
/* ===== 侧边栏 ===== */
#nav-sidebar { background: #eef2f3 !important; border-right: 1px solid #d7dee2 !important; }
#nav-logo { text-align: center; padding: 16px 8px 10px 8px; }
#nav-logo h2 {
    margin: 0 0 7px 0; font-size: 1.24em; font-weight: 800; letter-spacing: 1px;
    color: #17202a;
}
#nav-logo p { margin: 0; font-family: var(--mono); font-size: 0.68em; letter-spacing: 0.2em; color: var(--muted); }
#nav-radio .wrap { gap: 11px !important; padding: 4px 2px !important; }
#nav-radio label {
    background: rgba(255, 255, 255, .88); border: 1px solid #dce3e6 !important;
    border-radius: 8px !important; padding: 9px 12px !important;
    transition: all .16s ease; cursor: pointer;
    color: var(--ink) !important; font-size: 0.9em;
    box-shadow: 0 1px 3px rgba(27, 24, 80, .07);
}
#nav-radio label:hover { border-color: #8fc4bf !important; box-shadow: 0 4px 12px rgba(15, 118, 110, .12); transform: translateY(-1px); }
#nav-radio label.selected {
    background: #164e63 !important;
    border-color: transparent !important;
    box-shadow: 0 6px 16px rgba(22, 78, 99, .24);
    transform: translateY(-1px);
}
#nav-radio label.selected, #nav-radio label.selected * { color: #ffffff !important; }
#nav-radio label input { display: none; }
/* ===== Hero ===== */
.hero {
    position: relative; overflow: hidden;
    display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
    background: #17202a;
    border-radius: 8px; padding: 22px 26px; margin-bottom: 14px;
    color: #f8fafc;
    box-shadow: 0 12px 30px -18px rgba(23, 32, 42, .70), inset 0 1px 0 rgba(255, 255, 255, .08);
}
.hero::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: radial-gradient(rgba(255, 255, 255, .13) 1px, transparent 1.4px);
    background-size: 24px 24px; opacity: .45;
}
.hero > * { position: relative; z-index: 1; }
.hero .eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: var(--mono); font-size: 0.72em; letter-spacing: 0.24em; color: #fcd34d !important;
    background: rgba(252, 211, 77, .10); border: 1px solid rgba(252, 211, 77, .35);
    padding: 5px 12px; border-radius: 999px; margin-bottom: 12px;
}
.hero h1 { margin: 0; font-size: 1.85em; font-weight: 800; letter-spacing: 0; color: #ffffff; }
.hero h1 .light { color: #fcd34d; }
.hero p { margin: 10px 0 0; max-width: 880px; color: #d6daf7 !important; font-size: 0.92em; line-height: 1.75; }
.hero-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.hero-tags span {
    font-size: 0.76em; color: #e0e7ff !important; background: rgba(255, 255, 255, .10);
    border: 1px solid rgba(255, 255, 255, .20); padding: 4px 12px; border-radius: 999px;
}
.hero-side { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.hero-chain {
    font-family: var(--mono); font-size: 0.92em; color: #e0e7ff;
    background: #0d151d; border: 1px solid #34414c;
    padding: 12px 18px; border-radius: 6px; white-space: nowrap;
    max-width: 100%; overflow-x: auto;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .08);
}
.hero-chain b { color: #fcd34d; font-weight: 700; padding: 0 2px; }
.hero-chain-cap { font-family: var(--mono); font-size: 0.68em; letter-spacing: 0.18em; color: #a5b4fc; }

/* ===== 初学者读图说明 ===== */
.quick-guide {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px;
    margin: 0 0 14px 0;
}
.guide-card {
    background: #ffffff; border: 1px solid #dfe4e8; border-radius: 10px;
    padding: 13px 14px; box-shadow: 0 6px 18px rgba(23, 32, 42, .06);
}
.guide-card b { display: block; color: #164e63; margin-bottom: 5px; }
.guide-card span { color: #5c6875; font-size: .88em; line-height: 1.65; }
.guide-swatch { display:inline-flex; align-items:center; gap:6px; margin-right:8px; white-space:nowrap; }
.guide-dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
.guide-dot.idle { background:#cbd5e1; }
.guide-dot.cur { background:#f59e0b; box-shadow:0 0 0 4px rgba(245,158,11,.16); }
.guide-dot.done { background:#10b981; }
/* ===== 页头说明条 ===== */
.tab-head {
    display: flex; gap: 15px; align-items: flex-start;
    background: #ffffff;
    border: 1px solid var(--line); border-left: 4px solid #0f766e; border-radius: 8px;
    padding: 13px 16px; margin-bottom: 12px;
    box-shadow: 0 1px 2px rgba(27, 24, 80, .05), 0 14px 34px -22px rgba(27, 24, 80, .16);
}
.tab-badge {
    flex: 0 0 auto; font-family: var(--mono); font-weight: 800; font-size: 1.05em; letter-spacing: .03em;
    color: #ffffff; background: #164e63;
    border-radius: 6px; padding: 9px 13px;
    box-shadow: 0 5px 14px rgba(22, 78, 99, .22);
}
.tab-body { min-width: 0; }
.tab-body h3 { margin: 0 0 4px 0; font-size: 1.12em; font-weight: 700; color: var(--ink); }
.tab-body p { margin: 0 0 8px 0; font-size: 0.87em; color: var(--muted); line-height: 1.65; }
.pipe-line {
    display: inline-block; font-family: var(--mono); font-size: 0.78em; color: #0f5e59;
    background: #edf7f5; border: 1px solid #cce7e3; border-radius: 5px; padding: 4px 10px;
    box-shadow: inset 0 1px 0 #ffffff;
}
.pipe-line::before { content: "λ "; color: #c2413b; font-weight: 700; }
.pipe-line b { color: #b45309; font-weight: 700; }
@media (max-width: 760px) { .tab-head { flex-direction: column; } }
/* ===== 卡片 ===== */
.col-card {
    display: flex; flex-direction: column; row-gap: 12px !important;
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 14px 16px 16px 16px; margin-bottom: 10px;
    box-shadow: 0 2px 6px rgba(27, 24, 80, .07), 0 14px 34px -20px rgba(27, 24, 80, .16);
}
.gradio-container .gap-normal { gap: 14px !important; }
.col-card > :last-child { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.col-card > :last-child > * { flex: 1 1 auto; min-height: 0; }
.col-card > :last-child label { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.col-card > :last-child textarea { flex: 1 1 auto; min-height: 150px; resize: none !important; }
.col-card > :last-child .cm-editor,
.col-card > :last-child .CodeMirror { height: 100% !important; }
.col-card textarea, .col-card input[type="text"], .col-card input[type="number"] {
    background: #f8f9fe !important; border-color: #e4e7f5 !important;
}
.col-card textarea:focus, .col-card input[type="text"]:focus, .col-card input[type="number"]:focus {
    background: #ffffff !important; border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, .15) !important;
}
/* ===== 按钮 ===== */
.gradio-container button.primary {
    background: #0f766e !important;
    border: none !important; color: #ffffff !important; font-weight: 600 !important;
    letter-spacing: 0.02em;
    box-shadow: 0 3px 10px rgba(15, 118, 110, 0.24);
    transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
}
.gradio-container button.primary:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(15, 118, 110, 0.30); filter: saturate(1.08); }
.gradio-container button.primary:active { transform: translateY(0); box-shadow: 0 2px 8px rgba(15, 118, 110, 0.24); }
.gradio-container button.secondary {
    background: #ffffff !important;
    border: 1px solid #d5dde1 !important; color: #24424a !important; font-weight: 500;
    box-shadow: 0 1px 3px rgba(27, 24, 80, 0.07) !important;
    transition: all .15s ease;
}
.gradio-container button.secondary:hover {
    border-color: #8fc4bf !important; background: #edf7f5 !important;
    color: #0f5e59 !important; box-shadow: 0 2px 8px rgba(15, 118, 110, 0.10) !important;
}
.gradio-container button.lg { padding: 6px 14px !important; font-size: 0.88em !important; border-radius: 9px !important; min-height: 0 !important; }
.gradio-container button.sm { border-radius: 8px !important; padding: 5px 12px !important; font-size: 0.86em !important; min-height: 0 !important; }
.gradio-container .gr-button-block { width: 100% !important; margin: 0 !important; }
/* ===== 按钮行 ===== */
.btn-row { gap: 8px !important; align-items: center !important; margin: 2px 0 10px 0 !important; }
.btn-row button { width: auto !important; min-width: 0 !important; flex: 0 0 auto !important; padding: 6px 14px !important; font-size: 0.86em !important; min-height: 0 !important; }
.btn-row.tail { justify-content: flex-end; margin: 8px 0 2px 0 !important; }
.btn-row.tail button { padding: 8px 18px !important; font-size: 0.92em !important; }
.btn-row.split { gap: 12px !important; margin: 2px 0 12px 0 !important; }
.btn-row.split button { flex: 1 1 0 !important; padding: 10px 14px !important; font-size: 0.95em !important; }
/* ===== 输入单元：外壳即输入框 ===== */
.input-unit {
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 2px 6px 6px 6px; margin-bottom: 10px;
    box-shadow: 0 2px 6px rgba(27, 24, 80, .07), 0 14px 34px -20px rgba(27, 24, 80, .16);
}
.input-unit:focus-within { border-color: #0f766e; box-shadow: 0 0 0 3px rgba(15, 118, 110, .10); }
.input-unit label.container { border: none !important; background: transparent !important; box-shadow: none !important; }
.input-unit textarea, .input-unit input[type="text"], .input-unit input[type="number"] {
    border: none !important; background: transparent !important; box-shadow: none !important;
}
.input-unit .btn-row { margin-bottom: 0 !important; }
.input-unit .btn-row.tail { margin: 0 8px 2px 0 !important; }
.dashed-zone {
    border: 1.5px dashed #c9cff2 !important; border-radius: 14px !important;
    background: rgba(248, 249, 254, .6) !important;
    padding: 10px 12px !important;
}
.input-unit.fill { display: flex; flex-direction: column; }
.input-unit.fill > :first-child { flex: 1 1 auto !important; min-height: 0 !important; }
.input-unit.fill .btn-row.tail { flex: 0 0 auto !important; margin-top: auto !important; }
.input-unit > div > div { background: transparent !important; }
/* ===== 分组与布局辅助 ===== */
.gr-group { background: transparent !important; border: none !important; box-shadow: none !important; }
/* ===== 图结构区：House SVG 白卡 + 节点点亮 ===== */
.graph-box {
    background: #ffffff; border: 1px solid var(--line); border-radius: 8px;
    box-shadow: 0 2px 8px rgba(23, 32, 42, .06); overflow: hidden;
}
.graph-frame {
    background: #f8faf9; padding: 12px; text-align: center; overflow: hidden;
    min-height: 360px;
}
.graph-canvas {
    height: clamp(360px, 40vw, 510px); display: flex; align-items: center; justify-content: center;
    border: 1px solid #e5eaec; border-radius: 6px; background: #ffffff;
    overflow: auto;
}
.graph-frame svg {
    width: 100%; height: 100%; max-width: 920px;
    --bg:#ffffff !important; --fg:#24323b !important; --line:#94a3aa !important;
    --accent:#0f766e !important; --muted:#687780 !important; --surface:#f7faf9 !important;
    --border:#b8c5ca !important;
}
/* SVG 内部点亮（House 渲染器输出的 node g 带 data-id） */
.graph-frame g.node[data-lit="cur"] rect,
.graph-frame g.node[data-lit="cur"] polygon {
    fill: #fef3c7 !important; stroke: #f59e0b !important; stroke-width: 2.4 !important;
    filter: drop-shadow(0 0 7px rgba(245, 158, 11, .55));
    transform-box: fill-box; transform-origin: center;
    animation: node-breathe .9s ease-in-out infinite alternate;
}
.graph-frame g.node[data-lit="done"] rect,
.graph-frame g.node[data-lit="done"] polygon {
    fill: #d1fae5 !important; stroke: #10b981 !important; stroke-width: 1.6 !important;
    animation: node-settle .38s ease-out both;
}
.graph-frame g.node[data-lit="cur"] text,
.graph-frame g.node[data-lit="cur"] tspan { fill: #92400e !important; font-weight: 700 !important; }
.graph-frame g.node[data-lit="done"] text,
.graph-frame g.node[data-lit="done"] tspan { fill: #065f46 !important; }
.graph-frame polyline.edge { transition: stroke .25s ease, stroke-width .25s ease, opacity .25s ease; }
.graph-frame polyline.edge[data-lit="cur"] {
    stroke: #f59e0b !important; stroke-width: 2.4 !important;
    stroke-dasharray: 8 5; animation: edge-flow .65s linear infinite;
}
.graph-frame polyline.edge[data-lit="done"] {
    stroke: #10b981 !important; stroke-width: 1.8 !important; opacity: .95;
}
@keyframes node-breathe {
    from { transform: scale(.98); filter: drop-shadow(0 0 3px rgba(245, 158, 11, .38)); }
    to { transform: scale(1.035); filter: drop-shadow(0 0 10px rgba(245, 158, 11, .68)); }
}
@keyframes node-settle {
    from { opacity: .72; transform: scale(1.025); }
    to { opacity: 1; transform: scale(1); }
}
@keyframes edge-flow { to { stroke-dashoffset: -13; } }
/* 图下方的实时执行状态：与 SVG、节点徽章和终端保持同一语义。 */
.run-status {
    min-height: 38px; display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
    margin: 10px 0 5px; padding: 8px 11px; border: 1px solid #dce3e6;
    border-radius: 7px; background: #ffffff; color: #52606a; font-size: .82em;
}
.run-status .status-dot { width: 9px; height: 9px; border-radius: 50%; background: #a4adb3; flex: 0 0 auto; }
.run-status .status-copy { display: flex; align-items: center; gap: 8px; flex: 1 1 auto; min-width: 0; }
.run-status b { color: #24323b; }
.run-status .current-node {
    max-width: min(360px, 50vw); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-family: var(--mono); font-weight: 700; color: #92400e;
}
.run-status.running { border-color: #f1c36d; background: #fffbeb; color: #8a5a10; }
.run-status.running .status-dot {
    background: #f59e0b; box-shadow: 0 0 0 4px rgba(245, 158, 11, .18);
    animation: status-pulse .8s ease-in-out infinite alternate;
}
.run-status.settled { border-color: #b7dfd5; background: #f0faf7; color: #0f645b; }
.run-status.settled .status-dot { background: #10b981; }
.stream-badge {
    flex: 0 0 auto; font-family: var(--mono); font-size: .7em; letter-spacing: .08em;
    padding: 3px 7px; border: 1px solid currentColor; border-radius: 4px; opacity: .72;
}
@keyframes status-pulse { to { transform: scale(1.25); box-shadow: 0 0 0 6px rgba(245, 158, 11, .10); } }
.state-peek {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    margin: 0 0 6px; padding: 8px 11px; border: 1px dashed #cbd8dc;
    border-radius: 7px; background: #fbfdfc; color: #53616a; font-size: .82em;
}
.state-peek b { color: #0f5e59; }
.state-peek span { font-family: var(--mono); overflow-wrap: anywhere; }
/* 状态机透视卡片：只有「节点卡片 + 箭头」，无逐帧文案、无循环动画 —— 不会闪 */
.machine-card {
    margin: 7px 0; padding: 11px 12px; border: 1px solid #d9e4e3; border-radius: 8px;
    background: linear-gradient(135deg, #f8fffd, #f8fafc);
}
.machine-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
.machine-head b { color: #0f5e59; }
.machine-head span { color: #6b7780; font-size: .78em; }
.machine-flow {
    display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
    background: #ffffff; border: 1px solid #e2e9e9; border-radius: 6px; padding: 9px 10px;
}
.machine-flow .machine-empty { color: #8a96a0; font-size: .8em; }
/* 节点卡片 + 下方 State 徽标组成一个竖排单元，体现「节点提交增量 -> 交接本生长」 */
.machine-flow .mcell {
    display: inline-flex; flex-direction: column; align-items: center; gap: 3px;
    min-width: 0;
}
.machine-flow .mnode {
    font-family: var(--mono); font-size: .78em; padding: 4px 12px; border-radius: 6px;
    border: 1px solid #cfd8dc; background: #f6f8f9; color: #74818a;
    transition: background .25s ease, border-color .25s ease, color .25s ease;
}
.machine-flow .mnode.done { background: #d7f4ed; border-color: #9ddacb; color: #075e54; font-weight: 700; }
.machine-flow .mnode.cur {
    background: #fef3c7; border-color: #f59e0b; color: #92400e; font-weight: 800;
    box-shadow: 0 0 0 3px rgba(245, 158, 11, .16);
}
.machine-flow .mnode.boundary { border-radius: 999px; font-weight: 700; letter-spacing: .04em; }
.machine-flow .mnode.boundary.done { background: #eef2f3; border-color: #b8c5ca; color: #46545e; }
.machine-flow .mstate {
    max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-family: var(--mono); font-size: .64em; line-height: 1.5;
    padding: 1px 8px; border-radius: 999px;
    background: #f0faf7; border: 1px solid #b7dfd5; color: #0f645b;
    cursor: default;
}
.machine-flow .mstate.reading { background: #fffbeb; border-color: #f2bd58; color: #92400e; }
.machine-flow .mstate.pending { background: #f6f8f9; border-color: #dfe4e8; color: #9aa5ad; }
.machine-flow .marrow {
    font-family: var(--mono); font-size: .9em; color: #b0bac2; flex: 0 0 auto;
    align-self: flex-start; margin-top: 10px;
    transition: color .25s ease;
}
.machine-flow .marrow.done { color: #10b981; }
.machine-flow .marrow.cur { color: #f59e0b; font-weight: 800; }
/* 节点徽章行 */
.chip-row { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; padding: 5px 2px 3px; }
.chip {
    font-family: var(--mono); font-size: 0.78em; padding: 4px 12px; border-radius: 999px;
    background: #f1f4f5; border: 1px solid #dce3e6; color: #74818a;
    transition: all .18s ease;
}
.chip.done { background: #d7f4ed; border-color: #9ddacb; color: #075e54; font-weight: 700; animation: chip-in .28s ease-out both; }
.chip.cur {
    background: #fef3c7; border-color: #fcd34d; color: #92400e; font-weight: 800;
    box-shadow: 0 0 0 3px rgba(245, 158, 11, .18); animation: chip-pulse .8s ease-in-out infinite alternate;
}
@keyframes chip-in { from { transform: translateY(3px); opacity: .65; } to { transform: translateY(0); opacity: 1; } }
@keyframes chip-pulse { to { box-shadow: 0 0 0 6px rgba(245, 158, 11, .08); } }
/* ===== 过程透视终端 ===== */
.console .label-wrap span::before { content: "▍ "; color: #34d399; }
.console ::-webkit-scrollbar-thumb { background: #2c3a5c; }
.gradio-container.gradio-container-6-26-0 .contain .gradio-container.gradio-container-6-26-0 .contain .console textarea,
.gradio-container.gradio-container-6-26-0 .contain .console textarea,
.gradio-container .console textarea {
    background-image: linear-gradient(180deg, #0d1428, #0a0f1f) !important;
    background-color: #0a0f1f !important;
    color: #eaf6ee !important;
    font-family: var(--mono) !important; font-size: 0.88em !important;
    line-height: 1.75 !important;
    border: 1px solid #27324f !important; border-radius: 14px !important;
    box-shadow: inset 0 0 36px rgba(59, 130, 246, .08), inset 0 1px 0 rgba(255, 255, 255, .05);
    caret-color: #4ade80;
}
/* ===== 挂起审批条（琥珀警示） ===== */
.pending-bar {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    background: linear-gradient(90deg, #fffbeb, #fef3c7);
    border: 1.5px solid #f2bd58; border-left: 5px solid #d97706; border-radius: 8px;
    padding: 12px 16px; margin-bottom: 10px;
    font-size: 0.92em; color: #92400e;
}
.pending-bar .pulse {
    width: 10px; height: 10px; border-radius: 50%; background: #f59e0b;
    box-shadow: 0 0 0 4px rgba(245, 158, 11, .25); flex: 0 0 auto;
}
.document-preview {
    min-height: 360px; padding: 8px 20px !important; background:#fffdf8 !important;
    border:1px solid #eadfca !important; border-radius:8px !important;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.7);
}
.document-preview h1 { color:#263842; font-size:1.45em; border-bottom:2px solid #d7e7e3; padding-bottom:9px; }
.document-preview h2 { color:#0f766e; font-size:1.05em; margin-top:18px; }
.document-preview p { color:#43515a; line-height:1.85; }
/* ===== 10.14 人工审阅弹窗卡片 ===== */
.review-modal-mask {
    position: fixed; inset: 0; z-index: 9999;
    display: flex; align-items: center; justify-content: center;
    background: rgba(15, 32, 39, .55); backdrop-filter: blur(3px);
    padding: 20px;
}
.review-modal {
    width: min(680px, 94vw); max-height: 88vh; overflow-y: auto;
    background: #ffffff; border: 1px solid #d9e4e3; border-radius: 14px;
    padding: 18px 20px 16px 20px;
    box-shadow: 0 24px 70px -18px rgba(15, 40, 46, .55);
    animation: modal-pop .28s ease-out both;
}
.review-head { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.review-head b { color: #92400e; font-size: 1.06em; }
.review-tag {
    font-family: var(--mono); font-size: .68em; letter-spacing: .06em; color: #92400e;
    background: #fffbeb; border: 1px solid #f2bd58; border-radius: 999px; padding: 3px 10px;
}
.review-pulse {
    width: 10px; height: 10px; border-radius: 50%; background: #f59e0b;
    box-shadow: 0 0 0 4px rgba(245, 158, 11, .25); flex: 0 0 auto;
    animation: status-pulse .8s ease-in-out infinite alternate;
}
.review-sub { margin: 8px 0 2px; font-size: .84em; color: #6b7780; line-height: 1.7; }
.review-modal .document-preview { min-height: 160px; max-height: 40vh; overflow-y: auto; }
@keyframes modal-pop {
    from { opacity: 0; transform: translateY(14px) scale(.97); }
    to { opacity: 1; transform: translateY(0) scale(1); }
}
/* ===== 栈条（07 dialog_state 可视化） ===== */
.stack-visual { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 6px 2px; }
.stack-cell {
    font-family: var(--mono); font-size: 0.8em; padding: 6px 14px;
    background: linear-gradient(135deg, #eef2ff, #f5f0ff); border: 1.5px solid #c7d2fe;
    border-radius: 10px; color: #3730a3; font-weight: 700;
}
.stack-cell.empty { background: #f1f2fa; border-color: #dfe2f2; color: #8a8db2; font-weight: 400; }
.stack-cap { font-family: var(--mono); font-size: 0.72em; color: var(--muted); letter-spacing: .1em; }
/* ===== 页脚 ===== */
.footer {
    text-align: center; color: var(--muted); font-size: 0.85em;
    margin-top: 28px; padding: 18px 0 26px 0; border-top: 1px solid var(--line);
}
.footer b { color: var(--ink); }
.footer a { color: var(--chain); text-decoration: none; font-weight: 600; }
.footer a:hover { text-decoration: underline; }
.footer-note { margin-top: 6px; font-family: var(--mono); font-size: 0.92em; opacity: .75; }
@media (max-width: 760px) {
    .gradio-container { max-width: 100vw !important; padding-left: 10px !important; padding-right: 10px !important; }
    .hero { padding: 18px; gap: 14px; }
    .hero h1 { font-size: 1.55em; }
    .hero p { font-size: .86em; line-height: 1.6; }
    .hero-side { width: 100%; align-items: flex-start; }
    .hero-chain { width: 100%; font-size: .76em; padding: 10px 12px; }
    .quick-guide { grid-template-columns: 1fr; }
    .machine-head { align-items:flex-start; flex-direction:column; gap:3px; }
    .machine-flow { gap: 5px; }
    .tab-head { gap: 10px; padding: 12px; }
    .tab-badge { font-size: .92em; padding: 7px 10px; }
    .graph-frame { padding: 8px; min-height: 320px; }
    .graph-canvas { height: 340px; }
    .chip-row { justify-content: flex-start; flex-wrap: nowrap; overflow-x: auto; padding-bottom: 7px; }
    .chip { flex: 0 0 auto; }
    .run-status { align-items: flex-start; }
    .run-status .status-copy { flex-wrap: wrap; gap: 4px 8px; }
    .stream-badge { margin-left: auto; }
    .btn-row.split { flex-direction: column; }
}
"""

THEME = gr.themes.Soft(
    primary_hue="indigo", secondary_hue="violet", neutral_hue="slate",
    radius_size=gr.themes.sizes.radius_lg)

PAGES = [
    "🧱 10.2 State 图的构建",
    "🚦 10.3 条件路由",
    "_DISPATCH 10.4 Send 并行",
    "📡 10.5 可视化与流式调试",
    "🧠 10.6 记忆与 HITL",
    "🏨 10.7 MultiAgent 分层",
    "🛠 10.8 工具调用循环",
    "🧩 10.9 工作流设计模式",
    "🗄 10.10 长期记忆与 Time Travel",
    "🛡 10.11 持久执行与容错",
    "🪆 10.12 子图嵌套",
    "🎭 10.12b 多智能体模式",
    "✋ 10.13 HITL 进阶 interrupt",
    "🧪 10.14 Functional API",
]
PAGES[2] = "🕸 10.4 Send 并行分发"

with gr.Blocks(title="LangGraph 图工作台") as demo:

    # ================= 左侧边栏 =================
    # 默认收起侧栏，让窄屏先看到当前关卡；左上角 Toggle Sidebar 仍可随时打开导航。
    with gr.Sidebar(open=False, elem_id="nav-sidebar", width="280px"):
        gr.HTML("""<div id="nav-logo"><h2>🌊 Vibe Coding</h2><p>LANGGRAPH WORKBENCH · CH10</p></div>""")
        page_selector = gr.Radio(choices=PAGES, value=PAGES[0], label="章节导航",
                                 elem_id="nav-radio", show_label=False, container=True)

    # ================= 顶部横幅 =================
    gr.HTML("""
    <div class="hero">
      <div class="hero-main">
        <div class="eyebrow">VIBE CODING · CHAPTER 10 WORKBENCH</div>
        <h1>LangGraph <span class="light">图工作台</span></h1>
        <p>十四道图机制关卡。左边是图（House 风格 SVG），跑完一个节点点亮一个；下面是「过程透视」终端，逐节点打印状态增量——课本示例的真实 LangGraph 图在跑，工作台只是把它点亮。拒绝黑盒，看得见才学得会。</p>
        <div class="hero-tags">
          <span>🧱 State</span><span>🚦 条件路由</span><span>🕸 Send 并行</span>
          <span>🧠 Checkpointer</span><span>🪆 子图</span><span>✋ interrupt</span>
        </div>
      </div>
      <div class="hero-side">
        <div class="hero-chain">state <b>|</b> node <b>|</b> edge <b>|</b> interrupt <b>|</b> resume</div>
        <div class="hero-chain-cap">THE GRAPH PIPELINE</div>
      </div>
    </div>
    """)
    gr.HTML("""
    <div class="quick-guide">
      <div class="guide-card"><b>① START / END 怎么看</b><span>它们是 LangGraph 自动加的图边界：START 表示流程入场，END 表示流程出场。工作台会把它们也点亮，避免你误以为图凭空开始或突然结束。</span></div>
      <div class="guide-card"><b>② 节点颜色怎么读</b><span><span class="guide-swatch"><i class="guide-dot idle"></i>未到达</span><span class="guide-swatch"><i class="guide-dot cur"></i>正在执行</span><span class="guide-swatch"><i class="guide-dot done"></i>已完成</span>普通节点亮起时，才代表对应 Python 函数正在跑。</span></div>
      <div class="guide-card"><b>③ State 在哪里</b><span>图下方先给一句 State 摘要，右侧 JSON 展示完整公共交接本，终端逐行显示每个节点写入了哪些字段。</span></div>
    </div>
    """)

    def head(num, emoji, title, formula, desc):
        return f"""<div class="tab-head"><div class="tab-badge">{num}</div>
        <div class="tab-body"><h3>{emoji} {title}</h3>
        <p>{desc}</p><div class="pipe-line">{formula}</div></div></div>"""

    # ---------------- 每关通用组件工厂 ----------------

    def graph_section(svg_name):
        """图结构区：左 SVG 右徽章说明"""
        return gr.HTML(load_svg(svg_name), elem_classes=["graph-box"])

    def console_section():
        return gr.Textbox(label="🔍 过程透视", lines=10, interactive=False,
                          elem_classes=["console"],
                          placeholder="点击按钮后，这里逐节点打印状态增量…")

    # ================= 页面 10.2：State 图 =================
    with gr.Group(visible=True) as pg02:
        gr.HTML(head("10.2", "🧱", "State 图的构建与运行",
                     "StateGraph <b>|</b> add_node <b>|</b> add_edge <b>|</b> stream",
                     "图 = 路线图，节点 = 打工人，State = 公共交接本。点击运行，看 greeter 与 echo 两个节点如何接力传递 messages。"))
        t02_graph = gr.HTML(load_svg("02-diagram"), elem_classes=["graph-box"])
        t02_chips = gr.HTML(chips_html(node_order(ex02.build_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            t02_in = gr.Textbox(label="你的开场白", value="你好，今天天气怎么样？")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t02_btn = gr.Button("🚀 运行图", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t02_snap = gr.Code(label="📦 最终 State（公共交接本）", language="json")
            with gr.Column(scale=1):
                t02_console = console_section()

        def t02_run(user_text):
            graph = ex02.build_graph()
            order = node_order(graph)
            state = {}
            done = []
            lines = [f"[{now()}] 收到输入，图开始流转（START → greeter → echo → END）"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"messages": [("user", user_text)]}):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("02-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("02-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

        t02_btn.click(t02_run, inputs=[t02_in],
                      outputs=[t02_chips, t02_graph, t02_snap, t02_console])

    # ================= 页面 10.3：条件路由 =================
    with gr.Group(visible=False) as pg03:
        gr.HTML(head("10.3", "🚦", "条件路由与动态决策",
                     "add_conditional_edges <b>|</b> route() <b>|</b> Literal",
                     "分诊台（classify）判定意图后，路由函数像十字路口的指路牌，把请求送往三个科室之一。换不同输入，看点亮的支路如何变化。"))
        t03_graph = gr.HTML(load_svg("03-diagram"), elem_classes=["graph-box"])
        t03_chips = gr.HTML(chips_html(node_order(ex03.build_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            t03_in = gr.Textbox(label="用户请求（含「翻译」/「总结」走专属科室，其余走闲聊）",
                                value="帮我把这段话翻译成英文")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t03_btn = gr.Button("🚦 分诊运行", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t03_snap = gr.Code(label="📦 最终 State", language="json")
            with gr.Column(scale=1):
                t03_console = console_section()

        def t03_run(user_text):
            graph = ex03.build_graph()
            order = node_order(graph)
            state, done, lines = {}, [], [f"[{now()}] 收到请求，进入分诊台…"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"input": user_text, "category": ""}):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("03-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("03-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

        t03_btn.click(t03_run, inputs=[t03_in],
                      outputs=[t03_chips, t03_graph, t03_snap, t03_console])

    # ================= 页面 10.4：Send 并行 =================
    with gr.Group(visible=False) as pg04:
        gr.HTML(head("10.4", "🕸", "Send 动态并行分发",
                     "Send() <b>|</b> operator.add reducer <b>|</b> 隐式屏障",
                     "规划节点解析出 N 个城市，Send 就派 N 个并行实例同时查价（虚线 Send 边）；加法 reducer 把报价合并，aggregate 等所有实例到齐才汇总。"))
        t04_graph = gr.HTML(load_svg("04-diagram"), elem_classes=["graph-box"])
        t04_chips = gr.HTML(chips_html(node_order(ex04.build_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            t04_in = gr.Textbox(label="城市清单（图会解析出哪些城市就并行派几路）",
                                value="帮我同时查一下北京、上海和成都的机票")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t04_btn = gr.Button("🕸 Send 并行查价", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t04_snap = gr.Code(label="📦 最终 State（quotes 由 reducer 合并）", language="json")
            with gr.Column(scale=1):
                t04_console = console_section()

        def t04_run(user_text):
            graph = ex04.build_graph()
            order = node_order(graph)
            state, done, lines = {}, [], [f"[{now()}] 收到请求，plan 节点解析城市…"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"user_input": user_text}):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("04-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("04-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

        t04_btn.click(t04_run, inputs=[t04_in],
                      outputs=[t04_chips, t04_graph, t04_snap, t04_console])

    # ================= 页面 10.5：可视化与流式调试 =================
    with gr.Group(visible=False) as pg05:
        gr.HTML(head("10.5", "📡", "图的可视化与流式调试",
                     "draw_mermaid() <b>|</b> stream_mode=updates/values",
                     "两种 stream 模式对照：updates 只给「这个节点改了什么」的增量；values 每步都给完整快照。左侧图即课本 05 节 draw_mermaid() 的产物。"))
        t05_graph = gr.HTML(load_svg("05-diagram"), elem_classes=["graph-box"])
        t05_chips = gr.HTML(chips_html(node_order(ex05.build_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            t05_in = gr.Textbox(label="搜索关键词", value="LangGraph 是什么")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t05_btn_u = gr.Button("⚡ updates 模式（增量）", variant="primary", size="sm")
                t05_btn_v = gr.Button("📊 values 模式（全量）", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t05_snap = gr.Code(label="📦 最终 State", language="json")
            with gr.Column(scale=1):
                t05_console = console_section()

        def t05_run_updates(user_text):
            graph = ex05.build_graph()
            order = node_order(graph)
            state, done, lines = {}, [], [f"[{now()}] stream_mode='updates'：每个节点只吐自己的增量"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"query": user_text, "answer": ""}):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("05-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("05-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

        def t05_run_values(user_text):
            graph = ex05.build_graph()
            order = node_order(graph)
            lines = [f"[{now()}] stream_mode='values'：每步都吐完整快照（观察 answer 字段的累积）"]
            done, state = [], {}
            for snap in graph.stream({"query": user_text, "answer": ""}, stream_mode="values"):
                state = snap
                done = [n for n in order if n != "__start__" and n != "__end__"] if "answer" in snap and snap["answer"] else []
                cur = "reply" if "最终回答" in str(snap.get("answer", "")) else ("search" if snap.get("answer") else None)
                yield (chips_html(order, done, cur, state=snap), highlight_svg(load_svg("05-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines))
            yield (chips_html(order, order[1:-1], None, state=state), highlight_svg(load_svg("05-diagram"), order[1:-1], None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines))

        t05_btn_u.click(t05_run_updates, inputs=[t05_in],
                        outputs=[t05_chips, t05_graph, t05_snap, t05_console])
        t05_btn_v.click(t05_run_values, inputs=[t05_in],
                        outputs=[t05_chips, t05_graph, t05_snap, t05_console])

    # ================= 页面 10.6：记忆与 HITL（两阶段） =================
    with gr.Group(visible=False) as pg06:
        gr.HTML(head("10.6", "🧠", "Checkpointer、静态断点与正式驳回",
                     "MemorySaver <b>|</b> interrupt_before <b>|</b> update_state(as_node=...)",
                     "图在敏感节点前暂停。批准会在同一 thread_id 上传 None 续跑；驳回会补齐匹配 tool_call_id 的 ToolMessage，并用 update_state 把它记成敏感节点的输出，真正工具不会执行。"))
        t06_graph = gr.HTML(load_svg("06-diagram"), elem_classes=["graph-box"])
        t06_chips = gr.HTML(chips_html(node_order(ex06.build_guarded()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            t06_in = gr.Textbox(label="用户指令", value="帮我清空购物车")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t06_btn = gr.Button("🧠 发起请求", variant="primary", size="sm")
        t06_pending = gr.HTML(visible=False)
        with gr.Row(equal_height=False):
            t06_ok = gr.Button("✅ 批准（从存档续跑）", variant="primary", size="sm", visible=False)
            t06_no = gr.Button("❌ 驳回（写回执并跳过工具）", size="sm", visible=False)
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t06_snap = gr.Code(label="📦 存档中的 State", language="json")
            with gr.Column(scale=1):
                t06_console = console_section()

        def t06_run(user_text):
            graph = ex06.build_guarded()          # 全新 Checkpointer，互不串台
            order = node_order(graph)
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            _t06["graph"], _t06["config"] = graph, config
            state, done, lines = {}, [], [f"[{now()}] 图挂上 MemorySaver 存档，开始流转…"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"messages": [("user", user_text)]}, config):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("06-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])),
                       gr.update(visible=True), gr.update(visible=True), gr.update(visible=True))
            nxt = graph.get_state(config).next
            lines.append(f"[{now()}] 运行结束。next={nxt or '（无，已到 END）'}")
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("06-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines),
                   gr.update(visible=bool(nxt),
                             value=f'<div class="pending-bar"><span class="pulse"></span><b>敏感操作已拦截：</b>待执行节点 {nxt[0] if nxt else "—"} 等待审批 —— Checkpointer 已存档，批准即续跑</div>'),
                   gr.update(visible=bool(nxt)), gr.update(visible=bool(nxt)))

        def t06_resume():
            """批准：在刚才暂停的同一张图、同一 thread_id 上继续。"""
            graph, config = _t06["graph"], _t06["config"]
            order = node_order(graph)
            done = ["propose"]
            lines = [f"[{now()}] ✅ 已批准：对同一个 thread_id 执行 stream(None)，从暂停快照续跑…"]
            for done, cur, _lines, _values, trace in run_stream_updates(graph, None, config, done_prefix=done):
                for line in _lines:
                    if line not in lines:
                        lines.append(line)
            state = graph.get_state(config).values
            lines.append(f"[{now()}] sensitive_tool 已执行，summarize 收尾，图到 END。")
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("06-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines),
                   gr.update(visible=False), gr.update(visible=False), gr.update(visible=False))

        def t06_reject():
            graph, config = _t06["graph"], _t06["config"]
            result = ex06.reject_pending(graph, config, "工作台审批人拒绝了清空操作")
            order = node_order(graph)
            done = ["propose", "summarize"]
            lines = [
                f"[{now()}] ❌ 已驳回：为每个 tool_call_id 补齐 ToolMessage 拒绝回执",
                f"[{now()}] update_state(..., as_node='sensitive_tool') 创建新检查点，跳过真正的敏感工具",
                f"[{now()}] summarize 读取拒绝原因并收尾；购物车没有被清空",
            ]
            return (chips_html(order, done, None, state=result), highlight_svg(load_svg("06-diagram"), done, None),
                    json.dumps(result, ensure_ascii=False, indent=2, default=str), "\n".join(lines),
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=False))

        t06_btn.click(t06_run, inputs=[t06_in],
                      outputs=[t06_chips, t06_graph, t06_snap, t06_console, t06_pending, t06_ok, t06_no])
        t06_ok.click(t06_resume,
                     outputs=[t06_chips, t06_graph, t06_snap, t06_console, t06_pending, t06_ok, t06_no])
        t06_no.click(t06_reject,
                     outputs=[t06_chips, t06_graph, t06_snap, t06_console, t06_pending, t06_ok, t06_no])

    # ================= 页面 10.7：MultiAgent 状态栈 =================
    with gr.Group(visible=False) as pg07:
        gr.HTML(head("10.7", "🏨", "MultiAgent 分层架构与状态栈",
                     "dialog_state <b>|</b> 自定义 reducer <b>|</b> 压栈 / 弹栈",
                     "大堂经理识别「机票」意图后压栈转交航班助理；航班助理干完活弹栈交还。下方栈条实时显示 dialog_state 的压栈/弹栈过程。"))
        t07_graph = gr.HTML(load_svg("07-diagram"), elem_classes=["graph-box"])
        t07_chips = gr.HTML(chips_html(node_order(ex07.build_graph()), [], None))
        t07_stack = gr.HTML('<div class="stack-visual"><span class="stack-cap">dialog_state →</span>'
                            '<span class="stack-cell empty">（空栈：主助理值班）</span></div>')
        with gr.Column(elem_classes=["input-unit"]):
            t07_in = gr.Textbox(label="对大堂经理说点什么（含「机票」触发转交）",
                                value="帮我订一张去东京的机票")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t07_btn = gr.Button("🏨 找大堂经理", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t07_snap = gr.Code(label="📦 最终 State（dialog_state 应弹回空栈）", language="json")
            with gr.Column(scale=1):
                t07_console = console_section()

        def stack_bar(dialog_state):
            if not dialog_state:
                return ('<div class="stack-visual"><span class="stack-cap">dialog_state →</span>'
                        '<span class="stack-cell empty">（空栈：主助理值班）</span></div>')
            cells = "".join(f'<span class="stack-cell">{s}</span>' for s in dialog_state)
            return (f'<div class="stack-visual"><span class="stack-cap">dialog_state →</span>{cells}'
                    f'<span class="stack-cap">▲ 栈顶</span></div>')

        def t07_run(user_text):
            graph = ex07.build_graph()
            order = node_order(graph)
            state, done, lines = {}, [], [f"[{now()}] 用户开口，大堂经理接单…"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"messages": [("user", user_text)]}):
                state = values
                ds = state.get("dialog_state", [])
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("07-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str),
                       "\n".join(lines + list(_lines or [])) + "\n" + stack_bar(ds))
            ds = state.get("dialog_state", [])
            lines.append(f"[{now()}] 最终 dialog_state = {ds or '[]（已弹回空栈，控制权交还主助理）'}")
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("07-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str),
                   "\n".join(lines + list(_lines or [])) + "\n" + stack_bar(ds))

        t07_btn.click(t07_run, inputs=[t07_in],
                      outputs=[t07_chips, t07_graph, t07_snap, t07_console])

    # ================= 页面 10.8：工具调用循环 =================
    with gr.Group(visible=False) as pg08:
        gr.HTML(head("10.8", "🛠", "工具调用循环（ReAct 闭环）",
                     "ToolNode <b>|</b> tools_condition <b>|</b> assistant ⇄ tools",
                     "假模型按剧本先「点名」search_flights 工具，tools_condition 指路牌送进 ToolNode 执行，结果递回 assistant 形成闭环——注意 tools 节点被点亮两次前 assistant 会亮两轮。"))
        t08_graph = gr.HTML(load_svg("08-diagram"), elem_classes=["graph-box"])
        t08_chips = gr.HTML(chips_html(node_order(ex08.build_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            t08_in = gr.Textbox(label="用户问题（剧本固定查东京航班）", value="帮我查一下去东京的航班")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t08_btn = gr.Button("🛠 启动 ReAct 闭环", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t08_snap = gr.Code(label="📦 最终 messages（观察 Human → AI(tool_call) → Tool → AI 四连）", language="json")
            with gr.Column(scale=1):
                t08_console = console_section()

        def t08_run(user_text):
            graph = ex08.build_graph()            # 工厂内新剧本，防串台
            order = node_order(graph)
            state, done, lines = {}, [], [f"[{now()}] ReAct 闭环启动：模型 → 工具 → 模型"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"messages": [("user", user_text)]}):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("08-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("08-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

        t08_btn.click(t08_run, inputs=[t08_in],
                      outputs=[t08_chips, t08_graph, t08_snap, t08_console])

    # ================= 页面 10.9：工作流设计模式（三图 Tab） =================
    with gr.Group(visible=False) as pg09:
        gr.HTML(head("10.9", "🧩", "三大工作流设计模式",
                     "Routing <b>|</b> Orchestrator-Worker <b>|</b> Evaluator-Optimizer",
                     "三个可切换的经典模式：路由分诊 / 主管派工（Send）/ 评估改稿循环（带 3 版保险丝）。每个 Tab 有自己的图与运行按钮。"))
        with gr.Tabs():
            with gr.Tab("🚦 Routing 路由"):
                t09a_graph = gr.HTML(load_svg("09-routing-diagram"), elem_classes=["graph-box"])
                t09a_chips = gr.HTML(chips_html(node_order(ex09.build_routing_graph()), [], None))
                with gr.Column(elem_classes=["input-unit"]):
                    t09a_in = gr.Textbox(label="顾客问题（含「多少钱」走定价，否则走退款）",
                                         value="这个东西多少钱？")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t09a_btn = gr.Button("🚦 路由运行", variant="primary", size="sm")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1, elem_classes=["col-card"]):
                        t09a_snap = gr.Code(label="📦 最终 State", language="json")
                    with gr.Column(scale=1):
                        t09a_console = console_section()

                def t09a_run(user_text):
                    graph = ex09.build_routing_graph()
                    order = node_order(graph)
                    state, done, lines = {}, [], [f"[{now()}] Routing：一个入口，按问题主题分流"]
                    for done, cur, _lines, values, trace in run_stream_updates(graph, {"question": user_text, "answer": ""}):
                        state = values
                        yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("09-routing-diagram"), done, cur),
                               json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
                    yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("09-routing-diagram"), done, None),
                           json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

                t09a_btn.click(t09a_run, inputs=[t09a_in],
                               outputs=[t09a_chips, t09a_graph, t09a_snap, t09a_console])

            with gr.Tab("🕸 Orchestrator-Worker 派工"):
                t09b_graph = gr.HTML(load_svg("09-map-diagram"), elem_classes=["graph-box"])
                t09b_chips = gr.HTML(chips_html(node_order(ex09.build_map_graph()), [], None))
                with gr.Column(elem_classes=["input-unit"]):
                    t09b_in = gr.Textbox(label="目标语言（空格分隔，每种语言派一个工人）",
                                         value="英 日 法")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t09b_btn = gr.Button("🕸 主管派工", variant="primary", size="sm")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1, elem_classes=["col-card"]):
                        t09b_snap = gr.Code(label="📦 最终 State（results 由 reducer 汇聚）", language="json")
                    with gr.Column(scale=1):
                        t09b_console = console_section()

                def t09b_run(user_text):
                    graph = ex09.build_map_graph()
                    order = node_order(graph)
                    langs = user_text.split()
                    state, done, lines = {}, [], [f"[{now()}] 主管拆任务：{len(langs)} 种语言 → Send 派 {len(langs)} 个工人"]
                    for done, cur, _lines, values, trace in run_stream_updates(graph, {"langs": langs, "results": []}):
                        state = values
                        yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("09-map-diagram"), done, cur),
                               json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
                    yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("09-map-diagram"), done, None),
                           json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

                t09b_btn.click(t09b_run, inputs=[t09b_in],
                               outputs=[t09b_chips, t09b_graph, t09b_snap, t09b_console])

            with gr.Tab("🔁 Evaluator-Optimizer 改稿"):
                t09c_graph = gr.HTML(load_svg("09-eo-diagram"), elem_classes=["graph-box"])
                t09c_chips = gr.HTML(chips_html(node_order(ex09.build_eo_graph()), [], None))
                with gr.Column(elem_classes=["input-unit"]):
                    gr.HTML('<div style="font-size:.86em;color:#63668a;padding:2px 4px">评估器规则：每改一版涨 60 分，满 90 分通过；最多改 3 版（保险丝）。</div>')
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t09c_btn = gr.Button("🔁 启动写稿-评估循环", variant="primary", size="sm")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1, elem_classes=["col-card"]):
                        t09c_snap = gr.Code(label="📦 最终 State（观察 revision 与 score 的爬升）", language="json")
                    with gr.Column(scale=1):
                        t09c_console = console_section()

                def t09c_run():
                    graph = ex09.build_eo_graph()
                    order = node_order(graph)
                    state, done, lines = {}, [], [f"[{now()}] Evaluator-Optimizer：writer ⇄ evaluator 循环"]
                    for done, cur, _lines, values, trace in run_stream_updates(graph, {"draft": "", "score": 0, "revision": 0}):
                        state = values
                        yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("09-eo-diagram"), done, cur),
                               json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
                    yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("09-eo-diagram"), done, None),
                           json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

                t09c_btn.click(t09c_run, inputs=[],
                               outputs=[t09c_chips, t09c_graph, t09c_snap, t09c_console])

    # ================= 页面 10.10：长期记忆与 Time Travel =================
    with gr.Group(visible=False) as pg10:
        gr.HTML(head("10.10", "🗄", "Store 长期记忆与 Time Travel",
                     "InMemoryStore <b>|</b> get_state_history <b>|</b> update_state 改道",
                     "上半场看 Store 抽屉档案（换会话也在）；下半场 Time Travel：列出历史快照，点「改道」回到 step_a 之后替换 text，长出一条新历史。"))
        t10_graph = gr.HTML(load_svg("10-diagram"), elem_classes=["graph-box"])
        t10_chips = gr.HTML(chips_html(node_order(ex10.build_tt_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t10_btn = gr.Button("🗄 演示 Store 档案", size="sm")
                t10_tt_btn = gr.Button("⏱ 运行 Time Travel 图", variant="primary", size="sm")
                t10_replay_btn = gr.Button("▶️ 回放：让 B 重新执行", size="sm")
                t10_fork_btn = gr.Button("🪄 回到 A 点改道", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t10_snap = gr.Code(label="📦 State / 快照列表", language="json")
            with gr.Column(scale=1):
                t10_console = console_section()

        def t10_store_demo():
            from langgraph.store.memory import InMemoryStore
            store = InMemoryStore()
            ex10.seed_store(store)
            graph, store = ex10.make_assistant_graph(store)   # 把种子档案注入图实际使用的 Store
            drawer = [(i.key, i.value) for i in store.search(("user_123",))]
            config = {"configurable": {"thread_id": f"wb-{uuid.uuid4()}"}}
            order = node_order(graph)
            lines = [f"[{now()}] Store 抽屉（user_123）预填两张卡片：{drawer}",
                     f"[{now()}] 用全新 thread_id 启动 assistant 图；节点会从 Store 读取跨会话档案"]
            state, done = {}, []
            for done, cur, stream_lines, values, trace in run_stream_updates(
                    graph, {"user_id": "user_123", "reply": ""}, config):
                state = values
                view = {"短期_State": state, "长期_Store": drawer}
                yield (chips_html(order, done, cur, state=view),
                       highlight_svg(load_svg("10-store-diagram"), done, cur),
                       json.dumps(view, ensure_ascii=False, indent=2, default=str),
                       "\n".join(lines + list(stream_lines or [])))
            lines.append(f"[{now()}] Checkpointer 管会话内 State，Store 管跨会话档案：两个记忆层各管一段")
            view = {"短期_State": state, "长期_Store": drawer}
            yield (chips_html(order, done, None, state=view),
                   highlight_svg(load_svg("10-store-diagram"), done, None),
                   json.dumps(view, ensure_ascii=False, indent=2, default=str), "\n".join(lines))

        def t10_tt_run():
            graph = ex10.build_tt_graph()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            order = node_order(graph)
            state, done = {}, []
            intro = [f"[{now()}] Time Travel 正常运行：每过一个节点，Checkpointer 都保存一张状态照片"]
            for done, cur, stream_lines, values, trace in run_stream_updates(graph, {"text": "起点"}, config):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace),
                       highlight_svg(load_svg("10-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str),
                       "\n".join(intro + list(stream_lines or [])))
            history = list(graph.get_state_history(config))
            lines = [f"[{now()}] Time Travel 图跑完：起点 → A → B",
                     f"[{now()}] 历史快照数（含起点）：{len(history)}——每步都被 Checkpointer 存档"]
            snap_json = json.dumps([{"text": s.values.get("text"), "next": list(s.next or [])} for s in history],
                                   ensure_ascii=False, indent=2)
            yield (chips_html(order, done, None, state=graph.get_state(config).values),
                   highlight_svg(load_svg("10-diagram"), done, None), snap_json, "\n".join(lines))

        def t10_fork():
            graph = ex10.build_tt_graph()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            graph.invoke({"text": "起点"}, config)
            order = node_order(graph)
            history = list(graph.get_state_history(config))
            fork_config = next(s.config for s in history if s.values.get("text", "").endswith("-> A"))
            new_config = graph.update_state(fork_config, {"text": "起点 -> A（被人类改写）"}, as_node="step_a")
            new_result = graph.invoke(None, new_config)
            lines = [f"[{now()}] 找到 text=「起点 -> A」的快照，update_state(as_node='step_a') 改写",
                     f"[{now()}] invoke(None, fork_config)：从改写后的快照继续长出 B",
                     f"[{now()}] 改道后的新历史：{new_result['text']}——Time Travel = 回放 + 改道"]
            return (chips_html(order, ["step_a", "step_b"], None, state=new_result), highlight_svg(load_svg("10-diagram"), ["step_a", "step_b"], None),
                    json.dumps(new_result, ensure_ascii=False, indent=2), "\n".join(lines))

        def t10_replay():
            ex10.reset_step_b_counter()
            graph = ex10.build_tt_graph()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            first = graph.invoke({"text": "起点"}, config)
            history = list(graph.get_state_history(config))
            replay_config = next(s.config for s in history if s.values.get("text", "").endswith("-> A"))
            replayed = graph.invoke(None, replay_config)
            lines = [
                f"[{now()}] 第一次运行：step_b_runs={first['step_b_runs']}",
                f"[{now()}] 选择 A 之后的检查点执行 Replay；A 以前跳过，B 真实重跑",
                f"[{now()}] 回放结果：step_b_runs={replayed['step_b_runs']}。LLM/API/interrupt 同样会重新触发，结果未必相同",
            ]
            return (chips_html(node_order(graph), ["step_a", "step_b"], None, state=replayed),
                    highlight_svg(load_svg("10-diagram"), ["step_a", "step_b"], None),
                    json.dumps({"第一次": first, "回放后": replayed}, ensure_ascii=False, indent=2),
                    "\n".join(lines))

        t10_btn.click(t10_store_demo, outputs=[t10_chips, t10_graph, t10_snap, t10_console])
        t10_tt_btn.click(t10_tt_run, outputs=[t10_chips, t10_graph, t10_snap, t10_console])
        t10_replay_btn.click(t10_replay, outputs=[t10_chips, t10_graph, t10_snap, t10_console])
        t10_fork_btn.click(t10_fork, outputs=[t10_chips, t10_graph, t10_snap, t10_console])

    # ================= 页面 10.11：持久执行与容错 =================
    with gr.Group(visible=False) as pg11:
        gr.HTML(head("10.11", "🛡", "RetryPolicy 重试与断点恢复",
                     "RetryPolicy <b>|</b> Checkpointer <b>|</b> 崩溃 → 复活",
                     "两幕剧：① flaky_api 前两次抛超时被自动重试消化（看终端计数爬到 3）；② 图在 boom 节点崩掉，恢复后从最近快照复活——step_1 不会重跑。"))
        t11_graph = gr.HTML(load_svg("11-diagram"), elem_classes=["graph-box"])
        t11_chips = gr.HTML(chips_html(node_order(ex11.build_retry_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t11_btn = gr.Button("🛡 幕一：重试自愈（3 次内成功）", variant="primary", size="sm")
                t11_boom_btn = gr.Button("💥 幕二：运行中崩溃", size="sm")
                t11_rescue_btn = gr.Button("🚑 幕二：修复后复活", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t11_snap = gr.Code(label="📦 最终 State", language="json")
            with gr.Column(scale=1):
                t11_console = console_section()

        def t11_retry():
            ex11.reset_flaky()
            graph = ex11.build_retry_graph()
            order = node_order(graph)
            lines = [f"[{now()}] flaky_api 挂 RetryPolicy(max_attempts=3)：前两次抛 TimeoutError"]
            state = graph.invoke({"steps": [], "done": False})
            yield (chips_html(order, [], "__start__", state={"attempt": 0, "说明": "进入重试图"}),
                   highlight_svg(load_svg("11-diagram"), [], "__start__"), "{}", "\n".join(lines))
            for item in ex11.flaky_trace:
                attempt_view = {"attempt": item["attempt"], "node": "flaky_api", "result": item["result"],
                                "State尚未提交": item["attempt"] < 3}
                lines.append(f"[{now()}] 第 {item['attempt']} 次调用：{item['result']}")
                yield (chips_html(order, ["__start__"], "flaky_api", state=attempt_view),
                       highlight_svg(load_svg("11-diagram"), ["__start__"], "flaky_api"),
                       json.dumps(attempt_view, ensure_ascii=False, indent=2), "\n".join(lines))
                if ANIMATION_DELAY:
                    time.sleep(ANIMATION_DELAY)
            lines.append(f"[{now()}] 第 3 次成功后节点才提交状态增量；前两次没有污染 State ✓")
            done = ["__start__", "flaky_api", "__end__"]
            result_view = {"最终 State": state, "RetryPolicy 调用轨迹": list(ex11.flaky_trace)}
            yield (chips_html(order, done, None, state=result_view), highlight_svg(load_svg("11-diagram"), done, None),
                   json.dumps(result_view, ensure_ascii=False, indent=2), "\n".join(lines))

        def t11_boom():
            ex11.reset_boom()
            graph = ex11.build_rescue_graph()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            _rescue_state["graph"], _rescue_state["config"] = graph, config
            order = node_order(graph)
            lines = [f"[{now()}] 图运行：step_1 完成 → boom 节点引爆 RuntimeError！"]
            try:
                graph.invoke({"steps": [], "done": False}, config)
            except RuntimeError as e:
                lines.append(f"[{now()}] 💥 程序崩溃：{e}")
            lines.append(f"[{now()}] 但 Checkpointer 已存档 step_1 的成果——修复后可从最近快照复活")
            snap = graph.get_state(config)
            svg = "11-rescue-diagram"
            yield (chips_html(order, [], "__start__", state={}), highlight_svg(load_svg(svg), [], "__start__"),
                   "{}", f"[{now()}] START 把初始 State 交给 step_1")
            yield (chips_html(order, ["__start__"], "step_1", state={"steps": []}),
                   highlight_svg(load_svg(svg), ["__start__"], "step_1"),
                   json.dumps({"steps": []}, ensure_ascii=False, indent=2), f"[{now()}] step_1 正在写入第一项成果")
            failure_view = {"Checkpoint_State": snap.values, "失败节点": "boom", "next": list(snap.next or [])}
            yield (chips_html(order, ["__start__", "step_1"], "boom", state=failure_view),
                   highlight_svg(load_svg(svg), ["__start__", "step_1"], "boom"),
                   json.dumps(failure_view, ensure_ascii=False, indent=2), "\n".join(lines))

        def t11_rescue():
            graph, config = _rescue_state["graph"], _rescue_state["config"]
            if graph is None:
                graph = ex11.build_rescue_graph()
                order = node_order(graph)
                yield (chips_html(order, [], None), load_svg("11-rescue-diagram"), "{}",
                       f"[{now()}] 请先点「💥 幕二：运行中崩溃」")
                return
            order = node_order(graph)
            ex11.disarm_boom()
            before = graph.get_state(config).values
            yield (chips_html(order, ["__start__", "step_1"], "boom", state=before),
                   highlight_svg(load_svg("11-rescue-diagram"), ["__start__", "step_1"], "boom"),
                   json.dumps(before, ensure_ascii=False, indent=2),
                   f"[{now()}] 从 Checkpoint 恢复：step_1 保持绿色，只重新进入 boom")
            graph.invoke(None, config)
            snap = graph.get_state(config)
            lines = [f"[{now()}] 🚑 引爆开关已拆除，invoke(None, config) 从最近快照继续",
                     f"[{now()}] 最终状态：{snap.values['steps']}——注意 step_1 没有被重新执行 ✓"]
            done = ["__start__", "step_1", "boom", "__end__"]
            yield (chips_html(order, done, None, state=snap.values),
                   highlight_svg(load_svg("11-rescue-diagram"), done, None),
                   json.dumps(snap.values, ensure_ascii=False, indent=2), "\n".join(lines))

        t11_btn.click(t11_retry, outputs=[t11_chips, t11_graph, t11_snap, t11_console])
        t11_boom_btn.click(t11_boom, outputs=[t11_chips, t11_graph, t11_snap, t11_console])
        t11_rescue_btn.click(t11_rescue, outputs=[t11_chips, t11_graph, t11_snap, t11_console])

    # ================= 页面 10.12：子图嵌套 =================
    with gr.Group(visible=False) as pg12:
        gr.HTML(head("10.12", "🪆", "子图嵌套与 xray 透视",
                     "子图.compile() <b>|</b> 共享键透传 <b>|</b> get_graph(xray=True)",
                     "编译好的子图整个当父图的一个节点。切换「透视」开关看 xray：默认子图是黑盒单节点，xray=True 展开内部结构。"))
        t12_graph = gr.HTML(load_svg("12-diagram"), elem_classes=["graph-box"])
        t12_chips = gr.HTML(chips_html(node_order(ex12.build_graph()), [], None))
        with gr.Column(elem_classes=["input-unit"]):
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t12_btn = gr.Button("🪆 运行父子图", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t12_snap = gr.Code(label="📦 最终 State（父图能看到共享键 ticket）", language="json")
            with gr.Column(scale=1):
                t12_console = console_section()

        def t12_run():
            graph = ex12.build_graph()
            order = node_order(graph)
            state, done, lines = {}, [], [f"[{now()}] 父图把「航班部门子图」当普通节点调用…"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"messages": [("user", "帮我订机票")], "ticket": ""}):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("12-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
            black = " -> ".join(n.name for n in graph.get_graph().nodes.values())
            xray = " -> ".join(n.name for n in graph.get_graph(xray=True).nodes.values())
            lines.append(f"[{now()}] xray=False（黑盒）：{black}")
            lines.append(f"[{now()}] xray=True（透视）：{xray}")
            lines.append(f"[{now()}] 父图视角的共享键 ticket = {state.get('ticket')}（子图私有内部看不见，共享键透传）")
            yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("12-diagram"), done, None),
                   json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines))

        t12_btn.click(t12_run, outputs=[t12_chips, t12_graph, t12_snap, t12_console])

    # ================= 页面 10.12b：当前分类下的三种重点实现（12b 节） =================
    with gr.Group(visible=False) as pg12b:
        gr.HTML(head("10.12b", "🎭", "当前官方分类下的三种重点实现",
                     "Router <b>|</b> Subagents (Supervisor) <b>|</b> Custom workflow",
                     "Router 负责分类与并行分发；Subagents 由主 Agent 把专家当工具调用；Planner-Executor-Reviewer 属于 LangGraph 自定义工作流。完整分类还包括 Handoffs 与 Skills，详见 12 节。"))
        with gr.Tabs():
            with gr.Tab("🏥 Router 路由分流"):
                t12b_a_graph = gr.HTML(load_svg("12-diagram-02"), elem_classes=["graph-box"])
                t12b_a_chips = gr.HTML(chips_html(node_order(ex12b.build_router_graph()), [], None))
                with gr.Column(elem_classes=["input-unit"]):
                    t12b_a_in = gr.Textbox(label="用户请求（含「数据库」走 SQL，含「文档/知识库」走 RAG，其余走 Code）",
                                           value="帮我查一下上个月的数据库订单量")
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t12b_a_btn = gr.Button("🏥 分诊台分流", variant="primary", size="sm")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1, elem_classes=["col-card"]):
                        t12b_a_snap = gr.Code(label="📦 最终 State", language="json")
                    with gr.Column(scale=1):
                        t12b_a_console = console_section()

                def t12b_a_run(user_text):
                    graph = ex12b.build_router_graph()
                    order = node_order(graph)
                    state, done, lines = {}, [], [f"[{now()}] 分诊台接单，按意图分流到对应专员…"]
                    for done, cur, _lines, values, trace in run_stream_updates(graph, {"question": user_text, "kind": "", "answer": ""}):
                        state = values
                        yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("12-diagram-02"), done, cur),
                               json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
                    yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("12-diagram-02"), done, None),
                           json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

                t12b_a_btn.click(t12b_a_run, inputs=[t12b_a_in],
                                 outputs=[t12b_a_chips, t12b_a_graph, t12b_a_snap, t12b_a_console])

            with gr.Tab("👔 Subagents（Supervisor）"):
                t12b_b_graph = gr.HTML(load_svg("12-diagram-03"), elem_classes=["graph-box"])
                t12b_b_chips = gr.HTML(chips_html(node_order(ex12b.build_supervisor_graph()), [], None))
                with gr.Column(elem_classes=["input-unit"]):
                    gr.HTML('<div style="font-size:.86em;color:#63668a;padding:2px 4px">注意看终端：researcher 干完「交回主管」，主管再派 writer——这就是与 Orchestrator-Worker（一次拆完并行）的本质区别：循环派活。</div>')
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t12b_b_btn = gr.Button("👔 主管开始派单", variant="primary", size="sm")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1, elem_classes=["col-card"]):
                        t12b_b_snap = gr.Code(label="📦 最终 State（reports 由 reducer 汇聚）", language="json")
                    with gr.Column(scale=1):
                        t12b_b_console = console_section()

                def t12b_b_run():
                    graph = ex12b.build_supervisor_graph()
                    order = node_order(graph)
                    state, done, lines = {}, [], [f"[{now()}] 主管接单，进入循环派活：researcher → writer → 汇总…"]
                    for done, cur, _lines, values, trace in run_stream_updates(graph, {"task": "写一份行业调研报告", "cursor": 0, "reports": [], "final": ""}):
                        state = values
                        yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("12-diagram-03"), done, cur),
                               json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
                    yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("12-diagram-03"), done, None),
                           json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

                t12b_b_btn.click(t12b_b_run, outputs=[t12b_b_chips, t12b_b_graph, t12b_b_snap, t12b_b_console])

            with gr.Tab("🔁 Planner-Executor-Reviewer"):
                t12b_c_graph = gr.HTML(load_svg("12-diagram-04"), elem_classes=["graph-box"])
                t12b_c_chips = gr.HTML(chips_html(node_order(ex12b.build_per_graph()), [], None))
                with gr.Column(elem_classes=["input-unit"]):
                    gr.HTML('<div style="font-size:.86em;color:#63668a;padding:2px 4px">评审员规则：改到第 2 版即放行；重试达 3 版触发保险丝强制通过（呼应 9 节 Evaluator-Optimizer 的防死循环技巧）。看 executor 与 reviewer 被点亮多次。</div>')
                    with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                        t12b_c_btn = gr.Button("🔁 启动规划-执行-评审", variant="primary", size="sm")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1, elem_classes=["col-card"]):
                        t12b_c_snap = gr.Code(label="📦 最终 State（观察 revision 爬升）", language="json")
                    with gr.Column(scale=1):
                        t12b_c_console = console_section()

                def t12b_c_run():
                    graph = ex12b.build_per_graph()
                    order = node_order(graph)
                    state, done, lines = {}, [], [f"[{now()}] 规划师拆解需求 → 执行者出稿 → 评审员把关（不过就打回）…"]
                    for done, cur, _lines, values, trace in run_stream_updates(graph, {"requirement": "做一个数据看板", "plan": "", "draft": "", "verdict": "", "revision": 0}):
                        state = values
                        yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("12-diagram-04"), done, cur),
                               json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))
                    yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("12-diagram-04"), done, None),
                           json.dumps(state, ensure_ascii=False, indent=2, default=str), "\n".join(lines + list(_lines or [])))

                t12b_c_btn.click(t12b_c_run, outputs=[t12b_c_chips, t12b_c_graph, t12b_c_snap, t12b_c_console])

    # ================= 页面 10.13：HITL 进阶（金额滑杆切两级审批） =================
    with gr.Group(visible=False) as pg13:
        gr.HTML(head("10.13", "✋", "interrupt() 动态中断与 Command(resume)",
                     "interrupt() <b>|</b> Command(resume) <b>|</b> 多级审批",
                     "拖动金额滑杆：≤10 万组长一人审批；>10 万组长通过后还要老板二审。resume 的值会成为 interrupt() 的返回值——数据包进出，流程续上。"))
        t13_graph = gr.HTML(load_svg("13-diagram"), elem_classes=["graph-box"])
        t13_chips = gr.HTML(chips_html(node_order(ex13.build_graph()), [], None))
        t13_pending = gr.HTML(visible=False, elem_id="t13-pending")
        with gr.Column(elem_classes=["input-unit"]):
            t13_amount = gr.Slider(1000, 300000, value=5000, step=1000, label="转账金额（元）",
                                   info="> 100000 触发老板二审", elem_classes=["dashed-zone"])
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t13_btn = gr.Button("✋ 发起转账", variant="primary", size="sm")
        with gr.Row(equal_height=False):
            t13_ok = gr.Button("✅ 通过", variant="primary", size="sm", visible=False)
            t13_no = gr.Button("❌ 驳回", size="sm", visible=False)
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                t13_snap = gr.Code(label="📦 审批日志（log 字段）", language="json")
            with gr.Column(scale=1):
                t13_console = console_section()

        def t13_start(amount):
            graph = ex13.build_graph()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            _t13["graph"], _t13["config"] = graph, config
            _t13["resume_history"] = []
            order = node_order(graph)
            state, done, lines = {}, [], [f"[{now()}] 发起转账 {amount} 元，图进入 transfer 节点…"]
            for done, cur, _lines, values, trace in run_stream_updates(graph, {"amount": int(amount), "log": []}, config):
                state = values
                yield (chips_html(order, done, cur, state=values, trace=trace), highlight_svg(load_svg("13-diagram"), done, cur),
                       json.dumps(state, ensure_ascii=False, indent=2, default=str),
                       "\n".join(lines + list(_lines or [])),
                       gr.update(visible=False), gr.update(visible=False), gr.update(visible=False))
            result = graph.get_state(config)
            nxt = result.next
            pkt = (result.values.get("__interrupt__") or [None]) and None
            try:
                pkt = result.tasks[0].interrupts[0].value if result.tasks and result.tasks[0].interrupts else None
            except Exception:
                pass
            if pkt:
                lines.append(f"[{now()}] ⏸ interrupt() 抛出待审批数据包：{json.dumps(pkt, ensure_ascii=False)}")
                lines.append(f"[{now()}] 图挂起。批准/驳回都会以 Command(resume=...) 把决定塞回 interrupt() 的返回值")
                bar = (f'<div class="pending-bar"><span class="pulse"></span><b>{pkt["level"]}：</b>'
                       f'金额 {pkt["amount"]} 元 —— 请审批</div>')
                checkpoint = {"Checkpoint State": result.values, "next": list(result.next or []),
                              "interrupt 数据包": pkt, "resume 历史": []}
                yield (chips_html(order, done, "transfer", state=checkpoint),
                       highlight_svg(load_svg("13-diagram"), done, "transfer"),
                       json.dumps(checkpoint, ensure_ascii=False, indent=2), "\n".join(lines),
                       gr.update(visible=True, value=bar), gr.update(visible=True), gr.update(visible=True))
            else:
                yield (chips_html(order, done, None, state=state, trace=trace), highlight_svg(load_svg("13-diagram"), done, None),
                       json.dumps(state, ensure_ascii=False, indent=2), "\n".join(lines),
                       gr.update(visible=False), gr.update(visible=False), gr.update(visible=False))

        def t13_decide(approved: bool, note: str):
            graph, config = _t13["graph"], _t13["config"]
            order = node_order(graph)
            lines = [f"[{now()}] {note}"]
            _t13["resume_history"].append({"approved": approved, "说明": note})
            state = graph.invoke(Command(resume={"approved": approved}), config)
            snapshot = graph.get_state(config)
            try:
                tasks = graph.get_state(config).tasks
                pkt = next((t.interrupts[0].value for t in tasks if t.interrupts), None)
            except Exception:
                pkt = None
            state.pop("__interrupt__", None)
            checkpoint = {"Checkpoint State": snapshot.values, "next": list(snapshot.next or []),
                          "interrupt 数据包": pkt, "resume 历史": list(_t13["resume_history"])}
            if pkt:
                lines.append(f"[{now()}] ⏸ 又一层审批挂起：{json.dumps(pkt, ensure_ascii=False)}")
                lines.append(f"[{now()}] 注意：interrupt 仍在 transfer 节点内部；节点尚未 return，所以业务 log 要等本节点完成才提交")
                bar = (f'<div class="pending-bar"><span class="pulse"></span><b>{pkt["level"]}：</b>'
                       f'金额 {pkt["amount"]} 元 —— 请审批</div>')
                return (chips_html(order, ["__start__"], "transfer", state=checkpoint),
                        highlight_svg(load_svg("13-diagram"), ["__start__"], "transfer"),
                        json.dumps(checkpoint, ensure_ascii=False, indent=2), "\n".join(lines),
                        gr.update(visible=True, value=bar), gr.update(visible=True), gr.update(visible=True))
            lines.append(f"[{now()}] 流程终了：{state['log']}")
            checkpoint["interrupt 数据包"] = None
            return (chips_html(order, ["__start__", "transfer", "__end__"], None, state=checkpoint),
                    highlight_svg(load_svg("13-diagram"), ["__start__", "transfer", "__end__"], None),
                    json.dumps(checkpoint, ensure_ascii=False, indent=2), "\n".join(lines),
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=False))

        def t13_approve():
            return t13_decide(True, "✅ 审批人点了「通过」→ Command(resume={'approved': True})")

        def t13_reject():
            return t13_decide(False, "❌ 审批人点了「驳回」→ Command(resume={'approved': False})")

        t13_btn.click(t13_start, inputs=[t13_amount],
                      outputs=[t13_chips, t13_graph, t13_snap, t13_console, t13_pending, t13_ok, t13_no])
        confirm_approval_js = """() => {
            const detail = document.querySelector('#t13-pending')?.innerText?.trim() || '当前审批';
            if (!window.confirm(`确认通过？\n\n${detail}\n\n通过后会用 Command(resume) 恢复 LangGraph。`)) {
                throw new Error('用户取消审批');
            }
            return [];
        }"""
        confirm_reject_js = """() => {
            const detail = document.querySelector('#t13-pending')?.innerText?.trim() || '当前审批';
            if (!window.confirm(`确认驳回？\n\n${detail}\n\n驳回决定会写入 resume 历史并终止当前审批链。`)) {
                throw new Error('用户取消驳回');
            }
            return [];
        }"""
        t13_ok.click(t13_approve, js=confirm_approval_js,
                     outputs=[t13_chips, t13_graph, t13_snap, t13_console, t13_pending, t13_ok, t13_no])
        t13_no.click(t13_reject, js=confirm_reject_js,
                     outputs=[t13_chips, t13_graph, t13_snap, t13_console, t13_pending, t13_ok, t13_no])

    # ================= 页面 10.14：Functional API =================
    with gr.Group(visible=False) as pg14:
        gr.HTML(head("10.14", "🧪", "Functional API：@entrypoint 与 @task",
                     "@entrypoint <b>|</b> @task future <b>|</b> interrupt()",
                     "先创建翻译与摘要两个 future，让任务真正并行；统一取结果后写初稿，再进入人工审阅。若每行创建 future 后立刻 .result()，看似异步，实际仍是串行。"))
        t14_graph = gr.HTML(load_svg("14-diagram"), elem_classes=["graph-box"])
        t14_order = ["__start__", "translate", "summarize", "write_essay", "review", "__end__"]
        t14_chips = gr.HTML(chips_html(t14_order, [], None))
        with gr.Column(elem_classes=["input-unit"]):
            t14_in = gr.Textbox(label="作文题目", value="机器人安全")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t14_btn = gr.Button("🧪 启动写作流程", variant="primary", size="sm")
        # 人工审阅弹窗：流程走到 review 工序时弹出，初稿 + 驳回意见 + 决策按钮同屏
        with gr.Column(visible=False, elem_classes=["review-modal-mask"]) as t14_modal:
            with gr.Column(elem_classes=["review-modal"]):
                gr.HTML('<div class="review-head"><span class="review-pulse"></span>'
                        '<b>✋ 人工审阅请求</b><span class="review-tag">interrupt() 挂起 · 等待 Command(resume)</span></div>'
                        '<p class="review-sub">write_essay 已产出初稿，review 工序把决定权交给你 —— '
                        '批准或打回都会成为 interrupt() 的返回值，流程据此续跑。</p>')
                t14_document = gr.Markdown("流程运行后，这里会展示完整初稿。", elem_classes=["document-preview"])
                t14_feedback = gr.Textbox(label="驳回意见（仅点“打回修改”时使用）",
                                          value="请补充风险边界和人工兜底方案")
                with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                    t14_no = gr.Button("❌ 打回修改", size="sm")
                    t14_ok = gr.Button("✅ 批准发布", variant="primary", size="sm")
        with gr.Row(equal_height=True):
            with gr.Column(scale=1, elem_classes=["col-card"]):
                with gr.Tabs():
                    with gr.Tab("🧾 原始状态"):
                        t14_snap = gr.Code(label="Functional API 返回值与审批状态", language="json")
            with gr.Column(scale=1):
                t14_console = console_section()

        def t14_start(topic):
            flow = ex14.build_flow()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            _t14["flow"], _t14["config"] = flow, config
            result = flow.invoke(topic, config)
            try:
                pkt = result["__interrupt__"][0].value
            except Exception:
                pkt = None
            draft = pkt.get("essay", "") if isinstance(pkt, dict) else ""
            lines = [f"[{now()}] @entrypoint 先发出 translate_topic 与 summarize_topic 两张工单，再统一 .result()",
                     f"[{now()}] 两个准备任务并行完成，write_essay 使用合并材料生成初稿",
                     f"[{now()}] ⏸ review 工序 interrupt() 挂起，待审批数据包：{json.dumps(pkt, ensure_ascii=False) if pkt else '（无）'}",
                     f"[{now()}] 普通函数控制流 + 框架接管持久化——这就是 Functional API 的分界线"]
            console_text = "\n".join(lines) + (f"\n待审批数据包：{json.dumps(pkt, ensure_ascii=False)}" if pkt else "")            # Functional API 的 entrypoint 不提供逐节点 stream，因此这里按真实工序阶段
            # 展示已经完成的持久化任务；并行 Future 在同一帧同时点亮，再汇合到 review 挂起。
            stages = [
                ([], "__start__", "进入 START 入口：先把翻译和摘要两张 Future 工单发出去…"),
                (["__start__"], ["translate", "summarize"], "START 已完成，两张独立工单同时执行：翻译与摘要 Future 正在并行…"),
                (["__start__", "translate", "summarize"], "write_essay", "两个 Future 已完成，统一 .result() 后开始写初稿…"),
                (["__start__", "translate", "summarize", "write_essay"], "review", "初稿已生成，review 工序等待人工决定…"),
            ]
            for i, (done_nodes, current_node, stage_line) in enumerate(stages):
                stage_state = {"阶段": stage_line, "审批状态": "等待人工审阅"}
                if draft and current_node == "review":
                    stage_state["draft"] = draft
                raw = {"status": "waiting_review", "current": current_node,
                       "draft": draft if current_node == "review" else "初稿仍在上游工序中"}
                yield (chips_html(t14_order, done_nodes, current_node, state=stage_state),
                       highlight_svg(load_svg("14-diagram"), done_nodes, current_node),
                       draft or "*初稿正在生成…*", json.dumps(raw, ensure_ascii=False, indent=2),
                       console_text + f"\n[{now()}] ● {stage_line}",
                       gr.update(visible=(i == len(stages) - 1)))
                if ANIMATION_DELAY:
                    time.sleep(ANIMATION_DELAY)

        def t14_decide(approved: bool, note: str, feedback: str = ""):
            flow, config = _t14["flow"], _t14["config"]
            reason = feedback.strip() or "请补充具体修改意见"
            final = flow.invoke(Command(resume={"approved": approved, "reason": reason}), config)
            lines = [f"[{now()}] {note}",
                     f"[{now()}] resume 的值成为 interrupt() 的返回值，流程续跑完成",
                     f"[{now()}] 最终产出：{final}"]
            done_nodes = ["__start__", "translate", "summarize", "write_essay", "review"]
            result_view = {"status": "published" if approved else "needs_revision", "approved": approved,
                           "feedback": "" if approved else reason, "final": final}
            return (chips_html(t14_order, done_nodes + ["__end__"], None, state=result_view),
                    highlight_svg(load_svg("14-diagram"), done_nodes + ["__end__"], None),
                    final, json.dumps(result_view, ensure_ascii=False, indent=2), "\n".join(lines),
                    gr.update(visible=False))

        def t14_approve(feedback):
            return t14_decide(True, "✅ 审阅通过 → Command(resume)", feedback)

        def t14_reject(feedback):
            return t14_decide(False, "❌ 打回修改 → Command(resume)", feedback)

        t14_btn.click(t14_start, inputs=[t14_in],
                      outputs=[t14_chips, t14_graph, t14_document, t14_snap, t14_console, t14_modal])
        t14_ok.click(t14_approve, inputs=[t14_feedback],
                     outputs=[t14_chips, t14_graph, t14_document, t14_snap, t14_console, t14_modal])
        t14_no.click(t14_reject, inputs=[t14_feedback],
                     outputs=[t14_chips, t14_graph, t14_document, t14_snap, t14_console, t14_modal])

    # ================= 导航切换 =================
    page_groups = [pg02, pg03, pg04, pg05, pg06, pg07, pg08, pg09, pg10, pg11, pg12, pg12b, pg13, pg14]

    def show_page(selected):
        return [gr.update(visible=(selected == name)) for name in PAGES]

    page_selector.change(show_page, inputs=page_selector, outputs=page_groups)

    # ================= 页脚 =================
    gr.HTML("""
    <div class="footer">
      <div class="footer-line">🌊 <b>Vibe Coding 开源教学知识库</b> · 第十章配套图工作台（14 关卡）｜
      📖 <a href="https://docs.langchain.com/oss/python/langgraph/overview" target="_blank">LangGraph 官方文档</a> ｜
      🎛 <a href="https://www.gradio.app/docs" target="_blank">Gradio 官方文档</a> ｜
      🔍 每关都有「过程透视」终端 · 拒绝黑盒</div>
      <div class="footer-note">Powered by LangGraph 1.x · Gradio 6 · 全部演示零 API Key（假模型 / 规则驱动）</div>
    </div>
    """)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False, theme=THEME, css=custom_css)
