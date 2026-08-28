# 🤖 9.9 Agent 现代架构与 create_agent

> **“Chain 是按固定路线行驶的火车，而 Agent 是拥有 GPS、方向盘和随时变道能力的自动驾驶汽车。”**  
> 在 LangChain 1.x 中，Agent 的构建方式迎来了彻底的现代化变革：基于底座模型的 Tool Calling 协议与 LangGraph 运行时，实现高可靠的自主推理与工具调用闭环。

---

## 💡 概念大白话：固定铁轨与自动驾驶汽车

### 1. Chain 链与 Agent 智能体的本质区别
- **Chain（固定流水线）**：步骤是人类写死的（先翻译 ➔ 再摘要 ➔ 再存库）。无论遇到什么输入，都必须机械执行这三步；
- **Agent（自主决策体）**：大模型根据用户的具体目标，自主规划“第一步调用什么工具、看结果再决定第二步调用什么工具、何时得出结论并向人类汇报”。

### 2. 生活比喻：高级私人秘书与他的工作草稿本
- **`create_agent`（秘书总监）**：1.x 的标准入口，一条命令就把“大脑（模型）+ 双手（工具）+ 记忆（checkpointer）+ 规则（system_prompt）”装配成一位能自主办事的秘书；
- **LangGraph 状态机（秘书的办公流程）**：秘书的每一步（思考 → 动手 → 看结果 → 再思考）都由底层状态图自动循环驱动，无需手工写 while 循环；
- **`messages` 消息流水线（秘书的工作日志）**：每次调用的结果是一条完整消息流水线 —— `HumanMessage`（老板吩咐）→ `AIMessage.tool_calls`（秘书决定叫哪个部门）→ `ToolMessage`（部门回执）→ `AIMessage`（最终汇报）。审计只需逐条阅读这条流水线；
- **ReAct 推理循环**：
  1. **Thought（思考）**：分析现状与缺少的关键数据；
  2. **Action（行动）**：决定调用哪个具体工具并传递参数；
  3. **Observation（观察）**：读取工具返回的结果，合并进上下文，决定是否继续循环或输出最终答案。

<!-- 图表源文件：img/diagrams/09-diagram-01.mmd；视觉风格：Pastel 多巴胺 -->
<p align="center">
  <a href="img/diagrams/09-diagram-01.svg">
    <img src="img/diagrams/09-diagram-01.svg" alt="2. 生活比喻：高级私人秘书与他的工作草稿本" width="760">
  </a>
</p>

---

## 🏛️ LangChain 1.x Agent API 演进

LangChain 官方对 Agent API 进行了大规模规范化：

| API 版本 | 使用方式 | 状态与评价 |
| :--- | :--- | :--- |
| **远古时代 (<= 0.1.x)** | `initialize_agent(agent_type="zero-shot-react-description")` | ❌ **已废弃**。基于脆弱的纯文本正则匹配，极易解析崩溃。 |
| **0.3 过渡期** | `create_tool_calling_agent(llm, tools, prompt)` + `AgentExecutor` | ⚠️ **已迁至 `langchain-classic`**。基于模型原生 Function Calling 协议，但执行器已随 1.x 移除。 |
| **1.x 现代化新接口** | `from langchain.agents import create_agent` | 🌟 **当前唯一官方标准**。底层直接基于 LangGraph 状态机运行时构建，内置 Tool Calling 循环、错误自愈、Checkpointer 记忆与中间件。 |

> 🔑 **一句话记忆**：`AgentExecutor` 是 0.3 时代负责“循环执行”的引擎；1.x 把它彻底内化进 `create_agent`（LangGraph 状态机）。新版**不再需要** `AgentExecutor`、`agent_scratchpad` 占位符，`return_intermediate_steps` 也不再是必要参数。

---

## 💻 核心实操：构建多功能现代 Tool Calling Agent

### 1. 组装工具集（@tool 或普通函数皆可）

