# Skill：Air 框架前端（本项目 Web UI 重构用）

> 用途：把 `travel_agent_v2` 的 Web 层迁移到 Air 框架。**已于 2026-08-29 按计划执行完毕**（见 docs/refactor-plan-fastapi-air.md），本 skill 保留作为后续升级/复用参考，末尾附实测补记。
> 事实核验日期：2026-08-29（Air 处于 **alpha**，API 可能随版本变动——动手前先重读本页"版本卡"）。

## 0. 版本卡（动手前必读）

| 事实 | 值 | 来源 |
| :--- | :--- | :--- |
| PyPI 包名 | `air`（可选 extras：`air[standard]` = FastAPI 推荐配套） | pypi.org/project/air |
| 当前版本 | 0.48.1（2026-04-03 发布），**alpha 状态** | 同上 |
| Python 要求 | **>=3.13, <3.15**（本机默认 3.12，需先装 3.13，见下） | 同上 |
| 本体依赖 | 构建在 FastAPI、Starlette、Pydantic 之上 | 官方 README |
| 官方文档 | docs.airwebframework.org（有 llms.txt / llms-full.txt） | 官方 README |
| ⚠️ 同名陷阱 | `air.feldroy.com` 是**另一个同名项目**（audreyfeldroy 的静态站生成器），别看错文档站；Web 框架仓库是 `github.com/feldroy/air` | 本次调研实测 |

## 1. 环境准备（本机只有 Python 3.12 时的路径）

推荐用 `uv` 管理 3.13（不需要 brew 装系统 Python）：

```bash
# 安装 uv（若已有跳过）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 在 travel_agent_v2 下建 3.13 环境
uv python install 3.13
uv venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements.txt        # 现有依赖
uv pip install "air==0.48.*"              # alpha 阶段锁小版本
```

`requirements.txt` 届时加：`air>=0.48,<0.49`（等 FastAPI 由 air 依赖带入；若独立安装需 `fastapi` + `uvicorn`）。

## 2. 核心 API（官方 Quickstart 原文核对）

```python
import air

app = air.Air()                    # Air 包装了 FastAPI，@app.get 等装饰器全部通用

@app.get("/")
def index():
    return air.layouts.mvpcss(     # 官方布局：自带排版/样式的整页骨架
        air.H1("Hello, Air!"),
        air.P("Breathe it in."),
    )
```

- **Air Tags**：`air.Html / H1 / P / Div / Ul / Li / ...`——用 Python 类生成 HTML，属性用关键字参数（如 `air.Div("内容", class_="bubble")`）；
- **`@app.page` 装饰器**：函数名即路径（`def index` → `/`），HTML 页面的快捷写法；
- **Jinja 可混用**：`air.JinjaRenderer` 可与 Air Tags 同视图混用；
- **HTMX 友好**：提供配套工具函数（本项目可选）；
- **Pydantic 表单**：HTML 表单校验可直接吃 Pydantic 模型；
- **运行**：开发期 `air run`；或当作 FastAPI 用 `uvicorn app:app`（本项目用后者，与 API 共进程）。

> ⚠️ 以上 API 以 0.48.x 为准。因为 alpha，动手第一步先写一个 hello 页面跑通，再迁移。

## 3. 本项目的迁移方案（两 patterns 取一）

官方给出两种与 FastAPI 共存的方式，**本项目选"单一 Air 应用"**（更简单）：

```python
import air
from fastapi import FastAPI
from pydantic import BaseModel

api = FastAPI()                    # JSON API：chat/approve/reject/state/session

@api.post("/api/chat")
def chat(body: ChatIn) -> dict: ...

app = air.Air(fastapi_app=api)     # wrap 模式：一个应用同时有 API + Air 页面 + OpenAPI 文档

@app.page
def index():
    return air.layouts.mvpcss(...页面骨架...)
```

