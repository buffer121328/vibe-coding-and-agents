"""quality.py —— 从分节课搬进总装的纯函数零件（不调模型、不访问网络）。

对应教程：
- 11.5  加权 `reciprocal_rank_fusion`（图谱 1.05）/ `pack_contexts` / `order_contexts` / `explain_retrieval`
- 11.9  `citation_metrics`（格式门禁，不声称语义蕴含）
- 11.8  `RunBudget`（自省闭环熔断）
- 11.13 `scan_poisoning` / `mask_pii`

教学版把这些函数收拢到一处，入库、检索、引用、自省都走同一份实现，
避免“课上一种算法、总装里又手写一份”的静默分叉。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


# 与完整版 services/qa/ranking._DEFAULT_SOURCE_WEIGHTS 同构：图谱略加权。
SOURCE_WEIGHTS: dict[str, float] = {
    "vector": 1.0,
    "dense": 1.0,
    "bm25": 1.0,
    "graph": 1.05,
    "hybrid": 1.0,
}


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    rank_constant: int = 60,
    weights: Sequence[float] | None = None,
) -> list[tuple[str, float]]:
    """手写 RRF：只看名次不看绝对分数。同一列表内的重复 ID 只计第一次（11.5）。

    ``rankings`` 是各路召回结果，内层列表按名次从高到低排；哪一路排前面不参与计分，
    只有内层下标算名次。``rank_constant`` 是名次平滑项：它越大，前几名之间的分差越小，
    冷门路也更容易挤进融合榜——默认 60 是原论文的量级，调到 0 就退化成"第一名通吃"。
    ``weights`` 与 ``rankings`` 等长，对应完整版按来源加权（图谱 1.05）；不传则每路 1.0。

    返回 ``[(doc_id, 融合分)]``，按分数降序、同分再按 id 字典序排——考研据可复现，
    同分不能靠字典遍历顺序碰运气。``rank_constant`` 为负数或 ``weights`` 与
    ``rankings`` 不等长时抛 ``ValueError``，宁可当场报错也别静默按缺省权重重算。
    """
    if rank_constant < 0:
        raise ValueError("rank_constant 不能为负数")
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("weights 必须与 rankings 等长")
    scores: dict[str, float] = {}
    for index, ranking in enumerate(rankings):
        weight = 1.0 if weights is None else float(weights[index])
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranking, 1):
            if doc_id in seen:
                continue
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (rank_constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def _token_set(text: str) -> set[str]:
    """切出给 Jaccard 用的词袋：英文按整词、中文按**单字**。

    ``text`` 是要切分的原文（大小写不敏感）。中文按单字切是教学版的有意取舍：
    不引分词库，且近重复判定只看"字重不重合"，切粗一点反而更宽容。
    返回去重后的 token 集合，空文本得到空集。
    """
    return set(re.findall(r"[a-zA-Z0-9_.-]+|[\u4e00-\u9fff]", text.lower()))


def deduplicate_contexts(texts: Sequence[str], threshold: float = 0.85) -> list[str]:
    """按 Jaccard 相似度去掉近重复上下文，保留先出现的版本（11.5）。

    ``texts`` 是待去重的上下文（顺序就是优先级，先来的先留下）。``threshold`` 是
    相似度红线，取 0 到 1：达到或超过就算重复。定得太低会误杀"同一制度的不同条款"，
    太高则放过改写过的重复段——默认 0.85 是课堂试出来的折中。``threshold`` 越界抛
    ``ValueError``：这类参数写错只是手误，不该悄悄按 0 或 1 跑出一份看着正常的清单。

    返回去重后的文本列表，只做过滤不重排，调用方拿到的相对次序与传入一致。
    """
    if not 0 <= threshold <= 1:
        raise ValueError("threshold 必须在 0 到 1 之间")
    kept: list[str] = []
    signatures: list[set[str]] = []
    for text in texts:
        signature = _token_set(text)
        duplicate = False
        for previous in signatures:
            union = signature | previous
            similarity = len(signature & previous) / len(union) if union else 1.0
            if similarity >= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(text)
            signatures.append(signature)
    return kept


def pack_contexts(texts: Sequence[str], max_chars: int = 1800) -> list[str]:
    """先去近重复，再按字符预算装箱（11.5）。生产应改用 tokenizer 计 token。

    ``texts`` 是候选上下文，装箱顺序即优先级（重要的放前面，先到先占预算）。
    ``max_chars`` 是字符总预算，装不下的整块跳过而不是截半句——半句话进 Prompt
    比少一句话更坏，模型会照着残缺的条文编。返回装进预算的那些块，相对次序不变。
    """
    packed, used = [], 0
    for text in deduplicate_contexts(texts):
        if used + len(text) > max_chars:
            continue
        packed.append(text)
        used += len(text)
    return packed


def order_contexts(scored: list[tuple[str, float]]) -> list[str]:
    """把最相关的放首尾，对抗 lost-in-the-middle（11.5 / Lost in the Middle）。

    ``scored`` 是 ``[(doc_id, 分数)]``，分数越大越相关。榜首要占开头（模型看得最认真），
    榜眼占结尾（离问题最近），剩下的按分数升序塞中间——次相关的越靠中间越容易被忽略，
    这是故意的：反正它们本来就最不该被引用。返回排好序的 doc_id 列表。
    """
    if not scored:
        return []
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)
    if len(ranked) <= 2:
        return [doc_id for doc_id, _ in ranked]
    head = ranked[0][0]
    tail = ranked[1][0]
    middle = [doc_id for doc_id, _ in sorted(ranked[2:], key=lambda item: item[1])]
    return [head, *middle, tail]


def explain_retrieval(hits: list[dict]) -> list[dict]:
    """给每条命中补上“为什么是它”，并提醒各路分数不可直接比大小（11.5）。

    ``hits`` 是检索命中的原始字典列表，每条至少要带 ``route``（哪一路召回）、
    ``rank``（该路第几名），可选 ``fused_rank``（融合后第几名）。缺字段的按 "-" / 0
    兜底，前端不会因为少一个键就白屏。

    返回补过字段的**新字典**列表（原 ``hits`` 不动，便于对照排查）。每条多出两样东西：
    ``why`` 是给人看的中文理由，``is_confidence_comparable`` 恒为 False——它是一块
    写死的警示牌：BM25 分数和余弦相似度量纲不同，跨路比大小是新手最容易踩的坑，
    前端看到这个字段就该放弃"按分数排序、置信度一眼看高低"的做法。
    """
    explained: list[dict] = []
    for hit in hits or []:
        record = dict(hit)
        route = hit.get("route", "-") or "-"
        rank = hit.get("rank", 0) or 0
        fused = hit.get("fused_rank")
        fused_text = fused if fused is not None else "-"
        record["why"] = f"被 {route} 召回（该路第 {rank} 名），融合后第 {fused_text} 名"
        record["is_confidence_comparable"] = False
        explained.append(record)
    return explained


# 按「整句」切：分号常用来连接同一句里的并列小句（列表项尤其常见），
# 拿它当句子边界会把「重新上电；仍报错找行政部报修 [1]」切出半条无引用的假违规。
CLAIM_SPLIT = re.compile(r"(?<=[。！？!?])\s*|\n+")
CITATION = re.compile(r"\[(\d+)\]")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
# 以冒号结尾的行是「引出下文」（**处理步骤如下：**、……方法如下：），不是陈述句。
# 不排除它们，每条列表答案的引言都会被判成「无引用的陈述」。
_LABEL_ONLY = re.compile(r"^\s*(?:\*\*[^*]*[:：]\*\*|.{0,40}[:：])\s*$")
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.、)])\s*")


def extract_claims(answer: str) -> list[str]:
    """挑出「需要带引用的陈述句」。

    标题和纯标签不是陈述句：``## 处理步骤``、``**故障原因**：`` 这类行没有可引用的
    内容，把它们算成「没标出处的陈述」会让合规答案被门禁误杀（课堂版按行切句，
    完整版走结构化 claims，不存在这一步）。

    ``answer`` 是模型产出的原答案；空串、None 都当"没有陈述"处理，返回空列表。
    返回值是切分后的句子列表，即后面 ``citation_metrics`` 算完整率时的分母。
    """
    claims: list[str] = []
    for part in CLAIM_SPLIT.split(answer or ""):
        text = part.strip()
        if not text or len(text) <= 2:
            continue
        if _HEADING.match(text) or _LABEL_ONLY.match(text):
            continue
        if "资料不足" in text or "转人工" in text:
            continue
        claims.append(text)
    return claims


def citation_metrics(answer: str, source_count: int) -> dict[str, object]:
    """幽灵引用 + 有陈述却没标来源。只做格式门禁，不做语义蕴含（11.9 / 11.12）。

    ``answer`` 是待校验的答案原文，``source_count`` 是这次提供给模型的资料条数——
    角标超过它就是幽灵引用。只查"标了没标、越没越界"，不查"标的那条是否真支持这句话"：
    后者要语义蕴含，得另上模型，课堂版不做假把式。

    返回一个扁平字典，字段含义：``valid_source_ids`` / ``invalid_source_ids`` 分别是
    合规与越界角标（去重升序），``claim_count`` 是陈述句总数，``cited_claim_count`` 是
    其中带了角标的数量，``citation_completeness`` 是两者的比值（没有陈述句时记 1.0，
    纯拒答不算不完整），``format_passed`` 是门禁总判：没有越界角标，且陈述句都标了出处。
    """
    cited = [int(value) for value in CITATION.findall(answer)]
    valid = sorted({value for value in cited if 1 <= value <= source_count})
    invalid = sorted({value for value in cited if value < 1 or value > source_count})
    claims = extract_claims(answer)
    cited_claims = sum(bool(CITATION.search(claim)) for claim in claims)
    return {
        "valid_source_ids": valid,
        "invalid_source_ids": invalid,
        "claim_count": len(claims),
        "cited_claim_count": cited_claims,
        "citation_completeness": cited_claims / len(claims) if claims else 1.0,
        "format_passed": not invalid and (not claims or cited_claims == len(claims)),
    }


def scan_poisoning(text: str, trust_level: str = "internal") -> list[str]:
    """入库侧投毒扫描（11.13）：命中则返回中文信号，无命中返回空列表。

    ``text`` 是待入库的原文（整篇或一块都行）。``trust_level`` 是这份资料的来源可信度，
    传 ``"external"`` / ``"unknown"`` 会额外加一条"低信任来源"信号——内容合规不代表
    来源可信，两件事要分开报，人工复核时才知道是"文里有诱导"还是"来路不明"。
    缺省 ``"internal"`` 表示内部文档，不额外加码。

    返回中文信号列表：给审核员看的，不是给机器判断用的——一条命中不等于拒收，
    而是"入库可以，但这篇得有人看过"。规则写死在这三个套路（指令注入、诱导外泄、
    无出处断言）上，生产版应为规则库加版本号与旁路审计。
    """
    signals: list[str] = []
    rules = [
        (r"忽略(之前|上面|以上|先前).{0,6}(指令|规则|要求)|ignore\s+(all\s+)?previous\s+instructions|你现在是",
         "指令句式：疑似 Prompt 注入"),
        (r"(把|将).{0,6}(全部|所有).{0,8}(资料|内容|上下文).{0,8}(原样)?(输出|导出|打印|发送)|泄露|导出所有",
         "越权/外泄诱导：疑似诱导数据外泄"),
        (r"据可靠消息|内部渠道|据知情人士|据非公开",
         "异常新来源：无出处断言，需人工溯源核实"),
    ]
    for pattern, label in rules:
        if re.search(pattern, text, flags=re.IGNORECASE):
            signals.append(label)
    if trust_level in ("external", "unknown"):
        signals.append("低信任来源，需人工复核")
    return signals


def mask_pii(text: str) -> str:
    """日志/缓存脱敏（11.13）：手机号、邮箱、身份证、银行卡替换为占位，其余不动。

    ``text`` 是要写进日志或缓存的文本。用正则而不是模型：脱敏必须是幂等的、
    零幻觉的——漏一个数字是事故，模型"多脱一个"同样会让日志失去排查价值。
    替换顺序有讲究，身份证（18 位）和银行卡（16–19 位）都排在手机号前面，
    否则 18 位数字会先被手机号规则切掉中间一段。返回脱敏后的新字符串。
    """
    masked = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]", text)
    masked = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[身份证已脱敏]", masked)
    masked = re.sub(r"(?<!\d)\d{16,19}(?!\d)", "[银行卡已脱敏]", masked)
    masked = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已脱敏]", masked)
    return masked


def retrieval_metrics(
    retrieved: Sequence[str],
    relevant: Iterable[str] | Mapping[str, float],
    k: int,
) -> dict[str, float]:
    """Hit / Precision / Recall / MRR / nDCG，给门禁层做检索体检（11.9）。

    ``retrieved`` 是检索返回的 id 列表，按名次排（只看前 ``k`` 个）。``relevant`` 是
    标准答案：既可以只给 id 集合（每篇算 1 分），也可以给 ``{id: 相关度}`` 映射，
    后者才能让 nDCG 反映"相关 3 分的排在了 1 分前面"。``k`` 是评测深度，必须大于 0，
    否则抛 ``ValueError``（拿 0 当分母算 precision 只会得到一个漂亮而无意义的数）。

    返回五个指标的字典：``hit_rate_at_k``（前 k 里有没有命中，0 或 1）、
    ``precision_at_k``（命中数 / k）、``recall_at_k``（命中的不同 id / 全部应检索到的）、
    ``mrr``（第一个命中的名次倒数）、``ndcg_at_k``（带相关度加权的排序质量）。
    标准答案为空时，recall 与 nDCG 记 0.0。
    """
    if k <= 0:
        raise ValueError("k 必须大于 0")
    gains = dict(relevant) if isinstance(relevant, Mapping) else {doc_id: 1.0 for doc_id in relevant}
    ranked = list(retrieved[:k])
    hits = [doc_id for doc_id in ranked if doc_id in gains]
    first_rank = next((i for i, doc_id in enumerate(ranked, 1) if doc_id in gains), None)
    dcg = sum((2 ** gains.get(doc_id, 0.0) - 1) / math.log2(i + 1) for i, doc_id in enumerate(ranked, 1))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum((2 ** gain - 1) / math.log2(i + 1) for i, gain in enumerate(ideal, 1))
    return {
        "hit_rate_at_k": float(bool(hits)),
        "precision_at_k": len(hits) / k,
        "recall_at_k": len(set(hits)) / len(gains) if gains else 0.0,
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        "ndcg_at_k": dcg / idcg if idcg else 0.0,
    }


@dataclass
class RunBudget:
    """Agentic RAG 的硬预算；任一上限触发后停止自动循环（11.8 / 10.11 熔断）。

    三对字段一一对应，前一个是上限、后一个是已用量：``max_retrievals`` / ``retrievals``
    管检索，``max_rewrites`` / ``rewrites`` 管查询改写，``max_verifications`` /
    ``verifications`` 管答案复检。上限默认都是 1（课堂版够用：一次检索、一次改写、
    一次复检），已用量从 0 起算。

    预算放在对象里而不是散成几个函数参数，是为了让"这一跑还剩几次"变成可断言的状态：
    循环体内只问 ``consume`` 拿票，熔断判断就不会散落在各处、也不会被某条分支绕过。
    """

    max_retrievals: int = 1
    max_rewrites: int = 1
    max_verifications: int = 1
    retrievals: int = 0
    rewrites: int = 0
    verifications: int = 0

    def consume(self, action: str) -> bool:
        """给一次动作扣票：还有余额就 +1 并放行，超了原样退回。

        ``action`` 只认 ``"retrieval"`` / ``"rewrite"`` / ``"verify"`` 三个键，写别的抛
        ``ValueError``——拼错动作名若静默放行，预算就形同虚设，等于没有熔断。
        返回 True 表示这次可以做，False 表示预算已尽、调用方必须收手转降级。
        注意它**不抛**"超预算"异常：超预算是一条正常业务分支（该拒答就拒答），
        用异常表达会把降级路径挤进 except 里，反而看不清。
        """
        limits = {
            "retrieval": ("retrievals", self.max_retrievals),
            "rewrite": ("rewrites", self.max_rewrites),
            "verify": ("verifications", self.max_verifications),
        }
        if action not in limits:
            raise ValueError(f"未知动作：{action}")
        field_name, limit = limits[action]
        used = getattr(self, field_name)
        if used >= limit:
            return False
        setattr(self, field_name, used + 1)
        return True
