# 🧩 9.1 初识 LangChain 1.x 与生态架构

> **“标准化与乐高积木化，是软件工程从手工作坊走向工业化大生产的必由之路。”**  
> 在手写了原生 Agent 之后，本节我们将推开现代化 LLM 框架的大门，探索 LangChain 1.x 是如何通过标准协议与模块化拆分，让 AI 应用开发像搭积木一样高效稳健。

---

## 💡 为什么需要 LangChain？（生活比喻篇）

### 1. 手写代码的痛点：自制万能充电线
在第八章中，我们通过原生 Python 一行行手搓了 Agent 的思考循环、工具分发和记忆管理。这非常有助于我们理解底层逻辑，但如果到了真实商业化开发中：
- 换一个模型厂商（如从 OpenAI 换到 Anthropic 或本地 Ollama），API 的传参格式、流式事件结构全都不一样，代码必须大改；
- 想把“提示词 ➔ 模型 ➔ 解析器 ➔ 工具 ➔ 记忆”串联起来，需要写大量嵌套的胶水代码（Glue Code）；
- 每次写异常重试、流式输出、Token 计费，都要重复造轮子。

### 2. 生活比喻：万能转换插头与标准化乐高积木
- **原生调用**：就像去不同国家旅行，每个国家的插座形状、电压都不一样，你得带十几种不同的插头和变压器；
- **LangChain**：就像一个**工业级万能转换插头**和一套**标准化乐高卡扣积木**。无论底层接入的是 DeepSeek、GPT 系列还是 Claude 系列（甚至本地 Ollama），对外暴露的调用方法全部统一为 `invoke()`、`stream()`、`batch()`；无论何种组件，只要符合 `Runnable` 协议，就能像乐高积木一样用一个管道符 `|` 咔哒一声拼装在一起！

<!-- 图表源文件：img/diagrams/01-diagram-01.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/01-diagram-01.svg">
    <img src="img/diagrams/01-diagram-01.svg" alt="2. 生活比喻：万能转换插头与标准化乐高积木" width="760">
  </a>
</p>

---

## 🏛️ LangChain 1.x 的架构演进与包拆分

在早期（0.0.x ~ 0.1.x 版本），LangChain 常被社区诟病“过于臃肿、黑盒过深、API 变动频繁”。  
自 **LangChain 0.3** 起官方进行了彻底的解耦重构，**2025 年 10 月正式发布 1.0**（要求 **Python 3.10+**），确立了“小而精的核心 + 独立伙伴包”的清晰架构：

| 核心组件库 | 官方定位与职责 | 核心作用与包含内容 |
| :--- | :--- | :--- |
| **`langchain-core`** | **最轻量基石层**（零外部重依赖） | 定义核心抽象接口：`Runnable` 协议、`BaseMessage` 消息模型、`ChatPromptTemplate` 模板、`@tool` 装饰器、输出解析器。保证核心 API 语义化版本极其稳定。 |
| **`langchain`** | **1.x 主框架层**（精简命名空间） | 只保留构建 Agent 的“标准接口”：`create_agent`、`init_chat_model` / `init_embeddings`、Agent 中间件（Middleware）、`langchain.tools` 等。 |
| **`langchain-classic`** | **1.x 向后兼容包** | 收纳旧版遗留代码：`LLMChain`、`ConversationChain`、`AgentExecutor`、`initialize_agent` 等（旧代码不升级时可安装此包过渡）。 |
| **`langchain-openai` / `langchain-chroma` / `langchain-tavily` …** | **厂商 / 生态独立伙伴包** | **`langchain-community` 已于 2026 年 6 月正式 Sunset（仓库归档）**，主流集成全部迁移到“一厂商一包”的独立伙伴包：OpenAI、Anthropic、Chroma 向量库、Tavily 搜索等，按需轻量安装。 |
| **`langchain-community`** | **（已 Sunset，仅遗留兼容）** | 曾承载第三方向量库、文档加载器、DuckDuckGo 等工具。**新项目请勿再依赖**，改用独立伙伴包或直接封装底层 API。 |
| **`langgraph`** | **复杂状态图与多智能体运行时** | LangChain 官方推荐的底层多轮状态循环、`checkpointer` 记忆与多 Agent 编排引擎（第十章重点）。 |
| **`langchain-text-splitters`** | **文本切块工具库** | `RecursiveCharacterTextSplitter` 等文档切分器（RAG 前置步骤）。 |

