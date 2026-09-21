"""真实服务层冒烟：线程起 uvicorn + urllib 打真实 HTTP 请求（假模型驱动，无需 API Key）。

运行：uv run python tests/smoke_real_server.py   （在 travel_agent_v2 目录内执行）

TestClient 走的是 ASGI 内存直连，不经过真实网络栈；本脚本补上最后一层：
真实 uvicorn 事件循环 + TCP 端口 + urllib 客户端，验证
「页面 / 登录 / 比价链路 / 状态接口」一条龙，Cookie 也走真实 HTTP 头。
"""
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import json
from http.cookiejar import CookieJar

sys.path.insert(0, ".")

# 应用库指到临时目录，冒烟测试不污染开发库（必须在 import web.app 之前）
os.environ["TRIP_DESK_DB_DIR"] = tempfile.mkdtemp(prefix="trip-desk-smoke-")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

import infra.llm as llm_cfg


def tc(name, args, id_):
    return {"name": name, "args": args, "id": id_, "type": "tool_call"}


class Fake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


# 剧本：比价链路 2 条（Send 子图中间零消耗）
llm_cfg.llm = Fake(responses=[
    AIMessage(content="", tool_calls=[tc("ToMultiQuote", {"request": "全部比价"}, "call_1")]),
    AIMessage(content="四类行情已汇总，需要深入了解哪一类？"),
])

import uvicorn  # noqa: E402

from web import auth  # noqa: E402

from web.app import app  # noqa: E402  (必须在打补丁后导入)

PORT = 7861   # 避开默认 7860，防止和手工起的开发服务撞车
BASE = f"http://127.0.0.1:{PORT}"

config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
while not server.started:   # 等真实端口就绪
    time.sleep(0.1)

# 带 CookieJar 的 opener：真实网络栈里跑一遍「登录 → 带令牌请求」
jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path):
    with opener.open(BASE + path) as r:
        return r.status, r.read().decode("utf-8")


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(req) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def status_of(path):
    """只看状态码，把 HTTP 错误也当结果返回。"""
    try:
        with opener.open(BASE + path) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


ok = True

code, html = get("/")
assert code == 200 and "Trip Assistant 旅行管家" in html, "页面冒烟失败"
print(f"✅ GET / -> {code}，页面含标题（真实 uvicorn + TCP）")

assert status_of("/api/state") == 401, "没登录就该被拦下"
print("✅ GET /api/state（未登录）-> 401，认证闸门生效")

code, me = post("/api/auth/login", {"account": "alice", "password": "alice123"})
assert code == 200 and me["identity"]["authed"], "登录失败"
cookie = next((c for c in jar if c.name == auth.COOKIE_NAME), None)
assert cookie is not None, "登录没有下发 Cookie"
assert auth.decode_token(cookie.value) is not None, "下发的不是可验证的 JWT"
print(f"✅ POST /api/auth/login -> {code}，Cookie {auth.COOKIE_NAME} 是一枚可验证的 JWT")

code, data = post("/api/chat", {"message": "帮我看看全部行情"})
assert code == 200 and any("四类行情已汇总" in m["content"] for m in data["history"]), "比价链路失败"
assert not data["pending"], "比价不应挂起"
print(f"✅ POST /api/chat -> {code}，比价汇总已进对话，pending=False")

code, body = get("/api/state")
data = json.loads(body)
assert code == 200 and {"history", "status", "pending", "prefs"} <= set(data), "状态接口失败"
print(f"✅ GET /api/state -> {code}，snapshot 四键齐全")

code, bye = post("/api/auth/logout", {})
assert code == 200 and bye["authed"] is False, "退出登录失败"
assert status_of("/api/state") == 401, "注销后令牌应当失效"
print("✅ POST /api/auth/logout -> 200，退出登录后 /api/state 回到 401")

server.should_exit = True
thread.join(timeout=5)
print("\n✅ 真实服务冒烟通过" if ok else "\n❌ 冒烟失败")
