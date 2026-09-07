# 6.3 用户登录与操作权限

博客增加账号后，需要同时回答两个问题：访问者是谁，以及这个人能做什么。门禁卡可以证明身份，但不意味着持卡人能进入所有房间。本节据此区分登录认证与操作权限，并把检查落实到后端接口。

---

## 门禁卡、防伪手环与权限守卫

在给已有博客系统引入用户认证前，我们先通过日常场景理解核心机制：

<!-- 图表源文件：img/diagrams/03-diagram-01.mmd；视觉风格：Cyberpunk -->
<p align="center">
  <a href="img/diagrams/03-diagram-01.svg">
    <img src="img/diagrams/03-diagram-01.svg" alt="💡 一、门禁卡、防伪手环与权限守卫" width="860">
  </a>
</p>

- 🔐 **Bcrypt 加盐哈希**：数据库保存密码哈希而不是明文。攻击者拿到数据库后仍可能尝试猜测弱密码，因此还要设置合理的密码要求并保护数据库；
- 🎟️ **JWT（JSON Web Token）**：就像是游乐场的**带签名的身份凭据**。用户登录成功后，后端发给前端一个带有时效性（7天有效）和角色信息（`role: admin`）的 Token。之后前端每次发起请求都戴着手环，服务端不用每次查库验证密码，校验签名、有效期及相应权限后决定是否放行；
- 🛡️ **`Depends` 权限检查**：把认证和角色判断复用到受保护接口。公开读取与管理写操作采用不同要求，角色不符合时返回约定的 403 响应。

***

## Plan 模式：先讨论认证方案

改动认证功能前，先确认角色范围、登录方式和已有接口需要怎样调整，再让 AI 提出实施方案。

在已有系统中加入认证，先由开发者确定角色范围、数据归属和兼容要求，再让 Agent 比较实现方案。Agent 可以补充遗漏，但最终选择仍要对业务和安全结果负责。

### 1. 启动 Plan 模式并输入需求说明

在 Trae 对话框中切换到 **Plan 模式**，输入我们的宏观需求，要求 AI 针对现有项目给出合理方案并展开讨论：

<img src="./img/03_plan_prompt_input.png" alt="Trae Plan 模式意图输入" width="90%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

### 2. 交互式方案讨论与决策树选择

AI 会深入阅读项目现有的 `models.py`、`main.py` 和 `test_main.py`，并主动向我们弹出交互式的决策问询：

#### 决策一：权限隔离采用哪种粒度？

Trae 会列出当前系统的 3 种可选方案：

1. **作者归属隔离**：文章新增 `author_id`，作者只能改自己的，管理员管全部（改造面较大）；
2. **登录即可管理**：任何登录用户都能增删改所有文章（隔离性弱）；
3. **角色权限制**：普通用户只读，仅 `admin` 角色可写（最适合单人/团队博客，改造成本最小）。

<img src="./img/03_plan_option_permission_level.png" alt="Trae 方案交互选择：权限粒度" width="60%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

本例选择 **“角色权限”**：保留既有 `Post` 表结构，把改动集中在登录认证和接口权限检查上。这适合当前演示范围；若要支持多作者，还需要增加文章归属并重新设计授权规则。

#### 决策二：方案细节确认

Trae 会继续确认账号创建方式与前端改造范围：

<img src="./img/03_plan_option_discussion.png" alt="Trae 方案多维度细化讨论" width="60%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

本例采用以下约定：

- **账号来源**：演示环境在启动时创建首个管理员（`admin/admin123`），不开放注册接口。这个默认密码只能用于本地练习，实际部署必须改用安全凭据；
- **前端范围**：最小化轻量改造，仅增加登录弹窗、Token 存入 `localStorage`、根据当前角色控制写文章/编辑/删除按钮的显隐即可。

### 3. 方案保存与文档归档

讨论达成一致后，AI 会自动输出一份结构严密的实施蓝图。**此时我们把这份计划归档保存至** **`docs/phase05_用户注册登录与JWT权限隔离系统.md`**，作为本阶段全流程执行的标准指引。

***

## Agent 执行过程与核心代码

方案保存后，可以让 Trae Agent 按任务清单实现和检查。执行期间仍要关注它修改了哪些文件、是否使用了约定的接口，以及测试失败后做了什么调整。

### 1. 任务清单自动化执行

Trae Agent 会依据方案自动建立 10 项清晰的 Task 清单，并按照 **ATDD（验收测试驱动开发）** 的节奏依次推进：

<img src="./img/03_agent_executing_tasks.png" alt="Agent 任务清单自动化执行进度" width="90%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

***

### 2. 本阶段新增与改造代码解析

#### ① 数据模型层：`models.py`（新增 `User` 表）

