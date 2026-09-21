import functools
import os
import re
import numpy as np
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

# 读取 FAQ 文本文件（基于源码位置解析路径，从任意目录启动都能找到）
from infra.paths import FAQ_PATH as faq_path
with open(faq_path, encoding='utf8') as f:
    faq_text = f.read()
# 将 FAQ 文本按标题分割成多个文档
docs = [{"page_content": txt} for txt in re.split(r"(?=\n##)", faq_text)]

# Embedding 模型通过环境变量配置（参见根目录 .env.example），避免硬编码密钥。
# 复用 OPENAI_API_KEY / OPENAI_API_BASE；若 Embedding 走独立服务，可单独设置：
# EMBEDDING_API_KEY、EMBEDDING_API_BASE、EMBEDDING_MODEL_NAME
embeddings_model = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small"),
    api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("OPENAI_API_KEY", "your-api-key-here")),
    base_url=os.getenv("EMBEDDING_API_BASE", os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")),
)


class VectorStoreRetriever:
    """把「向量检索 + 关键词兜底」包成一个符合检索接口的小类。

    :param docs: 切好的段落
    :param vectors: 每段的向量（Embedding 不可用时为 None）
    """
    def __init__(self, docs: list, vectors: list):
        """记下段落与向量。

        :param docs: 段落列表
        :param vectors: 与段落一一对应的向量列表
        """
        self._arr = np.array(vectors)
        self._docs = docs

    @classmethod
    def from_docs(cls, docs):
        """尝试建向量索引；Embedding 配不通就退回纯关键词。

        :param docs: 切好的段落
        :return: 检索器实例（自带 fallback 标记）
        """
        embeddings = embeddings_model.embed_documents([doc["page_content"] for doc in docs])
        return cls(docs, embeddings)

    def query(self, query: str, k: int = 5) -> list[dict]:
        """检索与问题最相关的几段。

        :param query: 用户问题
        :param k: 取几段
        :return: [{"text": ..., "score": ...}]，按分数降序
        """
        embed = embeddings_model.embed_query(query)
        scores = np.array(embed) @ self._arr.T
        k = min(k, len(self._docs))
        top_k_idx = np.argpartition(scores, -k)[-k:]
        top_k_idx_sorted = top_k_idx[np.argsort(-scores[top_k_idx])]
        return [
            {**self._docs[idx], "similarity": scores[idx]} for idx in top_k_idx_sorted
        ]


def _tokenize(query: str) -> list[str]:
    """把查询切成可比较的小词。

    中文没有空格，原来用 `[\\u4e00-\\u9fff]{2,}` 会把「怎么才能退票呢」整段当成
    一个 token，于是每段 FAQ 的命中次数都是 0，兜底检索退化成「永远返回前两段」。
    这里改成滑窗 2-gram：整句 → 怎么 / 么才 / 才能 / 能退 / 退票 / 票呢，
    「退票」就能命中退改签那一章。英文仍按单词切。
    """
    text = query.lower()
    tokens = re.findall(r"[a-z]{3,}", text)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return list(dict.fromkeys(tokens))          # 去重，避免同一个词重复计分


def _keyword_query(query: str, k: int = 2) -> list[dict]:
    """Embedding 不可用时的本地兜底：按中文 2-gram / 英文词在 FAQ 段落里打分。"""
    tokens = _tokenize(query)
    scored = []
    for doc in docs:
        text = doc["page_content"].lower()
        score = sum(text.count(token) for token in tokens) if tokens else 0
        scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [{**doc, "similarity": float(score)} for score, doc in scored[:k]]


@functools.lru_cache(maxsize=1)
def _get_retriever() -> VectorStoreRetriever:
    """懒加载检索器（首次调用才切段、算向量，之后返回同一个）。

    用 `lru_cache` 而不是「模块级变量 + global 重新绑定」：后者在别处
    `from tools.policy import _retriever` 时会抓到初始值 None 并且永远不变。
    顺带一个好处——构造过程抛异常时 lru_cache 不缓存失败结果，下次调用会重试，
    正好配合 `lookup_policy` 里的 try/except 兜底。

    :return: 检索器实例
    """
    return VectorStoreRetriever.from_docs(docs)


@tool
def lookup_policy(query: str) -> str:
    """查询公司政策，检查某些选项是否允许。
    在进行航班变更或其他'写'操作之前使用此函数。"""
    try:
        results = _get_retriever().query(query, k=2)
    except Exception:
        results = _keyword_query(query, k=2)
    return "\n\n".join([doc["page_content"] for doc in results])


if __name__ == '__main__':
    print(lookup_policy('怎么才能退票呢？'))
