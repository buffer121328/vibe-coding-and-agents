# 10.4 并行执行与 Send 动态分发

上一节学会了让工作流分岔。如果几件事情彼此独立，为什么还要排队？

用户说“同时查北京和上海的机票”，串行查询会把等待时间叠在一起；两路一起发，墙上时钟往往能砍掉一半。这一节讲清两件事：**结构写死的并行**，以及**运行时才知道要派几路的 `Send`**。

---

## 1. Fan-out / Fan-in：同一拍里一起动

LangGraph 按超步推进。一个节点有多条出边时，下游会在**同一个超步**里同时被激活——这就是 Fan-out。这些下游都跑完后，结果流进同一个汇合点——Fan-in。汇合节点像一道屏障：缺一路，它不会提前开跑。

<!-- 图表源文件：img/diagrams/04-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/04-diagram-01.svg">
    <img src="img/diagrams/04-diagram-01.svg" alt="规划节点同时分出查航班、查酒店、查天气" width="760">
  </a>
</p>

可以把它想成项目排期：调研、报价、合规审查三份材料没有依赖，就该同一天发给三个同事；等三份都回来，再开汇总会。硬排成早中晚三班，只会让总耗时变长。

---

## 2. 最简单的并行：一个节点连出多条边

普通边和条件边都能扇出。源节点可以同时连向多个目标：

```python
builder.add_edge(START, "planner")
builder.add_edge("planner", "search_flights")
builder.add_edge("planner", "search_hotels")
builder.add_edge("search_flights", "merge")
builder.add_edge("search_hotels", "merge")
builder.add_edge("merge", END)
```

关键问题马上出现：**两路几乎同时往 State 里写，写同一个字段怎么办？**

- 字段带了 reducer（例如 `messages` 用 `add_messages`）→ 按规则合并，通常安全；
- 普通字段（例如两边都写 `results`）→ 后写入的会覆盖先写入的。

最稳妥的办法：每个并行节点写**不同字段**，到汇合节点再统一合并。

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
    flight_results: list
    hotel_results: list
```

---

## 3. reducer：多路结果的合并通道

确实需要往同一个列表里堆结果时，给字段配 reducer。最常用的是 `operator.add`（拼接）：

```python
import operator
from typing import TypedDict, Annotated

class State(TypedDict):
    quotes: Annotated[list, operator.add]
```

多个实例各自返回 `{"quotes": [xxx]}`，LangGraph 会把这些列表拼起来，而不是互相覆盖。reducer 的本质就是：`new_value = reducer(current_value, update_value)`。

记得 02 节的坑：带合并器的字段，返回 `[]` 清不掉，要用 `Overwrite([])`。

---

## 4. Send：任务数量运行时才知道

上面那种连边，节点数量在编译期就写死了。很多需求不是这样——“用户提了几个城市，就查几路机票”，N 要到运行时才知道。

这就是 **Map-Reduce**，官方用 `Send(node, arg)` 来表达：

- `node`：要触发的下游节点名；
- `arg`：传给**这一路实例**的私有状态，各路互不干扰。

```python
from langgraph.types import Send

def planner_node(state: State):
    cities = parse_cities(state["user_input"])
    return {"cities": cities}

def dispatch(state: State):
    return [
        Send("search_flights", {"city": city, "date": state["date"]})
        for city in state["cities"]
    ]
```

规划节点负责算出任务清单并写入 State；返回 `Send` 列表的函数是**条件边函数，不是节点**。把同一个函数既 `add_node` 又当路由用，节点执行时会因为“返回值不是状态字典”而报错。

```python
builder.add_node("planner", planner_node)
builder.add_node("search_flights", search_flights_node)
builder.add_conditional_edges("planner", dispatch)
```

<!-- 图表源文件：img/diagrams/04-diagram-02.mmd；视觉风格：House 浅色 -->
<p align="center">
  <a href="img/diagrams/04-diagram-02.svg">
    <img src="img/diagrams/04-diagram-02.svg" alt="Send 按城市动态派发多个查询实例" width="760">
  </a>
</p>

和普通边的差别：

- 普通边：编译时结构固定；
- `Send`：运行时决定发多少个、发给谁、带什么参数。

---

## 5. 把技巧拼起来：多城市比价

下面这段在 LangGraph 1.x 上可直接跑。`parse_cities` 和 `query_flight_api` 用模拟实现，真实项目换成结构化抽取和航司接口即可：

```python
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

