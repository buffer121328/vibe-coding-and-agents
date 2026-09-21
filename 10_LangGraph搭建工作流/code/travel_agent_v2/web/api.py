"""Trip Assistant JSON API —— FastAPI 实例与 /api/* 路由。

契约：
- POST /api/auth/login     账号密码登录
- POST /api/auth/register  注册（过图形验证码 + 绑定一份旅客档案）
- POST /api/auth/logout    退出登录，清 Cookie 并吊销令牌
- GET  /api/auth/me        当前登录状态（未登录也返回 200）
- GET  /api/auth/captcha   出一道图形验证码（前端点题板换一张）
- POST /api/auth/email/code 发邮箱验证码 —— **暂时下线**（演示环境没有邮件服务），
                            端点保留但直接回 503，恢复步骤见函数里的注释
- POST /api/chat           用户发言（挂起中视为“驳回 + 修改意见”）
- POST /api/approve        批准：从 interrupt() 续跑
- POST /api/reject         驳回：补齐 ToolMessage，让助理重规划
- POST /api/session        换 thread_id（对话清零，Store 档案保留）
- GET  /api/state          当前快照
- POST /api/chat/stream|approve/stream|reject/stream  节点级 SSE

处理函数在 web.runtime。这里延迟导入，避免与 app.py wrap 装配成环。
"""
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from web.auth import (
    AuthGate,
    captcha_required,
    clear_cookie,
    create_user,
    authenticate,
    current_session,
    find_user,
    issue_cookie,
    known_passengers,
    public_identity,
    require_session,
    validate_new_user,
)
# verify 现在只被「邮箱验证码暂时下线」那段注释引用（mailer 同理：只剩 _unauth_payload 里的
# smtp_configured / _dev_mode 两处），恢复功能时这两个 import 正好还要用，所以留着
from web import audit, captcha, mailer, orders, verify
from web.present import art, explore

api = FastAPI(
    title="Trip Assistant API",
    description="LangGraph 旅行助手工作台接口 —— 访问 /docs 可在线调试全部端点",
)
api.add_middleware(AuthGate)


@api.middleware("http")
async def html_no_store(request: Request, call_next):
    """页面骨架不缓存。

    app.js / CSS 由 Air 的 HashedStatic 带内容哈希，改了就换文件名；只有 HTML
    没这个待遇——浏览器会自作主张缓存，于是「代码改了、服务也重启了，页面还是旧的」。
    这里给 HTML 明确标不缓存，省得每次都要拿隐身窗口验证。
    """
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-store"
    return response


class ChatIn(BaseModel):
    """用户发言的请求体。

    :param message: 一句话，不能为空（空消息在 Pydantic 层就被 422 拦掉）
    """
    message: str = Field(min_length=1, description="用户发言")


class LoginIn(BaseModel):
    """登录请求体。

    :param account: 用户名或邮箱，两种都收
    :param password: 明文口令（只在传输层出现一次）
    :param captcha_id: 图形验证码题号（连错 3 次才需要）
    :param captcha_text: 图形验证码答案
    """
    account: str = Field(min_length=1, description="用户名或邮箱")
    password: str = Field(min_length=1, description="密码")
    captcha_id: str = Field(default="", description="图形验证码的题号（错太多次才需要）")
    captcha_text: str = Field(default="", description="图形验证码的答案")


class RegisterIn(BaseModel):
    """非空即可；格式类校验交给 create_user，
    这样注册表单拿到的是一条能直接显示给人看的中文提示，而不是 Pydantic 的字段报错。

    **邮箱验证码暂时下线**（2026-09-20，演示环境没有邮件服务）：
    现在注册这一道是图形验证码，所以 captcha_id / captcha_text 是必填的语义，
    邮箱仍然收下（账号要用它登录、找回），只是不再校验验证码。
    """

    username: str = Field(min_length=1, description="用户名：小写字母/数字/下划线，3–24 位")
    password: str = Field(min_length=1, description="密码，至少 6 位")
    passenger_id: str = Field(min_length=1, description="要绑定的旅客档案号")
    email: str = Field(min_length=1, description="邮箱（账号用它登录）")
    captcha_id: str = Field(default="", description="图形验证码题号")
    captcha_text: str = Field(default="", description="图形验证码答案")
    # code: str = Field(min_length=1, description="邮箱收到的 6 位验证码（暂时下线，见类注释）")


class EmailCodeIn(BaseModel):
    """邮箱验证码下单用：暂时下线，恢复时随端点一起放回来。"""

    email: str = Field(min_length=3, description="收验证码的邮箱")
    purpose: str = Field(default="register", description="register | login | reset")
    captcha_id: str = Field(default="", description="图形验证码题号")
    captcha_text: str = Field(default="", description="图形验证码答案")


