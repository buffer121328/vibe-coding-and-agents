from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ────────────────── 认证 / 用户 ──────────────────


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class UserBrief(BaseModel):
    id: int
    username: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBrief


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    role: Literal["admin", "reader"] = "reader"


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ────────────────── 文章 ──────────────────


class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    summary: str = ""  # 可选：人工预填导读；留空则发布后由 AI 后台生成
    category: str = "默认分类"
    tags: str = ""
    status: str = "published"


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    summary: str = ""  # AI 100 字导读，未生成为空串
    category: str
    tags: str
    status: str
    views: int
    likes: int = 0
    comment_count: int = 0
    liked: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryStat(BaseModel):
    category: str
    count: int


# ────────────────── 评论 ──────────────────


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class CommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    username: str
    content: str
    created_at: datetime


# ────────────────── 点赞 ──────────────────


class LikeResponse(BaseModel):
    liked: bool
    likes: int


# ────────────────── 分页 ──────────────────


class PaginatedPosts(BaseModel):
    items: list[PostResponse]
    total: int
    page: int
    page_size: int


class PaginatedComments(BaseModel):
    items: list[CommentResponse]
    total: int
    page: int
    page_size: int


# ────────────────── AI 能力 ──────────────────


class AIGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    category: str = ""


class AIGenerateResponse(BaseModel):
    summary: str
    tags: list[str]
    title_suggestion: str
    category_suggestion: str


class AIStatusResponse(BaseModel):
    enabled: bool
    model: str
    provider: str


class BackfillResponse(BaseModel):
    total: int      # 扫描到的无摘要文章数
    processed: int  # 本次实际尝试生成数（受 limit 截断）
    updated: int    # 成功落库数
    failed: int     # 失败数（仅记日志，不中断）
