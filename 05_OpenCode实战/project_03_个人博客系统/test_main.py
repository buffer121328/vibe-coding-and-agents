"""博客系统 API 验收测试"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base

# 测试用内存数据库 —— StaticPool 确保所有连接共享同一 DB
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_db():
    """每个测试前重建数据库"""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="session")
def client():
    """创建测试客户端，patch 数据库为内存引擎"""
    import database

    database.engine = test_engine
    database.SessionLocal = TestSessionLocal

    from main import app

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ────────────────── 创建文章 ──────────────────


def test_create_post_success(client):
    resp = client.post(
        "/api/posts",
        json={"title": "测试标题", "content": "测试内容"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试标题"
    assert data["content"] == "测试内容"
    assert data["category"] == "默认分类"
    assert data["status"] == "published"
    assert data["views"] == 0
    assert "id" in data
    assert "created_at" in data


def test_create_post_with_all_fields(client):
    resp = client.post(
        "/api/posts",
        json={
            "title": "Python入门",
            "content": "# Hello\nPython真好用",
            "category": "Python",
            "tags": "Python,入门",
            "status": "draft",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "Python"
    assert data["tags"] == "Python,入门"
    assert data["status"] == "draft"


def test_create_post_missing_title(client):
    resp = client.post("/api/posts", json={"content": "内容"})
    assert resp.status_code == 422


def test_create_post_empty_title(client):
    resp = client.post("/api/posts", json={"title": "", "content": "内容"})
    assert resp.status_code == 422


def test_create_post_missing_content(client):
    resp = client.post("/api/posts", json={"title": "标题"})
    assert resp.status_code == 422


def test_create_post_empty_content(client):
    resp = client.post("/api/posts", json={"title": "标题", "content": ""})
    assert resp.status_code == 422


# ────────────────── 获取列表 ──────────────────


def test_get_posts_empty(client):
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_posts_list(client):
    client.post("/api/posts", json={"title": "文章1", "content": "内容1"})
    client.post("/api/posts", json={"title": "文章2", "content": "内容2"})
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_posts_filter_category(client):
    client.post(
        "/api/posts",
        json={"title": "Py", "content": "c", "category": "Python"},
    )
    client.post(
        "/api/posts",
        json={"title": "JS", "content": "c", "category": "JavaScript"},
    )
    resp = client.get("/api/posts?category=Python")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["category"] == "Python"


def test_get_posts_filter_status(client):
    client.post(
        "/api/posts", json={"title": "t", "content": "c", "status": "draft"}
    )
    client.post(
        "/api/posts", json={"title": "t", "content": "c", "status": "published"}
    )
    resp = client.get("/api/posts?status=draft")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "draft"


def test_get_posts_search(client):
    client.post("/api/posts", json={"title": "FastAPI教程", "content": "内容"})
    client.post("/api/posts", json={"title": "Python笔记", "content": "内容"})
    resp = client.get("/api/posts?search=FastAPI")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ────────────────── 获取详情 ──────────────────


def test_get_post_detail(client):
    create_resp = client.post(
        "/api/posts", json={"title": "标题", "content": "内容"}
    )
    post_id = create_resp.json()["id"]
    resp = client.get(f"/api/posts/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "标题"


def test_get_post_not_found(client):
    resp = client.get("/api/posts/9999")
    assert resp.status_code == 404


def test_get_post_increment_views(client):
    create_resp = client.post(
        "/api/posts", json={"title": "标题", "content": "内容"}
    )
    post_id = create_resp.json()["id"]
    # 首次请求不自增
    resp1 = client.get(f"/api/posts/{post_id}")
    assert resp1.json()["views"] == 0
    # 带 increment_views 自增
    resp2 = client.get(f"/api/posts/{post_id}?increment_views=true")
    assert resp2.json()["views"] == 1
    # 再次自增
    resp3 = client.get(f"/api/posts/{post_id}?increment_views=true")
    assert resp3.json()["views"] == 2


# ────────────────── 编辑文章 ──────────────────


def test_update_post(client):
    create_resp = client.post(
        "/api/posts", json={"title": "原标题", "content": "原内容"}
    )
    post_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/posts/{post_id}",
        json={"title": "新标题", "content": "新内容"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "新标题"
    assert resp.json()["content"] == "新内容"


def test_update_post_partial(client):
    create_resp = client.post(
        "/api/posts", json={"title": "原标题", "content": "原内容"}
    )
    post_id = create_resp.json()["id"]
    resp = client.put(f"/api/posts/{post_id}", json={"title": "只改标题"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "只改标题"
    assert resp.json()["content"] == "原内容"


def test_update_post_not_found(client):
    resp = client.put("/api/posts/9999", json={"title": "x"})
    assert resp.status_code == 404


# ────────────────── 删除文章 ──────────────────


def test_delete_post(client):
    create_resp = client.post(
        "/api/posts", json={"title": "标题", "content": "内容"}
    )
    post_id = create_resp.json()["id"]
    resp = client.delete(f"/api/posts/{post_id}")
    assert resp.status_code == 204
    # 确认已删除
    resp2 = client.get(f"/api/posts/{post_id}")
    assert resp2.status_code == 404


def test_delete_post_not_found(client):
    resp = client.delete("/api/posts/9999")
    assert resp.status_code == 404


# ────────────────── 分类统计 ──────────────────


def test_get_categories_empty(client):
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_categories(client):
    client.post(
        "/api/posts",
        json={"title": "t", "content": "c", "category": "Python"},
    )
    client.post(
        "/api/posts",
        json={"title": "t", "content": "c", "category": "Python"},
    )
    client.post(
        "/api/posts",
        json={"title": "t", "content": "c", "category": "JavaScript"},
    )
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # 检查统计数量
    py_cat = next(c for c in data if c["category"] == "Python")
    js_cat = next(c for c in data if c["category"] == "JavaScript")
    assert py_cat["count"] == 2
    assert js_cat["count"] == 1