def _runtime():
    """延迟取到 `web.runtime` 包。

    为什么不在文件顶部 import：runtime 会装配 FastAPI 用到的东西，顶部写容易拧成环。

    :return: web.runtime 模块本身
    """
    from web import runtime
    return runtime


def _desk(request: Request):
    """把这次请求的 JWT 翻成一份 Desk：谁在用、在哪条会话上。

    身份是**随请求走的值**，不是进程全局——两个浏览器同时用不会互相顶掉。
    会话来源优先看客户端带的 `X-Thread-Id`（多标签页各聊各的），
    没带就用这个账号最近动过的那条（见 runtime.resolve_desk）。
    """
    claims = require_session(request)
    return _runtime().resolve_desk(
        str(claims["passenger_id"]),
        username=str(claims.get("sub") or ""),
        role=str(claims.get("role") or "passenger"),
        thread_hint=request.headers.get("x-thread-id", ""),
    )


def _unauth_payload() -> dict:
    """未登录时给前端的那份「空工作台」快照。

    :return: 只有登录页需要的字段（identity / accounts / 邮件配置）
    """
    return {
        "authed": False,
        "identity": public_identity(None),
        "accounts": known_passengers(),
        "mail_ready": mailer.smtp_configured(),
        "dev_mail": mailer._dev_mode(),
    }


@api.get("/api/auth/captcha")
def auth_captcha() -> dict:
    """出一道图形验证码。答案留在服务端，前端只拿到题号和 SVG。"""
    captcha_id, svg = captcha.new_challenge()
    return {"captcha_id": captcha_id, "svg": svg, "expires_in": captcha.TTL}


@api.post("/api/auth/email/code")
def auth_email_code(body: EmailCodeIn) -> dict:
    """发邮箱验证码。发之前必须先过图形验证码——否则这里会变成免费邮件轰炸接口。

    **暂时下线（2026-09-20）**：演示环境没有邮件服务，注册那一道邮箱码用不上，
    前端表单与这个端点一起注释掉了。恢复时把下面整段放回来即可（verify / mailer
    两个模块一直留着，没动）。
    """
    # if not captcha.check(body.captcha_id, body.captcha_text):
    #     raise HTTPException(status_code=400, detail="图形验证码不正确或已过期")
    # if body.purpose not in verify.PURPOSES:
    #     raise HTTPException(status_code=400, detail="未知的验证码用途")
    # if not verify.valid_email(body.email):
    #     raise HTTPException(status_code=400, detail="邮箱格式不对")
    # if body.purpose == "register":
    #     existing = find_user(body.email)
    #     if existing:
    #         raise HTTPException(status_code=400, detail="这个邮箱已经注册过了，直接登录或换个邮箱")
    #
    # ok, wait = verify.can_send(body.email, body.purpose)
    # if not ok:
    #     raise HTTPException(status_code=429, detail=f"发送太频繁，请 {wait} 秒后再试")
    #
    # code = verify.issue(body.email, body.purpose)
    # result = mailer.send_code(body.email, code, body.purpose)
    # if result.get("delivered") == "failed":
    #     raise HTTPException(status_code=502, detail=f"验证码邮件发送失败：{result.get('error', '')}")
    # payload = {
    #     "sent": True,
    #     "email": verify.normalize(body.email),
    #     "delivered": result.get("delivered"),
    #     "cooldown": verify.RESEND_COOLDOWN,
    #     "expires_in": verify.TTL,
    # }
    # # 本地没配 SMTP 时把验证码带回前端提示一下，生产必须关掉这个分支
    # if result.get("dev_mode"):
    #     payload["dev_mode"] = True
    #     payload["dev_code"] = result.get("code")
    # return payload
    raise HTTPException(status_code=503, detail="邮箱验证码功能暂时下线，注册只需图形验证码")


@api.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    """问一句「现在是谁」：未登录也返回 200，前端据此决定停在登录页还是进工作台。

    :param request: 带 Cookie 的请求
    :return: 快照；未登录时是 `_unauth_payload()`
    """
    claims = current_session(request)
    if not claims:
        return _unauth_payload()
    return _runtime().snapshot(_desk(request))


@api.post("/api/auth/login")
def auth_login(body: LoginIn, response: Response, request: Request) -> dict:
    # 连续错太多次的账号要再过一道图形验证码
    """账号密码登录：必要时补图形验证码，成功则签发 Cookie 并返回首屏快照。

    :param body: 账号 / 口令 / 可选图形码
    :param response: 用来写 HttpOnly Cookie
    :param request: 取线程信息（desk 解析用）
    :return: 登录后的快照；失败抛 401（账号不存在与密码错误返回同一句话）
    """
    if captcha_required(body.account) and not captcha.check(body.captcha_id, body.captcha_text):
        raise HTTPException(
            status_code=400,
            detail="输错次数较多，请先填写图形验证码",
            headers={"X-Captcha-Required": "1"},
        )
    user = authenticate(body.account, body.password)
    if not user:
        need = captcha_required(body.account)
        raise HTTPException(
            status_code=401,
            detail="账号或密码不正确",
            headers={"X-Captcha-Required": "1"} if need else {},
        )
    rt = _runtime()
    desk = rt.resolve_desk(
        user["passenger_id"], username=user["username"], role=user["role"]
    )
    snap = rt.login_passenger(desk, user["passenger_id"], user["role"])
    issue_cookie(response, user)
    return snap


