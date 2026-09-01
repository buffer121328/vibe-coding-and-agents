"""
app.py - 第八章《手搓 Agent》统一交互式 Gradio Master 工作台
==============================================================================
现代 IDE 风格【左侧源码联动 + 右侧交互沙箱】全景工作台架构：
1. 【最左侧】垂直章节实战导航栏（8.1 ~ 8.13 清晰排列，告别顶部标签栏溢出）
2. 【中间/左侧代码栏】对应章节的 Python 原生实现源码（下拉框切换视图、高亮与行号，高度与右侧精准对齐）
3. 【右侧实战栏】对应章节的可运行交互沙箱与调试控制台（高度与左侧精准对齐）
4. 【8.13 Mini-Agent】真实 ChatGPT / Codex 风格多轮气泡对话流，支持上下文持久记忆与清空重启
5. 【环境变量】模型配置已自动从 .env 全局载入，界面纯粹极简
6. 【流式打字机】真实微秒级节奏流式输出 + 呼吸光标动效

一键启动：uv run python app.py (或 python app.py)
默认地址：http://127.0.0.1:7860
==============================================================================
"""

import json
import os
import time
import gradio as gr
from dotenv import load_dotenv

# 导入 8.1 ~ 8.13 核心模块
from s01_env_setup import ZhipuGLMClient
from s02_react_loop import ReActAgent
from s03_plan_and_execute import PlanAndExecuteAgent
from s04_tool_registry import registry, FunctionCallingAgent
from s05_terminal_and_edit import run_bash, str_replace
from s06_permissions_hitl import PermissionGuard
from s07_hooks_lifecycle import create_default_hook_manager
from s08_context_compact import ContextManager, parse_raw_dialogue_to_messages, estimate_tokens
from s09_memory_and_skills import MemoryStore, SkillLoader
from s10_subagents import DeepResearchPipeline
from s11_session import SessionStore, demo_tree_branching
from s12_observability import run_mock_eval, run_real_agent_eval
from s13_mini_agent import MiniAgent, WebSearch, polish_markdown

load_dotenv()

# 全局共享客户端实例（自动从 .env 读取主备模型与 Key）
global_client = ZhipuGLMClient()

# 13 章节源码与名称映射
CHAPTERS = [
    (1, "📡 8.1 环境基建与模型接入", "s01_env_setup.py", "ZhipuGLMClient / chat_stream / OpenAI 协议直连"),
    (2, "🔄 8.2 ReAct 思考范式", "s02_react_loop.py", "ReActAgent / Thought-Action-Observation 极简闭环"),
    (3, "📋 8.3 Plan & Execute 规划范式", "s03_plan_and_execute.py", "PlanAndExecuteAgent / Todo 状态机调度"),
    (4, "🧰 8.4 工具注册与分发机制", "s04_tool_registry.py", "@tool 装饰器 / JSON Schema 生成 / 路由"),
    (5, "💻 8.5 终端执行与代码编辑", "s05_terminal_and_edit.py", "run_bash 沙箱 / str_replace 精准行替换"),
    (6, "🛡️ 8.6 权限控制与人类在环", "s06_permissions_hitl.py", "PermissionGuard / 四级风险门禁 / HITL 审核"),
    (7, "🪝 8.7 Hooks 生命周期", "s07_hooks_lifecycle.py", "HookManager / Pre & Post AOP 拦截 / 脱敏打点"),
    (8, "🗜️ 8.8 上下文工程与压缩", "s08_context_compact.py", "ContextManager / 0ms 滑动截断 / /compact 深度摘要"),
    (9, "🧠 8.9 记忆系统与技能挂载", "s09_memory_and_skills.py", "MemoryStore / SkillLoader / SKILL.md 动态挂载"),
    (10, "👥 8.10 Subagents 多智能体协作", "s10_subagents.py", "DeepResearchPipeline / 4 专家上下文隔离流水线"),
    (11, "🗂️ 8.11 会话持久化与多分支", "s11_session.py", "SessionStore / 树状分叉 / 平行宇宙存档"),
    (12, "📡 8.12 可观测性与性能评估", "s12_observability.py", "EventBus / TokenCostAudit / 验证器评测套件"),
    (13, "🤖 8.13 Mini-Agent 综合实战", "s13_mini_agent.py", "MiniAgent / 深度思考 + 联网搜索 + 个人超级助理"),
]

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter

code_formatter = HtmlFormatter(style="one-dark", linenos="table", cssclass="code-highlight")
pygments_css = code_formatter.get_style_defs(".code-highlight")

def get_chapter_code(chapter_num: int) -> str:
    """读取指定章节的 Python 原生完整源码"""
    filename = ""
    for num, _, f, _ in CHAPTERS:
        if num == chapter_num:
            filename = f
            break
    if not filename:
        return "# 暂无代码"
    
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(filepath):
        return f"# 未找到源码文件：{filename}"
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"# 读取源码失败：{e}"

def render_code_viewer_html(chapter_num: int) -> str:
    """使用 Pygments 纯原生渲染带行号与 OneDark 配色的 Python 源码（100% 稳定高亮，零组件坍缩风险）"""
    filename = CHAPTERS[0][2]
    desc = CHAPTERS[0][3]
    for num, _, f, d in CHAPTERS:
        if num == chapter_num:
            filename = f
            desc = d
            break
            
    code_text = get_chapter_code(chapter_num)
    highlighted = highlight(code_text, PythonLexer(), code_formatter)
    
    return f"""
    <div class="code-header-bar">
        <span class="code-file-tag">📄 code/{filename}</span>
        <span class="code-desc-tag">{desc}</span>
    </div>
    <div class="code-scroll-pane">
        {highlighted}
    </div>
    """

