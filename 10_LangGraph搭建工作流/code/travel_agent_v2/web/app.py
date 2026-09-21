"""Trip Assistant Web 层 —— FastAPI 后端 + Air 前端（wrap 模式，单一应用）。

运行：uvicorn web.app:app    （在 travel_agent_v2 目录内执行；需先配置 .env）
浏览器打开 http://127.0.0.1:7860 ；/docs 是 FastAPI 自动生成的 OpenAPI 调试页。

单 worker 纪律：图、Checkpointer 连接与 Store 都在这一个进程里，
多 worker 会各存各的档，启动命令不要加 --workers N。

身份不进全局：谁在用、在哪条会话上，由每个请求自己带一份 Desk（见 web/runtime/identity.py），
所以同一进程能同时服务多个账号。
"""
import air
import uvicorn

from web import auth, runtime
from web.present import views
from web.api import api

HOST, PORT = "127.0.0.1", 7860

runtime.init()

# 兼容旧引用：只留那些不需要身份的符号。处理函数现在都要一份 Desk，
# 想直接调就去 web.runtime（例如 runtime.chat_turn(desk, "…")）。
GRAPH = runtime.GRAPH
PASSENGER_ID = runtime.PASSENGER_ID
Desk = runtime.Desk
resolve_desk = runtime.resolve_desk

app = air.Air(fastapi_app=api)


@app.page
def index():
    """整台工作台的页面骨架（Air Tags 渲染成 HTML）。

    :return: 完整 HTML 文档（登录页 + 六个分页 + 静态脚本引用）
    """
    return views.index()


if __name__ == "__main__":
    if auth.using_dev_secret():
        print("[登录认证] 未配置 TRIP_DESK_SECRET，正在使用开发默认密钥；上线前务必换掉。")
    print(f"Trip Assistant 工作台已启动：http://{HOST}:{PORT}  （Ctrl+C 退出；单 worker，勿加 --workers）")
    uvicorn.run(app, host=HOST, port=PORT)
