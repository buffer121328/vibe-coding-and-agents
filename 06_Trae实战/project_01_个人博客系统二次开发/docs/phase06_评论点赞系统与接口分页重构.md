# 阶段六：评论与点赞社交系统 + 接口分页重构 — 实施方案

## 一、概述（Summary）

在「个人博客系统」（FastAPI + SQLite + SQLAlchemy 2.0 + 单文件 HTML 前端 + JWT 角色权限隔离）基础上，实现**社交互动与性能重构**：

- 新增 `comments` 表（文章 ↔ 评论 **一对多**关联）与 `likes` 表（文章 ↔ 用户，**点赞去重防刷**）
- 新增评论接口：发表 / 列表（分页、按时间升序楼层排序）/ 删除（评论作者本人或 admin）
- 新增点赞接口：点赞 / 取消点赞（**幂等**，重复点赞不叠加计数；计数用 `likes` 表 `COUNT(*)` 保证精确）
- **接口分页重构**：`GET /api/posts` 与评论列表统一 `Page & PageSize` 参数化分页，返回 `{items, total, page, page_size}` 元信息
- 前端：首页分页导航 + 文章卡片点赞/评论数徽标 + 阅读器内点赞按钮与**楼层评论**渲染

遵循项目红线：分层清晰、ATDD（先写测试再编码）、`uv` 管理依赖、JWT 守卫、`uv run pytest -q` 全绿交付。

---

## 二、现状分析（Current State Analysis）

| 文件 | 现状 | 与本阶段关系 |
| :--- | :--- | :--- |
| `models.py` | `User` + `Post` 两表，`Post` 无点赞/评论字段 | 需新增 `Comment`、`Like` 表 |
| `schemas.py` | 认证/用户/文章 DTO；`PostResponse` 为裸字段 | 需扩展 `PostResponse`（likes/comment_count/liked）+ 新增评论/点赞/分页 DTO |
| `database.py` | SQLite 引擎 + `SessionLocal` + `get_db` | 无需改动（复用） |
| `security.py` | `get_current_user`（必登录）/ `require_admin` 守卫 | 需新增 `get_optional_user`（列表展示已点赞态但不强制登录） |
| `main.py` | 文章/分类接口；`GET /api/posts` **返回裸数组** | 需评论/点赞路由 + 分页改造 + 删除文章级联清理 |
| `index.html` | 首页卡片网格、阅读器（仅 Markdown）、登录弹窗 | 需分页导航 + 点赞按钮 + 评论楼层区 |
| `test_main.py` | 42 用例全绿；`test_get_posts_*` 断言**裸数组** | 需改造列表断言 + 新增评论/点赞/分页用例 |
| `.trae/rules/backend.md` | 已声明「Page & PageSize 分页，返回 items+total+page+page_size」 | 本阶段将其落地为实际契约，阶段后按惯例同步文档 |

**关键破坏性点**：`GET /api/posts` 响应结构从「裸数组」改为「分页对象」，既有 `test_get_posts_*` 五个用例与前端 `loadPosts()` 必须**同步改造**。

---

## 三、目标与决策（Goals & Decisions）

本阶段已确定的决策：

1. **评论与点赞均需登录**（未登录 401）；**浏览评论与点赞数公开**（无需登录）。
2. **点赞防刷**：`likes` 表对 `(post_id, user_id)` 建**唯一约束**，点赞接口幂等——重复点赞不新增记录、不叠加计数；计数一律 `COUNT(*)` 实时统计，杜绝刷量。
3. **评论删除权限**：评论作者本人或 admin 可删；其余用户 403；未登录 401。
4. **楼层渲染**：评论列表按 `created_at` 升序返回（1楼 为最早评论），前端以「N楼」编号；分页时楼层号 = `(page-1)*page_size + 序号`。
5. **分页契约**：列表接口统一 `page`（≥1，默认 1）+ `page_size`（1~50）Query 参数，返回 `{items, total, page, page_size}`；首页文章 `page_size=9`（3×3 网格），评论默认 `page_size=20`。
6. **删除文章级联清理**：删除 `Post` 时同步删除其全部点赞与评论（SQLite 默认不启用外键约束，手动清理保证无孤儿数据）。
7. **详情/列表均带社交计数**：`PostResponse` 增加 `likes`（点赞数）、`comment_count`（评论数）、`liked`（当前登录用户是否已点赞，未登录为 `false`）。

补充合理假设（已记录，如不合意可调整）：
- 评论内容 `min_length=1, max_length=1000`（Pydantic 校验，超限 422）。
- 评论不支持回复/楼中楼、@提及、富文本（本期仅纯文本 Markdown 原样渲染）。
- 不做点赞用户列表、不做评论审核、不做实时推送。
- 前端评论区在阅读器内「内容下方」展示；未登录显示「登录后参与评论」引导，不展示输入框。

