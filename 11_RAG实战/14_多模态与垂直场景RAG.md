# 11.14 知识不止是文字 —— 多模态与垂直场景 RAG

> **痛点场景**：你以为知识库都是干净的 Word 文档，现实却是：产品手册的关键步骤**藏在截图里**；财务知识的核心是**一张张表格**；客服质检要搜**几万小时的通话录音**；海外团队要用英文问中文制度库。到这一节，前面 13 节的“文本 RAG”装备已经全部就位，本节处理四类最常见的高难度场景：**跨语言、表格问答、音视频 RAG、端侧部署。**

---

## 🩹 痛点：文字只是知识的“冰山一角”

| 场景 | 知识的真实形态 | 纯文本 RAG 的下场 |
| :--- | :--- | :--- |
| 产品手册/图纸 | 截图、流程图、图文混排 PDF | 图片直接被丢弃，答案漏掉关键步骤 |
| 财务/运营数据 | 多层表头、合并单元格的表格 | 切块把表格拆散，数字问答全错 |
| 客服/会议资产 | 通话录音、会议视频 | 压根没有文本层，无从入库 |
| 跨国团队 | 中文制度库，英文提问 | 英文问题检索不出中文答案 |

---

## 💡 思路：多模态 RAG 的三条技术路线

处理“非文字”知识，业界有三条路线，**按“信息离文字有多远”来选**：

<!-- 图表源文件：img/diagrams/14-diagram-01.mmd；视觉风格：House 统一风格 -->
<p align="center">
  <a href="img/diagrams/14-diagram-01.svg">
    <img src="img/diagrams/14-diagram-01.svg" alt="💡 思路：多模态 RAG 的三条技术路线" width="960">
  </a>
</p>

| 路线 | 怎么做 | 适合 | 代价 |
| :--- | :--- | :--- | :--- |
| **A. 文本化**（先翻译成文字） | OCR / 图片描述（captioning）/ ASR 转写后走普通文本 RAG | 信息主要承载在“内容”而非“版面” | 有损：图表结构、版面含义丢失 |
| **B. 多模态嵌入**（统一向量空间） | 用 CLIP / ColPali 把图片、页面整体嵌入，与文本同库检索 | 版面、图表结构本身有语义（11.11 的 ColPali） | 需要 GPU 索引多模态向量 |
| **C. 多模态大模型直读**（VLM 摘要/作答） | 检索命中的页面**原图**直接喂给多模态 LLM 作答 | 复杂图表推理、截图问答 | 每次调用贵，上下文占用大 |

> 💡 **实战中最常见的是 A+C 组合拳**：入库时给每张图/每页生成文本描述（路线 A，负责“搜得到”），命中后把原图一起喂给 VLM 精读（路线 C，负责“看得懂”）。纯路线 B 是 ColPali 阵营的玩法，适合扫描件大户。

---

## 🧑‍💻 代码实现一：图文混排 PDF 的“描述 + 直读”组合拳

```python
# 11.14 图文混排 RAG：图片文本化入库 + 命中原图给 VLM 精读
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

vlm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=500)

def caption_image(image_b64: str) -> str:
    """路线 A：入库前给图片写'替身文本'。让图片内容也能被文本检索命中。"""
    msg = ChatPromptTemplate.from_messages([
        ("user", [
            {"type": "text", "text": "用 2~3 句中文描述这张图的内容，"
             "把图里的关键数字、步骤、结论都写出来。"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ])
    ])
    return vlm.invoke(msg.format_messages()).content

# 入库：chunks += [Document(page_content=f"[图片] {caption_image(b64)}",
#                           metadata={"image_ref": "p7_img2.png", ...})]
# 检索：正常文本检索即可命中图片的替身文本
# 生成：命中后把 metadata 里 image_ref 指向的原图 + 问题一起交给 VLM 精读作答
```

---

## 🧑‍💻 代码实现二：跨语言 RAG —— 三种方案对号入座

“英文问题搜中文库”的本质是**让问题和文档落进同一个语义空间**：

