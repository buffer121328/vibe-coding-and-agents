"""server.py —— 启动入口的兼容层。

真正的应用在 ``web/app.py``。分层之后启动命令变成 ``uvicorn forge_lite.web.app:app``，
但文档、旧笔记和肌肉记忆还停在 ``forge_lite.server:app``。这个模块只做一件事：
把 ``app`` 再导出一次，让两条命令都能起服务。

不要在这里加路由。路由只住 ``web/app.py``，这里一加就又变成第二份真相。
"""

from .web.app import app

__all__ = ["app"]
