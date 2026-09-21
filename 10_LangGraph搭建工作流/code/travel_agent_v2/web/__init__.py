"""Trip Assistant Web 层包：FastAPI 后端 + Air 前端工作台。

- web.runtime 图单例、快照、节点级 SSE
- web.api     FastAPI 实例与 /api/*、/api/*/stream
- web.app     air.Air(fastapi_app=api) 装配
- web.views   Air Tags 页面骨架（旅行工作台；Air alpha 升级只改这里）
"""
