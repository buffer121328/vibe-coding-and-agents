"""
s14_multimodal_rag.py
=====================
11.14 配套代码：多模态与垂直场景 RAG
痛点：知识不止是文字 → 图片描述文本化 + 命中原图 VLM 精读 + 跨语言嵌入 + 音频转写时间戳切块。
"""

import os

import base64
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


def build_time_windows(segments: list[dict], window_sec: int = 45, overlap_sec: int = 5) -> list[dict]:
    """把 ASR 片段合并成可检索时间窗，并保留说话人/置信度等元数据。"""
    if window_sec <= overlap_sec or overlap_sec < 0:
        raise ValueError("window_sec 必须大于 overlap_sec，且 overlap_sec 不能为负")
    chunks, current = [], []
    start = None
    emitted_end = -1.0
    for segment in segments:
        start = segment["start"] if start is None else start
        current.append(segment)
        if segment["end"] - start >= window_sec:
            chunks.append({
                "start": start,
                "end": segment["end"],
                "text": "".join(item["text"] for item in current),
                "min_confidence": min((item.get("confidence", 1.0) for item in current), default=1.0),
            })
            emitted_end = segment["end"]
            cutoff = segment["end"] - overlap_sec
            current = [item for item in current if item["end"] > cutoff]
            start = current[0]["start"] if current else None
    if current and current[-1]["end"] > emitted_end:
        chunks.append({
            "start": start,
            "end": current[-1]["end"],
            "text": "".join(item["text"] for item in current),
            "min_confidence": min((item.get("confidence", 1.0) for item in current), default=1.0),
        })
    return chunks


def validate_table_operation(operation: str) -> None:
    """表格工具只接受只读分析动作；真实 Text-to-SQL 还要数据库只读账号与行数预算。"""
    forbidden = ("insert", "update", "delete", "drop", "alter", "truncate", "写入", "删除")
    lowered = operation.lower()
    if any(token in lowered for token in forbidden):
        raise PermissionError("表格问答只允许只读计算")


def rows_to_documents(rows: list[dict], table: str, primary_key: str, unit_note: str = "",
                      updated_at: str = "") -> list[Document]:
    """结构化数据 RAG 路线①：每行拼成「列名: 值；列名: 值」的一句话，元数据带回表坐标与口径。

    空值列跳过；primary_key 列不存在时 metadata 里留空字符串，不抛异常。
    """
    docs = []
    for row in rows:
        sentence = "；".join(f"{col}: {val}" for col, val in row.items() if val)
        docs.append(Document(
            page_content=f"[表 {table}] {sentence}",
            metadata={
                "table": table,
                "primary_key": str(row.get(primary_key, "")),
                "unit_note": unit_note,
                "updated_at": updated_at,
                "columns": ",".join(row.keys()),
            },
        ))
    return docs


def flatten_json(obj, prefix: str = "") -> dict[str, str]:
    """把嵌套 JSON 展平成「字段路径 → 值」字典：dict 递归、list 用 [i] 下标、标量转 str。

    路径可写进元数据，引用「第 2 个商品的价格」时能顺着路径回到原始 JSON 核对；
    空 dict/list 保留为 "{}"/"[]"，避免信息被吞掉。
    """
    if isinstance(obj, dict):
        if not obj:
            return {prefix: "{}"}
        flat: dict[str, str] = {}
        for key, value in obj.items():
            flat.update(flatten_json(value, f"{prefix}.{key}" if prefix else str(key)))
        return flat
    if isinstance(obj, list):
        if not obj:
            return {prefix: "[]"}
        flat = {}
        for i, value in enumerate(obj):
            flat.update(flatten_json(value, f"{prefix}[{i}]"))
        return flat
    return {prefix: str(obj)}


def demo_structured_data() -> None:
    """演示结构化数据入库：CSV 行变成句子文档 + 嵌套 JSON 展平成路径字典。"""
    rows = [
        {"部门": "研发", "金额": "1200", "备注": ""},
        {"部门": "市场", "金额": "800", "备注": "客户招待"},
        {"部门": "行政", "金额": "300", "备注": ""},
    ]
    print("\n=== 结构化数据 RAG（行 → 句子文档）===")
    for doc in rows_to_documents(rows, table="报销明细", primary_key="部门", unit_note="金额单位：元"):
        print(doc.page_content, "|", doc.metadata)

    order = {"order_id": "SO-2026-0001", "order": {"items": [{"price": 19.9}, {"price": 5.0}]}}
    print("=== 嵌套 JSON 展平（路径 → 值）===")
    for path, value in flatten_json(order).items():
        print(f"{path} = {value}")


