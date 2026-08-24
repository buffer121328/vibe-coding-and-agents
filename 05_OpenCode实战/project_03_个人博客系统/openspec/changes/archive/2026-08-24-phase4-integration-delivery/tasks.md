## 1. SPA 路由配置

- [x] 1.1 在 `main.py` 添加 `from pathlib import Path` 和 `from fastapi.responses import FileResponse`
- [x] 1.2 定义 `BASE_DIR = Path(__file__).resolve().parent`
- [x] 1.3 添加 `GET /` 路由，返回 `FileResponse(BASE_DIR / "index.html")`

## 2. 集成验收

- [x] 2.1 启动服务器，验证 `GET /` 返回 index.html
- [x] 2.2 验证 `GET /api/posts` 正常返回 JSON
- [x] 2.3 验证 `POST /api/posts` 创建文章
- [x] 2.4 验证前端页面可以正常加载和交互
