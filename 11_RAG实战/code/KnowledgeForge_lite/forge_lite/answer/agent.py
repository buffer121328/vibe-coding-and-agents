"""agent.py —— LangGraph 自省闭环：改写 → 检索 → 分级 → 引用生成 → 校验 → 复检。

蒸馏来源：完整版 agents/qa_agent + qa_query/qa_generation + workflows QA 编排。
对应教程：11.6（查询改写护栏）、11.8（CRAG 分级 + 自我校正闭环）、11.12（四道闸门）。
教学版把完整版的“联网兜底/知识更新”节点省掉，检索与完整版同构：先裁工牌再三路融合。
自省重试受 RunBudget 硬限制：每个质量关卡只给 1 次机会，绝不带病交付。
"""

from typing import Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from .. import config
from ..llm import llm          # 全模块共用这一个客户端，别自己建
from ..retrieve.citation import CITE_PROMPT, REFUSAL, Source, check_citations, format_sources
from ..store.conversations import ConversationError, get_store
from ..core.evidence import qualify, status_label
from ..core.identity import Actor, resolve_actor
from ..core.labels import intent_text
from ..core.quality import RunBudget, mask_pii
from ..retrieve.search import hybrid_search
from ..core.rewrite import classify_intent_local, expand_queries, should_decompose

class Grade(BaseModel):
    """检索结果与问题的相关性分级（CRAG 思想，教程 11.8）。

    ``relevant`` 是"这批资料里到底有没有能回答问题的信息"这个判断本身，它直接决定
    生成那一关跑不跑；``reason`` 是一句话理由，会被拼进 ``warn`` 一起落盘——
    拒答必须写清是哪道闸门拦的，否则课堂上看就是"机器坏了"。
    """

    relevant: bool = Field(description="资料里是否包含能回答问题的信息")
    reason: str = Field(description="一句话理由")


class FaithCheck(BaseModel):
    """生成答案的忠实度复检（教程 11.9/11.12 的裁判）。

    ``faithful`` 是逐句核对后的总判定：答案每个陈述是否都能在资料里找到依据；
    ``bad_spans`` 装的是被判无依据的句子原文（没有则空列表），会被原样拼进 ``warn``——
    这里刻意收原文而不是角标编号，是为了让课堂上能一眼看出模型编了哪一句。
    """

    faithful: bool = Field(description="答案每个陈述是否都能在资料中找到依据")
    bad_spans: list[str] = Field(default_factory=list, description="无依据的句子，没有则空列表")


class State(TypedDict):
    """在六个节点之间传阅的共享状态包：每个节点读几个键、再整包覆盖写回几个键。

    入口 ``ask`` 只塞起始字段（``question`` / ``budget`` / ``warn`` / ``user_id`` 等），
    其余键由节点跑一步补一步，所以节点里读状态一律用 ``.get()`` 兜底，
    别假设某个键一定存在——图可以从半途重入，评测也可能只喂一部分。

    - ``question`` 用户原问题，全程不被覆盖（改写只动 ``queries``）；
    - ``queries`` 真正拿去检索的查询列表，第 0 条永远是原问题；
    - ``sources`` 授权裁剪后命中的资料块（``Source`` 对象，带回落映射用的 ``doc_id``）；
    - ``answer`` 生成中的答案正文；被打回重生成时清空重来；
    - ``citations`` 校验通过的角标回映射结果，拒答时清空；
    - ``attempts`` 已重试次数，轨迹面板的"预算与重试"那一步读它（教程 10.11 熔断思想）；
    - ``budget`` 本次问答的预算票箱，检索与改写各扣一次票；
    - ``status`` 三态信号：``ok`` 放行、``refuse`` 收摊拒答、``regen`` 打回重生成；
    - ``warn`` 面向课堂的累计提示（哪道闸门拦的、哪一路降级了），落盘前会过脱敏；
    - ``user_id`` 提问人的工牌 id，检索裁剪和落盘归属都认它；
    - ``intent`` 本地规则判出的意图键，供前端显示和评测分组；
    - ``routes`` 本次实际走通的检索通道，形如 ``bm25+dense+graph``；
    - ``evidence`` 证据资格结论（``EvidenceQualifier`` 的 ``as_dict()``）；
    - ``source_details`` 每块的各路名次：去哪一路第几名、融合后第几名。
    """

    question: str
    queries: list[str]
    sources: list[Source]
    answer: str
    citations: list[dict]
    attempts: int          # 已重试次数（防死循环，教程 10.11 熔断思想）
    budget: RunBudget
    status: Literal["ok", "refuse", "regen"]
    warn: str
    user_id: str
    intent: str
    routes: str
    evidence: dict
    source_details: list[dict]   # 每块的各路名次：去哪一路第几名、融合后第几名


