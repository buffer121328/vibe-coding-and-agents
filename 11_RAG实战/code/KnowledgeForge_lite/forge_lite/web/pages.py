"""web/pages.py —— 控制台的页面结构（零构建，手写 HTML）。

这层只出结构：三段壳层（深色侧边栏 / 白顶栏 / 内容区），
外观全在 ``static/console.css``，行为在 ``static/workbench.js`` 与 ``static/console.js``。

壳层与信息架构对齐完整版 KnowledgeForge（``frontend/src/components/Layout.tsx``）：
侧边栏按「知识应用 / 治理与合规」分组，顶栏左边是面包屑加页面标题。
唯一不同的是右上角：完整版放登录用户，Lite 放四张可点的工牌——
**先看清权限，再选身份**，这是本产品的演示核心。

图标是手写的 24 栅格描边 SVG（``stroke-width`` 统一 1.7）。``air`` 没有 SVG
元素，所以走 ``air.Raw`` 内联；名字不在表里就画一个中性方框，不静默消失。
"""

from __future__ import annotations

import air

# ── 图标 ────────────────────────────────────────────────────────

_ICONS = {
    "chat": "M20 12a7 7 0 0 1-7 7H8l-4 3v-4.4A7 7 0 0 1 8 5h5a7 7 0 0 1 7 7Z",
    "doc": "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Zm0 0v5h5M9 13h6M9 17h4",
    "eval": "M9 3h6M10 3v6.2L5.6 17A2 2 0 0 0 7.4 20h9.2a2 2 0 0 0 1.8-3L14 9.2V3M7.5 15h9",
    "fold": "M4 6h16M4 12h9M4 18h16M17 10l3 2-3 2",
    "unfold": "M4 6h16M4 12h16M4 18h16",
    "menu": "M4 6h16M4 12h16M4 18h16",
    "info": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v.5m0 3.5v5",
    "upload": "M12 16V4m0 0L8 8m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2",
    "play": "M7 4.5v15l12-7.5-12-7.5Z",
    "refresh": "M20 11a8 8 0 1 0-1.2 5M20 5v6h-6",
    "plus": "M12 5v14M5 12h14",
    "export": "M12 4v12m0 0 4-4m-4 4-4-4M4 18v1a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-1",
    "chevron": "m9 6 6 6-6 6",
    "close": "M6 6l12 12M18 6 6 18",
    "user": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 0c-3.3 0-6 2.2-6 5v2h12v-2c0-2.8-2.7-5-6-5Z",
    "robot": "M12 3v3M7 8h10a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2Zm2.5 4.5v.5m5-.5v.5M9.5 14h5",
    "logout": "M15 12H4m0 0 3-3m-3 3 3 3M12 4h6a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6",
    "thumbs-up": "M7 21V11l4-8a2 2 0 0 1 2 2v4h5.4a2 2 0 0 1 2 2.4l-1.3 7A2 2 0 0 1 17 20H7Zm0 0H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1h3",
    "thumbs-down": "M17 3v10l-4 8a2 2 0 0 1-2-2v-4H5.6a2 2 0 0 1-2-2.4l1.3-7A2 2 0 0 1 7 4h10Zm0 0h3a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-3",
    "flag": "M5 21V4m0 0 6 1.5 8-1.5v10l-8 1.5L5 14",
}


def icon(name: str, class_: str = "icon") -> air.Raw:
    """引用一个 24 栅格描边图标。

    ``name`` 是 ``_ICONS`` 里的键（如 ``"doc"`` / ``"chat"``），查不到就画一个中性方框——
    图标缺失不该让页面塌掉，但也不该静默消失。
    ``class_`` 是挂在 ``<svg>`` 上的类名，默认 ``icon``（16px）。
    图标本体只在页面顶部渲染一次（见 ``icon_sprite``），这里出的只是 ``<use>`` 引用。
    """
    if name not in _ICONS:
        name = "box"
    return air.Raw(
        f'<svg class="{class_}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'
    )