> 🚨 **2026 年生态现状提醒**：官方推荐“**生产环境只用 `langchain` + `langchain-core` + 独立伙伴包**”。本教程 9.8 的 Chroma 将使用 `langchain-chroma`，9.13 综合实战的联网搜索将使用 `ddgs`（DuckDuckGo 官方库）或 `langchain-tavily`，均已避开已归档的 `langchain-community`。

---

## 💻 快速实操：统一模型接入与三种调用姿势

无论使用的是 OpenAI 原生接口，还是国内托管平台（如字节跳动·火山方舟 DeepSeek、硅基流动、月之暗面），在 LangChain 1.x 中均可通过统一客户端快速接入。

### 1. 统一客户端工厂配置（推荐：init_chat_model）

LangChain 1.x 提供了官方统一的模型初始化入口 **`init_chat_model`**（位于 `langchain.chat_models`）。它支持 `"厂商:模型名"` 的写法，一行代码自动路由到对应伙伴包，无需关心类名与导入路径：

```python
# code/s01_model_io.py —— 1.x 官方推荐的统一工厂
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model  # 1.x 统一模型工厂

load_dotenv()

def get_chat_model_unified(temperature: float = 0.7):
    """统一模型初始化工厂：init_chat_model('厂商:模型') 一行接入任意厂商"""
    return init_chat_model(
        model=os.getenv("MODEL_NAME", "deepseek:deepseek-chat"),  # 厂商:模型 写法
        temperature=temperature,
        streaming=True,
    )
```

> 📌 **两种姿势对比**：
> - **`init_chat_model("deepseek:deepseek-chat")`** —— 1.x 官方推荐，自动识别 `deepseek` 厂商并加载 `langchain-deepseek` 伙伴包；
> - **`ChatOpenAI(base_url="https://api.deepseek.com/v1")`** —— 经典写法，适用于任意 **OpenAI 兼容端点**（火山方舟、硅基流动、DeepSeek、通义等），灵活设置 `base_url`。本教程 `s01_model_io.py` 的默认 `get_chat_model()` 沿用此工厂以兼容国内各家中转服务，并额外提供 `get_chat_model_unified()` 供你体验 1.x 统一写法，二者本质等价。

### 2. 三种核心调用模式对比

```python
llm = get_chat_model()

# 姿势 1：同步阻塞调用 invoke() —— 适合后台离线批处理
response = llm.invoke("请用一句话解释什么是 LangChain？")
print(response.content)

# 姿势 2：实时流式输出 stream() —— 适合交互式 Chatbot（丝滑打字机体验）
for chunk in llm.stream("写一首赞美程序员的打油诗。"):
    print(chunk.content, end="", flush=True)

# 姿势 3：高并发批量调用 batch() —— 适合多任务并行推理
responses = llm.batch(["用三个词形容 Python", "用三个词形容 Rust"])
for r in responses:
    print(r.content.strip())
```

### 3. 1.x 新特性速览：标准内容块（Standard Content Blocks）

1.x 为所有模型厂商统一了多模态/推理/引用等复杂输出的消息格式，新增 `AIMessage.content_blocks` 属性，可拿到**完全类型化**的 `text`、`reasoning`、`citations`、`tool_call` 等块，跨厂商零适配：

```python
resp = llm.invoke("9.4 与 9.9 谁大？请给出推理过程")
# 传统文本（跨版本兼容）
print(resp.content)
# 1.x 标准内容块（可分离“思考过程”与“最终答案”）
for block in resp.content_blocks:
    print(block.type, block)   # 如 TextBlock / ReasoningBlock ...
```

### 4. 模型能力档案（Model Profiles）：不调接口先摸清模型底细（1.1 新特性）