# ==============================================================================
# 🎨 现代化 IDE 风格高对比度 CSS (高度精准对齐)
# ==============================================================================
custom_css = pygments_css + "\n" + """

/* 全局页面宽度自适应铺满 */
.gradio-container {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif !important;
    max-width: 98% !important;
    width: 98% !important;
    margin: 0 auto !important;
    padding: 8px 16px !important;
}

/* 顶部 Hero 区域 - 高对比度明晰设计 */
.hero-container {
    background: linear-gradient(135deg, #090d16 0%, #1e1b4b 50%, #0f172a 100%) !important;
    border-radius: 16px !important;
    padding: 18px 24px !important;
    margin-bottom: 12px !important;
    color: #ffffff !important;
    box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.4) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
}

.hero-top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    flex-wrap: wrap;
    gap: 10px;
}

.hero-tagline {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(99, 102, 241, 0.4) !important;
    border: 1px solid #818cf8 !important;
    color: #e0e7ff !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 4px 14px !important;
    border-radius: 9999px !important;
}
.hero-tagline span {
    color: #e0e7ff !important;
}

.pulse-dot {
    width: 8px;
    height: 8px;
    background-color: #34d399;
    border-radius: 50%;
    box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.8);
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.8); }
    70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(52, 211, 153, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
}

.hero-title {
    font-size: 23px !important;
    font-weight: 800 !important;
    line-height: 1.3 !important;
    margin: 4px 0 6px 0 !important;
    color: #ffffff !important;
    text-shadow: 0 2px 4px rgba(0,0,0,0.5);
}

.hero-desc {
    font-size: 13px !important;
    line-height: 1.6 !important;
    color: #f1f5f9 !important;
    margin: 0 0 10px 0 !important;
    max-width: 1200px !important;
}
.hero-desc b, .hero-desc strong {
    color: #38bdf8 !important;
    font-weight: 700 !important;
}

.hero-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.badge-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.16) !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
    padding: 3px 10px !important;
    border-radius: 8px !important;
    font-size: 12px !important;
    color: #ffffff !important;
    font-weight: 500 !important;
}

/* 左侧章节导航容器：高度跟随自身宽度，避免固定像素卡片 */
.sidebar-container {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 12px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    aspect-ratio: 2 / 5 !important;
    overflow-y: auto !important;
}

.sidebar-title {
    font-size: 13.5px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    margin-bottom: 10px !important;
    padding-bottom: 8px !important;
    border-bottom: 2px solid #f1f5f9 !important;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.chapter-nav-radio .wrap {
    display: flex !important;
    flex-direction: column !important;
    gap: 5px !important;
}

.chapter-nav-radio label {
    display: flex !important;
    align-items: center !important;
    padding: 8px 10px !important;
    border-radius: 8px !important;
    border: 1px solid #e2e8f0 !important;
    background: #f8fafc !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    color: #1e293b !important;
}

.chapter-nav-radio label:hover {
    background: #eef2ff !important;
    border-color: #c7d2fe !important;
    color: #4338ca !important;
}

.chapter-nav-radio label.selected {
    background: #4f46e5 !important;
    border-color: #4338ca !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.25) !important;
}
.chapter-nav-radio label.selected * {
    color: #ffffff !important;
}

/* 💻 中间/左侧代码视窗容器：以列宽决定高度，和右侧保持同一比例 */
.code-viewer-panel {
    background: #282c34 !important;
    border: 1px solid #3e4451 !important;
    border-radius: 12px !important;
    padding: 12px 14px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    aspect-ratio: 4 / 5 !important;
    overflow: hidden !important;
    display: grid !important;
    grid-template-rows: auto minmax(0, 1fr) !important;
    flex-direction: column !important;
    box-sizing: border-box !important;
}

.code-header-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 8px;
    margin-bottom: 8px;
    border-bottom: 1px solid #3e4451;
    flex-shrink: 0;
}
.code-file-tag {
    background: #21252b;
    color: #61afef;
    border: 1px solid #3e4451;
    font-size: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 6px;
}
.code-desc-tag {
    font-size: 12px;
    color: #9da5b4;
}

/* 源码视窗：单层原生滚动，绝不坍缩，零套娃 */
.code-scroll-pane {
    min-height: 0 !important;
    height: auto !important;
    flex: 1 1 auto !important;
    max-height: none;
    overflow-y: scroll !important;
    overflow-x: auto;
    border-radius: 8px;
    background: #282c34;
    scrollbar-width: auto;
    scrollbar-color: #64748b #1f2430;
}

/* Gradio HTML 组件会默认按内容撑高；把中间包装层也压进网格轨道，滚轮才真正属于源码窗格 */
.code-viewer-panel > .block,
.code-viewer-panel .html-container,
.code-viewer-panel .prose {
    min-height: 0 !important;
    height: 100% !important;
    overflow: hidden !important;
}
.code-viewer-panel .html-container,
.code-viewer-panel .prose {
    display: flex !important;
    flex-direction: column !important;
}

.code-scroll-pane::-webkit-scrollbar {
    width: 11px;
    height: 11px;
}
.code-scroll-pane::-webkit-scrollbar-track {
    background: #1f2430;
    border-radius: 8px;
}
.code-scroll-pane::-webkit-scrollbar-thumb {
    background: #64748b;
    border: 2px solid #1f2430;
    border-radius: 8px;
}
.code-scroll-pane::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
}

.code-highlighttable {
    width: 100%;
    border-collapse: collapse;
    margin: 0;
    font-size: 12.5px;
    line-height: 1.55;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

.code-highlighttable td.linenos {
    width: 45px;
    user-select: none;
    text-align: right;
    padding-right: 12px;
    color: #5c6370;
    border-right: 1px solid #3e4451;
    vertical-align: top;
}

.code-highlighttable td.code {
    padding-left: 12px;
    vertical-align: top;
}

.code-highlighttable pre {
    margin: 0;
    padding: 0;
    font-family: inherit;
    font-size: inherit;
    line-height: inherit;
    white-space: pre;
}

/* 🛠️ 右侧沙箱工作台容器：与代码视窗使用同一宽高比例 */
.playground-panel {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 14px 16px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    aspect-ratio: 4 / 5 !important;
    overflow-y: auto !important;
}

/* 章节头部说明卡片 */
.chapter-header-card {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-left: 4px solid #6366f1;
    padding: 10px 14px;
    border-radius: 0 10px 10px 0;
    margin-bottom: 10px;
    border-top: 1px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #e2e8f0;
}
.chapter-header-title {
    font-size: 14.5px;
    font-weight: 700;
    color: #0f172a !important;
    margin-bottom: 2px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.chapter-header-desc {
    font-size: 12px;
    color: #334155 !important;
    margin: 0;
    line-height: 1.4;
}

/* 代码联动提示横条 */
.linkage-bar {
    background: #eef2ff;
    border: 1px solid #c7d2fe;
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 11.5px;
    color: #3730a3;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* 流式打字机高质感输出卡片 */
.typewriter-output-card {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 14px 16px !important;
    min-height: 0 !important;
    max-height: none !important;
    aspect-ratio: 16 / 9 !important;
    overflow-y: auto !important;
    font-size: 13.5px !important;
    line-height: 1.7 !important;
    color: #0f172a !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}

/* macOS 风格终端容器 */
.mac-terminal {
    background-color: #0f172a;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 8px 12px -2px rgba(0, 0, 0, 0.3);
    border: 1px solid #334155;
    margin-bottom: 8px;
}
.mac-titlebar {
    background-color: #1e293b;
    padding: 5px 10px;
    display: flex;
    align-items: center;
    gap: 6px;
    border-bottom: 1px solid #334155;
}
.mac-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    display: inline-block;
}
.dot-red { background-color: #ef4444; }
.dot-yellow { background-color: #f59e0b; }
.dot-green { background-color: #10b981; }
.mac-title {
    font-size: 11.5px;
    color: #94a3b8;
    font-family: monospace;
    margin-left: 6px;
}

/* KPI 指标卡片网格 */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 8px;
    margin: 8px 0;
}
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 8px;
    min-height: 0;
    aspect-ratio: 1.8 / 1;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.kpi-value {
    font-size: 16px;
    font-weight: 800;
    color: #4338ca !important;
    margin-bottom: 1px;
}
.kpi-label {
    font-size: 11px;
    color: #475569 !important;
    font-weight: 600;
}

/* 智能体多角色流水线指示条 */
.pipeline-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 6px 10px;
    margin-bottom: 8px;
    overflow-x: auto;
}
.pipeline-step {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11.5px;
    font-weight: 600;
    color: #1e293b !important;
    white-space: nowrap;
}
.pipeline-arrow {
    color: #94a3b8;
    font-weight: bold;
}

/* 8.13 多轮 Chatbot 对话框美化 */
.chat-container-box {
    border-radius: 12px !important;
    border: 1px solid #e2e8f0 !important;
    background: #f8fafc !important;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.02) !important;
    height: clamp(260px, 32vh, 430px) !important;
    min-height: 0 !important;
    max-height: 430px !important;
    aspect-ratio: auto !important;
}

/* 8.13 对话区：收紧信息层级，避免“巨型空白 + 控件散落” */
.mini-agent-view {
    display: flex !important;
    flex-direction: column !important;
    gap: 12px !important;
}
.mini-agent-view .chapter-header-card,
.mini-agent-view .linkage-bar {
    margin-bottom: 0 !important;
}
.mini-agent-view .mini-shortcuts {
    display: grid !important;
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    gap: 10px !important;
}
.mini-agent-view .mini-shortcuts > *,
.mini-agent-view .mini-input-row > *,
.mini-agent-view .mini-options-row > * {
    min-width: 0 !important;
}
.mini-agent-view .mini-input-row {
    align-items: stretch !important;
    gap: 10px !important;
}
.mini-agent-view .mini-input-row textarea {
    min-height: 56px !important;
}
.mini-agent-view .mini-input-row button {
    min-height: 56px !important;
}
.mini-agent-view .mini-options-row {
    align-items: stretch !important;
    gap: 10px !important;
}
.mini-agent-view .mini-options-row > .block {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 10px !important;
}
.mini-agent-view .mini-memory-row {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 8px 12px !important;
}
.mini-agent-view .mini-trace {
    margin-top: 0 !important;
    border-top: 1px solid #e2e8f0 !important;
}

/* 8.11 会话分支：一个按钮 + 一个结果区 */
.session-demo-shell {
    display: flex !important;
    flex-direction: column !important;
    gap: 12px !important;
}
.session-action-box {
    background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%) !important;
    border: 1px solid #c7d2fe !important;
    border-radius: 16px !important;
    padding: 14px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}
.session-action-box button {
    width: 100% !important;
    min-height: 58px !important;
    font-size: 18px !important;
    font-weight: 800 !important;
}
.session-result-card {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 16px !important;
    padding: 14px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}
.session-result-card .session-result-title {
    font-size: 14px !important;
    font-weight: 800 !important;
    color: #0f172a !important;
    margin-bottom: 4px !important;
}
.session-result-card .session-result-note {
    font-size: 12px !important;
    color: #64748b !important;
    margin-bottom: 10px !important;
}
.session-result-card .block {
    min-height: 0 !important;
}
.session-result-output {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 12px 14px !important;
}
.session-result-output h3 {
    margin-top: 0.35rem !important;
    font-size: 14px !important;
}

/* 小屏幕改为自然高度，避免窄屏下比例卡片过矮或内容拥挤 */
@media (max-width: 900px) {
    .sidebar-container,
    .code-viewer-panel,
    .playground-panel,
    .typewriter-output-card,
    .chat-container-box {
        aspect-ratio: auto !important;
    }

    .sidebar-container,
    .code-viewer-panel,
    .playground-panel {
        min-height: 360px !important;
    }

    .code-scroll-pane {
        min-height: 300px !important;
        height: 300px !important;
    }

    .mini-agent-view .mini-shortcuts {
        grid-template-columns: 1fr !important;
    }

    .mini-agent-view .mini-options-row {
        flex-direction: column !important;
    }

    .session-action-box button {
        min-height: 52px !important;
        font-size: 16px !important;
    }
}

/* 页脚 */
.footer-container {
    text-align: center;
    padding: 14px 0 6px 0;
    margin-top: 14px;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 12px;
}
"""

