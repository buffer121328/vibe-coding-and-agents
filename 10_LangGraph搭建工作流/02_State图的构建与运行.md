# 02 State 图的构建与运行

在上一节中，我们将 LangGraph 比作一张“飞行棋棋盘”。这一节，我们来看看如何用代码画出这张棋盘，并让数据（棋子）在上面跑起来。

## 1. 定义状态 (State) - 大家的“公共黑板”

在 LangGraph 中，所有的节点（Node）都只做一件事：**读取当前的状态 -> 进行处理 -> 返回需要更新的状态。**

为了确保大家看到的信息是一致的，我们需要定义一个 `State`（状态）。这通常是一个 `TypedDict`。

这就像一个“项目交接本”。当上一个班次的员工（节点）下班时，他在本子上写下新的进展；下一个班次的员工接手时，先看一遍交接本，再接着干活。

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class State(TypedDict):
    # add_messages 会告诉图，这不是替换旧消息，而是追加新消息
    messages: Annotated[list, add_messages]
    # 其他你想保存的全局变量，比如从用户话语中提取的目的地
    destination: str
```

> 这里的 `add_messages` 是 LangGraph 提供的一个辅助函数。如果不加它，新的消息会直接**覆盖**掉旧消息；加上它，新的消息就会乖乖排在旧消息后面，形成完整的对话历史。

## 2. 定义节点 (Nodes) - 具体的处理步骤

节点就是 Python 函数。它的输入是当前的交接本（`State`），输出是**需要更新到交接本上的内容**。

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-3.5-turbo") # 这里也可以使用最新的 claude-3 或 deepseek

def agent_node(state: State):
    """思考节点：让大模型看看当前的聊天记录，并给出回复"""
    response = llm.invoke(state["messages"])
    # 我们只返回需要“追加/更新”的部分，LangGraph 会自动帮我们合并
    return {"messages": [response]}
```

## 3. 把节点连起来 (Edges) - 画路线图

有了交接本和处理节点，我们就可以把他们用线连起来，构成 `StateGraph`。

```python
from langgraph.graph import StateGraph, START, END

# 1. 拿出空棋盘，告诉它我们的交接本格式是 State
builder = StateGraph(State)

# 2. 把处理节点放到图中
builder.add_node("assistant", agent_node)

# 3. 画线：规定走法
builder.add_edge(START, "assistant") # 从开始点，不加区分地走向 assistant
builder.add_edge("assistant", END)   # assistant 思考完毕后，直接结束

# 4. 编译成图（相当于把草稿变成可执行的程序）
graph = builder.compile()
```

## 4. 运行这个图

```python
# 初始状态
initial_state = {"messages": [("user", "你好，今天天气怎么样？")]}

# stream 会流式输出中间每个节点产生的新状态
for event in graph.stream(initial_state):
    print("-------")
    print(event)
```

## 5. 条件边 (Conditional Edges) - 动态路由

上面的图是直来直去的，但遇到复杂情况时，我们需要在“十字路口”做选择。在 LangGraph 中，我们使用 `add_conditional_edges` 来实现。

它接收三个参数：
1. **当前节点**：从哪里出发
2. **路由函数**：一个普通的 Python 函数，负责看看当前状态，决定下一步去哪。
3. **映射表**（可选）：把路由函数的返回值，映射到具体的节点名字上。

```python
def route_logic(state: State):
    last_message = state["messages"][-1]
    # 如果大模型想要调用工具，就去执行工具
    if last_message.tool_calls:
        return "tools_node"
    # 否则直接结束
    return END

# 把路由逻辑加到图里
builder.add_conditional_edges(
    "assistant", # 从 assistant 出来后
    route_logic, # 问问 route_logic 接下来去哪
    ["tools_node", END] # 它只可能去这两个地方之一
)
```

**总结：**
在 LangGraph 1.x 中，构建图的三步曲永远是：**定义 State -> 添加 Node -> 画 Edge（或 Conditional Edge） -> compile() 编译。**

> 📁 **本节示例代码**：[code/examples/02_state_graph_demo.py](code/examples/02_state_graph_demo.py) —— 无需 API Key 即可运行，可与本文对照着跑。

---

**下一节：** 想让工作流在“十字路口”自动选择走哪条路？我们将深入条件路由，学会让大模型当“路由裁判”，并构建意图分流与决策树。
<!-- CH10-14_EXPANSION -->

## 状态字段要写清更新方式

状态不是一个大家随意修改的全局变量。节点返回的是“这一步希望更新的字段”，LangGraph 再按字段的 reducer 规则合并。普通字段通常以后值覆盖前值；带 `add_messages` 的消息字段则按消息规则追加或更新。

设计状态时，可以为每个字段补三项说明：谁负责写入、哪些节点读取、冲突时怎样合并。并行节点如果同时写同一个普通字段，往往会出现更新冲突；若确实需要收集多路结果，应使用列表 reducer，或让各分支写入不同字段后在汇总节点统一处理。

还要避免把临时对象全部塞进状态。数据库连接、客户端实例和不能序列化的对象会妨碍检查点保存。状态更适合保存能够重建流程的业务数据和标识符。

---
