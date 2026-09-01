"""
s06_query_rewrite.py
====================
11.6 配套代码：查询重写与意图路由
痛点：用户提问含糊 → 在 testdata 真实知识库上演示 HyDE 以答搜答、
Multi-Query 多路并发、结构化意图路由，以及改写护栏。
"""

import os

import asyncio
from typing import List
from typing import Literal

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from shared_corpus import all_pages, make_embeddings, page_documents


def make_llm():
    from shared_corpus import make_llm as _factory
    return _factory(temperature=0)


class BatchedEmbeddings:
    """Chroma 入库分批包装：绕开部分端点 10 条 input 上限。"""

    def __init__(self):
        self._inner = make_embeddings()

    def embed_documents(self, texts):
        from shared_corpus import embed_texts_batched
        return embed_texts_batched(self._inner, list(texts))

    def embed_query(self, text):
        return self._inner.embed_query(text)


def build_kb_retriever(k: int = 3):
    """把 testdata 真实语料建成 Chroma 检索器（进程内重建，无外部依赖）。"""
    docs = page_documents(all_pages())
    vectorstore = Chroma.from_documents(docs, BatchedEmbeddings())
    return vectorstore.as_retriever(search_kwargs={"k": k})


def merge_queries(original: str, rewrites: List[str], limit: int = 4) -> List[str]:
    """始终保留用户原问题，避免改写模型把关键编号、否定词或时间条件改丢。"""
    merged, seen = [], set()
    for query in [original, *rewrites]:
        normalized = " ".join(query.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)
        if len(merged) >= limit:
            break
    return merged


def should_decompose(question: str) -> bool:
    """简单的多跳信号；真实系统应用评测集校准分类器。"""
    connectors = ("分别", "比较", "先", "再", "以及", "同时", "之间", "为什么又")
    return len(question) > 45 or sum(token in question for token in connectors) >= 2


def demo_hyde() -> None:
    """HyDE：生成假想文档 → 用其向量检索真实制度库（问题故意口语化）。"""
    llm = make_llm()
    retriever = build_kb_retriever(k=2)

    hyde_prompt = ChatPromptTemplate.from_template(
        "请针对问题写一段可能回答它的企业制度文档片段（即使细节不完全准确也行，重点是术语与陈述句风格）：\n问题：{question}\n假想文档："
    )
    hyde_chain = hyde_prompt | llm | StrOutputParser()
    question = "出差回来晚了一天，钱最晚啥时候能到手？"   # 口语化：直接检索很难命中「提交时限」页
    hypo_doc = hyde_chain.invoke({"question": question})
    print("=== HyDE 生成的假想文档 ===")
    print(hypo_doc[:120] + "...")

    hits = retriever.invoke(hypo_doc)   # 关键一步：用假答案的向量去检索
    print("\n=== 用假答案检索命中的真实文档 ===")
    for d in hits:
        print(f"- [{d.metadata['id']}]《{d.metadata['title']}》")

    print("\n=== 对照：不用 HyDE 直接检索 ===")
    for d in retriever.invoke(question):
        print(f"- [{d.metadata['id']}]《{d.metadata['title']}》")


async def demo_multi_query() -> None:
    """Multi-Query：LLM 生成 3 路扩展查询，并发检索真实库后去重合并。"""
    retriever = build_kb_retriever(k=2)
    llm = make_llm()

    expand_prompt = ChatPromptTemplate.from_template(
        "你是检索查询改写器。把下面的问题从 3 个不同角度改写成更专业、更可检索的中文查询"
        "（针对公司制度知识库）。只输出 3 行查询本身，每行一个，不要编号、不要解释、不要 markdown：\n{question}\n"
    )

    async def multi_query_search(question: str) -> List:
        raw_lines = (expand_prompt | llm | StrOutputParser()).invoke({"question": question}).strip().splitlines()
        cleaned: List[str] = []
        for line in raw_lines:
            line = line.strip().lstrip("0123456789.、- ").strip()
            line = line.strip("*#").strip()
            if line and "角度" not in line and "：" not in line[:6] and len(line) > 4:
                cleaned.append(line)
        rewrites = cleaned[:3]
        queries = merge_queries(question, rewrites)
        print("扩展查询:", queries)
        results = await asyncio.gather(*[asyncio.to_thread(retriever.invoke, q) for q in queries])
        seen, merged = set(), []
        for batch in results:
            for d in batch:
                if d.metadata["id"] not in seen:
                    seen.add(d.metadata["id"])
                    merged.append(d)
        return merged

    merged = await multi_query_search("我下周要去北京见客户，吃住行都能报多少，发票有什么讲究？")
    print(f"\n=== 去重后共 {len(merged)} 篇真实文档 ===")
    for d in merged:
        print(f"- [{d.metadata['id']}]《{d.metadata['title']}》")


def demo_routing() -> None:
    """结构化意图路由：把问题分派到 testdata 里真实存在的三张「知识库」。"""
    llm = make_llm()
    class RouteQuery(BaseModel):
        destination: Literal["ops_kb", "policy_kb", "hr_kb", "chitchat"] = Field(
            description="ops_kb=设备运维(RX9000/打印机故障), policy_kb=差旅报销与发票制度, hr_kb=年假与体检制度, chitchat=与知识库完全无关的寒暄"
        )
        rewrite: str = Field(description="规范化后的检索关键词（中文）")

    # 分诊提示词显式给出判定边界：弱模型对「报销算不算闲聊」的边界很模糊
    ROUTE_PROMPT = ChatPromptTemplate.from_template(
        "你是公司知识库助手的分诊台。请判断用户问题属于哪个知识库。\n"
        "判定标准：只要问题涉及出差、住宿、报销、发票、餐饮补贴等费用话题，一律 policy_kb；\n"
        "涉及打印机、设备、故障码，ops_kb；涉及年假、体检、入职，hr_kb；\n"
        "只有和知识库完全无关的寒暄才是 chitchat。\n\n用户问题：{question}"
    )
    router = llm.with_structured_output(RouteQuery)
    tests = [
        "去上海出差住宿报销发票抬头怎么开？",
        "打印机显示 E3 怎么处理？",
        "年假有几天，怎么申请？",
        "今天天气怎么样？",
    ]
    for test in tests:
        result = router.invoke(ROUTE_PROMPT.format(question=test))
        print(f"\n问题: {test}")
        print(f"路由目标: {result.destination}")
        print(f"规范化查询: {result.rewrite}")
        if result.destination == "policy_kb":
            print("→ 进入差旅报销制度库检索链路")
        elif result.destination == "chitchat":
            print("→ 直接闲聊回答，省去检索成本")


def demo_rewrite_guardrails() -> None:
    """展示改写的两条保险：保留原问题，多跳问题先拆解再检索。"""
    original = "比较 2025 和 2026 年上海住宿标准，并说明新版何时生效"
    rewrites = ["上海差旅住宿标准", "2026 差旅制度生效日期", "上海住宿标准"]
    print("\n=== 查询改写护栏 ===")
    print("检索查询:", merge_queries(original, rewrites))
    print("需要拆解:", should_decompose(original))
    print("（testdata 里正好有 2025 已废止与 2026 现行两版制度，适合演示版本冲突题）")


if __name__ == "__main__":
    demo_hyde()
    asyncio.run(demo_multi_query())
    demo_routing()
    demo_rewrite_guardrails()