class State(TypedDict):
    user_input: str
    cities: list
    quotes: Annotated[list, operator.add]
    final_answer: str

def parse_cities(user_input: str) -> list[str]:
    known = ["北京", "上海", "广州", "深圳", "杭州", "成都"]
    return [c for c in known if c in user_input]

def query_flight_api(city: str, date: str) -> int:
    return 600 + 120 * (len(city.encode()) % 5)

def plan(state: State):
    return {"cities": parse_cities(state["user_input"])}

def fan_out(state: State):
    return [Send("search_one_city", {"city": c}) for c in state["cities"]]

def search_one_city(state: dict):
    city = state["city"]
    quote = query_flight_api(city, "2026-09-01")
    return {"quotes": [{"city": city, "price": quote}]}

def aggregate(state: State):
    cheapest = min(state["quotes"], key=lambda q: q["price"])
    return {"final_answer": f"最低价是 {cheapest['city']}，仅需 {cheapest['price']} 元"}

builder = StateGraph(State)
builder.add_node("plan", plan)
builder.add_node("search_one_city", search_one_city)
builder.add_node("aggregate", aggregate)
builder.add_edge(START, "plan")
builder.add_conditional_edges("plan", fan_out)
builder.add_edge("search_one_city", "aggregate")
builder.add_edge("aggregate", END)

graph = builder.compile()
print(graph.invoke({"user_input": "帮我同时查一下北京、上海和成都的机票"})["final_answer"])
```

记住闭环：`Send` 给每路一份私有 `arg` → 各路返回的更新经 reducer 合并回全局 State → `aggregate` 等所有实例完成再跑。这就是标准 Map-Reduce。

---

## 6. 并行之前，先确认任务互不依赖

并行适合同时查多个城市、分别分析多份独立材料。后一步必须读前一步结果时，不要为了“看起来更快”硬拆。写库、扣库存、发通知这类带副作用的操作更要小心，多路可能争用同一份数据。

汇总节点需要约定：顺序、去重、部分失败怎么处理。四路查询里有一路超时，是返回其余三路、重试失败项，还是整次失败，只能由业务决定。reducer 只会合并状态，不会替你判断结果是否完整。

并行也不会自动省钱。多个模型调用是同时发出去的，Token 总量不会变少。建议：

- 控制扇出数量，必要时在节点内分批；
- 给可能死循环的图设 `recursion_limit`；
- 用 `stream_mode` 观察每一路的进度（下一节）。

评估收益时，同时记录总耗时、调用次数、失败率和限流。墙上时间缩短了，账单未必下降。

> 📁 **本节示例代码**：[code/examples/04_parallel_send_demo.py](code/examples/04_parallel_send_demo.py)

---

## 扩展阅读

**官方文档**

- 图 API 概念（并行、Send、Map-Reduce、reducer）：[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- 使用图 API —— 分支与 Send：[How-to：Graph API](https://docs.langchain.com/oss/python/langgraph/how-tos/graph-api)

**社区教程**

- Matt Harrison《LangGraph from scratch, part 2》：[matt-harrison.com](https://matt-harrison.com/posts/9-5-26-langgraph-part-2/)
- PocketFlow《Control Flow Primitives》：[GitHub](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/main/docs/LangGraph/04_control_flow_primitives___branch____send____interrupt__.md)

---

**下一节：** 图越画越复杂，怎么把这张棋盘画给同事看？怎么实时观察每一步的状态流转？