def n_rewrite(state: State) -> State:
    """⓪ 查询改写（11.6）：原问题必须保留；本地规则为主，模型扩写为辅。

    ``state`` 里只读 ``question``（以及可能已有的 ``warn`` 用来累积提示）。返回整包覆盖后的
    新 state：``queries`` 换成检索用的查询列表，``intent`` 打上本地意图标签，
    多跳信号写进 ``warn`` 但不改变行为——教学版仍按单轮检索。

    原问题一个字都不动：改写只能往后追加说法，不能顶替原问题，
    否则扩写一旦跑偏，连个能回退的锚点都没了。
    """
    question = state["question"]
    queries = [question]
    if config.ENABLE_REWRITE:
        queries = expand_queries(question, llm)
    warn = state.get("warn") or ""
    if should_decompose(question):
        warn = (warn + " 本题含多跳信号，教学版仍按单轮检索，生产可拆成子查询。").strip()
    return {**state, "queries": queries, "intent": classify_intent_local(question), "warn": warn}


def n_retrieve(state: State) -> State:
    """① 检索：授权裁剪后的三路召回（向量 + BM25 + 图谱）进同一套 RRF。

    ``state`` 里读 ``question`` / ``queries`` / ``user_id`` / ``budget``。检索同样要扣预算票：
    票不够就不往下走，直接置成拒答——与其拿着半份资料硬答，不如老实说资料不足。
    工牌在检索**之前**换成交付给 ``hybrid_search`` 的 ``actor``，先裁库再打分（11.13）。

    返回整包覆盖后的新 state，额外写入 ``sources`` / ``routes`` / ``evidence`` /
    ``source_details``，并把 ``attempts`` 归零：这是新一轮的起点，上一轮的重试计数
    不该记在它头上。
    """
    budget = state.get("budget") or RunBudget()
    if not budget.consume("retrieval"):
        return {**state, "sources": [], "status": "refuse", "answer": REFUSAL,
                "budget": budget, "citations": []}
    actor = resolve_actor(state.get("user_id"))
    hits = hybrid_search(state.get("queries") or [state["question"]], actor=actor)
    sources = [Source(doc_id=f"{h['source']}#{h['chunk_index']}",
                      text=h["text"], why=h.get("why", ""))
               for h in hits]
    # 路由取「单条通道」的并集：命中的 route 字段是 "bm25+dense" 这样的组合串，
    # 直接拿整串去重会得到 "bm25+dense+bm25+dense+graph" 这种重复徽章。
    lanes: set[str] = set()
    for hit in hits:
        for lane in str(hit.get("route") or "hybrid").split("+"):
            if lane.strip():
                lanes.add(lane.strip())
    routes = "+".join(sorted(lanes)) if hits else ""
    warn = state.get("warn") or ""
    if any(h.get("degraded") == "graph_unavailable" for h in hits):
        warn = (warn + " 图谱一路降级，本次只融合向量和 BM25。").strip()
    evidence = qualify(state["question"], hits)
    # 落盘用的检索明细：轨迹面板要靠它画「三路各召回第几名」，
    # 刷新后从会话柜恢复也能还原，不用重跑检索（11.5 可解释检索）。
    source_details = [{
        "doc_id": f"{hit['source']}#{hit['chunk_index']}",
        "source": hit["source"],
        "chunk_index": hit.get("chunk_index", 0),
        "route": hit.get("route") or "",
        "route_rank": int(hit.get("route_rank") or 0),
        "fused_rank": int(hit.get("fused_rank") or 0),
        "why": hit.get("why") or "",
    } for hit in hits]
    return {**state, "sources": sources, "attempts": 0, "status": "ok",
            "citations": [], "budget": budget, "routes": routes, "warn": warn,
            "evidence": evidence.as_dict(), "source_details": source_details}


