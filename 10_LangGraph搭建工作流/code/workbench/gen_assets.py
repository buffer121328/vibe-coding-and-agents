"""gen_assets.py —— 从分节示例导出 mermaid 图源码（.mmd），供 House 渲染器出 SVG。

运行：python gen_assets.py   （在 workbench 目录内执行）
产物：assets/{节号}-diagram.mmd（随后用 node ../../scripts/render-house.mjs 渲染成 .svg）

节点 id 一律使用真实节点名（工作台点亮徽章与 SVG data-id 一一对应）；
Send 动态分支边（如 04 的 plan -> search_one_city）在 LangGraph 静态图里不存在，
按教学语义手工补画并以虚线标注。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "examples"))

OUT = HERE / "assets"
OUT.mkdir(exist_ok=True)

# LangGraph 静态图里不可见、但教学上必须画出的动态边（虚线）：{节号: [(src, dst), ...]}
EXTRA_EDGES = {
    "04": [("plan", "search_one_city"), ("search_one_city", "aggregate")],
}


def edge_line(src: str, dst: str, conditional: bool) -> str:
    """条件边画虚线（与 LangGraph 官方 draw_mermaid 的 -.-> 约定一致）"""
    arrow = '-.->' if conditional else '-->'
    return f"    {src} {arrow} {dst}"


def graph_to_mmd(graph, extra: list[tuple[str, str]] | None = None) -> str:
    """编译后的 LangGraph 图 -> House 风格 mermaid 源码（节点名 = 真实节点名）"""
    g = graph.get_graph()
    lines = []
    for n in g.nodes.values():
        # House 渲染器只认矩形/菱形两种 shape，起止节点用矩形语法（标签才会渲染出来）
        if n.name == "__start__":
            lines.append(f'    {n.name}["开始"]')
        elif n.name == "__end__":
            lines.append(f'    {n.name}["结束"]')
        else:
            lines.append(f'    {n.name}["{n.name}"]')
    seen = set()
    for e in g.edges:
        lines.append(edge_line(e.source, e.target, e.conditional))
        seen.add((e.source, e.target))
    for src, dst in (extra or []):
        if (src, dst) not in seen:
            lines.append(f"    {src} -.->|\"Send\"| {dst}")
    return "\n".join(lines)


def export(name: str, body: str):
    text = "graph TD\n" + body.strip() + "\n"
    (OUT / f"{name}.mmd").write_text(text, encoding="utf-8")
    print(f"wrote assets/{name}.mmd")


def main():
    from importlib import import_module

    m = {s: import_module(f"{s}_{'state_graph' if s == '02' else 'conditional_routing' if s == '03' else 'parallel_send' if s == '04' else 'streaming_debug' if s == '05' else 'memory_hitl' if s == '06' else 'multiagent_stack' if s == '07' else 'tool_loop' if s == '08' else 'workflow_patterns' if s == '09' else 'memory_timetravel' if s == '10' else 'durable_execution' if s == '11' else 'subgraphs' if s == '12' else 'hitl_interrupt'}_demo")
         for s in ["02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13"]}

    def dump(sec: str, graph):
        export(f"{sec}-diagram", graph_to_mmd(graph, EXTRA_EDGES.get(sec)))

    dump("02", m["02"].build_graph())
    dump("03", m["03"].build_graph())
    dump("04", m["04"].build_graph())
    dump("05", m["05"].build_graph())
    dump("06", m["06"].build_guarded())
    dump("07", m["07"].build_graph())
    dump("08", m["08"].build_graph())
    export("09-routing-diagram", graph_to_mmd(m["09"].build_routing_graph()))
    export("09-map-diagram", graph_to_mmd(m["09"].build_map_graph()))
    export("09-eo-diagram", graph_to_mmd(m["09"].build_eo_graph()))
    dump("10", m["10"].build_tt_graph())
    export("10-store-diagram", graph_to_mmd(m["10"].build_assistant_graph()))
    dump("11", m["11"].build_retry_graph())
    export("11-rescue-diagram", graph_to_mmd(m["11"].build_rescue_graph()))
    dump("12", m["12"].build_graph())
    dump("13", m["13"].build_graph())

    # 12b 三张图也从真实编译图生成，避免展示节点 ID 与 Python 节点名脱节，
    # 导致工作台收到流事件却无法点亮 SVG。
    m12b = import_module("12b_multiagent_paradigms_demo")
    export("12-diagram-02", graph_to_mmd(m12b.build_router_graph()))
    export("12-diagram-03", graph_to_mmd(m12b.build_supervisor_graph()))
    export("12-diagram-04", graph_to_mmd(m12b.build_per_graph()))

    # 14 Functional API：不画图，手工补一张 future 并行 + 审批流程图
    export("14-diagram", """
    __start__["输入：作文题目"]
    translate["@task 翻译 future"]
    summarize["@task 摘要 future"]
    write_essay["统一 .result() 后写初稿"]
    review["@task 人工审阅（interrupt）"]
    __end__["产出：完整文稿 / 修改单"]
    __start__ --> translate
    __start__ --> summarize
    translate --> write_essay
    summarize --> write_essay
    write_essay --> review
    review -->|"批准发布 / 驳回并返回修改单"| __end__
""")


if __name__ == "__main__":
    main()