def demo_caption_image() -> None:
    """路线 A：给图片写“替身文本”，让图片内容也能被文本检索命中。"""
    from shared_corpus import make_llm
    vlm = make_llm(temperature=0, max_tokens=500)

    def caption_image(image_path: str) -> str:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        msg = ChatPromptTemplate.from_messages([
            ("user", [
                {"type": "text", "text": "用 2~3 句中文描述这张图的内容，"
                 "把图里的关键数字、步骤、结论都写出来。"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ])
        ])
        return vlm.invoke(msg.format_messages()).content

    print("=== 图片描述文本化 ===")
    demo_img = Path("img/demo_chart.png")
    if not demo_img.exists():
        demo_img.parent.mkdir(exist_ok=True)
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(5, 3))
            months = ["1月", "2月", "3月"]
            ax.bar(months, [0.31, 0.34, 0.29], color="#4f46e5")
            ax.set_title("Q1 gross margin")
            ax.set_ylabel("margin")
            fig.savefig(demo_img, dpi=120)
            print(f"（演示素材已生成：{demo_img}）")
        except ImportError:
            print("[跳过] 无本地图片且无 matplotlib，请放一张图片到 img/demo_chart.png")
            return
    try:
        print(caption_image(str(demo_img)))   # 换成任意本地图片
    except Exception as e:
        print(f"[当前端点不支持图片输入，跳过 VLM 精读] {type(e).__name__}")
        print("生产做法：给 VLM 端点（gpt-4o / qwen-vl 等）单独配 VISION_MODEL 环境变量")
        print("入库协议不变：page_content=f\"[图片] {描述}\"，metadata.image_ref 指向原图")
    print("入库：page_content=f\"[图片] {描述}\"，metadata 里存 image_ref 指向原图。")


def demo_cross_lingual() -> None:
    """跨语言检索：用 .env 里的多语言 Embedding 端点，让英文问题直接命中中文制度库。

    实现方式说明：
    - 默认走 API：`shared_corpus.make_embeddings()` 连接 .env 配置的 OpenAI 兼容
      Embedding 端点（如方舟 doubao-embedding），多语言模型天然支持跨语言检索；
    - 想本地部署（可选）：`pip install sentence-transformers` 后加载
      `SentenceTransformer("BAAI/bge-m3")`（约 2.3GB，[BGE-M3](https://huggingface.co/BAAI/bge-m3)），
      或用 Ollama/Xinference 等起一个 OpenAI 兼容的本地 Embedding 服务，
      再把 .env 的 OPENAI_API_BASE 指过去即可，代码零改动。
    """
    from shared_corpus import all_pages, find_page, make_embeddings
    import numpy as np

    emb = make_embeddings()
    # 真实制度页：REAL-RAG-TRAVEL-2026#p4《提交时限》
    zh_doc = find_page("REAL-RAG-TRAVEL-2026#p4", all_pages()).text[:120]
    q_en = "How many days to submit the expense report?"
    q_zh = "差旅报销单须在几天内提交？"

    doc_v = np.array(emb.embed_query(zh_doc))
    print(f"=== 跨语言检索（真实制度页：《提交时限》）===")
    for name, q in [("英文问题", q_en), ("中文问题", q_zh)]:
        q_v = np.array(emb.embed_query(q))
        sim = float(doc_v @ q_v / (np.linalg.norm(doc_v) * np.linalg.norm(q_v)))
        print(f"{name} 与《提交时限》页相似度 = {sim:.3f}")

    print("⚠️ 生成层补一条硬规则：用用户提问的语言回答，引用原文保持原文语言。")


def demo_transcribe() -> None:
    """音频 RAG：ASR 转写 → 时间窗切块 → 时间戳进元数据（搜到哪句跳到哪句）。"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("\n[跳过 faster-whisper] pip install faster-whisper")
        return

    def transcribe_with_timestamps(audio_path: str, window_sec: int = 45) -> list[dict]:
        model = WhisperModel("medium", compute_type="int8")
        segments, _ = model.transcribe(audio_path, language="zh", vad_filter=True)
        rows = [{"start": seg.start, "end": seg.end, "text": seg.text,
                 "confidence": getattr(seg, "avg_logprob", 0.0)} for seg in segments]
        return build_time_windows(rows, window_sec=window_sec, overlap_sec=5)

    print("=== 音频转写切块 ===")
    audio = Path("q3_review.mp3")
    if not audio.exists():
        print(f"[跳过] 无本地音频 {audio}——放任意中文音频后重跑即可看时间窗切块")
        return
    print(transcribe_with_timestamps(str(audio)))


def demo_table_policy() -> None:
    """表格问答的分工铁律：LLM 负责理解与表达，计算下放给代码。"""
    import pandas as pd

    from shared_corpus import make_llm
    df = pd.DataFrame({"月份": ["1月", "2月", "3月"],
                       "毛利率": [0.31, 0.34, 0.29]})
    from langchain_core.prompts import ChatPromptTemplate
    llm = make_llm(temperature=0)

    print("=== 表格问答 ===")
    validate_table_operation("SELECT 月份, 毛利率 FROM monthly_margin")
    # 反面示范：让 LLM 口算 “3 月环比变化多少” —— 容易算错
    # 正面示范：pandas 算，LLM 只解读
    delta = df["毛利率"].iloc[2] - df["毛利率"].iloc[1]
    resp = llm.invoke(ChatPromptTemplate.from_template(
        "表格计算结果：3 月毛利率环比变化 {delta:+.1%}。用一句人话向业务方解读。"
    ).format(delta=delta))
    print(resp.content)


if __name__ == "__main__":
    demo_caption_image()
    demo_cross_lingual()
    demo_transcribe()
    demo_table_policy()
    demo_structured_data()
