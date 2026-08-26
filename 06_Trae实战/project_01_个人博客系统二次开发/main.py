from contextlib import asynccontextmanager
import os
from pathlib import Path

import ai_service
import database
import security
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Base, Comment, Like, Post, User
from schemas import (
    AIGenerateRequest,
    AIGenerateResponse,
    AIStatusResponse,
    BackfillResponse,
    CategoryStat,
    CommentCreate,
    CommentResponse,
    LikeResponse,
    LoginRequest,
    PaginatedComments,
    PaginatedPosts,
    PostCreate,
    PostResponse,
    PostUpdate,
    TokenResponse,
    UserBrief,
    UserCreate,
    UserResponse,
)

# 允许通过项目根目录 .env 注入 LLM_API_KEY 等环境变量（无 .env 文件也不报错）
load_dotenv()

# 项目根目录（index.html 所在位置）
BASE_DIR = Path(__file__).resolve().parent


def seed_admin(db: Session):
    """首次启动/首次建库时创建种子管理员"""
    if db.query(User).filter(User.username == security.ADMIN_USERNAME).first():
        return
    db.add(
        User(
            username=security.ADMIN_USERNAME,
            password_hash=security.hash_password(security.ADMIN_PASSWORD),
            role="admin",
        )
    )
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时自动建表并种子化管理员"""
    Base.metadata.create_all(bind=database.engine)
    with database.SessionLocal() as db:
        seed_admin(db)
    yield


app = FastAPI(title="个人博客系统", version="0.1.0", lifespan=lifespan)

# CORS 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ────────────────────────── 社交统计辅助 ──────────────────────────


def _post_counts(db: Session, post_ids: list[int]) -> dict[int, dict[str, int]]:
    """批量统计多篇文章的点赞数与评论数，返回 {post_id: {"likes": n, "comments": n}}"""
    if not post_ids:
        return {}
    like_rows = (
        db.query(Like.post_id, func.count(Like.id))
        .filter(Like.post_id.in_(post_ids))
        .group_by(Like.post_id)
        .all()
    )
    comment_rows = (
        db.query(Comment.post_id, func.count(Comment.id))
        .filter(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id)
        .all()
    )
    like_map = {pid: n for pid, n in like_rows}
    comment_map = {pid: n for pid, n in comment_rows}
    return {
        pid: {"likes": like_map.get(pid, 0), "comments": comment_map.get(pid, 0)}
        for pid in post_ids
    }


def _liked_post_ids(db: Session, user: User | None) -> set[int]:
    """当前用户已点赞的文章 ID 集合（未登录返回空集）"""
    if not user:
        return set()
    return {pid for (pid,) in db.query(Like.post_id).filter(Like.user_id == user.id).all()}


def _post_response(
    post: Post, counts: dict[int, dict[str, int]], liked_ids: set[int]
) -> PostResponse:
    """组装携带社交字段的 PostResponse"""
    c = counts.get(post.id, {"likes": 0, "comments": 0})
    return PostResponse(
        id=post.id,
        title=post.title,
        content=post.content,
        summary=post.summary,
        category=post.category,
        tags=post.tags,
        status=post.status,
        views=post.views,
        likes=c["likes"],
        comment_count=c["comments"],
        liked=post.id in liked_ids,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


# ────────────────────────── 前端页面 ──────────────────────────


@app.get("/")
def serve_index():
    """返回前端单页面"""
    return FileResponse(BASE_DIR / "index.html", media_type="text/html")


# ────────────────────────── 认证 / 用户 ──────────────────────────


@app.post("/api/auth/login", response_model=TokenResponse)
def login(login_in: LoginRequest, db: Session = Depends(database.get_db)):
    """用户名密码登录，校验通过后颁发 JWT"""
    user = db.query(User).filter(User.username == login_in.username).first()
    if not user or not security.verify_password(login_in.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenResponse(
        access_token=security.create_access_token(user),
        user=UserBrief(id=user.id, username=user.username, role=user.role),
    )


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(security.get_current_user)):
    """获取当前登录用户信息"""
    return current_user


@app.post("/api/users", response_model=UserResponse, status_code=201)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(database.get_db),
    _: User = Depends(security.require_admin),
):
    """管理员创建用户"""
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        username=user_in.username,
        password_hash=security.hash_password(user_in.password),
        role=user_in.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/users", response_model=list[UserResponse])
def get_users(
    db: Session = Depends(database.get_db),
    _: User = Depends(security.require_admin),
):
    """管理员获取用户列表"""
    return db.query(User).order_by(User.id).all()


# ────────────────────────── 文章 CRUD ──────────────────────────


@app.get("/api/posts", response_model=PaginatedPosts)
def get_posts(
    category: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(database.get_db),
    current_user: User | None = Depends(security.get_optional_user),
):
    """获取文章列表，支持分类/状态/关键词过滤 + Page & PageSize 分页"""
    query = db.query(Post)
    if category:
        query = query.filter(Post.category == category)
    # 隐私防线：非 admin（含未登录/reader）一律看不到草稿/非发布文章。
    # 未显式指定状态 → 只看已发布；显式请求其他状态（如 draft）→ 直接返回空集，杜绝探测
    if current_user is None or current_user.role != "admin":
        if status and status != "published":
            return PaginatedPosts(items=[], total=0, page=page, page_size=page_size)
        query = query.filter(Post.status == "published")
    elif status:
        query = query.filter(Post.status == status)
    if search:
        query = query.filter(
            Post.title.contains(search) | Post.content.contains(search)
        )
    total = query.count()
    posts = (
        query.order_by(Post.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    counts = _post_counts(db, [p.id for p in posts])
    liked_ids = _liked_post_ids(db, current_user)
    items = [_post_response(p, counts, liked_ids) for p in posts]
    return PaginatedPosts(items=items, total=total, page=page, page_size=page_size)


@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(
    post_id: int,
    increment_views: bool = Query(False),
    db: Session = Depends(database.get_db),
    current_user: User | None = Depends(security.get_optional_user),
):
    """获取文章详情，可选自增阅读量，携带点赞/评论计数与已点赞态"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")
    # 隐私防线：草稿/非发布文章仅 admin 可见，其他用户一律 404（避免探测文章存在性）
    if post.status != "published" and (
        current_user is None or current_user.role != "admin"
    ):
        raise HTTPException(status_code=404, detail="文章不存在")
    if increment_views:
        post.views += 1
        db.commit()
        db.refresh(post)
    counts = _post_counts(db, [post.id])
    liked_ids = _liked_post_ids(db, current_user)
    return _post_response(post, counts, liked_ids)


