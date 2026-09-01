"""
s08_agentic_rag.py
==================
11.8 配套代码：Agentic RAG 自省自校正
痛点：答非所问与幻觉 → 用 LangGraph 构建「检索 → 分级 → 联网兜底 → 生成 → 幻觉复检」闭环，
检索的不再是两句假文档，而是 testdata 里的真实制度库。
"""

import os
from functools import lru_cache

from typing import List
from typing import TypedDict

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from rag_quality import RunBudget
from shared_corpus import all_pages, make_embeddings, page_documents

# ---------- 1. 基础设施（延迟初始化：导入模块不应调用外部 API） ----------
@lru_cache(maxsize=1)
def get_llm():
    from shared_corpus import make_llm
    return make_llm(temperature=0)


class BatchedEmbeddings:
    """Chroma 入库分批包装：绕开部分端点 10 条 input 上限。"""

    def __init__(self):
        self._inner = make_embeddings()

    def embed_documents(self, texts):
        from shared_corpus import embed_texts_batched
        return embed_texts_batched(self._inner, list(texts))

    def embed_query(self, text):
        return self._inner.embed_query(text)


@lru_cache(maxsize=1)
def get_retriever():
    """真实制度库检索器：testdata 8 份文档 28 页。"""
    docs = page_documents(all_pages())
    vectorstore = Chroma.from_documents(docs, BatchedEmbeddings())
    return vectorstore.as_retriever(search_kwargs={"k": 3})

# ---------- 2. 结构化评判模型 ----------
from typing import Literal

from pydantic import BaseModel, Field


class GradeDocs(BaseModel):
    """判断每篇文档是否与问题相关（用于 CRAG 分级）"""
    binary_score: Literal["yes", "no"] = Field(description="文档是否相关")

class CheckHallucination(BaseModel):
    """判断答案是否忠实于参考资料（用于幻觉复检）"""
    faithful: Literal["yes", "no"] = Field(description="答案是否完全有依据")

class CheckAnswer(BaseModel):
    """判断答案是否真正回答了问题"""
    answered: Literal["yes", "no"] = Field(description="答案是否回答了问题")

@lru_cache(maxsize=1)
def get_graders():
    llm = get_llm()
    return (
        llm.with_structured_output(GradeDocs),
        llm.with_structured_output(CheckHallucination),
        llm.with_structured_output(CheckAnswer),
    )

# ---------- 3. 全局状态 ----------
class GraphState(TypedDict):
    question: str
    documents: List[str]
    generation: str
    needs_web_search: bool


def decide_after_verification(faithful: bool, answered: bool, budget: RunBudget) -> str:
    """把停止条件写成代码：通过就交付；未通过只允许有限重写，否则拒答/转人工。"""
    if faithful and answered:
        return "deliver"
    if budget.consume("rewrite"):
        return "retry"
    return "refuse"

# ---------- 4. 节点 ----------
def retrieve(state: GraphState) -> GraphState:
    print("→ [检索] 查询真实制度知识库")
    docs = get_retriever().invoke(state["question"])
    for d in docs:
        print(f"   · [{d.metadata['id']}]《{d.metadata['title']}》")
    return {"documents": [f"[{d.metadata['id']}] {d.page_content}" for d in docs]}

def grade_documents(state: GraphState) -> GraphState:
    """CRAG 核心：逐篇分级，过滤无关噪声"""
    print("→ [分级] 裁判评估每篇文档")
    grader, _, _ = get_graders()
    filtered, need_web = [], False
    for doc in state["documents"]:
        prompt = ChatPromptTemplate.from_template(
            "问题：{question}\n文档：{doc}\n该文档是否包含回答问题所需信息？"
        )
        verdict = grader.invoke(prompt.format(question=state["question"], doc=doc))
        if verdict.binary_score == "yes":
            filtered.append(doc)
            print("   ✅ 采纳相关文档")
        else:
            print("   ❌ 剔除无关文档")
    if not filtered:
        need_web = True
        print("   ⚠️ 无相关文档 → 需要联网兜底")
    return {"documents": filtered, "needs_web_search": need_web}

def web_search(state: GraphState) -> GraphState:
    """联网兜底：生产环境可接入 Tavily/DuckDuckGo 真实搜索"""
    print("→ [联网] 私有库不足，发起实时搜索")
    web_doc = "【实时联网结果】2026 年最新 AI 编程范式综述..."
    return {"documents": state["documents"] + [web_doc]}

def generate(state: GraphState) -> GraphState:
    print("→ [生成] 基于合格文档组织答案")
    prompt = ChatPromptTemplate.from_template(
        "严格基于以下资料回答问题，不得编造：\n{context}\n\n问题：{question}\n答案："
    )
    res = (prompt | get_llm() | StrOutputParser()).invoke(
        {"context": "\n".join(state["documents"]), "question": state["question"]}
    )
    return {"generation": res}

def check_hallucination(state: GraphState) -> GraphState:
    """幻觉复检 + 答案完整度复检"""
    print("→ [复检] 核对答案是否忠实且有依据")
    context = "\n".join(state["documents"])
    _, hallucination_checker, answer_checker = get_graders()
    faithful = hallucination_checker.invoke(
        f"参考：{context}\n答案：{state['generation']}\n答案是否完全有依据？"
    )
    answered = answer_checker.invoke(
        f"问题：{state['question']}\n答案：{state['generation']}\n答案是否回答了问题？"
    )
    if faithful.faithful == "yes" and answered.answered == "yes":
        print("   ✅ 忠实且已作答 → 交付")
        return {"generation": state["generation"]}
    print("   ❌ 存在幻觉/未作答 → 到达预算后必须拒答或转人工，不能无限自省")
    return {"generation": state["generation"], "needs_web_search": True}

# ---------- 5. 构图 ----------
workflow = StateGraph(GraphState)
workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("web_search", web_search)
workflow.add_node("generate", generate)
workflow.add_node("check_hallucination", check_hallucination)

workflow.add_edge(START, "retrieve")
workflow.add_edge("retrieve", "grade_documents")

def after_grade(state: GraphState) -> str:
    return "web_search" if state["needs_web_search"] else "generate"

workflow.add_conditional_edges("grade_documents", after_grade, {"web_search": "web_search", "generate": "generate"})
workflow.add_edge("web_search", "generate")
workflow.add_edge("generate", "check_hallucination")
workflow.add_edge("check_hallucination", END)

app = workflow.compile()


def main() -> None:
    print("说明：本脚本是借鉴 CRAG/Self-RAG 思想的工作流，不等同于复现论文训练方法。")
    budget = RunBudget(max_rewrites=1)
    print("预算演示:", decide_after_verification(False, False, budget), "→",
          decide_after_verification(False, False, budget))
    print("===== 场景 1：真实制度库命中 =====")
    r1 = app.invoke({"question": "RX-9000 出现 ERR-404-X9 故障码应该怎么处理？"})
    print(f"💡 {r1['generation']}\n")

    print("===== 场景 2：真实制度库缺失 → 联网兜底 =====")
    r2 = app.invoke({"question": "2026 年最新开源大模型发布情况？"})
    print(f"💡 {r2['generation']}")


if __name__ == "__main__":
    main()
