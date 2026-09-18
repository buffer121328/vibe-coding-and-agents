"""
SmartBuyer · mcp_tools.py —— MCP 工具生态接入（Phase 3）
========================================================
课程出身：9.1 的 1.4 新特性 `langchain.mcp` 命名空间 + 9.7 的 `ProviderToolSearchMiddleware`
/ `LLMToolSelectorMiddleware`（演进路线 Phase 3，见项目 README）。

能力（全部经 1.4.0 本地实测核对的 API）：
1. `MCPAdapter`：把任意 MCP 服务器（http/https URL 或本地 stdio 脚本）的工具一键转成 LangChain 工具，
   `list_tools(cache_mode=...)` 支持工具清单缓存（use / refresh / bypass，SEP-2549）；
2. `ProviderToolSearchMiddleware`：把低频工具标记 defer_loading，交厂商服务端工具搜索按需取回
   schema（Anthropic Sonnet 4+ / OpenAI gpt-5.5+ 支持），大幅压缩请求体；
3. `LLMToolSelectorMiddleware`：工具再多时，先由小模型分诊出本问相关的几把，主模型只看精选。

⚠️ beta 提示：`langchain.mcp` 在 1.4 处于 beta（官方 LangChainBetaWarning），API 可能变动；
   生产使用请锁定版本。安全提示：适配器只接受 http(s) URL 字符串作为 target，
   传本地脚本路径会被拒绝（防止误执行本地进程），本地 stdio 服务器请显式传 fastmcp transport。

用法：
    # 1) 配置 .env：SMARTBUYER_MCP_URLS="https://mcp.example.com/mcp,https://mcp2.example.com/sse"
    # 2) 演示装配：uv run python -m smart_buyer.mcp_tools
    # 3) 编程调用：from smart_buyer.mcp_tools import build_mcp_tools, build_middleware_stack
"""

import os
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel

console = Console()


# ==============================================================================
# 0. 【默认数据源】内置演示服务器：进程内 FastMCP，5 把电商行情工具（零外部依赖）
# ==============================================================================
def get_builtin_server():
    """返回内置 mcp_server.FastMCP 实例（进程内，不占端口、不联网）。
    生产环境替换：把它换成真实 MCP 服务器的 http(s) URL（SMARTBUYER_MCP_URLS）。"""
    from smart_buyer.mcp_server import mcp as builtin_server
    return builtin_server


