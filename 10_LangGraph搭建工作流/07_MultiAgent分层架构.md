# 10.7 Multi-Agent 状态栈交接：Handoffs 入门

业务变复杂之后，最先爆的往往不是工具数量，而是**一张 Prompt 塞不下**。

做一个旅行助手：航班改签、租车计费、酒店退款，规则和工具全写进同一个系统提示词，模型会开始用错工具、答非所问。这不是它“不够聪明”，是同一位同事被要求同时背三本业务手册。

解法不一定是再造一群 Agent。如果只是按需加载一段专业知识，12 节的 Skills 更轻。本节聚焦另一种需求：**专业助理要直接接手多轮对话**——这就是 Handoffs。

---

## 1. 前台接待，专员接手

可以把它想成医院或银行的前台：

- 你说“我要改签下周一的航班”，前台判断这是机票业务，把你转到机票专员；
- 你说“这笔租车押金怎么退”，转到租车专员；
- 你问“今天北京天气怎么样”，前台自己查一下就回答，不必占用专员。

对应到图里：

1. **主助理**：Prompt 很短，核心职责是意图识别和路由。它只有少量通用工具，外加几个“转交工具”；
2. **专业子助理**：Prompt 很厚，工具很专。干完或遇到超纲问题，把控制权交还主助理。

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="主助理通过转交工具把对话交给专业子助理" width="760">
  </a>
</p>

这个入门版把主助理和专业助理平铺在同一张图里，用 **状态栈 `dialog_state`** 记录当前谁在接待。它还不是真子图——12 节会讲如何把整张子图当成父图的一个节点。按当前官方分类，这种“活跃角色写进状态、专业助理直接继续和用户说话”的体验，就是 **Handoffs**。

---

## 2. 三步把交接做出来

### Step 1：交接本上记下“现在谁在接客”

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
    dialog_state: Annotated[list[str], update_dialog_stack]
```

`dialog_state` 是一个栈：空表示主助理在场；`"update_flight"` 压在栈顶，表示航班助理正在接待。自定义 reducer 负责压栈 / 弹栈，配套示例里有一份可运行实现。

### Step 2：给主助理配备转交工具

转交在代码里往往**伪装成工具**。主助理看到用户要订机票，就调用 `ToFlightBookingAssistant`：

```python
class ToFlightBookingAssistant(BaseModel):
    """当用户需要预订、修改或取消航班时，将对话委托给航班助理。"""
    request: str = Field(description="需要航班助理帮忙做的具体需求")
```

它并不发网络请求，而是一枚意图信号。条件边捕捉到这个工具调用，把流程路由到航班助理入口，同时把 `dialog_state` 压栈为 `update_flight`。

工具的**名字和描述**就是主助理的选人说明书。写得含糊，它会把租车问题交给机票专员。

### Step 3：子助理要能退场

子助理没有酒店工具。用户订着机票突然问“那边酒店怎么样”，它必须把控制权还回去。统一的退场工具通常叫 `CompleteOrEscalate`：

```python
class CompleteOrEscalate(BaseModel):
    """任务完成，或用户偏离你的专业范围时，把控制权交还主助理。"""
    cancel: bool = True
    reason: str = Field(description="交还的原因")
```

调用后，图把栈顶弹出，流程回到主助理。压栈和弹栈必须成对，否则旧助理的规则会污染下一轮对话。

Agent 越多，路由成本、上下文传递和排错成本也越高。能用一个节点加一段专业说明解决的，不必拆成新助理。

---

## 3. 交接时到底传什么？

客服转接时，原坐席既不能只说“你接一下”，也不该把用户十年的通话录音全部转发。至少要交代：当前要办什么、已经查过什么、哪些工具调用还没回执。

本例为了教学透明，共享完整 `messages`。生产项目要明确三件事：

1. 转交工具的名字和描述，是否让主助理知道“什么时候该交给谁”；
2. 接手者收到的是完整历史、筛选后的消息，还是一段结构化摘要；
3. 交回主助理时，是返回最终结果，还是把整个子轨迹塞回去。

这就是多智能体的上下文工程。传得太少会缺背景；传得太多会烧 Token、泄露无关信息，还可能拆散 `tool_call` 与 `ToolMessage` 的配对。

当前官方把专家当成工具来调用的模式叫 **Subagents**：专家干完活，结果回到主助理，专家并不长期直接对用户说话。Handoffs 则相反——接手者成为当前活跃角色。不要因为“都用了转交工具”就把两者当成同一种架构。12 节会把五种模式放在一张表里。

---

## 交接协议比角色名称更重要

把任务交给专业助理时，至少传递：当前目标、已经确认的事实、尚未解决的问题、允许使用的工具。只丢一长串聊天记录，接手者会重新猜测重点，还可能把用户已经回答过的问题再问一遍。

主助理应清楚何时转交、何时收回。子助理的返回值最好包含结果摘要和完成状态；若要升级处理，说明缺了什么条件。可以用一组连续对话测试状态栈：进入航班助理 → 处理一个问题 → 返回主助理 → 再进入酒店助理。检查每次压栈弹栈是否成对，以及旧规则有没有误伤后续对话。

> 📁 **本节示例代码**：[code/examples/07_multiagent_stack_demo.py](code/examples/07_multiagent_stack_demo.py)

---

## 扩展阅读

- Multi-agent 总览与五种当前模式：[multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent)
- Handoffs（活跃 Agent、消息交接）：[handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)
- Subagents（主 Agent 把专家当工具调用，与本节对比）：[subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)

---

**下一节：** 多智能体编队已经就位，每个助理内部靠什么干活？补上所有 Agent 共用的核心闭环——工具调用循环。
