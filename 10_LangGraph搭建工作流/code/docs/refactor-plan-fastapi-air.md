# 改造计划：travel_agent_v2 迁移到 FastAPI 后端 + Air 前端

> 状态：**已执行完毕（2026-08-29）**——六步全部完成，三层测试全绿。执行中的实测偏差已回写 skills（见 air-frontend-skill.md §7 实测补记）：
> - `air.Html` 子元素必须位置参数（`children=` 会被渲染成属性）；
> - `static/` 由 air 内置 HashedStatic 自动挂载并加内容哈希，无需手动 mount，但必须从 `travel_agent_v2` 目录启动；
> - 新增会话端点按本计划 §6 定为 `POST /api/session`（stdlib 版曾叫 `/api/new_session`）；
> - 新增 `tests/smoke_real_server.py`（真实服务层冒烟），测试入口保持 python 脚本直跑（项目未引入 pytest）。
> 编写日期：2026-08-29
> 配套 skills：[../skills/README.md](../skills/README.md)（动手前按序阅读）

## 1. 背景与目标

`travel_agent_v2` 当前的 Web 层（`web_ui.py`）是"零依赖"过渡方案：标准库 `http.server` + 手写路由 + 内嵌 HTML 大字符串。本改造把它升级为：

- **后端**：FastAPI（自动 OpenAPI 文档、Pydantic 请求校验、明确的 405/422 语义）；
- **前端**：Air 框架（feldroy/air，构建在 FastAPI 之上，Air Tags 用 Python 类生成 HTML）；
- **不变**：LangGraph 图层（`main.build_graph()`）、处理函数（`chat_turn/approve/reject/new_session/_snapshot`）、终端版 `main.py`、无 API Key 的测试套路。

**明确不做**（延续既有取舍）：生产部署/多 worker、多用户会话隔离、SSE 流式、鉴权、HTMX 交互改造（第一版保留原生 JS fetch）。

## 2. 现状盘点（改造的起点）

| 资产 | 状态 | 改造角色 |
| :--- | :--- | :--- |
| `main.py: build_graph()` | 已是可导入纯函数（Checkpointer + Store + 四助理 + 两个子图） | 原样复用 |
| `web_ui.py` 处理函数 | `chat_turn/approve/reject/new_session/_snapshot` 已与 UI 解耦，四场景测试覆盖 | 原样保留，迁入新位置 |
| `web_ui.py` HTTP/HTML 层 | `ThreadingHTTPServer` + `PAGE` 大字符串 | **整体替换**（FastAPI + Air） |
| `tests/test_new_mechanisms.py` | 假模型驱动，无 Key 跑通三机制 | 保留 + 新增 Web 层用例 |
| `requirements.txt` | 无任何 Web 框架依赖 | 新增 `air`（自带 fastapi/uvicorn） |

## 3. 选型事实卡（2026-08-29 核验，动手前建议复查）

- **Air**：PyPI 包名 `air`，当前 0.48.1（2026-04-03 发布），**alpha 状态**；要求 **Python >=3.13,<3.15**；构建在 FastAPI/Starlette/Pydantic 之上；官方文档 docs.airwebframework.org（含 llms-full.txt）。仓库 `github.com/feldroy/air`。⚠️ `air.feldroy.com` 是同名静态站生成器项目，勿混淆。
- **FastAPI**：由 `air[standard]` 或 air 依赖带入，无需单独钉版本。
- **本机环境**：当前只有 Python 3.12 —— **必须先解决 3.13**（见步骤 1）。

## 4. 目标架构

```
浏览器 ──HTTP──> uvicorn（单 worker）
                   └─ app = air.Air(fastapi_app=api)      # wrap 模式，单一应用
                        ├─ GET  /            -> Air Tags 渲染页面骨架 + 内嵌 JS
                        ├─ GET  /docs        -> FastAPI 自动 OpenAPI（白送）
                        └─ /api/*（FastAPI 路由 + Pydantic 请求体）
                             └─ 处理函数（复用自 web_ui.py）─> GRAPH 单例（build_graph()）
                                                                  ├─ Checkpointer（MemorySaver，进程内）
                                                                  └─ Store（InMemoryStore，进程内）
```

## 5. 目标文件结构（改动清单）

```
travel_agent_v2/
├── web/                      # 新增：Web 层包
│   ├── __init__.py
│   ├── app.py                # air.Air(fastapi_app=api) 装配 + GRAPH 单例 + 处理函数（自 web_ui.py 迁入）
│   ├── api.py                # FastAPI() 实例与 /api/* 路由（Pydantic 请求体）
│   └── views.py              # Air Tags 页面骨架（集中放置，便于 Air alpha 升级时统一适配）
├── static/
│   └── app.js                # 前端交互脚本（自 PAGE 字符串中抽出，逻辑不变）
├── web_ui.py                 # 删除（git 历史可回溯）
├── requirements.txt          # 新增 air>=0.48,<0.49；注释注明 Python>=3.13
└── tests/
    ├── test_new_mechanisms.py            # 保留（处理函数层，须全绿）
    └── test_web_api.py                   # 新增：TestClient 三层断言（见 §9）
```

`main.py`、`core/`、`tools/`、`db/` **零改动**。

## 6. API 契约（与现有端点一一对应，语义不变）

