"""
s08_rag_retrieval.py - RAG 核心链路与向量检索增强
------------------------------------------------------------------
对应章节：9.8 RAG 核心链路与向量检索增强
核心功能：
1. 文档分块：RecursiveCharacterTextSplitter 切分长篇技术文档
2. 向量入库：使用 langchain-chroma（独立伙伴包）建立语义索引
3. 现代 LCEL RAG 管道编排
4. 引用溯源与开卷问答体验

安装：pip install -U langchain-chroma  （langchain-community 已 Sunset，勿再使用）
"""

import os
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma                    # ✅ 独立伙伴包
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from rich.console import Console
from rich.panel import Panel
from s01_model_io import get_chat_model

console = Console()

def get_embeddings():
    """获取 Embeddings 实例（URL / 模型 / Key 全部由 .env 环境变量提供）"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
    model = os.getenv("EMBEDDING_MODEL", "")

    # 若有可用 key 则走标准 embedding，否则使用兼容模式
    # 方舟等国产端点只接受字符串输入：禁用 tiktoken 预分词，直接发送原文
    return OpenAIEmbeddings(
        api_key=api_key or "sk-dummy",
        base_url=api_base,
        model=model,
        check_embedding_ctx_length=False,
        tiktoken_enabled=False,
    )

def prepare_knowledge_base():
    """准备模拟的企业内部技术规范文档"""
    raw_docs = [
        Document(
            page_content="""
            【企业编码安全规范 - 2026版】
            1. 生产环境禁止使用 root 账号运行任何微服务容器。
            2. 所有 API 接口对外暴露时必须强制启用 JWT 鉴权与 RBAC 权限网关，禁止匿名访问核心数据库。
            3. API Key、数据库密码等绝密凭据严禁明文硬编码在代码仓库中，必须统一由 HashiCorp Vault 或 KMS 托管注入环境变量。
            4. 每次代码提交必须通过自动化静态代码扫描（SonarQube），安全漏洞严重等级大于 High 的 PR 一律禁止合并。
            """,
            metadata={"source": "安全规范手册.md", "category": "Security"}
        ),
        Document(
            page_content="""
            【微服务高可用发布规范 - 2026版】
            1. 核心业务服务必须部署在至少两个可用区（Multi-AZ），副本数不得低于 3 个。
            2. 生产发布必须采用灰度金丝雀发布（Canary Release），初始流量比例不超过 5%，观察 15 分钟无 Error 告警后方可全量。
            3. 服务必须配置健康检查探针（livenessProbe 与 readinessProbe），超时时间统一设置为 3 秒。
            """,
            metadata={"source": "高可用运维指南.md", "category": "DevOps"}
        )
    ]
    return raw_docs

def build_vector_store(docs: List[Document]):
    """切分并向量化入库；远端 Embedding 端点不可用时自动降级为本地确定性向量"""
    # 1. 文本切块
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=30,
        separators=["\n\n", "\n", "。", "；", " "]
    )
    splits = text_splitter.split_documents(docs)
    console.print(f"[dim]已将文档切分为 {len(splits)} 个语义 Chunk 片段。[/dim]")

    # 2. 向量入库 (Chroma)；端点不可用 → 兼容模式（本地伪向量，保证链路可演示）
    try:
        embeddings = get_embeddings()
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
            collection_name="enterprise_knowledge_demo"
        )
    except Exception as e:
        from langchain_core.embeddings import DeterministicFakeEmbedding
        console.print(f"[yellow]远端 Embedding 不可用（{str(e)[:80]}…），切换本地确定性向量兼容模式。[/yellow]")
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=DeterministicFakeEmbedding(size=384),
            collection_name="enterprise_knowledge_demo"
        )
    return vectorstore

def format_docs(docs: List[Document]) -> str:
    """格式化检索到的参考文档片段"""
    formatted = []
    for idx, doc in enumerate(docs, 1):
        src = doc.metadata.get("source", "未知来源")
        formatted.append(f"【参考资料 {idx} | 来源: {src}】\n{doc.page_content.strip()}")
    return "\n\n".join(formatted)

def demo_rag_chain():
    """演示完整的 LCEL RAG 检索生成问答链"""
    console.print(Panel("[bold cyan]1. 构建 LCEL RAG 检索增强生成链[/bold cyan]", expand=False))
    
    raw_docs = prepare_knowledge_base()
    try:
        vectorstore = build_vector_store(raw_docs)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
        
        # 定义 RAG 专属 Prompt
        prompt = ChatPromptTemplate.from_template("""你是一家知名互联网大厂的资深架构师与规范审查员。
请根据以下严格提供的参考资料回答问题。如果参考资料中没有提及，请明确说明'规范中暂无规定'，严禁胡编乱造。

【参考资料】：
{context}

【用户提问】：
{question}

请给出专业、严谨且条理清晰的解答：""")

        llm = get_chat_model(temperature=0.1)
        
        # 现代 LCEL RAG 组装公式：
        rag_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        
        test_questions = [
            "我们在做新系统上线发布时，金丝雀发布的初始流量和观察时间是多少？",
            "开发人员为了方便，能不能把数据库连接密码直接写在 Python 脚本的 settings.py 里？"
        ]
        
        for q in test_questions:
            console.print(f"\n[bold green]❓ 用户提问：[/bold green]{q}")
            answer = rag_chain.invoke(q)
            console.print(f"[bold blue]💡 智能专家回答：[/bold blue]\n{answer}\n")
            console.print("-" * 40)
            
    except Exception as e:
        console.print(f"[red]RAG 演示报错（如未配置有效 Embeddings API）：{e}[/red]")

if __name__ == "__main__":
    console.print("[bold magenta]🚀 LangChain 1.x RAG 核心链路与向量检索增强演示[/bold magenta]\n")
    demo_rag_chain()
