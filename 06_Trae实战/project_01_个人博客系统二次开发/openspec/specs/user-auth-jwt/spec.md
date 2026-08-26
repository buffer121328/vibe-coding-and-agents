# user-auth-jwt Specification

## Purpose
提供用户账号体系与 JWT 鉴权闭环，实现角色权限隔离：普通用户（reader）只读、管理员（admin）可写，写接口与管理接口受 JWT 守卫保护。
## Requirements
### Requirement: 用户登录颁发 JWT
系统 SHALL 提供 `POST /api/auth/login` 接口，接收 `username` 与 `password`，校验通过后返回 `access_token`（JWT）、`token_type`（bearer）及用户概要（id/username/role）。

#### Scenario: 登录成功
- **WHEN** 用户提交正确的用户名与密码
- **THEN** 接口返回 200 与有效的 JWT，以及用户角色信息

#### Scenario: 密码错误
- **WHEN** 用户提交错误的密码
- **THEN** 接口返回 401，提示用户名或密码错误

#### Scenario: 用户不存在
- **WHEN** 用户提交不存在的用户名
- **THEN** 接口返回 401，提示用户名或密码错误

#### Scenario: 缺少必要字段
- **WHEN** 请求体缺少用户名或密码字段
- **THEN** 接口返回 422

### Requirement: 当前用户查询
系统 SHALL 提供 `GET /api/auth/me` 接口，通过 `Authorization: Bearer <token>` 返回当前登录用户信息（id/username/role/created_at），且不泄露密码哈希。

#### Scenario: 携带有效 Token
- **WHEN** 用户携带有效 JWT 请求 `/api/auth/me`
- **THEN** 接口返回 200 与当前用户信息，且响应中不包含 `password_hash`

#### Scenario: 无 Token
- **WHEN** 用户未携带 Token 请求 `/api/auth/me`
- **THEN** 接口返回 401

#### Scenario: 无效 Token
- **WHEN** 用户携带伪造或已失效的 Token 请求 `/api/auth/me`
- **THEN** 接口返回 401

### Requirement: 文章写操作权限隔离
系统 SHALL 将 `POST/PUT/DELETE /api/posts` 限定为仅管理员可调用：未登录返回 401，非 admin 角色返回 403，admin 正常执行。

#### Scenario: 未登录写文章
- **WHEN** 未登录用户调用创建/修改/删除文章接口
- **THEN** 接口返回 401

#### Scenario: 非管理员写文章
- **WHEN** reader 角色用户调用创建/修改/删除文章接口
- **THEN** 接口返回 403

#### Scenario: 管理员写文章
- **WHEN** admin 角色用户携带有效 Token 调用写接口
- **THEN** 接口正常执行（创建 201 / 修改 200 / 删除 204）

### Requirement: 仅管理员管理用户
系统 SHALL 将 `POST /api/users` 与 `GET /api/users` 限定为仅管理员可调用，用于创建账号与查看用户列表。

#### Scenario: 管理员创建用户
- **WHEN** admin 提交 `{username, password, role}`（role 为 admin 或 reader）
- **THEN** 接口返回 201 与用户信息（不含 password_hash）

#### Scenario: 用户名重复
- **WHEN** 创建的用户名已存在
- **THEN** 接口返回 409

#### Scenario: 非法角色
- **WHEN** 提交的 role 不是 admin 或 reader
- **THEN** 接口返回 422

#### Scenario: 非管理员访问用户管理
- **WHEN** 未登录或 reader 角色调用用户管理接口
- **THEN** 接口分别返回 401 或 403

### Requirement: 种子管理员
系统 SHALL 在首次启动建表后自动创建种子管理员账号（默认 `admin`），确保系统初始即有可登录的管理员；密码可经环境变量覆盖。

#### Scenario: 首次启动
- **WHEN** 系统首次启动且用户表为空
- **THEN** 自动创建 `admin` 管理员账号，可用其登录

#### Scenario: 非首次启动
- **WHEN** 系统已有用户数据
- **THEN** 不重复创建种子管理员