# ==============================================================================
# 1. MCP 工具接入：MCPAdapter（1.4 beta）
# ==============================================================================
def _wrap_async_tool(tool):
    """1.4 的 MCPAdapter 产出 StructuredTool（只支持 async 调用）。
    create_agent 的模型调度走 ainvoke 没问题，但 ToolNode 的同步 invoke 路径
    会抛 NotImplementedError——包一层同步适配，让课程版 main.py 的同步 Agent
    也能直接用 MCP 工具。"""
    from langchain_core.tools import StructuredTool
    import asyncio

    def _sync_call(**kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # 已在事件循环内（Agent 的 async 路径）：直接透传协程
            return tool.coroutine(**kwargs)
        return asyncio.run(tool.coroutine(**kwargs))

    return StructuredTool.from_function(
        func=_sync_call,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )


def build_mcp_tools(urls: list[str] | None = None, cache_mode: str = "use", include_builtin: bool = True):
    """把 MCP 服务器的工具转成 LangChain 工具列表（同步可用，直接可进 create_agent）。

    数据源（两路合并）：
    - 内置演示服务器（默认开启）：进程内 FastMCP，5 把电商行情工具（比价/官参/以旧换新/物流/售后）；
    - 外部 MCP 服务器：环境变量 SMARTBUYER_MCP_URLS（逗号分隔 http(s) URL），生产用。

    Args:
        urls: 外部 MCP 服务器地址；None=读环境变量；传 [] 表示不用外部服务器。
        cache_mode: 工具清单缓存策略（1.4 SEP-2549）：
              "use" 默认用缓存 | "refresh" 强制刷新 | "bypass" 绕过缓存直连。
        include_builtin: 是否装载内置演示服务器（False 时纯外部源）。

    Returns:
        (tools, errors)：tools 是同步可用的 BaseTool 列表；errors 是逐源的失败记录。
    """
    import asyncio
    sources: list[tuple[str, Any]] = []
    if include_builtin:
        sources.append(("builtin://smart-buyer-market", get_builtin_server()))
    external = [
        u.strip() for u in (os.getenv("SMARTBUYER_MCP_URLS", "") if urls is None else ",".join(urls)).split(",")
        if u.strip()
    ]
    sources.extend((u, u) for u in external)

    tools, errors = [], []
    if not sources:
        return tools, errors

    from langchain.mcp import MCPAdapter

    async def _collect():
        nonlocal tools, errors
        for name, target in sources:
            try:
                adapter = MCPAdapter(target)       # http(s) URL 防误执行校验；in-process server 直接放行
                fetched = await adapter.list_tools(cache_mode=cache_mode)
                wrapped = [_wrap_async_tool(t) for t in fetched]   # async 工具 → 同步可用
                tools.extend(wrapped)
                console.print(f"[dim]🔗 MCP[{name}] → {len(wrapped)} 个工具：{[t.name for t in wrapped]}[/dim]")
            except Exception as e:                 # 单个服务器挂了不拖垮整机
                errors.append((name, str(e)))
                console.print(f"[yellow]⚠️ MCP[{name}] 接入失败：{e}[/yellow]")

    asyncio.run(_collect())
    return tools, errors


# ==============================================================================
# 2. 工具治理中间件栈：延迟挂载 + LLM 分诊（工具多时的两道节流阀）
# ==============================================================================
DEFERRED_TOOLS_ENV = "SMARTBUYER_MCP_DEFERRED"    # 逗号分隔的低频工具名，如 "longtail_report,archive_query"


def build_middleware_stack(mcp_tool_count: int = 0):
    """按工具数量装配 1.4 工具治理中间件：

    - 工具 > 12 把：启用 ProviderToolSearchMiddleware（defer 环境变量点名的低频工具）
      + LLMToolSelectorMiddleware（每问先分诊，主模型最多同时看 6 把）；
    - 否则返回空栈（工具少时不必多此一举，省一层延迟）。
    """
    from langchain.agents.middleware import (
        LLMToolSelectorMiddleware,
        ProviderToolSearchMiddleware,
    )

    stack: list[Any] = []
    if mcp_tool_count <= 12:
        return stack

    deferred = [t.strip() for t in os.getenv(DEFERRED_TOOLS_ENV, "").split(",") if t.strip()]
    if deferred:
        stack.append(ProviderToolSearchMiddleware(searchable_tools=deferred))
        console.print(f"[dim]🛰️ 已延迟挂载 {len(deferred)} 把低频工具（服务端按需取回 schema）[/dim]")
    stack.append(LLMToolSelectorMiddleware(max_tools=6))   # 分诊上限：主模型每问最多 6 把
    console.print("[dim]🧭 已启用 LLM 工具分诊（max_tools=6）[/dim]")
    return stack


# ==============================================================================
# 3. 演示入口：报告当前 MCP 配置与中间件决策（不真实联网，零 Token）
# ==============================================================================
if __name__ == "__main__":
    console.print(Panel("[bold cyan]🔌 SmartBuyer Phase 3：MCP 工具生态接入演示[/bold cyan]", expand=False))

    urls = [u.strip() for u in os.getenv("SMARTBUYER_MCP_URLS", "").split(",") if u.strip()]
    console.print(f"[bold]SMARTBUYER_MCP_URLS：[/bold]{urls or '（未配置，MCP 工具为空——属正常优雅降级）'}")

    tools, errors = build_mcp_tools()
    console.print(f"\n[bold green]✅ 接入 MCP 工具：{len(tools)} 把[/bold green]"
                  + (f"；失败 {len(errors)} 个服务器" if errors else ""))
    for t in tools[:10]:
        desc = str(getattr(t, 'description', '') or '')[:60]
        console.print(f"  • {t.name}: {desc}")

    mw = build_middleware_stack(mcp_tool_count=len(tools))
    console.print(f"\n[bold]工具治理中间件栈：[/bold]{[m.__class__.__name__ for m in mw] or '（工具 ≤12 把，无需节流）'}")

    console.print("\n[dim]进阶用法：把 build_mcp_tools() 的结果传给 SmartBuyerAgent 的 tools，或塞进 deep_agent.py 子代理的 tools 字段——MCP 工具与 @tool 本地工具在框架眼里无差别。[/dim]")