| 方案 | 做法 | 适合 | 代表模型 |
| :--- | :--- | :--- | :--- |
| **多语言嵌入**（首选） | 嵌入模型天生跨语言，中英问题直接搜中文库 | 绝大多数场景 | [BGE-M3](https://github.com/FlagOpen/FlagEmbedding)、multilingual-e5 |
| **查询翻译** | 先把问题翻译成文档语言再检索 | 嵌入模型跨语言能力弱时的补救 | 任意翻译模型/LLM |
| **双语平行库** | 同一内容两个语言版本都入库 | 法务/合规要求“引用原文”的场景 | 解析管道加一道翻译 |

```python
# 11.14 跨语言检索：多语言嵌入一库通吃
from langchain_huggingface import HuggingFaceEmbeddings

emb = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")   # 100+ 语言对齐
# 中文文档入库后，英文问题可以直接命中：
# emb.embed_query("How many days to submit the expense report?")
#   ≈ emb.embed_query("差旅报销单须在几天内提交？")   余弦相似度极高
```

> ⚠️ **跨语言的隐藏坑在生成层**：检索命中了，但模型可能用英文回答中文文档。解法是在 11.12 的接地 Prompt 里加一条硬规则——“**使用用户提问的语言回答，引用原文保持原文语言**”。

---

## 🧑‍💻 代码实现三：音视频 RAG —— 时间戳就是你的元数据

音频/视频没有文本层，先转写、再切块、**把时间戳写进元数据**，检索结果就能直接跳转播放：

```python
# 11.14 音视频 RAG：ASR 转写 → 时间窗切块 → 带时间戳元数据入库
# pip install faster-whisper
from faster_whisper import WhisperModel

def transcribe_with_timestamps(audio_path: str, window_sec: int = 45) -> list[dict]:
    model = WhisperModel("medium", compute_type="int8")
    segments, _ = model.transcribe(audio_path, language="zh", vad_filter=True)
    # 按固定时间窗聚合：45 秒一个 chunk，块与块留 5 秒重叠
    chunks, buf, start = [], [], None
    for seg in segments:
        if start is None:
            start = seg.start
        buf.append(seg.text)
        if seg.end - start >= window_sec:
            chunks.append({"start": start, "end": seg.end, "text": "".join(buf)})
            buf, start = [], seg.end - 5   # 5 秒重叠，防止话被拦腰切断
    if buf:
        chunks.append({"start": start, "end": seg.end, "text": "".join(buf)})
    return chunks

# 入库：Document(page_content=c["text"],
#                metadata={"media": "q3_review.mp4", "start": c["start"], "end": c["end"]})
# 前端：拿到命中 chunk 的 start/end，播放器直接 seek 过去——这就是“搜到哪句跳到哪句”
```

视频再加一路：**用关键帧抽帧 + 实现代一的图片描述，让“画面里的事”也可检索**（比如“哪一页 PPT 讲了预算”）。ASR 引擎选型：本地/离线用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（Whisper 蒸馏加速版），云上可用各家语音转写 API，OpenAI Whisper 官方仓库见 [github.com/openai/whisper](https://github.com/openai/whisper)。

---

## 🚀 拓展：表格问答与端侧 RAG 速览

### 表格问答（Table QA）

表格是结构化数据，**不要用“切文本”的方式对待它**（呼应 11.2 的入库策略）：

| 问题类型 | 推荐打法 |
| :--- | :--- |
| “3 月的毛利率是多少？”（单点查找） | 表格行级嵌入 + 表头语义增强，命中后整行返回 |
| “哪个月环比增长最快？”（聚合/比较） | 别让 LLM 硬算——把表格转成 SQL（Text-to-SQL）或 pandas，让代码执行，LLM 只负责“读懂意图和解读结果” |
| 超宽表（上百列） | 先做列筛选（按表头语义挑相关列），再进生成，避免上下文爆炸 |

> 💡 **经验法则**：数字计算一律下放给工具（SQL/pandas），LLM 只做它擅长的“理解与表达”。让大模型口算 23×47，是对它最残忍的 misuse。

### 端侧 RAG（跑在自己电脑/手机上）

数据不出本地的场景（个人笔记、涉密行业、离线环境），用小模型全家桶组装：

| 组件 | 开箱即用方案 |
| :--- | :--- |
| 本地向量库 | [sqlite-vec](https://github.com/asg017/sqlite-vec)（SQLite 扩展，零部署） |
| 本地嵌入/生成模型 | [Ollama](https://ollama.com/) 一条命令拉模型，OpenAI 兼容接口 |
| 桌面知识库成品 | [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm)（11.10 选型地图里的“本地私有”选手） |

端侧的代价是模型小、上下文短——**切块要更小（11.2）、重排要更省（11.5）、生成层 Prompt 要更精简（11.12）**，本章所有“省着用”的技巧在端侧全部是刚需。

---

## 🔗 权威官方参考

- [BGE-M3：多语言多粒度嵌入（BAAI FlagEmbedding）](https://github.com/FlagOpen/FlagEmbedding)
- [ColPali：视觉文档检索（详见 11.11）](https://github.com/illuin-tech/colpali)
- [faster-whisper：本地快速语音转写（SYSTRAN）](https://github.com/SYSTRAN/faster-whisper)
- [OpenAI Whisper 官方仓库](https://github.com/openai/whisper)
- [sqlite-vec：SQLite 向量检索扩展](https://github.com/asg017/sqlite-vec)
- [Ollama：本地大模型一键运行](https://ollama.com/)
- [AnythingLLM：全栈本地 AI 知识库](https://github.com/Mintplex-Labs/anything-llm)
- [OpenCLIP：开源图文对齐模型实现](https://github.com/mlfoundations/open_clip)
