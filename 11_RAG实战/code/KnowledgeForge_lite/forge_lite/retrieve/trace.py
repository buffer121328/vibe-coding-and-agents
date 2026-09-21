"""trace.py —— 检索轨迹：把「为什么是这几块」摊开给证据抽屉看。

蒸馏来源：完整版 QA 的 ``reasoning_steps`` + run 详情（前端点开看这一跑用了哪些资料）。
对应教程：11.5（可解释检索）+ 11.12（引用与路由）。

一次问答在页面上只看到答案和角标；出问题时需要往下翻一层：

1. **改了哪些查询**：原问题必须排在第一位，改写只追加；
2. **每一路各召回什么**：BM25 / 向量 / 图谱各自的名次，融合后排第几；
3. **证据资格**：能不能生成、为什么不能、缺哪个槽位；
4. **预算用掉多少**：检索 / 重写 / 复检各用了几次——卡在熔断上时一眼看出。

本模块只做**纯函数组装**：吃 ask() 的返回值或会话柜里的 run 行，吐结构化轨迹。
不调模型、不读网络，所以离线测试和证据抽屉能用同一份实现。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from ..core.evidence import status_label
from ..core.labels import ROUTE_LABELS, intent_text


@dataclass
class TraceStep:
    """轨迹里的一步。``lane`` 为 bm25/dense/graph 时表示某一路的召回。

    ``lane`` 是这一步属于哪个环节（``rewrite`` / 三路 id / ``evidence`` / ``budget``）；
    ``title`` 是给页面显示的一行标题；``detail`` 是补充说明；``rank`` 是名次，没有名次
    就是 ``None``（不是 0——0 是"第零名"，None 才是"这条路不排名次"）；
    ``item_id`` 是可选的身份串，比如改写步骤记下原问题，方便点进去对照。
    """

    lane: str
    title: str
    detail: str = ""
    rank: int | None = None
    item_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        """摊成扁平字典；``rank`` 允许为 ``None``，JSON 里就是 ``null``。"""
        return asdict(self)


@dataclass
class RetrievalTrace:
    """一次问答的体检单。字段与完整版 run 详情同形状，前端不另算。

    ``question`` 是原问题；``queries`` 是实际参与检索的查询（第一条必须是原问题）；
    ``intent`` / ``intent_label`` 是意图代号与中文；``status`` / ``status_label``
    是这一跑的结局（``ok`` / ``refuse`` …）；``response_status`` / ``evidence_label``
    是证据资格的代号与中文——两者刻意分开：结局是"答没答"，资格是"资料够不够答"；
    ``routes`` / ``route_labels`` 是召回走了哪几路及其中文名；``sources`` 是来源表
    （角标、出处、片段）；``lanes`` 是每块资料的逐路名次；``steps`` 是给页面读的
    有序步骤；``evidence`` 是原始资格结论（导出后可以原样再喂回来重渲染）；
    ``warn`` 是降级/兜底提示；``citations`` 是引用角标；``run_id`` 与
    ``conversation_id`` 指回会话柜里那一跑。
    """

    question: str
    queries: list[str] = field(default_factory=list)
    intent: str = ""
    intent_label: str = ""
    status: str = ""
    status_label: str = ""
    response_status: str = ""
    evidence_label: str = ""
    routes: list[str] = field(default_factory=list)
    route_labels: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    lanes: list[dict[str, Any]] = field(default_factory=list)
    steps: list[TraceStep] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    warn: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    run_id: str = ""
    conversation_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        """摊成给前端/导出的字典：``steps`` 逐条展开，其余列表各拷一份。

        拷列表而不是直接给引用，是因为这份字典会被存进 run 行、再读回来重渲染，
        中途谁都不该能顺着引用改到轨迹对象本身。
        """
        return {
            "question": self.question,
            "queries": list(self.queries),
            "intent": self.intent,
            "intent_label": self.intent_label,
            "status": self.status,
            "status_label": self.status_label,
            "response_status": self.response_status,
            "evidence_label": self.evidence_label,
            "routes": list(self.routes),
            "route_labels": list(self.route_labels),
            "sources": list(self.sources),
            "lanes": list(self.lanes),
            "steps": [step.as_dict() for step in self.steps],
            "evidence": self.evidence,
            "warn": self.warn,
            "citations": list(self.citations),
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
        }


def _split_route(route: str) -> list[str]:
    """把 ``routes`` 字符串拆成路线 id 列表并去重保序。

    ``route`` 形如 ``"bm25+dense"``——用 ``+`` 或空格分隔都认，所以先统一换成空格
    再切；``hybrid`` 这类融合名也在同一套规则里拆。去重是为了页面不出现
    "关键词 + 关键词"。
    """
    lanes: list[str] = []
    for part in str(route or "").replace("+", " ").split():
        key = part.strip().lower()
        if key and key not in lanes:
            lanes.append(key)
    return lanes


def _source_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把 ``payload`` 里的 citations + contexts 拼成来源表：角标号、出处、片段。

    两份列表按位置对齐（第 n 个 context 配第 n 个 citation）；citation 缺了角标就
    自己按序号补一个 ``[n]``，缺了 doc_id 就留空——留空比编一个假块号诚实，
    页面上显示"（未标注）"即可。返回的表按片段顺序排，就是角标顺序。
    """
    citations = list(payload.get("citations") or [])
    contexts = list(payload.get("contexts") or [])
    rows: list[dict[str, Any]] = []
    for index, text in enumerate(contexts):
        citation = citations[index] if index < len(citations) else {}
        rows.append({
            "position": index + 1,
            "marker": citation.get("marker") or f"[{index + 1}]",
            "doc_id": citation.get("doc_id") or "",
            "chunk_key": citation.get("doc_id") or "",
            "snippet": str(text)[:200],
        })
    return rows


