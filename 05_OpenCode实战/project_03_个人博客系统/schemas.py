from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    category: str = "默认分类"
    tags: str = ""
    status: str = "published"


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    category: str
    tags: str
    status: str
    views: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryStat(BaseModel):
    category: str
    count: int
