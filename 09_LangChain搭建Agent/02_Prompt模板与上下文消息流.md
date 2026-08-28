# 🎭 9.2 Prompt 模板与上下文消息流

> **“提示词不仅是一段字符串，更是带有结构、角色与上下文生命周期的动态场记本。”**  
> 在现代大模型应用中，简单粗暴的字符串拼接极易引发格式错乱与注入风险。本节我们将学习 LangChain 1.x 的 Prompt 模板系统与消息流模型。

---

## 💡 概念大白话：剧组台词提示器与对话场记本

### 1. 手工字符串拼接的灾难
在传统写法中，很多人习惯用 Python 的 `f"你是一个{role}，请回答：{user_input}"` 来拼提示词。但这会带来三大痛点：
- **角色混乱**：大模型无法准确区分哪些是系统核心人设（System），哪些是人类提问（Human），哪些是模型自己的历史回复（AI）；
- **动态多轮历史难以缝合**：多轮对话记录是一组列表，手动格式化非常繁琐且容易溢出；
- **少样本示例（Few-Shot）难以规范维护**。

### 2. 生活比喻：拍戏现场的提词器与场记板
- **`SystemMessage`（导演设定卡）**：告诉演员你在这场戏里演的是谁、有什么性格底线；
- **`HumanMessage`（对手演员的台词）**：对手说了一句话；
- **`AIMessage`（主角的回应）**：你上一场给出的台词；
- **`ToolMessage`（道具组送来的道具）**：执行工具返回的结果（如一张天气表、一份计算数据）；
- **`MessagesPlaceholder`（动态剧本插页）**：在剧本中间留一个活页夹，随时把之前的多轮对戏记录整体塞进去！

<!-- 图表源文件：img/diagrams/02-diagram-01.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/02-diagram-01.svg">
    <img src="img/diagrams/02-diagram-01.svg" alt="2. 生活比喻：拍戏现场的提词器与场记板" width="760">
  </a>
</p>

---

## 🏛️ LangChain 1.x 四大核心消息模型

在 `langchain_core.messages` 中，所有交互均统一封装为强类型的消息对象：

| 消息类名 | 对应角色 (Role) | 核心职责与应用场景 |
| :--- | :--- | :--- |
| **`SystemMessage`** | `system` | 设定模型的全局行为准则、人设风格、输出格式约束与安全防线。 |
| **`HumanMessage`** | `user` | 代表人类用户的输入或外部系统传递过来的原始查询。 |
| **`AIMessage`** | `assistant` | 模型生成的回复。若模型触发了工具调用，其 `tool_calls` 属性会包含工具调用元数据。 |
| **`ToolMessage`** | `tool` | 承载外部工具函数执行后的返回数据，必须附带对应 `tool_call_id`。 |

> 🆕 **1.x 补充**：
> - **模块化导入**：1.x 中 `langchain` 主包会重新导出常用消息类（如 `from langchain.messages import SystemMessage`），与 `langchain_core.messages` 等价，按需使用；
> - **AIMessage 内容块**：1.x 的 `AIMessage.content_blocks` 提供类型化的 `TextBlock` / `ReasoningBlock` / `CitationBlock`，可把“推理过程”与“最终答案”拆开处理；
> - **工具调用闭环四件套**：`AIMessage.tool_calls`（模型想调什么）→ `ToolMessage(tool_call_id=...)`（工具返回结果）→ 拼回消息列表 → 模型继续推理。这条链路正是 9.9 `create_agent` 的底层循环，LCEL 手写亦可复现。

---

## 💻 核心实操：ChatPromptTemplate 与 MessagesPlaceholder

### 1. 动态变量多角色模板

```python
# code/s02_prompt_and_messages.py
from langchain_core.prompts import ChatPromptTemplate

# 定义包含动态变量的 Prompt 模板
prompt_template = ChatPromptTemplate.from_messages([
    ("system", "你是一名精通 {domain} 领域的翻译专家，目标是将内容翻译为生动优雅的 {target_lang}。"),
    ("human", "请翻译以下文本：\n{source_text}")
])

# 传入字典变量，一键格式化为消息列表
messages = prompt_template.format_messages(
    domain="AI 智能体开发",
    target_lang="中文",
    source_text="LangChain provides standardized abstractions for agent workflows."
)
```

### 2. 使用 MessagesPlaceholder 动态注入历史多轮对话

在构建支持多轮对话的 Chatbot 或 Agent 时，最核心的能力就是**将动态长度的历史消息列表无缝塞入 Prompt**：

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

# 定义带占位符的模板
chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个幽默风趣的智能管家。"),
    MessagesPlaceholder(variable_name="history"), # 历史会话活页夹
    ("human", "{user_input}")
])

# 历史对话记录
chat_history = [
    HumanMessage(content="你好，我叫小明，我买的键盘一直没发货。"),
    AIMessage(content="小明你好！别着急，我已经帮你查到物流单号啦！")
]

# 渲染完整输入
rendered_input = chat_prompt.invoke({
    "history": chat_history,
    "user_input": "那我大概还要等多久能收到？"
})
```

### 3. Few-Shot 少样本提示词模板（让 AI 模仿专业输出）

```python
from langchain_core.prompts import FewShotChatMessagePromptTemplate, ChatPromptTemplate

# 1. 定义示例库
examples = [
    {"input": "这个手机电池真耐用", "output": "【正面评价】续航表现优异"},
    {"input": "屏幕边缘有划痕，差评！", "output": "【负面评价】外观品控瑕疵"}
]

example_prompt = ChatPromptTemplate.from_messages([
    ("human", "{input}"),
    ("ai", "{output}")
])

# 2. 组装少样本模板
few_shot_prompt = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    examples=examples
)

final_prompt = ChatPromptTemplate.from_messages([
    ("system", "请按照示例对用户评论进行情感与特征分类。"),
    few_shot_prompt,
    ("human", "{input}")
])
```

---

## 📚 权威官方资料直达

- 🔗 **Prompt 模板官方指南**：[LangChain Prompt Templates Documentation](https://docs.langchain.com/oss/python/langchain/prompts)
- 🔗 **消息模型官方概念**：[LangChain Messages Concepts](https://docs.langchain.com/oss/python/langchain/messages)
- 🔗 **Few-Shot 提示词官方实践**：[Few-shot Prompt Templates](https://docs.langchain.com/oss/python/langchain/prompts#few-shot-examples)

---

## 🎯 本节小结与思考

1. **核心收获**：掌握了四大消息对象、`ChatPromptTemplate` 动态变量渲染，以及 `MessagesPlaceholder` 动态会话注入机制。
2. **下一步探索**：有了 Prompt 和模型，我们该如何用最优雅的语法把它们串成一条工业级流水线，并支持并发和自动重试？下一节我们将学习 LangChain 最精髓的灵魂 —— **9.3 LCEL 表达式语言与流式调度**。