---

## 四、方案设计（Design）

### 4.1 数据模型 — `models.py` 新增 `Comment` / `Like`

```python
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_like_post_user"),
    )
```

> `Like` 的 `(post_id, user_id)` 唯一约束是「防刷」的数据库层保证；计数用 `COUNT(*)` 实时统计。

### 4.2 Schema — `schemas.py` 新增 / 扩展

```python
# PostResponse 扩展三个社交字段（默认值保证旧调用兼容）
class PostResponse(BaseModel):
    id: int
    title: str
    content: str
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


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class CommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    username: str          # 联表 User 冗余展示名
    content: str
    created_at: datetime


class LikeResponse(BaseModel):
    liked: bool
    likes: int


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
```

### 4.3 认证 — `security.py` 新增 `get_optional_user`

列表/详情接口需要展示「当前用户是否已点赞」，但**未登录不能 401**（读接口保持公开）。新增可选登录依赖：

```python
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(database.get_db),
) -> User | None:
    """可选登录依赖：有有效 Token 返回用户，否则返回 None（不抛 401）"""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        return None
    return db.query(User).filter(User.id == user_id).first()
```

### 4.4 API 契约（新增 / 变更）

| 方法 | 路径 | 权限 | 说明 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/posts` | 公开（可选登录） | **变更**：新增 `page` / `page_size`，返回 `PaginatedPosts`；保留 category/status/search 过滤 |
| `GET` | `/api/posts/{id}` | 公开（可选登录） | **变更**：响应含 `likes` / `comment_count` / `liked` |
| `GET` | `/api/posts/{id}/comments` | 公开 | **新增**：分页返回评论（升序，楼层顺序），`PaginatedComments`；文章不存在 404 |
| `POST` | `/api/posts/{id}/comments` | 登录 | **新增**：body `{content}` → 201 `CommentResponse`；未登录 401；空/超长内容 422；文章不存在 404 |
| `DELETE` | `/api/comments/{id}` | 登录 | **新增**：作者或 admin 可删 → 204；未登录 401；非作者非 admin 403；不存在 404 |
| `POST` | `/api/posts/{id}/like` | 登录 | **新增**：幂等点赞 → 200 `LikeResponse{liked,likes}`；未登录 401；文章不存在 404 |
| `DELETE` | `/api/posts/{id}/like` | 登录 | **新增**：幂等取消点赞 → 200 `LikeResponse{liked:false,likes}` |
| `DELETE` | `/api/posts/{id}` | 仅 admin | **变更**：删除文章时级联清理其点赞与评论 |

错误格式沿用 `{"detail": "..."}`。

### 4.5 后端 — `main.py`

- 辅助函数（避免逐条 COUNT 的 N+1）：
  - `_post_counts(db, post_ids)`：用 `IN` + `GROUP BY` 一次查出点赞数与评论数，返回 `{post_id: {"likes": n, "comments": n}}`
  - `_liked_post_ids(db, user)`：当前用户已点赞的文章 ID 集合（未登录返回空集）
  - `_post_response(post, counts, liked_ids)`：组装带社交字段的 `PostResponse`
- `get_posts`：过滤 → `count()` 取 total → `offset/limit` 取页 → 批量 counts → 组装 `PaginatedPosts`
- `get_post`：复用 `_post_counts` / `_liked_post_ids` 组装详情
- 评论三接口与点赞两接口按 4.4 契约实现；评论列表 `order_by(created_at.asc(), id.asc())` 保证楼层稳定
- `delete_post`：先 `delete(Like/comment where post_id=...)` 再删文章

### 4.6 前端 — `index.html`

- **分页**：`loadPosts()` 解析分页响应 `{items,total,page,page_size}`；新增 `pageInfo` 状态；网格下方渲染「上一页 / 第 x 页 / 下一页」控件（首页 `page_size=9`；切换分类/搜索时重置 `page=1`）；导航统计改用 `total`。
- **卡片社交徽标**：卡片底部元信息增加 `<heart>点赞数` 与 `<message-square>评论数`。
- **阅读器点赞按钮**：内容顶部/元信息区加「♥ 点赞 N」按钮；未登录点击弹登录框；点击后 `POST`/`DELETE /api/posts/{id}/like` 并即时更新按钮态与计数（`liked=true` 填充红色心形）。
- **评论楼层区**（阅读器内容下方）：
  - 头部「💬 评论（N）」+ 列表；每条评论渲染 `N楼`、用户名、相对时间、内容；作者本人或 admin 显示删除按钮。
  - 输入框：登录显示 `textarea + 发表评论`；未登录显示「登录后参与评论」引导。
  - 加载：`GET /api/posts/{id}/comments?page=1&page_size=20`，若 `items` 满页且有更多则显示「加载更多评论」追加下一页（楼层号按偏移累计）。
  - 发表/删除成功后刷新评论列表并同步阅读器点赞/评论计数。
- 保持玻璃拟态风格与既有交互习惯。

### 4.7 测试 — `test_main.py`（ATDD）

**改造既有用例**（分页契约）：
- `test_get_posts_empty`：断言 `items == []` 且 `total == 0`
- `test_get_posts_list` / `filter_category` / `filter_status` / `search`：改读 `items` 数组与 `total`

**新增用例**：
- 分页：`page=1&page_size=2` 建 5 篇断言分页正确；`page=0` / `page_size=0` / `page_size=100` → 422
- 评论：创建成功 201（含 username）；未登录 401；空内容 422；文章不存在 404；列表分页 + 升序楼层；空列表；删除（作者 204 / admin 204 / 他人 403 / 未登录 401 / 不存在 404）
- 点赞：点赞 200（liked=true, likes=1）；**重复点赞幂等**（仍 1）；未登录 401；文章不存在 404；取消点赞 200（likes=0）；未点赞时取消幂等；详情 `GET /api/posts/{id}` 携带 likes/comment_count/liked；列表响应含社交字段
- 级联：删除文章后其评论/点赞一并清除

---

## 五、改动文件清单（Files & Why/How）

| 文件 | 改动 | 原因 / 方式 |
| :--- | :--- | :--- |
| `models.py` | 新增 `Comment`、`Like` 表 | 评论一对多 + 点赞唯一约束防刷 |
| `schemas.py` | `PostResponse` 扩展社交字段；新增 `CommentCreate/CommentResponse/LikeResponse/PaginatedPosts/PaginatedComments` | 分页与社交 DTO |
| `security.py` | 新增 `get_optional_user` + `oauth2_scheme_optional` | 读接口展示已点赞态但不强制登录 |
| `main.py` | 分页改造 + 评论/点赞路由 + 删除级联清理 | 社交系统落地 |
| `index.html` | 分页导航 + 卡片徽标 + 阅读器点赞 + 评论楼层区 | 前端闭环 |
| `test_main.py` | 改造列表断言 + 新增评论/点赞/分页用例 | ATDD |
| 文档同步 | `agents.md`、`.trae/rules/backend.md` | 项目惯例「每阶段同步文档」 |

> `database.py`、`User` / `Post` 表结构**不改动**。

---

## 六、实施步骤（Tasks）

1. `models.py` 新增 `Comment`、`Like`（含唯一约束）
2. `security.py` 新增 `get_optional_user`
3. `schemas.py` 扩展 `PostResponse` + 新增评论/点赞/分页 DTO
4. `test_main.py`：先改造既有列表断言（红灯）→ 再新增分页/评论/点赞用例（红灯）→ 后编码（绿灯）
5. `main.py`：辅助函数 + 分页改造 + 评论/点赞接口 + 删除级联
6. `uv run pytest -q` 全绿
7. `index.html` 前端改造（分页 / 点赞 / 评论楼层）
8. 启动服务实测：分页翻页、点赞幂等、评论楼层与删除权限、未登录引导
9. OpenSpec `sync` 合并主规格 + `archive` 归档 + 同步 `agents.md` / `.trae/rules/backend.md`

---

## 七、验证步骤（Verification）

- 自动化：`uv run pytest -q` 全绿（既有 + 新增用例）。
- API 层抽查（curl）：登录拿 Token → 点赞两次计数仍 1（幂等）；未登录点赞 401；评论列表分页结构；他人评论删除 403。
- 手工（浏览器）：首页分页翻页；卡片显示点赞/评论数；阅读器点赞填充/取消；评论按楼层显示、发表/删除（作者/admin/他人）、未登录引导登录；刷新后登录态与已点赞态保持。

---

## 八、风险与注意事项

- **分页破坏性改造**：`GET /api/posts` 响应结构变更，必须同步改既有 5 个列表用例与前端 `loadPosts()`，避免「接口 200 但契约错」。
- **列表 N+1**：社交计数必须用 `IN + GROUP BY` 批量统计，严禁逐篇 `COUNT` 查询。
- **SQLite 外键默认不启用**：删除文章须手动级联删除点赞与评论，否则产生孤儿数据。
- **点赞幂等**：唯一约束兜底数据库层防刷；接口侧需「存在则跳过、不存在则新增」，重复调用不报错不叠加。
- **楼层稳定性**：评论排序必须 `created_at + id` 双键升序，避免同秒评论顺序抖动；分页时楼层号按偏移累计。
- **401 vs 422 顺序**：新接口「缺字段」断言用登录态请求，规避依赖框架校验顺序。
- **读接口不强制登录**：`get_optional_user` 不能抛出 401，否则破坏「未登录可浏览」的既有行为。
