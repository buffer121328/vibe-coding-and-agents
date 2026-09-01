# 06 Memory 记忆与 Human-in-the-loop (人类在环)

在前面几节，我们已经让大模型在状态图里跑了起来，也学会了条件路由、并行分发与流式调试。但这里还有两个很要命的实际问题：

1. **健忘症**：如果程序结束了，或者用户过了半天再来问一句“那我刚刚说想去哪来着？”，大模型是不记得的，因为状态只在内存里短暂存活。
2. **脱缰野马**：如果大模型决定调用一个工具“清空数据库”或“直接扣费订机票”，你敢让它直接执行吗？

LangGraph 1.x 用一个机制优雅地解决了这两个问题：**Checkpointer（检查点保存机制）**。

## 1. Checkpointer - 自动存档的“记忆面包”

**生活化比喻：**
想象你在玩单机游戏《黑神话：悟空》。如果你每次被 Boss 打死都要从第一关重新玩，你一定会崩溃。所以游戏有“土地庙”给你上香存档。

在 LangGraph 里，每个执行步（super-step）结束时，Checkpointer 都会拍一张“快照”（保存当前的 State）。只要使用真正落盘的 Checkpointer，程序或机器重启后就能凭 `thread_id` 找回进度。

最简单的是内存级保存（只适合教学和测试），生产环境应换成 Postgres 等持久化实现。`MemorySaver` 随进程消失，不能兑现“重启恢复”的承诺；11 节会专门拆解这条边界。

```python
from langgraph.checkpoint.memory import MemorySaver

# 1. 拿出一个记忆存储器
memory = MemorySaver()

# 2. 编译图的时候，把记忆存储器插进去
graph = builder.compile(checkpointer=memory)

# 3. 运行的时候，告诉它你是哪个存档（thread_id）
config = {"configurable": {"thread_id": "user_zhangsan_123"}}

# 即便这是第二次运行，只要 thread_id 不变，大模型就能接上之前的话茬
graph.invoke({"messages": [("user", "我要订机票")]}, config)
```

## 2. Human-in-the-loop (HITL) - “老板，请签字确认”

既然我们有了存档能力，那我们就解锁了 LangGraph 中最实用的高级特性：**中断与人工干预**。

**生活化比喻：**
想象你在公司里是一个实习生（大模型），你可以自己查资料、写方案（安全工具）。但如果你要动用公司账户打款（敏感工具），财务系统（LangGraph）会拦截你，说：“这个动作太危险，必须等老板（人类）签字同意。”。老板去开会了，没关系，你的状态被存在了“存档文件”里。等老板开完会回来，看了方案觉得没问题，点个头，流程继续往下走。

为了先看懂“停住—存档—恢复”的底层过程，本节使用静态断点 `interrupt_before`。它适合教学和调试；真正的生产审批应使用 13 节的节点内 `interrupt()`，因为它能按运行时数据决定是否暂停，并能携带结构化审批数据。

```python
# 编译时，告诉图：在进入 "book_flight_sensitive_tools" 这个节点之前，必须踩刹车！
graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["book_flight_sensitive_tools"]
)
```

### 它是怎么运行的？

1. 大模型说：“我要调用订票工具。”
2. 路线图指向了 `book_flight_sensitive_tools` 节点。
3. LangGraph 发现这个节点在“刹车名单”里，于是保存当前存档，立刻结束程序并返回（处于暂停状态）。
4. （老板的微信收到了一条审批消息）
5. 老板点击了“同意”。
6. 程序再次启动，传入同样的 `thread_id`，但**不需要传新的消息，直接传 `None`**：
   `graph.stream(None, config)`
7. LangGraph 会读取存档，发现上次停在了订票节点前，于是直接踩油门进入该节点，完成订票。

### 如果老板不同意呢？（正式版：补回执 + 修改存档）

如果老板看了一眼说：“等一下，这个机票太贵了，你换个便宜的。”
老板不需要执行危险工具，也不能随手把一份新输入塞给暂停中的图。此时历史里已经有一条 AI 工具调用；如果没有同 `tool_call_id` 配对的 `ToolMessage`，消息历史会残缺，后续模型可能直接报错。

正确动作分三步：找到待审批的工具调用、构造一一配对的拒绝回执、用 `update_state(..., as_node=...)` 把它记成“敏感工具节点的输出”，最后传 `None` 从下一节点继续。

```python
from langchain_core.messages import ToolMessage

# 1. 从暂停快照中取出模型刚才发起的全部工具调用
snapshot = graph.get_state(config)
tool_calls = snapshot.values["messages"][-1].tool_calls

# 2. 每个 tool_call_id 都补一条拒绝回执，不能漏配
rejections = [
    ToolMessage(
        tool_call_id=call["id"],
        content="工具调用被用户拒绝。原因：太贵了，请找低于 1000 元的方案。",
    )
    for call in tool_calls
]

# 3. 把回执记成敏感工具节点的输出：真正的订票节点不会执行
fork_config = graph.update_state(
    config,
    {"messages": rejections},
    as_node="book_flight_sensitive_tools",
)

# 4. 从新快照的下一节点继续，让助理读取拒绝原因并重新规划
graph.invoke(None, fork_config)
```

这里的 `as_node` 很关键：它告诉 LangGraph“这份更新相当于敏感工具节点已经返回”，图因此沿着该节点之后的边继续，却不会真的扣款或下单。`update_state` 会创建一个新检查点，不会偷偷篡改原历史。

> ⚠️ **别混淆两种审批方式**：本节的 `interrupt_before + update_state` 是理解检查点和静态断点的教学路径；13 节的 `interrupt() + Command(resume=...)` 才是新项目做生产审批的首选。旅行助手实战已经采用后一种方式。

## 3. 扩展阅读

**官方文档**
- Persistence（检查点、线程、`update_state` 与回放）：[docs.langchain.com/oss/python/langgraph/persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- Interrupts（静态断点与动态 `interrupt()` 的适用边界）：[docs.langchain.com/oss/python/langgraph/interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- INVALID_CHAT_HISTORY（工具调用与 ToolMessage 必须配对）：[docs.langchain.com/oss/python/langgraph/errors/INVALID_CHAT_HISTORY](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CHAT_HISTORY)

> 📁 **本节示例代码**：[code/examples/06_memory_hitl_demo.py](code/examples/06_memory_hitl_demo.py) —— 同时演示真实批准和 `update_state` 正式驳回，无需 API Key。

---

**下一节：** 一个 Agent 忙不过来怎么办？我们将引入“主助理 + 多个专家子助理”的 Multi-Agent 分层路由架构。