```python
# code/s09_modern_agent.py
import math
from langchain_core.tools import tool
from s01_model_io import get_chat_model

# 1. 准备多模工具（create_agent 也接受普通 Python 函数）
@tool
def calculate_expression(expression: str) -> str:
    """数学表达式求值计算器。支持加减乘除、乘方、括号运算。"""
    try:
        allowed = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        return f"计算结果: {eval(expression, {'__builtins__': {}}, allowed)}"
    except Exception as e:
        return f"计算出错: {e}"

@tool
def query_weather(city: str) -> str:
    """查询指定城市的实时气象与穿衣出行建议。"""
    weather_map = {"上海": "上海今天小雨，气温 22°C ~ 26°C，建议带伞。"}
    return weather_map.get(city, f"未收录城市 {city} 的天气。")

@tool
def currency_converter(amount: float, from_curr: str, to_curr: str) -> str:
    """实时汇率转换工具 (支持 USD, CNY, EUR)。"""
    rates = {"USD": 7.25, "EUR": 7.85, "CNY": 1.0}
    cny = amount * rates[from_curr.upper()]
    target = cny / rates[to_curr.upper()]
    return f"{amount} {from_curr} = {target:.2f} {to_curr}"
```

### 2. 一行创建 1.x 标准 Agent（create_agent）

```python
from langchain.agents import create_agent

tools = [calculate_expression, query_weather, currency_converter]
llm = get_chat_model(temperature=0.1)

# 1.x 标准姿势：无需 AgentExecutor / agent_scratchpad
agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt="你是一位顶级智能私人助理。涉及天气、汇率和算术时严禁盲猜，必须调用对应工具！",
)

# 2. 以消息列表方式传入复合多任务指令
query = "我打算去上海玩 3 天，查下天气；另外预定每晚 180 美元的酒店，住 3 晚折合人民币多少钱？"
response = agent.invoke({"messages": [("user", query)]})

# 3. 取最终答复（结果是一个“完整消息列表”，最后一条即最终回答）
print("最终回答：\n", response["messages"][-1].content)
```

### 3. 推理审计：从 messages 中还原工具调用链

`create_agent` 的结果本身就是一条**完整的消息流水线**（用户提问 → AI 发起工具调用 → 工具返回 → AI 最终答复）。逐一打印即可审计每一步推理：

```python
print("\n--- 🔍 Agent 思考与工具调用链明细 ---")
for msg in response["messages"]:
    if msg.type == "ai" and msg.tool_calls:
        for tc in msg.tool_calls:
            print(f"🧠 思考：调用工具 [{tc['name']}]，参数 {tc['args']}")
    elif msg.type == "tool":
        print(f"⚙️ 工具返回: {msg.content}")
    elif msg.type == "ai":
        print(f"💬 AI: {msg.content}")
```

### 4. 流式输出与事件流

```python
# 逐 token 流式（打字机效果）
async for chunk in agent.astream({"messages": [("user", query)]}, stream_mode="values"):
    last = chunk["messages"][-1]
    if last.type == "ai" and last.content:
        print(last.content, end="", flush=True)
```

### 5. system_prompt 支持 SystemMessage 实例（1.1）

`create_agent(..., system_prompt=...)` 除了字符串，还能直接传 **`SystemMessage` 对象**，方便程序化组合系统指令（配合中间件动态修改系统提示时也更内聚）：

```python
# code/s09_modern_agent.py —— build_modern_agent()
from langchain_core.messages import SystemMessage

system_prompt = SystemMessage(
    content="""你是一位精通多领域的超级智能私人助理。
遇到任何涉及数学算术、实时天气、汇率计算的问题时，请严格调用对应的工具，绝不自行盲猜！"""
)
agent = create_agent(model=llm, tools=tools, system_prompt=system_prompt)
```

### 6. 中间件：给 Agent 一键加装生产级可靠性（1.1）

配合 9.7 讲到的官方预置中间件，`create_agent` 可直接装配 `ModelRetryMiddleware`（弱网/429/5xx 自动重试），不再需要手写重试逻辑：

```python
# code/s09_modern_agent.py —— build_modern_agent()
from langchain.agents.middleware import ModelRetryMiddleware

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=system_prompt,
    middleware=[ModelRetryMiddleware(max_retries=2)],
)
```