@app.post("/api/posts", response_model=PostResponse, status_code=201)
def create_post(
    post_in: PostCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    _: User = Depends(security.require_admin),
):
    """发布新文章（仅管理员）；summary 为空且 AI 可用时，后台自动生成摘要与标签"""
    post = Post(**post_in.model_dump())
    db.add(post)
    db.commit()
    db.refresh(post)
    _maybe_auto_enrich(background_tasks, post)
    return post


@app.put("/api/posts/{post_id}", response_model=PostResponse)
def update_post(
    post_id: int,
    post_in: PostUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    _: User = Depends(security.require_admin),
):
    """修改编辑文章（仅管理员）；summary 为空且 AI 可用时，后台自动生成摘要与标签"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")
    for field, value in post_in.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    db.commit()
    db.refresh(post)
    _maybe_auto_enrich(background_tasks, post)
    return post


@app.delete("/api/posts/{post_id}", status_code=204)
def delete_post(
    post_id: int,
    db: Session = Depends(database.get_db),
    _: User = Depends(security.require_admin),
):
    """删除文章（仅管理员），并级联清理其点赞与评论"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")
    # SQLite 默认未启用外键级联，手动清理社交数据
    db.query(Like).filter(Like.post_id == post_id).delete()
    db.query(Comment).filter(Comment.post_id == post_id).delete()
    db.delete(post)
    db.commit()


# ────────────────────────── 分类统计 ──────────────────────────


@app.get("/api/categories", response_model=list[CategoryStat])
def get_categories(db: Session = Depends(database.get_db)):
    """获取分类列表及文章数统计"""
    results = (
        db.query(Post.category, func.count(Post.id).label("count"))
        .group_by(Post.category)
        .all()
    )
    return [CategoryStat(category=r[0], count=r[1]) for r in results]


# ────────────────────────── 评论 ──────────────────────────


def _post_exists(db: Session, post_id: int) -> bool:
    return db.query(Post.id).filter(Post.id == post_id).first() is not None