def n_grade(state: State) -> State:
    """② 分级：资料里压根没有答案就别硬答（11.8 CRAG / 11.12 拒答）。

    ``state`` 里读 ``question`` / ``sources`` / ``evidence``，写回 ``status`` / ``answer`` /
    ``warn``。完整版在生成前先跑 EvidenceQualifier。Lite 同步：资格不够直接拒答，
    不把『有点像』交给生成模型去圆。部分证据仍放行，但会把缺的槽位写进 warn。

    资格已经说「够答 / 部分答」时，**不再让模型一票否决**。课堂黄金集里「打印机
    E3」那条，资料明明写着处理步骤，模型分级却会偶尔判不相关——同一道题两次跑、
    一次过一次挂，门禁就没法当门禁用。CRAG 的模型分级只在资格没结论时当兜底
    （没跑过 ``qualify`` 的老路径、测试替身）。

    返回的 state 只有 ``status`` 是 ``ok`` 时才会流向生成：这一关不过，
    后面三道闸门连跑的机会都没有——它是最便宜的一道，所以放在最前面拦。
    """
    evidence = state.get("evidence") or {}
    if evidence and not evidence.get("allows_generation", True):
        reason = status_label(str(evidence.get("response_status") or "refuse"))
        missing = evidence.get("missing_information") or []
        extra = "；".join(item.get("description") or "" for item in missing if item)
        warn = (state.get("warn") or "")
        warn = (warn + f" 证据资格：{reason}" + (f"（{extra}）" if extra else "")).strip()
        return {**state, "status": "refuse", "answer": REFUSAL, "warn": warn}
    if not state["sources"]:
        return {**state, "status": "refuse", "answer": REFUSAL}
    # 资格已经放行：模型分级不许再把该答的题拦下来。
    if evidence.get("allows_generation"):
        return {**state, "status": "ok"}
    g = llm.with_structured_output(Grade).invoke(ChatPromptTemplate.from_template(
        "问题：{q}\n资料：\n{s}\n判断资料是否包含回答该问题所需的信息。"
    ).format(q=state["question"], s=format_sources(state["sources"])))
    if not g.relevant:
        # 拒答必须写清是哪道闸门拦的：静默拒答在课堂上等于「机器坏了」
        warn = (state.get("warn") or "") + f" 分级判定资料与问题不相关（{g.reason}），已拒答。"
        return {**state, "status": "refuse", "answer": REFUSAL, "warn": warn.strip()}
    return {**state, "status": "ok"}


def n_generate(state: State) -> State:
    """③ 生成：接地 Prompt + 引用标注。

    ``state`` 里读 ``question`` 与 ``sources``，把模型的返回正文原样写进 ``answer``。
    这一关不做任何校验（校验是下一关的事），重生成也是回到这里：
    ``check`` / ``verify`` 打回时只置 ``status="regen"`` 并清空旧答案，
    靠同一条入边再进一次。
    """
    resp = llm.invoke(CITE_PROMPT.format(
        numbered_sources=format_sources(state["sources"]), question=state["question"]))
    return {**state, "answer": resp.content}


def n_check(state: State) -> State:
    """④ 程序校验：幽灵引用/拒答话术 → 有机会就重生成一次。

    ``state`` 里读 ``answer`` / ``sources`` / ``budget``，写回 ``status`` / ``citations`` /
    ``warn``。模型自己写的「【资料不足】」在这里被翻译成统一的 ``REFUSAL`` 话术——
    前端只需认一种拒答写法，不必猜模型这轮换了什么说法。

    校验不过时先看预算：``rewrite`` 票还有就退回重生成（``status="regen"``，顺手清空答案），
    票用完就拒答。同一个缺陷只给一次改正机会，给了第二次它就敢每次都赌第三次。
    """
    from ..retrieve.citation import build_citations
    if state["answer"].startswith("【资料不足】"):
        return {**state, "status": "refuse", "answer": REFUSAL}
    ok, _ = check_citations(state["answer"], len(state["sources"]))
    if not ok:
        budget = state.get("budget") or RunBudget()
        if budget.consume("rewrite"):
            return {**state, "attempts": state.get("attempts", 0) + 1, "status": "regen",
                    "citations": [], "answer": "", "budget": budget,
                    "warn": (state.get("warn") or "") + " 引用格式不合格，已重生成一次。"}
        warn = (state.get("warn") or "") + " 引用格式连续不合格，已拒答（不带病交付）。"
        return {**state, "status": "refuse", "answer": REFUSAL, "citations": [],
                "budget": budget, "warn": warn.strip()}
    return {**state, "status": "ok",
            "citations": build_citations(state["answer"], state["sources"])}


