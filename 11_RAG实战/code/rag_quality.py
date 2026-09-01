"""RAG 教程共用的离线质量工具。

这些函数不调用模型、不访问网络，专门把教程里容易被“感觉”替代的部分变成
可测试的数字：检索指标、引用完整性、上下文去重、运行预算、缓存作用域和索引版本。
分节脚本可以直接导入；测试也能在没有 API Key 的机器上运行。
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Mapping, Sequence


def retrieval_metrics(
    retrieved: Sequence[str],
    relevant: Iterable[str] | Mapping[str, float],
    k: int,
) -> dict[str, float]:
    """计算一组常用检索指标。

    ``relevant`` 传集合时，每篇相关文档收益均为 1；传映射时可给高度相关文档更高收益，
    用于 nDCG。MRR 只看第一个相关结果，Recall@k 则关心相关文档有没有被捞全。
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


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], rank_constant: int = 60) -> list[tuple[str, float]]:
    """融合不同量纲的排名；同一列表内的重复 ID 只计第一次。"""
    if rank_constant < 0:
        raise ValueError("rank_constant 不能为负数")
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranking, 1):
            if doc_id in seen:
                continue
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rank_constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def _token_set(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9_.-]+|[\u4e00-\u9fff]", text.lower())
    return set(words)


def deduplicate_contexts(texts: Sequence[str], threshold: float = 0.85) -> list[str]:
    """按 Jaccard 相似度去掉近重复上下文，保留最先出现的版本。"""
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


CLAIM_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
CITATION = re.compile(r"\[(\d+)\]")


def citation_metrics(answer: str, source_count: int) -> dict[str, object]:
    """检查幽灵引用和“有陈述却没标来源”的引用完整性。

    这里只做确定性的格式门禁，不声称判断了来源是否真的支持结论；语义蕴含仍需
    人工、规则或独立验证模型完成。
    """
    cited = [int(value) for value in CITATION.findall(answer)]
    valid = sorted({value for value in cited if 1 <= value <= source_count})
    invalid = sorted({value for value in cited if value < 1 or value > source_count})
    claims = [part.strip() for part in CLAIM_SPLIT.split(answer) if part.strip()]
    claims = [claim for claim in claims if "资料不足" not in claim and "转人工" not in claim]
    cited_claims = sum(bool(CITATION.search(claim)) for claim in claims)
    return {
        "valid_source_ids": valid,
        "invalid_source_ids": invalid,
        "claim_count": len(claims),
        "cited_claim_count": cited_claims,
        "citation_completeness": cited_claims / len(claims) if claims else 1.0,
        "format_passed": not invalid and (not claims or cited_claims == len(claims)),
    }


@dataclass(frozen=True)
class SourceVersion:
    """可比较的新旧资料。authority 越大越可信，同可信度下优先新生效日期。"""

    source_id: str
    topic: str
    effective_date: date
    authority: int = 0
    status: str = "active"


def choose_current_sources(sources: Sequence[SourceVersion]) -> dict[str, SourceVersion]:
    """每个主题选择仍有效且权威性、日期最高的资料。"""
    chosen: dict[str, SourceVersion] = {}
    for source in sources:
        if source.status != "active":
            continue
        previous = chosen.get(source.topic)
        if previous is None or (source.authority, source.effective_date) > (
            previous.authority,
            previous.effective_date,
        ):
            chosen[source.topic] = source
    return chosen


@dataclass(frozen=True)
class CacheScope:
    tenant_id: str
    entitlement_hash: str
    knowledge_snapshot: str
    model_id: str
    prompt_version: str
    retrieval_version: str
    locale: str = "zh-CN"

    def key(self, question: str) -> str:
        raw = "|".join((
            self.tenant_id,
            self.entitlement_hash,
            self.knowledge_snapshot,
            self.model_id,
            self.prompt_version,
            self.retrieval_version,
            self.locale,
            question.strip(),
        ))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class RunBudget:
    """Agentic RAG 的硬预算；任何一个上限触发后都应停止自动循环。"""

    max_retrievals: int = 2
    max_rewrites: int = 1
    max_verifications: int = 1
    retrievals: int = 0
    rewrites: int = 0
    verifications: int = 0

    def consume(self, action: str) -> bool:
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


@dataclass
class IndexManifest:
    """最小化的蓝绿索引状态机。只有通过回归门禁的 staging 版本才能激活。"""

    active_version: str
    staging_version: str | None = None
    history: list[str] = field(default_factory=list)

    def stage(self, version: str) -> None:
        if version == self.active_version:
            raise ValueError("staging 版本不能与 active 相同")
        self.staging_version = version

    def promote(self, regression_passed: bool) -> str:
        if self.staging_version is None:
            raise RuntimeError("没有待发布索引")
        if not regression_passed:
            raise RuntimeError("回归门禁未通过，禁止切换索引")
        self.history.append(self.active_version)
        self.active_version, self.staging_version = self.staging_version, None
        return self.active_version

    def rollback(self) -> str:
        if not self.history:
            raise RuntimeError("没有可回滚版本")
        self.active_version = self.history.pop()
        return self.active_version


def percentile(values: Sequence[float], p: float) -> float:
    """无需 numpy 的线性插值分位数，适合展示 P50/P95/P99。"""
    if not values:
        raise ValueError("values 不能为空")
    if not 0 <= p <= 100:
        raise ValueError("p 必须在 0 到 100 之间")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * p / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
