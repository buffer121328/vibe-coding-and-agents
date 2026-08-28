# ⚡ 9.3 LCEL 表达式语言与流式调度

> **“LCEL (LangChain Expression Language) 是 LangChain 从玩具走向工业级生产的最强进化。”**  
> 告别繁琐的嵌套调用，用 Unix 经典的管道符 `|`，像搭装配流水线一样将 Prompt、LLM、解析器、工具和容灾备份完美串联。

---

## 💡 为什么需要 LCEL？（生活比喻篇）

### 1. 传统嵌套调用的地狱
在早期的 AI 应用开发中，代码往往是层层嵌套的：
```python
# 传统的恶梦写法：可读性差，无法统一流式，无法自动并发，无法优雅容错
prompt_text = format_prompt(user_input)
raw_response = call_llm(prompt_text)
parsed_result = parse_output(raw_response)
db_result = save_to_db(parsed_result)
```
如果要在中间加入**流式打字机输出、多分支并行执行、异步并发、调用失败自动切换备用模型**，代码量会瞬间膨胀上百行。

### 2. 生活比喻：自动化工厂传送带与双路备用发电机
- **管道符 `|`**：就像工厂里的**标准化传送带**。上一个工位（Prompt 模板）加工完的半成品，通过传送带自动推给下一个工位（LLM 模型），再推给质检工位（解析器）；
- **`RunnableParallel`**：主传送带分叉出两条副线，一条做红烧、一条做清蒸，最后在打包台汇合；
- **`with_fallbacks`**：主发电机（例如 GPT-4o / 主接口）一旦跳闸断电，工厂毫秒级自动切换到备用柴油发电机（DeepSeek 备用线路），生产线绝不停工！

<!-- 图表源文件：img/diagrams/03-diagram-01.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/03-diagram-01.svg">
    <img src="img/diagrams/03-diagram-01.svg" alt="2. 生活比喻：自动化工厂传送带与双路备用发电机" width="760">
  </a>
</p>

---

## 🏛️ LCEL 的核心基石：Runnable 协议族

在 LCEL 体系中，每一个参与组装的组件（Prompt、LLM、Retriever、Parser、自定义函数）都实现了标准的 **`Runnable` 协议**。这意味着所有组件天然拥有一致的 6 大调用方法：

| 调用方法 | 同步 / 异步 | 核心应用场景与特性 |
| :--- | :--- | :--- |
| **`invoke(input)`** | 同步 | 传入单条数据，返回单一结果。适合离线处理。 |
| **`ainvoke(input)`** | 异步 (async) | 基于 `asyncio` 的异步单条调用，高并发 Web 服务首选。 |
| **`stream(input)`** | 同步生成器 | 实时返回 Iterator 流式 Chunk 数据块，实现打字机效果。 |
| **`astream(input)`** | 异步生成器 | 异步流式输出，配合 FastAPI / SSE 实时推送到前端。 |
| **`batch(inputs)`** | 同步批量 | 传入列表，LangChain 内部自动进行并发加速。 |
| **`abatch(inputs)`** | 异步批量 | 高性能批量异步并发。 |

---

## 💻 核心实操：LCEL 高级用法清单

### 1. 最基础的 LCEL 链：Prompt | LLM | StrOutputParser

```python
# code/s03_lcel_chains.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from s01_model_io import get_chat_model

prompt = ChatPromptTemplate.from_template("请用一句话幽默解释 {concept} 的本质。")
llm = get_chat_model()
parser = StrOutputParser() # 自动提取 AIMessage.content 字符串

# 优雅的 LCEL 组装
chain = prompt | llm | parser

# 一行调用！
result = chain.invoke({"concept": "递归函数"})
print(result)
```

### 2. 多任务并行分支：RunnableParallel 与 RunnablePassthrough

