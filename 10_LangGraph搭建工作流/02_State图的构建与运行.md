# 10.2 State 图的构建与运行

上一节把 LangGraph 比作一张飞行棋棋盘。这一节把棋盘画出来，并让数据在格子之间跑起来。构建图的四步曲几乎永远不变：

**定义 State → 添加 Node → 画 Edge → `compile()`。**

真正容易踩坑的，不是这四步的顺序，而是：**状态怎么合并、哪些东西不该进状态、运行时上下文往哪放。**

---

## 1. 定义状态：大家共用的交接本

每个节点只做三件事：**读当前状态 → 干活 → 返回想更新的字段**。为了让下一格看到的内容一致，先约定交接本的格式。最常见的写法是 `TypedDict`：

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class State(TypedDict):
    # add_messages：新消息追加进去，而不是把旧对话整页覆盖掉
    messages: Annotated[list, add_messages]
    destination: str
```

`add_messages` 是一个 **reducer（合并器）**。每个字段都有自己的合并规则：

- 普通字段默认是**后写覆盖前写**；
- 带 reducer 的字段按函数合并：`新值 = reducer(当前值, 本次更新)`。

不加 `add_messages`，模型每次回复都会把历史对话抹掉；加上它，新消息会排在旧消息后面，同 ID 的消息则按 ID 覆盖（适合修正一条已发出的工具回执）。

写小例子时，还可以直接用官方预置的 [`MessagesState`](https://docs.langchain.com/oss/python/langgraph/graph-api)：它只有 `messages` 一个字段，并且已经配好 `add_messages`。要加业务字段，继承它即可：

```python
from langgraph.graph import MessagesState

class TripState(MessagesState):
    destination: str
    budget: int
```

> 📌 状态不是“大家随便改的全局变量”。节点返回的是**这一步希望更新的部分**，LangGraph 再按字段规则合并。设计时建议给每个字段写清三件事：谁负责写入、哪些节点会读、冲突时怎么合并。

---

## 2. 定义节点：读本子、干活、交回增量

节点就是普通 Python 函数。输入是当前 State，输出是一份**增量字典**：

```python
from langchain.chat_models import init_chat_model

llm = init_chat_model("openai:gpt-4o-mini", temperature=0)

def agent_node(state: State):
    """思考节点：读完整对话，追加一条模型回复"""
    response = llm.invoke(state["messages"])
    return {"messages": [response]}
```

只返回需要改的字段。没提到的字段保持原样。

1.x 里节点还可以多收两个可选参数：

| 参数 | 类型 | 放什么 |
| :--- | :--- | :--- |
| `state` | 你的 State | 业务快照：消息、订单号、分类结果 |
| `config` | `RunnableConfig` | 运行配置，例如 `thread_id`、`recursion_limit` |
| `runtime` | `Runtime[Context]` | 运行时对象：上下文、Store、stream writer |

数据库连接、模型客户端、当前用户的租户 ID，**不要塞进 State**。那些东西不能（或不该）被存档。官方做法是 `context_schema` + `runtime.context`，下一小节展开。

---

## 3. 把节点连起来，编译成可运行的图

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)
builder.add_node("assistant", agent_node)
builder.add_edge(START, "assistant")
builder.add_edge("assistant", END)

graph = builder.compile()
```

`START` / `END` 是虚拟边界，不是你写的业务函数。`compile()` 会检查结构（比如有没有悬空节点），并挂上 Checkpointer、缓存等运行时插件。图必须编译后才能 `invoke` / `stream`。

运行：

```python
initial_state = {"messages": [("user", "你好，帮我看一下明天去杭州的票")]}

for event in graph.stream(initial_state):
    print("-------")
    print(event)
```

`stream` 每走完一个节点就吐出一份更新，比干等 `invoke` 的最终结果好调试得多。可视化与流式细节见 05 节。

---

## 4. 条件边：十字路口先打个样

直来直去的图很快就会不够用。`add_conditional_edges` 让一个节点走完后，根据状态选择下一格：

```python
def route_logic(state: State):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools_node"
    return END

builder.add_conditional_edges(
    "assistant",
    route_logic,
    ["tools_node", END],
)
```

三个参数分别是：从哪出发、路由函数、可能去哪些地方。路由函数应保持只读；把“决策算清楚”和“按字段指路”拆开，会好测得多。完整讲法在 03 节。

同一节点不要既画固定边、又用条件边 / `Command` 动态跳转——两条路可能同时触发。官方明确不建议混用。

