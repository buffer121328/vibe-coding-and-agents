# 04 并行执行与 Send 动态分发

在上一节，我们学会了用条件路由让工作流“分岔”。但如果你想让多个独立的任务“同时开工”，而不是一轮轮排队呢？

比如用户说“帮我查一下去北京和去上海的机票”，如果一个个查，慢且费时间；如果能**同时**查两个城市，速度直接翻倍。这一节我们就来看 LangGraph 的并行机制。

## 1. 什么是并行执行（Fan-out / Fan-in）？

LangGraph 的图本质上是一个有向图。官方底层算法借鉴了 Google 的 **Pregel** 消息传递模型：程序以离散的 **超步（Super-step）** 推进——**同一个超步里并行运行的节点**，先后运行的不同超步里的节点。

当一个节点有**多条出边**时，LangGraph 会同时把数据推送给所有下游节点——这就是 **Fan-out（扇出）**。当所有下游节点都执行完，它们的结果会流进同一个汇合点——这就是 **Fan-in（扇入）**。

<!-- 图表源文件：img/diagrams/04-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/04-diagram-01.svg">
    <img src="img/diagrams/04-diagram-01.svg" alt="1. 什么是并行执行（Fan-out / Fan-in）？" width="760">
  </a>
</p>

**生活化比喻：** 这就像饭店后厨。主厨（规划节点）一声令下：“凉菜、热菜、汤一起上！”三个灶台（并行节点）同时开工，最后所有菜一起端到传菜口（汇合节点）。如果一道道排队做，客人早就饿晕了。

## 2. 最简单的并行：一个节点连出多条边

官方文档明确指出：LangGraph 对节点的并行执行提供**原生支持**，通过扇出/扇入机制实现，普通边和条件边都可以用。在 02 节我们学的 `add_edge` 是把一个节点连向一个目标，但其实一个源节点可以**同时连出多条边**：

```python
builder.add_node("planner", planner_node)
builder.add_node("search_flights", search_flights_node)
builder.add_node("search_hotels", search_hotels_node)
builder.add_node("merge", merge_node)

# 从 planner 同时连出两条边 -> 两个节点并行执行
builder.add_edge(START, "planner")
builder.add_edge("planner", "search_flights")
builder.add_edge("planner", "search_hotels")
# 并行分支汇合到 merge（merge 是一个隐式屏障，等所有分支跑完才开始）
builder.add_edge("search_flights", "merge")
builder.add_edge("search_hotels", "merge")
builder.add_edge("merge", END)
```

> ⚠️ **关键点：并行节点的结果如何合并回 State？**
> 并行节点几乎同时执行，它们都会往 `State` 里写数据。如果它们想写同一个字段，就会产生“写冲突”。
> - 如果该字段用了 reducer（比如 `messages` 用 `add_messages`），消息会被**追加**而不是覆盖，安全；
> - 如果该字段是普通字段（比如 `flight_results`），后写入的会把先写入的**覆盖**掉！此时你需要自己定义合并逻辑，或者让每个节点写不同的字段。

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]  # 有 reducer，可以安全并行追加
    flight_results: list    # 普通字段：并行写会互相覆盖，要小心！
    hotel_results: list
```

**最佳实践：** 让每个并行节点写**不同的字段**，最后在汇合节点统一合并，这是最不容易出错的做法。

## 3. reducer：并行结果的安全合并通道

reducer（归约器）是 LangGraph 状态管理的灵魂。并行节点想要安全地往同一个字段写数据，就必须给这个字段配一个 reducer。除了 `add_messages`，最常用的是把 `list` 字段配上 `operator.add`（拼接）：

```python
import operator
from typing import TypedDict, Annotated

class State(TypedDict):
    quotes: Annotated[list, operator.add]   # 多个并行节点返回的列表会拼起来
