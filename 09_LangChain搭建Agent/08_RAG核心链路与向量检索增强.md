# 📚 9.8 RAG 核心链路与向量检索增强

> **“微调是让学生去读研深造，而 RAG 是给学生发一套随身携带的百科全书随时翻阅。”**  
> 检索增强生成（Retrieval-Augmented Generation，RAG）是解决大模型幻觉、突破上下文长度限制、注入企业私有知识库的最强武器。

---

## 💡 概念大白话：图书馆智能索引员与开卷考试

### 1. 闭卷考试与大模型幻觉
大模型的参数是固化在权重里的，就像一个参加**闭卷考试**的学生：
- 遇到没学过的企业私有规范，只能凭借想象力“胡说八道”（幻觉）；
- 法律法规或产品报价一旦更新，重新训练或微调（Fine-Tuning）动辄需要数周时间和数十万元算力。

### 2. 生活比喻：智能图书馆索引员与开卷参考书
- **文档切块（Text Chunking）**：把一本 500 页的大部头拆成一张张便于查阅的“知识便签”；
- **向量嵌入（Embeddings）**：给每张便签提炼一个高维语义坐标，意思相近的便签在空间上离得最近；
- **向量数据库（Chroma / Milvus）**：智能图书馆的书架索引系统；
- **RAG 管道（LCEL Pipeline）**：当用户提问时，系统像**智能图书管理员**一样，0.01 秒内精准抽出最相关的 2~3 张便签，连同问题一起递给大模型：“请严格参考这几份资料，准确回答用户的问题！”

<!-- 图表源文件：img/diagrams/08-diagram-01.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/08-diagram-01.svg">
    <img src="img/diagrams/08-diagram-01.svg" alt="2. 生活比喻：智能图书馆索引员与开卷参考书" width="760">
  </a>
</p>

---

## 💻 核心实操：构建企业规范 LCEL RAG 问答链

### 1. 文档切块与 Chroma 向量库构建

> 📦 **安装说明（2026 生态现状）**：`langchain-community` 已 Sunset，Chroma 向量库需使用**独立伙伴包 `langchain-chroma`**：
> ```bash
> pip install -U langchain-chroma
> ```

```python
# code/s08_rag_retrieval.py
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma                      # ✅ 独立伙伴包（不再用 community）
from langchain_openai import OpenAIEmbeddings

# 1. 模拟企业规范私有文档
docs = [
    Document(
        page_content="""
        【微服务高可用发布规范 - 2026版】
        1. 核心业务服务必须部署在至少两个可用区（Multi-AZ），副本数不得低于 3 个。
        2. 生产发布必须采用灰度金丝雀发布，初始流量比例不超过 5%，观察 15 分钟无 Error 告警后方可全量。
        3. 服务必须配置健康检查探针，超时时间统一设置为 3 秒。
        """,
        metadata={"source": "高可用运维指南.md"}
    )
]

# 2. 递归字符切块器（兼顾段落、换行与标点完整性）
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=150,
    chunk_overlap=20,
    separators=["\n\n", "\n", "。", " "]
)
splits = text_splitter.split_documents(docs)

# 3. 向量化并持久化至 Chroma 向量库
#    Embedding 的服务地址 / 模型名称 / API Key 全部集中在 .env 环境变量中管理，代码里不写死
import os
embeddings = OpenAIEmbeddings(
    api_key=os.getenv("OPENAI_API_KEY"),     # 从 .env 读取 Embedding API Key
    base_url=os.getenv("OPENAI_API_BASE"),   # 从 .env 读取 OpenAI 兼容服务地址
    model=os.getenv("EMBEDDING_MODEL"),      # 从 .env 读取向量模型名称
)
vectorstore = Chroma.from_documents(
    documents=splits,
    embedding=embeddings,
    persist_directory="./chroma_db",   # 可选：落盘持久化
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
```

> 🆕 **1.x 补充：`init_embeddings` 统一嵌入工厂**。与 `init_chat_model` 同理，LangChain 1.x 提供 `langchain.embeddings.init_embeddings` 一行初始化任意厂商嵌入模型：
> ```python
> from langchain.embeddings import init_embeddings
> embeddings = init_embeddings("openai:text-embedding-3-small")   # 或 "deepseek:..." 等
> ```

### 2. 使用 LCEL 组装标准 RAG 链式管道

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from s01_model_io import get_chat_model

def format_docs(retrieved_docs):
    """格式化参考片段"""
    return "\n\n".join([f"【来源: {d.metadata.get('source')}】\n{d.page_content}" for d in retrieved_docs])

# RAG 专属 Prompt
rag_prompt = ChatPromptTemplate.from_template("""你是一名资深架构审查员。
请根据以下提供的规范参考资料准确回答问题。若资料未提及，请明确说明，严禁胡编。

【参考规范】：
{context}

【提问】：
{question}

请给出专业严谨的回答：""")

llm = get_chat_model(temperature=0.1)

# 经典 LCEL RAG 组装公式
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | rag_prompt
    | llm
    | StrOutputParser()
)

# 运行提问
answer = rag_chain.invoke("生产环境发布金丝雀初始流量是多少？观察时间多久？")
print(answer)
```

---

## 🌟 进阶技术选型：普通 RAG vs Agentic RAG

| 维度对比 | 经典静态 RAG (Naive / Advanced RAG) | 智能体 RAG (Agentic RAG) 🚀 |
| :--- | :--- | :--- |
| **检索触发机制** | 每次提问**无脑强制**触发向量检索。 | **由 Agent 自主判断**：简单闲聊不检索，复杂问题才调用检索工具。 |
| **多源融合** | 仅检索单一固定的向量知识库。 | 可同时调用本地向量库、实时联网搜索、SQL 数据库，并根据结果交叉验证。 |
| **多轮反思与重试** | 检索出来的文档如果不匹配，直接硬着头皮答错。 | Agent 发现初次检索结果质量不足时，会自动修改关键词重新检索（Self-Reflection）。 |

---

## 📚 权威官方资料直达

- 🔗 **LangChain RAG 官方教程**：[Build a Retrieval Augmented Generation (RAG) App](https://docs.langchain.com/oss/python/tutorials/rag)
- 🔗 **Chroma 向量数据库官方文档**：[Chroma Vector Store Docs](https://docs.trychroma.com/)
- 🔗 **文本切分器完全指南**：[Text Splitters Concepts](https://docs.langchain.com/oss/python/langchain/text-splitters)
- 🔗 **Chroma LangChain 集成指南**：[Chroma integration](https://docs.langchain.com/oss/python/integrations/vectorstores/chroma)

---

## 🎯 本节小结与思考

1. **核心收获**：掌握了“切块 ➔ 向量化 ➔ 检索 ➔ 上下文组装 ➔ 生成”的完整 RAG 链路（使用独立伙伴包 `langchain-chroma`），理解了 Agentic RAG 的进阶范式。
2. **下一步探索**：我们已经齐聚了模型、模板、LCEL 管道、结构化输出、工具、记忆和 RAG。如何将它们总装为一个全自动运转的 Agent？下一节我们学习 **9.9 Agent 现代架构与 create_agent**。
