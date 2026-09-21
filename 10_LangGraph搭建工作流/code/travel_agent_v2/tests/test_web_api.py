"""Web 层（FastAPI + Air）测试：假模型驱动，无需 API Key。

运行：uv run python tests/test_web_api.py   （在 travel_agent_v2 目录内执行）

三层测试计划：
- 处理函数层四场景回归在 tests/test_new_mechanisms.py（必须全绿，本文件不重复）；
- HTTP 层：TestClient 逐端点断言（状态码 / snapshot 结构 / 405 / 422 / 页面元素）；
- 真实服务层：仅最后冒烟一次，见 tests/smoke_real_server.py。

铁律：llm_cfg.llm = Fake(...) 必须发生在 import web.app 之前——图与处理函数
在 import 期就绑定了模型。
"""
import os
import sys
import tempfile

sys.path.insert(0, ".")

# 应用库（账号 / 会话目录 / 订单 / 审计）指到临时目录：
# 跑测试不会污染 db/app.sqlite，也不会顶掉开发时攒下的会话与订单。
# 必须在 import web.app 之前设置——store 在导入时就解析了路径。
os.environ["TRIP_DESK_DB_DIR"] = tempfile.mkdtemp(prefix="trip-desk-test-")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

import infra.llm as llm_cfg


def tc(name, args, id_):
    return {"name": name, "args": args, "id": id_, "type": "tool_call"}


class Fake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self  # 主助理在 import 时会调用 bind_tools


# 剧本（按调用顺序消费，全文件共享一个队列）：
# 1-5 条：订车场景（真子图 + 子图内 interrupt，敏感工具前挂起）→ 批准恢复
# 6-10 条：订车驳回场景（动态 interrupt 返回拒绝结果，敏感工具不执行）
# 11-12 条：并行比价场景（Send 子图中间零消耗）
# 13-14 条：比价 SSE 场景
#
# 注意：登录/注册（/api/auth/*）与 /api/session 都不消耗模型，只有真正发言才吃剧本。
llm_cfg.llm = Fake(responses=[
    AIMessage(content="", tool_calls=[tc("ToBookCarRental", {
        "location": "成都", "start_date": "2026-10-01", "end_date": "2026-10-03",
        "request": "SUV"}, "call_1")]),
    AIMessage(content="", tool_calls=[tc("search_car_rentals", {"location": "成都"}, "call_2")]),
    AIMessage(content="", tool_calls=[tc("book_car_rental", {"rental_id": 1}, "call_3")]),  # 敏感 -> 拦截
    AIMessage(content="", tool_calls=[tc("CompleteOrEscalate", {"cancel": True, "reason": "任务完成"}, "call_4")]),
    AIMessage(content="您的租车已订好，还有什么可以帮您？"),
    AIMessage(content="", tool_calls=[tc("ToBookCarRental", {
        "location": "成都", "start_date": "2026-10-04", "end_date": "2026-10-06",
        "request": "SUV"}, "call_6")]),
    AIMessage(content="", tool_calls=[tc("search_car_rentals", {"location": "成都"}, "call_7")]),
    AIMessage(content="", tool_calls=[tc("book_car_rental", {"rental_id": 2}, "call_8")]),
    AIMessage(content="已收到拒绝意见，本次租车没有执行。"),
    AIMessage(content="租车操作已取消，还有什么可以帮您？"),
    AIMessage(content="", tool_calls=[tc("ToMultiQuote", {"request": "全部比价"}, "call_11")]),
    AIMessage(content="四类行情已汇总，需要深入了解哪一类？"),
    AIMessage(content="", tool_calls=[tc("ToMultiQuote", {"request": "再比一次"}, "call_13")]),
    AIMessage(content="四类行情已汇总，需要深入了解哪一类？"),
    # 15-18 条：test_new_session 与 test_session_history_is_persistent_and_isolated
    # 各要发言一次（它们排在 test_chat_* 之后消费同一个队列）
    AIMessage(content="", tool_calls=[tc("ToMultiQuote", {"request": "新会话用"}, "call_15")]),
    AIMessage(content="四类行情已汇总，需要深入了解哪一类？"),
    AIMessage(content="", tool_calls=[tc("ToMultiQuote", {"request": "会话持久化用"}, "call_17")]),
    AIMessage(content="四类行情已汇总，需要深入了解哪一类？"),
])

from fastapi.testclient import TestClient  # noqa: E402

from web import auth, captcha  # noqa: E402
from web.app import app  # noqa: E402  (必须在打补丁后导入)

client = TestClient(app)

DEFAULT_USER = "alice"
DEFAULT_PASSWORD = "alice123"
DEFAULT_PAX = "3442 587242"


