"""web/app.py —— 服务化：会话柜 API + SSE 问答 + 三栏工作台。

蒸馏来源：完整版 ``api/``（会话 CRUD、问答、反馈）+ ``frontend/`` 问答页。
对应教程：11.13。教学版省略 JWT，但每条接口都带 ``user_id``：
工牌既裁检索，也裁会话——IT 员工列不出财务负责人的会话。

启动：uvicorn forge_lite.web.app:app --reload --port 8800
页面：http://127.0.0.1:8800/
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import air
from fastapi import File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import config
from ..store.accounts import (
    IDENTITIES,
    SESSION_DAYS,
    Account,
    AccountError,
    authenticate,
    create_session,
    init_db,
    drop_session,
    read_session,
    register as register_account,
)
from ..answer.agent import ask as ask_agent
from ..store.audit import get_audit
from ..data.catalog import (
    get_chunk_by_doc_id,
    highlight_span,
    list_chunks_of,
    list_documents,
)
from ..service.documents import (
    ALLOWED_SUFFIXES,
    MAX_UPLOAD_BYTES,
    DocumentError,
    DocumentNotFound,
    delete_document,
    document_chunks,
    index_summary,
    list_documents_admin,
    preview_chunk_plan,
    summarize_upload_results,
    upload_document,
)
from ..answer.evaluation import (
    GOLDEN_SET,
    cases_index,
    iter_cases,
    list_reports,
    load_report,
    save_report,
    summarize,
)
from ..answer.classroom import EMPTY_COPY, badge_cards, prompts_for
from ..store.conversations import (
    ConversationConflict,
    ConversationError,
    get_store,
)
from ..core.evidence import split_routes, status_label
from ..service.export import build_export
from ..service.graph_view import list_entities, neighborhood
from ..core.identity import USERS, resolve_actor
from ..retrieve.search import warm_tokenizer
from ..core.labels import intent_text
from ..core.sseutil import format_error, format_frame, stream_answer
from ..retrieve.trace import build_trace
from .pages import render_chat_page, render_login_page

app = air.Air(title="KnowledgeForge Lite", version="0.2.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"


class AskBody(BaseModel):
    """问答请求体。
    """
    question: str
    user_id: str = "it_staff"
    conversation_id: str | None = None


class ConversationCreateBody(BaseModel):
    """新建会话的请求体。
    """
    user_id: str = "it_staff"
    title: str = ""


class ConversationRenameBody(BaseModel):
    """重命名会话的请求体。
    """
    user_id: str = "it_staff"
    title: str


class FeedbackBody(BaseModel):
    """一条答案反馈。
    """
    user_id: str = "it_staff"
    rating: str = Field(pattern="^(up|down|issue)$")
    note: str = ""


def _actor_payload(user_id: str | None) -> dict[str, str]:
    """给前端的身份信息（页眉、工牌架、导出都用它）。
    ``user_id`` 是工牌 id，``None`` 或不认识的值会回落到默认工牌。返回 ``user_id`` / ``name`` / ``role`` / ``department`` 四个键。
    """
    actor = resolve_actor(user_id)
    return {
        "user_id": actor.user_id,
        "name": actor.display_name,
        "role": actor.role,
        "department": actor.department,
    }


def _http_from_store(exc: Exception) -> HTTPException:
    """把会话存储抛出的异常翻成对外的 HTTP 状态码。

    **"找不到"和"没权限"给同一个回答**，不泄露会话存不存在；
    ``exc`` 是 store 层抛出的异常。``ConversationError`` 一律 404——**"找不到"和"没权限"给同一个回答**，不泄露会话存不存在；冲突类 400；其余 500 并给一句笼统的话。
    """
    if isinstance(exc, ConversationError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ConversationConflict):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="会话柜异常")


@app.get("/health")
def health() -> JSONResponse:
    """存活探针。前端启动时 ping 它，用来区分"服务没起来"和"接口报错"。"""
    return JSONResponse({"status": "ok"})


@app.get("/whoami")
def whoami() -> JSONResponse:
    """身份与课堂文案：四张工牌卡（各带可见/裁掉的篇数）加空状态剧本。

    """
    return JSONResponse({
        "users": [
            {
                "user_id": user.user_id,
                "name": user.display_name,
                "role": user.role,
                "department": user.department,
            }
            for user in USERS.values()
        ],
        "badges": badge_cards(),
        "empty": EMPTY_COPY,
    })


@app.get("/classroom/prompts")
def classroom_prompts(user_id: str = Query(default="it_staff")) -> JSONResponse:
    """空状态那张剧本表：问一句 / 该看见什么 / 换工牌对照。
    ``user_id`` 是当前工牌；返回的题目按"自己工牌在前、对照题在后"排。
    """
    actor = resolve_actor(user_id)
    return JSONResponse({
        "actor": _actor_payload(actor.user_id),
        "prompts": prompts_for(actor.user_id),
        "empty": EMPTY_COPY,
    })


# ── 账号与会话 ──────────────────────────────────────────────────
#
# 会话是一串随机 token 存在库里（见 accounts.py），cookie 只装它。
# 登出 = 删掉那一行，立刻失效——不用维护黑名单。

SESSION_COOKIE = "forge_session"
GUEST_COOKIE = "forge_guest"


def _account_from(request: Request) -> Account | None:
    """从请求 cookie 里认出登录账号，没登录返回 ``None``。
    ``request`` 是当前 HTTP 请求。cookie 只装会话 token，账号信息从库里查——所以登出删一行就立刻失效。
    """
    return read_session(request.cookies.get(SESSION_COOKIE) or "")


def _set_session(response, token: str) -> None:
    """把会话 token 写进 cookie。
    ``response`` 是要返回的响应对象；``token`` 是 ``accounts.create_session`` 发的串。``HttpOnly`` 让页面脚本读不到它，``SameSite=Lax`` 挡跨站请求顺带带上它。
    """
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                        max_age=SESSION_DAYS * 86400, path="/")


@app.get("/login")
def login_page():
    """登录 / 注册页。未登录访问控制台会被 303 到这里。"""
    return render_login_page()


@app.get("/api/auth/me")
def auth_me(request: Request) -> JSONResponse:
    """当前登录账号。没登录返回 200 + account:null——这不是错误，是"还没登录"。
    ``request`` 用来读会话 cookie。
    """
    account = _account_from(request)
    return JSONResponse({
        "account": account.as_dict() if account else None,
        "guest": bool(request.cookies.get(GUEST_COOKIE)),
        "identities": [{"key": key, **value} for key, value in IDENTITIES.items()],
    })


@app.post("/api/auth/login")
async def auth_login(request: Request) -> JSONResponse:
    """登录：核对口令、开会话、写 cookie。
    ``request`` 的 JSON 体要带 ``username`` 和 ``password``。账号不存在和口令错都回同一个 401 文案——不区分这两者，否则这个接口就成了"某用户名存不存在"的探测器。
    """
    body = await request.json()
    account = authenticate(str(body.get("username") or ""), str(body.get("password") or ""))
    if account is None:
        raise HTTPException(status_code=401, detail="用户名或密码不对。")
    response = JSONResponse({"account": account.as_dict()})
    _set_session(response, create_session(account.username))
    response.delete_cookie(GUEST_COOKIE, path="/")
    return response


@app.post("/api/auth/register")
async def auth_register(request: Request) -> JSONResponse:
    """注册：建账号、顺手登录。
    ``request`` 的 JSON 体要带 ``username``、``password``，可选 ``display_name``、``role``、``department``。字段校验在 ``accounts.register`` 里做，那边的 ``AccountError`` 直接翻成 400，消息就是给页面看的人话。
    """
    body = await request.json()
    try:
        account = register_account(
            str(body.get("username") or ""),
            str(body.get("password") or ""),
            str(body.get("display_name") or ""),
            str(body.get("identity") or "it_staff"),
        )
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = JSONResponse({"account": account.as_dict()})
    _set_session(response, create_session(account.username))
    response.delete_cookie(GUEST_COOKIE, path="/")
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> JSONResponse:
    """登出：删掉服务端那一条会话，并清 cookie。
    ``request`` 用来读当前 token。删库里的行 = 立刻失效，不需要令牌黑名单。
    """
    drop_session(request.cookies.get(SESSION_COOKIE) or "")
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.post("/api/auth/guest")
def auth_guest() -> JSONResponse:
    """访客演示：不建账号，用默认工牌走一遍。课堂上不想注册时的入口。"""
    response = JSONResponse({"guest": True})
    response.set_cookie(GUEST_COOKIE, "1", httponly=True, samesite="lax", path="/")
    return response


@app.page
def index(request: Request):
    """控制台。没登录也没以访客身份进过，就先去登录页。
    ``request`` 用来读会话 cookie；没登录也没点过"访客"就 303 去登录页。
    """
    if _account_from(request) is None and not request.cookies.get(GUEST_COOKIE):
        return RedirectResponse("/login", status_code=303)
    return render_chat_page()

@app.get("/api/conversations")
def list_conversations(
    user_id: str = Query(default="it_staff"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> JSONResponse:
    """列出某个工牌的会话，按最近更新倒序。
    ``user_id`` 是工牌 id；``limit`` 是本页条数（1–100）；``cursor`` 是上一页末尾给的游标，不传就从最新开始。用游标不用 OFFSET——翻页时不会有记录被漏掉或重复。
    """
    actor = resolve_actor(user_id)
    page = get_store().list_conversations(actor.user_id, limit=limit, cursor=cursor)
    get_audit().record("list_conversations", actor.user_id, extra={"count": len(page.items)})
    payload = page.as_dict()
    payload["actor"] = _actor_payload(actor.user_id)
    return JSONResponse(payload)


@app.post("/api/conversations")
def create_conversation(body: ConversationCreateBody) -> JSONResponse:
    """新建一个会话。
    ``body`` 里带 ``user_id``（归属工牌）和可选 ``title``；标题留空时按第一句话起名。
    """
    actor = resolve_actor(body.user_id)
    record = get_store().create_conversation(actor.user_id, title=body.title)
    get_audit().record("create_conversation", actor.user_id, conversation_id=record.id)
    return JSONResponse(record.as_dict())


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user_id: str = Query(default="it_staff")) -> JSONResponse:
    """读一个会话的全部消息。
    ``conversation_id`` 是会话 id；``user_id`` 是当前工牌。会话不属于这张工牌时按 404 处理——**不是"拒绝访问"，是"不存在"**，不泄露别人有没有这个会话。
    """
    actor = resolve_actor(user_id)
    try:
        detail = get_store().get_conversation(conversation_id, actor.user_id)
    except (ConversationError, ConversationConflict) as exc:
        raise _http_from_store(exc) from exc
    get_audit().record("get_conversation", actor.user_id, conversation_id=conversation_id)
    payload = detail.as_dict()
    payload["actor"] = _actor_payload(actor.user_id)
    return JSONResponse(payload)


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, body: ConversationRenameBody) -> JSONResponse:
    """改会话标题。
    ``conversation_id`` 是目标会话；``body`` 里带 ``user_id``（必须归属它）和新 ``title``。
    """
    actor = resolve_actor(body.user_id)
    try:
        record = get_store().rename_conversation(conversation_id, actor.user_id, body.title)
    except (ConversationError, ConversationConflict) as exc:
        raise _http_from_store(exc) from exc
    get_audit().record("rename_conversation", actor.user_id, conversation_id=conversation_id)
    return JSONResponse(record.as_dict())


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user_id: str = Query(default="it_staff")) -> JSONResponse:
    """删一个会话。
    ``conversation_id`` 是目标会话；``user_id`` 是当前工牌。走软删除留痕，审计里仍看得到删过。
    """
    actor = resolve_actor(user_id)
    try:
        run_ids = get_store().delete_conversation(conversation_id, actor.user_id)
    except (ConversationError, ConversationConflict) as exc:
        raise _http_from_store(exc) from exc
    get_audit().record("delete_conversation", actor.user_id, conversation_id=conversation_id)
    return JSONResponse({"ok": True, "run_ids": run_ids})


@app.post("/api/runs/{run_id}/feedback")
def submit_feedback(run_id: str, body: FeedbackBody) -> JSONResponse:
    """给某一次问答留一条反馈。
    ``run_id`` 是哪一跑；``body`` 里带 ``user_id``、``rating``（up / down / issue）和选填 ``note``。
    """
    actor = resolve_actor(body.user_id)
    try:
        record = get_store().upsert_feedback(run_id, actor.user_id, body.rating, body.note)
    except (ConversationError, ConversationConflict) as exc:
        raise _http_from_store(exc) from exc
    get_audit().record(
        "feedback", actor.user_id, run_id=run_id,
        detail=body.rating, extra={"note": record.get("note") or ""},
    )
    return JSONResponse(record)


@app.get("/api/catalog")
def catalog(user_id: str = Query(default="it_staff")) -> JSONResponse:
    """这张工牌看得见的文档目录。
    ``user_id`` 是工牌 id；返回可见文档和"被裁掉几篇"的计数——被裁的只给条数、不给标题，列出名字本身就是泄露。
    """
    actor = resolve_actor(user_id)
    snapshot = list_documents(actor.user_id)
    get_audit().record("list_catalog", actor.user_id, extra={"visible": snapshot.as_dict()["visible_count"]})
    return JSONResponse(snapshot.as_dict())


@app.get("/api/chunks")
def chunks(
    source: str = Query(default=""),
    doc_id: str = Query(default=""),
    user_id: str = Query(default="it_staff"),
    highlight: str = Query(default=""),
) -> JSONResponse:
    """读一块切块原文，或按 doc_id 反查。
    参数走查询串：``source`` 定位文件；``user_id`` 是当前工牌（预览原文和检索走同一把 ACL）；``highlight`` 是要标黄的那段。
    """
    actor = resolve_actor(user_id)
    if doc_id:
        preview = get_chunk_by_doc_id(doc_id, actor.user_id)
        if preview is None:
            raise HTTPException(status_code=404, detail="切块不存在")
        payload = preview.as_dict()
        payload["highlight"] = highlight_span(preview.text, highlight)
        get_audit().record("preview_chunk", actor.user_id, detail=preview.key)
        return JSONResponse(payload)
    if not source:
        raise HTTPException(status_code=400, detail="需要 source 或 doc_id")
    items = [item.as_dict() for item in list_chunks_of(source, actor.user_id)]
    if not items:
        raise HTTPException(status_code=404, detail="文档不存在")
    get_audit().record("preview_chunk", actor.user_id, detail=source)
    return JSONResponse({"source": source, "chunks": items})


@app.get("/api/audit")
def audit_feed(user_id: str = Query(default="it_staff"), limit: int = Query(default=50, ge=1, le=200)) -> JSONResponse:
    """审计流水。
    ``user_id`` 是当前工牌（审计按工牌过滤）；``limit`` 是条数上限。
    """
    actor = resolve_actor(user_id)
    return JSONResponse({"items": get_audit().for_actor(actor.user_id, limit=limit)})


def _require_admin(user_id: str | None, area: str) -> None:
    """文档区与评测区是管理面：和完整版一样按角色挡，返回 403 并说清怎么换。
    ``user_id`` 是当前工牌；``area`` 是区名（"文档区" / "评测区"），用来拼提示语。
    """
    actor = resolve_actor(user_id)
    if actor.role != "company_admin":
        raise HTTPException(
            status_code=403,
            detail=f"{area}只有公司管理员能进（当前工牌：{actor.display_name}）。切到「公司管理员」再试。",
        )


@app.get("/api/documents")
def documents_overview(user_id: str = Query(default="it_staff")) -> JSONResponse:
    """文档区总览：账本 + 切块账 + 隔离原因，管理员可见。
    ``user_id`` 必须是公司管理员，否则 403。
    """
    _require_admin(user_id, "文档区")
    actor = resolve_actor(user_id)
    rows = [row.as_dict() for row in list_documents_admin()]
    get_audit().record("list_catalog", actor.user_id, detail="documents_console",
                       extra={"count": len(rows)})
    return JSONResponse({
        "documents": rows,
        "summary": index_summary(),
        "limits": {
            "max_bytes": MAX_UPLOAD_BYTES,
            "suffixes": list(ALLOWED_SUFFIXES),
            "chunk": {"size": config.CHUNK_SIZE, "overlap": config.CHUNK_OVERLAP},
        },
    })


@app.post("/api/documents/upload")
async def documents_upload(
    files: list[UploadFile] = File(default_factory=list),
    user_id: str = Query(default="it_staff"),
) -> JSONResponse:
    """上传一篇或多篇，逐篇入库。只对上传的文件做嵌入，别的文档不动。
    ``files`` 是这次上传的文件列表（可多选）；``user_id`` 必须是公司管理员。只对上传的文件做嵌入，其它文档的重算留给全量同步。
    """
    _require_admin(user_id, "文档区")
    actor = resolve_actor(user_id)
    if not files:
        raise HTTPException(status_code=400, detail="没有收到文件")
    results: list[dict[str, Any]] = []
    for item in files:
        raw = await item.read()
        try:
            results.append(upload_document(item.filename or "未命名.txt", raw))
        except DocumentError as exc:
            results.append({"source": item.filename or "未命名.txt", "status": "rejected", "error": str(exc)})
    payload = summarize_upload_results(results)
    for row in payload["items"]:
        get_audit().record("preview_chunk" if row.get("status") == "rejected" else "list_catalog",
                           actor.user_id, detail=f"upload:{row.get('source')}",
                           extra={"status": row.get("status"), "chunks": row.get("chunks")})
    payload["overview"] = {
        "documents": [row.as_dict() for row in list_documents_admin()],
        "summary": index_summary(),
    }
    return JSONResponse(payload)


@app.delete("/api/documents/{source}")
def documents_delete(source: str, user_id: str = Query(default="it_staff")) -> JSONResponse:
    """删源文件并级联清理索引与账本。管理员可见。
    ``source`` 是要删的文件名；``user_id`` 必须是公司管理员。
    """
    _require_admin(user_id, "文档区")
    actor = resolve_actor(user_id)
    try:
        result = delete_document(source)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    get_audit().record("delete_conversation", actor.user_id, detail=f"doc:{result['source']}")
    result["overview"] = {
        "documents": [row.as_dict() for row in list_documents_admin()],
        "summary": index_summary(),
    }
    return JSONResponse(result)


@app.get("/api/documents/{source}/chunks")
def documents_chunks(
    source: str,
    user_id: str = Query(default="it_staff"),
    text: str = Query(default="", description="给了就把这段文本按当前旋钮切一遍（不落盘）"),
    chunk_size: int | None = Query(default=None, ge=50, le=2000),
    overlap: int | None = Query(default=None, ge=0, le=400),
) -> JSONResponse:
    """一篇文档的切块；带 text 参数时改为「切块预演」，直接看旋钮的效果。
    ``source`` 是文件名；``user_id`` 必须是公司管理员；``chunk_size`` 与 ``overlap`` 只在预演模式（传了 ``text``）下生效，越界由服务端拒绝。
    """
    _require_admin(user_id, "文档区")
    if text:
        plan = preview_chunk_plan(text, chunk_size=chunk_size, overlap=overlap)
        return JSONResponse({"mode": "preview", "chunks": plan,
                             "chunk_size": chunk_size or config.CHUNK_SIZE,
                             "overlap": overlap if overlap is not None else config.CHUNK_OVERLAP})
    name = Path(str(source)).name
    chunks = document_chunks(name)
    row = next((item for item in list_documents_admin() if item.source == name), None)
    if row is None and not chunks:
        raise HTTPException(status_code=404, detail="文档不在账本里")
    return JSONResponse({
        "mode": "chunks",
        "source": name,
        "status": row.status if row else "indexed",
        "signals": row.signals if row else [],
        "chunks": chunks,
    })


@app.get("/api/evaluation/cases")
def evaluation_cases(user_id: str = Query(default="it_staff")) -> JSONResponse:
    """黄金集用例清单。
    ``user_id`` 必须是公司管理员，否则 403。返回用例索引和当前的门禁线。
    """
    _require_admin(user_id, "评测区")
    return JSONResponse({"cases": cases_index(), "gate": config.PASS_RATE_GATE})


@app.post("/api/evaluation/run")
def evaluation_run(user_id: str = Query(default="it_staff"), note: str = Query(default="")) -> StreamingResponse:
    """逐条跑黄金集，SSE 把每一条的结果推给页面，最后给摘要并落一份报告。
    ``user_id`` 必须是公司管理员；``note`` 是给这份报告留的一句备注。
    """
    _require_admin(user_id, "评测区")
    actor = resolve_actor(user_id)

    def event_stream():
        """逐条跑黄金集，每跑完一条推一帧 ``case``，最后推 ``summary`` 并存报告。

        没有参数——它闭包捕获外面的 ``actor`` 和 ``note``。异常也翻成 ``error`` 帧推出去，
        不往上抛：SSE 已经开始写了，抛出去只能得到一个断掉的流。
        """
        results = []
        try:
            for result in iter_cases():
                results.append(result)
                yield format_frame({"type": "case", **result.as_dict()}, event="case")
        except Exception as exc:  # 模型端点挂了：如实报，不假装跑完
            yield format_error(f"评测中断：{exc}")
            get_audit().record("ask", actor.user_id, status="error", detail=f"evaluation:{exc}")
            return
        summary = summarize(results)
        report = save_report(results, note=note)
        yield format_frame({"type": "summary", "summary": summary,
                            "report": report["path"], "created_at": report["created_at"]},
                           event="summary")
        get_audit().record("ask", actor.user_id, status="evaluation",
                           detail=f"pass={summary['passed']}/{summary['total']}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/evaluation/reports")
def evaluation_reports(user_id: str = Query(default="it_staff"), limit: int = Query(default=10, ge=1, le=50)) -> JSONResponse:
    """历史评测报告清单，新的在前。
    ``user_id`` 必须是公司管理员；``limit`` 是最多返回几条摘要。
    """
    _require_admin(user_id, "评测区")
    return JSONResponse({"reports": list_reports(limit=limit)})


@app.get("/api/evaluation/reports/{name}")
def evaluation_report(name: str, user_id: str = Query(default="it_staff")) -> JSONResponse:
    """读一份评测报告的全文。
    ``name`` 是报告文件名（会被校验成 ``eval-*.json``，挡目录穿越）；``user_id`` 必须是公司管理员。
    """
    _require_admin(user_id, "评测区")
    try:
        return JSONResponse(load_report(name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="报告不存在") from exc


@app.post("/api/evaluation/ragas")
def evaluation_ragas(user_id: str = Query(default="it_staff")) -> StreamingResponse:
    """Ragas 0.4 三指标逐条打分。缺依赖或缺 Key 时如实报错，不吞异常。
    ``user_id`` 必须是公司管理员。每条要调 3 次裁判模型，比较慢。
    """
    _require_admin(user_id, "评测区")
    actor = resolve_actor(user_id)

    def event_stream():
        """逐条调 Ragas 三项指标，每完成一条推一帧 ``case``，最后推 ``summary``。

        没有参数——它闭包捕获外面的 ``actor``。同理，失败也翻成 ``error`` 帧。
        """
        from ..answer.evaluate import iter_ragas
        try:
            collected = []
            for row in iter_ragas():
                collected.append(row)
                yield format_frame({"type": "case", **row}, event="case")
        except ImportError:
            yield format_error("Ragas 裁判不可用：pip install 'ragas>=0.4.3' openai langchain-community")
            return
        except Exception as exc:
            yield format_error(f"Ragas 打分失败：{exc}")
            get_audit().record("ask", actor.user_id, status="error", detail=f"ragas:{exc}")
            return
        keys = ("faithfulness", "context_recall", "answer_relevancy")
        averages = {
            key: (sum(float(row.get(key) or 0.0) for row in collected) / len(collected)) if collected else 0.0
            for key in keys
        }
        yield format_frame({"type": "summary", "averages": averages, "count": len(collected)},
                           event="summary")
        get_audit().record("ask", actor.user_id, status="ragas",
                           detail="、".join(f"{key}={value:.2f}" for key, value in averages.items()))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/runs/{run_id}/trace")
def run_trace(run_id: str, user_id: str = Query(default="it_staff")) -> JSONResponse:
    """某一跑的检索轨迹：查询、路由、证据资格、预算。证据抽屉展开用。
    ``run_id`` 是哪一跑；``user_id`` 是当前工牌（轨迹也按工牌裁）。
    """
    actor = resolve_actor(user_id)
    try:
        record = get_store().get_run(run_id, actor.user_id)
    except (ConversationError, ConversationConflict) as exc:
        raise _http_from_store(exc) from exc
    trace = build_trace({
        "question": record.question,
        "queries": record.queries,
        "intent": record.intent,
        "status": record.status,
        "routes": record.routes,
        "citations": record.citations,
        # 明细行（带各路名次）直接透传，build_trace 会据此画「三路召回」
        "source_details": [item for item in record.contexts if isinstance(item, dict)],
        "contexts": [item.get("snippet") if isinstance(item, dict) else str(item)
                     for item in record.contexts],
        # 资格结论跟运行结局是两套词：evidence 里才是 answered / insufficient_evidence，
        # 拿 record.status（ok / refuse）去顶替会让抽屉画出「证据 ok」。
        "evidence": record.evidence or {},
        "warn": record.warn,
        "run_id": record.id,
        "conversation_id": record.conversation_id,
    })
    get_audit().record("read_trace", actor.user_id, run_id=run_id,
                        conversation_id=record.conversation_id)
    return JSONResponse(trace.as_dict())


@app.get("/api/conversations/{conversation_id}/export")
def export_conversation(
    conversation_id: str,
    user_id: str = Query(default="it_staff"),
    format: str = Query(default="md", pattern="^(md|json)$"),
):
    """导出自己的会话。格式只认 md / json，别的当入参错误。
    ``conversation_id`` 是会话 id；``user_id`` 是当前工牌；``format`` 取 ``md`` 或 ``json``。
    """
    from fastapi import Response
    actor = resolve_actor(user_id)
    try:
        bundle = build_export(get_store(), conversation_id, actor.user_id, fmt=format)
    except (ConversationError, ConversationConflict) as exc:
        raise _http_from_store(exc) from exc
    get_audit().record("export_conversation", actor.user_id,
                        conversation_id=conversation_id, detail=f"format:{format}")
    # HTTP 头只能走 latin-1：中文标题要按 RFC 5987 转义，另给一个 ASCII 回落名
    from urllib.parse import quote
    ascii_name = f"conversation-{conversation_id[-8:]}.{'json' if format == 'json' else 'md'}"
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(bundle.filename)}"
    )
    return Response(
        content=bundle.content,
        media_type=bundle.media_type,
        headers={"Content-Disposition": disposition},
    )


@app.get("/api/graph")
def graph_neighborhood(
    entity: str = Query(default=""),
    user_id: str = Query(default="it_staff"),
    limit: int = Query(default=12, ge=1, le=40),
) -> JSONResponse:
    """图谱邻接预览。工牌看不见的源文档上的边直接裁掉。
    ``entity`` 是实体名；``user_id`` 是当前工牌；``limit`` 是每类邻居的条数上限。
    """
    actor = resolve_actor(user_id)
    if entity:
        return JSONResponse(neighborhood(entity, actor.user_id, limit=limit).as_dict())
    return JSONResponse({
        "actor": _actor_payload(actor.user_id),
        "entities": list_entities(actor.user_id),
    })


@app.post("/ask")
def ask(body: AskBody):
    """问答主入口，SSE 流式返回。
    ``body`` 里带 ``question``（问句）、``user_id``（以哪张工牌问）、``conversation_id``（接着哪个会话，空则新开）。依次推 ``message`` 增量、``citations``、``done`` 三种帧。
    """
    actor = resolve_actor(body.user_id)

    def event_stream():
        """跑一次完整问答链，推 ``message`` 增量、``citations``、``done`` 三种帧。

        没有参数——它闭包捕获外面的 ``body`` 和 ``actor``。
        帧的顺序由 ``sseutil.ALLOWED_EVENTS`` 定死：先增量、再引用、最后 done，
        客户端靠这个顺序决定什么时候可以渲染。
        """
        try:
            state = ask_agent(
                body.question,
                user_id=actor.user_id,
                conversation_id=body.conversation_id,
                persist=True,
            )
        except Exception as exc:
            from ..core.sseutil import format_error
            yield format_error("问答失败，请稍后重试")
            get_audit().record("ask", actor.user_id, status="error", question=body.question, detail=str(exc))
            return
        get_audit().record(
            "ask",
            actor.user_id,
            conversation_id=str(state.get("conversation_id") or ""),
            run_id=str(state.get("run_id") or ""),
            status=str(state.get("status") or ""),
            routes=str(state.get("routes") or ""),
            question=body.question,
        )
        done: dict[str, Any] = {
            "status": state.get("status"),
            "citations": state.get("citations") or [],
            "warn": state.get("warn") or "",
            "routes": state.get("routes") or "",
            "intent": state.get("intent") or "",
            "intent_label": intent_text(str(state.get("intent") or "")),
            "actor": actor.display_name,
            "actor_id": actor.user_id,
            "conversation_id": state.get("conversation_id") or "",
            "run_id": state.get("run_id") or "",
            "history_saved": bool(state.get("history_saved")),
            "response_status": state.get("response_status") or "",
            # 拒答就显示「已拒答」：资格说「够答」但引用/复检拦下时，不能显示已回答
            "response_label": (
                status_label("refuse") if state.get("status") == "refuse"
                else status_label(str(state.get("response_status") or state.get("status") or ""))
            ),
            "evidence": state.get("evidence") or {},
            "route_chips": split_routes(str(state.get("routes") or "")),
            "contexts": [
                {"doc_id": (state.get("citations") or [{}])[i].get("doc_id") if i < len(state.get("citations") or []) else "",
                 "snippet": text[:400]}
                for i, text in enumerate(state.get("contexts") or [])
            ],
            "queries": state.get("queries") or [body.question],
            "source_details": state.get("source_details") or [],
        }
        yield from stream_answer(state.get("answer") or "", state.get("citations") or [], done)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 启动时把账号库的建表做掉：库是空的（不预置任何账号），但表和索引要先在，
# 否则第一个来注册的人会撞上一句"no such table"，那不该是用户看到的第一句话。
init_db()

# 预热 jieba 词典：第一次建前缀树要 300ms 左右，不该让第一个提问的用户等它
warm_tokenizer()


@app.middleware("http")
async def revalidate_static(request, call_next):
    """静态资源每次都回源校验一轮（ETag 命中就是 304，很便宜）。

    StaticFiles 只给 last-modified / etag，不给 Cache-Control——浏览器会按
    「启发式缓存」直接拿旧文件，于是改完 JS/CSS 刷新页面看到的还是上一版。
    ``request`` 是进来的请求；``call_next`` 是下一环，拿到响应之后再改头。
    """
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["cache-control"] = "no-cache"
    return response
