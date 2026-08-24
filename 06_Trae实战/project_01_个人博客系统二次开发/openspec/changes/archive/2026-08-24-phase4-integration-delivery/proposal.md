## Why

前后端代码都已完成，但前端需要通过后端托管才能正常访问（同源请求 API）。需要打通前后端通信，完成单页托管配置，并进行全链路功能自测确保交付质量。

## What Changes

- 在 `main.py` 添加根路由 `/` 返回 `index.html`（SPA 单页托管）
- 验证前后端联调：CRUD 全链路功能正常
- 验证跨域配置：CORS 中间件正确放行
- 验证异常场景：404、参数校验失败等

## Capabilities

### New Capabilities

- `integration-delivery`: 前后端联调、单页托管、全链路功能验收

### Modified Capabilities

（无）

## Impact

- 修改文件：`main.py`（添加 `/` 路由）
- 不新增依赖
- 不修改前端代码