def _lane_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """每一块资料的「哪几路召回了它、主路第几名、融合后第几名」。

    ``payload`` 是 ask() 的返回值或会话柜里的 run 行。

    数据来自检索明细（`source_details`）；老记录里没有明细就退回
    contexts 里的字典行；再没有就空表——不编造名次。
    """
    details: list[Any] = list(payload.get("source_details") or [])
    if not details:
        details = [item for item in (payload.get("contexts") or []) if isinstance(item, Mapping)]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(details):
        if not isinstance(item, Mapping):
            continue
        route = str(item.get("route") or "")
        lane_ids = _split_route(route)
        primary = lane_ids[0] if lane_ids else ""
        rows.append({
            "doc_id": item.get("doc_id") or "",
            "marker": item.get("marker") or f"[{index + 1}]",
            "fused_rank": int(item.get("fused_rank") or index + 1),
            "route_rank": int(item.get("route_rank") or 0),
            "why": str(item.get("why") or ""),
            "primary": primary,
            "lanes": [
                {
                    "id": lane,
                    "label": ROUTE_LABELS.get(lane, lane),
                    # 只有主路记了名次；其余路只知道「召回过」，不假装知道名次
                    "rank": int(item.get("route_rank") or 0) if lane == primary else None,
                }
                for lane in lane_ids
            ],
        })
    rows.sort(key=lambda row: row["fused_rank"] or 999)
    return rows


def _route_steps(payload: Mapping[str, Any]) -> list[TraceStep]:
    """按 citations 反推每一路的贡献。没有明细就只列融合结果。

    ``payload`` 是 ask() 返回值或会话柜 run 行。一路都拆不出来（``routes`` 为空）
    时给一条"本轮没有召回"的步骤，让页面显示"确实没召回"而不是留白。
    """
    steps: list[TraceStep] = []
    merged = _split_route(str(payload.get("routes") or ""))
    if not merged:
        steps.append(TraceStep(lane="hybrid", title="本轮没有召回", detail="候选池为空或被工牌裁空"))
        return steps
    for lane in merged:
        steps.append(TraceStep(
            lane=lane,
            title=f"{ROUTE_LABELS.get(lane, lane)}一路召回",
            detail="与其它一路或多路共用 RRF 排名；每路分数不可直接比大小",
        ))
    return steps


def _evidence_step(evidence: Mapping[str, Any]) -> TraceStep:
    """把资格结论 ``evidence`` 折成一步，把理由、缺的资料、覆盖率串成一句人话。

    空字典也照样产出一步（标题写"未评估"）——轨迹上缺了这一段，读的人会以为
    "没写就是没问题"，而实际含义恰恰相反：这一跑根本没走到评估那一步。
    """
    if not evidence:
        return TraceStep(lane="evidence", title="证据资格：未评估",
                         detail="本轮没有产出资格结论（通常是被预算拦住之前就结束了）")
    label = status_label(str(evidence.get("response_status") or ""))
    reasons = "、".join(str(code) for code in (evidence.get("reason_codes") or [])) or "无"
    missing = "；".join(
        str(item.get("description") or "")
        for item in (evidence.get("missing_information") or [])
        if isinstance(item, Mapping)
    )
    detail = f"理由：{reasons}"
    if missing:
        detail += f"；缺：{missing}"
    coverage = evidence.get("coverage")
    if isinstance(coverage, (int, float)):
        detail += f"；覆盖率 {float(coverage):.2f}"
    return TraceStep(
        lane="evidence",
        title=f"证据资格：{label}",
        detail=detail,
        rank=None,
    )


