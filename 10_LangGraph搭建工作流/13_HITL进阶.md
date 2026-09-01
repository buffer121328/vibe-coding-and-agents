# 13 HITL 进阶：interrupt() 动态中断与 Command 恢复

06 节我们用 `interrupt_before` 在敏感节点前踩了刹车。它好用，但有两个先天局限：刹车点**编译期写死**（想在运行时按需刹车？不行），暂停时**只能看状态**（想附一个结构化的“待审批数据包”给审批人？得自己从状态里扒）。

LangGraph 1.x 官方现在更推荐**节点内动态中断** `interrupt()`。06 节用 `update_state` 补拒绝回执，是理解静态断点和检查点的正式做法；本节进一步把审批条件与数据包放进节点，组成新项目更适合的 HITL 工具箱。16 节旅行助手已经按本节方式迁移。

## 1. interrupt()：想踩就踩的动态刹车

**生活化比喻：** `interrupt_before` 像地铁线路上固定的安检口——进站必检，不管你今天带没带行李。`interrupt()` 则像快递柜：快递员（节点）跑到一半，发现“这个包裹超过 5000 元需要实名签收”，就地打住，把**包裹清单**放进快递柜，给你发个取件码。你验完货，用取件码回一句话（同意 / 拒绝 / 改地址），快递员**从原地继续跑**。

```python
from langgraph.types import interrupt, Command

def book_flight(state: State):
    ticket = pick_ticket(state)
    # 就地暂停：把结构化“待审批数据包”抛给调用方，等待人类答复
    decision = interrupt({
        "action": "订票确认",
        "flight": ticket.flight_no,
        "price": ticket.price,
        "refundable": ticket.refundable,
    })
    # 恢复后，decision 就是人类传入的答复值，代码原地继续
    if decision.get("approved"):
        return {"booking": confirm(ticket), "messages": [...] }
    return {"messages": [AIMessage(content=f"好的，已放弃订票：{decision.get('reason')}")]}
```

恢复的方式是把答案包在 `Command(resume=...)` 里重新调用图：

```python
# 第一次运行：执行到 interrupt() 处挂起
result = graph.invoke({"messages": [...]}, config)
# result["__interrupt__"] 里能看到刚才那个“包裹清单”

# 人类审批后：带着答复恢复（resume 的值会成为 interrupt() 的返回值）
graph.invoke(Command(resume={"approved": True}), config)
```

注意 `interrupt()` 的三条铁律（官方文档原话级别的重点）：

1. **必须挂 Checkpointer**——中断的本质是存档 + 退出；
2. **恢复时节点从头重跑**：`interrupt()` 之前的代码会再执行一遍，所以它前面的副作用要幂等，且 `interrupt()` 别包在裸 `try/except` 里（它靠抛特殊异常实现暂停，被吞了就永远停不下来）；
3. **resume 的值必须是可 JSON 序列化的**——它要被写进存档。

还有一个很容易在前端看错的细节：`interrupt()` 发生在节点函数内部时，节点还没有 `return`，所以这次节点的业务 State 增量也还没有正式提交。大额转账在组长通过、等待老板二审时，Checkpoint 会记录新的中断数据包和恢复历史，但 `log` 字段要等 `transfer` 节点完整结束后才一次写回。这不是状态丢了，而是节点还没“交卷”。配套工作台把 **Checkpoint State / next / interrupt 数据包 / resume 历史** 分开显示，正是为了看清这层区别。

## 2. 静态刹车 vs 动态刹车怎么选？

| 手段 | 刹车时机 | 能否携带审批数据 | 官方定位 |
| :--- | :--- | :--- | :--- |
| `interrupt_before` / `interrupt_after` | 编译期写死在节点边界 | 不能（自己读状态） | 调试用静态断点 |
| `interrupt()` | 节点内部任意位置、可按条件触发 | 能（任意 JSON 数据包） | HITL 生产首选 |

官方文档把静态断点归到“Debugging with interrupts（调试用）”，而把审批类需求统统指向 `interrupt()`。一个实用判断：**刹车条件依赖运行时数据**（比如“只有金额超过 5000 才拦”）时，只能用 `interrupt()`——静态刹车不认金额。

## 3. 进阶姿势三连

### 3.1 条件拦截：该拦才拦

```python
def book_hotel(state: State):
    hotel = search(state)
    if hotel.price > 5000:               # 贵的才惊动老板
        decision = interrupt({"hotel": hotel.name, "price": hotel.price})
        if not decision["approved"]:
            return {"messages": [AIMessage(content="已按您的要求换一家更便宜的")]}
    return {"booking": confirm(hotel)}   # 便宜的直接订，不打扰人类
```

### 3.2 多级审批：先组长后老板

```python
def transfer_money(state: State):
    amount = state["amount"]
    if not interrupt({"level": "组长审批", "amount": amount})["approved"]:
        return {"messages": [AIMessage(content="组长驳回")] }
    if amount > 100000 and not interrupt({"level": "老板审批", "amount": amount})["approved"]:
        return {"messages": [AIMessage(content="老板驳回")] }
    return {"receipt": do_transfer(amount)}
```

恢复时逐级给 `Command(resume=...)`，每恢复一次走完一层审批再停下一次——中断会像快递柜一样**排队**，官方支持一次并行挂起多个 interrupt，恢复时按 interrupt ID 对号入座。

### 3.3 与流式配合：审批 UI 的正确姿势

前端做审批界面时，用 `stream` 模式持续收事件；收到 `__interrupt__` 事件就弹出审批卡片，用户点击后发送 `Command(resume=...)` 继续流式接收。`interrupt()` 抛出的数据包就是审批卡片的数据源，不再需要前端去猜“现在卡在哪一步”。

## 4. 扩展阅读

**官方文档**
- Interrupts（interrupt / Command(resume) / 多重中断 / 子图行为的官方母本）：[docs.langchain.com/oss/python/langgraph/interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- Use time-travel（拒绝工具调用与改道的底层机制）：[docs.langchain.com/oss/python/langgraph/use-time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- 图 API 概念（Command 的全部变体与适用边界）：[docs.langchain.com/oss/python/langgraph/graph-api](https://docs.langchain.com/oss/python/langgraph/graph-api)

> 📁 **本节示例代码**：[code/examples/13_hitl_interrupt_demo.py](code/examples/13_hitl_interrupt_demo.py) —— 无需 API Key 即可运行，可与本文对照着跑。

---
**下一节：** 学了这么多 StateGraph 的招式，其实 LangGraph 还有第二套武功：Functional API——给现有 Python 函数加上持久化与 HITL，只需两个装饰器。下一节讲两套 API 怎么选。