### 7. response_format：整个 Agent 的最终答复强制结构化（1.1+）

9.4 讲的是“单次 LLM 调用”结构化；`create_agent(..., response_format=Pydantic模型)` 则让**整个 Agent 跑完所有工具调用后的最终答复**都强转成该 Schema —— 非常适合“对话结束后自动生成报表/单据”：

```python
# code/s09_modern_agent.py —— demo_structured_response()
from pydantic import BaseModel, Field

class FinalAnswer(BaseModel):
    summary: str = Field(description="最终中文总结")
    key_points: list[str] = Field(description="3~5 条关键要点")
    used_tools: list[str] = Field(description="本次调用过的工具名列表")

agent = create_agent(model=llm, tools=[...], system_prompt="...", response_format=FinalAnswer)
res = agent.invoke({"messages": [("user", "请帮我算一下 125 × 38.5 ÷ 1.05² 的结果")]})
print(res["messages"][-1].content)   # 已符合 FinalAnswer 的 JSON
```

### 8. v3 流式协议：更细粒度的 Agent 级事件流（1.3）

1.3 为 `create_agent` 接入全新的 **`astream_events(..., version="v3")`**（链式场景仍用 9.3 的 `version="v2"`），事件结构更统一、含 Agent 节点级事件，适合前端实时渲染思考与工具调用过程：

```python
# code/s09_modern_agent.py —— demo_stream_v3()
async for event in await agent.astream_events({"messages": [("user", "上海天气如何？")]}, version="v3"):
    if "on_chat_model_stream" in event["event"]:
        chunk = event["data"].get("chunk")
        if chunk is not None and getattr(chunk, "content", None):
            print(chunk.content, end="", flush=True)
```

> ⚠️ 注意：`CompiledStateGraph.astream_events` 返回的是**协程**，需先 `await` 拿到异步迭代器再遍历。

### 9. 中间件进阶：动态工具注册与 HITL 精细决策（1.3）

1.3 给中间件新增两项能力，让 Agent 更聚焦、更可控：

- **动态工具注册**：中间件可在运行中**按需动态注册/卸载工具**（对应 Anthropic “Agent Skills / 渐进式披露”思路），不必在创建时一次列全所有工具——上下文更省、Agent 更聚焦。
- **HITL `respond` 决策**：`HumanInTheLoopMiddleware`（人类在环）新增 `respond` 分支决策，可精细控制“哪些工具调用需要人工确认、哪些直接放行”。

```python
from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware

# 示意：仅对"删除/付款"等高危工具要求人工确认
agent = create_agent(
    model=llm,
    tools=tools,
    middleware=[HumanInTheLoopMiddleware()],
)
```

### 10. AgentState 自定义状态：给 Agent 加一本私房账本（`state_schema`）

每个 Agent 内部都维护一份 **`AgentState`**（TypedDict），内置 `messages` 字段（**只增不改**的完整对话历史）。当你想在运行中额外跟踪 `user_id`、调用次数、业务计数器时，只需子类化 `AgentState` 并通过 `state_schema=` 注入：

```python
# code/s09_modern_agent.py —— demo_custom_state()
from langchain.agents import AgentState, create_agent
from typing_extensions import NotRequired

class MyState(AgentState):
    user_id: NotRequired[str]      # NotRequired：可选自定义字段
    call_count: NotRequired[int]

agent = create_agent(model=llm, tools=tools, state_schema=MyState)

# invoke 时把自定义字段作为初始状态一并传入
result = agent.invoke({
    "messages": [("user", "你好，我是谁？")],
    "user_id": "user-123",
    "call_count": 0,
})
```

> 🔑 **工程价值**：这些自定义字段对**中间件完全可见**——9.11 会讲到，`before_model` / `after_model` / `wrap_model_call` 的 `state` 参数里都能直接 `state["user_id"]`、`state["call_count"]`，从而实现"按调用次数限流熔断""按用户等级动态切换模型/工具"等高级控制。`AgentState` 也是所有中间件钩子的标准签名。