def n_verify(state: State) -> State:
    """⑤ 忠实度复检：首次不过可重生成一次，再不过就拒答，绝不带病交付。

    ``state`` 里读 ``sources`` / ``answer`` / ``citations`` / ``budget`` / ``status``。
    已经有结论是 ``refuse`` 的直接原样放行，不白花一次裁判调用；没有角标的答案
    （纯拒答话术）也不送裁判，顺带避开"空答案被判不忠实"的假阳性。

    复检与引用校验**共用同一张 rewrite 票**，所以整条链路最多重生成一次，
    不会出现"引用放行一次、忠实度又放行一次"的双份宽容。
    """
    if state.get("status") == "refuse":
        return state
    if state.get("citations"):
        budget = state.get("budget") or RunBudget()
        check = llm.with_structured_output(FaithCheck).invoke(ChatPromptTemplate.from_template(
            "资料：\n{s}\n答案：{a}\n逐句检查答案是否有资料外编造的内容。"
        ).format(s=format_sources(state["sources"]), a=state["answer"]))
        if not check.faithful:
            # 复检失败与引用校验共用 rewrite 预算：整条链路只许重写一次
            if budget.consume("rewrite"):
                return {**state, "attempts": state.get("attempts", 0) + 1, "status": "regen",
                        "warn": f"首次复检发现无依据表述：{check.bad_spans}",
                        "budget": budget}
            return {**state, "status": "refuse", "answer": REFUSAL,
                    "citations": [], "warn": f"复检失败：{check.bad_spans}",
                    "budget": budget}
        return {**state, "status": "ok", "warn": state.get("warn") or "", "budget": budget}
    return {**state, "status": "ok", "warn": state.get("warn") or ""}


def route_after_grade(state: State) -> Literal["generate", "end"]:
    """分级后的岔路口：``refuse`` 直接收摊，其余去生成。

    ``state`` 只看 ``status``，而且用 ``get`` 兜住缺键——这一关的职责是拦人，
    不该因为状态包不完整就把正常问题误拦下来（缺键当"没拒答"处理）。
    返回下一个节点名：``"end"`` 或 ``"generate"``。
    """
    return "end" if state.get("status") == "refuse" else "generate"


def route_after_check(state: State) -> Literal["generate", "verify", "end"]:
    """引用校验后的三岔口：拒答收摊、重生成回炉、通过则去复检。

    ``state`` 只看 ``status``：``refuse`` → ``end``，``regen`` → ``generate``，
    其余（``ok``）→ ``verify``。分成三态而不是两态，是因为"打回重写"和"通过"
    必须能和"被拦下"区分开——两态会逼着调用方从 ``attempts`` 反推这轮到底发生了啥。
    返回下一个节点名。
    """
    if state.get("status") == "refuse":
        return "end"
    return "generate" if state.get("status") == "regen" else "verify"


def route_after_verify(state: State) -> Literal["generate", "end"]:
    """复检后的岔路口：还有票就回炉重生成，否则无论成败都收摊。

    ``state`` 只看 ``status``：``regen`` → ``generate``，其余一律 ``end``。
    这里读的是必填键而不是 ``.get()``：能走到复检说明前面几关都填过它，
    真缺了就是图接错了，当场报错好过默默收摊。返回下一个节点名。
    """
    return "generate" if state["status"] == "regen" else "end"


def build_graph():
    """把六个节点和三条条件边接成 LangGraph，编译成可 ``invoke`` 的图。

    为什么这么分岔（教程 11.12 的四道闸门）：

    - 分级不过 → ``end``：「不在资料里硬答」是产品底线，而这一关最便宜（不用生成），
      所以放在生成之前先拦；
    - 引用校验不过 → ``generate``：幽灵引用是格式病，值得一次重写；
    - 复检不过 → ``generate``：忠实度是事实病，同样只给一次重写；
    - 两次重写共用同一张 ``rewrite`` 票（``RunBudget``），所以"引用放一次、复检再放一次"
      的连环宽容不会发生——每个关卡各给一次机会，加起来最多重生成一回。

    另有一处刻意安排：检索扣不到预算票时直接把状态置成拒答，而不是抛异常——
    拒答是正常业务分支，用异常表达会把降级路径挤进 ``except`` 里看不清。

    返回编译好的图对象；模块导入时调用一次，``ask`` 复用同一张图。
    """
    g = StateGraph(State)
    g.add_node("rewrite", n_rewrite)
    g.add_node("retrieve", n_retrieve)
    g.add_node("grade", n_grade)
    g.add_node("generate", n_generate)
    g.add_node("check", n_check)
    g.add_node("verify", n_verify)
    g.set_entry_point("rewrite")
    g.add_edge("rewrite", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route_after_grade, {"generate": "generate", "end": END})
    g.add_edge("generate", "check")
    g.add_conditional_edges(
        "check", route_after_check,
        {"generate": "generate", "verify": "verify", "end": END},
    )
    g.add_conditional_edges("verify", route_after_verify, {"generate": "generate", "end": END})
    return g.compile()