---

## 5. 1.x 容易漏掉的三块：Runtime、Schema、Overwrite

旧教程几乎只讲 `TypedDict` + `add_messages`。对照 [Graph API 文档](https://docs.langchain.com/oss/python/langgraph/graph-api)，下面三块已经是正式知识，不是边角料。

### 5.1 Runtime 上下文：运行时配置不要写进交接本

用户 ID、模型提供商、数据库客户端，属于**这次运行的环境**，不是业务状态。用 `context_schema` 声明，调用时传入 `context=`，节点从 `runtime.context` 读取：

```python
from dataclasses import dataclass
from langgraph.runtime import Runtime

@dataclass
class Context:
    user_id: str
    llm_provider: str = "openai"

def assistant(state: State, runtime: Runtime[Context]):
    provider = runtime.context.llm_provider
    # 按租户选模型、查权限，而不是把连接对象写进 State
    return {"messages": [("assistant", f"当前通道：{provider}")]}

builder = StateGraph(State, context_schema=Context)
graph = builder.compile()
graph.invoke(
    {"messages": [("user", "你好")]},
    context={"user_id": "u_42", "llm_provider": "deepseek"},
)
```

和第九章的“三类上下文”是同一思路：State 存对话与业务字段，Store 存跨会话档案，Runtime 上下文存货到这次请求、但不必快照的东西。

### 5.2 输入 / 输出 Schema：对外只暴露该暴露的字段

默认情况下，`invoke` 的入参和出参都是整份内部 State。生产接口往往只想收 `question`，只想返回 `answer`，中间的检索草稿、重试计数不必泄漏。可以拆成三份类型：

```python
class InputState(TypedDict):
    question: str

class OutputState(TypedDict):
    answer: str

class OverallState(TypedDict):
    question: str
    drafts: list[str]
    answer: str

builder = StateGraph(
    OverallState,
    input_schema=InputState,
    output_schema=OutputState,
)
```

节点内部仍可读写 `drafts`；`invoke` 的返回值按 `output_schema` 裁切。注意：`stream_mode="values"` 仍可能打出内部字段，调试时用 `updates` 或显式 `output_keys` 更干净。

还有一类 **PrivateState**：只在某几个节点之间传递、不必出现在对外 I/O 里。需要时再加，不必一上来就把状态拆成四份。

### 5.3 Overwrite：带 reducer 的字段，空列表清不掉

这是并行和循环里的高频坑。字段如果用了 `operator.add` 这类合并器，你返回 `[]` **不会清空**，因为“当前列表 + 空列表”还是原列表。要整体替换，包一层 `Overwrite`：

```python
from langgraph.types import Overwrite

def reset_errors(state: State):
    return {"errors": Overwrite([])}
```

另外两个相关零件，知道名字即可，后面用到再展开：

- **`UntrackedValue`**：运行时存在、永不写入检查点，适合连接池、缓存句柄；
- **`RemainingSteps`**：距离触发递归上限还剩几步，适合在死循环前主动收尾，而不是等 `GraphRecursionError`。

递归上限从 1.0.6 起默认 1000，通过顶层配置设置，**不要**塞进 `configurable`：

```python
graph.invoke(inputs, config={"recursion_limit": 25, "configurable": {"thread_id": "t1"}})
```

---

## 状态字段要写清更新方式

并行节点如果同时写同一个普通字段，后到的会覆盖先到的。真要收集多路结果，给列表配 reducer，或让各分支写不同字段，最后在汇总节点合并。

临时对象不要进状态。数据库连接、客户端实例、不能序列化的对象会让检查点存失败，恢复时也还原不了。状态只保存**能让流程接着往下走的业务数据和标识符**。

> 📁 **本节示例代码**：[code/examples/02_state_graph_demo.py](code/examples/02_state_graph_demo.py) —— 无需 API Key。第一次先在 `code/examples` 里 `uv sync`，再 `uv run python 02_state_graph_demo.py`。

---

## 扩展阅读

- 使用图 API（State、节点、边、Schema、Runtime）：[How-to：Graph API](https://docs.langchain.com/oss/python/langgraph/how-tos/graph-api)
- 图 API 概念（reducer、Overwrite、私有通道）：[Graph API 概念](https://docs.langchain.com/oss/python/langgraph/graph-api)

---

**下一节：** 想让工作流在十字路口自动选路？我们把条件路由讲透：路径表、`Literal` 约束、决策与路由分离，以及 `Command` 这种“改状态 + 跳转”的写法。