@app.get("/api/posts/{post_id}/comments", response_model=PaginatedComments)
def get_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(database.get_db),
):
    """获取文章评论列表（分页，按时间升序 = 楼层顺序）"""
    if not _post_exists(db, post_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    query = (
        db.query(Comment, User.username)
        .join(User, Comment.user_id == User.id)
        .filter(Comment.post_id == post_id)
    )
    total = query.count()
    rows = (
        query.order_by(Comment.created_at.asc(), Comment.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        CommentResponse(
            id=c.id,
            post_id=c.post_id,
            user_id=c.user_id,
            username=username,
            content=c.content,
            created_at=c.created_at,
        )
        for c, username in rows
    ]
    return PaginatedComments(items=items, total=total, page=page, page_size=page_size)


@app.post("/api/posts/{post_id}/comments", response_model=CommentResponse, status_code=201)
def create_comment(
    post_id: int,
    comment_in: CommentCreate,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(security.get_current_user),
):
    """发表评论（需登录）"""
    if not _post_exists(db, post_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    comment = Comment(
        post_id=post_id, user_id=current_user.id, content=comment_in.content
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return CommentResponse(
        id=comment.id,
        post_id=comment.post_id,
        user_id=comment.user_id,
        username=current_user.username,
        content=comment.content,
        created_at=comment.created_at,
    )


@app.delete("/api/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: int,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(security.get_current_user),
):
    """删除评论：评论作者本人或 admin 可删"""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    if comment.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除他人评论")
    db.delete(comment)
    db.commit()


# ────────────────────────── 点赞 ──────────────────────────


@app.post("/api/posts/{post_id}/like", response_model=LikeResponse)
def like_post(
    post_id: int,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(security.get_current_user),
):
    """点赞文章（需登录，幂等：重复点赞不叠加计数）"""
    if not _post_exists(db, post_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    exists = (
        db.query(Like)
        .filter(Like.post_id == post_id, Like.user_id == current_user.id)
        .first()
    )
    if not exists:
        db.add(Like(post_id=post_id, user_id=current_user.id))
        db.commit()
    likes = db.query(func.count(Like.id)).filter(Like.post_id == post_id).scalar()
    return LikeResponse(liked=True, likes=likes)


@app.delete("/api/posts/{post_id}/like", response_model=LikeResponse)
def unlike_post(
    post_id: int,
    db: Session = Depends(database.get_db),
    current_user: User = Depends(security.get_current_user),
):
    """取消点赞（需登录，幂等）"""
    if not _post_exists(db, post_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    like = (
        db.query(Like)
        .filter(Like.post_id == post_id, Like.user_id == current_user.id)
        .first()
    )
    if like:
        db.delete(like)
        db.commit()
    likes = db.query(func.count(Like.id)).filter(Like.post_id == post_id).scalar()
    return LikeResponse(liked=False, likes=likes)


# ────────────────────────── AI 能力 ──────────────────────────


def _maybe_auto_enrich(background_tasks: BackgroundTasks, post: Post) -> None:
    """发布/更新后：若 summary 为空且 AI 可用，则后台异步生成摘要与标签"""
    if ai_service.ai_enabled() and not post.summary:
        background_tasks.add_task(_auto_enrich_post, post.id)


def _auto_enrich_post(post_id: int) -> None:
    """后台任务：为无摘要文章生成 100 字导读与标签（按字段独立回填，尊重人工输入）"""
    if not ai_service.ai_enabled():
        return
    try:
        with database.SessionLocal() as db:
            post = db.query(Post).filter(Post.id == post_id).first()
            if not post or (post.summary and post.tags):
                return
            result = ai_service.generate_all(post.title, post.content, post.category)
            changed = False
            if not post.summary and result.get("summary"):
                post.summary = str(result["summary"])[:200]
                changed = True
            if not post.tags and result.get("tags"):
                tags = ",".join(
                    str(t).strip() for t in result["tags"] if str(t).strip()
                )
                if tags:
                    post.tags = tags[:200]
                    changed = True
            if changed:
                db.commit()
    except Exception as exc:  # 记日志兜底，绝不影响发布/更新主流程
        print(f"[ai] 自动生成失败 post_id={post_id}: {exc}")


@app.get("/api/ai/status", response_model=AIStatusResponse)
def ai_status():
    """AI 能力可用状态（公开），前端据此显隐「✨ AI 灵感」面板"""
    return AIStatusResponse(
        enabled=ai_service.ai_enabled(),
        model=os.getenv("LLM_MODEL", ai_service.DEFAULT_MODEL),
        provider=ai_service.provider_name(),
    )


@app.post("/api/ai/generate", response_model=AIGenerateResponse)
def ai_generate(
    req: AIGenerateRequest,
    _: User = Depends(security.require_admin),
):
    """编辑器灵感副驾：一次性生成 摘要/标签/标题/分类 建议（仅 admin）"""
    if not ai_service.ai_enabled():
        raise HTTPException(status_code=503, detail="未配置 LLM_API_KEY，AI 能力不可用")
    try:
        result = ai_service.generate_all(req.title, req.content, req.category)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{exc}") from exc
    return AIGenerateResponse(
        summary=str(result.get("summary", "")),
        tags=[str(t) for t in result.get("tags", [])],
        title_suggestion=str(result.get("title_suggestion", "")),
        category_suggestion=str(result.get("category_suggestion", "")),
    )


@app.post("/api/ai/backfill", response_model=BackfillResponse)
def ai_backfill(
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(security.require_admin),
):
    """存量批量回填：对无摘要的旧文章逐篇生成摘要与标签（幂等，仅 admin）"""
    if not ai_service.ai_enabled():
        raise HTTPException(status_code=503, detail="未配置 LLM_API_KEY，AI 能力不可用")
    with database.SessionLocal() as db:
        candidates = (
            db.query(Post)
            .filter(Post.summary == "")
            .order_by(Post.id.asc())
            .limit(limit)
            .all()
        )
        total = len(candidates)
        processed = 0
        updated = 0
        failed = 0
        for post in candidates:
            processed += 1
            try:
                result = ai_service.generate_all(
                    post.title, post.content, post.category
                )
                changed = False
                if not post.summary and result.get("summary"):
                    post.summary = str(result["summary"])[:200]
                    changed = True
                if not post.tags and result.get("tags"):
                    tags = ",".join(
                        str(t).strip() for t in result["tags"] if str(t).strip()
                    )
                    if tags:
                        post.tags = tags[:200]
                        changed = True
                if changed:
                    db.commit()
                    updated += 1
            except Exception:
                failed += 1
        return BackfillResponse(
            total=total, processed=processed, updated=updated, failed=failed
        )