@api.post("/api/auth/register")
def auth_register(body: RegisterIn, response: Response) -> dict:
    # 顺序很重要：先把用户名/密码/邮箱/档案这些便宜的错误判掉，
    # 再去消费图形验证码。否则一个「密码太短」会把验证码烧掉，用户得重新看图。
    """注册：先判便宜的错误，再消费图形验证码，最后建号并直接登录。

    :param body: 用户名 / 密码 / 邮箱 / 档案号 / 图形码
    :param response: 用来写 Cookie
    :return: 注册即登录后的快照
    """
    try:
        validate_new_user(body.username, body.password, body.passenger_id, body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 邮箱验证码暂时下线（见 RegisterIn 的注释）：注册这一道改成图形验证码，
    # 它现在是唯一的门，所以必须在这里校验——不能因为少了一道码就干脆不设防。
    if not captcha.check(body.captcha_id, body.captcha_text):
        raise HTTPException(status_code=400, detail="图形验证码不正确或已过期")

    # 恢复邮箱验证码时把下面这段放回来（并去掉上面的图形码校验）：
    # ok, why = verify.verify(body.email, body.code, "register")
    # if not ok:
    #     raise HTTPException(status_code=400, detail=why)

    try:
        user = create_user(body.username, body.password, body.passenger_id, body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rt = _runtime()
    desk = rt.resolve_desk(
        user["passenger_id"], username=user["username"], role=user["role"]
    )
    snap = rt.login_passenger(desk, user["passenger_id"], user["role"])
    issue_cookie(response, user)
    return snap


@api.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> dict:
    """退出登录：清 Cookie、吊销令牌（jti 进名单），把工作台恢复成未登录的样子。

    :param request: 带 Cookie 的请求
    :param response: 用来清 Cookie
    :return: 未登录快照（含演示账号列表，方便前端直接重画登录页）
    """
    claims = current_session(request)
    desk = _desk(request) if claims else _runtime().BOOT_DESK
    snap = _runtime().logout_passenger(desk)
    clear_cookie(response, claims)
    return {**_unauth_payload(), **snap}


@api.post("/api/chat")
def chat(body: ChatIn, request: Request) -> dict:
    """一轮对话（非流式）。

    :param body: 用户发言
    :param request: 带 Cookie 的请求
    :return: 跑完后的快照（含挂起时的审批包）
    """
    return _runtime().chat_turn(_desk(request), body.message)


@api.post("/api/approve")
def do_approve(request: Request) -> dict:
    """批准：从 `interrupt()` 续跑（非流式）。

    :param request: 带 Cookie 的请求
    :return: 续跑后的快照
    """
    return _runtime().approve(_desk(request))


@api.post("/api/reject")
def do_reject(request: Request) -> dict:
    """驳回：补齐 ToolMessage 让专员重规划（非流式）。

    :param request: 带 Cookie 的请求
    :return: 驳回后的快照
    """
    return _runtime().reject(_desk(request))


@api.post("/api/session")
def new_session(request: Request) -> dict:
    """新建一条对话（等价于界面上点「＋ 新对话」）。

    :param request: 带 Cookie 的请求
    :return: 切到新会话后的快照
    """
    return _runtime().new_session(_desk(request))


class SessionPatch(BaseModel):
    """改名请求体。

    :param title: 新名字，1–40 字
    """
    title: str = Field(min_length=1, max_length=40, description="新的会话名")


@api.get("/api/sessions")
def list_sessions(request: Request) -> dict:
    """当前账号的会话列表 + 当前是哪条。

    :param request: 带 Cookie 的请求
    :return: {"sessions": [...], "active": thread_id}
    """
    rt = _runtime()
    desk = _desk(request)
    return {"sessions": rt.sessions_view(desk), "active": desk.thread_id}


@api.post("/api/sessions")
def create_session(request: Request) -> dict:
    """同 `new_session`，留着给 REST 风格的调用方。

    :param request: 带 Cookie 的请求
    :return: 新会话快照
    """
    return _runtime().new_session(_desk(request))


@api.post("/api/sessions/{thread_id}/open")
def open_session(thread_id: str, request: Request) -> dict:
    """切换到某条历史对话（只能切自己的）。

    :param thread_id: 目标会话 id
    :param request: 带 Cookie 的请求
    :return: 切换后的快照；不是自己的或不存在则 404
    """
    try:
        return _runtime().open_session(_desk(request), thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api.patch("/api/sessions/{thread_id}")
def rename_session(thread_id: str, body: SessionPatch, request: Request) -> dict:
    """给某条会话改名。

    :param thread_id: 目标会话 id
    :param body: 新标题
    :param request: 带 Cookie 的请求
    :return: 改名后的快照
    """
    try:
        return _runtime().rename_session(_desk(request), thread_id, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api.delete("/api/sessions/{thread_id}")
def delete_session(thread_id: str, request: Request) -> dict:
    """删除某条会话（正在用的那条不让删）。

    :param thread_id: 目标会话 id
    :param request: 带 Cookie 的请求
    :return: 删除后的快照
    """
    try:
        return _runtime().delete_session(_desk(request), thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api.get("/api/orders")
def list_orders(request: Request) -> dict:
    """订单中心数据：普通账号看自己的，运营账号看全量。

    :param request: 带 Cookie 的请求
    :return: {"counts": ..., "items": ..., "owner_view": bool}
    """
    return _runtime().orders_view(_desk(request))


class OrderCancel(BaseModel):
    """退单请求体。

    :param order_id: 订单号（必须为正）
    """
    order_id: int = Field(gt=0, description="订单号")


@api.post("/api/orders/cancel")
def cancel_order(body: OrderCancel, request: Request) -> dict:
    """退单：释放库存标记、写审计、把订单置为已取消。

    :param body: 订单号
    :param request: 带 Cookie 的请求
    :return: 退单后的快照（多带一个 cancelled 字段供前端提示）
    """
    rt = _runtime()
    desk = _desk(request)
    owner_view = desk.role == "ops"
    try:
        order = orders.cancel_order(body.order_id, desk.passenger_id, owner_view)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.write(
        audit.CANCEL,
        actor=desk.actor,
        passenger_id=desk.passenger_id,
        thread_id=desk.thread_id or "",
        target=f"{order['kind']}#{order['ref']}",
        detail={"title": order["title"], "via": "订单中心"},
    )
    snap = rt.snapshot(desk)
    snap["cancelled"] = {"id": order["id"], "title": order["title"]}
    return snap


@api.get("/api/explore")
def explore_city(city: str = "", request: Request = None) -> dict:
    """按城市直接翻库存（景点 / 酒店 / 租车），不经过模型；只要求登录。"""
    _desk(request)
    if not city:
        return {"cities": _runtime().explore_cities(), "city": "", "spots": [], "hotels": [], "cars": []}
    data = explore.browse(city)
    data["art"] = art.tile(data.get("code") or "", 40, data.get("cn") or "")
    data["photo"] = art.photo(data.get("code") or "")
    for key, kind in (("spots", "spot"), ("hotels", "hotel"), ("cars", "car")):
        for item in data.get(key) or []:
            item["kind_art"] = art.kind_art(kind)
    return data


@api.get("/api/audit")
def list_audit(request: Request) -> dict:
    """审计流水（只给运营账号）。

    :param request: 带 Cookie 的请求
    :return: 全量流水；非 ops 账号抛 403
    """
    desk = _desk(request)
    if desk.role != "ops":
        raise HTTPException(status_code=403, detail="审计流水只有运营账号能看")
    return {
        "summary": audit.summary(),
        "items": audit.recent(120),
        "owner_view": True,
    }


@api.get("/api/state")
def state(request: Request) -> dict:
    """当前快照（前端轮询 / 首屏都用它）。

    :param request: 带 Cookie 的请求
    :return: 快照
    """
    return _runtime().snapshot(_desk(request))


def _sse_response(generator):
    """把同步生成器包装成 `text/event-stream` 响应。

    :param generator: 逐条 yield SSE 字符串的生成器
    :return: StreamingResponse（关掉缓冲，别让代理攒着）
    """
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@api.post("/api/chat/stream")
def chat_stream(body: ChatIn, request: Request):
    """一轮对话的节点级 SSE。

    :param body: 用户发言
    :param request: 带 Cookie 的请求
    :return: StreamingResponse
    """
    return _sse_response(_runtime().iter_chat(_desk(request), body.message))


@api.post("/api/approve/stream")
def approve_stream(request: Request):
    """批准执行的 SSE。

    :param request: 带 Cookie 的请求
    :return: StreamingResponse
    """
    return _sse_response(_runtime().iter_approve(_desk(request)))


@api.post("/api/reject/stream")
def reject_stream(request: Request):
    """驳回重规划的 SSE。

    :param request: 带 Cookie 的请求
    :return: StreamingResponse
    """
    return _sse_response(_runtime().iter_reject(_desk(request)))
