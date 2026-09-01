# 14 Functional API：@entrypoint 与 @task，两套 API 怎么选

到这里，你摸过的都是 LangGraph 的 **Graph API**（`StateGraph` / 节点 / 边）。但官方其实提供了第二套武功：**Functional API**——不改架构、不画图，给普通 Python 函数直接加上持久化、记忆、HITL 与流式。这一节讲清它的两个装饰器，并给出两套 API 的选型对照表。

## 1. 为什么需要第二套 API？

**生活化比喻：** 你已经开了一家成熟餐馆（现有 Python 代码），现在想加“扫码看后厨实时监控”（流式）和“出餐前顾客确认”（HITL）。两个方案：
- **推倒重装**（Graph API）：把厨房改成流水线工位（节点 + 边），动土三个月；
- **加装设备**（Functional API）：每道关键工序装个摄像头和确认铃（`@task` + `@entrypoint`），厨房布局不变。

对你那堆“已经能跑、但没持久化”的 Python 脚本，Functional API 是官方认可的**最小改动路径**。

## 2. 两个装饰器：@entrypoint 与 @task

- **`@entrypoint`**：工作流的**总入口**，相当于 `main()`。负责持有上下文（记忆、流式写出器），决定从哪开始、到哪结束。
- **`@task`**：工作流里的**一道工序**（一次 API 调用、一段数据处理）。每道工序的执行结果都会被 Checkpointer 存档——这就是持久化能力的最小颗粒。

```python
from langgraph.func import entrypoint, task
from langgraph.checkpoint.memory import MemorySaver

@task
def translate_topic(topic: str) -> str:
    return llm.invoke(f"把 {topic} 翻译成英文提纲").content

@task
def summarize_topic(topic: str) -> str:
    return llm.invoke(f"给 {topic} 写三句话摘要").content

@task
def write_essay(topic: str, materials: list[str]) -> str:
    """工序一：根据并行准备好的材料写初稿"""
    return llm.invoke(f"围绕 {topic} 写短文，参考：{materials}").content

@task
def review(essay: str) -> str:
    """工序二：人工审阅——复用 13 节的 interrupt()"""
    decision = interrupt({"essay": essay, "ask": "这篇可以发布吗？"})
    return essay if decision["approved"] else f"需修改：{decision['reason']}"

@entrypoint(checkpointer=MemorySaver())
def essay_flow(topic: str):
    # 先把两张工单都派出去，再统一等结果：这才是真并行
    translation_future = translate_topic(topic)
    summary_future = summarize_topic(topic)
    materials = [translation_future.result(), summary_future.result()]
    draft = write_essay(topic, materials).result()
    final = review(draft).result()
    return final

# 用法与图几乎一致：thread_id 就是存档编号
config = {"configurable": {"thread_id": "user-42"}}
essay_flow.invoke("机器人安全", config)
```

配套工作台不会再用一句“机器人应当……”冒充产出：两个 future 同时点亮，合流后展示完整 Markdown 初稿；人工通过后保留完整文稿并把状态标为 `published`，驳回则展示修改意见和 `needs_revision`。左侧“文稿预览”给读者看业务产物，右侧“原始状态”用来理解框架返回值，两者不要混成一个黑盒 JSON。

注意 `@task` 返回的不是结果本身而是一个 **future（对未来的承诺）**。要让互不依赖的任务并行，必须先创建所有 future，再统一 `.result()`：

```python
translation_future = translate_to_en(text)
summary_future = summarize(text)

# 两张工单都已发出，现在再统一等待结果
a = translation_future.result()
b = summary_future.result()
```

下面这种写法看起来也用了 future，实际仍是串行，应该避免：

```python
a = translate_to_en(text).result()  # 在这里等完，下一张工单还没发
b = summarize(text).result()
```

## 3. 两套 API 选型对照表

| 维度 | Graph API（StateGraph） | Functional API（@entrypoint/@task） |
| :--- | :--- | :--- |
| 心智模型 | 画一张“轨道图”，节点在轨道上跑 | 写普通 Python，给函数加超能力 |
| 控制流 | 边、条件边、Send、Command 显式定义 | 就是普通 Python（if/for/try 随便用） |
| 并行 | 多出边 / Send 动态分发 | future 先发后取 |
| 存档颗粒度 | 每个超步（super-step） | 每个 @task |
| 现有代码改造成本 | 高（重构成节点） | **低（包一层装饰器）** |
| 可视化 | `get_graph()` 直接画 | 结构较难可视化 |
| 多智能体路由 / 复杂拓扑 | 天生主场 | 不擅长 |
| 适合 | 新建的复杂编排、Multi-Agent | 给现有流程加持久化 / HITL / 记忆 |

**官方选型建议的通俗版**：从零搭多智能体大编排，用 Graph API；手头已有能跑的 Python 流程，只想加“存档、断点续跑、人工审批”，用 Functional API。两者还能混用——`@entrypoint` 里可以直接 invoke 一个编译好的图。

> 💡 Functional API 的“确定性”要求值得一记：中断恢复时，`@entrypoint` 函数会**从头重新执行**，已完成的 `@task` 直接命中存档。所以同一个 task 用相同输入要产出相同结果（或做成幂等），中断点前的代码不要依赖“只执行一次”的副作用。

## 4. 扩展阅读

**官方文档**
- Functional API 概览（@entrypoint / @task 全解）：[docs.langchain.com/oss/python/langgraph/functional-api](https://docs.langchain.com/oss/python/langgraph/functional-api)
- Use Functional API（动手教程）：[docs.langchain.com/oss/python/langgraph/use-functional-api](https://docs.langchain.com/oss/python/langgraph/use-functional-api)
- Choosing between Graph and Functional APIs（官方选型对比）：[docs.langchain.com/oss/python/langgraph/choosing-apis](https://docs.langchain.com/oss/python/langgraph/choosing-apis)

> 📁 **本节示例代码**：[code/examples/14_functional_api_demo.py](code/examples/14_functional_api_demo.py) —— 无需 API Key 即可运行，可与本文对照着跑。

---
**下一节：** 图在本地跑通了，怎么部署成线上服务？怎么像看监控大屏一样看到每一次模型调用、每一个工具执行？下一节讲部署与可观测性。