```python
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

# 分支 1：写赞美诗
poem_chain = ChatPromptTemplate.from_template("为主题 '{topic}' 写两句赞美诗。") | llm | parser

# 分支 2：写吐槽
roast_chain = ChatPromptTemplate.from_template("为主题 '{topic}' 写两句程序员视角的吐槽。") | llm | parser

# 并行管道
parallel_chain = RunnableParallel({
    "topic": RunnablePassthrough(), # 原样透传用户输入
    "praise": poem_chain,           # 并行执行分支 1
    "roast": roast_chain            # 并行执行分支 2
})

# 汇聚链
summary_prompt = ChatPromptTemplate.from_template(
    "【主题】：{topic}\n【赞美】：{praise}\n【吐槽】：{roast}\n请给出 20 字以内客观综合结语。"
)

full_pipeline = parallel_chain | summary_prompt | llm | parser
print(full_pipeline.invoke({"topic": "加班文化"}))
```

### 3. 容灾降级与双活高可用：with_fallbacks

在生产环境中，任何外部大模型都有可能遇到网络超时、限流（429）或服务不可用（503）。LCEL 原生提供了极简的容灾机制：

```python
from langchain_openai import ChatOpenAI

# 主模型（可能因网络或额度异常故障）
primary_llm = ChatOpenAI(model="gpt-4o", timeout=5, max_retries=1)

# 备用模型（火山方舟 DeepSeek 或本地模型）
backup_llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key="your_key"
)

# 一行代码配置容灾降级！
resilient_llm = primary_llm.with_fallbacks([backup_llm])

safe_chain = ChatPromptTemplate.from_template("解释高可用架构：{topic}") | resilient_llm | parser
# 若 primary_llm 报错，内部自动捕获并无缝由 backup_llm 补位执行
print(safe_chain.invoke({"topic": "金融支付网关"}))
```

### 4. LCEL 进阶补充：分支路由、自动重试与事件流（1.x 依旧核心）

LCEL 在 1.x 中依然是编排的灵魂（`create_agent` 底层同样是 LangGraph 状态机，但链式场景仍首选 LCEL）。以下三个高频武器建议一并掌握：

```python
from langchain_core.runnables import RunnableBranch, RunnableLambda

# 4.1 RunnableBranch：按条件动态路由（替代 if-else）
route = RunnableBranch(
    (lambda x: "天气" in x, 天气链),   # (条件, 对应链)
    (lambda x: "汇率" in x, 汇率链),
    默认闲聊链,                          # 兜底分支
)

# 4.2 with_retry：调用失败自动重试（应对 429 / 5xx 瞬时抖动）
retry_llm = llm.with_retry(stop_after_attempt=3, wait_exponential_jitter=False)

# 4.3 astream_events：异步事件流，可实时捕获链内每一步的
#     on_chat_model_start / on_parser_end 等事件（可用于前端进度条、日志审计）
async for event in chain.astream_events({"concept": "递归"}, version="v2"):
    if event["event"] == "on_chat_model_stream":
        print(event["data"]["chunk"].content, end="")
```

> 🆕 **1.3 升级：新一代 v3 流式协议**。链式场景仍用 `version="v2"`；而 **Agent（`create_agent`）** 在 1.3 起接入全新的 **`astream_events(..., version="v3")`** —— 事件结构更统一、更细粒度（含 Agent 节点级事件），适合前端实时渲染思考/工具调用过程。用法见 9.9（`code/s09_modern_agent.py` 的 `demo_stream_v3()`）。

---

## 📚 权威官方资料直达

- 🔗 **LCEL 官方概念与设计哲学**：[LangChain Expression Language (LCEL)](https://docs.langchain.com/oss/python/langchain/lcel)
- 🔗 **Runnable 协议接口规范**：[Runnable Interface Documentation](https://docs.langchain.com/oss/python/langchain/lcel#runnable-interface)
- 🔗 **Fallbacks 容灾降级实践**：[How to add fallbacks to a runnable](https://docs.langchain.com/oss/python/langchain/lcel#fallbacks)

---

## 🎯 本节小结与思考

1. **核心收获**：理解了 LCEL 管道符 `|` 的底层哲学，掌握了 `RunnableParallel` 并行分支与 `with_fallbacks` 企业级高可用容灾。
2. **下一步探索**：大模型吐出的文本虽然生动，但后端代码往往需要严格的 JSON 或强类型对象（如获取结构化财报、用户信息）。下一节我们学习 **9.4 结构化输出与容错解析**。