graph = build_graph()


def ask(
    question: str,
    user_id: str | Actor | None = None,
    conversation_id: str | None = None,
    persist: bool = True,
) -> dict:
    """对外唯一入口：返回带工牌、三路路由、引用和会话柜编号的问答结果。

    ``question`` 是用户原问题，也是新会话默认标题的来源；``user_id`` 是提问人的工牌，
    传 id 字符串或 ``Actor`` 都行，不传则退回 ``config.DEFAULT_USER_ID``——它一处两用：
    决定检索能看见哪些文档，也决定这条记录写进谁的会话。``conversation_id`` 是续聊的会话号，
    必须属于这张工牌，否则当作没传、新开一格——指针不是权限。``persist`` 传 True（默认）
    就写入会话柜（完整版 history_saved）；评测脚本传 False 关落盘，避免黄金集把 runtime
    会话柜刷脏。

    contexts 是本次检索到的资料原文列表——评估框架（Ragas）需要它算 context 指标，
    前端做“点角标跳原文”也用它，一处生产、多处消费。

    返回的是扁平字典而不是 ``State``：除 ``answer`` / ``citations`` / ``status`` / ``warn`` 外，
    还带 ``actor``（工牌四件套）、``intent_label``（中文意图标签，刷新后不该退回英文键名）、
    ``response_status``（最终结论——资格说「够答」但被引用或复检闸门半路拦下时会改判为
    ``insufficient_evidence``，前端照它显示徽章）以及 ``conversation_id`` / ``run_id`` /
    ``history_saved``；``persist=False`` 时后三个留空。

    ``question`` 为空串且 ``persist=True`` 时抛 ``ConversationConflict``：
    落盘那一步先校验问句，宁可当场报错也不留下半条空消息。
    """
    actor = resolve_actor(user_id or config.DEFAULT_USER_ID)
    result = graph.invoke({
        "question": question, "budget": RunBudget(), "warn": "",
        "user_id": actor.user_id, "intent": "", "routes": "",
        "evidence": {}, "source_details": [],
    })
    result["contexts"] = [s.text for s in result.get("sources", [])]
    payload = {k: result.get(k) for k in (
        "question", "answer", "citations", "status", "warn", "contexts", "queries",
        "user_id", "intent", "routes", "evidence", "source_details")}
    payload["actor"] = {
        "user_id": actor.user_id, "name": actor.display_name,
        "role": actor.role, "department": actor.department,
    }
    payload["evidence"] = result.get("evidence") or {}
    # 意图给中文标签一起落盘：刷新后从会话柜恢复的消息不该退回英文键名
    payload["intent_label"] = intent_text(payload.get("intent") or "")
    # 资格结论与实际结局必须一致：资格说「够答」但引用/复检闸门半路拒答时，
    # 不能仍挂着「已回答」的徽章——前端照 status 显示最终结论，把资格留给轨迹页。
    evidence_status = (payload["evidence"] or {}).get("response_status")
    if payload.get("status") == "refuse":
        payload["response_status"] = "insufficient_evidence"
    else:
        payload["response_status"] = evidence_status or "answered"
    payload["response_label"] = (
        status_label("refuse") if payload.get("status") == "refuse"
        else status_label(str(payload.get("response_status") or payload.get("status") or ""))
    )
    # 日志侧脱敏：答案里若误带电话/邮箱，不原样落盘（11.13）
    if payload.get("warn"):
        payload["warn"] = mask_pii(payload["warn"])
    payload["conversation_id"] = conversation_id or ""
    payload["run_id"] = ""
    payload["history_saved"] = False
    if persist:
        store = get_store()
        owned_id = conversation_id or None
        if owned_id:
            try:
                store.get_conversation(owned_id, actor.user_id)
            except ConversationError:
                owned_id = None
        conv_id, run_id = store.record_answer(
            actor.user_id, question, payload, conversation_id=owned_id,
        )
        payload["conversation_id"] = conv_id
        payload["run_id"] = run_id
        payload["history_saved"] = True
    return payload


if __name__ == "__main__":
    import json
    print(json.dumps(ask("去上海出差住一晚能报多少？"), ensure_ascii=False, indent=2))
