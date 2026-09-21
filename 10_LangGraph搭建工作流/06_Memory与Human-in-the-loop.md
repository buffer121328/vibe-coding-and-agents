# 10.6 Memory 记忆与 Human-in-the-loop

前面几节，图已经能跑、能分叉、能并行。还剩两个很实际的问题：

1. **健忘**：状态默认只活在这一次调用的内存里。用户过了半天再问“我刚才说想去哪”，模型两眼一抹黑。
2. **没人签字**：模型决定清空数据库、扣费订机票时，你敢让它直接执行吗？

LangGraph 用同一套机制回答这两个问题：**Checkpointer（检查点）**。有了它，会话能续上，流程也能在闸门前停住。

---

## 1. Checkpointer：每走一步拍一张快照

可以把它想成单机游戏的存档点。每个超步结束，Checkpointer 就把当前 State 拍下来。只要用真正落盘的实现，进程重启后凭 `thread_id` 就能找回进度。

教学里最常见的是内存版：

```python
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

config = {"configurable": {"thread_id": "user_zhangsan_123"}}
graph.invoke({"messages": [("user", "我要订机票")]}, config)
```

同一 `thread_id` 再次调用，图会带着上次的消息和字段继续，而不是空白开局。

官方现在也把内存实现叫作 `InMemorySaver`（与 `MemorySaver` 同类：都在 RAM 里，进程一停就没了）。它适合课堂和单测，**兑不了“机器重启还能恢复”的承诺**。生产请换：

| 实现 | 放哪 | 什么时候用 |
| :--- | :--- | :--- |
| `MemorySaver` / `InMemorySaver` | 内存 | 教学、测试 |
| [`SqliteSaver`](https://docs.langchain.com/oss/python/langgraph/persistence) | 本地文件 | 开发机、小流量 |
| [`PostgresSaver`](https://docs.langchain.com/oss/python/langgraph/persistence) / `AsyncPostgresSaver` | PostgreSQL | 生产 |

`thread_id` 相当于办事单号。同一段会话继续用同一个；新任务误用旧号，会把历史状态带进来。服务端还要校验线程归属，不能只凭客户端传来的 ID 就允许读状态。

长线程的检查点会一直涨。生产上要设保留策略或定期裁剪，Postgres 里 `thread_id` 长度也有限制（文档写明不超过 255 字符）。

---

## 2. 静态断点：先看懂“停住—存档—恢复”

有了存档，就可以在危险节点前刹车。为了把底层过程看清楚，本节用编译期写死的 `interrupt_before`。它适合教学和调试；真正的生产审批应使用 13 节的节点内 `interrupt()`——那种能按运行时数据决定是否暂停，并能带上结构化审批包。

```python
graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["book_flight_sensitive_tools"],
)
```

运行过程是这样的：

1. 模型说“我要调用订票工具”；
2. 边指向 `book_flight_sensitive_tools`；
3. LangGraph 发现它在刹车名单里，保存快照，立刻返回（图处于暂停）；
4. 审批人在界面上看到待执行动作；
5. 点“同意”后，用**同一个** `thread_id` 再次调用，**不要传新消息，传 `None`**：

```python
graph.stream(None, config)
```

图读取存档，发现上次停在订票节点前，于是进入该节点，完成订票。

---

## 3. 老板不同意：补回执，而不是塞一句新话

历史里已经有一条带 `tool_calls` 的 AI 消息。如果没有同 `tool_call_id` 配对的 `ToolMessage`，消息历史会残缺，后续模型可能直接报错（官方错误码 [INVALID_CHAT_HISTORY](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CHAT_HISTORY)）。

正确动作分三步：取出待审批的工具调用 → 构造一一配对的拒绝回执 → 用 `update_state(..., as_node=...)` 把它记成“敏感工具节点的输出”，再传 `None` 从下一节点继续。

```python
from langchain_core.messages import ToolMessage

snapshot = graph.get_state(config)
tool_calls = snapshot.values["messages"][-1].tool_calls

rejections = [
    ToolMessage(
        tool_call_id=call["id"],
        content="工具调用被用户拒绝。原因：太贵了，请找低于 1000 元的方案。",
    )
    for call in tool_calls
]

fork_config = graph.update_state(
    config,
    {"messages": rejections},
    as_node="book_flight_sensitive_tools",
)
graph.invoke(None, fork_config)
```

`as_node` 的意思是：“这份更新相当于敏感工具节点已经返回”。图沿着该节点之后的边继续，却不会真的扣款。`update_state` 会创建新检查点，不会偷偷改掉原历史。

> ⚠️ 两种审批不要混为一谈：本节的 `interrupt_before + update_state` 是理解检查点的教学路径；13 节的 `interrupt() + Command(resume=...)` 才是新项目做生产审批的首选。旅行助手实战已经采用后一种。

---

## 检查点保存的是进度，不是业务事务

检查点能让图从某一步继续，但**不会自动撤销**已经发出的邮件、已扣款订单、已写入外部系统的数据。中断前后的外部操作需要幂等键、事务或补偿，尤其要防止恢复时再执行一遍。

人工审批应展示将执行的动作、关键参数和影响范围。审批人改参数后，程序要重新校验；若等待期间库存或价格已经变了，也应重新确认，而不是机械执行旧计划。

> 📁 **本节示例代码**：[code/examples/06_memory_hitl_demo.py](code/examples/06_memory_hitl_demo.py) —— 同时演示批准续跑和 `update_state` 正式驳回。

---

## 扩展阅读

- Persistence（检查点、线程、`update_state`）：[persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- Interrupts（静态断点与动态 `interrupt()` 的边界）：[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- 工具调用必须与 ToolMessage 配对：[INVALID_CHAT_HISTORY](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CHAT_HISTORY)

---

**下一节：** 一个助理忙不过来、Prompt 也塞不下时，怎样用主助理 + 专业助理做控制权交接。
