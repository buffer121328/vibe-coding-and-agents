# Skill：假模型驱动的 Web 层测试（本项目回归套路）

> 用途：FastAPI/Air 改造前后，如何在不花一分钱 API Key 的情况下验证整条 Web 链路。
> 前置先例：`travel_agent_v2/tests/test_new_mechanisms.py`（已验证可用的套路，本 skill 是它的通用化）。

## 1. 核心思路

被测对象是"图 + HTTP 壳"，大模型只是其中一个可替换的零件。用 `langchain_core` 内置的**假聊天模型**按剧本返回消息（含 `tool_calls`），即可让主助理、子助理、转交路由、工具执行全部真实运转。

```python
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

def tc(name, args, id_):   # 构造一个工具调用
    return {"name": name, "args": args, "id": id_, "type": "tool_call"}

class Fake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self        # 关键！主助理在 import 时会调用 llm.bind_tools(...)

import core.llm_config as llm_cfg
llm_cfg.llm = Fake(responses=[...])   # 必须在 import 业务模块之前打补丁
```

## 2. 铁律（每条都实测踩过）

1. **补丁时机**：`llm_cfg.llm = Fake(...)` 必须发生在 import `core.sub_agents` / `core.primary_agent` / `main` **之前**——它们在 import 期就把 llm 绑进 runnable；
2. **bind_tools 必须覆盖**：假模型默认不支持 bind_tools，不覆盖会在 import 期直接崩；
3. **剧本队列是全局一次性的**：主助理和子助理共享同一个假模型实例， responses 按调用顺序消费。写剧本时按"一轮对话消费几条"精确计数，否则会静默错位或耗尽报错；
4. **一轮对话的典型消耗**：主助理 1 条 + 子助理 N 条 + 收尾 1 条；纯工具轮（如并行比价子图）中间不耗剧本。

## 3. 剧本参考（三个场景的完整消耗清单）

```python
responses = [
    # 场景一：订车（真子图 + 子图内 interrupt）——5 条
    AIMessage(content="", tool_calls=[tc("ToBookCarRental", {...}, "c1")]),   # 主助理转交
    AIMessage(content="", tool_calls=[tc("search_car_rentals", {...}, "c2")]),# 安全工具
    AIMessage(content="", tool_calls=[tc("book_car_rental", {...}, "c3")]),   # 敏感工具 -> 拦截
    # —— 此处 approve：恢复后 ——
    AIMessage(content="", tool_calls=[tc("CompleteOrEscalate", {...}, "c4")]),# 交还主助理
    AIMessage(content="您的租车已订好，还有什么可以帮您？"),
    # 场景二：Store 偏好 —— 2 条
    AIMessage(content="", tool_calls=[tc("recall_preferences", {}, "c5")]),
    AIMessage(content="我记得您喜欢靠窗的座位。"),
    # 场景三：并行比价（Send 子图中间零消耗）—— 2 条
    AIMessage(content="", tool_calls=[tc("ToMultiQuote", {...}, "c6")]),
    AIMessage(content="四类行情已汇总。"),
]
```

## 4. Web 层测试的三层打法

```python
# 第 0 步：环境与补丁就绪后
update_dates()                 # 刷新演示数据库（路径基于源码位置，cwd 无关）
from main import build_graph   # 或 from web.app import app（FastAPI/Air 版，app 导入期自建图）
```

| 层 | 打法 | 断言什么 |
| :--- | :--- | :--- |
| 处理函数层 | 直接调 `chat_turn / approve / reject` | 挂起标记 `pending`、历史消息内容、偏好面板数据 |
| HTTP 层 | `TestClient(app)`（httpx 驱动，无需起服务器） | 状态码、JSON 结构、`GET /` 页面含关键元素 |
| 真实服务层 | 起线程跑 uvicorn + `urllib` 打请求 | 仅最后冒烟一次（页面 200、关键接口 200） |

> 落地文件（FastAPI + Air 改造后）：处理函数层 `tests/test_new_mechanisms.py`、HTTP 层 `tests/test_web_api.py`、真实服务层 `tests/smoke_real_server.py`，均为 python 直跑脚本、无需 API Key。

注意：处理函数层与 HTTP 层**共享同一个假模型队列**——要么给足剧本，要么分层分进程跑，否则后跑的层会"无米下锅"。

## 5. HTTP 层断言参考（FastAPI 版）

```python
from fastapi.testclient import TestClient
client = TestClient(app)

def test_page_renders():
    r = client.get("/")
    assert r.status_code == 200 and "Trip Assistant" in r.text

def test_chat_quote_flow():
    r = client.post("/api/chat", json={"message": "帮我看看全部行情"})
    data = r.json()
    assert r.status_code == 200
    assert any("已同时查完四类行情" in m["content"] for m in data["history"])
    assert not data["pending"]          # 比价无敏感操作，不应挂起

def test_method_mismatch():
    assert client.post("/api/state").status_code == 405   # FastAPI 明确 405，比手写 404 友好
```

## 6. 收尾纪律

- 测试会写演示数据库（订车场景）与内存 Store——进程结束即消失，落盘的 `travel_new.sqlite` 会在下次 `update_dates()` 重建，无需专门清理；
- 测试脚本放在 `tests/` 内，命令行入口保持**无 API Key 可跑**，作为项目常驻冒烟。