def _budget_step(payload: Mapping[str, Any]) -> TraceStep:
    """把 ``payload`` 里的重试次数折成一步，顺带把熔断规矩写在旁边。

    重试次数写在说明里而不是标题里：一步的标题要能横向对齐，次数是可变的细节。
    """
    retries = payload.get("attempts")
    detail = "每个质量关卡只给 1 次重试，超了直接拒答（RunBudget 熔断）"
    if retries is not None:
        detail = f"已重试 {retries} 次；" + detail
    return TraceStep(lane="budget", title="预算与重试", detail=detail)


def build_trace(payload: Mapping[str, Any] | None = None) -> RetrievalTrace:
    """吃 ask() 返回值或会话柜 run 行，吐结构化轨迹。缺字段不算错，如实留空。

    ``payload`` 是这一跑的原始记录，``None`` 当空字典处理——轨迹要能对着一份不完整的
    老记录渲染出来，而不是逼调用方先补齐字段。

    返回 ``RetrievalTrace``：改写、各路召回、证据资格、预算四段齐全；
    证据资格缺字段、或误把运行结局（``ok`` / ``refuse`` / ``regen``）当成资格码时，
    按结局反推（拒答记"证据不足"），不让页面把 ``ok`` 原样显示给用户。
    """
    data: Mapping[str, Any] = payload or {}
    question = str(data.get("question") or "")
    intent = str(data.get("intent") or "")
    status = str(data.get("status") or "")
    evidence = dict(data.get("evidence") or {})
    # 资格码和运行结局是两套词：answered / insufficient_evidence 是资格，
    # ok / refuse / regen 是流水线三态。老接口曾把 record.status 塞进
    # evidence.response_status，页面就会画出「证据 ok」这种内部切口。
    outcome_codes = {"ok", "refuse", "regen"}
    raw_status = str(evidence.get("response_status") or "")
    if not raw_status or raw_status in outcome_codes:
        evidence["response_status"] = (
            "insufficient_evidence" if status == "refuse"
            else ("answered" if status == "ok" else ("" if status in outcome_codes else status))
        )
        evidence["allows_generation"] = evidence["response_status"] in {
            "answered", "partially_answered",
        }
    elif "allows_generation" not in evidence:
        evidence["allows_generation"] = evidence["response_status"] in {
            "answered", "partially_answered",
        }
    routes = _split_route(str(data.get("routes") or ""))
    queries = [str(item) for item in (data.get("queries") or []) if str(item).strip()]

    steps: list[TraceStep] = []
    if queries:
        steps.append(TraceStep(
            lane="rewrite",
            title="查询改写",
            detail="原问题必须留在第一位；改写只追加，不替换",
            item_id=queries[0],
        ))
    steps.extend(_route_steps(data))
    if queries and len(queries) > 1:
        steps.append(TraceStep(
            lane="queries",
            title=f"实际参与检索的查询（{len(queries)} 条）",
            detail=" ｜ ".join(queries),
        ))
    steps.append(_evidence_step(evidence))
    steps.append(_budget_step(data))

    # 显式 lanes 优先：导出的轨迹（含名次行）可以原样再喂回来重渲染，
    # 存档、板书、测试都靠这条 round-trip。
    explicit_lanes = data.get("lanes")
    lanes = (
        [row for row in explicit_lanes if isinstance(row, Mapping)]
        if isinstance(explicit_lanes, list) and explicit_lanes
        else _lane_rows(data)
    )
    return RetrievalTrace(
        question=question,
        queries=queries,
        intent=intent,
        intent_label=intent_text(intent) if intent else "",
        status=status,
        status_label=status_label(status),
        response_status=str(evidence.get("response_status") or ""),
        evidence_label=status_label(str(evidence.get("response_status") or "")),
        routes=routes,
        route_labels=[ROUTE_LABELS.get(lane, lane) for lane in routes],
        sources=_source_rows(data),
        lanes=lanes,
        steps=steps,
        evidence=evidence,
        warn=str(data.get("warn") or ""),
        citations=list(data.get("citations") or []),
        run_id=str(data.get("run_id") or ""),
        conversation_id=str(data.get("conversation_id") or ""),
    )