| 方法+路径 | 请求体 | 响应（统一 snapshot JSON） | 对应处理函数 |
| :--- | :--- | :--- | :--- |
| `POST /api/chat` | `{"message": str}` | snapshot | `chat_turn(message)`；挂起中收到消息视为"驳回+修改意见" |
| `POST /api/approve` | 无 | snapshot | `approve()`：`stream(None)` 续跑 |
| `POST /api/reject` | 无 | snapshot | `reject()`：伪造 ToolMessage |
| `POST /api/session` | 无 | snapshot | `new_session()`：换 thread_id |
| `GET /api/state` | – | snapshot | `_snapshot()` |

snapshot 结构：`{"history": [{role, content}], "status": str, "pending": str|null, "prefs": [{key, value}]}`。

Pydantic 模型：

```python
class ChatIn(BaseModel):
    message: str = Field(min_length=1)
```

## 7. 分步实施（每步含验收标准）

### 步骤 1：环境就绪（Python 3.13 + 依赖）
- `uv python install 3.13 && uv venv --python 3.13 && uv pip install -r requirements.txt "air==0.48.*"`
- 验收：`python -c "import air, fastapi; print(air.__version__)"` 输出 0.48.x。

### 步骤 2：Hello 页面跑通（先验证 alpha API 再迁移）
- 最小 `air.Air()` + `air.layouts.mvpcss` 页面，uvicorn 起服；
- 验收：浏览器/curl 拿到 200 且含 "Hello"。若 `layouts.mvpcss` 等 API 与文档不符（alpha 风险），以安装包内源码类型提示为准调整，并回写 skills。

### 步骤 3：后端 API 迁移
- 新建 `web/api.py` 与 `web/app.py`：把 `web_ui.py` 的处理函数与 `GRAPH` 单例迁入；路由按 §6 实现；
- 验收：`TestClient` 下现有四场景（订车审批/偏好/比价/新会话）全部走通（剧本套路见 web-testing-skill）。

### 步骤 4：前端 Air Tags 迁移
- `web/views.py` 用 Air Tags 重写页面骨架（聊天区/状态栏/审批条/侧栏，样式沿用现有 CSS）；交互 JS 抽到 `static/app.js`；
- 验收：`GET /` 200 且含 "Trip Assistant"、审批条容器、偏好面板容器。

### 步骤 5：真实服务冒烟
- 线程起 uvicorn，`urllib` 打 `GET /`、`POST /api/chat`（比价链路）、`GET /api/state`；
- 验收：三个请求全部 200 且断言通过（沿用 tests/test_new_mechanisms.py 的剧本）。

### 步骤 6：收尾
- 删除 `web_ui.py`；`requirements.txt` 更新；项目 README 与 16 节文档的"Web 前端"小节改写（Framework 变更 + 运行方式 `uvicorn web.app:app` 或 `air run`）；全量回归（`pytest tests/` 或直接 python 跑两份测试脚本）。

## 8. 关键技术点

1. **单 worker 纪律**：`MemorySaver`/`InMemoryStore` 进程内存储，多 worker 各存各档——文档与启动命令都写死单 worker；
2. **同步处理函数**：LLM 调用阻塞，FastAPI 自动丢线程池，无需 async 改造；
3. **子图穿透的挂起展示**：`snap.tasks[0].state` 再取 `get_state().next`（已有实现，迁移时原样带走）；
4. **Air alpha 免疫**：所有 Air Tags 集中在 `views.py`，API 变动只改一个文件；
5. **页面与 API 共进程**：用官方 wrap 模式 `air.Air(fastapi_app=api)`；若该模式在 0.48.x 有 bug，降级到 mount 模式（`api.mount("/", air_app)`），skills 里有备选。

## 9. 测试计划

| 层 | 工具 | 用例 |
| :--- | :--- | :--- |
| 处理函数层 | 直接调用（剧本见 skills） | 迁移自现有四场景，必须原样全绿 |
| HTTP 层 | `fastapi.testclient.TestClient` | §6 每个端点：状态码 + snapshot 结构 + 方法不匹配 405 + 页面元素 |
| 真实服务层 | 线程 + uvicorn + urllib | 比价链路一条龙（仅冒烟） |

剧本消耗清单、补丁时机（`llm_cfg.llm = Fake(...)` 先于业务模块 import）等铁律见 [web-testing-skill](../skills/web-testing-skill.md)。

## 10. 风险与回滚

| 风险 | 影响 | 缓解 |
| :--- | :--- | :--- |
| Air alpha API 与文档不符（已实测发生的同名文档站混淆） | 返工 | 步骤 2 先跑 hello；包内类型提示为准；Tags 集中在 views.py |
| 本机无 Python 3.13 | 无法安装 air | uv 管理 3.13（不影响系统 Python）；硬约束无绕行 |
| `air.Air(fastapi_app=...)` wrap 模式 bug | 路由冲突 | 降级 mount 模式；再不行 Air 只渲染页面、API 独立 FastAPI 挂载 |
| MemorySaver 进程内存储 | 重启丢会话 | 与现状一致，属既有取舍（生产换 SqliteSaver，不在本次范围） |

**回滚方案**：改造在独立分支/提交进行，`git checkout main -- web_ui.py requirements.txt && rm -rf web/` 即恢复 stdlib 版；`main.py`/`core/`/`tools/` 零改动保证回滚零风险。

## 11. 文档同步（收尾时一并完成）

- 项目 `README.md`：目录树（web/、static/、删除 web_ui.py）、运行方式、Web 前端小节改写；
- `16_综合实战_旅行助手项目.md`：结构剖析与"如何运行"的 Web 部分改为 FastAPI + Air 表述；
- 根 README 如有涉及（第十章树只列 md 文件，预计无需改）。