（备选：`api.mount("/", air_app)` 的 mount 模式——仅当 wrap 模式在 0.48.x 出问题时切换。）

页面骨架迁移策略：现有 `PAGE` 字符串里的**结构用 Air Tags 重写**（标题、聊天区、审批条、侧栏），**交互逻辑保留原生 JS fetch**（Air 是服务端 HTML 框架，JSON 轮询/提交本就该用少量 JS；引入 HTMX 属可选优化，第一版不做）。动态 JS 代码建议存为独立 `static/app.js`，用 `air.Air` 的 static 挂载或 `<script>` 内联。

## 4. 迁移对照表（现有 stdlib 版 → Air 版）

| 现有（web_ui.py） | Air 版 |
| :--- | :--- |
| `PAGE` 大字符串 | `@app.page def index` + Air Tags |
| `ThreadingHTTPServer` + Handler 类 | uvicorn 跑 `air.Air(fastapi_app=api)` |
| `do_GET/do_POST` 手写分发 | `@api.get/@api.post` 装饰器 + Pydantic 请求体 |
| 手写 `Content-Length`/JSON 序列化 | `JSONResponse` 自动处理 |
| 访问日志静默 hack | uvicorn 日志天然干净 |

处理函数（`chat_turn / approve / reject / new_session / _snapshot`）**原样保留**——它们已和 UI 解耦且有测试覆盖。

## 5. 验证清单

1. `uv pip install` 后 `python -c "import air; print(air.__version__)"` 确认 0.48.x；
2. hello 页面先跑通（`air run` 或 uvicorn），再迁移；
3. 迁移后跑 `tests/test_new_mechanisms.py`（处理函数层不受影响，必须全绿）；
4. 新增 TestClient 用例：`GET /` 含页面关键元素、`POST /api/chat` 走通比价链路；
5. 真实浏览器冒烟：审批条出现 → 批准 → 偏好面板更新。

## 6. 风险与回滚

- **alpha API 变动**：锁 `air==0.48.*`；把 Air Tags 集中在一个 `views.py` 里，升级时只动一处；
- **Python 3.13 缺失**：uv 一条命令解决；若坚持系统 3.12，则 Air 不可用——那是硬约束；
- **回滚**：`git checkout -- web_ui.py requirements.txt` 即回到 stdlib 版（改造在独立提交/工作区进行）。

## 7. 实测补记（2026-08-29 改造执行时的真实踩坑记录，0.48.1）

| 实测结论 | 说明 |
| :--- | :--- |
| wrap 模式可用 | `air.Air(fastapi_app=api)` 下页面 + API + `/docs` 同进程正常：405（方法不匹配）与 422（空消息校验）语义都对 |
| `air.Air` 不是 FastAPI 子类 | 它是 Starlette 系应用，`.mount()` 等方法可用，但别按 FastAPI 子类假设类型 |
| ⚠️ `air.Html` 子元素必须**位置参数** | 传 `children=[...]` 关键字会被当成自定义属性原样渲染出去（`<html children="...">`），实测首坑 |
| `air.Style` / `air.Script` 原样输出 | 内容不转义，CSS 花括号与 JS 的 `>` 都安全，可放心内嵌 |
| 属性名映射 | `class_`→`class`、`id_`→`id`、`data_url`→`data-url`、`lang` 等直接透传，`**custom_attributes` 兜底 |
| static/ 自动挂载 | `air.Air` 启动时自动探测 **cwd 下** 的 `static/` 目录挂 `HashedStatic`，页面里的 `<script src>` 会被重写成内容哈希文件名（如 `app.58ac2b2d.js`，原名也仍可访问）——**不要自己再 mount**，且必须从项目根目录启动 uvicorn |
| 无害告警 | `@app.page` 会触发一条 Duplicate Operation ID 的 UserWarning，纯噪音可忽略 |
| 实测版本组合 | Python 3.13.12 + air 0.48.1 + fastapi 0.141.1（由 air 依赖带入）|