### 11. 人类在环 HITL：高危操作必须签字画押（完整流程）

对"发邮件、删库、付款"等高危工具，`HumanInTheLoopMiddleware` 能让 Agent **在执行前暂停**，等人类批准后才继续。完整姿势 = `interrupt_on`（声明哪些工具要审批）+ `checkpointer`（中断后能恢复）+ `Command(resume=...)`（人工批准/拒绝）：

```python
# code/s09_modern_agent.py —— demo_hitl()
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

agent = create_agent(
    model=llm,
    tools=[search, send_email, delete_database],
    middleware=[HumanInTheLoopMiddleware(
        interrupt_on={"send_email": True, "delete_database": True},  # 高危工具需审批
    )],
    checkpointer=InMemorySaver(),   # 必须有 checkpointer，中断状态才能持久化
)

config = {"configurable": {"thread_id": "user_1"}}
# 第一次调用：Agent 规划到 send_email 时自动暂停，返回中断信息等待人类
result = agent.invoke({"messages": [("user", "帮我给团队发一封会议通知邮件")]}, config=config)

# 人类审阅后，用同一 thread_id 恢复执行（approve 放行 / reject 拒绝）
result = agent.invoke(
    Command(resume={"decisions": [{"type": "approve"}]}),
    config=config,
)
```

> 💡 **三句话记忆**：`interrupt_on` 是"审批白名单"；`checkpointer + thread_id` 是"中断后的存档点"；`Command(resume=...)` 是"签字后的放行条"。

> 💡 **旧代码迁移对照（0.3 → 1.x）**：
> | 0.3 写法 | 1.x 写法 |
> | :--- | :--- |
> | `from langchain.agents import create_tool_calling_agent, AgentExecutor` | `from langchain.agents import create_agent` |
> | `agent = create_tool_calling_agent(llm, tools, prompt)` | `agent = create_agent(model=llm, tools=tools, system_prompt=...)` |
> | `agent_executor = AgentExecutor(agent=agent, tools=tools, ...)` | 不再需要；`create_agent` 即完整可调用对象 |
> | `agent_executor.invoke({"input": query})` | `agent.invoke({"messages": [("user", query)]})` |
> | `response["output"]` | `response["messages"][-1].content` |
> | `response["intermediate_steps"]` | 遍历 `response["messages"]` 中的 `tool_calls` / `tool` 消息 |
> | `MessagesPlaceholder(variable_name="agent_scratchpad")` | 由运行时自动维护，无需占位符 |

---

## 📚 权威官方资料直达

- 🔗 **LangChain Agent 架构官方概念**：[LangChain Agents Overview](https://docs.langchain.com/oss/python/langchain/agents)
- 🔗 **create_agent 官方指南**：[Build an Agent with create_agent](https://docs.langchain.com/oss/python/langchain/agents)
- 🔗 **LangChain 1.x Agent 迁移指南**：[Migrate to create_agent](https://docs.langchain.com/oss/python/migrate/langchain-v1#migrate-to-create_agent)
- 🔗 **Agent 中间件（含官方预置）**：[LangChain Agent Middleware](https://docs.langchain.com/oss/python/langchain/agents#middleware)
- 🔗 **人类在环（HITL）官方指南**：[Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- 🔗 **LangGraph 智能体运行时**：[LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)

---

## 🎯 本节小结与思考

1. **核心收获**：掌握了 LangChain 1.x 标准 Agent 入口 `create_agent`（`model` + `tools` + `system_prompt` + 可选 `checkpointer` / `middleware` / `response_format` / `state_schema`），学会了通过 `messages` 消息流水线进行工具调用链推理审计，掌握了 `AgentState` 自定义状态与 HITL 人类在环的完整审批流程，以及 0.3 → 1.x 的完整迁移对照。
2. **下一步探索**：现在我们已经掌握了 LangChain 1.x 的全部核心零件！下一节我们将继续深入**上下文工程与动态上下文注入**——如何给 Agent 在正确时机递上正确的上下文。
