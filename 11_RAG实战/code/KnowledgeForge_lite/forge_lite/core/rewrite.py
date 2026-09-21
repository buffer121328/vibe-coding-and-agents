"""rewrite.py —— 查询重写：原问题必须保留 + 本地规则拆主题（完整版同款）。

蒸馏来源：完整版 services/qa/query.py（classify_intent_local + rewrite_query_local）。
对应教程：11.6（Multi-Query 护栏 / 多跳信号）。

完整版这条故意不用模型：改写要可复现、可测、不把幻觉塞进检索入口。
Lite 默认走同一套本地规则；只有显式传入 llm 时才再追加一句「制度检索腔」。
总装只装三块最值钱的保险：
1. 改写后的查询必须和原问题一起检索（`merge_queries`），避免数字/否定词被改丢；
2. 顿号枚举主题时拆成「主题 + 制度」子查询，分头召回再由 RRF 融合（完整版同款）；
3. 多跳信号只做提示，不在这里拆成子图（拆解是进阶，不是基本功能）。
"""

from __future__ import annotations

import re


def merge_queries(original: str, rewrites: list[str], limit: int = 4) -> list[str]:
    """始终把用户原问题放在第一位；改写只追加，不替换（11.6 改写护栏）。

    ``original`` 是用户原话，``rewrites`` 是各路改写结果（顺序即优先级，靠前的先入选）。
    ``limit`` 是融合后的条数上限：每多一条就多一路召回、多一份延迟，默认 4 是
    "覆盖够用又不至于把检索拖成串行"的折中。

    改写最大的风险是把关键数字、否定词改丢（"不超过 3 天"改成"出差天数规定"），
    原问题永远留在第一位就是那条回退绳——即使改写全错，至少还能按原话召回一次。
    返回去重（按空白归一化后比较）且截到 ``limit`` 条的查询列表；全被过滤空时
    兜底返回 ``[original]``，绝不返回空列表让检索静默干跑。
    """
    merged, seen = [], set()
    for query in [original, *rewrites]:
        normalized = " ".join((query or "").split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)
        if len(merged) >= limit:
            break
    return merged or [original]


def should_decompose(question: str) -> bool:
    """简单的多跳信号。真实系统要用评测集校准分类器，这里只作提示。

    ``question`` 是用户原问题。判据两条：句子长（超过 45 字，通常塞了不止一个问题），
    或者出现两个以上连接词（"先……再……"、"分别"、"比较"这类串场词）。

    只给提示、不在这里拆子查询：拆解要靠靠谱的规划器，规则硬拆容易把一句话劈成
    两个都不完整的问句，召回反而更差。返回 True 表示"这题可能要多跳"，由上游决定
    是加提示、多召回几路，还是留到进阶版处理。
    """
    connectors = ("分别", "比较", "先", "再", "以及", "同时", "之间", "为什么又")
    return len(question) > 45 or sum(token in question for token in connectors) >= 2


def classify_intent_local(question: str) -> str:
    """规则意图分类（完整版 QueryIntent 的课堂版）。生成侧可用来选拒答话术。

    ``question`` 是用户原问题，大小写不敏感（"VS" 和 "vs" 算同一个信号）。
    返回五个意图字符串之一：``comparative``（比大小找差异）、``procedural``（问怎么做）、
    ``analytical``（问为什么、要解释）、``exploratory``（要列表、要概述），
    都不匹配则回落 ``factoid``（问一个具体事实）——它是兜底而不是第五类信号，
    所以永远不抛异常，也永远有返回值。

    用关键词而不是模型：拒答话术要在 500ms 内选出来，且分类器抽风不该让问答崩掉。
    """
    rules = (
        ("comparative", ("区别", "对比", "相比", "不同", "vs", "versus")),
        ("procedural", ("怎么做", "怎么处理", "怎么办", "如何", "步骤", "流程", "怎样")),
        ("analytical", ("为什么", "原因", "怎么理解", "为何")),
        ("exploratory", ("有哪些", "概述", "介绍一下", "列出", "哪些")),
    )
    lowered = question.lower()
    for intent, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "factoid"


