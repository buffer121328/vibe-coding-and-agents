## Context

后端 API 和前端 index.html 都已完成。需要在 FastAPI 中添加静态文件服务，让前端可以通过后端托管访问。

## 架构决策

### SPA 路由
- 在 `main.py` 添加 `GET /` 路由
- 使用 `FileResponse` 返回 `index.html`
- 路由放在 API 路由之前，避免被 `/api/posts/{post_id}` 匹配

### CORS 配置
- 已有 `CORSMiddleware` 配置（`allow_origins=["*"]`）
- 无需修改

## 关键文件

- `main.py`（修改）：添加 `GET /` 路由
- `index.html`（已存在）：无需修改
