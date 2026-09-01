"""
s12_citation_grounded_gen.py
============================
11.12 配套代码：生成层防幻觉与引用溯源
痛点：答案没出处没人敢用 → 编号引用协议 + 程序校验 + 在线忠实度复检 + 流式生成。
资料来自 testdata 真实制度页（shared_corpus），不再手搓例句。
"""

import os

from dataclasses import dataclass
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from rag_quality import citation_metrics
from shared_corpus import demo_pages, find_page, make_llm as _make_llm


@dataclass
class Source:
    doc_id: str
    text: str


def _page_source(chunk_id: str, pages=None) -> Source:
    """从真实语料取一页当编号来源。"""
    pages = pages if pages is not None else demo_pages()
    p = find_page(chunk_id, pages)
    return Source(p.chunk_id, p.text)


@lru_cache(maxsize=1)
def get_llm():
    return _make_llm(temperature=0)

CITE_PROMPT = ChatPromptTemplate.from_template(
    "你是企业知识库助手。严格遵守：\n"
    "1. 只依据下方带编号的资料回答，禁止使用任何资料外的知识；\n"
    "2. 每个关键陈述句末尾必须标注依据编号，如 [1] 或 [2]；\n"
    "3. 资料不足以回答时，只回复：【资料不足】。\n\n"
    "资料：\n{numbered_sources}\n\n问题：{question}"
)


def format_sources(sources: list[Source]) -> str:
    return "\n".join(f"[{i + 1}] （{s.doc_id}）{s.text}" for i, s in enumerate(sources))


def check_citations(answer: str, n_sources: int) -> tuple[bool, list[int]]:
    """程序性格式门禁：杜绝幽灵引用，并要求每个陈述句有来源。"""
    metrics = citation_metrics(answer, n_sources)
    valid = metrics["valid_source_ids"]
    return bool(metrics["format_passed"] and valid), valid


def demo_citation() -> None:
    """接地生成 + 引用标注 + 引用校验三合一管道；资料 = 真实制度页。"""
    def answer_with_citation(question: str, sources: list[Source]) -> dict:
        resp = get_llm().invoke(CITE_PROMPT.format(
            numbered_sources=format_sources(sources), question=question))
        ok, cited = check_citations(resp.content, len(sources))
        if resp.content.startswith("【资料不足】") or not ok:
            return {"answer": "抱歉，知识库中暂无可靠依据，已转人工。", "citations": []}
        return {"answer": resp.content,
                "citations": [{"marker": f"[{i}]", "doc_id": sources[i - 1].doc_id}
                              for i in cited]}

    srcs = [_page_source("REAL-RAG-TRAVEL-2026#p1"),    # 真实页：住宿标准
            _page_source("REAL-RAG-TRAVEL-2026#p4")]    # 真实页：提交时限

    print("=== 引用溯源（资料 = testdata 真实制度页）===")
    result = answer_with_citation("去上海出差住一晚能报多少？报销单最晚什么时候交？", srcs)
    print("引用映射:", result["citations"])
    print(result["answer"])
    bad = "住宿上限为 500 元 [1]。报销期限为十天。另见不存在的来源 [9]。"
    print("\n引用质量门禁（故意失败）:", citation_metrics(bad, len(srcs)))
    print("提示：格式通过仍不等于语义被来源支持，下一步还要做逐主张蕴含校验。")


class VerifiedAnswer(BaseModel):
    is_faithful: bool = Field(description="答案每个陈述是否都能在资料中找到依据")
    hallucination_spans: list[str] = Field(description="无依据的陈述句列表，没有则空")


def demo_verify() -> None:
    """返回前的在线忠实度复检：幻觉在出门口被拦下。"""
    verifier = get_llm().with_structured_output(VerifiedAnswer)
    srcs = [_page_source("REAL-RAG-TRAVEL-2026#p1")]
    # 第一句是真实制度内容，第二句是编造的——看看复检能不能抓出来
    answer = "一晚上限 500 元。此外公司会额外报销机票全款。"

    v = verifier.invoke(ChatPromptTemplate.from_template(
        "资料：\n{sources}\n答案：{answer}\n逐句检查答案是否有资料外编造的内容。"
    ).format(sources=format_sources(srcs), answer=answer))

    print("=== 在线忠实度复检 ===")
    print(f"is_faithful = {v.is_faithful}，无依据句 = {v.hallucination_spans}")


def demo_stream() -> None:
    """流式生成：首字延迟（TTFT）是 RAG 体验的生命线。"""
    srcs = [_page_source("REAL-RAG-TRAVEL-2026#p1")]
    chain = CITE_PROMPT | get_llm()

    print("=== 流式生成 ===")
    for chunk in chain.stream({"numbered_sources": format_sources(srcs),
                               "question": "去上海出差住一晚能报多少？"}):
        print(chunk.content, end="", flush=True)
    print()


if __name__ == "__main__":
    demo_citation()
    demo_verify()
    demo_stream()
