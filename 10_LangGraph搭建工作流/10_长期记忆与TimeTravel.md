# 10 长期记忆（Store）与 Time Travel 时间穿梭

06 节我们学了 Checkpointer——但它只负责“一局游戏内”的存档：换个 `thread_id`（新会话），Agent 就得了失忆症。用户昨天说过“我对花生过敏”，今天再来订餐，Agent 毫无印象。这一节补齐记忆的另一半：**跨线程的长期记忆**，以及一个彩蛋能力——**Time Travel（时间穿梭）**。

## 1. 两层记忆：存档柜 vs 会员档案

**生活化比喻：**
- **Checkpointer（短期记忆）**像网吧的**存档柜**：你今天的游戏进度（对话状态）存在柜子里，凭票根（`thread_id`）随时取。但换个网吧（新会话），柜子就跟你没关系了。
- **Store（长期记忆）**像理发店的**会员档案**：你的偏好、禁忌、历史消费记在店里，不管你哪天来、找哪位理发师，翻档案就知道“3 号椅，张先生，两侧剪短，不打薄”。

| 维度 | Checkpointer（短期） | Store（长期） |
| :--- | :--- | :--- |
| 作用域 | 单个线程（一次会话） | 跨线程（所有会话共享） |
| 存什么 | 完整状态快照（消息、变量） | 精挑细选的事实/偏好/画像 |
| 类比 | 游戏存档 | 会员档案卡 |
| 实现 | `MemorySaver` / SQLite / Postgres | `InMemoryStore` / Postgres 等 |

## 2. Store 三板斧：put / get / search

Store 里的每条记忆放在一个**命名空间（namespace）**下，就像档案柜按“客户姓名”分抽屉，抽屉里再按“条目 ID”放卡片：

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()

# 存：namespace 相当于 (用户ID,) 两级抽屉，key 是卡片编号
store.put(("user_123",), "allergy", {"food": "花生"})
store.put(("user_123",), "preference", {"seat": "靠窗"})

# 取：按 key 精确取一张卡片
item = store.get(("user_123",), "allergy")

# 搜：按前缀搜整个抽屉，翻出所有卡片
items = store.search(("user_123",))
```

把它接进图里只需两步——编译时传入 `store`，节点函数里多收一个 `store` 参数：

```python
builder = StateGraph(State)
# ... 添加节点 ...
graph = builder.compile(store=store)

def assistant(state: State, *, store: BaseStore):
    profile = store.search(("user_123",))       # 开工前先翻档案
    context = "；".join(f"{i.key}={i.value}" for i in profile)
    # ... 把 context 拼进 Prompt ...
```

> 💡 **进阶：语义检索**。`InMemoryStore` 支持 `index` 配置接入 Embedding 模型，之后 `store.search(query, query="用户不能吃什么")` 就能按**语义相似度**翻档案，而不是按前缀精确匹配——档案多到翻不动时特别有用。生产环境可换 `PostgresStore` 等持久化实现。

**该记什么、谁来记？** 两个常见做法：一是把“记忆写入”做成一个工具，让模型在对话中自己决定“这条值得记下来”（可参考官方 langmem 库）；二是在对话结束后用一个小模型批量总结“本次会话值得沉淀的事实”。别什么都记——档案塞满垃圾，翻起来比没档案还慢。

## 3. Time Travel：给图装一个“时间机器”

有了 Checkpointer，图在**每一步**都留有快照。Time Travel 就是利用这些历史快照，做两件事：**回放（Replay）**与**改道（Fork）**。

**生活化比喻：** 围棋复盘。棋下完了（甚至输了），你可以回到第 37 手，看看当时如果换一种下法会怎样——历史棋谱（快照）都还在，随时翻回去重演。

```python
# 1. 列出全部历史快照（像翻棋谱）
for i, snap in enumerate(graph.get_state_history(config)):
    print(i, snap.values["messages"][-1].content[:30])
    print("   由节点", snap.next, "继续可走到下一步")

# 2. 回放：拿历史某一刻的 config 原样重跑（参数全不变，结果一般也不变）
old_config = next(s.config for s in graph.get_state_history(config))
graph.invoke(None, old_config)   # 传 None 表示“接着这个快照往下走”

# 3. 改道（Fork）：回到过去某一步，改掉当时的状态，然后分岔出新历史
graph.update_state(old_config, {"messages": [HumanMessage("改成去大阪，预算砍半")]})
graph.invoke(None, old_config)   # 同一个快照，但输入已变 → 长出一条新分支
```

`update_state` 还有个重要参数 `as_node`：它声明“这次修改**假装**是哪个节点写的”。如果不指定，修改会被算作系统强插；指定 `as_node` 后，图会从该节点之后的边继续正常流转——这是 06 节“伪造 ToolMessage 拒绝工具调用”手法的正式版。

Time Travel 最实用的三个场景：

1. **调试**：某个节点行为不对？回到它前一步，改个输入重跑，不用从头执行整个流程；
2. **HITL 拒绝**：06 节的“老板不同意，改需求重来”本质就是一次 Fork；
3. **分支对比**：同一个起点跑出 A/B 两条历史，对比哪种路由策略效果更好。

## 4. 扩展阅读

**官方文档**
- Memory 概览（短期 / 长期记忆并列讲解）：[docs.langchain.com/oss/python/langgraph/memory](https://docs.langchain.com/oss/python/langgraph/memory)
- Stores（Store API 与语义检索细节）：[docs.langchain.com/oss/python/langgraph/stores](https://docs.langchain.com/oss/python/langgraph/stores)
- Use time-travel（回放 / 改道 / update_state 完整教程）：[docs.langchain.com/oss/python/langgraph/use-time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- Persistence（Checkpointer 与 Store 的总览）：[docs.langchain.com/oss/python/langgraph/persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- langmem（官方记忆工程库：记忆提取、更新、遗忘策略）：[github.com/langchain-ai/langmem](https://github.com/langchain-ai/langmem)

> 📁 **本节示例代码**：[code/examples/10_memory_timetravel_demo.py](code/examples/10_memory_timetravel_demo.py) —— 无需 API Key 即可运行，可与本文对照着跑。

---
**下一节：** 跑到一半程序崩了、接口超时了，能不能像单机游戏一样“从断点复活”？下一节讲 Durable Execution 持久执行与容错三件套（重试、超时、缓存）。
