# 10.10 长期记忆（Store）与 Time Travel

06 节的 Checkpointer 只负责**一局游戏内**的存档：换一个 `thread_id`，Agent 就失忆。用户昨天说过“我对花生过敏”，今天再来订餐，它毫无印象。这一节补齐记忆的另一半：**跨线程的长期记忆**，以及一个经常被误解的能力——**Time Travel**。

---

## 1. 两层记忆：这局进度 vs 会员档案

- **Checkpointer（短期）**像网吧的存档柜：今天这局游戏的进度凭票根（`thread_id`）取。换一台机器、换一个会话，柜子就跟你无关。
- **Store（长期）**像健身房的会员卡：偏好、禁忌、历史记录记在店里。哪天来、找哪位教练，翻档案就知道“3 号器械，张先生，膝盖旧伤，深蹲不要上大重量”。

| 维度 | Checkpointer | Store |
| :--- | :--- | :--- |
| 作用域 | 单个线程（一次会话） | 跨线程（按你定的命名空间共享） |
| 存什么 | 完整状态快照（消息、变量） | 精挑过的事实 / 偏好 / 画像 |
| 类比 | 这局游戏存档 | 会员档案 |
| 常见实现 | `MemorySaver` / `SqliteSaver` / `PostgresSaver` | `InMemoryStore` / Postgres 等 |

大多数应用两套一起用：Checkpointer 管“这次聊到哪了”，Store 管“这个人是谁”。Agent Server / LangGraph Platform 可以代管存储，本地开发则自己传入。

长对话还要把短期历史裁剪或摘要，否则上下文窗口会被撑满。第九章的 `trim_messages`、Summarization 中间件，和这里的 Checkpointer 是同一层问题的不同工具。

---

## 2. Store 三个方法：put / get / search

每条记忆放在一个 **namespace（命名空间）** 下。可以把它想成档案柜的抽屉标签，常用 `(user_id,)` 或 `(tenant_id, user_id)`，再在抽屉里用 `key` 放卡片：

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()

store.put(("user_123",), "allergy", {"food": "花生", "severity": "过敏性休克风险"})
store.put(("user_123",), "preference", {"seat": "靠窗", "meal": "素食"})
store.put(("user_123",), "recent_trip", {"city": "大阪", "date": "2026-08-12"})

item = store.get(("user_123",), "allergy")
items = store.search(("user_123",))
```

接进图里两步：编译时传入 `store`，节点函数多收一个 `store` 参数（1.x 也可以从 `runtime.store` 取）：

```python
from langgraph.store.base import BaseStore

graph = builder.compile(store=store, checkpointer=memory)

def assistant(state: State, *, store: BaseStore):
    profile = store.search((state["user_id"],))
    context = "；".join(f"{i.key}={i.value}" for i in profile)
    # 把 context 拼进系统提示，再调用模型
    return {"reply": f"已读取档案：{context or '（暂无）'}"}
```

多租户一定要把租户 ID 放进 namespace，防止 A 公司的偏好被 B 公司的会话搜到。

### 语义检索：档案多到翻不动时

`InMemoryStore` 可以配 Embedding 索引。之后 `search` 不再只是“列出整个抽屉”，而是按**语义相似度**取卡片：

```python
store = InMemoryStore(
    index={"dims": 1536, "embed": your_embeddings}  # 真实项目接入 Embedding 模型
)
hits = store.search(("user_123",), query="用户不能吃什么")
```

生产换 Postgres 等持久化 Store，并加上 `filter` 做结构化过滤（例如只要 `type=preference`）。官方记忆工程库 [langmem](https://github.com/langchain-ai/langmem) 还提供提取、更新、遗忘策略，不必从零设计“什么该记、什么该删”。

### 该记什么、谁来记？

两种常见写法：

1. **热路径**：把“写入记忆”做成工具，模型在对话中自己决定“这条值得记下”。立刻能用，但增加延迟和复杂度；
2. **后台**：对话结束后用小模型批量总结“本次值得沉淀的事实”。不挡用户，但要想好触发频率。

别什么都记。一次性验证码、临时行程、身份证号，不该当作普通偏好。稳定偏好和用户确认过的事实，才配长期存放，并写上来源、更新时间、适用范围。读取时应让用户知道哪些信息影响了当前回答，并允许更正或删除。

---

## 3. Time Travel：回放不是放录像

有了 Checkpointer，图在每一步都留有快照。Time Travel 做两件事：**回放（Replay）**和**改道（Fork）**。

像围棋复盘：棋谱还在，你可以回到第 37 手，换一种下法。但复盘时如果那一步要重新落子，棋盘上就会真的再下一子——不是看录像。

```python
# 1. 列出历史快照
for i, snap in enumerate(graph.get_state_history(config)):
    print(i, snap.values["messages"][-1].content[:40])
    print("   next =", snap.next)

# 2. 回放：拿历史某一刻的 config 继续
#    该快照之前的步骤会跳过，之后的节点会重新执行
old_config = next(s.config for s in graph.get_state_history(config))
replayed = graph.invoke(None, old_config)

# 3. 改道：改掉当时的状态，分岔出新历史
fork_config = graph.update_state(
    old_config,
    {"messages": [("user", "改成去大阪，预算砍半")]},
    as_node="planner",
)
graph.invoke(None, fork_config)
```

要点：

- **Replay 会重跑下游节点。** 模型可能换一种回答，接口可能返回新价格，副作用也可能再次发生。回放前仍要检查幂等，不要把“参数一样”当成“结果必然一样”。
- **`as_node` 声明这次修改相当于哪个节点写的**，从而决定沿哪条边继续。06 节跳过敏感工具的正式驳回，就是这个用法。
- 应接住 `update_state` 返回的新 config，再从这个新检查点继续。

三个最实用的场景：调试时回到出错节点的前一步改输入；HITL 拒绝后 Fork 出新方案；同一起点跑 A/B 两条历史做对比。

Time Travel 不能让现实世界回到过去。历史节点如果已经调过外部写操作，重新执行前仍需幂等校验。测试时可先只用只读工具，确认分叉状态正确后再碰写操作。

> 📁 **本节示例代码**：[code/examples/10_memory_timetravel_demo.py](code/examples/10_memory_timetravel_demo.py)

---

## 扩展阅读

- Memory 概览：[memory](https://docs.langchain.com/oss/python/langgraph/memory)
- Stores 与语义检索：[stores](https://docs.langchain.com/oss/python/langgraph/stores)
- Use time-travel：[use-time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- Persistence 总览：[persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- langmem：[github.com/langchain-ai/langmem](https://github.com/langchain-ai/langmem)

---

**下一节：** 跑到一半程序崩了、接口超时了，能不能从断点复活？Durable Execution 与重试、超时、缓存三件套。