```

这样，多个并行实例各自返回 `{"quotes": [xxx]}`，LangGraph 会自动把所有这些列表**拼接**到同一个 `quotes` 里，而不是互相覆盖。reducer 本质是一个函数：`new_value = reducer(current_value, update_value)`。

## 4. 动态并行：Send API（Map-Reduce 模式）

上面那种“连边”方式的并行，节点数量和结构是**写死**的。但很多场景下，我们事先不知道要并行几个任务——比如“对用户提的 5 个城市同时查航班”，城市的数量是运行时才知道的。

这时就需要 **`Send` API**。官方文档把这种“把一个大任务拆成 N 个小任务并行处理，再合并结果”的模式叫做 **Map-Reduce**。`Send` 的签名是 `Send(node, arg)`：

- `node`：要触发的下游节点名；
- `arg`：传给该节点实例的**私有状态**（只对这个实例可见，互不干扰）。

```python
from langgraph.types import Send

# 规划节点：先做"拆任务"，把解析出的城市写进 State
def planner_node(state: State):
    cities = parse_cities(state["user_input"])   # 例如 ["北京", "上海", "广州"]
    return {"cities": cities}

# Send 路由函数：按城市数量动态派发 N 个并行实例（注意它不是节点，是条件边函数）
def dispatch(state: State):
    return [
        Send("search_flights", {"city": city, "date": state["date"]})
        for city in state["cities"]
    ]
```

然后在图中，把 `planner` 与 `search_flights` 注册成节点，并用条件边把动态派发接进去：

```python
builder.add_node("planner", planner_node)
builder.add_node("search_flights", search_flights_node)

# 路由函数返回的是 Send 列表，LangGraph 会自动并行分发到多个实例
builder.add_conditional_edges("planner", dispatch)
```

> ⚠️ **常见坑**：返回 `Send` 列表的函数是**条件边函数**，不是节点。如果你把同一个函数既 `add_node` 又当路由函数用，节点执行时会因为“返回值不是状态字典”而报错。正确的分工是：规划节点负责算出任务清单（写入 State），Send 路由函数负责照清单派发。

整个 Map-Reduce 闭环长这样：

<!-- 图表源文件：img/diagrams/04-diagram-02.mmd；视觉风格：House 浅色 -->
<p align="center">
  <a href="img/diagrams/04-diagram-02.svg">
    <img src="img/diagrams/04-diagram-02.svg" alt="Send 的 Map-Reduce 动态分发" width="760">
  </a>
</p>

> 💡 **Send 与普通边的区别：**
> - 普通边：编译时结构固定，一次只触发一个固定的下游节点；
> - Send：运行时动态决定“发多少个、发给谁、带什么参数”，适合**数量不定的批量并行**。

## 5. 并行场景实战：多城市机票比价

把上面所有技巧组合起来，就是一个完整的、复制即可运行的“多城市比价”并行工作流（下面的代码在 LangGraph 1.x 上实测可跑通；为方便本地验证，`parse_cities` 与 `query_flight_api` 用极简模拟实现，真实项目里换成 LLM 结构化抽取和真实航司 API 即可）：

```python
import operator
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

class State(TypedDict):
    user_input: str
    cities: list                            # 规划节点算出的任务清单
    quotes: Annotated[list, operator.add]   # 用加法 reducer 合并各城市报价
    final_answer: str

# ---- 两个模拟依赖：真实项目中分别换成 LLM 抽取与航司查询 API ----
def parse_cities(user_input: str) -> list[str]:
    """极简版城市解析：词典匹配演示用。真实项目用 with_structured_output 抽取更稳"""
    known_cities = ["北京", "上海", "广州", "深圳", "杭州", "成都"]
    return [c for c in known_cities if c in user_input]

def query_flight_api(city: str, date: str) -> int:
    """模拟航司报价接口：返回一个编造的价格"""
    return 600 + 120 * (len(city.encode()) % 5)

def plan(state: State):
    """规划节点（Map）：解析城市写进状态"""
    return {"cities": parse_cities(state["user_input"])}

