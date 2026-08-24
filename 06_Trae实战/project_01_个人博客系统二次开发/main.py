from contextlib import asynccontextmanager
from pathlib import Path

import database
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Base, Post
from schemas import CategoryStat, PostCreate, PostResponse, PostUpdate

# 项目根目录（index.html 所在位置）
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时自动建表"""
    Base.metadata.create_all(bind=database.engine)
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


# ────────────────────────── 前端页面 ──────────────────────────


@app.get("/")
def serve_index():
    """返回前端单页面"""
    return FileResponse(BASE_DIR / "index.html", media_type="text/html")


# ────────────────────────── 文章 CRUD ──────────────────────────


@app.get("/api/posts", response_model=list[PostResponse])
def get_posts(
    category: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(database.get_db),
):
    """获取文章列表，支持分类/状态/关键词过滤"""
    query = db.query(Post)
    if category:
        query = query.filter(Post.category == category)
    if status:
        query = query.filter(Post.status == status)
    if search:
        query = query.filter(
            Post.title.contains(search) | Post.content.contains(search)
        )
    return query.order_by(Post.created_at.desc()).all()


@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(
    post_id: int,
    increment_views: bool = Query(False),
    db: Session = Depends(database.get_db),
):
    """获取文章详情，可选自增阅读量"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")
    if increment_views:
        post.views += 1
        db.commit()
        db.refresh(post)
    return post


@app.post("/api/posts", response_model=PostResponse, status_code=201)
def create_post(post_in: PostCreate, db: Session = Depends(database.get_db)):
    """发布新文章"""
    post = Post(**post_in.model_dump())
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@app.put("/api/posts/{post_id}", response_model=PostResponse)
def update_post(
    post_id: int, post_in: PostUpdate, db: Session = Depends(database.get_db)
):
    """修改编辑文章"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")
    for field, value in post_in.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    db.commit()
    db.refresh(post)
    return post


@app.delete("/api/posts/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(database.get_db)):
    """删除文章"""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")
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