def rewrite_query_local(question: str) -> dict:
    """本地改写，不调模型。思想对齐完整版 rewrite_query_local：

    - 原问题永远第一位；
    - 抽实体词拼成一条关键词查询；
    - 顿号枚举主题（「招聘、培训和绩效考核……」）再为每个主题补「主题 + 制度」。

    ``question`` 是用户原问题。不求全：把「招聘、培训、考核」这类顿号枚举拆成
    三条独立查询，是因为一整句丢给 BM25 时三个主题会互相稀释关键词；补「制度」
    二字则是把口语问法往企业文档的用词上靠，让词面召回也有机会命中。

    返回 ``{"queries": [...], "entities": [...], "intent": "..."}``：``queries`` 是
    最多 4 条候选查询（原问题在第一），``entities`` 是抽出的实体词（供调试与解释），
    ``intent`` 是 ``classify_intent_local`` 的判定结果。只读不改，同一问题必得同一份结果。
    """
    tokens = [
        token for token in re.split(r"[\s，。？?！!、；;：:（）()【】\[\]\"']+", question) if token
    ]
    stop_words = {"是什么", "什么", "怎么", "如何", "为什么", "哪些", "有没有", "吗", "呢", "的", "了", "和", "与"}
    entities = [token for token in tokens if len(token) >= 2 and token not in stop_words][:5]
    queries = [question]
    if entities:
        joined = " ".join(entities)
        if joined != question:
            queries.append(joined)
    if "、" in question:
        segments = [segment.strip() for segment in question.split("、")]
        topics: list[str] = []
        for segment in segments:
            has_predicate = any(
                marker in segment
                for marker in ("什么", "哪些", "如何", "怎么", "为什么", "能否", "是否", "何时")
            )
            topic_part = segment
            if has_predicate:
                match = re.search(r"(?:能否|如何|哪些|什么|怎么|是否|何时|为什么)", segment)
                topic_part = segment[: match.start()] if match else ""
            for token in re.split(r"[和与]", topic_part):
                token = token.strip(" ，,。？?！!；;：:")
                if 2 <= len(token) <= 12 and token not in topics:
                    topics.append(token)
            if has_predicate:
                break
        for topic in topics[:3]:
            candidate = f"{topic} 制度要求"
            if candidate not in queries:
                queries.append(candidate)
    return {"queries": queries[:4], "entities": entities, "intent": classify_intent_local(question)}


def expand_queries(question: str, llm=None) -> list[str]:
    """默认走本地规则；有模型时再追加一句制度检索腔。失败回退，改写不能变成单点故障。

    ``question`` 是用户原问题。``llm`` 是可选的 LangChain 模型对象，传 None（默认）
    就纯走本地规则——本地规则已是完整可用的一条路，模型只是锦上添花。传了模型就用
    ``invoke`` 追加一句更适合检索企业制度的说法，末尾仍与本地改写一起过 ``merge_queries``。

    模型超时、报错、返回空串都不算失败路径的终点：捕获后打一行 ``[改写降级]`` 就
    退回本地结果。改写只是检索的前置动作，让它变成整条链路的单点故障是不划算的。
    返回最多 4 条查询、原问题在第一位。
    """
    local = rewrite_query_local(question)
    extras = list(local["queries"][1:])
    if llm is None:
        return merge_queries(question, extras, limit=4)
    try:
        resp = llm.invoke(
            "把下面的口语化问题改写成一句适合检索企业制度文档的中文查询。"
            "必须保留关键数字、否定词和时间；只输出查询本身，不要编号、不要解释。\n"
            f"问题：{question}"
        )
        text = (getattr(resp, "content", None) or str(resp)).strip()
        line = next((ln.strip().strip("*#`").strip() for ln in text.splitlines() if ln.strip()), "")
        line = line.lstrip("0123456789.、- ").strip()
        if line:
            extras.append(line)
        return merge_queries(question, extras, limit=4)
    except Exception as exc:  # 改写失败不能拖死问答
        print(f"[改写降级] 本次只用本地规则：{exc}")
        return merge_queries(question, extras, limit=4)
