"""evaluation.py —— 评测区服务层：逐条跑黄金集、落报告、留历史。

蒸馏来源：完整版 ``evaluation/`` 的评测运行与结果留档（evidence-gate runner 的课堂版）。
对应教程：11.9（三元组定位：检索的病与生成的病分开看）。

评测区看三件事，一条用例一行：

1. **行为对不对**：``expect`` 是 answer 还是 refuse，实际是否一致——**这一条不依赖裁判模型**；
2. **检索找没找到**：期望文档是否出现在引用里，给出 Hit / Recall / MRR——同样不需要裁判；
3. **答案质量**：交给 Ragas 0.4 三个指标（另开一个动作，见 ``evaluate.py``）。

所以 Lite 的评测分两层，和完整版一致：**门禁层不调裁判**（快、每次改动都能跑），
**体检层交给 Ragas**（慢、上线前跑）。报告落 ``runtime/evaluations/``，历史可回看。

为什么"行为判定"要给拒答题留出空期望文档：拒答题没有该召回的文档，
硬套 Hit/Recall 会把它算成"检索失败"——那是把两种病混成一种。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .. import config
from .evaluate import GOLDEN_SET
from ..core.identity import resolve_actor
from ..core.quality import retrieval_metrics


def reports_dir() -> Path:
    """评测报告的存放目录：``runtime/evaluations``。

    做成函数是为了跟 ``config.RUNTIME_DIR`` 联动——测试换运行时目录，报告也跟着走，
    不会把用例产物写进课堂那一份。返回目录的 ``Path``；此刻不一定存在，
    ``save_report`` 落盘时会建出来。
    """
    return config.RUNTIME_DIR / "evaluations"


@dataclass
class CaseResult:
    """一条用例的运行结果。字段与完整版 evidence-gate 的报告行同形状。

    输入侧：``case_id`` 是用例编号（黄金集里的 ``id``），``question`` 是原问题，
    ``user_id`` / ``actor_name`` 是问它的工牌（前者给机器对账，后者给页面显示），
    ``expect`` 是期望行为（``answer`` / ``refuse``），``expected_docs`` 是期望召回的文件名，
    拒答题为空列表。

    结果侧：``status`` 是实际结论；``behavior_ok`` 是行为判定——它不依赖裁判模型，
    所以每次改代码都能便宜地重跑；``hit`` / ``recall`` / ``mrr`` 是检索三项
    （拒答题恒为 0，理由见 ``run_case``）；``cited_docs`` 是实际引用到的文件名，
    ``citation_ok`` 是引用格式判定；``routes`` 是走通的检索通道，``evidence_status``
    是证据资格结论；``latency_ms`` 是一次问答的墙钟耗时，``warn`` 是链路累计提示；
    ``answer_preview`` 是答案前 160 字——够人工复盘，又不至于把报告撑爆。

    结论侧：``passed`` 是行为 + 检索 + 引用三项的合取判定，``reason`` 是一句人话解释，
    页面直接显示它，不必自己拼失败原因。
    """

    case_id: str
    question: str
    user_id: str
    actor_name: str
    expect: str
    expected_docs: list[str] = field(default_factory=list)
    status: str = ""
    behavior_ok: bool = False
    hit: float = 0.0
    recall: float = 0.0
    mrr: float = 0.0
    cited_docs: list[str] = field(default_factory=list)
    citation_ok: bool = True
    routes: str = ""
    evidence_status: str = ""
    latency_ms: int = 0
    warn: str = ""
    answer_preview: str = ""
    passed: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        """摊平成报告 JSON 里的一行；这些字段名就是报告契约，前端照着读。"""
        return asdict(self)


def _cited_docs(citations: list[dict[str, Any]] | None) -> list[str]:
    """从引用列表里抽出**文件名**（不是 doc_id），去重且保持引用顺序。

    ``citations`` 是 ``ask`` 返回的角标回映射结果，``doc_id`` 形如
    ``员工差旅管理制度.md#2``。评测只关心"命中了哪篇文档"，所以切块号在这里剥掉——
    带着它去比对 ``expected_docs``，同一篇文档的不同块会被当成不同文档，人工核对时更绕。
    返回文件名列表；引用为空或格式不对时返回空列表。
    """
    names: list[str] = []
    for item in citations or []:
        doc_id = str(item.get("doc_id") or "")
        name = doc_id.split("#", 1)[0]
        if name and name not in names:
            names.append(name)
    return names


def run_case(case: dict[str, Any], ask_fn: Callable[..., dict] | None = None) -> CaseResult:
    """跑一条用例。``ask_fn`` 可注入替身，测试与 SSE 都用它。

    ``case`` 是黄金集里的一条：``question`` 必填，``id`` / ``expect`` / ``expected_docs`` /
    ``user_id`` 可选；``ask_fn`` 是问答函数，不传就延迟导入 ``agent.ask``——
    延迟这一下是为了让离线测试不必拉起模型依赖。

    判定规则（写在这里，别让它散在页面里）：

    - ``behavior_ok``：期望作答就必须作答且带引用；期望拒答就必须是拒答；
    - ``passed``：行为对 **且** 期望文档命中（有期望文档时）**且** 引用格式通过；
    - 拒答题不看 Hit/Recall——它本来就该空手而归。硬算会把"该拒答且拒答了"记成
      "检索失败"，等于把检索的病和生成的病混成一种，页面上再也分不开。

    返回 ``CaseResult``；``case`` 缺 ``question`` 时会按 ``KeyError`` 当场炸——
    用例写错就该在第一次跑时发现，别让它悄悄产出一条没意义的记录。
    """
    if ask_fn is None:
        from .agent import ask as ask_fn
    actor = resolve_actor(case.get("user_id"))
    started = time.perf_counter()
    result = ask_fn(case["question"], user_id=actor.user_id, persist=False)
    latency = int((time.perf_counter() - started) * 1000)

    expect = str(case.get("expect") or "answer")
    expected_docs = list(case.get("expected_docs") or [])
    status = str(result.get("status") or "")
    cited = _cited_docs(result.get("citations"))
    answered = status == "ok"
    refused = status == "refuse"

    behavior_ok = refused if expect == "refuse" else (answered and bool(cited))
    # 引用合法性已在生成链路里过了门禁；门禁层只记结果，不再另算一遍。
    citation_ok = True
    metrics = {"hit_rate_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0}
    if expected_docs and answered:
        measured = retrieval_metrics(cited or ["(none)"], expected_docs, k=max(len(cited), 1))
        metrics = {key: measured[key] for key in ("hit_rate_at_k", "recall_at_k", "mrr")}
    elif expected_docs and not answered:
        metrics = {"hit_rate_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0}

    passed = behavior_ok and citation_ok and (not expected_docs or metrics["hit_rate_at_k"] > 0)
    if passed:
        reason = "行为与检索都符合预期"
    elif not behavior_ok:
        reason = f"期望{('拒答' if expect == 'refuse' else '作答')}，实际 {status or '未知'}"
    else:
        reason = f"未召回期望文档：{('、'.join(expected_docs))}"

    return CaseResult(
        case_id=str(case.get("id") or case["question"][:12]),
        question=case["question"],
        user_id=actor.user_id,
        actor_name=actor.display_name,
        expect=expect,
        expected_docs=expected_docs,
        status=status,
        behavior_ok=behavior_ok,
        hit=float(metrics["hit_rate_at_k"]),
        recall=float(metrics["recall_at_k"]),
        mrr=float(metrics["mrr"]),
        cited_docs=cited,
        citation_ok=citation_ok,
        routes=str(result.get("routes") or ""),
        evidence_status=str(result.get("response_status") or ""),
        latency_ms=latency,
        warn=str(result.get("warn") or ""),
        answer_preview=str(result.get("answer") or "")[:160],
        passed=passed,
        reason=reason,
    )


def run_gate(
    cases: list[dict[str, Any]] | None = None,
    ask_fn: Callable[..., dict] | None = None,
) -> bool:
    """跑门禁层并打印成绩单，返回是否过 ``PASS_RATE_GATE``。

    ``cases`` 是要跑的用例列表，缺省用 ``GOLDEN_SET``；``ask_fn`` 是问答函数，
    不传则由 ``run_case`` 用真的 ``agent.ask``——测试注入替身，命令行才走真链路。

    这一层**不调 Ragas**：只看该答的答了没有、该拒的拒了没有、期望文档召回了没有。
    改完切块 / 检索 / 闸门，应该跑的是它，不是 ``04_ragas_eval.py``。
    裁判打分留给上线前或评测区的第二个按钮。
    """
    results = list(iter_cases(cases, ask_fn=ask_fn))
    summary = summarize(results)
    print("\n=== KnowledgeForge Lite · 门禁层（不调裁判） ===")
    print("看：该答的答了没有 / 该拒的拒了没有 / 期望文档召回了没有")
    for item in results:
        mark = "过" if item.passed else "挂"
        print(f"  [{mark}] [{item.actor_name}] {item.question}  → {item.status}  {item.reason}")
    total = summary.get("total") or 0
    passed = summary.get("passed") or 0
    rate = float(summary.get("pass_rate") or 0.0)
    gate = float(summary.get("gate") if "gate" in summary else config.PASS_RATE_GATE)
    passed_gate = bool(summary.get("passed_gate")) if total else False
    print(f"\n通过 {passed}/{total}（{rate:.0%}）  门禁线 {gate:.0%}  {'过' if passed_gate else '没过'}")
    print("行为错了先看闸门；命中错了先看检索。Ragas 三指标请跑 scripts/04_ragas_eval.py。")
    return passed_gate


def iter_cases(
    cases: list[dict[str, Any]] | None = None,
    ask_fn: Callable[..., dict] | None = None,
) -> Iterator[CaseResult]:
    """逐条跑并逐条吐结果——SSE 靠它把进度一条条推给页面。

    ``cases`` 是要跑的用例列表，缺省用 ``GOLDEN_SET``；``ask_fn`` 是问答函数，
    不传则由 ``run_case`` 用真的 ``agent.ask``。逐条 ``yield`` 出 ``CaseResult``：
    吐一条、页面推一条，跑满八条不必等到最后一刻才看见第一个结果。
    判断用 ``cases if cases is not None else GOLDEN_SET`` 而不是 ``cases or GOLDEN_SET``：
    显式传空列表的调用方要的是"一条都不跑"，不该被当成没传。
    """
    for case in cases if cases is not None else GOLDEN_SET:
        yield run_case(case, ask_fn=ask_fn)


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    """通过率 + 两个分层的均值，给页面顶部一条摘要。

    ``results`` 是这一轮跑完的 ``CaseResult`` 列表。返回一个扁平字典：``total`` /
    ``passed`` / ``pass_rate`` / ``behavior_rate``（行为合格率，与检索分开看）、
    ``hit_rate`` 与 ``recall``（只对有期望文档的用例取均值——拒答题没有该召回的东西，
    把它们算进分母等于惩罚正确答案）、``avg_latency_ms``、``refused``（拒答条数），
    以及 ``gate`` / ``passed_gate``（``config.PASS_RATE_GATE`` 那道上线门禁过没过）。

    空列表返回一份全 0 的摘要而不是抛异常：还没跑过用例的页面也得能渲染出顶部条。
    """
    total = len(results)
    if not total:
        return {"total": 0, "passed": 0, "pass_rate": 0.0, "behavior_rate": 0.0,
                "hit_rate": 0.0, "recall": 0.0, "avg_latency_ms": 0, "refused": 0,
                "gate": config.PASS_RATE_GATE, "passed_gate": False}
    passed = sum(1 for item in results if item.passed)
    behavior = sum(1 for item in results if item.behavior_ok)
    scored = [item for item in results if item.expected_docs]
    return {
        "total": total,
        "passed": passed,
        "pass_rate": passed / total,
        "behavior_rate": behavior / total,
        "hit_rate": (sum(item.hit for item in scored) / len(scored)) if scored else 0.0,
        "recall": (sum(item.recall for item in scored) / len(scored)) if scored else 0.0,
        "avg_latency_ms": int(sum(item.latency_ms for item in results) / total),
        "refused": sum(1 for item in results if item.status == "refuse"),
        "gate": config.PASS_RATE_GATE,
        "passed_gate": (passed / total) >= config.PASS_RATE_GATE,
    }


def save_report(results: list[CaseResult], note: str = "") -> dict[str, Any]:
    """把一次评测落成 JSON 报告，返回报告摘要（含文件名）。

    ``results`` 是这一轮的用例结果；``note`` 是操作人留的一句话（比如"换了切块大小"），
    截到 200 字——它是事后翻历史时唯一的上下文，但也不该长到把报告撑肿。
    报告里同时记下 ``schema`` / ``chat_model`` / ``embed_model``：隔几天换了模型再比分数时，
    没有这三个字段就分不清"是真改好了"还是"换了裁判"。

    文件名用 UTC 时间戳（``eval-YYYYmmdd-HHMMSS.json``）；返回的报告字典在写盘内容之外
    多带一个 ``path``（只有文件名、不含目录），供前端点击查看。
    """
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema": config.INDEX_SCHEMA,
        "chat_model": config.CHAT_MODEL,
        "embed_model": config.EMBED_MODEL,
        "note": note[:200],
        "summary": summarize(results),
        "cases": [item.as_dict() for item in results],
    }
    reports_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = reports_dir() / f"eval-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["path"] = str(path.name)
    return report


def list_reports(limit: int = 10) -> list[dict[str, Any]]:
    """历史报告摘要，新的在前。页面只读摘要，点开才读全文。

    ``limit`` 是最多列几份，小于 1 会被抬到 1。返回摘要列表，每项含文件名、创建时间、
    备注与几个关键分数：摘要只读报告头部，不把 ``cases`` 整段搬进来——一屏十份报告的
    全量用例有几百 KB，而列表页一个字都用不上。

    先按文件名（也就是写入时刻）取一批，再按报告自己记的 ``created_at`` 重排：
    文件名记的是落盘那一刻、``created_at`` 记的是开跑那一刻，碰上跨秒的评测两者会错位，
    以报告自述的时间为准。读坏的文件直接跳过（``OSError`` / ``JSONDecodeError``），
    一份坏报告不该连累整页历史。
    """
    if not reports_dir().exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(reports_dir().glob("eval-*.json"), reverse=True)[:max(limit, 1) * 2]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = payload.get("summary") or {}
        rows.append({
            "path": path.name,
            "created_at": payload.get("created_at") or "",
            "note": payload.get("note") or "",
            "total": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "pass_rate": summary.get("pass_rate", 0.0),
            "hit_rate": summary.get("hit_rate", 0.0),
            "schema": payload.get("schema") or "",
            "chat_model": payload.get("chat_model") or "",
        })
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)[: max(limit, 1)]


def load_report(name: str) -> dict[str, Any]:
    """读一份历史报告全文。文件名只许 basename，挡住路径穿越。

    ``name`` 是列表页给出的文件名。先取 ``Path.name`` 再校验前后缀，于是
    ``../../etc/passwd`` 这类会先被剥成一段普通名字、前后缀又对不上，两道都过不去。
    返回报告字典；名字不合法抛 ``ValueError``，文件不存在抛 ``FileNotFoundError``——
    两种都属于"你点了个不存在的东西"，交给上层翻成 404 就好。
    """
    safe = Path(str(name or "")).name
    if not safe.startswith("eval-") or not safe.endswith(".json"):
        raise ValueError("报告文件名不合法")
    path = reports_dir() / safe
    if not path.exists():
        raise FileNotFoundError(safe)
    return json.loads(path.read_text(encoding="utf-8"))


def cases_index() -> list[dict[str, Any]]:
    """用例表：给页面先看"要考什么"，再按按钮跑。

    返回黄金集的行列表：``id`` / ``question`` / ``expect`` / ``expected_docs`` 之外，
    还带上工牌的 ``actor_name`` 与 ``reference``——页面上要显示"这题是谁在问、
    标准答案是什么"，不该逼着人拿 ``user_id`` 去对照身份表。
    """
    rows = []
    for case in GOLDEN_SET:
        actor = resolve_actor(case.get("user_id"))
        rows.append({
            "id": case.get("id") or case["question"][:12],
            "question": case["question"],
            "expect": case.get("expect") or "answer",
            "expected_docs": list(case.get("expected_docs") or []),
            "user_id": actor.user_id,
            "actor_name": actor.display_name,
            "reference": case.get("reference") or "",
        })
    return rows