def icon_sprite() -> air.Raw:
    """把整套图标渲染成 ``<symbol>`` 集合，每页一次。

    服务端用 ``icon()`` 引用、前端用 ``workbench.js`` 的 ``ico()`` 引用，
    两边指向同一份定义——图标只有一处真相，不会漂。返回一段隐藏的 ``<svg>``。
    """
    symbols = "".join(
        f'<symbol id="i-{name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{path}"/></symbol>'
        for name, path in _ICONS.items()
    )
    return air.Raw(f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{symbols}</svg>')


# ── 导航：与完整版 navigation.ts 同构，只保留 Lite 有后端的页面 ──

NAV_GROUPS = (
    ("知识应用", (("qa", "智能问答", "chat"), ("docs", "知识文档", "doc"))),
    ("治理与合规", (("eval", "评测治理", "eval"),)),
)
PAGE_NAMES = {key: label for _group, items in NAV_GROUPS for key, label, _icon in items}


def _nav_item(key: str, label: str, icon_name: str, first: bool) -> air.Button:
    """侧边栏的一个导航项。

    ``key`` 是视图名（``qa`` / ``docs`` / ``eval``），同时用来拼 id ``nav-{key}``；
    ``label`` 是显示文字；``icon_name`` 取 ``_ICONS`` 的键；
    ``first`` 为真时带上 ``is-on``（页面首屏默认选中第一项）。返回一个按钮。
    """
    return air.Button(
        icon(icon_name, "icon"),
        air.Span(label),
        type="button", id=f"nav-{key}", data_view=key,
        class_="nav-item" + (" is-on" if first else ""),
        role="tab",
    )


def _nav() -> air.Aside:
    """左侧深色导航栏：品牌块 + 按组分节的导航 + 底部收起按钮。

    分组结构对着完整版 ``Layout.tsx`` 的 ``groupLabels``——「知识应用 / 治理与合规」，
    只是这里只保留 Lite 有后端的页面。返回一个 ``<aside>``。
    """
    groups = []
    first = True
    for title, items in NAV_GROUPS:
        buttons = []
        for key, label, icon_name in items:
            buttons.append(_nav_item(key, label, icon_name, first))
            first = False
        groups.append(air.Div(air.P(title, class_="nav-group-title"), *buttons, class_="nav-group"))
    return air.Aside(
        air.Div(
            air.Div("KF", class_="brand-mark"),
            air.Div(air.Strong("KnowledgeForge"), air.Span("Lite · Enterprise AI")),
            class_="brand",
        ),
        air.Nav(*groups, class_="nav", aria_label="主导航"),
        air.Div(
            air.Button(icon("fold", "icon"), air.Span("收起导航"), type="button", id="sider-toggle"),
            class_="sider-foot",
        ),
        class_="sider", id="sider",
    )


def _header() -> air.Header:
    """顶栏：左边面包屑压页面标题，右边演示工牌架 + 账号区。

    账号区是完整版 ``Layout.tsx`` 的 user menu（头像 + 显示名 + 角色·部门 + 退出登录）；
    左边的工牌架是 Lite 额外挂的演示身份切换器，完整版没有这一块。
    返回一个 ``<header>``。
    """
    return air.Header(
        air.Div(
            air.Button(icon("menu", "icon"), type="button", id="nav-open",
                       class_="btn sider-toggle", aria_label="打开导航"),
            air.Div(
                air.P(air.B("管理控制台"), air.B(" / "), air.B(PAGE_NAMES["qa"], id="crumb-page"), class_="crumb"),
                air.Span(PAGE_NAMES["qa"], id="page-name", class_="page-name"),
            ),
            class_="",
        ),
        air.Div(
            # 账号区：头像 + 显示名 + 角色·部门（完整版 Layout 的 user menu）。
            # 顶栏**只放身份**——工牌对照是课堂教具，挪到问答区去了。
            air.Div(
                air.Button(
                    air.Div("KF", class_="avatar", id="account-avatar"),
                    air.Div(
                        air.Strong("访客", id="account-name"),
                        air.Span("未登录", id="account-meta"),
                        class_="account-copy",
                    ),
                    type="button", class_="btn", aria_label="账号菜单",
                ),
                air.Div(
                    air.Button(icon("logout", "icon"), air.Span("退出登录"), type="button", id="account-logout"),
                    class_="menu", id="account-menu", hidden=True,
                ),
                class_="account-menu",
            ),
            class_="account",
        ),
        class_="header",
    )


def _tabs(items: tuple, prefix: str) -> air.Div:
    """一排选项卡。

    ``items`` 是 ``(key, label)`` 的序列，第一个默认选中；
    ``prefix`` 直接拼在 key 前面拼出 id：``"tab-"`` → ``tab-catalog``，
    ``"docs-tab-"`` → ``docs-tab-list``。返回一个 ``<div class="tabs">``。
    """
    return air.Div(
        *[
            air.Button(label, type="button", id=f"{prefix}{key}", data_tab=key,
                       class_="tab" + (" is-on" if index == 0 else ""), role="tab")
            for index, (key, label) in enumerate(items)
        ],
        class_="tabs",
    )


# ── 智能问答 ────────────────────────────────────────────────────


def _drawer(name: str, title: str) -> air.Aside:
    """右侧滑入的抽屉，看详情用。

    ``name`` 是抽屉标识（``qa`` / ``docs`` / ``eval``），用来拼 id
    ``{name}-drawer``、``{name}-drawer-title``、``{name}-drawer-body`` 等；
    ``title`` 是标题栏文字，也是无障碍标签。
    完整版的 ``Drawer`` 是同一个用法。返回一个默认隐藏的 ``<aside>``。
    """
    return air.Aside(
        air.Div(
            air.Div(
                air.H3(title, id=f"{name}-drawer-title"),
                air.P("—", id=f"{name}-drawer-sub", class_="sub"),
            ),
            air.Button(icon("close", "icon"), type="button", id=f"{name}-drawer-close",
                       class_="drawer-close", aria_label="关闭"),
            class_="drawer-head",
        ),
        air.Div(id=f"{name}-drawer-body", class_="drawer-body"),
        class_="drawer", id=f"{name}-drawer", hidden=True,
        role="dialog", aria_label=title,
    )


def _qa_view() -> air.Div:
    """智能问答视图：左历史会话卡 + 右对话卡，证据开在抽屉里。

    两栏等高（靠 CSS 的 ``height: calc(100vh - ...)``），左边列会话、右边列消息，
    卡片内部各自滚动。证据（目录/出处/轨迹）不做常驻第三栏——常驻会把对话挤窄，
    完整版也是抽屉。返回一个 ``<div id="view-qa">``。
    """
    return air.Div(
        # 权限对照条：四张工牌一行排开，各带「可见 N / 裁掉 M」。
        # 它是课堂教具，所以待在课程内容里，而不是待在应用框架的顶栏上；
        # 点一下仍然是切换演示身份——那一步是"权限先于检索"这条结论能落地的关键。
        air.Div(
            air.Span("演示身份", class_="identity-label"),
            air.Div(id="badge-rack", class_="rack", role="radiogroup", aria_label="演示工牌"),
            air.Span("换一张牌再问同一句，看答案从作答变拒答", class_="identity-hint"),
            class_="identity-bar",
        ),
        # 两栏网格单独一层：外层负责"对照条 + 网格"的纵向排布，
        # 内层负责 280px + 1fr 的左右分栏。两者是同一个 div 的话 flex 和 grid 会打架。
        air.Div(
        air.Section(
            air.Div(
                air.H3("历史会话"),
                air.Button(icon("plus", "icon"), type="button", id="new-conv",
                           class_="btn is-sm", aria_label="新会话"),
                class_="card-head",
            ),
            air.Div(id="drawers", class_="conv-list"),
            class_="card qa-history",
        ),
        air.Section(
            air.Div(
                air.H3("智能问答"),
                air.Div(
                    air.Button(icon("doc", "icon"), air.Span("可见文档"), type="button",
                               id="qa-open-catalog", class_="btn is-sm"),
                    air.Button(icon("export", "icon"), air.Span("导出"), type="button",
                               id="export-conv", class_="btn is-sm"),
                    class_="page-actions",
                ),
                class_="card-head",
            ),
            air.Div(id="transcript", class_="turns"),
            air.Form(
                air.Textarea(id="q", name="question", rows=1, class_="textarea",
                             placeholder="输入问题，Enter 发送，Shift+Enter 换行"),
                air.Button(icon("play", "icon"), air.Span("发送"), type="submit",
                           id="ask-btn", class_="btn is-primary"),
                class_="composer", id="ask-form",
            ),
            air.P(id="status", class_="msg"),
            class_="card thread",
        ),
        air.Aside(
            air.Div(
                _tabs((("catalog", "目录"), ("chunk", "出处"), ("trace", "轨迹")), "tab-"),
                air.Button(icon("close", "icon"), type="button", id="qa-drawer-close",
                           class_="drawer-close", aria_label="关闭"),
                class_="drawer-head",
            ),
            air.Div(id="evidence-body", class_="drawer-body", role="tabpanel", aria_label="证据抽屉"),
            class_="drawer", id="qa-drawer", hidden=True, role="dialog", aria_label="证据",
        ),
            class_="qa",
        ),
        class_="view is-on qa-view", id="view-qa", data_view="qa",
    )


# ── 知识文档 ────────────────────────────────────────────────────


def _lab_panel() -> air.Section:
    """切块实验台：同一段文本换个尺寸与重叠，切块结果立刻变。"""
    return air.Section(
        air.Div(
            air.H3("切块实验台"),
            air.Span("还没选文档", id="lab-source", class_="muted"),
            class_="card-head",
        ),
        air.Div(
            air.P("把一段文本按不同尺寸与重叠切一遍。这里只算不落盘、不调模型——"
                  "所以可以随便试；试好了要真生效，得改 .env 里的旋钮再重建索引。", class_="hint"),
            air.Textarea(id="lab-text", rows=6, class_="textarea",
                         placeholder="粘一段制度原文，或先在上面的表里点一行的「看切块」把正文带过来"),
            air.Div(
                air.Label(air.Span("每块字数"),
                          air.Input(id="lab-size", type="number", min="50", max="2000",
                                    step="10", class_="input"), class_="field"),
                air.Label(air.Span("重叠字数"),
                          air.Input(id="lab-overlap", type="number", min="0", max="400",
                                    step="10", class_="input"), class_="field"),
                air.Button(icon("refresh", "icon"), air.Span("重切一次"), type="button",
                           id="lab-apply", class_="btn is-primary"),
                air.Button("恢复默认", type="button", id="lab-reset", class_="btn"),
                class_="page-actions",
            ),
            air.P(id="lab-message", class_="msg"),
            air.Div(id="lab-stats", class_="lab-stats"),
            air.Div(id="lab-chunks", class_="chunks"),
            class_="card-body lab",
        ),
        class_="card",
    )


def _docs_view() -> air.Div:
    """知识文档视图：页面头 + 选项卡（列表 / 上传）+ 统计卡 + 表格 + 切块实验台。

    列表和上传是两个选项卡而不是两块堆叠内容——一屏只回答一个问题。
    表格与切块详情分成"列表"和"抽屉"，点「查看分块」开抽屉。
    返回一个 ``<div id="view-docs">``。
    """
    return air.Div(
        air.Div(
            air.Div(
                icon("doc", "page-icon"),
                air.Div(
                    air.H2("知识文档"),
                    air.P("上传即入库：解析 → 清洗 → 切块 → 投毒扫描 → 写入索引。"
                          "被隔离的留在账本里但不进检索——为什么被挡下，写在它那一行。",
                          class_="page-desc"),
                ),
                class_="page-head-main",
            ),
            air.Div(
                air.Button(icon("refresh", "icon"), air.Span("刷新列表"), type="button",
                           id="docs-refresh", class_="btn"),
                class_="page-actions",
            ),
            class_="page-head",
        ),
        air.Div(
            _tabs((("list", "已入库文档"), ("upload", "文档上传")), "docs-tab-"),
            class_="card-head",
        ),
        air.Div(
            air.Div(id="docs-summary", class_="stats"),
            air.Div(id="docs-locked", class_="locked", hidden=True),
            air.Div(id="docs-table", class_="table-wrap"),
            class_="card",
            id="docs-panel-list",
        ),
        air.Div(
            air.Div(
                air.Label(
                    icon("upload", "icon"),
                    air.Span("把文件拖到这里，或"),
                    air.Input(id="docs-file", type="file", multiple=True, class_="visually-hidden"),
                    air.Span("选择文件", class_="link-like"),
                    air.Span(id="docs-file-names", class_="muted"),
                    class_="dropzone", **{"for": "docs-file"},
                ),
                air.P("支持 Markdown / 纯文本 / HTML / Word / PDF，单篇不超过 8 MB。"
                      "只对上传的文件做嵌入，其它文档不重算。", class_="hint"),
                air.Div(
                    air.Button(icon("upload", "icon"), air.Span("上传并入库"), type="button",
                               id="docs-upload", class_="btn is-primary"),
                    class_="page-actions",
                ),
                class_="card-body",
            ),
            air.P(id="docs-message", class_="msg"),
            class_="card",
            id="docs-panel-upload",
            hidden=True,
        ),
        _lab_panel(),
        _drawer("docs", "查看分块"),
        class_="view", id="view-docs", data_view="docs", hidden=True,
    )


# ── 评测治理 ────────────────────────────────────────────────────


def _eval_view() -> air.Div:
    """评测治理视图：页面头 + 说明条 + 统计卡 + 用例表 + Ragas 指标 + 历史报告。

    统计卡只在跑过之后才有数；没跑过时 ``#eval-summary`` 里是一条空状态提示。
    用例行可点，详情开抽屉。返回一个 ``<div id="view-eval">``。
    """
    return air.Div(
        air.Div(
            air.Div(
                icon("eval", "page-icon"),
                air.Div(
                    air.H2("评测治理"),
                    air.P("门禁层不调裁判：先看每条用例的行为对不对（该答就答、该拒就拒）、"
                          "检索有没有拿到该召回的文档；答案质量交给 Ragas 0.4 的三指标，单独一个动作。",
                          class_="page-desc"),
                ),
                class_="page-head-main",
            ),
            air.Div(
                air.Button(icon("play", "icon"), air.Span("运行门禁评测"), type="button",
                           id="eval-run", class_="btn is-primary"),
                air.Button(icon("eval", "icon"), air.Span("跑 Ragas 三指标"), type="button",
                           id="eval-ragas", class_="btn"),
                air.Button(icon("refresh", "icon"), air.Span("刷新历史"), type="button",
                           id="eval-refresh", class_="btn"),
                class_="page-actions",
            ),
            class_="page-head",
        ),
        air.Div(
            icon("info", "icon"),
            air.Div(
                air.H4("门禁层与体检层分开跑"),
                air.Span("门禁看行为与命中，不调裁判，每次改动都能跑；"
                         "Ragas 要调裁判模型且慢，上线前跑。两者都会落报告。"),
            ),
            class_="alert",
        ),
        air.Div(id="eval-summary", class_="stats"),
        air.P(id="eval-message", class_="msg"),
        air.Div(id="eval-locked", class_="locked", hidden=True),
        air.Div(id="eval-table", class_="table-wrap"),
        air.Div(
            air.Div(air.H3("Ragas 0.4 三指标"), class_="card-head"),
            air.Div(id="eval-ragas-panel", class_="card-body"),
            class_="card",
        ),
        air.Div(
            air.Div(air.H3("历史报告"), class_="card-head"),
            air.Div(id="eval-reports", class_="card-body"),
            class_="card",
        ),
        _drawer("eval", "用例详情"),
        class_="view", id="view-eval", data_view="eval", hidden=True,
    )


def render_login_page() -> air.Html:
    """登录 / 注册。居中一张卡，与完整版 ``pages/Login.tsx`` 同构。

    品牌块、标题、副标题、表单、主按钮——顺序一致；只是 Lite 没有品牌插画，
    用和侧边栏同一个 KF 渐变方块顶上。
    """
    return air.Html(
        air.Head(
            air.Meta(charset="utf-8"),
            air.Meta(name="viewport", content="width=device-width, initial-scale=1"),
            air.Title("登录 · KnowledgeForge Lite"),
            air.Link(rel="preconnect", href="https://fonts.googleapis.com"),
            air.Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
            air.Link(
                rel="stylesheet",
                href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
            ),
            air.Link(rel="stylesheet", href="/static/console.css"),
        ),
        air.Body(
            icon_sprite(),
            air.Div(
                air.Div(
                    air.Div(
                        air.Div("KF", class_="brand-mark"),
                        air.H1("KnowledgeForge Lite"),
                        air.P("企业级知识库 · 课堂版", class_="auth-sub"),
                        class_="auth-brand",
                    ),
                    air.Div(
                        air.Button("登录", type="button", id="auth-tab-login", data_tab="login",
                                   class_="tab is-on", role="tab"),
                        air.Button("注册", type="button", id="auth-tab-register", data_tab="register",
                                   class_="tab", role="tab"),
                        class_="tabs auth-tabs",
                    ),
                    air.Div(
                        air.Label(air.Span("用户名"),
                                  air.Input(id="auth-username", type="text", class_="input",
                                            autocomplete="username", placeholder="用户名"),
                                  class_="field"),
                        air.Label(air.Span("密码"),
                                  air.Input(id="auth-password", type="password", class_="input",
                                            autocomplete="current-password", placeholder="密码"),
                                  class_="field"),
                        class_="auth-form",
                        id="auth-pane-login",
                    ),
                    air.Div(
                        air.Label(air.Span("用户名"),
                                  air.Input(id="reg-username", type="text", class_="input",
                                            autocomplete="username", placeholder="3–24 个字符"),
                                  class_="field"),
                        air.Label(air.Span("密码"),
                                  air.Input(id="reg-password", type="password", class_="input",
                                            autocomplete="new-password", placeholder="至少 6 位"),
                                  class_="field"),
                        air.Label(air.Span("显示名（可留空）"),
                                  air.Input(id="reg-display", type="text", class_="input",
                                            placeholder="别人看到的名字"),
                                  class_="field"),
                        # 一个下拉，四张工牌——角色和部门不分开选，就不会拼出不存在的组合
                        air.Label(air.Span("身份"),
                                  air.Select(
                                      air.Option("IT 员工 · 看得见 IT 故障单，看不见财务密级",
                                                 value="it_staff", selected=True),
                                      air.Option("人事员工 · 只看得见公开文档",
                                                 value="hr_staff"),
                                      air.Option("财务负责人 · 看得见财务密级文档",
                                                 value="finance_head"),
                                      air.Option("公司管理员 · 不过滤部门，管理视图都能进",
                                                 value="admin"),
                                      id="reg-identity", class_="select",
                                  ),
                                  class_="field"),
                        class_="auth-form",
                        id="auth-pane-register",
                        hidden=True,
                    ),
                    air.P(id="auth-message", class_="msg"),
                    air.Button("登录", type="button", id="auth-submit", class_="btn is-primary auth-submit"),
                    air.Div(
                        air.Button("不注册，以访客身份看看", type="button", id="auth-guest",
                                   class_="btn is-link"),
                        class_="auth-hint",
                    ),
                    class_="card auth-card",
                ),
                class_="auth-shell",
            ),
            air.Script(src="/static/auth.js"),
        ),
    )


def render_chat_page() -> air.Html:
    """控制台：壳层 + 三个视图，侧边栏切换，不跳页。"""
    return air.Html(
        air.Head(
            air.Meta(charset="utf-8"),
            air.Meta(name="viewport", content="width=device-width, initial-scale=1"),
            air.Title("KnowledgeForge Lite · 控制台"),
            air.Link(rel="preconnect", href="https://fonts.googleapis.com"),
            air.Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
            air.Link(
                rel="stylesheet",
                href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
            ),
            air.Link(rel="stylesheet", href="/static/console.css"),
        ),
        air.Body(
            icon_sprite(),
            air.Div(
                _nav(),
                air.Main(
                    _header(),
                    air.Main(
                        air.Div(_qa_view(), _docs_view(), _eval_view(), class_="content-inner"),
                        class_="content",
                    ),
                    class_="main",
                ),
                class_="shell",
            ),
            air.Div(id="scrim", class_="scrim", hidden=True),
            air.Script(src="/static/workbench.js"),
            air.Script(src="/static/console.js"),
        ),
    )
