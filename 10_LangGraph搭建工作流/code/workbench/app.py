"""
app.py - LangGraph 图工作台（第十章 14 关可视化演示）
------------------------------------------------------------------
可视化对象：../examples/ 下 02~14 节的 14 个分节参考示例（真实 LangGraph 图，零 API Key）。
每一关把「发生了什么」透出来：
- 🗺 图结构：House 风格 SVG（assets/ 预渲染）+ 节点徽章行，跑完一个节点点亮一个
- 🔍 过程透视终端：stream_mode="updates" 逐节点打印状态增量，拒绝黑盒
- 📦 State 快照：运行结束后的完整状态 JSON
设计原则：教学透明 —— 课本示例原码在跑，工作台只是把它点亮。
文件分工：kit.py 放各页共用的画图与流式驱动，assets/workbench.css 放样式，本文件只管
「import 示例 → 每页布局 + 回调」。
启动：.venv/bin/python app.py   访问：http://127.0.0.1:7860（端口可用 GRADIO_SERVER_PORT 覆盖）
"""

import importlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

import gradio as gr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "examples"))

from langgraph.types import Command  # noqa: E402

from kit import (  # noqa: E402
    ANIMATION_DELAY, chips_html, highlight_svg, load_svg, node_order, now, run_stream_updates,
)

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

# 跨回调会话状态（挂起图的续跑句柄；Gradio 回调间共享）
_t06 = {"graph": None, "config": None}
_rescue_state = {"graph": None, "config": None}
_t13 = {"graph": None, "config": None, "resume_history": []}
_t14 = {"flow": None, "config": None}

CUSTOM_CSS = (HERE / "assets" / "workbench.css").read_text(encoding="utf-8")

THEME = gr.themes.Soft(
    primary_hue="indigo", secondary_hue="violet", neutral_hue="slate",
    radius_size=gr.themes.sizes.radius_lg)

PAGES = [
    "🧱 10.2 State 图的构建",
    "🚦 10.3 条件路由",
    "🕸 10.4 Send 并行分发",
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
                     "图 = 路线图，节点 = 格子上的工序，State = 公共交接本。点击运行，看 greeter 与 echo 两个节点如何接力传递 messages。"))
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
                     "前台主助理识别「机票」意图后压栈转交航班专员；专员办完弹栈交还。下方栈条实时显示 dialog_state 的压栈/弹栈过程。"))
        t07_graph = gr.HTML(load_svg("07-diagram"), elem_classes=["graph-box"])
        t07_chips = gr.HTML(chips_html(node_order(ex07.build_graph()), [], None))
        t07_stack = gr.HTML('<div class="stack-visual"><span class="stack-cap">dialog_state →</span>'
                            '<span class="stack-cell empty">（空栈：主助理值班）</span></div>')
        with gr.Column(elem_classes=["input-unit"]):
            t07_in = gr.Textbox(label="对前台主助理说点什么（含「机票」触发转交）",
                                value="帮我订一张去东京的机票")
            with gr.Row(equal_height=False, elem_classes=["btn-row tail"]):
                t07_btn = gr.Button("🏨 找前台主助理", variant="primary", size="sm")
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
            state, done, lines = {}, [], [f"[{now()}] 用户开口，前台主助理接单…"]
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
                    gr.HTML('<div style="font-size:.86em;color:#63668a;padding:2px 4px">评估器规则：每改一版涨 40 分（上限 100），满 90 分通过；最多改 3 版（保险丝）。本演示第 3 版到 100 分过线。</div>')
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
            interrupts = result.tasks[0].interrupts if result.tasks else ()
            pkt = interrupts[0].value if interrupts else None
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
      <div class="footer-note">Powered by LangGraph 1.2 · Gradio 6 · 全部演示零 API Key（假模型 / 规则驱动）</div>
    </div>
    """)

if __name__ == "__main__":
    # 端口默认 7860，可用 GRADIO_SERVER_PORT 覆盖——16 节的旅行助手也用 7860，
    # 两个台子同时开时必须错开（工作台无状态，随便换；空串按没配处理）。
    PORT = int((os.environ.get("GRADIO_SERVER_PORT") or "").strip() or 7860)
    demo.launch(server_name="127.0.0.1", server_port=PORT, share=False, theme=THEME, css=CUSTOM_CSS)