def render_trace_markdown(trace: RetrievalTrace | Mapping[str, Any]) -> str:
    """把轨迹摊成 Markdown，导出会话和课堂板书共用。

    ``trace`` 既可以是 ``RetrievalTrace`` 对象，也可以是它的 ``as_dict()`` 结果
    （导出再读回来就是后一种），两条路走同一份渲染代码，板书和导出不会长得不一样。
    返回多行 Markdown；表格里的竖线会转义，免得一段正文把整张表撑破。
    """
    data = trace.as_dict() if isinstance(trace, RetrievalTrace) else dict(trace)
    lines: list[str] = []
    header = data.get("status_label") or data.get("status") or "未标注"
    lines.append(f"**状态**：{header}")
    if data.get("response_status"):
        lines.append(f"**证据资格**：{status_label(str(data['response_status']))}")
    if data.get("intent_label"):
        lines.append(f"**意图**：{data['intent_label']}")
    if data.get("route_labels"):
        lines.append(f"**召回路由**：{' + '.join(data['route_labels'])}")
    if data.get("queries"):
        lines.append("")
        lines.append("检索用的查询（第一条必须是原问题）：")
        for index, query in enumerate(data["queries"], 1):
            lines.append(f"{index}. {query}")
    steps = data.get("steps") or []
    if steps:
        lines.append("")
        lines.append("| 环节 | 说明 |")
        lines.append("| :--- | :--- |")
        for step in steps:
            detail = str(step.get("detail") or "").replace("|", "\\|")
            lines.append(f"| {step.get('title', '')} | {detail} |")
    lanes = data.get("lanes") or []
    if lanes:
        lines.append("")
        lines.append("| 融合名次 | 出处 | 各路召回 |")
        lines.append("| :--- | :--- | :--- |")
        for row in lanes:
            detail = "、".join(
                f"{item.get('label', item.get('id', ''))}"
                + (f" 第 {item['rank']} 名" if item.get("rank") else "")
                for item in (row.get("lanes") or [])
            ) or "—"
            lines.append(
                f"| {row.get('fused_rank', '')} | {row.get('doc_id') or '（未标注）'} | {detail} |"
            )
    sources = data.get("sources") or []
    if sources:
        lines.append("")
        lines.append("| 角标 | 出处 | 片段 |")
        lines.append("| :--- | :--- | :--- |")
        for row in sources:
            snippet = str(row.get("snippet") or "").replace("\n", " ").replace("|", "\\|")[:80]
            lines.append(f"| {row.get('marker', '')} | {row.get('doc_id') or '（未标注）'} | {snippet} |")
    if data.get("warn"):
        lines.append("")
        lines.append(f"> ⚠️ {data['warn']}")
    return "\n".join(lines)


def summarize_routes(trace: RetrievalTrace | Mapping[str, Any]) -> str:
    """一句话路由摘要，给工具条用：`关键词 + 向量 + 图谱`。

    ``trace`` 是轨迹对象或它的字典形状。一路都没有时返回"无召回"而不是空串——
    工具条上一片空白看起来像还没加载完。
    """
    data = trace.as_dict() if isinstance(trace, RetrievalTrace) else dict(trace)
    labels = data.get("route_labels") or []
    return " + ".join(labels) if labels else "无召回"


def coverage_note(trace: RetrievalTrace | Mapping[str, Any]) -> str:
    """给证据抽屉顶部的一句人话：这块资料够不够答。

    ``trace`` 是轨迹对象或它的字典形状。没有资格结论时明说"本轮没有资格结论"，
    而不是默认成"够答"——默认成够答，就等于把"没评估"当成了"没问题"。
    """
    data = trace.as_dict() if isinstance(trace, RetrievalTrace) else dict(trace)
    evidence = data.get("evidence") or {}
    if not evidence:
        return "本轮没有资格结论。"
    label = status_label(str(evidence.get("response_status") or ""))
    if evidence.get("allows_generation"):
        return f"资料够答（{label}）。"
    reasons = evidence.get("reason_codes") or []
    return f"资料不够自动作答（{label}）" + (f"：{'、'.join(map(str, reasons))}" if reasons else "。")
