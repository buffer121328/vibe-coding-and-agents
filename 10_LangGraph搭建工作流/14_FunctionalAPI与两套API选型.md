# 10.14 Functional API：@entrypoint 与 @task，两套 API 怎么选

到这里，你摸过的都是 **Graph API**（`StateGraph` / 节点 / 边）。官方其实提供了第二套写法：**Functional API**——不改架构、不画图，给普通 Python 函数直接加上持久化、记忆、HITL 与流式。这一节讲清两个装饰器，并给出选型对照。

---

## 1. 为什么需要第二套 API？

假设你已经有一套能跑的 Python 流程：读两份资料、生成摘要、等人审阅再发布。现在想加“断点续跑”和“发布前人工确认”。两条路：

- **推倒重画（Graph API）：** 把每一步改成节点，用边把控制流重新铺一遍；
- **加装设备（Functional API）：** 关键步骤套上 `@task`，入口套上 `@entrypoint`，`if` / `for` / `try` 原样保留。

对“已经能跑、但没持久化”的脚本，Functional API 是官方认可的**最小改动路径**。两套 API 共用同一套运行时，可以在同一个应用里混用：`@entrypoint` 里可以 `invoke` 一张编译好的图；Graph 节点里也可以调用 `@task`。

---

## 2. 两个装饰器

- **`@entrypoint`：** 工作流总入口，相当于 `main()`。持有 Checkpointer、决定从哪开始到哪结束。
- **`@task`：** 一道需要存档的工序（一次 API 调用、一段数据处理）。每道工序的结果都会被 Checkpointer 记下——这是持久化的最小颗粒。

```python
from langgraph.func import entrypoint, task
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

@task
def translate_topic(topic: str) -> str:
    return llm.invoke(f"把「{topic}」翻译成英文提纲").content

@task
def summarize_topic(topic: str) -> str:
    return llm.invoke(f"给「{topic}」写三句话摘要").content

@task
def write_essay(topic: str, materials: list[str]) -> str:
    return llm.invoke(f"围绕 {topic} 写短文，参考：{materials}").content

@task
def review(essay: str) -> str:
    decision = interrupt({"essay": essay, "ask": "这篇可以发布吗？"})
    return essay if decision["approved"] else f"需修改：{decision['reason']}"

@entrypoint(checkpointer=MemorySaver())
def essay_flow(topic: str):
    translation_future = translate_topic(topic)
    summary_future = summarize_topic(topic)
    materials = [translation_future.result(), summary_future.result()]
    draft = write_essay(topic, materials).result()
    return review(draft).result()

config = {"configurable": {"thread_id": "user-42"}}
essay_flow.invoke("机器人安全", config)
```

`@task` 返回的不是结果本身，而是一个 **future**。要让互不依赖的任务并行，必须先创建所有 future，再统一 `.result()`：

```python
translation_future = translate_topic(topic)
summary_future = summarize_topic(topic)
a = translation_future.result()
b = summary_future.result()
```

下面这种写法看起来也用了 future，实际仍是串行——第一行就已经把第二张工单堵住了：

```python
a = translate_topic(topic).result()
b = summarize_topic(topic).result()
```

配套工作台会把两个 future 同时点亮，合流后展示完整 Markdown 初稿；人工通过后把状态标为 `published`，驳回则展示修改意见。左侧“文稿预览”给读者看业务产物，右侧“原始状态”用来理解框架返回值，两者不要混成一个黑盒 JSON。

---

## 3. 确定性：中断恢复时入口会从头再走一遍

Functional API 有一条必须遵守的纪律：中断或失败后恢复时，**`@entrypoint` 函数会从头重新执行**，已经完成的 `@task` 直接命中存档，不会重跑。所以：

- 同一个 task、相同输入，要产出相同结果，或做成幂等；
- 随机数、当前时间、真实 HTTP 调用，必须放在 `@task` 里，不能写在入口函数的裸代码中；
- 中断点前不要依赖“只执行一次”的副作用（发邮件、扣款）；
- 入口和 task 的入参出参必须可 JSON 序列化，否则检查点存不下。

`@task` 只能从 entrypoint、另一个 task 或 Graph 节点里调用，不能从普通应用代码随便调——否则绕过了存档边界。

---

## 4. 两套 API 选型对照

| 维度 | Graph API（StateGraph） | Functional API（@entrypoint / @task） |
| :--- | :--- | :--- |
| 心智模型 | 画一张轨道图，节点在轨道上跑 | 写普通 Python，给函数加超能力 |
| 控制流 | 边、条件边、Send、Command 显式定义 | 就是普通 Python（if / for / try） |
| 并行 | 多出边 / Send 动态分发 | future 先发后取 |
| 存档颗粒度 | 每个超步 | 每个 `@task` |
| 现有代码改造成本 | 高（重构成节点） | **低（包一层装饰器）** |
| 可视化 | `get_graph()` 直接画 | 结构较难可视化 |
| 多智能体路由 / 复杂拓扑 | 天生主场 | 不擅长 |
| 适合 | 新建的复杂编排、Multi-Agent | 给现有流程加持久化 / HITL / 记忆 |

**通俗版官方建议：** 从零搭多智能体大编排，用 Graph API；手头已有能跑的 Python 流程，只想加存档、断点续跑、人工审批，用 Functional API。两者可以混用。

比较时不要只看代码行数，还要看：运行路径是否容易观察、状态能否修改、错误能否单独重试、团队是否习惯图式设计。无论哪套 API，恢复执行都要求副作用可控。函数从头重放、已完成任务从检查点取回，需要通过故障测试确认，而不能只根据装饰器推断。

可以把“读取两份资料并生成摘要”分别用两套 API 实现一遍，手感会比只看对照表清楚。

> 📁 **本节示例代码**：[code/examples/14_functional_api_demo.py](code/examples/14_functional_api_demo.py)

---

## 扩展阅读

- Functional API 概览：[functional-api](https://docs.langchain.com/oss/python/langgraph/functional-api)
- Use Functional API：[use-functional-api](https://docs.langchain.com/oss/python/langgraph/use-functional-api)
- 官方选型对比：[choosing-apis](https://docs.langchain.com/oss/python/langgraph/choosing-apis)

---

**下一节：** 图在本地跑通了，怎么部署成线上服务？生产环境出了问题，怎样看见它卡在哪一步？部署选项与可观测性取舍。