def _login(username=DEFAULT_USER, password=DEFAULT_PASSWORD, reset=True):
    """登录；（默认）顺手换一个新会话，让用例从干净抽屉开始。"""
    r = client.post("/api/auth/login", json={"account": username, "password": password})
    assert r.status_code == 200, r.text
    if reset:
        client.post("/api/session")
    return r.json()


# ---------- 登录认证 ----------

def test_auth_requires_login():
    """没登录的请求一律 401；页面和文档放行。"""
    fresh = TestClient(app)
    assert fresh.get("/api/state").status_code == 401
    assert fresh.post("/api/chat", json={"message": "你好"}).status_code == 401
    assert fresh.post("/api/session").status_code == 401
    assert fresh.get("/docs").status_code == 200
    assert fresh.get("/").status_code == 200
    me = fresh.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["authed"] is False
    assert me.json()["accounts"], "登录页要靠这份演示账号列表渲染"


def test_auth_rejects_wrong_password():
    """密码错和用户名不存在返回同一个 401，不泄露哪个错了。"""
    fresh = TestClient(app)
    wrong_pass = fresh.post("/api/auth/login", json={"account": DEFAULT_USER, "password": "nope"})
    assert wrong_pass.status_code == 401
    assert "账号或密码" in wrong_pass.json()["detail"]

    no_user = fresh.post("/api/auth/login", json={"account": "ghost", "password": "whatever"})
    assert no_user.status_code == 401
    assert no_user.json()["detail"] == wrong_pass.json()["detail"]

    assert fresh.get("/api/state").status_code == 401


