"""
kit.py - 图工作台的通用零件：和具体哪一关无关，app.py 的每一页都在复用
------------------------------------------------------------------
- 节点徽章行 / 状态机卡片 / SVG 内高亮：把「跑到哪个节点了」画出来
- State 摘要与增量格式化：过程透视终端里每一行字从这里出
- run_stream_updates：stream_mode="updates" 的通用逐节点驱动，大多数关卡直接套用
"""

import html
import json
import os
import re
import time
from pathlib import Path

from langchain_core.messages import BaseMessage

ASSETS = Path(__file__).resolve().parent / "assets"
# 节点之间停顿的秒数，只为让人看清点亮顺序；冒烟测试里设 0
ANIMATION_DELAY = max(0.0, float(os.getenv("WORKBENCH_ANIMATION_DELAY", "0.55")))


# ==============================================================================
# 画图：节点点亮徽章 / SVG 内高亮 / 过程透视格式化
# ==============================================================================

def now():
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


# ==============================================================================
# 流式驱动：逐节点 yield，交给各页回调刷新界面
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
