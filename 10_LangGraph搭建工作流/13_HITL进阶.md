# 10.13 HITL 进阶：interrupt() 动态中断与 Command 恢复

06 节用 `interrupt_before` 在敏感节点前踩了刹车。它好懂，但有两个先天局限：刹车点**编译期写死**（运行时按金额决定拦不拦？做不到）；暂停时**只能看状态**（想给审批人一份结构化数据包，得自己从 State 里扒）。

LangGraph 1.x 官方现在把静态断点归到“调试用”，把审批类需求指向节点内 **`interrupt()`**。06 节用 `update_state` 补拒绝回执，是理解检查点的正式做法；本节把审批条件和数据包放进节点，组成新项目更合适的工具箱。16 节旅行助手已经按这种方式迁移。

---

## 1. interrupt()：想踩就踩的动态刹车

`interrupt_before` 像地铁固定安检口——进站必检，不管你今天有没有行李。`interrupt()` 更像寄件柜：流程跑到一半，发现“这个包裹超过 5000 元需要实名签收”，就地打住，把**包裹清单**放进柜子，给你发取件码。你验完货，回一句同意 / 拒绝 / 改地址，流程从原地继续。

```python
from langgraph.types import interrupt, Command

def book_flight(state: State):
    ticket = pick_ticket(state)
    decision = interrupt({
        "action": "订票确认",
        "flight": ticket.flight_no,
        "price": ticket.price,
        "refundable": ticket.refundable,
    })
    if decision.get("approved"):
        return {"booking": confirm(ticket)}
    return {"messages": [("assistant", f"已放弃订票：{decision.get('reason')}")]}
```

恢复时把答案包在 `Command(resume=...)` 里重新调用：

```python
result = graph.invoke({"messages": [...]}, config)
# result["__interrupt__"] 里是刚才那份包裹清单
# 新代码更推荐 stream_events v3 的 interrupted 事件

graph.invoke(Command(resume={"approved": True}), config)
```

三个硬约束：

1. **必须挂 Checkpointer。** 中断的本质是存档 + 退出。生产用落盘实现。
2. **恢复时节点从头重跑。** `interrupt()` 之前的代码会再执行一遍，所以它前面的副作用要幂等；也**不要**把 `interrupt()` 包在裸 `try/except` 里——它靠抛特殊异常实现暂停，被吞了就永远停不下来。
3. **resume 的值必须可 JSON 序列化。** 它要写进存档，函数对象、数据库连接都不行。

还有一个前端容易看错的细节：`interrupt()` 发生在节点函数内部时，节点还没有 `return`，这次的业务 State 增量也还没正式提交。大额转账在组长通过、等待老板二审时，Checkpoint 会记录新的中断包和恢复历史，但 `log` 字段要等 `transfer` 节点完整结束后才一次写回。这不是状态丢了，而是节点还没交卷。配套工作台把 Checkpoint State / next / interrupt 数据包 / resume 历史分开显示，正是为了看清这层区别。

同一节点里不要 `while True` 地循环调用 `interrupt()`，也不要打乱多次中断的顺序——恢复时按调用次序（以及并行时的 interrupt ID）对号入座。校验逻辑放在 State + 条件边里，而不是靠循环中断硬撑。

---

## 2. 静态刹车 vs 动态刹车

| 手段 | 刹车时机 | 能否携带审批数据 | 官方定位 |
| :--- | :--- | :--- | :--- |
| `interrupt_before` / `interrupt_after` | 编译期写死在节点边界 | 不能（自己读状态） | 调试用静态断点 |
| `interrupt()` | 节点内部任意位置、可按条件触发 | 能（任意 JSON 数据包） | HITL 生产首选 |

一个实用判断：**刹车条件依赖运行时数据**（“只有金额超过 5000 才拦”）时，只能用 `interrupt()`。静态刹车不认金额。

`Command(resume=...)` 是调用方在中断之后传入的输入。`update` / `goto` 属于节点返回值。不要把 `Command(update=...)` 当成下一轮用户消息。

---

## 3. 三种进阶用法

### 3.1 条件拦截：该拦才拦

```python
def book_hotel(state: State):
    hotel = search(state)
    if hotel.price > 5000:
        decision = interrupt({"hotel": hotel.name, "price": hotel.price})
        if not decision["approved"]:
            return {"messages": [("assistant", "已按您的要求换一家更便宜的")]}
    return {"booking": confirm(hotel)}
```

便宜的订单不打扰人；贵的才弹出审批卡。审批卡片应把动作翻译成具体影响，例如“把订单 123 的金额从 300 元改为 280 元”，而不是只显示函数名 `update_order`。必要时展示原值、新值、调用原因和有效期限。

### 3.2 多级审批：先组长后老板

```python
def transfer_money(state: State):
    amount = state["amount"]
    if not interrupt({"level": "组长审批", "amount": amount})["approved"]:
        return {"messages": [("assistant", "组长驳回")]}
    if amount > 100000 and not interrupt({"level": "老板审批", "amount": amount})["approved"]:
        return {"messages": [("assistant", "老板驳回")]}
    return {"receipt": do_transfer(amount)}
```

恢复时逐级给 `Command(resume=...)`：每恢复一次走完一层，再停下一次。并行节点可以同时挂起多个 interrupt，恢复时用 `{interrupt_id: value}` 对号入座。

多人审批要记录谁在何时批准了什么。审批内容发生变化时，旧批准应失效；高风险操作可以要求两人确认或设置金额阈值。

### 3.3 与流式输出配合：审批 UI

前端用 `stream` / `stream_events` 持续收事件；收到中断就弹出审批卡片，用户点击后发送 `Command(resume=...)` 继续。`interrupt()` 抛出的数据包就是卡片的数据源，前端不必猜“现在卡在哪一步”。HITL 循环更推荐 `stream_events(..., version="v3")` 里的 `messages` / `values` / `interrupted` 投影。

副作用尽量放在中断**之后**，或封装成幂等任务。官方文档也是这个建议，见 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

> 📁 **本节示例代码**：[code/examples/13_hitl_interrupt_demo.py](code/examples/13_hitl_interrupt_demo.py) —— 小额一审、大额二审，无需 API Key。

---

## 扩展阅读

- Interrupts（官方母本）：[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- Time travel（拒绝工具调用与改道）：[use-time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- Command 的全部变体：[graph-api](https://docs.langchain.com/oss/python/langgraph/graph-api)

---

**下一节：** 学了这么多 `StateGraph` 的招式，其实还有第二套 API：Functional API——给现有 Python 函数加上持久化与 HITL，只需两个装饰器。