def test_auth_password_is_hashed_not_stored_plain():
    """账号存在应用库（db/app.sqlite），库里只有盐和哈希，明文不落库。"""
    import sqlite3

    conn = sqlite3.connect(auth.store.APP_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (DEFAULT_USER,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "演示账号应当已经建好"
    assert row["password_hash"] != DEFAULT_PASSWORD
    assert len(row["password_hash"]) == 64, "PBKDF2-SHA256 输出 32 字节十六进制"
    assert row["salt"]
    assert auth.verify_password(DEFAULT_PASSWORD, row["salt"], row["password_hash"])
    assert not auth.verify_password("nope", row["salt"], row["password_hash"])


def test_auth_cookie_is_signed_jwt():
    """Cookie 是一枚 HS256 JWT：三段式、签名可验、声明齐全。"""
    fresh = TestClient(app)
    r = fresh.post("/api/auth/login", json={"account": DEFAULT_USER, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200

    token = fresh.cookies.get(auth.COOKIE_NAME)
    assert token and token.count(".") == 2, "应当是三段式 JWT"

    header = auth.jwt.get_unverified_header(token)
    assert header["alg"] == "HS256"

    claims = auth.decode_token(token)
    assert claims["sub"] == DEFAULT_USER
    assert claims["passenger_id"] == DEFAULT_PAX
    assert claims["iss"] == auth.ISSUER
    assert claims["exp"] - claims["iat"] == auth.TOKEN_TTL
    assert claims["jti"]

    # 改一个字节，签名立刻失效
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert auth.decode_token(tampered) is None


def test_auth_register_then_login():
    """注册这一个门现在是图形验证码（邮箱验证码暂时下线，见 web/api.py 与 views.py 的注释）。
    顺带覆盖：验证码错/缺会被拦、弱密码 / 档案不存在 / 用户名重复 / 邮箱重复都拦得住，
    以及「便宜的错误不烧验证码」这条顺序纪律。"""
    fresh = TestClient(app)
    name = "dave_test"
    mail = "dave@example.com"

    def puzzle(client=None):
        """出一张新题，顺手把答案拿出来（captcha.peek 只给测试用）。"""
        c = client or fresh
        cap = c.get("/api/auth/captcha").json()
        return {"captcha_id": cap["captcha_id"], "captcha_text": captcha.peek(cap["captcha_id"])}

    def register(**over):
        body = {"username": name, "password": "dave12345", "passenger_id": DEFAULT_PAX, "email": mail}
        body.update(over)
        return fresh.post("/api/auth/register", json=body)

    # 不填图形验证码 -> 拦下
    missing = register()
    assert missing.status_code == 400
    assert "图形验证码" in missing.json()["detail"]

    # 填错 -> 拦下，而且这次作废（一题一用）
    wrong_cap = puzzle()
    wrong = register(captcha_id=wrong_cap["captcha_id"], captcha_text="XXXX")
    assert wrong.status_code == 400
    assert "图形验证码" in wrong.json()["detail"]

    # 弱密码 / 档案不存在：都该在「消费验证码」之前被拦掉，所以同一道题还能接着用
    keep = puzzle()
    weak = register(password="123", **keep)
    assert weak.status_code == 400
    assert "密码" in weak.json()["detail"]
    bad_pid = register(passenger_id="9999 999999", **keep)
    assert bad_pid.status_code == 400

    # 这一道题没被上面几次失败烧掉，这次应当成功
    ok = register(**keep)
    assert ok.status_code == 200, ok.text
    assert ok.json()["identity"]["authed"] is True
    claims = auth.decode_token(fresh.cookies.get(auth.COOKIE_NAME))
    assert claims["sub"] == name and claims["email"] == mail

    assert fresh.get("/api/state").status_code == 200
    fresh.post("/api/auth/logout")
    assert fresh.get("/api/state").status_code == 401

    # 注册过的账号能用用户名也能用邮箱登录
    assert fresh.post("/api/auth/login", json={"account": name, "password": "dave12345"}).status_code == 200
    fresh.post("/api/auth/logout")
    assert fresh.post("/api/auth/login", json={"account": mail, "password": "dave12345"}).status_code == 200

    # 用户名与邮箱都不能重复（这两条也在消费验证码之前判）
    dup_user = TestClient(app).post(
        "/api/auth/register",
        json={"username": name, "password": "dave12345", "passenger_id": DEFAULT_PAX,
              "email": "other@example.com"},
    )
    assert dup_user.status_code == 400
    assert "用户名已经注册过" in dup_user.json()["detail"]

    dup_mail = TestClient(app).post(
        "/api/auth/register",
        json={"username": "dave_other", "password": "dave12345", "passenger_id": DEFAULT_PAX,
              "email": mail},
    )
    assert dup_mail.status_code == 400
    assert "邮箱已经注册过" in dup_mail.json()["detail"]


def test_auth_login_needs_captcha_after_failures():
    """密码连错 3 次之后要过图形验证码；登录成功把计数清零。"""
    fresh = TestClient(app)
    for _ in range(3):
        r = fresh.post("/api/auth/login", json={"account": DEFAULT_USER, "password": "wrong"})
        assert r.status_code == 401

    blocked = fresh.post(
        "/api/auth/login", json={"account": DEFAULT_USER, "password": DEFAULT_PASSWORD}
    )
    assert blocked.status_code == 400
    assert "图形验证码" in blocked.json()["detail"]

    cap = fresh.get("/api/auth/captcha").json()
    ok = fresh.post(
        "/api/auth/login",
        json={"account": DEFAULT_USER, "password": DEFAULT_PASSWORD,
              "captcha_id": cap["captcha_id"], "captcha_text": captcha.peek(cap["captcha_id"])},
    )
    assert ok.status_code == 200
    assert ok.json()["identity"]["username"] == DEFAULT_USER

    fresh.post("/api/auth/logout")
    clean = fresh.post(
        "/api/auth/login", json={"account": DEFAULT_USER, "password": DEFAULT_PASSWORD}
    )
    assert clean.status_code == 200, "登录成功后应当不再要图形验证码"


def test_auth_captcha_is_single_use():
    """图形验证码一题只能用一次，且答案不在下发内容里。

    借注册接口来验：注册现在是这道码唯一的消费者（邮箱验证码暂时下线）。
    """
    fresh = TestClient(app)
    cap = fresh.get("/api/auth/captcha").json()
    assert "<svg" in cap["svg"]
    answer = captcha.peek(cap["captcha_id"])
    assert answer not in cap["svg"], "答案不能出现在 SVG 里"

    body = {"password": "captcha123", "passenger_id": DEFAULT_PAX}
    first = fresh.post(
        "/api/auth/register",
        json={"username": "cap_one", "email": "cap1@example.com",
              "captcha_id": cap["captcha_id"], "captcha_text": answer, **body},
    )
    assert first.status_code == 200, first.text
    second = fresh.post(
        "/api/auth/register",
        json={"username": "cap_two", "email": "cap2@example.com",
              "captcha_id": cap["captcha_id"], "captcha_text": answer, **body},
    )
    assert second.status_code == 400, "同一道题不能用第二次"
    assert "图形验证码" in second.json()["detail"]


def test_model_window_keeps_recent_turns():
    """送进模型的上下文有上限，且永远从一条人类发言开始、不会为空。"""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from agent.context import MODEL_WINDOW, window

    msgs = []
    for i in range(40):
        msgs.append(HumanMessage(f"问题 {i}"))
        msgs.append(AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": f"c{i}", "type": "tool_call"}]))
        msgs.append(ToolMessage("回执", tool_call_id=f"c{i}"))

    out = window(msgs)
    assert 0 < len(out) <= MODEL_WINDOW, "窗口要有上限，但不能为空"
    assert out[0].type == "human", "切片必须从人类发言开始，工具调用与回执才不会被拆散"
    assert out[-1] is msgs[-1], "最新一条必须在窗口里"

    assert window(msgs[:3]) == msgs[:3], "没超上限就原样给"
    assert window([]) == []

    # 长尾全是工具消息（一连串工具循环）时也不能返回空——空上下文等于模型失忆
    tool_tail = [HumanMessage("开头")] + [AIMessage("x"), ToolMessage("t", tool_call_id="z")] * 30
    tail_window = window(tool_tail)
    assert tail_window, "工具长尾也要给出非空窗口"


def test_long_term_memory_is_persistent_and_injected():
    """长期记忆两件事：落盘（换个连接还在）+ 开局自动读进 user_info（不靠模型自觉）。"""
    import sqlite3

    from langgraph.store.sqlite import SqliteStore

    from memory.store import PREFERENCES_DB, store
    from main import _profile_text

    # 1) 落盘：同一个文件另开一个连接，写进去的还在
    store.put(("pref_test-pax",), "room", {"value": "无烟房"})
    other = SqliteStore(sqlite3.connect(PREFERENCES_DB, check_same_thread=False))
    assert other.get(("pref_test-pax",), "room").value == {"value": "无烟房"}

    # 2) 自动进上下文：档案一下就拼好了（模型不必先想起来调工具）
    text = _profile_text({"configurable": {"passenger_id": "3442 587242"}}, store)
    assert "seat_preference" in text and "靠窗" in text
    assert _profile_text({"configurable": {}}, store) == "", "没有身份就什么都别给"


def test_auth_isolates_accounts():
    """换个账号，航段、档案、对话抽屉都跟着换；换回来抽屉还在。"""
    fresh = TestClient(app)

    fresh.post("/api/auth/login", json={"account": DEFAULT_USER, "password": DEFAULT_PASSWORD})
    a = fresh.get("/api/state").json()
    assert a["passenger_id"] == DEFAULT_PAX
    assert [leg["from"] for leg in a["itinerary"]["legs"]] == ["PEK", "CTU"]
    assert any(p["key"] == "seat_preference" for p in a["prefs"]), "alice 应有预置档案"
    thread_a = a["thread_id"]

    fresh.post("/api/auth/login", json={"account": "bob", "password": "bob123"})
    b = fresh.get("/api/state").json()
    assert b["passenger_id"] == "0000 000343"
    assert [leg["from"] for leg in b["itinerary"]["legs"]] == ["SHA", "SYX"], "行程应换成另一条航线"
    assert b["prefs"] == [], "另一个账号不该看到别人的档案"
    assert b["history"] == [], "另一个账号的对话抽屉是空的"
    assert b["thread_id"] != thread_a

    fresh.post("/api/auth/login", json={"account": DEFAULT_USER, "password": DEFAULT_PASSWORD})
    back = fresh.get("/api/state").json()
    assert back["thread_id"] == thread_a, "回到原账号，对话抽屉应当还是原来那一个"


def test_auth_logout_revokes_token():
    """退出登录要吊销 jti：JWT 无状态，服务端得自己记账。"""
    fresh = TestClient(app)
    fresh.post("/api/auth/login", json={"account": DEFAULT_USER, "password": DEFAULT_PASSWORD})
    token = fresh.cookies.get(auth.COOKIE_NAME)
    claims = auth.decode_token(token)
    assert claims is not None

    r = fresh.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json()["authed"] is False

    # 令牌本身签名仍然有效，但 jti 已进吊销名单
    assert auth.is_revoked(claims["jti"])
    assert auth.decode_token(token) is None
    assert fresh.get("/api/state").status_code == 401


# ---------- 页面与静态资源 ----------

def test_page_renders():
    """GET /：Air Tags 页面骨架含登录页、左侧导航、六个分页、看板与前端脚本"""
    r = client.get("/")
    assert r.status_code == 200
    assert "Trip Assistant 旅行管家" in r.text
    assert 'id="login"' in r.text             # 登录页
    assert 'id="login-user"' in r.text        # 用户名输入
    assert 'id="login-pass"' in r.text        # 密码输入
    assert 'id="form-register"' in r.text     # 注册表单
    assert 'id="reg-pax"' in r.text           # 注册时绑定旅客档案
    assert 'id="login-demos"' in r.text       # 演示账号
    assert 'id="login-captcha"' in r.text     # 登录图形验证码
    assert 'id="reg-captcha"' in r.text       # 注册图形验证码
    assert 'id="reg-email"' in r.text         # 注册邮箱
    # 邮箱验证码暂时下线（2026-09-20）：这几个容器随表单一起注释掉了，恢复时再断言回来
    # assert 'id="reg-code"' in r.text          # 邮箱验证码输入
    # assert 'id="send-code"' in r.text         # 发送验证码按钮
    # assert 'id="code-note"' in r.text         # 验证码提示行
    assert 'id="reg-captcha-img"' in r.text   # 图形验证码题板（现在点它就能换一张）
    # 登录说明必须和表单一致：只承诺图形验证码，不能再写「和邮箱验证码」
    assert "图形验证码" in r.text
    assert "和 <em>邮箱验证码</em>" not in r.text
    assert 'id="signout-btn"' in r.text       # 退出登录按钮
    assert 'id="pax-chip"' in r.text          # 当前旅客档案
    assert 'id="thread-chip"' in r.text       # 当前会话
    assert 'id="model-chip"' in r.text        # 模型名
    assert 'id="mode-chip"' in r.text         # 真实模型 / 未配 Key
    assert 'id="page-title"' in r.text and 'id="page-sub"' in r.text
    assert 'id="approval"' in r.text          # 审批条容器
    assert 'id="approval-detail"' in r.text   # interrupt() 结构化数据包展示区
    assert 'id="sessions"' in r.text          # 会话历史
    assert 'id="chat"' in r.text              # 对话区
    assert 'id="graph"' in r.text             # 节点流程条
    assert 'id="map"' in r.text               # 行程页：真实底图
    assert 'id="legs"' in r.text              # 航段列表
    assert 'id="kpis"' in r.text              # 行程概览计数
    assert 'id="city-chips"' in r.text        # 有库存的城市
    assert 'id="explore-cities"' in r.text    # 探索：城市卡
    assert 'id="explore"' in r.text           # 探索：选中城市的库存
    assert 'id="cards"' in r.text             # 工具回执长出来的卡片容器
    assert 'id="orders"' in r.text            # 订单
    assert 'id="audit"' in r.text             # 审计流水
    assert 'id="stack"' in r.text             # 对话状态栈
    assert 'id="prefs"' in r.text             # 跨会话档案
    assert 'id="trace"' in r.text             # 节点时间线
    # 看板：出港牌（时钟 + 信号灯计数 + 类型筛选 + 行表）
    assert 'id="board"' in r.text
    assert 'id="board-clock"' in r.text and 'id="board-date"' in r.text
    assert 'id="board-count"' in r.text
    for lamp in ("total", "booked", "open", "hold", "flights"):
        assert f'id="lamp-{lamp}"' in r.text, lamp
    for seg in ("all", "car", "hotel", "spot", "open"):
        assert f'id="seg-{seg}"' in r.text, seg
    # 左侧导航按页切：每一页一个容器、一个导航项
    for key in ("chat", "trip", "explore", "board", "orders", "ops"):
        assert f'id="nav-{key}"' in r.text, key
        assert f'id="page-{key}"' in r.text, key
    assert "去程 / 回程各一条" in r.text      # 航段那一块的说明
    assert "经纬度按公开边界线性投影" in r.text  # 地图那一块的说明
    assert 'class="nav-item' in r.text
    assert "gate-card" in r.text               # 登录是一张卡片
    # air 内置 HashedStatic 会把脚本引用改写成带内容哈希的文件名（如 app.58ac2b2d.js）
    assert '<script src="/static/app.' in r.text


def test_static_js_served():
    """air 自动挂载的 static 生效：app.js 原始路径可访问"""
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "render" in r.text
    assert "去程" in r.text
    assert "/api/auth/login" in r.text        # 前端走登录接口
    assert "/api/auth/register" in r.text     # 注册接口
    assert "arcPath" not in r.text


# ---------- 快照结构 ----------

def test_state_snapshot_structure():
    """GET /api/state：snapshot 四个键齐全且类型正确"""
    _login()
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert {"history", "status", "pending", "prefs"} <= set(data)
    assert isinstance(data["history"], list)
    assert isinstance(data["prefs"], list)
    assert data["pending"] is None            # 刚换会话，空闲
    assert "thread_id" in data and "trace" in data
    assert "itinerary" in data and "board" in data
    assert "history_truncated" in data, "快照要带「历史是否被截断」这个标记"
    assert "identity" in data and data["identity"]["authed"] is True
    assert isinstance(data["cards"], list)          # 生成式卡片（本轮没查就没有）
    assert isinstance(data["explore"], list) and data["explore"], "探索面板要有城市列表"
    assert data["explore"][0]["art"], "城市要带几何标记"
    assert data["route"], "行程要有坐标地图"
    assert 'class="cap"' in data["route"], "地图要有省会城市的底点层"
    assert isinstance(data["itinerary"].get("legs"), list)
    assert data["itinerary"]["legs"], "旅客北京↔成都航段应出现在行程快照里"
    assert data["board"]["cars"]["total"] >= 1
    assert {"booked", "open", "items"} <= set(data["board"]["cars"])


# ---------- 对话与审批 ----------

def test_chat_car_rental_approval_flow():
    """POST /api/chat 订车 -> 敏感工具挂起 -> POST /api/approve 恢复"""
    _login()
    r = client.post("/api/chat", json={"message": "帮我在成都订一辆SUV"})
    assert r.status_code == 200
    data = r.json()
    assert data["pending"]                    # 子图内 book_car_rental 前被 interrupt 拦下
    assert data["pending"]["payload"]["kind"] == "tool_approval"
    assert data["pending"]["payload"]["tool_calls"][0]["name"] == "book_car_rental"
    assert "已挂起" in data["status"]

    r = client.post("/api/approve")           # 批准：从存档续跑
    assert r.status_code == 200
    data = r.json()
    assert data["pending"] is None
    assert any("已订好" in m["content"] for m in data["history"] if m["role"] == "assistant")


def test_chat_car_rental_rejection_flow():
    """动态审批驳回：Command(resume=False) 补齐 ToolMessage，敏感工具不执行。"""
    _login()
    r = client.post("/api/chat", json={"message": "帮我再订一辆SUV"})
    assert r.status_code == 200 and r.json()["pending"]

    r = client.post("/api/reject")
    assert r.status_code == 200
    data = r.json()
    assert data["pending"] is None
    assert any("用户点击了驳回" in m["content"] for m in data["history"] if m["role"] == "tool")
    assert any("没有执行" in m["content"] or "已取消" in m["content"]
               for m in data["history"] if m["role"] == "assistant")


def test_chat_quote_flow():
    """POST /api/chat 并行比价：无敏感操作，不挂起，四路汇总进对话"""
    _login()
    r = client.post("/api/chat", json={"message": "帮我看看全部行情"})
    assert r.status_code == 200
    data = r.json()
    assert not data["pending"]
    assert any("四类行情已汇总" in m["content"] for m in data["history"])


def test_chat_stream_quote_flow():
    """节点级 SSE：比价链路推 snapshot，不挂起。"""
    _login()
    r = client.post("/api/chat/stream", json={"message": "再帮我看看全部行情"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    assert "四类行情已汇总" in r.text
    assert '"type": "snapshot"' in r.text or '"type":"snapshot"' in r.text


# ---------- 会话与校验 ----------

def test_new_session():
    """POST /api/session：换 thread_id，历史清零，snapshot 结构不变"""
    _login()
    client.post("/api/chat", json={"message": "帮我在成都订一辆SUV"})

    r = client.post("/api/session")
    assert r.status_code == 200
    data = r.json()
    assert {"history", "status", "pending", "prefs"} <= set(data)
    assert data["history"] == []              # Checkpointer 会话记忆随 thread_id 清零
    assert data["pending"] is None
    assert data["prefs"], "换会话不该动 Store 档案"


def test_chat_validation():
    """空消息被 Pydantic 拦下：422 + 明确错误字段"""
    _login()
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][-1] == "message"


def test_method_mismatch():
    """方法不匹配：FastAPI 明确 405（stdlib 版是含糊的 404）"""
    assert client.post("/api/state").status_code == 405
    assert client.get("/api/chat").status_code == 405
    assert client.get("/api/auth/login").status_code == 405


def test_docs_available():
    """wrap 模式白送的 OpenAPI 文档页"""
    assert client.get("/docs").status_code == 200



# ---------- 会话历史与持久化 ----------

def test_two_accounts_do_not_cross_contaminate():
    """两个客户端交替请求，各自看到自己的档案、航段、会话与偏好。

    这是「身份不进全局」那条约定的回归：以前当前是谁、当前在哪条会话上存在一个
    进程级 SESSION 字典里，A 的请求会把 passenger_id / thread_id 写成 B 的，
    A 的下一句就落进 B 的档案。现在身份随请求走（见 web/runtime/identity.py 的 Desk）。
    """
    alice = TestClient(app)
    bob = TestClient(app)
    alice.post("/api/auth/login", json={"account": "alice", "password": "alice123"})
    bob.post("/api/auth/login", json={"account": "bob", "password": "bob123"})

    a1 = alice.get("/api/state").json()
    b1 = bob.get("/api/state").json()
    a2 = alice.get("/api/state").json()
    b2 = bob.get("/api/state").json()

    assert a1["passenger_id"] == a2["passenger_id"] == DEFAULT_PAX
    assert b1["passenger_id"] == b2["passenger_id"] == "0000 000343"
    assert [leg["from"] for leg in a1["itinerary"]["legs"]] == ["PEK", "CTU"]
    assert [leg["from"] for leg in b1["itinerary"]["legs"]] == ["SHA", "SYX"]
    assert a1["thread_id"] == a2["thread_id"], "对方的请求不该把我的当前会话换掉"
    assert b1["thread_id"] == b2["thread_id"]
    assert a1["thread_id"] != b1["thread_id"]
    assert any(p["key"] == "seat_preference" for p in a1["prefs"])
    assert b1["prefs"] == []


def test_thread_hint_keeps_two_tabs_apart():
    """带上 X-Thread-Id 时，服务端按那条会话办事——同一账号两个标签页各聊各的。"""
    alice = TestClient(app)
    alice.post("/api/auth/login", json={"account": "alice", "password": "alice123"})
    first = alice.get("/api/state").json()["thread_id"]
    # 改个名：空草稿会在新建下一条时被清理，改名之后它就算「有主」，留得住
    alice.patch(f"/api/sessions/{first}", json={"title": "第一条"})
    second = alice.post("/api/sessions").json()["thread_id"]

    back_to_first = alice.get("/api/state", headers={"X-Thread-Id": first}).json()
    assert back_to_first["thread_id"] == first, "带了 thread 提示就按提示那条来"

    stray = alice.get("/api/state", headers={"X-Thread-Id": "not-a-real-thread"}).json()
    assert stray["thread_id"] != "not-a-real-thread", "提示不合法就退回自己的最近一条"
    assert stray["thread_id"] in {first, second}


def test_sessions_listed_renamed_opened_deleted():
    """会话目录：新建 / 列表 / 改名 / 切换 / 删除，且不能动别人的。

    新规矩：点「新对话」永远给一条新的空对话（可预期），但列表里**最多留一条空草稿**——
    上一条没聊过、也没改过名的会被顺手清掉；聊过一句或改过名的都算有主，留着。
    """
    _login()
    first = client.get("/api/state").json()["thread_id"]

    snap = client.post("/api/sessions").json()
    second = snap["thread_id"]
    assert second != first, "点新对话就给新的 thread_id"
    drafts = [s["thread_id"] for s in snap["sessions"] if s["title"] == "新对话"]
    assert drafts == [second], "空草稿只该剩当前这条（上一条被清掉）"

    # 改过名的空对话算「有主」，再新建时不动它
    r = client.patch(f"/api/sessions/{second}", json={"title": "成都三日游"})
    assert r.status_code == 200
    snap = client.post("/api/sessions").json()
    third = snap["thread_id"]
    titles = {item["thread_id"]: item["title"] for item in snap["sessions"]}
    assert titles.get(second) == "成都三日游", "改过名的会话要留着"
    assert titles.get(third) == "新对话"
    assert len([s for s in snap["sessions"] if s["title"] == "新对话"]) == 1

    # 切换 / 正在用的删不掉（要删先切走）/ 别人的打不开
    assert client.post(f"/api/sessions/{second}/open").json()["thread_id"] == second
    assert client.delete(f"/api/sessions/{second}").status_code == 400, "正在用的对话不能删"

    other = TestClient(app)
    other.post("/api/auth/login", json={"account": "bob", "password": "bob123"})
    assert other.post(f"/api/sessions/{second}/open").status_code == 404, "别人的对话打不开"
    assert other.get("/api/state").json()["thread_id"] != second

    assert client.post(f"/api/sessions/{third}/open").json()["thread_id"] == third
    r = client.delete(f"/api/sessions/{second}")
    assert r.status_code == 200
    assert all(item["thread_id"] != second for item in r.json()["sessions"])


def test_empty_session_drafts_do_not_pile_up():
    """连点「新对话」不会在列表里堆出一排「新对话 0 轮」。"""
    _login()
    for _ in range(3):
        snap = client.post("/api/sessions").json()
    drafts = [s for s in snap["sessions"] if s["title"] == "新对话"]
    assert len(drafts) == 1, "空草稿最多留一条"
    assert drafts[0]["thread_id"] == snap["thread_id"], "留下的应当是当前这条"


def test_session_history_is_persistent_and_isolated():
    """对话存档落在磁盘上：换会话清零，切回来历史还在。"""
    _login()
    snap = client.post("/api/chat", json={"message": "帮我看看全部行情"}).json()
    first = snap["thread_id"]
    assert snap["history"], "刚说过话，当前会话应当有历史"

    fresh = client.post("/api/sessions").json()
    assert fresh["history"] == [], "新对话应当是空的"

    back = client.post(f"/api/sessions/{first}/open").json()
    assert back["thread_id"] == first
    assert back["history"], "切回旧对话，历史应当还在（存档在磁盘上）"
    assert any("四类行情已汇总" in m["content"] for m in back["history"])


# ---------- 订单中心 ----------

def test_orders_recorded_from_booking():
    """前面那条订车链路会在订单中心留下订单：金额按库存单价算，机票自动推导。"""
    _login()
    data = client.get("/api/orders").json()

    flights = [o for o in data["items"] if o["kind"] == "flight"]
    assert len(flights) >= 2, "旅客的两个航段应当各有一条机票订单"
    assert all(o["amount"] > 0 for o in flights)

    cars = [o for o in data["items"] if o["kind"] == "car"]
    assert cars, "订车链路应当在订单中心留下记录"
    confirmed = [o for o in cars if o["status"] == "confirmed"]
    assert confirmed, "批准过的租车应当是已确认"
    assert all(o["amount"] > 0 for o in confirmed), "租车金额应当按每天单价 × 天数算出来"
    assert data["counts"]["amount"] > 0
    assert data["owner_view"] is False

    # 下单和批准都应该在审计里留痕（这个用例跑在订车链路之后）
    snap = client.get("/api/state").json()
    actions = snap["audit"]["summary"]["by_action"]
    assert actions.get("approve"), "批准动作应当进审计"
    assert actions.get("book"), "下单动作应当进审计"
    assert snap["audit"]["owner_view"] is False


def test_orders_cancel_releases_inventory():
    """订单中心取消一单：订单变已取消，库存的 booked 标记同步放开。"""
    _login()
    data = client.get("/api/orders").json()
    target = next(
        (o for o in data["items"] if o["kind"] == "car" and o["status"] == "confirmed"),
        None,
    )
    assert target, "需要一条已确认的租车订单来做取消"

    r = client.post("/api/orders/cancel", json={"order_id": target["id"]})
    assert r.status_code == 200, r.text
    snap = r.json()
    after = [o for o in snap["orders"]["items"] if o["id"] == target["id"]][0]
    assert after["status"] == "cancelled"

    # 库存看板上对应的车应当变回空位
    board = {item["id"]: item for item in snap["board"]["cars"]["items"]}
    assert board[int(target["ref"])]["booked"] is False

    # 重复取消不报错（幂等）
    again = client.post("/api/orders/cancel", json={"order_id": target["id"]})
    assert again.status_code == 200


# ---------- 探索接口 ----------

def test_explore_browse_by_city():
    """探索：不靠对话直接翻库存。城市列表带计数，按城市能取到三类卡片。"""
    _login()
    listing = client.get("/api/explore").json()
    cities = {item["city"]: item for item in listing["cities"]}
    assert "Chengdu" in cities
    assert cities["Chengdu"]["spots"] >= 1
    assert cities["Chengdu"]["cn"] == "成都"

    data = client.get("/api/explore?city=成都").json()          # 中文也能查
    assert data["city"] == "Chengdu"
    assert data["spots"] and data["hotels"] and data["cars"]
    spot = data["spots"][0]
    assert spot["title"] and spot["price"]
    assert data["art"], "城市要带一枚几何标记"

    empty = client.get("/api/explore?city=火星").json()
    assert empty["city"] == "" and empty["spots"] == []


# ---------- 角色与审计 ----------

def test_audit_records_actions_and_is_ops_only():
    """审计：普通账号只看自己的；运营账号能看全量，且能看全部订单。"""
    _login()
    snap = client.get("/api/state").json()
    assert snap["identity"]["role"] == "passenger"
    assert snap["audit"]["owner_view"] is False
    assert snap["audit"]["items"], "普通账号也该看到自己的流水"
    assert {i["actor"] for i in snap["audit"]["items"]} == {DEFAULT_USER}

    assert client.get("/api/audit").status_code == 403, "审计接口只对运营开放"

    carol = TestClient(app)
    r = carol.post("/api/auth/login", json={"account": "carol", "password": "carol123"})
    assert r.status_code == 200
    carol_snap = r.json()
    assert carol_snap["identity"]["passenger_id"] == "0001 998571"
    assert [leg["from"] for leg in carol_snap["itinerary"]["legs"]] == ["CAN", "XIY"]

    ops = TestClient(app)
    r = ops.post("/api/auth/login", json={"account": "ops", "password": "ops12345"})
    assert r.status_code == 200
    data = r.json()
    assert data["identity"]["role"] == "ops"
    assert data["identity"]["passenger_id"] == "0002 445566", "运营账号必须有自己的档案，不能和 carol 合住"
    assert [leg["from"] for leg in data["itinerary"]["legs"]] == ["HGH", "TAO"]
    assert data["orders"]["owner_view"] is True

    r = ops.get("/api/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total"] > 0
    actions = {item["action"] for item in body["items"]}
    assert "login" in actions, "登录应当留下流水"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✅ {name}")
            except AssertionError as e:
                failed += 1
                print(f"❌ {name}: {e}")
    print(f"\n{'全部通过' if not failed else f'{failed} 个用例失败'}")
    sys.exit(1 if failed else 0)