def fan_out(state: State):
    """Send 路由函数（不是节点！）：按城市数量动态派发 N 个并行实例"""
    return [Send("search_one_city", {"city": c}) for c in state["cities"]]

def search_one_city(state: dict):
    city = state["city"]                     # 每个实例只看到自己的私有状态
    quote = query_flight_api(city, "2026-09-01")   # 模拟查价
    return {"quotes": [{"city": city, "price": quote}]}

def aggregate(state: State):
    cheapest = min(state["quotes"], key=lambda q: q["price"])
    return {"final_answer": f"最低价是 {cheapest['city']}，仅需 {cheapest['price']} 元"}

builder = StateGraph(State)
builder.add_node("plan", plan)
builder.add_node("search_one_city", search_one_city)
builder.add_node("aggregate", aggregate)
builder.add_edge(START, "plan")
builder.add_conditional_edges("plan", fan_out)       # 动态分发
builder.add_edge("search_one_city", "aggregate")     # 隐式屏障：等所有实例完成
builder.add_edge("aggregate", END)

graph = builder.compile()
result = graph.invoke({"user_input": "帮我同时查一下北京、上海和成都的机票"})
print(result["final_answer"])   # -> 最低价是 北京，仅需 720 元
```

这里的核心机制值得记住：`Send` 给每个实例的 `arg` 是**独立私有状态**，实例返回的更新通过 `quotes` 的 reducer 合并回全局 State，下游 `aggregate` 节点则像一个“汇合屏障”，等所有并行实例跑完才执行。这就是标准的 **Map-Reduce** 闭环。

## 6. 并行与成本提醒

并行虽然快，但多个 LLM 调用是**同时**发出去的，Token 消耗不会变少。真实项目中建议：
- 控制并发的数量（可以在节点内部做分批处理）；
- 给可能死循环的图设置 `recursion_limit`（配置里传 `{"recursion_limit": N}`）；
- 用 `stream_mode` 观察每个并行分支的执行状态（下一节讲可视化与流式）。

## 7. 扩展阅读

**官方文档**
- LangGraph 图 API 概念（并行、Send、Map-Reduce、reducer）：[官方概念文档](https://docs.langchain.com/oss/python/langgraph/concepts/low_level)（中文镜像：[langgraph.com.cn](https://langgraph.com.cn/concepts/low_level.1.html)）
- 使用图 API —— “创建分支”与“Map-Reduce 和 Send API”两节：[How-to：使用图 API](https://docs.langchain.com/oss/python/langgraph/how-tos/graph-api)（中文镜像：[github.langchain.ac.cn](https://github.langchain.ac.cn/langgraph/how-tos/graph-api/)）

**社区教程**
- Matt Harrison《LangGraph from scratch, part 2：streaming, subgraphs and dynamic fan-out》（把 Send 的并行语义讲得很清楚）：[matt-harrison.com](https://matt-harrison.com/posts/9-5-26-langgraph-part-2/)
- CSDN《langgraph 分支之动态分支（Dynamic Branch）》（Send 扇出的诗/词/笑话例子）：[blog.csdn.net](https://blog.csdn.net/weixin_42439274/article/details/163115219)
- PocketFlow 教程《Control Flow Primitives》（含 Send 的 Map-Reduce 解释）：[GitHub](https://github.com/The-Pocket/PocketFlow-Tutorial-Codebase-Knowledge/blob/main/docs/LangGraph/04_control_flow_primitives___branch____send____interrupt__.md)

> 📁 **本节示例代码**：[code/examples/04_parallel_send_demo.py](code/examples/04_parallel_send_demo.py) —— 无需 API Key 即可运行，可与本文对照着跑。

---

**下一节：** 图越画越复杂，怎么把这张“棋盘”画出来给同事看？怎么实时观察每一步的状态流转？我们将学习图的可视化与流式调试。
