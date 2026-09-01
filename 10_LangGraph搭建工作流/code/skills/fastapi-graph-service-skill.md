# Skill：用 FastAPI 包装 LangGraph 图为 Web 服务

> 用途：把 `travel_agent_v2/main.py` 里的 `build_graph()` 产物暴露为 HTTP API 时的关键模式与坑。
> 适用版本：FastAPI 0.115+（`air[standard]` 自带，无需单独安装）。

## 1. 核心心智模型

编译后的 LangGraph 图（`CompiledStateGraph`）是一个**进程内的普通 Python 对象**，包成 Web 服务只需要三件事：

1. **模块级单例**：图在应用启动时构建一次，所有请求共享；
2. **会话 = `thread_id`**：每个会话一个 `thread_id`，通过 `config={"configurable": {...}}` 传入；
3. **中断不是普通异常**：节点内 `interrupt()` 会让本次 `stream/invoke` 正常结束并保存检查点；从 `StateSnapshot.tasks[*].interrupts` 读取结构化数据包，用 `Command(resume=...)` 恢复。

```python
# app 启动时（模块级，只执行一次）
from main import build_graph
GRAPH = build_graph()

# 每个请求
config = {"configurable": {"passenger_id": PASSENGER_ID, "thread_id": thread_id}}
for _ in GRAPH.stream({"messages": [("user", message)]}, config, stream_mode="values"):
    pass                      # stream 返回惰性迭代器，必须消费！
snap = GRAPH.get_state(config)
pending = any(task.interrupts for task in snap.tasks) or bool(snap.next)
```

## 2. 本项目已踩实的关键模式（来自 web_ui.py 与 tests/）

| 模式 | 代码要点 |
| :--- | :--- |
| 消费 stream | `for _ in GRAPH.stream(...): pass` —— 不消费等于没执行 |
| 判断挂起 | 普通图读 `snap.tasks[*].interrupts`；嵌套子图还要沿 `task.state` 读取子图快照 |
| 看穿子图内部 | `task.state` 是**子图的 checkpoint config**；递归读取子图 `next/tasks/interrupts`，得到路径与数据包 |
| 批准 | `GRAPH.stream(Command(resume={"approved": True}), config)` |
| 驳回+修改 | `Command(resume={"approved": False, "reason": ...})`；图内审批节点为每个调用补齐 ToolMessage |
| 取完整历史 | `GRAPH.get_state(config).values["messages"]`，按 `AIMessage/ToolMessage/human` 分类渲染 |

## 3. FastAPI 路由设计（与现有处理函数一一对应）

现有 `web_ui.py` 已把业务逻辑解耦成纯函数（`chat_turn` / `approve` / `reject` / `new_session` / `_snapshot`），FastAPI 化只是给它们套 HTTP 壳：

```python
from fastapi import FastAPI
from pydantic import BaseModel

class ChatIn(BaseModel):
    message: str

api = FastAPI()

@api.post("/api/chat")
def chat(body: ChatIn) -> dict:
    return chat_turn(body.message)      # 直接复用已验证的纯函数

@api.post("/api/approve")
def do_approve() -> dict:
    return approve()
```

要点：
- **请求体用 Pydantic 模型**，天然获得校验与 OpenAPI 文档（`/docs`）；
- 处理函数是同步阻塞的（LLM 调用耗时），FastAPI 会自动丢进线程池，**不需要** async；
- 异常让框架兜底：图执行抛错时返回 500 + 简要信息即可，教学项目无需精细错误码。

## 4. 并发与会话的边界（教学项目的明确取舍）

- **单进程单 worker**：`uvicorn app:app`（不要 `--workers N`）。`MemorySaver` 和 `InMemoryStore` 都在进程内存里，多 worker 会各存各的档；
- **单全局会话**（与现 stdlib 版一致）：`SESSION["thread_id"]` 是模块级状态。多用户需要把 thread_id 下发到浏览器端并在请求头带回——列为"不做的扩展"；
- Graph 对象本身**非线程安全**（并发写同一个 thread 的 checkpoint 会冲突）：同一 `thread_id` 的请求应串行。教学单用户场景下不会触发，若要加固可给 `chat_turn` 加一把 `threading.Lock`。

## 5. 测试：fastapi.testclient

```python
from fastapi.testclient import TestClient
client = TestClient(app)        # httpx 驱动，无需启动真实服务器

def test_chat():
    r = client.post("/api/chat", json={"message": "帮我看看全部行情"})
    assert r.status_code == 200
    assert any("已同时查完四类行情" in m["content"] for m in r.json()["history"])
```

配合 `tests/test_new_mechanisms.py` 已有的"假模型补丁"套路（先 `llm_cfg.llm = Fake(...)` 再 import 应用模块），整条链路可以**无 API Key 全覆盖**。

## 6. 已知坑

1. `stream()` 惰性——见上；
2. `get_state(config)` 在会话第一条消息前调用是安全的（返回空快照）；
3. BaseHTTPRequestHandler 时代的 `POST /api/state` 404 之类的方法不匹配问题：FastAPI 会明确返回 405，且 `/docs` 里方法一目了然；
4. uvicorn 的 reload 模式会 fork 出新进程重复执行 `build_graph()`，联调时建议 `--reload` 只在改前端时开。