从 1.1 起，聊天模型暴露了 **`.profile`** 属性（数据来自开源项目 [models.dev](https://models.dev/)），**不用发请求、不消耗 Token** 就能知道这个模型支持什么、不支持什么——结构化输出？Tool Calling？多模态？上下文窗口多大？写代码前先查档案，就能自动决定“要不要加 JSON 解析兜底、能不能绑工具、能不能走原生结构化输出”：

```python
# code/s01_model_io.py —— demo_model_profiles()
llm = init_chat_model("openai:gpt-4o-mini", temperature=0)
profile = llm.profile                 # dict：模型能力出厂档案
print(profile["tool_calling"])        # True —— 支持工具调用
print(profile["structured_output"])   # True —— 原生结构化输出
print(profile["max_input_tokens"])    # 128000 —— 上下文窗口
```

> 💡 工程价值：不同模型能力差异巨大，手写硬编码极易踩坑。有了 `.profile`，你可以**根据模型能力自动降级/升级策略**；配合 9.9 的 `create_agent(response_format=...)`，结构化输出策略还能自动从模型档案推断（ProviderStrategy / strict）。

### 5. 跨厂商标准异常体系（1.3 工程化细节）

1.3 起 `create_agent` / `init_chat_model` 统一了**跨厂商异常分类**（Standard Model Exceptions），异常处理不再需要 catch 各种厂商私有错误。`langchain-openai` 还支持**显式 Prompt Caching**（提示词缓存，配合 9.7 成本审计更省钱）。

### 6. 动态模型选择与路由：同一套代码，按需切换大脑（1.x 进阶）

`create_agent(model=...)` 的 `model` 参数非常灵活——既可以传字符串标识符（`"openai:gpt-4o-mini"`），也可以传已初始化好的模型实例。更进一步，结合 **9.11 自定义中间件**，我们还能在**运行中按任务难度、成本预算或用户等级动态切换模型**——"简单问题用便宜小模型，复杂问题才出动旗舰模型"：

```python
# 示意：在 wrap_model_call 中间件里按需"换大脑"（完整机制见 9.11）
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from langchain.chat_models import init_chat_model

cheap_llm = init_chat_model("openai:gpt-4o-mini", temperature=0)
strong_llm = init_chat_model("openai:gpt-4o", temperature=0)

@wrap_model_call
def route_by_complexity(request: ModelRequest, handler) -> ModelResponse:
    last = request.messages[-1].content
    # 命中"深度分析/复杂推理"等信号时，动态切换到更强的模型
    request = request.override(model=strong_llm if "深度分析" in last else cheap_llm)
    return handler(request)
```

> 🧭 **三句话分清三种"换模型"**：
> | 能力 | 触发时机 | 一句话记忆 |
> | :--- | :--- | :--- |
> | **`with_fallbacks`**（9.3） | 主模型**调用失败后** | 备胎兜底，坏了才换 |
> | **`ModelFallbackMiddleware`**（9.7） | 主模型**调用失败后** | 中间件版的备胎兜底 |
> | **动态模型选择**（本节） | **每次调用前**按策略主动挑选 | 按需点将，未雨绸缪 |

---

## 📚 权威官方资料直达

- 🔗 **LangChain 官方首页（1.x 文档中心）**：[https://docs.langchain.com/](https://docs.langchain.com/)
- 🔗 **LangChain 1.x 发布说明**：[What's new in LangChain v1](https://docs.langchain.com/oss/python/releases/langchain-v1)
- 🔗 **LangChain 1.x 迁移指南**：[Migrate to LangChain v1](https://docs.langchain.com/oss/python/migrate/langchain-v1)
- 🔗 **模型能力档案（Model Profiles）**：[LangChain Models](https://docs.langchain.com/oss/python/langchain/models)
- 🔗 **LangChain 官方 GitHub 仓库**：[https://github.com/langchain-ai/langchain](https://github.com/langchain-ai/langchain)
- 🔗 **参考学习项目 (BrandPeng)**：[Langchain1.0-Langgraph1.0-Learning](https://github.com/BrandPeng/Langchain1.0-Langgraph1.0-Learning)

---

## 🎯 本节小结与思考

1. **核心收获**：掌握了 LangChain 1.x 的解耦架构哲学，学会了使用统一标准接口调用大模型并提取元数据，以及按需动态切换模型的"路由"思路。
2. **下一步探索**：模型已经跑通，如何优雅地组织 System 角色、用户输入与多轮对话历史？下一节我们深入学习 **9.2 Prompt 模板与上下文消息流**。
