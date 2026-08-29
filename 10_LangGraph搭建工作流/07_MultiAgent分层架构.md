# 07 Multi-Agent 分层架构设计

随着你的业务越来越复杂，你可能会发现一个严重的问题：**一个大模型的 Prompt 塞不下了**。

如果你想做一个“全能旅行助手”，它既要懂航班改签规则，又要懂租车计费标准，还要负责酒店退款。如果你把所有的规则、几十个工具全写在一个 Prompt 里，大模型一定会犯晕，产生“认知负荷过载”（通俗点说就是大脑超载，开始胡言乱语或者用错工具）。

怎么解决？答案是：**Multi-Agent（多智能体协作）**。

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

在 LangGraph 中，这本质上是一个**包含多个子图的巨型网络**。但为了保持状态干净，我们通常使用一种被称为 **“状态栈” (Dialog State Stack)** 的技巧。

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

通过这种“呼之即来，挥之即去”的转交机制，我们就构建出了一个高度解耦、可无限扩展的智能体团队！

> 📁 **本节示例代码**：[code/examples/07_multiagent_stack_demo.py](code/examples/07_multiagent_stack_demo.py) —— 无需 API Key 即可运行，可与本文对照着跑。

---

**下一节：** 多智能体编队已经就位，但每个“助理”内部靠什么干活？我们将补上所有 Agent 共用的核心闭环——工具调用循环（ToolNode / tools_condition），以及高层快车道 `create_agent`。