custom_theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="slate",
    neutral_hue="slate",
    radius_size="lg",
)

# ==============================================================================
# 🛠️ 构建 Gradio Blocks 主应用
# ==============================================================================
with gr.Blocks(
    title="🛠️ 手搓 Agent 全通关工作台 | Vibe Coding",
    fill_width=True,
) as demo:

    # 🌟 顶部炫彩科技 Hero 头部（纯净极简，配置自动走 .env）
    gr.HTML("""
    <div class="hero-container">
        <div class="hero-top-bar">
            <div class="hero-tagline">
                <span class="pulse-dot"></span>
                <span>Vibe Coding · 现代智能体核心教程代码库</span>
            </div>
            <div style="display:flex; align-items:center; gap:12px;">
                <span style="font-size:12.5px; color:#e2e8f0; font-weight:500;">
                    🟢 智谱 GLM-5.3-Flash 主力 + 火山方舟灾备 (.env 已自动载入)
                </span>
            </div>
        </div>
        <h1 class="hero-title">🛠️ 第八章：手搓 Agent —— 从 0 到 1 打造 AI 智能体内核</h1>
        <p class="hero-desc">
            打破黑盒依赖！<b>左侧实时对照 Python 原生底层源码</b>，<b>右侧运行交互沙箱与多轮对话推演</b>。
            涵盖 <b>ReAct 闭环</b>、<b>规划范式</b>、<b>工具分发</b>、<b>权限门禁</b>、<b>上下文压缩</b> 与 <b>多轮记忆对话</b>。
        </p>
        <div class="hero-badges">
            <span class="badge-item">🎯 13 个原生代码模块</span>
            <span class="badge-item">💻 源码下拉视窗与高度对齐</span>
            <span class="badge-item">💬 8.13 多轮对话</span>
            <span class="badge-item">🛡️ 权限门禁前端实时审计</span>
            <span class="badge-item">🚀 真实流式 Token 打字机</span>
        </div>
    </div>
    """)

    # 当前选中小节状态
    state_curr_chapter = gr.State(1)

    # ==========================================================================
    # 🌟 核心布局：【最左侧导航】 + 【中间代码视窗】 + 【右侧交互沙箱】 (高度精准对齐 740px)
    # ==========================================================================
    with gr.Row():

        # ----------------------------------------------------------------------
        # 1. 最左侧：垂直章节导航栏 (Scale 2, 紧凑整洁)
        # ----------------------------------------------------------------------
        with gr.Column(scale=2, min_width=200, elem_classes=["sidebar-container"]):
            gr.HTML("""
            <div class="sidebar-title">
                <span>📚 章节实战目录</span>
                <span style="font-size:11px; color:#6366f1; font-weight:600;">13 模块</span>
            </div>
            """)
            nav_radio = gr.Radio(
                choices=[name for _, name, _, _ in CHAPTERS],
                value=CHAPTERS[0][1],
                label="选择实战章节",
                show_label=False,
                elem_classes=["chapter-nav-radio"],
            )

        # ----------------------------------------------------------------------
        # 2. 中间/左侧：对应章节 Python 原生完整源码视窗 (Pygments OneDark 高亮，单层原生滚动)
        # ----------------------------------------------------------------------
        with gr.Column(scale=5, elem_classes=["code-viewer-panel"]) as code_col:
            code_display = gr.HTML(
                value=render_code_viewer_html(1),
            )

        # ----------------------------------------------------------------------
        # 3. 右侧栏：13 个章节对应的交互实战工作台 (高度 740px 对齐)
        # ----------------------------------------------------------------------
        with gr.Column(scale=5, elem_classes=["playground-panel"]) as playground_col:

            # ==================================================================
            # 模块 1: 8.1 环境基建与模型接入
            # ==================================================================
            with gr.Column(visible=True) as view_1:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">📡 8.1 裸调智谱 BigModel API 与流式打字机机制</div>
                    <p class="chapter-header-desc">Agent 最底层的基石是与大模型的双向流式通信。通过 SSE 逐字获取 Token，消除等待焦虑，构建打字机效果。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>右侧输入触发 <code>ZhipuGLMClient.chat_stream()</code>，逐字吐出 Token 并带呼吸光标</span>
                </div>
                """)
                t1_input = gr.Textbox(
                    label="💬 输入你的 Prompt", 
                    value="用一句话通俗解释什么是 Agent 的第一性原理？",
                    lines=2
                )
                with gr.Row():
                    t1_btn1 = gr.Button("🎯 Agent 第一性原理", size="sm")
                    t1_btn2 = gr.Button("⚡ 流式打字机原理", size="sm")
                    t1_btn3 = gr.Button("🔄 ReAct 与规划区别", size="sm")
                t1_submit = gr.Button("🚀 发送流式对话 (调用 chat_stream)", variant="primary")
                
                gr.Markdown("#### 🖥️ 模型流式打字机响应")
                t1_output = gr.Markdown(value="*(等待发送指令…)*", elem_classes=["typewriter-output-card"])

                t1_btn1.click(lambda: "用一句话通俗解释什么是 Agent 的第一性原理？", outputs=[t1_input])
                t1_btn2.click(lambda: "用日常生活中的比喻，通俗解释大模型流式打字机（Stream）的底层工作原理。", outputs=[t1_input])
                t1_btn3.click(lambda: "通俗对比 ReAct（边想边做）和 Plan-and-Execute（先想后做）两种 Agent 思考范式。", outputs=[t1_input])

                def tab1_stream(prompt):
                    if not prompt or not prompt.strip():
                        yield "⚠️ 请输入有效的 Prompt！"
                        return
                    text = ""
                    try:
                        for chunk in global_client.chat_stream([{"role": "user", "content": prompt}]):
                            for char in chunk:
                                text += char
                                yield text + " ▌"
                                time.sleep(0.012)
                        yield text
                    except Exception as e:
                        yield f"❌ 模型调用异常: {e}"

                t1_submit.click(tab1_stream, inputs=[t1_input], outputs=[t1_output])

            # ==================================================================
            # 模块 2: 8.2 ReAct 思考范式
            # ==================================================================
            with gr.Column(visible=False) as view_2:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🔄 8.2 手写 Thought ➔ Action ➔ Observation 极简闭环</div>
                    <p class="chapter-header-desc">ReAct (Reasoning + Acting) 经典闭环：通过自然语言推演（Thought）、执行工具（Action）、捕获环境反馈（Observation），循环迭代直至得出最终答案。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>点击运行将实例化 <code>ReActAgent(global_client).run()</code>，观察正则解析与单步推演</span>
                </div>
                """)
                t2_query = gr.Textbox(label="用户复杂提问", value="北京和深圳现在的气温加起来是多少度？", lines=2)
                with gr.Row():
                    t2_btn_q1 = gr.Button("🌡️ 北京和深圳气温总和？", size="sm")
                    t2_btn_q2 = gr.Button("💰 员工 101 税后收入计算", size="sm")
                t2_btn = gr.Button("🧠 运行 ReAct 思考推演 (调用 ReActAgent.run)", variant="primary")
                t2_ans = gr.Textbox(label="🎯 最终答案 (Final Answer)", lines=3)
                t2_log = gr.JSON(label="🔍 步骤追踪 (Thought / Action / Observation Trace)")

                t2_btn_q1.click(lambda: "北京和深圳现在的气温加起来是多少度？", outputs=[t2_query])
                t2_btn_q2.click(lambda: "查询员工 101 的档案并计算他的基本工资加上 5000 奖金后的税后总收入", outputs=[t2_query])

                def tab2_run(query):
                    if not query or not query.strip():
                        yield "⚠️ 请输入有效的问题！", []
                        return
                    agent = ReActAgent(global_client)
                    yield from agent.run_stream(query)
                t2_btn.click(tab2_run, inputs=[t2_query], outputs=[t2_ans, t2_log])

            # ==================================================================
            # 模块 3: 8.3 Plan & Execute 规划范式
            # ==================================================================
            with gr.Column(visible=False) as view_3:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">📋 8.3 意图拆解、Todo 状态机与逐步执行</div>
                    <p class="chapter-header-desc">先规划后执行：将宏观目标分解为 Todo 状态机（Pending ➔ In Progress ➔ Completed），避免长链路迷失方向。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>调用 <code>PlanAndExecuteAgent.run_all_stream()</code>：实时推送 Todo 状态流转与单步产出</span>
                </div>
                """)
                t3_goal = gr.Textbox(label="宏观目标 (Goal)", value="为一家独立精品咖啡店设计会员成长与积分体系方案", lines=2)
                with gr.Row():
                    t3_g1 = gr.Button("☕ 独立咖啡店会员体系", size="sm")
                    t3_g2 = gr.Button("📱 记账小程序架构规划", size="sm")
                t3_btn = gr.Button("📝 拆解并全自动执行 (调用 run_all_stream)", variant="primary")
                t3_status = gr.Textbox(label="当前进度状态", lines=1)
                t3_todos = gr.JSON(label="Todo 状态机清单 (Pending -> In Progress -> Completed)")
                t3_summary = gr.Markdown("### 📄 交付汇总报告\n*(执行过程中将在此实时流式累加每步交付报告)*")

                t3_g1.click(lambda: "为一家独立精品咖啡店设计会员成长与积分体系方案", outputs=[t3_goal])
                t3_g2.click(lambda: "规划一款支持语音记账与自动分类的个人记账小程序架构与开发步骤", outputs=[t3_goal])

                def tab3_run(goal):
                    if not goal or not goal.strip():
                        yield "⚠️ 请输入有效的宏观目标！", [], ""
                        return
                    agent = PlanAndExecuteAgent(global_client)
                    yield from agent.run_all_stream(goal)
                t3_btn.click(tab3_run, inputs=[t3_goal], outputs=[t3_status, t3_todos, t3_summary])

            # ==================================================================
            # 模块 4: 8.4 工具注册与分发
            # ==================================================================
            with gr.Column(visible=False) as view_4:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🧰 8.4 @tool 装饰器、JSON Schema 自动生成与分发机</div>
                    <p class="chapter-header-desc">利用 Python 装饰器与反射机制，自动提取函数签名与 Docstring 生成 OpenAI 兼容的 Tools JSON Schema，大模型自主决策路由。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>查看左侧 <code>@tool</code> 装饰器如何自动反射生成右侧下方的 <code>tools schema</code></span>
                </div>
                """)
                t4_input = gr.Textbox(
                    label="用户指令", 
                    value="帮我查询员工 101 的档案，并计算基本工资 30000 加上奖金 8000 的税后收入（税率 20%）", 
                    lines=2
                )
                t4_btn = gr.Button("🛠️ 触发 Function Calling 路由 (调用 chat_with_tools)", variant="primary")
                t4_ans = gr.Textbox(label="模型整合回复", lines=3)
                t4_schemas = gr.JSON(label="自动生成的 Tools JSON Schema")
                t4_calls = gr.JSON(label="底层工具调用握手报文 (Tool Call / Tool Message)")

                def tab4_run(query):
                    if not query or not query.strip():
                        yield "⚠️ 请输入有效的指令！", [], []
                        return
                    agent = FunctionCallingAgent(global_client, registry)
                    yield from agent.chat_with_tools_stream(query)
                t4_btn.click(tab4_run, inputs=[t4_input], outputs=[t4_ans, t4_schemas, t4_calls])

            # ==================================================================
            # 模块 5: 8.5 终端执行与代码编辑
            # ==================================================================
            with gr.Column(visible=False) as view_5:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">💻 8.5 Bash 命令执行与 Claude Code 招牌 str_replace 精准行替换</div>
                    <p class="chapter-header-desc">AI 编程助手的两大底层手脚：安全的 Shell 终端执行沙箱与基于上下文唯一定位的文本精准替换算法。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>分别调用左侧 <code>run_bash()</code> 子进程执行 与 <code>str_replace()</code> 文本行替换生成 Diff</span>
                </div>
                """)
                gr.Markdown("#### ⚡ 1. 终端执行测试 (run_bash)")
                t5_cmd = gr.Textbox(label="Shell 命令", value="python3 -c 'import sys, platform; print(f\"Python {sys.version.split()[0]} on {platform.system()}\")'")
                with gr.Row():
                    t5_cmd_preset1 = gr.Button("🐍 Python 版本", size="sm")
                    t5_cmd_preset2 = gr.Button("📁 目录清单", size="sm")
                t5_cmd_btn = gr.Button("⚡ 运行终端命令 (run_bash)")
                
                gr.HTML("""
                <div class="mac-terminal">
                    <div class="mac-titlebar">
                        <span class="mac-dot dot-red"></span>
                        <span class="mac-dot dot-yellow"></span>
                        <span class="mac-dot dot-green"></span>
                        <span class="mac-title">bash ~ /vibe_coding</span>
                    </div>
                </div>
                """)
                t5_cmd_out = gr.Textbox(label="终端标准输出 (stdout / stderr)", lines=2)
                
                t5_cmd_preset1.click(lambda: "python3 -c 'import sys; print(f\"Python: {sys.version}\")'", outputs=[t5_cmd])
                t5_cmd_preset2.click(lambda: "ls -lh", outputs=[t5_cmd])
                t5_cmd_btn.click(run_bash, inputs=[t5_cmd], outputs=[t5_cmd_out])

                gr.Markdown("#### ✂️ 2. 精准行替换算法 (str_replace)")
                t5_fpath = gr.Textbox(label="目标文件路径", value="sample_code.py")
                t5_old = gr.Textbox(label="待替换原始文本 (old_str)", value="name = 'world'", lines=1)
                t5_new = gr.Textbox(label="替换后目标文本 (new_str)", value="name = 'Vibe Coding 智能体'", lines=1)
                t5_edit_btn = gr.Button("✂️ 执行精准替换并生成 Diff", variant="primary")
                t5_diff = gr.Textbox(label="Unified Diff 变更视图 (+ / -)", lines=3)

                def tab5_edit(fpath, old_s, new_s):
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write("def greet():\n    name = 'world'\n    print(f'hello {name}')\n")
                    ok, msg, diff = str_replace(fpath, old_s, new_s)
                    return diff or msg
                t5_edit_btn.click(tab5_edit, inputs=[t5_fpath, t5_old, t5_new], outputs=[t5_diff])

            # ==================================================================
            # 模块 6: 8.6 权限控制与人类在环
            # ==================================================================
            with gr.Column(visible=False) as view_6:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🛡️ 8.6 危险指令门禁与 Human-in-the-Loop 审核拦截</div>
                    <p class="chapter-header-desc">建立 LOW / MEDIUM / HIGH / CRITICAL 四级安全防御梯次，对高危文件删除、系统级命令实施人类在环确认拦截。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>调用 <code>PermissionGuard.evaluate_risk()</code> 规则匹配与拦截决策</span>
                </div>
                """)
                t6_tool = gr.Dropdown(label="调用的工具", choices=["run_bash", "str_replace", "view_file"], value="run_bash")
                t6_arg = gr.Textbox(label="工具参数 (如命令或文件路径)", value="rm -rf /", lines=1)
                with gr.Row():
                    t6_p1 = gr.Button("🟢 安全查看 (ls -la)", size="sm")
                    t6_p2 = gr.Button("🟡 配置文件修改", size="sm")
                    t6_p3 = gr.Button("🔴 危险删除 (rm -rf /)", size="sm")
                t6_btn = gr.Button("🔍 风险评估与安全门禁审查", variant="primary")
                t6_risk = gr.HTML('<div class="status-pill status-info">请点击按钮进行风险评估</div>')
                t6_res = gr.JSON(label="安全门禁决策详细结果")

                t6_p1.click(lambda: ("run_bash", "ls -la"), outputs=[t6_tool, t6_arg])
                t6_p2.click(lambda: ("str_replace", "config.yaml"), outputs=[t6_tool, t6_arg])
                t6_p3.click(lambda: ("run_bash", "rm -rf /"), outputs=[t6_tool, t6_arg])

                def tab6_eval(tool, arg):
                    guard = PermissionGuard()
                    args = {"command": arg} if tool == "run_bash" else {"file_path": arg, "old_str": "a", "new_str": "b"}
                    risk, reason = guard.evaluate_risk(tool, args)
                    res = guard.check_and_execute(tool, args, lambda **kw: "模拟执行成功", interactive_prompt=False)
                    
                    risk_colors = {
                        "safe": "#10b981",
                        "moderate": "#f59e0b",
                        "critical": "#ef4444"
                    }
                    color = risk_colors.get(risk.value.lower(), "#64748b")
                    html = f"""
                    <div style="padding:10px 14px; border-radius:8px; background:#ffffff; border:1px solid #e2e8f0; margin-bottom:8px;">
                        <div style="font-size:11.5px; color:#475569;">风险评级判定</div>
                        <div style="font-size:16px; font-weight:800; color:{color};">等级：{risk.value.upper()}</div>
                        <div style="font-size:12px; color:#0f172a; margin-top:3px;"><b>判定原因：</b>{reason}</div>
                    </div>
                    """
                    return html, res
                t6_btn.click(tab6_eval, inputs=[t6_tool, t6_arg], outputs=[t6_risk, t6_res])

            # ==================================================================
            # 模块 7: 8.7 Hooks 生命周期
            # ==================================================================
            with gr.Column(visible=False) as view_7:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🪝 8.7 AOP 切面拦截、自动敏感信息脱敏与耗时统计</div>
                    <p class="chapter-header-desc">借鉴企业级 AOP 切面思想，通过 pre_tool 与 post_tool 钩子，对 Agent 工具执行前进行参数修正，对执行后进行 API Key 自动脱敏与性能耗时采集。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>调用 <code>HookManager.run_pre_tool()</code> 与 <code>run_post_tool()</code> 完成全链路加工</span>
                </div>
                <div class="pipeline-bar">
                    <div class="pipeline-step"><span>1️⃣ Pre-Tool</span></div>
                    <div class="pipeline-arrow">➔</div>
                    <div class="pipeline-step"><span>2️⃣ Tool Exec</span></div>
                    <div class="pipeline-arrow">➔</div>
                    <div class="pipeline-step"><span>3️⃣ Post-Tool 脱敏</span></div>
                </div>
                """)
                t7_input = gr.Textbox(
                    label="模拟返回含敏感信息的原始文本", 
                    value="数据库连接成功: host=127.0.0.1, key=sk-abcdef1234567890xyz, endpoint=glm-20250225123456-abcdef", 
                    lines=2
                )
                t7_btn = gr.Button("🧪 触发生命周期 Hooks 加工", variant="primary")
                t7_output = gr.Textbox(label="脱敏与耗时加工后的产出 (已遮蔽 sk-*** 并注入耗时)", lines=3)

                def tab7_run(raw_text):
                    hm = create_default_hook_manager()
                    args = hm.run_pre_tool("mock_tool", {"dummy": 1})
                    final_res = hm.run_post_tool("mock_tool", args, raw_text)
                    return final_res
                t7_btn.click(tab7_run, inputs=[t7_input], outputs=[t7_output])

            # ==================================================================
            # 模块 8: 8.8 上下文工程与压缩
            # ==================================================================
            with gr.Column(visible=False) as view_8:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🗜️ 8.8 上下文工程双轨体系：0ms 滑动窗口截断 vs /compact 深度语义压缩</div>
                    <p class="chapter-header-desc">超长对话如何既不爆 Token 又不失忆？工业级 Harness 提供两大核心策略：截断轨（0ms 零成本硬丢弃过期轮次与工具首尾折叠）+ 压缩轨（调用 LLM 提炼结构化事实与前情提要）。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>分别调用 <code>ContextManager.truncate_sliding_window()</code>、<code>compact_history()</code> 与 <code>compare_all_strategies()</code></span>
                </div>
                """)

                # 预设长对话与长日志文本
                preset_ecommerce = """用户：你好，我正在用 Vue3 + FastAPI 重构电商系统的收银台模块，请帮我设计前后端架构。
助理：收到！建议采用分层架构：前端 Pinia 管理支付状态机（Pending/Paying/Success/Failed），后端 FastAPI 提供防重下单接口，接入微信与支付宝 SDK，使用 Redis 分布式锁保障幂等性。
用户：我按照你的建议写了支付接口，但是压测时并发一高就报 500 错误，日志显示：psycopg2.OperationalError: deadlock detected，该怎么排查？
助理：这是高并发下的数据库死锁！原因是在更新库存表 (inventory) 和创建订单表 (orders) 时加锁顺序不一致。排查方案：
1. 统一所有事务内的加锁顺序（始终先锁 orders 再锁 inventory）；
2. 使用 SELECT ... FOR UPDATE 时按商品 ID 升序排序加锁；
3. 将扣减库存逻辑改为原子 SQL：UPDATE inventory SET stock = stock - 1 WHERE id = 101 AND stock > 0。
用户：改完原子 SQL 后死锁解决了！现在前端想接入二维码轮询支付状态，帮我写个轮询组件。
助理：没问题，这是使用 Vue3 <script setup> 编写的支付二维码与 2 秒间隔轮询组件代码：
```vue
<template>
  <div class="pay-box">
    <img :src="qrCodeUrl" />
    <p v-if="paying">支付中，请使用微信扫码...</p>
  </div>
</template>
<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
const paying = ref(true);
let timer = null;
const checkStatus = async () => {
  const res = await fetch('/api/pay/status');
  if (res.status === 200) { paying.value = false; clearInterval(timer); }
};
onMounted(() => { timer = setInterval(checkStatus, 2000); });
onUnmounted(() => { clearInterval(timer); });
</script>
```
用户：太棒了！现在支付已联调通过。接下来我们要开发退款审批流模块，需要对接财务 ERP。
助理：收到，退款审批流建议设计为状态机：用户申请 ➔ 客服初审 ➔ 财务复核 ➔ 触发原路退款 ➔ 同步 ERP 凭证。我为你生成退款数据表模型与审批状态枚举。"""

                preset_microservices = """用户：我们正在将单体电商拆分为用户服务、订单服务、库存服务与支付服务，内部 RPC 选型用 gRPC 还是 HTTP REST？
助理：高并发内部通信强烈推荐 gRPC（基于 HTTP/2 + Protobuf，二进制序列化性能高出 5~10 倍，且支持双向流式传输）；对外暴露的 API 网关保留标准 HTTP RESTful。
用户：拆分后出现分布式事务问题：用户支付成功但库存扣减网络超时，导致订单状态不一致，该怎么解决？
助理：分布式事务在互联网高并发场景下不建议使用阻塞性能极差的 2PC/XA，推荐「Saga 最终一致性」或「本地消息表 + MQ 保证原子性」：
1. 订单服务在本地数据库事务中同时写入订单记录和一条 Outbox 事件消息；
2. 异步轮询或 CDC 组件将 Outbox 消息可靠投递到 Kafka/RabbitMQ；
3. 库存服务消费消息扣减库存，消费成功后发送 ACK，下游接口实现幂等去重。
用户：我们在压测 Kafka 消费者时发现了严重消息堆积，日志报 ConnectionResetError，怎么排查？
助理：排查思路与优化建议：
1. 检查消费者单次拉取消息量 max.poll.records 是否过大，导致单批次业务处理时间超过 max.poll.interval.ms 触发了 Consumer Group 重平衡 (Rebalance)；
2. 调小单次拉取量（如 500 降至 50），将下游 DB 写入改为批量 ExecuteMany；
3. 为无法解析的异常消息建立死信队列 (DLQ)，防止单个毒丸消息阻塞全队列。
用户：调整 max.poll.records 从 500 降到 50 并加入批量插入后，消费堆积恢复正常！接下来帮我配置 Prometheus 告警指标。
助理：已为你整理核心告警指标：`kafka_consumergroup_lag`（消费延迟水位）、`http_requests_duration_seconds`（P99 接口时延）与 `process_resident_memory_bytes`（服务内存水位）。"""

                preset_logs = "\n".join([
                    f"[2026-08-27 10:00:{i:02d}] INFO Service-Worker-{i%4}: processing build batch {i}, status=200, thread_pool_active=8, memory_usage=512MB"
                    for i in range(120)
                ])

                gr.Markdown("#### 📚 1. 选择或输入真实长对话 / 超长工具输出")
                with gr.Row():
                    t8_p1 = gr.Button("🛒 1. 电商全栈开发与支付排错 (~1800 Tokens)", size="sm")
                    t8_p2 = gr.Button("🐛 2. 微服务重构与分布式排错 (~2200 Tokens)", size="sm")
                    t8_p3 = gr.Button("📊 3. 120行超长终端编译日志 (工具截断专用)", size="sm")

                t8_long_input = gr.Textbox(
                    label="💬 对话历史 / 终端长日志 (支持自由编辑修改)", 
                    value=preset_ecommerce, 
                    lines=6
                )

                gr.Markdown("#### 🛠️ 2. 执行双轨上下文策略")
                with gr.Row():
                    t8_budget_slider = gr.Slider(
                        minimum=200, 
                        maximum=1200, 
                        value=500, 
                        step=50, 
                        label="🎛️ 滑动窗口 Token 预算上限 (仅对滑动截断生效)"
                    )
                
                with gr.Row():
                    t8_btn_truncate = gr.Button("✂️ 策略一：滑动窗口截断 (0ms 零成本)", variant="secondary")
                    t8_btn_compact = gr.Button("📦 策略二：/compact 深度历史压缩 (LLM提炼Facts)", variant="primary")
                    t8_btn_compare = gr.Button("⚖️ 策略三：全策略多维度对比矩阵", variant="secondary")
                    t8_btn_tool = gr.Button("🪵 工具超长输出首尾截断 (Head+Tail)", size="sm")

                t8_summary_info = gr.Markdown("### 📊 处理收益与策略报告\n*(点击上方按钮执行对应上下文工程策略)*")
                t8_res_json = gr.JSON(label="加工后的上下文消息列表 (Messages)")

                # 按钮绑定预设
                t8_p1.click(lambda: preset_ecommerce, outputs=[t8_long_input])
                t8_p2.click(lambda: preset_microservices, outputs=[t8_long_input])
                t8_p3.click(lambda: preset_logs, outputs=[t8_long_input])

                # 策略 1：滑动截断
                def tab8_truncate_handler(text, budget):
                    if not text or not text.strip():
                        return "⚠️ 请输入有效的对话文本！", []
                    msgs = parse_raw_dialogue_to_messages(text)
                    cm = ContextManager(global_client)
                    trunc_msgs, info, dropped = cm.truncate_sliding_window(msgs, max_tokens=int(budget))
                    report = f"""### ✂️ 【滑动窗口截断】执行报告 (Sliding Window Truncation)
> **特点**：⚡ **0ms 延迟**、💰 **0 API 消耗**。锁定 System Prompt，从最旧消息向前逐条剔除。

- **原始消息数**：{len(msgs)} 条 (估算 {estimate_tokens(msgs)} Tokens)
- **截断后消息数**：{len(trunc_msgs)} 条 (估算 {estimate_tokens(trunc_msgs)} Tokens)
- **丢弃过期消息**：{dropped} 条
- **信息保留度**：⚠️ **中低**（早期交互细节硬丢失，仅保留 System 设定与最近几轮）

```
{info}
```
"""
                    return report, trunc_msgs

                t8_btn_truncate.click(tab8_truncate_handler, inputs=[t8_long_input, t8_budget_slider], outputs=[t8_summary_info, t8_res_json])

                # 策略 2：/compact 深度压缩
                def tab8_compact_handler(text):
                    if not text or not text.strip():
                        return "⚠️ 请输入有效的对话文本！", []
                    msgs = parse_raw_dialogue_to_messages(text)
                    raw_tokens = estimate_tokens(msgs)
                    cm = ContextManager(global_client)
                    compact_msgs, info = cm.compact_history(msgs)
                    compact_tokens = estimate_tokens(compact_msgs)
                    saved_tokens = max(0, raw_tokens - compact_tokens)
                    saved_rate = (saved_tokens / max(raw_tokens, 1)) * 100

                    report = f"""### 📦 【/compact 深度历史压缩】执行报告 (Deep History Summary)
> **特点**：🧠 **大模型语义理解提炼**，将多轮繁杂试错浓缩为《前情提要与事实备忘》，保留项目关键决策与已修 Bug。

- **Token 变化**：从 **{raw_tokens}** 骤降至 **{compact_tokens}** Tokens
- **净释放空间**：**{saved_tokens}** Tokens (压缩率 **{saved_rate:.1f}%**)
- **信息保留度**：🌟 **极高**（业务目标、技术栈、修改文件、解决的问题全部结构化继承）

```
{info}
```
"""
                    return report, compact_msgs

                t8_btn_compact.click(tab8_compact_handler, inputs=[t8_long_input], outputs=[t8_summary_info, t8_res_json])

                # 策略 3：全策略对比矩阵
                def tab8_compare_handler(text, budget):
                    if not text or not text.strip():
                        return "⚠️ 请输入有效的对话文本！", {}
                    msgs = parse_raw_dialogue_to_messages(text)
                    cm = ContextManager(global_client)
                    res = cm.compare_all_strategies(msgs, budget_tokens=int(budget))
                    
                    report = f"""### ⚖️ 【全策略多维度对比矩阵】(Strategy Comparison Matrix)

| 策略方案 | Token 占用 | 压缩/释放幅度 | 执行耗时 | 信息保留能力 | 推荐适用场景 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. 原始未处理 (Raw)** | **{res['raw']['tokens']}** | 0% | 0 ms | 100% (但容易迷失/费用爆炸) | 短会话 (< 1000 Tokens) |
| **2. 滑动窗口截断 (Truncation)** | **{res['truncation']['tokens']}** | 释放 {res['truncation']['saved_rate']} | **{res['truncation']['latency_ms']} ms** (极速) | ⚠️ 低 (早期旧记忆彻底丢弃) | 实时性要求极高、单次独立查询 |
| **3. /compact 深度压缩 (Compact)** | **{res['compact']['tokens']}** | 压缩率 **{res['compact']['saved_rate']}** | ~1-2 s (调LLM) | 🌟 **极高** (核心事实全结构化提炼) | 持续项目开发、长程排错与代码重构 |
"""
                    return report, res

                t8_btn_compare.click(tab8_compare_handler, inputs=[t8_long_input, t8_budget_slider], outputs=[t8_summary_info, t8_res_json])

                # 策略 4：工具超长输出首尾截断
                def tab8_tool_handler(text):
                    if not text or not text.strip():
                        return "⚠️ 请输入日志文本！", []
                    cm = ContextManager(global_client)
                    lines = text.strip().splitlines()
                    truncated = cm.truncate_tool_result(text, line_limit=20)
                    trunc_lines = truncated.splitlines()
                    report = f"""### 🪵 【工具超长输出首尾截断】执行报告 (Tool Result Budget)
- **原始行数**：{len(lines)} 行
- **截断后行数**：{len(trunc_lines)} 行 (保留首 10 行 + 尾 10 行，中间折叠)
- **防爆原理**：终端编译日志、数据库查询结果动辄上千行，直接回填会撑爆上下文；首尾保留既看到了启动参数，又看到了最终退出码与报错！
"""
                    return report, [{"role": "tool_result", "content": truncated}]

                t8_btn_tool.click(tab8_tool_handler, inputs=[t8_long_input], outputs=[t8_summary_info, t8_res_json])

            # ==================================================================
            # 模块 9: 8.9 记忆系统与技能挂载
            # ==================================================================
            with gr.Column(visible=False) as view_9:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🧠 8.9 长期偏好记忆持久化与 SKILL.md 动态挂载</div>
                    <p class="chapter-header-desc">MemoryStore 负责跨会话记忆读写，SkillLoader 负责动态读取技能文件并组装增强型 System Prompt。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>调用 <code>MemoryStore.remember()</code> 写入文件与 <code>SkillLoader.assemble_system_prompt()</code> 组装</span>
                </div>
                """)
                mem_store = MemoryStore("gradio_agent_memory.json")
                skill_ldr = SkillLoader("skills")
                
                gr.Markdown("#### 💾 1. 记忆写入与持久化")
                t9_k = gr.Textbox(label="记忆键名 (Key)", value="技术栈偏好")
                t9_v = gr.Textbox(label="记忆内容 (Value)", value="前后端分离架构，前端使用 TailwindCSS，后端使用 FastAPI")
                t9_save_btn = gr.Button("💾 保存到长期记忆库")
                t9_mem_status = gr.HTML('<div class="status-pill status-info">记忆状态：就绪</div>')
                
                gr.Markdown("#### 🧩 2. 动态技能包挂载")
                t9_skills = gr.CheckboxGroup(
                    label="勾选动态挂载的技能包 (Skills)", 
                    choices=skill_ldr.list_skills(), 
                    value=skill_ldr.list_skills()
                )
                t9_gen_btn = gr.Button("⚡ 生成组装后的增强 System Prompt", variant="primary")
                t9_preview = gr.Textbox(label="增强型 System Prompt 最终预览", lines=6)

                def tab9_save(k, v):
                    mem_store.remember(k, v)
                    return f'<div class="status-pill status-success">✅ 已成功保存记忆: <b>[{k}]</b> ➔ {v}</div>'
                t9_save_btn.click(tab9_save, inputs=[t9_k, t9_v], outputs=[t9_mem_status])

                def tab9_gen(skills):
                    return skill_ldr.assemble_system_prompt("你是一个资深全栈架构师。", skills, mem_store)
                t9_gen_btn.click(tab9_gen, inputs=[t9_skills], outputs=[t9_preview])

            # ==================================================================
            # 模块 10: 8.10 Subagents 多智能体协作
            # ==================================================================
            with gr.Column(visible=False) as view_10:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">👥 8.10 上下文隔离与 DeepResearch 四专家流水线</div>
                    <p class="chapter-header-desc">多智能体协同模式：将复杂研报任务按职责拆解为 4 位专家智能体，独立上下文运行，避免长上下文相互污染。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>调用 <code>DeepResearchPipeline.execute_research()</code> 顺序流转 4 位专家智能体</span>
                </div>
                """)
                t10_topic = gr.Textbox(label="深度研究课题", value="2026年 Agentic Coding 与传统 IDE 的架构融合趋势", lines=2)
                with gr.Row():
                    t10_p1 = gr.Button("🚀 2026 Agentic Coding 趋势", size="sm")
                    t10_p2 = gr.Button("🔒 端侧部署与隐私计算", size="sm")
                t10_btn = gr.Button("🚀 启动 4 专家协同深度研究", variant="primary")
                t10_status = gr.Textbox(label="协同流水线状态", lines=2)
                t10_trace = gr.JSON(label="多智能体上下文隔离流转日志 (Timeline)")
                t10_report = gr.Markdown("### 📑 终极深度分析研报\n*(研究完成后在此呈现 4 位专家联袂打造的结构化报告)*")

                t10_p1.click(lambda: "2026年 Agentic Coding 与传统 IDE 的架构融合趋势", outputs=[t10_topic])
                t10_p2.click(lambda: "大模型在端侧与移动设备部署的技术挑战与隐私计算方案", outputs=[t10_topic])

                def tab10_run(topic):
                    if not topic or not topic.strip():
                        yield "⚠️ 请输入有效的研究课题！", [], ""
                        return
                    pipeline = DeepResearchPipeline(global_client, search_provider=WebSearch().search)
                    yield from pipeline.execute_research_stream(topic)
                t10_btn.click(tab10_run, inputs=[t10_topic], outputs=[t10_status, t10_trace, t10_report])

            # ==================================================================
            # 模块 11: 8.11 会话持久化与多分支
            # ==================================================================
            with gr.Column(visible=False) as view_11:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🗂️ 8.11 会话存档 / 读档 / 分叉 / 导出 —— 给 Agent 装上平行宇宙</div>
                    <p class="chapter-header-desc">基于树状结构管理对话 Session，支持从任意历史节点开辟平行宇宙分支（Branching），并一键导出完整 Markdown 记录。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>点击按钮后，下面的结果区会同时展示会话树摘要与导出预览</span>
                </div>
                """)
                with gr.Column(elem_classes=["session-demo-shell"]):
                    with gr.Column(elem_classes=["session-action-box"]):
                        gr.HTML('<div class="session-result-title">▶︎ 先点这个按钮</div><div class="session-result-note">它会一次性跑完主会话、双分支、恢复和导出。</div>')
                        t11_btn = gr.Button("🌿 运行主会话 → 双分支 → 恢复 → 导出", variant="primary")
                    with gr.Column(elem_classes=["session-result-card"]):
                        gr.HTML('<div class="session-result-title">结果区</div><div class="session-result-note">下面这块只负责看结果，不负责触发操作。</div>')
                        t11_result = gr.Markdown(
                            "点击上方按钮后，这里会一次性显示会话树摘要和 Markdown 导出预览。",
                            elem_classes=["session-result-output"],
                        )

                def tab11_run():
                    store = SessionStore("gradio_sessions")
                    result = demo_tree_branching(store)
                    sessions_json = json.dumps(store.list_sessions(), ensure_ascii=False, indent=2)
                    return (
                        "### 🌳 会话树摘要\n"
                        f"```json\n{sessions_json}\n```\n\n"
                        "### 📄 Markdown 导出预览\n"
                        f"```markdown\n{result['export_md'][:1500]}\n```"
                    )
                t11_btn.click(tab11_run, outputs=t11_result)

            # ==================================================================
            # 模块 12: 8.12 可观测性与性能评估
            # ==================================================================
            with gr.Column(visible=False) as view_12:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">📡 8.12 事件总线 + Token 费用审计 + 评估套件 (本地 Mock 演示)</div>
                    <p class="chapter-header-desc">采集 EventBus 轨迹与 Token/时延，并用任务验证器判断结果是否真的正确；未配置官方价格时不估算费用。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b><code>EventBus</code> 收集事件，<code>EvalCase.validator</code> 验证答案，<code>TokenCostAudit</code> 统计用量</span>
                </div>
                <div class="kpi-grid">
                    <div class="kpi-card"><div class="kpi-value">Validator</div><div class="kpi-label">🎯 结果判定方式</div></div>
                    <div class="kpi-card"><div class="kpi-value">2 × 3</div><div class="kpi-label">📊 Mock 任务与轮次</div></div>
                    <div class="kpi-card"><div class="kpi-value">Trace</div><div class="kpi-label">⚡ 事件轨迹回放</div></div>
                    <div class="kpi-card"><div class="kpi-value">显式配置</div><div class="kpi-label">💰 官方模型价格</div></div>
                </div>
                """)
                with gr.Row():
                    t12_btn = gr.Button("🎯 本地 Mock 评估 (2 任务 × 3 次)", size="sm")
                    t12_real_btn = gr.Button("🚀 真实引擎联动评估 (s01+s02 ReActAgent)", size="sm", variant="primary")
                t12_trace = gr.Textbox(label="🔍 轨迹事件流回放预览", lines=5)
                t12_report = gr.JSON(label="完整评估报告 (成功率 / 时延 / Token / 账单)")
                t12_cost = gr.Markdown("### 💰 费用审计账单\n*(运行评估后在此呈现精细化财务核算)*")

                def _tab12_build(report, task_key):
                    cost_md = f"```text\n{report['summary']['cost_audit']}\n```"
                    trace_lines = [
                        f"[{ev['event_type']:>10}] {ev['content'][:40]} (tokens={ev['tokens']}, {ev['latency_ms']:.0f}ms)"
                        for ev in report["tasks"][task_key]["traces"][0]["events"]
                    ]
                    return "\n".join(trace_lines), report, cost_md

                def tab12_run_mock():
                    report = run_mock_eval()
                    return _tab12_build(report, list(report["tasks"])[0])

                def tab12_run_real():
                    try:
                        report = run_real_agent_eval(client=global_client)
                        return _tab12_build(report, list(report["tasks"])[0])
                    except Exception as e:
                        return f"❌ 真实引擎评估失败（请检查 .env 的 ZHIPU_API_KEY）：{e}", {}, f"```text\n{e}\n```"

                t12_btn.click(tab12_run_mock, outputs=[t12_trace, t12_report, t12_cost])
                t12_real_btn.click(tab12_run_real, outputs=[t12_trace, t12_report, t12_cost])

            # ==================================================================
            # 模块 13: 8.13 Mini-Agent 综合实战 (ChatGPT / Codex 风格多轮连续对话)
            # ==================================================================
            with gr.Column(visible=False, elem_classes=["mini-agent-view"]) as view_13:
                gr.HTML("""
                <div class="chapter-header-card">
                    <div class="chapter-header-title">🤖 8.13 个人 Mini-Agent：Codex / ChatGPT 风格多轮连续对话</div>
                    <p class="chapter-header-desc">支持连续多轮上下文记忆、深度思考推演、实时联网搜索、技能插件挂载与权限门禁实时审计。</p>
                </div>
                <div class="linkage-bar">
                    <span>⚡ <b>代码联动：</b>持续调用 <code>MiniAgent.chat()</code>，自动继承多轮对话上下文并写入 <code>SessionStore</code> 存档</span>
                </div>
                """)
                
                # 多轮 Agent 实例状态与会话历史
                state_mini_agent = gr.State(None)
                
                # 💬 ChatGPT / Codex 风格对话视窗 (气泡流)
                t13_chatbot = gr.Chatbot(
                    label="💬 智能体多轮对话流",
                    show_label=False,
                    elem_classes=["chat-container-box"],
                )
                
                # 预设快捷提示词
                with gr.Row(elem_classes=["mini-shortcuts"]):
                    t13_p1 = gr.Button("🌐 2026 前端框架新趋势", size="sm")
                    t13_p2 = gr.Button("💾 记住我的偏好: Python+FastAPI", size="sm")
                    t13_p3 = gr.Button("❓ 问刚才记住的偏好", size="sm")

                # 输入框与多功能按钮
                with gr.Row(elem_classes=["mini-input-row"]):
                    t13_msg_input = gr.Textbox(
                        placeholder="💬 输入消息，按回车或点击发送进行连续多轮对话...",
                        lines=1,
                        max_lines=3,
                        scale=7,
                        show_label=False,
                        container=False,
                    )
                    t13_send_btn = gr.Button("🚀 发送", variant="primary", scale=1)
                    t13_clear_btn = gr.Button("🗑️ 清空重置", variant="secondary", scale=1)

                # 增强选项与插件挂载
                with gr.Row(elem_classes=["mini-options-row"]):
                    t13_opts = gr.CheckboxGroup(
                        label="🚀 增强模式", 
                        choices=["🧠 深度思考", "🔍 强制联网搜索"], 
                        value=["🧠 深度思考"]
                    )
                    t13_skills = gr.CheckboxGroup(
                        label="🧩 挂载技能插件", 
                        choices=["git_expert", "python_cleaner"], 
                        value=[]
                    )
                with gr.Row(elem_classes=["mini-memory-row"]):
                    t13_allow_memory = gr.Checkbox(
                    label="💾 允许本轮保存偏好（仅授权 save_preference，不放行终端或代码编辑）",
                    value=False,
                    )
                
                # 决策与权限审批 Trace
                with gr.Accordion("🔍 决策流与权限门禁审计 Trace (permission_gate / tool_call / finish)", open=False, elem_classes=["mini-trace"]):
                    t13_trace = gr.JSON(label="决策链路跟踪与权限审计事件")

                # 预设按钮事件
                t13_p1.click(lambda: "2026年最新的主流前端框架有哪些新趋势？请联网核实", outputs=[t13_msg_input])
                t13_p2.click(lambda: "请记住我的偏好：我的全栈技术栈首选是 Python + FastAPI + TailwindCSS", outputs=[t13_msg_input])
                t13_p3.click(lambda: "我之前跟你说过的技术栈偏好是什么？请帮我写一个用户注册接口", outputs=[t13_msg_input])

                # 多轮连续对话主函数（支持动态就绪与状态推进）
                def mini_agent_chat_turn(user_msg, chat_history, agent_inst, opts, skills, allow_memory):
                    if not user_msg or not user_msg.strip():
                        yield chat_history, "", agent_inst, []
                        return
                    
                    if agent_inst is None:
                        agent_inst = MiniAgent(global_client)
                    # 每轮重新绑定最小权限回调，取消勾选后授权立即失效。
                    agent_inst.guard.approval_callback = (
                        lambda tool_name, _args: bool(allow_memory) and tool_name == "save_preference"
                    )
                    
                    chat_history = chat_history or []
                    # 追加用户问题气泡与临时就绪状态（Gradio 6 仅支持 messages 格式）
                    chat_history.append({"role": "user", "content": user_msg})
                    chat_history.append({"role": "assistant", "content": "⏳ *(Agent 正在分析意图与调度推演...)*"})
                    yield chat_history, "", agent_inst, []
                    
                    deep = "🧠 深度思考" in opts
                    if deep:
                        chat_history[-1]["content"] = "🧠 *(正在进行深度思考与前置规划推演...)*"
                        yield chat_history, "", agent_inst, []

                    if "🔍 强制联网搜索" in opts:
                        if not any(m.get("content", "").startswith("用户要求你优先调用 web_search") for m in agent_inst.messages):
                            agent_inst.messages.append({
                                "role": "system",
                                "content": "用户要求你优先调用 web_search 联网检索后再回答。请在获取到搜索结果后直接总结输出最终答案，不要重复搜索。"
                            })
                    
                    # 执行 Agent 多轮对话（内部自动维护上下文与持久化）
                    res = agent_inst.chat(user_msg, deep_think=deep, active_skills=skills)
                    ans = polish_markdown(res["final_answer"])
                    usage_badge = res.get("usage_badge", "")

                    if usage_badge:
                        # 📊 作为消息气泡的下方附属
                        ans_with_badge = (
                            f"{ans}\n\n---\n"
                            f"<div style='font-size:11px; color:#475569; font-family:ui-monospace, Menlo, monospace; "
                            f"background:#f8fafc; padding:4px 9px; border-radius:6px; border:1px solid #e2e8f0; "
                            f"display:inline-block; margin-top:4px;'>{usage_badge}</div>"
                        )
                    else:
                        ans_with_badge = ans

                    # 更新助手回复气泡
                    chat_history[-1]["content"] = ans_with_badge
                    yield chat_history, "", agent_inst, res["trace"]

                # 清空上下文重置
                def mini_agent_reset():
                    new_agent = MiniAgent(global_client)
                    return [], "", new_agent, []

                t13_send_btn.click(
                    mini_agent_chat_turn,
                    inputs=[t13_msg_input, t13_chatbot, state_mini_agent, t13_opts, t13_skills, t13_allow_memory],
                    outputs=[t13_chatbot, t13_msg_input, state_mini_agent, t13_trace],
                )
                t13_msg_input.submit(
                    mini_agent_chat_turn,
                    inputs=[t13_msg_input, t13_chatbot, state_mini_agent, t13_opts, t13_skills, t13_allow_memory],
                    outputs=[t13_chatbot, t13_msg_input, state_mini_agent, t13_trace],
                )
                t13_clear_btn.click(
                    mini_agent_reset,
                    outputs=[t13_chatbot, t13_msg_input, state_mini_agent, t13_trace],
                )

            # 视图收集数组
            all_views = [view_1, view_2, view_3, view_4, view_5, view_6, view_7, view_8, view_9, view_10, view_11, view_12, view_13]

    # ==========================================================================
    # 🌟 交互路由与代码联动逻辑
    # ==========================================================================
    
    # 1. 切换章节 -> 联动更新完整源码高亮、小节状态与右侧沙箱
    def handle_chapter_nav(selected_label):
        chap_num = 1
        for num, name, filename, desc in CHAPTERS:
            if name == selected_label:
                chap_num = num
                break
        
        # 纯原生 HTML 高亮渲染（带行号、OneDark配色、单层滚动、绝对不坍缩）
        code_html = render_code_viewer_html(chap_num)
        
        # 13 个视图显隐更新
        view_updates = [gr.update(visible=(i == (chap_num - 1))) for i in range(13)]
        return (*view_updates, code_html, chap_num)

    nav_radio.change(
        handle_chapter_nav,
        inputs=[nav_radio],
        outputs=[*all_views, code_display, state_curr_chapter],
    )

    # 底部说明与版权
    gr.HTML("""
    <div class="footer-container">
        <p><b>Vibe Coding · AI 辅助编程与 Agent 概念理论教学知识库</b> | MIT License</p>
        <p style="font-size:12px; margin-top:3px;">基于 智谱 BigModel GLM-5.3-Flash 与 火山方舟 DeepSeek-V4-Flash 跨厂商高可用架构</p>
    </div>
    """)

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1", 
        server_port=7860, 
        share=False,
        theme=custom_theme,
        css=custom_css,
    )