我们在 `models.py` 中新增了轻量且安全的 `User` 表，维持现有的 `Post` 表结构完全不变（最小改造成本）：

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)  # 严格只存 bcrypt 哈希
    role: Mapped[str] = mapped_column(String(20), default="reader")           # admin | reader
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
```

#### ② 安全与认证中枢：`security.py`（独立解耦模块）

为了不让 `main.py` 变成几千行难以维护的代码，我们将密码加密、JWT 颁发与 FastAPI 依赖守卫全部封装在独立的 `security.py` 中：

```python
"""认证安全模块：密码哈希 / JWT 颁发校验 / 权限守卫依赖"""
import os
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import database
from models import User

# JWT 密钥与配置（支持环境变量注入）
SECRET_KEY = os.getenv("BLOG_SECRET_KEY", "dev-secret-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 7 * 24 * 60  # Token 7 天有效

ADMIN_USERNAME = os.getenv("BLOG_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("BLOG_ADMIN_PASSWORD", "admin123")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def hash_password(raw: str) -> str:
    """bcrypt 哈希加盐：单向加密"""
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(raw: str, hashed: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配"""
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user: User) -> str:
    """颁发带签名的身份凭据（JWT）"""
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)) -> User:
    """依赖守卫：解析 Bearer Token 并获取当前用户（无效/过期抛出 401）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的登录凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_exception
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """仅管理员可通行的守卫（非 admin 抛出 403 Forbidden）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user
```

#### ③ 数据契约层：`schemas.py`（新增 DTO）

新增了请求入参校验与响应出参模型。**切记：`UserResponse`** **绝不能包含** **`password_hash`。**

```python
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

class UserBrief(BaseModel):
    id: int; username: str; role: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBrief

class UserResponse(BaseModel):
    id: int; username: str; role: str; created_at: datetime
    model_config = {"from_attributes": True}
```

#### ④ 后端路由与种子管理：`main.py`

在 `main.py` 中新增了自动种子化管理员、登录认证路由，并在所有写操作接口挂载 `security.require_admin` 守卫：

```python
def seed_admin(db: Session):
    """首次建库时自动初始化种子管理员 admin/admin123"""
    if db.query(User).filter(User.username == security.ADMIN_USERNAME).first():
        return
    db.add(User(username=security.ADMIN_USERNAME, password_hash=security.hash_password(security.ADMIN_PASSWORD), role="admin"))
    db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=database.engine)
    with database.SessionLocal() as db:
        seed_admin(db)
    yield

# 登录接口
@app.post("/api/auth/login", response_model=TokenResponse)
def login(login_in: LoginRequest, db: Session = Depends(database.get_db)):
    user = db.query(User).filter(User.username == login_in.username).first()
    if not user or not security.verify_password(login_in.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenResponse(access_token=security.create_access_token(user), user=UserBrief(id=user.id, username=user.username, role=user.role))

# 写文章（加挂 require_admin 守卫，未登录 401 / 越权 403）
@app.post("/api/posts", response_model=PostResponse, status_code=201)
def create_post(post_in: PostCreate, db: Session = Depends(database.get_db), _: User = Depends(security.require_admin)):
    post = Post(**post_in.model_dump())
    db.add(post); db.commit(); db.refresh(post)
    return post
```

#### ⑤ 单文件前端轻量改造：`index.html`（简要介绍）

前端保持单文件纯静态（零 npm 构建链）架构，仅进行了 3 处微创级改造：

1. **状态本地持久化**：使用 `localStorage` 存取 `blog_token` 与 `blog_user`；
2. **UI 按权限动态渲染（`updateAuthUI`）**：
   - 未登录状态：顶部显示「登录」按钮，隐藏「写文章」按钮，文章卡片只读（隐藏编辑与删除按钮）；
   - 管理员登录后：顶部显示 `admin` 账号与「退出」按钮，点亮「写文章」按钮与卡片操作；
3. **`apiFetch`** **拦截器与 401 自愈**：
   - 每次网络请求自动在 Header 中添加 `Authorization: Bearer <token>`；
   - 若接口返回 `401 Unauthorized`，自动清除本地凭证并唤起登录模态框。

***

## 安全机制原理与边界（实现原理）

### 1. JWT 的“三段式”结构：为什么改一个字节都会被识破？

JWT 本质上是一串被 `.` 分成三段的 Base64 字符串：**`Header.Payload.Signature`**（形如 `eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.xxxx`）。

<!-- 图表源文件：img/diagrams/03-diagram-02.mmd；视觉风格：GitHub Dark -->
<p align="center">
  <a href="img/diagrams/03-diagram-02.svg">
    <img src="img/diagrams/03-diagram-02.svg" alt="1. 🪪 JWT 的“三段式”结构：为什么改一个字节都会被识破？" width="860">
  </a>
</p>

- **Header（头部）**：声明令牌类型（JWT）与签名算法（HS256）；
- **Payload（载荷）**：存放“声明”，比如我们的 `sub`（用户 ID）、`role`（角色）与 `exp`（过期时间）。**注意：Payload 只是 Base64 编码，并没有加密，任何人都能解码看到内容**，所以严禁把密码等敏感信息塞进去；
- **Signature（签名）**：把 `Header + Payload` 拼起来，用**只有服务端知道的密钥（SECRET\_KEY）** 做 HMAC-SHA256 哈希。任何人都能“读”前两段，但**没有密钥就改不了**——因为你一旦篡改 Payload 里的 `role`，签名就立刻对不上，服务端验签时直接判 401。

> 🧠 **一句话理解**：JWT 就像一张**带防伪钢印（签名）的会员卡**。卡面信息（角色、有效期）人人都能看，但只有店家（服务端）用私藏印章盖出来的钢印才有效；你敢拿记号笔涂改“普通会员”为“至尊会员”，钢印就对不上，门卫直接把你拦下。

***

### 2. Bcrypt 为什么是“单向不可逆”的？为何不用 MD5 / SHA256？

普通快速哈希不适合直接保存密码，因为攻击者可以高速尝试候选密码；未加盐时还容易受到预计算攻击。Bcrypt 为密码存储提供盐和可调计算成本：

1. **随机加盐（Salt）**：每次哈希生成随机盐值，因此相同密码通常得到不同结果，可以显著增加预计算表攻击的成本；
2. **刻意慢（Work Factor 成本因子）**：Bcrypt 会循环迭代成千上万次，单次验证就要几十毫秒。对你来说只是“卡顿一下”，但黑客用 GPU 暴力穷举时，尝试成本提高，但仍需结合密码强度和登录限速。

> ⚙️ 例如 `bcrypt.gensalt()` 默认成本因子 12，即执行 2¹² = 4096 轮迭代；你还可以通过参数调高成本因子，让密码“更难啃”。**这就是为什么本阶段红线里明确写着：密码必须 bcrypt 哈希，严禁明文/MD5 存储。**

***

### 3. `OAuth2PasswordBearer` 与 `Depends`：FastAPI 依赖注入的魔力

很多同学第一次看到 `Depends(security.require_admin)` 可能一头雾水，其实它是 FastAPI 最优雅的“插销式”鉴权：

- **`OAuth2PasswordBearer(tokenUrl="/api/auth/login")`**：它本身不校验任何东西，只负责在请求到达路由函数前，**自动从 HTTP 请求的** **`Authorization: Bearer <token>`** **头里提取 Token 字符串**；
- **`get_current_user`**：拿到 Token 后调用 `jwt.decode` 验签、解析出 `user_id`，再查库返回 `User` 对象；Token 无效/过期则抛 401；
- **`require_admin`**：在 `get_current_user` 基础上，再检查 `role != "admin"` 则抛 403；
- **`Depends(...)`** **依赖注入**：把这些“检查逻辑”声明成路由的依赖项，FastAPI 会在**每个请求进入路由函数前自动执行依赖链**——这就像进贵宾厅要过的一道道安检门，路由函数本身只用关心业务，完全不用写重复的鉴权代码。

> 💡 **依赖链**：`POST /api/posts` 请求 → `Depends(require_admin)` → `Depends(get_current_user)` → `Depends(oauth2_scheme)` 提取 Token → 验签 → 查库 → 校验角色 → 通过后路由函数才开始干活。

***

### 4. 生产环境安全最佳实践 检查清单（对标）

| 检查项           | 本阶段落地                     | 生产环境更严要求                             |
| :------------ | :------------------------ | :----------------------------------- |
| **密码存储**      | bcrypt 加盐哈希，绝不存明文         | 提高成本因子；必要时上 Argon2id                 |
| **Token 密钥**  | 环境变量 `BLOG_SECRET_KEY` 注入 | 使用强随机密钥（≥32 字节），严禁硬编码与提交 Git         |
| **Token 有效期** | 7 天长效 Token               | 缩短有效期 + 引入 Refresh Token（刷新令牌）轮换机制   |
| **传输安全**      | 本地开发 HTTP                 | 生产必须 HTTPS（否则 Token 会被中间人窃取）         |
| **越权防护**      | `Depends` 守卫 + 角色校验       | 全接口逐一测试 401 / 403 矩阵；接口最小权限原则        |
| **登录爆破**      | ——                        | 引入登录失败次数限制 + 验证码 / 限流（Rate Limiting） |

> 🎯 **给进阶同学的小作业**：尝试为博客系统追加“登录失败 5 次锁 15 分钟”的防爆破逻辑（可用 SQLite 记录失败次数），再补 2\~3 个 pytest 用例验证它——这也是面试官非常爱考的高频点。

***

## 浏览器全流程实测效果

启动本地服务器（`uv run uvicorn main:app --reload --port 8000`）后，通过浏览器检查登录和权限流程：

### 1. 未登录状态（纯净只读主页）

首次打开页面，右上角展示「登录」按钮，全站文章正常公开浏览，**未登录状态下无法编辑和新增文章**（“写文章”按钮与每篇文章卡片上的“编辑/删除”按钮均被安全隐藏）：

<img src="./img/03_ui_readonly_homepage.png" alt="未登录只读主页" width="90%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

### 2. 点击唤起暗黑玻璃拟态登录弹窗

点击「登录」按钮，在登录窗口中输入演示用管理员账号 `admin / admin123`。若项目离开本地练习环境，应先更换默认密码：

<img src="./img/03_ui_login_modal.png" alt="暗黑玻璃拟态登录弹窗" width="90%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

### 3. 登录成功态（权限全开）

登录成功后，顶部右上角展示当前登录身份 `admin` 与「退出」按钮，写文章与操作按钮全部点亮，刷新页面依然保持登录状态：

<img src="./img/03_ui_logged_in_state.png" alt="登录成功状态" width="30%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

***

## ATDD 测试验收与规格归档

在 Agent 完成编码后，自动化验收套件与 OpenSpec 规范顺利收尾：

<img src="./img/03_phase_completed_acceptance.png" alt="阶段一全流程验收与文档同步" width="90%" style="border: 1px solid #d9d9d9; border-radius: 6px; box-sizing: border-box;">

1. **🧪 自动化回归测试（42 passed 全部通过）**：
   - 运行 `uv run pytest -v`，覆盖登录成功/失败、Token 过期、401 拦截、403 越权、种子管理员自愈等全套用例，测试通过率 100%。
2. **📋 OpenSpec 规格校验与归档**：
   - 执行 `openspec validate --all` 校验 0 failed；
   - 执行 `openspec archive --yes` 自动将变更合并入主规格 `specs/user-auth-jwt/spec.md`；
   - 同步更新 `agents.md`、`.traerules`、`.trae/rules/backend.md` 等项目规则。

***

## 权限要同时覆盖操作和数据

门禁不仅要检查能否进门，也要检查能否进入指定房间。博客也是如此：用户登录成功后，不应因此获得所有文章和所有管理操作的权限。

本阶段采用角色区分时，可以先写出访问表，再对照每个接口检查。以下是设计与验收用的检查项，具体允许范围以本项目规格为准。

| 请求者 | 检查重点 |
| --- | --- |
| 未登录访问者 | 能否只看到公开内容，写操作是否被拒绝 |
| 普通读者 | 是否能互动，但不能调用管理接口 |
| 管理员 | 是否能完成管理操作，错误输入是否仍会校验 |
| 凭据过期或无效的用户 | 是否返回认证失败，并引导重新登录 |

前端隐藏按钮只是使用体验，真正的检查必须在后端。还需要检查列表和详情是否一致：列表隐藏了草稿，但猜到文章编号后仍能通过详情接口读到，也属于权限缺口。

JWT 的签名用于检查凭据是否被改动，载荷通常可以解码查看，因此不能把密码和密钥放进去。退出登录时，若只清除浏览器凭据，服务端未过期的旧令牌仍可能有效；需要立即失效时，要另行设计撤销机制。

验收不要只覆盖“登录成功”。至少加入错误密码、过期凭据、普通用户调用管理员接口、未登录访问受限数据等场景。每个拒绝结果都应与接口约定一致。

## 认证和授权要分别验收

认证回答“请求者是谁”，授权回答“这个身份能做什么”。两者混在一个测试里，容易出现登录流程正常，却仍能读取或修改他人数据的情况。可以先验证凭据签发、过期和篡改，再为每种角色逐一检查文章、评论和管理接口。

| 检查层次 | 代表场景 | 预期结果 |
| --- | --- | --- |
| 身份认证 | 密码错误、令牌过期、签名被改动 | 拒绝请求，不进入业务逻辑 |
| 角色授权 | 普通用户访问管理员接口 | 返回约定的权限错误 |
| 数据归属 | 用户修改不属于自己的内容 | 即使已经登录也应拒绝 |
| 凭据保存 | 数据库泄露或日志输出 | 不出现明文密码和签名密钥 |

还要测试服务重启后的行为：密钥稳定时，未过期令牌是否继续有效；密钥变化时，旧令牌怎样处理。前端清除登录状态后，再用旧令牌直接请求接口，可以帮助判断系统是否需要服务端撤销机制。

---

## 本节回顾

认证确认身份，授权限制操作与数据范围。检查后端接口之外，还要核对列表、详情和前端提示是否保持一致。

继续阅读：[6.4 评论、点赞与分页改造](./04_阶段二实战：评论点赞系统与接口分页重构.md)。
