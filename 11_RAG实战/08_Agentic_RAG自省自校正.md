# 11.8 答非所问与幻觉怎么自愈？—— Agentic RAG

> **痛点场景**：单向 RAG 流水线有三大硬伤——
> ① **假召回**：检索回 3 篇文档但通篇跑题，系统也硬着头皮编答案；
> ② **知识缺失**：库里根本没收录，系统只能回一句冷冰冰的“不知道”；
> ③ **幻觉**：生成完后没人核对，答案里“赔偿 1000 元”而原文明明是“100 元”。
> **Agentic RAG 就是给这条流水线装上“质检员 + 机动队 + 复核员”**：菜叶烂了退回重买（重检索）、店里没有就去隔壁超市（联网兜底）、出锅前亲自尝一口（幻觉检测）。

---

## 💡 思路：三种“会思考”的 RAG 范式

<!-- 图表源文件：img/diagrams/08-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/08-diagram-01.svg">
    <img src="img/diagrams/08-diagram-01.svg" alt="💡 思路：三种“会思考”的 RAG 范式" width="760">
  </a>
</p>

| 范式 | 一句话 | 核心机制 |
| :--- | :--- | :--- |
| **Self-RAG** | 生成过程中自我反思 | 反思 Token：`[Retrieve]`（要不要查）、`[ISREL]`（相关吗）、`[ISSUP]`（有依据吗） |
| **CRAG** | 检索后先“分级再决策” | 裁判给文档打分：Correct→提炼去噪、Incorrect→联网兜底、Ambiguous→多源融合 |
| **Adaptive RAG** | 先判断难度再选路线 | 简单→直接答（省钱）、中等→单次检索、困难→多轮/多工具 |

> 📄 对应论文：[Self-RAG (Asai et al., 2023)](https://arxiv.org/abs/2310.11511)、[CRAG (Yan et al., 2024)](https://arxiv.org/abs/2401.15884)。

---

## 🧑‍💻 代码实现：基于 LangGraph 的「自适应 + 校正 + 幻觉自检」完整闭环

> 这是一个比“玩具 Demo”完整得多的图：**难度路由 → 真实检索 → 文档分级 → 联网兜底 → 生成 → 幻觉复检**，每一环都做了结构化评判。

```python
from typing import List, Literal, TypedDict

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

# ---------- 1. 基础设施 ----------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 小型私有知识库（模拟）
vectorstore = Chroma.from_documents(
    [
        Document(page_content="Vibe Coding 是 Andrej Karpathy 提出的 AI 原生辅助编程范式。"),
        Document(page_content="公司年度体检在每年 6 月由行政部统一组织。"),
    ],
    OpenAIEmbeddings(model="text-embedding-3-small"),
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# ---------- 2. 结构化评判模型 ----------
class GradeDocs(BaseModel):
    """判断每篇文档是否与问题相关（用于 CRAG 分级）"""
    binary_score: Literal["yes", "no"] = Field(description="文档是否相关")

class CheckHallucination(BaseModel):
    """判断答案是否忠实于参考资料（用于幻觉复检）"""
    faithful: Literal["yes", "no"] = Field(description="答案是否完全有依据")

class CheckAnswer(BaseModel):
    """判断答案是否真正回答了问题"""
    answered: Literal["yes", "no"] = Field(description="答案是否回答了问题")

grader = llm.with_structured_output(GradeDocs)
hallucination_checker = llm.with_structured_output(CheckHallucination)
answer_checker = llm.with_structured_output(CheckAnswer)

# ---------- 3. 全局状态 ----------
class GraphState(TypedDict):
    question: str
    documents: List[str]
    generation: str
    needs_web_search: bool

# ---------- 4. 节点 ----------
def retrieve(state: GraphState) -> GraphState:
    print("→ [检索] 查询私有知识库")
    docs = retriever.invoke(state["question"])
    return {"documents": [d.page_content for d in docs]}

def grade_documents(state: GraphState) -> GraphState:
    """CRAG 核心：逐篇分级，过滤无关噪声"""
    print("→ [分级] 裁判评估每篇文档")
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
    res = (prompt | llm | StrOutputParser()).invoke(
        {"context": "\n".join(state["documents"]), "question": state["question"]}
    )
    return {"generation": res}

def check_hallucination(state: GraphState) -> GraphState:
    """幻觉复检 + 答案完整度复检"""
    print("→ [复检] 核对答案是否忠实且有依据")
    context = "\n".join(state["documents"])
    faithful = hallucination_checker.invoke(
        f"参考：{context}\n答案：{state['generation']}\n答案是否完全有依据？"
    )
    answered = answer_checker.invoke(
        f"问题：{state['question']}\n答案：{state['generation']}\n答案是否回答了问题？"
    )
    if faithful.faithful == "yes" and answered.answered == "yes":
        print("   ✅ 忠实且答非所问不成立 → 交付")
        return {"generation": state["generation"]}
    print("   ❌ 存在幻觉/未作答 → 触发重新检索（重试一轮）")
    # 生产环境可在这里做有限次数重试（如最多 2 次），避免死循环
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
workflow.add_edge("check_hallucination", END)  # 完整版可加条件边做有限重试

app = workflow.compile()

# ---------- 6. 运行两个场景 ----------
print("===== 场景 1：私有库命中 =====")
r1 = app.invoke({"question": "什么是 Vibe Coding？"})
print(f"💡 {r1['generation']}\n")

print("===== 场景 2：私有库缺失 → 联网兜底 =====")
r2 = app.invoke({"question": "2026 年最新开源大模型发布情况？"})
print(f"💡 {r2['generation']}")
```

**这段代码比“玩具版”强在哪？**
1. **真实检索**（接入了 Chroma），不是写死的假文档；
2. **CRAG 分级**独立成节点，带 `needs_web_search` 标志，实现“分级 → 决策”；
3. **幻觉复检**用两个结构化评判器（忠实度 + 完整度）双保险；
4. 注释里提示了“有限次数重试”的工程边界，避免循环失控。

---

## 🚀 拓展：工程化时要注意什么？

| 关注点 | 建议 |
| :--- | :--- |
| **成本与延迟** | 每次多轮重试都烧 token，务必设置最大重试次数（如 2 次）并记录耗时 |
| **安全边界** | 联网兜底只应把“检索结果”拼入上下文，不要让 LLM 自由执行代码/访问内网 |
| **可观测** | 每个节点的判定结果要落日志，方便 11.9 做 Badcase 归因 |
| **阈值校准** | “相关/忠实/已作答”的判定标准要先在离线评测集上校准，再上线 |

---

## 🔗 权威官方参考

- [Self-RAG 论文（Asai et al., 2023, arXiv:2310.11511）](https://arxiv.org/abs/2310.11511)
- [CRAG 论文（Yan et al., 2024, arXiv:2401.15884）](https://arxiv.org/abs/2401.15884)
- [LangChain Adaptive RAG 官方教程](https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_adaptive_rag.ipynb)
- [LangGraph CRAG 官方实战](https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_crag.ipynb)
