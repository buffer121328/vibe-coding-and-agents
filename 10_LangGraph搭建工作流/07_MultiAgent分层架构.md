# 07 Multi-Agent 状态栈交接：Handoffs 入门

随着你的业务越来越复杂，你可能会发现一个严重的问题：**一个大模型的 Prompt 塞不下了**。

如果你想做一个“全能旅行助手”，它既要懂航班改签规则，又要懂租车计费标准，还要负责酒店退款。如果你把所有的规则、几十个工具全写在一个 Prompt 里，大模型一定会犯晕，产生“认知负荷过载”（通俗点说就是大脑超载，开始胡言乱语或者用错工具）。

一种解法是 **Multi-Agent（多智能体协作）**。但不要为了角色多就拆 Agent：如果只是按需加载一段专业知识，12 节会介绍更轻的 Skills；本节聚焦“专业助理需要直接接手多轮对话”的 Handoffs 场景。

## 1. 架构理念：前台大堂经理与后厨专家

**生活化比喻：**
去大饭店吃饭，接待你的一定是“大堂经理”（Primary Assistant）。大堂经理非常热情，但他不会炒菜。
- 你说：“我要一份北京烤鸭。”
- 大堂经理会判断意图，然后把单子递给“烤鸭厨师”（子助理 A）。
- 你说：“我要一碗阳春面。”
- 经理会把单子交给“面点师”（子助理 B）。
- 如果你问：“今天天气怎么样？”（通用闲聊）
- 经理自己用手机查一下就回答你了，不需要惊动后厨。

在这个架构中：
1. **主助理 (Primary Assistant)**：Prompt 很短，它的核心职责是“意图识别”与“路由”。它只拥有少数通用工具，以及几个特殊的“转交工具”（Transfer Tools）。
2. **专业子助理 (Specialized Assistants)**：Prompt 非常详细，拥有专属领域的工具（如订机票专用 API）。它们只负责自己那摊事，做完了或者遇到搞不定的问题，就把任务交还给大堂经理（Escalate）。

<!-- 图表源文件：img/diagrams/07-diagram-01.mmd；视觉风格：Linear 紫色科技感 -->
<p align="center">
  <a href="img/diagrams/07-diagram-01.svg">
    <img src="img/diagrams/07-diagram-01.svg" alt="1. 架构理念：前台大堂经理与后厨专家" width="760">
  </a>
</p>

## 2. 在 LangGraph 中如何实现？

这个入门版先把主助理与专业助理平铺在同一张图里，用 **状态栈（Dialog State Stack）**记录当前谁在接待用户。它还不是真子图：12 节会再讲如何把一个完整子图作为父图节点。按当前官方分类，本节这种“活跃角色写进状态、专业助理直接继续和用户对话”的体验更接近 **Handoffs**。

### Step 1: 在状态中加入对讲机频段 (Dialog State)

我们在交接本 `State` 里加一个字段 `dialog_state`，它记录了当前正在和用户对话的是谁。

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
    # 记录当前谁在接客。如果是空，说明是大堂经理；如果是 "update_flight"，说明切到了航班助理。
    dialog_state: Annotated[list[str], update_dialog_stack] 
```

### Step 2: 给主助理配备“转交工具”

所谓转交，在代码里其实就是**假装它是一个工具**。
主助理看到用户想订机票，它就调用 `ToFlightBookingAssistant` 工具。

```python
# 这不是一个真去发网络请求的工具，这是一个意图模型！
class ToFlightBookingAssistant(BaseModel):
    """当用户需要预订、修改或取消航班时，将对话委托给航班助理。"""
    request: str = Field(description="你需要让航班助理帮忙做的具体需求")
```

当 LangGraph 发现主助理输出了这个工具调用时，条件边（Conditional Edge）就会捕捉到，并把流程路由到航班助理的入口节点。同时，把 `dialog_state` 修改为 `update_flight`。

### Step 3: 子助理的“退堂鼓” (Complete or Escalate)

子助理干完活后，或者遇到用户的要求超纲了（比如订着机票，用户突然问“那边的酒店怎么样”），子助理是没有酒店工具的。
这时候，子助理必须把控制权还给主助理。

我们给所有子助理都配备一个统一的脱壳工具：`CompleteOrEscalate`。

```python
class CompleteOrEscalate(BaseModel):
    """当任务完成，或者用户偏离了你的专业范围时，调用此工具将控制权交还主助理"""
    cancel: bool = True
    reason: str = Field(description="交还给主助理的原因")
```

当子助理调用这个工具时，LangGraph 会将 `dialog_state` 的栈顶元素 `pop` 掉，重新回到主助理的逻辑分支。

通过这种压栈、弹栈和工具回执配对，我们得到了一套可观察的控制权交接。不过 Agent 越多，路由成本、上下文传递和排错成本也越高，不能理解成可以“无限扩展”。

## 3. 交接时到底传什么？

**生活化比喻：** 客服转接电话时，原客服既不能只说“你接一下”，也不该把用户十年的所有录音都发给同事。至少要交代：用户当前要办什么、已经查过什么、哪些工具调用还没回执。

本例为了教学透明，共享完整 `messages`。生产项目要明确三件事：

1. 转交工具的名字和描述是否让主助理知道“什么时候该交给谁”；
2. 接手者收到完整历史、筛选后的消息，还是一段结构化摘要；
3. 交回主助理时，是返回最终结果，还是把整个子助理轨迹塞回来。

这就是多智能体的上下文工程。传得太少会缺背景，传得太多会烧 Token、泄露无关信息，还可能破坏 tool call 与 ToolMessage 的配对。

## 4. 扩展阅读

**官方文档**
- Multi-agent 总览与五种当前模式：[docs.langchain.com/oss/python/langchain/multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent)
- Handoffs（活跃 Agent 状态、消息交接与实现方式）：[docs.langchain.com/oss/python/langchain/multi-agent/handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)
- Subagents（主 Agent 把专家作为工具调用，与本节对比）：[docs.langchain.com/oss/python/langchain/multi-agent/subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)

> 📁 **本节示例代码**：[code/examples/07_multiagent_stack_demo.py](code/examples/07_multiagent_stack_demo.py) —— 无需 API Key 即可运行，可与本文对照着跑。

---

**下一节：** 多智能体编队已经就位，但每个“助理”内部靠什么干活？我们将补上所有 Agent 共用的核心闭环——工具调用循环（ToolNode / tools_condition），以及高层快车道 `create_agent`。
