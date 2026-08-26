"""博客系统 API 验收测试"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import ai_service
from models import Base, Post

# 测试用内存数据库 —— StaticPool 确保所有连接共享同一 DB
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """每个测试前重建数据库并种子化管理员（保证可登录）

    默认删除 LLM_API_KEY，使 AI 能力默认禁用、既有用例完全隔离；
    AI 用例内部再通过 setenv + stub 显式开启。
    """
    from main import seed_admin

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    seed_admin(db)
    db.close()
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


# ────────────────── 认证辅助 ──────────────────


def admin_headers(client):
    """以种子管理员登录，返回携带 Authorization 的请求头"""
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def reader_headers(client):
    """创建一个 reader 用户并登录，返回携带 Authorization 的请求头"""
    resp = client.post(
        "/api/users",
        json={"username": "reader1", "password": "reader123", "role": "reader"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "reader1", "password": "reader123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ────────────────── 认证：登录 ──────────────────


def test_login_success(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"


def test_login_wrong_password(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-pass"},
    )
    assert resp.status_code == 401


def test_login_user_not_found(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "whatever1"},
    )
    assert resp.status_code == 401


def test_login_missing_fields(client):
    resp = client.post("/api/auth/login", json={"username": "admin"})
    assert resp.status_code == 422


# ────────────────── 认证：当前用户 ──────────────────


def test_me_with_token(client):
    resp = client.get("/api/auth/me", headers=admin_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"
    assert "password_hash" not in data


def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_invalid_token(client):
    resp = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert resp.status_code == 401


# ────────────────── 写接口权限隔离 ──────────────────


def test_create_post_unauthorized(client):
    resp = client.post("/api/posts", json={"title": "t", "content": "c"})
    assert resp.status_code == 401


def test_create_post_reader_forbidden(client):
    resp = client.post(
        "/api/posts",
        json={"title": "t", "content": "c"},
        headers=reader_headers(client),
    )
    assert resp.status_code == 403


def test_update_post_unauthorized(client):
    create_resp = client.post(
        "/api/posts", json={"title": "t", "content": "c"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    resp = client.put(f"/api/posts/{post_id}", json={"title": "x"})
    assert resp.status_code == 401


def test_update_post_reader_forbidden(client):
    create_resp = client.post(
        "/api/posts", json={"title": "t", "content": "c"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/posts/{post_id}", json={"title": "x"}, headers=reader_headers(client)
    )
    assert resp.status_code == 403


def test_delete_post_unauthorized(client):
    create_resp = client.post(
        "/api/posts", json={"title": "t", "content": "c"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    resp = client.delete(f"/api/posts/{post_id}")
    assert resp.status_code == 401


def test_delete_post_reader_forbidden(client):
    create_resp = client.post(
        "/api/posts", json={"title": "t", "content": "c"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    resp = client.delete(f"/api/posts/{post_id}", headers=reader_headers(client))
    assert resp.status_code == 403


# ────────────────── 用户管理（仅 admin） ──────────────────


def test_create_user_success(client):
    resp = client.post(
        "/api/users",
        json={"username": "alice", "password": "alice123", "role": "reader"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["role"] == "reader"
    assert "password_hash" not in data


def test_create_user_duplicate_username(client):
    resp = client.post(
        "/api/users",
        json={"username": "admin", "password": "whatever1", "role": "reader"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 409


def test_create_user_invalid_role(client):
    resp = client.post(
        "/api/users",
        json={"username": "bob", "password": "bob123", "role": "superuser"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 422


def test_create_user_unauthorized(client):
    resp = client.post(
        "/api/users",
        json={"username": "bob", "password": "bob123", "role": "reader"},
    )
    assert resp.status_code == 401


def test_create_user_reader_forbidden(client):
    resp = client.post(
        "/api/users",
        json={"username": "bob", "password": "bob123", "role": "reader"},
        headers=reader_headers(client),
    )
    assert resp.status_code == 403


def test_get_users_admin(client):
    resp = client.get("/api/users", headers=admin_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert any(u["username"] == "admin" for u in data)


def test_get_users_unauthorized(client):
    resp = client.get("/api/users")
    assert resp.status_code == 401


def test_get_users_reader_forbidden(client):
    resp = client.get("/api/users", headers=reader_headers(client))
    assert resp.status_code == 403


# ────────────────── 创建文章 ──────────────────


def test_create_post_success(client):
    resp = client.post(
        "/api/posts",
        json={"title": "测试标题", "content": "测试内容"},
        headers=admin_headers(client),
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
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "Python"
    assert data["tags"] == "Python,入门"
    assert data["status"] == "draft"


def test_create_post_missing_title(client):
    resp = client.post(
        "/api/posts", json={"content": "内容"}, headers=admin_headers(client)
    )
    assert resp.status_code == 422


def test_create_post_empty_title(client):
    resp = client.post(
        "/api/posts", json={"title": "", "content": "内容"}, headers=admin_headers(client)
    )
    assert resp.status_code == 422


def test_create_post_missing_content(client):
    resp = client.post(
        "/api/posts", json={"title": "标题"}, headers=admin_headers(client)
    )
    assert resp.status_code == 422


def test_create_post_empty_content(client):
    resp = client.post(
        "/api/posts", json={"title": "标题", "content": ""}, headers=admin_headers(client)
    )
    assert resp.status_code == 422


# ────────────────── 获取列表 ──────────────────


def test_get_posts_empty(client):
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_get_posts_list(client):
    client.post(
        "/api/posts", json={"title": "文章1", "content": "内容1"}, headers=admin_headers(client)
    )
    client.post(
        "/api/posts", json={"title": "文章2", "content": "内容2"}, headers=admin_headers(client)
    )
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_get_posts_filter_category(client):
    client.post(
        "/api/posts",
        json={"title": "Py", "content": "c", "category": "Python"},
        headers=admin_headers(client),
    )
    client.post(
        "/api/posts",
        json={"title": "JS", "content": "c", "category": "JavaScript"},
        headers=admin_headers(client),
    )
    resp = client.get("/api/posts?category=Python")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["category"] == "Python"


def test_get_posts_filter_status(client):
    # 注意：按状态过滤仅对 admin 生效（草稿对非 admin 保密）
    client.post(
        "/api/posts", json={"title": "t", "content": "c", "status": "draft"}, headers=admin_headers(client)
    )
    client.post(
        "/api/posts", json={"title": "t", "content": "c", "status": "published"}, headers=admin_headers(client)
    )
    resp = client.get("/api/posts?status=draft", headers=admin_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "draft"


def test_get_posts_search(client):
    client.post(
        "/api/posts", json={"title": "FastAPI教程", "content": "内容"}, headers=admin_headers(client)
    )
    client.post(
        "/api/posts", json={"title": "Python笔记", "content": "内容"}, headers=admin_headers(client)
    )
    resp = client.get("/api/posts?search=FastAPI")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


# ────────────────── 分页 ──────────────────


def test_get_posts_pagination(client):
    for i in range(5):
        client.post(
            "/api/posts",
            json={"title": f"文章{i}", "content": "内容"},
            headers=admin_headers(client),
        )
    resp = client.get("/api/posts?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2
    # 第二页
    resp2 = client.get("/api/posts?page=3&page_size=2")
    data2 = resp2.json()
    assert data2["total"] == 5
    assert data2["page"] == 3
    assert len(data2["items"]) == 1


def test_get_posts_invalid_page(client):
    resp = client.get("/api/posts?page=0")
    assert resp.status_code == 422


def test_get_posts_invalid_page_size(client):
    resp = client.get("/api/posts?page_size=0")
    assert resp.status_code == 422
    resp2 = client.get("/api/posts?page_size=100")
    assert resp2.status_code == 422


# ────────────────── 获取详情 ──────────────────


def test_get_post_detail(client):
    create_resp = client.post(
        "/api/posts", json={"title": "标题", "content": "内容"}, headers=admin_headers(client)
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
        "/api/posts", json={"title": "标题", "content": "内容"}, headers=admin_headers(client)
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


# ────────────────── 草稿隐私隔离（draft privacy） ──────────────────


def test_public_list_hides_drafts(client):
    """未登录访客的公开列表：草稿不可见"""
    client.post(
        "/api/posts", json={"title": "公开文章", "content": "c"}, headers=admin_headers(client)
    )
    client.post(
        "/api/posts",
        json={"title": "私密草稿", "content": "隐私内容", "status": "draft"},
        headers=admin_headers(client),
    )
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "公开文章"


def test_public_list_status_draft_cannot_bypass(client):
    """未登录访客即使显式传 status=draft 也拿不到草稿（无法绕过）"""
    client.post(
        "/api/posts",
        json={"title": "私密草稿", "content": "隐私内容", "status": "draft"},
        headers=admin_headers(client),
    )
    resp = client.get("/api/posts?status=draft")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_reader_list_hides_drafts(client):
    """普通登录用户同样看不到草稿"""
    client.post(
        "/api/posts",
        json={"title": "私密草稿", "content": "隐私内容", "status": "draft"},
        headers=admin_headers(client),
    )
    resp = client.get("/api/posts", headers=reader_headers(client))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_admin_list_sees_drafts(client):
    """管理员可以查看（并过滤）草稿"""
    client.post(
        "/api/posts",
        json={"title": "私密草稿", "content": "隐私内容", "status": "draft"},
        headers=admin_headers(client),
    )
    resp = client.get("/api/posts?status=draft", headers=admin_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "draft"


def test_public_detail_draft_404(client):
    """未登录访客直接访问草稿详情 → 404（不暴露存在性）"""
    create_resp = client.post(
        "/api/posts",
        json={"title": "私密草稿", "content": "隐私内容", "status": "draft"},
        headers=admin_headers(client),
    )
    draft_id = create_resp.json()["id"]
    resp = client.get(f"/api/posts/{draft_id}")
    assert resp.status_code == 404


def test_reader_detail_draft_404(client):
    """普通用户访问草稿详情 → 404"""
    create_resp = client.post(
        "/api/posts",
        json={"title": "私密草稿", "content": "隐私内容", "status": "draft"},
        headers=admin_headers(client),
    )
    draft_id = create_resp.json()["id"]
    resp = client.get(f"/api/posts/{draft_id}", headers=reader_headers(client))
    assert resp.status_code == 404


def test_admin_detail_draft_ok(client):
    """管理员可以读取草稿详情"""
    create_resp = client.post(
        "/api/posts",
        json={"title": "私密草稿", "content": "隐私内容", "status": "draft"},
        headers=admin_headers(client),
    )
    draft_id = create_resp.json()["id"]
    resp = client.get(f"/api/posts/{draft_id}", headers=admin_headers(client))
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


# ────────────────── 编辑文章 ──────────────────


def test_update_post(client):
    create_resp = client.post(
        "/api/posts", json={"title": "原标题", "content": "原内容"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/posts/{post_id}",
        json={"title": "新标题", "content": "新内容"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "新标题"
    assert resp.json()["content"] == "新内容"


def test_update_post_partial(client):
    create_resp = client.post(
        "/api/posts", json={"title": "原标题", "content": "原内容"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/posts/{post_id}", json={"title": "只改标题"}, headers=admin_headers(client)
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "只改标题"
    assert resp.json()["content"] == "原内容"


def test_update_post_not_found(client):
    resp = client.put(
        "/api/posts/9999", json={"title": "x"}, headers=admin_headers(client)
    )
    assert resp.status_code == 404


# ────────────────── 删除文章 ──────────────────


def test_delete_post(client):
    create_resp = client.post(
        "/api/posts", json={"title": "标题", "content": "内容"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    resp = client.delete(f"/api/posts/{post_id}", headers=admin_headers(client))
    assert resp.status_code == 204
    # 确认已删除
    resp2 = client.get(f"/api/posts/{post_id}")
    assert resp2.status_code == 404


def test_delete_post_not_found(client):
    resp = client.delete("/api/posts/9999", headers=admin_headers(client))
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
        headers=admin_headers(client),
    )
    client.post(
        "/api/posts",
        json={"title": "t", "content": "c", "category": "Python"},
        headers=admin_headers(client),
    )
    client.post(
        "/api/posts",
        json={"title": "t", "content": "c", "category": "JavaScript"},
        headers=admin_headers(client),
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


# ────────────────── 社交辅助 ──────────────────


def _create_post(client, title="测试文章", content="内容", **kwargs):
    """管理员创建一篇测试文章并返回 id"""
    resp = client.post(
        "/api/posts",
        json={"title": title, "content": content, **kwargs},
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def other_reader_headers(client):
    """创建第二个 reader 用户并登录，用于他人越权测试"""
    resp = client.post(
        "/api/users",
        json={"username": "reader2", "password": "reader123", "role": "reader"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "reader2", "password": "reader123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ────────────────── 评论 ──────────────────


def test_create_comment_success(client):
    post_id = _create_post(client)
    resp = client.post(
        f"/api/posts/{post_id}/comments",
        json={"content": "好文！"},
        headers=reader_headers(client),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["post_id"] == post_id
    assert data["content"] == "好文！"
    assert data["username"] == "reader1"
    assert "created_at" in data


def test_create_comment_unauthenticated(client):
    post_id = _create_post(client)
    resp = client.post(f"/api/posts/{post_id}/comments", json={"content": "x"})
    assert resp.status_code == 401


def test_create_comment_empty(client):
    post_id = _create_post(client)
    resp = client.post(
        f"/api/posts/{post_id}/comments",
        json={"content": ""},
        headers=reader_headers(client),
    )
    assert resp.status_code == 422


def test_create_comment_post_not_found(client):
    resp = client.post(
        "/api/posts/9999/comments",
        json={"content": "x"},
        headers=reader_headers(client),
    )
    assert resp.status_code == 404


def test_get_comments_empty(client):
    post_id = _create_post(client)
    resp = client.get(f"/api/posts/{post_id}/comments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_get_comments_list_asc(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    client.post(f"/api/posts/{post_id}/comments", json={"content": "一楼"}, headers=h)
    client.post(f"/api/posts/{post_id}/comments", json={"content": "二楼"}, headers=h)
    resp = client.get(f"/api/posts/{post_id}/comments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    # 楼层升序：最早评论在前
    assert [c["content"] for c in data["items"]] == ["一楼", "二楼"]
    assert data["items"][0]["username"] == "reader1"


def test_get_comments_pagination(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    for i in range(3):
        client.post(
            f"/api/posts/{post_id}/comments",
            json={"content": f"评论{i}"},
            headers=h,
        )
    resp = client.get(f"/api/posts/{post_id}/comments?page=2&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["page"] == 2
    assert len(data["items"]) == 1


def test_get_comments_invalid_page(client):
    post_id = _create_post(client)
    resp = client.get(f"/api/posts/{post_id}/comments?page=0")
    assert resp.status_code == 422


def test_get_comments_post_not_found(client):
    resp = client.get("/api/posts/9999/comments")
    assert resp.status_code == 404


def test_delete_comment_owner(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    create_resp = client.post(
        f"/api/posts/{post_id}/comments", json={"content": "x"}, headers=h
    )
    comment_id = create_resp.json()["id"]
    resp = client.delete(f"/api/comments/{comment_id}", headers=h)
    assert resp.status_code == 204
    assert client.get(f"/api/posts/{post_id}/comments").json()["total"] == 0


def test_delete_comment_admin(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    create_resp = client.post(
        f"/api/posts/{post_id}/comments", json={"content": "x"}, headers=h
    )
    comment_id = create_resp.json()["id"]
    resp = client.delete(f"/api/comments/{comment_id}", headers=admin_headers(client))
    assert resp.status_code == 204


def test_delete_comment_other_user_forbidden(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    create_resp = client.post(
        f"/api/posts/{post_id}/comments", json={"content": "x"}, headers=h
    )
    comment_id = create_resp.json()["id"]
    resp = client.delete(f"/api/comments/{comment_id}", headers=other_reader_headers(client))
    assert resp.status_code == 403


def test_delete_comment_unauthenticated(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    create_resp = client.post(
        f"/api/posts/{post_id}/comments", json={"content": "x"}, headers=h
    )
    comment_id = create_resp.json()["id"]
    resp = client.delete(f"/api/comments/{comment_id}")
    assert resp.status_code == 401


def test_delete_comment_not_found(client):
    resp = client.delete("/api/comments/9999", headers=admin_headers(client))
    assert resp.status_code == 404


# ────────────────── 点赞 ──────────────────


def test_like_post(client):
    post_id = _create_post(client)
    resp = client.post(f"/api/posts/{post_id}/like", headers=reader_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert data["liked"] is True
    assert data["likes"] == 1


def test_like_post_idempotent(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    client.post(f"/api/posts/{post_id}/like", headers=h)
    resp2 = client.post(f"/api/posts/{post_id}/like", headers=h)
    assert resp2.status_code == 200
    assert resp2.json()["liked"] is True
    assert resp2.json()["likes"] == 1  # 防刷：重复点赞不叠加


def test_like_post_unauthenticated(client):
    post_id = _create_post(client)
    resp = client.post(f"/api/posts/{post_id}/like")
    assert resp.status_code == 401


def test_like_post_not_found(client):
    resp = client.post("/api/posts/9999/like", headers=reader_headers(client))
    assert resp.status_code == 404


def test_unlike_post(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    client.post(f"/api/posts/{post_id}/like", headers=h)
    resp = client.delete(f"/api/posts/{post_id}/like", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["liked"] is False
    assert data["likes"] == 0


def test_unlike_post_not_liked_idempotent(client):
    post_id = _create_post(client)
    resp = client.delete(f"/api/posts/{post_id}/like", headers=reader_headers(client))
    assert resp.status_code == 200
    assert resp.json()["liked"] is False
    assert resp.json()["likes"] == 0


def test_unlike_post_unauthenticated(client):
    post_id = _create_post(client)
    resp = client.delete(f"/api/posts/{post_id}/like")
    assert resp.status_code == 401


def test_unlike_post_not_found(client):
    resp = client.delete("/api/posts/9999/like", headers=reader_headers(client))
    assert resp.status_code == 404


# ────────────────── 社交计数 ──────────────────


def test_post_detail_social_counts(client):
    post_id = _create_post(client)
    h = reader_headers(client)
    client.post(f"/api/posts/{post_id}/like", headers=h)
    client.post(f"/api/posts/{post_id}/comments", json={"content": "顶"}, headers=h)
    resp = client.get(f"/api/posts/{post_id}", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["likes"] == 1
    assert data["comment_count"] == 1
    assert data["liked"] is True


def test_post_detail_liked_false_when_anonymous(client):
    post_id = _create_post(client)
    resp = client.get(f"/api/posts/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["liked"] is False


def test_post_list_social_counts(client):
    post_id = _create_post(client)
    client.post(f"/api/posts/{post_id}/like", headers=reader_headers(client))
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["likes"] == 1
    assert item["comment_count"] == 0
    assert item["liked"] is False


# ────────────────── 级联清理 ──────────────────


def test_delete_post_cascades_social_data(client):
    from models import Comment, Like

    post_id = _create_post(client)
    h = reader_headers(client)
    client.post(f"/api/posts/{post_id}/like", headers=h)
    client.post(f"/api/posts/{post_id}/comments", json={"content": "x"}, headers=h)
    resp = client.delete(f"/api/posts/{post_id}", headers=admin_headers(client))
    assert resp.status_code == 204
    # 数据库层验证：点赞与评论一并清除
    db = TestSessionLocal()
    try:
        assert db.query(Comment).filter(Comment.post_id == post_id).count() == 0
        assert db.query(Like).filter(Like.post_id == post_id).count() == 0
    finally:
        db.close()


# ────────────────── AI 能力 ──────────────────


def _enable_ai(monkeypatch):
    """开启 AI 能力，并用确定性 stub 替换 LLM 调用（不消耗真实 token）"""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_service,
        "_chat_json",
        lambda system, user: {
            "summary": "这是一段 AI 生成的 100 字导读。",
            "tags": ["Python", "FastAPI"],
            "title_suggestion": "更吸引人的标题",
            "category_suggestion": "技术",
        },
    )


def test_ai_status_enabled(client, monkeypatch):
    _enable_ai(monkeypatch)
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["model"]
    assert data["provider"]


def test_ai_status_disabled(client):
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_ai_generate_success(client, monkeypatch):
    _enable_ai(monkeypatch)
    resp = client.post(
        "/api/ai/generate",
        json={"title": "测试", "content": "正文内容", "category": "技术"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "100 字导读" in data["summary"]
    assert data["tags"] == ["Python", "FastAPI"]
    assert data["title_suggestion"] == "更吸引人的标题"
    assert data["category_suggestion"] == "技术"


def test_ai_generate_unauthorized(client, monkeypatch):
    _enable_ai(monkeypatch)
    resp = client.post("/api/ai/generate", json={"title": "t", "content": "c"})
    assert resp.status_code == 401


def test_ai_generate_reader_forbidden(client, monkeypatch):
    _enable_ai(monkeypatch)
    resp = client.post(
        "/api/ai/generate",
        json={"title": "t", "content": "c"},
        headers=reader_headers(client),
    )
    assert resp.status_code == 403


def test_ai_generate_missing_fields(client, monkeypatch):
    _enable_ai(monkeypatch)
    resp = client.post(
        "/api/ai/generate", json={"title": "t"}, headers=admin_headers(client)
    )
    assert resp.status_code == 422


def test_ai_generate_disabled(client):
    resp = client.post(
        "/api/ai/generate",
        json={"title": "t", "content": "c"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 503


def test_ai_generate_llm_failure(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def boom(system, user):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(ai_service, "_chat_json", boom)
    resp = client.post(
        "/api/ai/generate",
        json={"title": "t", "content": "c"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 502


def test_publish_auto_enrich(client, monkeypatch):
    """发布空 summary 文章 → 后台自动生成摘要与标签落库"""
    _enable_ai(monkeypatch)
    resp = client.post(
        "/api/posts",
        json={"title": "AI 教程", "content": "本文讲解 FastAPI 与 AI 的结合。"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]
    db = TestSessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        assert post.summary == "这是一段 AI 生成的 100 字导读。"
        assert post.tags == "Python,FastAPI"
    finally:
        db.close()


def test_publish_respects_manual_summary(client, monkeypatch):
    """人工预填 summary/tags 时，自动生成绝不覆盖"""
    _enable_ai(monkeypatch)
    resp = client.post(
        "/api/posts",
        json={
            "title": "t",
            "content": "c",
            "summary": "人工写的导读",
            "tags": "手工标签",
        },
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]
    db = TestSessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        assert post.summary == "人工写的导读"
        assert post.tags == "手工标签"
    finally:
        db.close()


def test_publish_no_ai_degrades_gracefully(client):
    """未配置 key 时发布不报错、summary 保持空串（优雅降级）"""
    resp = client.post(
        "/api/posts",
        json={"title": "t", "content": "c"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 201
    assert resp.json()["summary"] == ""


def test_update_triggers_auto_enrich_when_summary_empty(client, monkeypatch):
    """AI 禁用时创建（summary 空），后启用 AI 再更新 → 后台补齐摘要"""
    create_resp = client.post(
        "/api/posts", json={"title": "t", "content": "c"}, headers=admin_headers(client)
    )
    post_id = create_resp.json()["id"]
    _enable_ai(monkeypatch)
    resp = client.put(
        f"/api/posts/{post_id}",
        json={"content": "更新后的正文"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    db = TestSessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        assert post.summary == "这是一段 AI 生成的 100 字导读。"
    finally:
        db.close()


def test_backfill_fills_empty_summary_posts(client, monkeypatch):
    """批量回填只处理无摘要文章，全部落库"""
    for i in range(3):
        client.post(
            "/api/posts",
            json={"title": f"旧文章{i}", "content": "旧正文"},
            headers=admin_headers(client),
        )
    _enable_ai(monkeypatch)
    resp = client.post("/api/ai/backfill", headers=admin_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["processed"] == 3
    assert data["updated"] == 3
    assert data["failed"] == 0
    db = TestSessionLocal()
    try:
        assert db.query(Post).filter(Post.summary == "").count() == 0
    finally:
        db.close()


def test_backfill_limit(client, monkeypatch):
    for i in range(3):
        client.post(
            "/api/posts",
            json={"title": f"旧文章{i}", "content": "旧正文"},
            headers=admin_headers(client),
        )
    _enable_ai(monkeypatch)
    resp = client.post("/api/ai/backfill?limit=1", headers=admin_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["processed"] == 1
    assert data["updated"] == 1


def test_backfill_idempotent(client, monkeypatch):
    client.post(
        "/api/posts", json={"title": "t", "content": "c"}, headers=admin_headers(client)
    )
    _enable_ai(monkeypatch)
    client.post("/api/ai/backfill", headers=admin_headers(client))
    resp2 = client.post("/api/ai/backfill", headers=admin_headers(client))
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["total"] == 0
    assert data["updated"] == 0


def test_backfill_disabled(client):
    resp = client.post("/api/ai/backfill", headers=admin_headers(client))
    assert resp.status_code == 503


def test_backfill_unauthorized(client, monkeypatch):
    _enable_ai(monkeypatch)
    resp = client.post("/api/ai/backfill")
    assert resp.status_code == 401
