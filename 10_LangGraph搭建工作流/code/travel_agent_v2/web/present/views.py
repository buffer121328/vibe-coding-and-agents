"""Air Tags 页面骨架 —— 国内旅行管家工作台。

Air 处于 alpha（0.48.x），本文件是全项目唯一接触 Air Tags 的地方。
页面只负责骨架，内容由 static/app.js 用 /api/auth/* 与 /api/state 动态填充。

结构：左侧固定导航 + 右侧六个分页（对话 / 行程 / 探索 / 看板 / 订单 / 运维）。
不再把所有东西挤在一屏——每一页只做一件事。
看板按机场出港牌组织：等宽数据列右对齐、信号灯表状态、顶部大字计数、可按类型筛。
"""
import air


CSS = """
:root {
  /* ---- 板面：抬起的表面（导航 / 看板 / 登录卡片） ---- */
  --void:    #ffffff;   /* 板底 */
  --panel:   #f6fafe;   /* 抬起的板面 */
  --panel-2: #e9f3fd;   /* 行 / 悬停 / 当前项 */
  --line:    #e2ecf5;   /* 发丝分隔 */
  --line-2:  #cfdeec;   /* 强调分隔 */
  --text:    #10233a;   /* 板上的字：深藏青 */
  --dim:     #4a6379;   /* 板上的次级字 */
  --dim-2:   #7b93a8;   /* 板上的三级字 */
  --lamp-ok:   #12b981; /* 已订 / 通过 */
  --lamp-hold: #ff8f2e; /* 待签 / 挂起 */
  --lamp-no:   #f4535f; /* 驳回 / 取消 */
  --accent:    #1a7fe8; /* 信息 / 主操作：明亮天蓝 */
  --accent-2:  #4aa0f5;
  --accent-deep: #0f5fb0; /* 浅底上的蓝字：压深一档才够读 */

  /* ---- 纸面：给阅读用的底 ---- */
  --paper:  #f1f7fd;    /* 冷调淡蓝白 */
  --card:   #ffffff;
  --ink:    #10233a;
  --ink-2:  #4a6379;
  --ink-3:  #7b93a8;
  --rule:   #dbe7f2;
  --rule-2: #eaf2f9;
  --hold-bg: #fff4e6;
  --ok-bg:   #e7f9f1;
  --no-bg:   #ffecee;
  --sky:     linear-gradient(180deg, #e8f3ff 0%, #ffffff 100%);
  --shadow:  0 1px 2px rgba(16, 35, 58, .04), 0 12px 26px -16px rgba(16, 35, 58, .18);
  --r-card: 14px;
  --r-ctl: 10px;

  /* ---- 航图：唯一一块"印刷品"台面 ---- */
  --map-plate: #e8eef4;
  --map-ink:   #1d4f7c;
  --map-city:  #6d879c;
  --map-fill:  #ffffff;

  --mono: "Azeret Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
  --sans: "Noto Sans SC", "PingFang SC", "Source Han Sans SC", system-ui, sans-serif;
  --nav-w: 186px;
}
* { box-sizing: border-box; margin: 0; }
html, body { height: 100%; }
body {
  font-family: var(--sans);
  font-size: 14px; line-height: 1.6;
  color: var(--ink); background: var(--paper);
  min-height: 100vh;
}
::selection { background: var(--accent); color: #fff; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.num, time, .mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
img { display: block; }

/* ============================ 登录 ============================ */
.gate {
  position: fixed; inset: 0; z-index: 40; display: grid; place-items: center;
  padding: 26px 18px; overflow-y: auto;
  background:
    radial-gradient(880px 440px at 12% -14%, #d6e9ff 0%, transparent 62%),
    radial-gradient(680px 360px at 94% 6%, #dff7ef 0%, transparent 58%),
    linear-gradient(170deg, #f4faff 0%, var(--paper) 58%, #e9f3ff 100%);
}
.gate[hidden] { display: none; }
.gate-card {
  width: min(960px, 100%); display: grid;
  /* 右栏（表单）留宽一点：它是这一页真正要动手的地方 */
  grid-template-columns: minmax(0, 1fr) minmax(360px, 480px);
  background: var(--card); border: 1px solid var(--line-2);
  border-radius: 22px; overflow: hidden;
  box-shadow: 0 2px 4px rgba(16, 35, 58, .04), 0 34px 66px -30px rgba(16, 35, 58, .34);
}
/* 左栏三段式：顶条在最上、标题块居中、提示条贴底 */
.gate-side { padding: 32px 32px 28px; border-right: 1px solid var(--line); display: flex; flex-direction: column; }
.gate-side .stamp-top {
  display: flex; justify-content: space-between; gap: 12px;
  font-family: var(--mono); font-size: 11px; letter-spacing: .08em; color: var(--dim-2);
  padding-bottom: 12px; border-bottom: 1px solid var(--line);
}
.gate-body { flex: 1; display: flex; flex-direction: column; justify-content: center; min-height: 0; }
.gate-side h1 {
  margin: 0 0 12px; font-size: 30px; font-weight: 700; line-height: 1.25; color: var(--text);
}
.gate-side h1 em { font-style: normal; color: var(--accent); }
.gate-side .lede { font-size: 13.5px; line-height: 1.85; color: var(--dim); max-width: 34ch; }
/* 登录页的技术细节收成一个默认收起的提示框：页面上只留一句产品说明 */
/* 收成窄块（宽度随内容），不铺满整栏——它是个「想问再点」的角标，不是一块告示 */
.gate-hint {
  margin-top: 18px; align-self: flex-start; width: fit-content; max-width: 100%;
  border: 1px solid var(--rule); border-radius: var(--r-ctl);
  background: var(--paper);
}
.gate-hint > summary {
  cursor: pointer; list-style: none; padding: 10px 13px;
  display: flex; align-items: center; gap: 8px;
  font-size: 12.5px; color: var(--dim);
}
.gate-hint > summary::-webkit-details-marker { display: none; }
.gate-hint > summary::before { content: "ⓘ"; color: var(--accent-deep); font-size: 12px; }
.gate-hint > summary:hover { color: var(--ink); }
.gate-hint[open] > summary { color: var(--ink); border-bottom: 1px solid var(--rule); }
.gate-hint-body { padding: 2px 13px 12px; }
.gate-list { margin-top: 6px; }
.gate-list div {
  display: grid; grid-template-columns: 56px minmax(0, 1fr); gap: 10px;
  padding: 10px 0; border-bottom: 1px solid var(--rule);
  font-size: 13px; color: var(--dim); line-height: 1.6;
}
.gate-list div:last-child { border-bottom: 0; }
.gate-list b { font-size: 12px; font-weight: 500; color: var(--accent-deep); }
.gate-list em { font-style: normal; color: var(--text); }
.gate-hint .gate-note {
  margin-top: 10px; padding-top: 0; font-size: 11.5px; line-height: 1.7; color: var(--ink-3);
}
.gate-note code { font-family: var(--mono); color: var(--accent-deep); }
.gate-form { background: var(--sky); padding: 30px 24px 24px; display: flex; flex-direction: column; }
.tabs { display: flex; border-bottom: 1px solid var(--line); margin-bottom: 20px; }
.tabs .tab {
  flex: 1; border: 0; border-bottom: 2px solid transparent; background: transparent;
  padding: 9px 4px; font: 500 13.5px var(--sans); color: var(--dim-2); cursor: pointer;
}
.tabs .tab[aria-selected="true"] { color: var(--accent); border-bottom-color: var(--accent); }
.form { display: flex; flex-direction: column; gap: 13px; }
.form[hidden] { display: none; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-family: var(--mono); font-size: 11px; letter-spacing: .05em; color: var(--dim-2); }
.field input, .field select {
  width: 100%; padding: 10px 12px; font: 14px var(--mono); color: var(--text);
  background: var(--void); border: 1px solid var(--line-2); border-radius: var(--r-ctl);
}
.field input::placeholder { font-family: var(--sans); color: var(--dim-2); }
.field input:focus, .field select:focus { border-color: var(--accent); outline: none; }
.field-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: end; }
.field-note { font-size: 11.5px; line-height: 1.6; color: var(--dim-2); }
.field-note.warn { color: var(--lamp-hold); }
.field-note.ok { color: var(--lamp-ok); }
.captcha { display: none; align-items: center; gap: 10px; }
.captcha.on { display: flex; }
/* 图片本身就是「换一张」的按钮：点一下重新出题，不用再挂一个按钮在旁边 */
.captcha-img {
  flex: 0 0 auto; width: 132px; height: 42px; padding: 0; border: 1px solid var(--line-2);
  background: var(--paper); overflow: hidden; display: grid; place-items: center;
  cursor: pointer; border-radius: var(--r-ctl);
}
.captcha-img:hover:not(:disabled) { border-color: var(--accent); }
.captcha-img:disabled { cursor: progress; }
.captcha-img svg { width: 132px; height: 42px; display: block; }
.alert { display: none; padding: 9px 11px; font-size: 12.5px; line-height: 1.65; border-radius: var(--r-ctl); }
.alert.on { display: block; }
.alert.bad { background: var(--no-bg); color: #8d2a20; border: 1px solid #e8bdb8; }
.alert.good { background: var(--ok-bg); color: #245c3c; border: 1px solid #b8d6c4; }
.btn {
  font-family: var(--sans); font-size: 13.5px; font-weight: 500;
  padding: 10px 15px; border: 1px solid var(--accent); border-radius: var(--r-ctl);
  background: var(--accent); color: #fff; cursor: pointer;
}
.btn:hover { background: var(--accent-2); border-color: var(--accent-2); }
.btn.ghost { background: transparent; color: var(--accent); }
.btn.ghost:hover { background: rgba(74, 168, 216, .12); }
.btn.hold { background: var(--lamp-hold); border-color: var(--lamp-hold); color: #fff; }
.btn.hold:hover { background: #f5b455; }
.btn.no { background: transparent; color: var(--lamp-no); border-color: var(--lamp-no); }
.btn.no:hover { background: rgba(226, 87, 76, .12); }
.btn:disabled { opacity: .5; cursor: progress; }
.btn.block { width: 100%; }
.btn.small { font-size: 12px; padding: 6px 10px; }
.demo { margin-top: 20px; padding-top: 15px; border-top: 1px dashed var(--line); }
.demo[hidden] { display: none; }
.demo .cap { font-family: var(--mono); font-size: 10.5px; letter-spacing: .05em; color: var(--dim-2); margin-bottom: 8px; }
.demo-card {
  width: 100%; display: flex; align-items: baseline; gap: 8px; text-align: left;
  border: 1px solid var(--line); background: var(--card); padding: 7px 9px; margin-bottom: 5px;
  cursor: pointer; font: 12.5px var(--sans); color: var(--dim); border-radius: var(--r-ctl);
}
.demo-card:hover { border-color: var(--accent); color: var(--text); }
.demo-card b { font-family: var(--mono); font-weight: 500; color: var(--accent); }
.demo-card em { font-style: normal; margin-left: auto; font: 11px var(--mono); color: var(--dim-2); }

/* ============================ 应用骨架：侧边栏 + 内容区 ============================ */
.app { display: grid; grid-template-columns: var(--nav-w) minmax(0, 1fr); height: 100vh; }
.nav {
  background: var(--void); border-right: 1px solid var(--line);
  display: flex; flex-direction: column; min-height: 0;
}
.nav-brand {
  padding: 16px 16px 14px; border-bottom: 1px solid var(--line); background: var(--sky);
}
.nav-brand b { display: block; font-size: 17px; font-weight: 700; color: var(--text); letter-spacing: -.01em; }
.nav-brand span { display: block; margin-top: 4px; font: 10.5px var(--mono); color: var(--dim-2); }
.nav-list { padding: 8px; display: flex; flex-direction: column; gap: 3px; overflow-y: auto; }
.nav-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  border: 0; background: transparent; border-radius: var(--r-ctl);
  padding: 9px 10px; cursor: pointer; font: 500 13.5px var(--sans); color: var(--dim);
  text-align: left;
}
.nav-item:hover { background: var(--panel); color: var(--text); }
.nav-item[aria-current="page"] {
  background: var(--panel-2); color: var(--accent-deep); font-weight: 600;
}
.nav-item .ico { width: 16px; height: 16px; flex: 0 0 16px; color: currentColor; opacity: .9; }
.nav-item .ico svg { width: 16px; height: 16px; display: block; }
.nav-item .tag {
  margin-left: auto; font: 10px var(--mono); color: var(--dim-2);
  border: 1px solid var(--line); padding: 0 6px; border-radius: 999px;
}
.nav-item .dot {
  margin-left: auto; width: 7px; height: 7px; border-radius: 50%; background: var(--lamp-hold);
}
.nav-foot { margin-top: auto; padding: 12px 14px 14px; border-top: 1px solid var(--line); }
.nav-foot .who { font: 11px var(--mono); color: var(--dim-2); margin-bottom: 8px; }
.nav-foot .who b { color: var(--text); font-weight: 500; }
.nav-foot button {
  width: 100%; border: 1px solid var(--line-2); background: transparent; color: var(--dim);
  font: 12px var(--mono); padding: 7px; cursor: pointer; border-radius: var(--r-ctl);
}
.nav-foot button:hover { border-color: var(--lamp-no); color: var(--lamp-no); }

/* 主区是竖向 flex：顶栏吃掉自己的高度，分页吃掉剩下的，别让页面用 100% 去顶顶栏 */
.main { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--paper); }
.topbar {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  padding: 12px 20px; background: var(--card); border-bottom: 1px solid var(--rule);
}
.topbar h2 { font-size: 16px; font-weight: 700; color: var(--ink); }
.topbar .sub { font: 11px var(--mono); color: var(--ink-3); }
.topbar .chips { margin-left: auto; display: flex; gap: 7px; flex-wrap: wrap; }
.chip {
  display: inline-flex; align-items: center; gap: 5px;
  border: 1px solid var(--rule); background: var(--paper);
  padding: 4px 10px; font: 11px var(--mono); color: var(--ink-3); border-radius: 999px;
}
.chip b { color: var(--ink); font-weight: 500; }
.chip.live b { color: #1f7a4d; }
.chip.demo b { color: #a8621a; }
/* 当前页是主区里的弹性子项：自己滚，不把底部的输入行顶出屏幕 */
.page { display: none; min-height: 0; overflow-y: auto; }
.page[data-active="true"] { display: block; flex: 1; min-height: 0; }

/* 行程页：地图 + 航段 + 库存；两栏 */
.page-split { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(300px, .85fr); gap: 16px; padding: 18px 20px 22px; align-items: start; }
.card-block { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r-card); overflow: hidden; box-shadow: var(--shadow); }
.block-head {
  display: flex; align-items: baseline; gap: 8px; padding: 11px 14px;
  border-bottom: 1px solid var(--rule-2); background: var(--paper);
}
.block-head .t { font-size: 13px; font-weight: 700; color: var(--ink); }
.block-head .n { font: 10.5px var(--mono); color: var(--ink-3); }
.block-head .r { margin-left: auto; font: 10.5px var(--mono); color: var(--ink-3); }

/* ============================ 对话页 ============================ */
/* 四行：会话条 / 流程条 / 对话区（占满并自己滚）/ 底部输入 */
.chat-wrap { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; height: 100%; }
.session-bar {
  display: flex; align-items: center; gap: 8px; padding: 10px 20px;
  background: var(--card); border-bottom: 1px solid var(--rule);
}
.sessions { display: flex; gap: 6px; overflow-x: auto; flex: 1; min-width: 0; padding-bottom: 2px; }
.sessions::-webkit-scrollbar { height: 5px; }
.sessions::-webkit-scrollbar-thumb { background: var(--rule); }
.session-chip {
  display: flex; align-items: center; gap: 6px; flex: 0 0 auto; max-width: 230px;
  border: 1px solid var(--rule); background: var(--card); padding: 5px 10px;
  font: 12px var(--sans); color: var(--ink-2); cursor: pointer; min-height: 28px; border-radius: 999px;
}
.session-chip:hover { border-color: var(--accent); }
.session-chip[aria-current="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
.session-chip .st { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 132px; }
.session-chip .sn { font: 10px var(--mono); opacity: .7; white-space: nowrap; flex: 0 0 auto; }
.session-chip .sx {
  border: 0; background: transparent; color: inherit; opacity: .55; cursor: pointer;
  padding: 0 2px; font: 13px/1 var(--sans); flex: 0 0 auto;
}
.session-chip .sx:hover { opacity: 1; }
.session-chip input { border: 1px solid var(--accent); background: #fff; color: var(--ink); font: 12px var(--sans); width: 128px; padding: 1px 4px; }
.session-new {
  flex: 0 0 auto; font: 11px var(--mono); padding: 6px 11px; border: 1px dashed var(--rule);
  background: transparent; color: var(--ink-2); cursor: pointer; border-radius: 999px;
}
.session-new:hover { border-color: var(--accent); color: var(--accent); }
#chat { overflow-y: auto; padding: 20px 24px 8px; min-height: 0; }
.turn { margin: 0 0 20px; }
.bubble { padding: 10px 13px; margin: 8px 0; font-size: 14px; line-height: 1.72; word-break: break-word; }
.user { margin-left: 28%; background: var(--accent); color: #fff; white-space: pre-wrap; border-radius: 14px 14px 4px 14px; }
.answer { background: var(--card); border: 1px solid var(--rule); border-radius: 4px 14px 14px 14px; }
.answer.md h1, .answer.md h2, .answer.md h3 { font-size: 15px; font-weight: 700; color: var(--ink); margin: 10px 0 6px; }
.answer.md p { margin: 0 0 8px; }
.answer.md ul, .answer.md ol { margin: 0 0 8px 20px; }
.answer.md li { margin: 3px 0; }
.answer.md code { font-family: var(--mono); font-size: 12.5px; background: var(--paper); padding: 1px 5px; }
.answer.md pre { background: var(--void); color: var(--text); padding: 11px; overflow-x: auto; font: 12px/1.6 var(--mono); margin: 9px 0; }
.answer.md strong, .answer.md b { color: var(--ink); }
/* 工具过程：默认收起，抬头只有次数 + 状态徽章 */
.thinking { margin: 8px 0; border: 1px solid var(--rule); background: var(--card); font-size: 12.5px; border-radius: var(--r-ctl); overflow: hidden; }
.thinking > summary {
  cursor: pointer; padding: 8px 11px; list-style: none;
  display: flex; align-items: center; gap: 9px;
  font: 11px var(--mono); color: var(--ink-2);
}
.thinking > summary::-webkit-details-marker { display: none; }
.thinking > summary::before { content: "▸"; font-size: 9px; color: var(--ink-3); transition: transform .16s ease; }
.thinking[open] > summary::before { transform: rotate(90deg); }
.thinking[open] > summary { border-bottom: 1px solid var(--rule); }
.thinking-body { padding: 10px 12px 12px; }
.thinking-row { margin: 0 0 9px; }
.thinking-row:last-child { margin-bottom: 0; }
.thinking-row b { font: 11.5px var(--mono); font-weight: 500; color: var(--ink-2); }
.thinking-row pre { white-space: pre-wrap; margin: 4px 0 0; font: 11.5px/1.6 var(--mono); color: var(--ink-2); }
.badge { font: 10px var(--mono); padding: 1px 7px; border: 1px solid currentColor; border-radius: 999px; }
.badge.running { color: #a8621a; }
.badge.done { color: #1f7a4d; }
.thinking > summary .badge { margin-left: auto; }
/* 起手卡：一屏给出四个能立刻点的入口 */
.starters { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; padding: 6px 0; }
.starter {
  display: grid; gap: 6px; text-align: left; cursor: pointer;
  border: 1px solid var(--rule); background: var(--card); padding: 14px 15px;
  font-family: inherit; border-radius: var(--r-card); box-shadow: var(--shadow);
}
.starter:hover { border-color: var(--accent); }
.starter .k { font: 10.5px var(--mono); color: var(--accent); letter-spacing: .05em; }
.starter .q { font-size: 13.5px; color: var(--ink); line-height: 1.6; }
.empty-hint { padding: 12px 0 4px; }
.empty-hint .hint-note { font: 11.5px var(--mono); color: var(--ink-3); margin-bottom: 12px; }
.chat-foot { border-top: 1px solid var(--rule); background: var(--card); }
.quick { display: flex; flex-wrap: wrap; gap: 7px; padding: 10px 20px 0; }
.quick button {
  border: 1px solid var(--rule); background: var(--paper); color: var(--ink-2);
  font: 12px var(--sans); padding: 6px 12px; cursor: pointer; border-radius: 999px;
}
.quick button:hover { border-color: var(--accent); color: var(--accent); }
#status {
  padding: 9px 20px; font: 11.5px var(--mono); color: var(--ink-3);
}
#status.hold { color: #a8621a; background: var(--hold-bg); }
#approval { display: none; margin: 0 20px 10px; padding: 13px 14px; background: var(--hold-bg); border: 1px solid #e6c489; border-radius: var(--r-card); }
#approval.on { display: block; }
.approve-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding-bottom: 9px; margin-bottom: 9px; border-bottom: 1px dashed #e6c489; }
.approve-head .lamp { display: inline-flex; align-items: center; gap: 6px; font: 11px var(--mono); color: #8a5a12; }
.approve-head .lamp i { width: 8px; height: 8px; border-radius: 50%; background: var(--lamp-hold); }
.approve-path { font: 11px var(--mono); color: #8a5a12; }
.approve-total { margin-left: auto; }
.approve-item { display: flex; flex-wrap: wrap; gap: 6px 20px; padding: 5px 0; }
.kv { display: inline-flex; align-items: baseline; gap: 6px; font-size: 13px; }
.kv i { font-style: normal; font: 10.5px var(--mono); color: var(--ink-3); white-space: nowrap; }
.kv b { font: 12.5px var(--mono); font-weight: 500; color: var(--ink); }
.approve-actions { display: flex; gap: 8px; margin-top: 11px; }
.inputrow { display: flex; gap: 9px; padding: 11px 20px 16px; }
.inputrow input {
  flex: 1; padding: 12px 14px; font: 14px var(--sans); color: var(--ink);
  background: var(--paper); border: 1px solid var(--rule); border-radius: var(--r-ctl);
}
.inputrow input:focus { border-color: var(--accent); outline: none; }

/* 智能体流程：一条常显的跑道 */
.flow-strip {
  display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
  padding: 9px 20px; background: var(--card); border-bottom: 1px solid var(--rule);
}
.flow-strip .lead { font: 10.5px var(--mono); color: var(--ink-3); }
.node {
  border: 1px solid var(--rule); background: var(--paper); padding: 4px 11px;
  font: 11px var(--mono); color: var(--ink-2); white-space: nowrap; border-radius: 999px;
}
.node.done { border-color: #b8d6c4; background: var(--ok-bg); color: #1f7a4d; }
.node.on { border-color: var(--accent); background: var(--accent); color: #fff; }
.node.hold { border-color: #e6c489; background: var(--hold-bg); color: #a8621a; }
.cluster { display: flex; flex-wrap: wrap; gap: 4px; padding: 3px; border: 1px dashed var(--rule); }
.join { width: 12px; height: 1px; background: var(--rule); flex: 0 0 12px; }

/* ============================ 行程：地图与航段 ============================ */
.route-map { background: var(--map-plate); border-bottom: 1px solid var(--rule); }
.route-map svg { display: block; width: 100%; height: auto; }
.route-map image { filter: grayscale(0.9) brightness(1.06) contrast(0.92); }
.route-credit { font: 9.5px var(--mono); color: var(--map-city); padding: 3px 14px 0; background: var(--map-plate); }
/* 图例：三层符号各是什么意思，一行说完 */
.route-legend { font: 10.5px var(--mono); color: var(--map-city); padding: 2px 14px 8px; background: var(--map-plate); }
.leg { display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 11px; padding: 15px 16px; border-bottom: 1px dashed var(--rule); }
.leg:last-child { border-bottom: 0; }
.leg-mark {
  display: flex; flex-direction: column; align-items: center; gap: 4px; padding-top: 3px;
  font: 10px var(--mono); color: var(--ink-3);
}
.leg-mark i { width: 9px; height: 9px; border-radius: 50%; border: 2px solid var(--ink); background: var(--card); }
.leg-mark span { width: 1px; flex: 1; background: var(--rule); min-height: 22px; }
.leg-top { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.leg-top .pair { font: 15px var(--mono); font-weight: 500; color: var(--ink); }
.leg-top .pair em { font-style: normal; color: var(--ink-3); padding: 0 4px; }
.leg-top .city { font-size: 12.5px; color: var(--ink-2); }
.leg-top .lamp { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; font: 11px var(--mono); }
.leg-top .lamp i { width: 8px; height: 8px; border-radius: 50%; background: var(--lamp-ok); }
.leg-top .lamp.hold i { background: var(--lamp-hold); }
.leg-meta { display: flex; flex-wrap: wrap; gap: 5px 18px; margin-top: 7px; }
.leg-meta .kv b { font-size: 12px; }
/* 智能体流程灯：挂在航段上的小圆点用同一套信号色 */
.kpis { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0; }
.kpi { padding: 14px 14px 12px; border-bottom: 1px solid var(--rule); border-right: 1px solid var(--rule); }
.kpi:nth-child(2n) { border-right: 0; }
.kpi b { display: block; font: 600 26px var(--mono); color: var(--ink); line-height: 1.1; }
.kpi span { font: 10.5px var(--mono); color: var(--ink-3); }
.kpi.warn b { color: #a8621a; }
.chips-row { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 14px; }
.city-chip { border: 1px solid var(--rule); background: var(--paper); padding: 3px 10px; font: 11px var(--mono); color: var(--ink-2); border-radius: 999px; }
.city-chip.hold { border-color: #e6c489; background: var(--hold-bg); color: #a8621a; }
.city-more { font: 11px var(--mono); color: var(--ink-3); align-self: center; }
.blank { padding: 26px 20px; font-size: 13.5px; line-height: 1.85; color: var(--ink-2); }
.blank b { color: var(--ink); }

/* ============================ 探索 ============================ */
.explore-wrap { padding: 18px 20px 24px; display: grid; grid-template-columns: minmax(0, 300px) minmax(0, 1fr); gap: 18px; align-items: start; }
.city-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.city-tile {
  display: flex; flex-direction: column; padding: 0; overflow: hidden; text-align: left;
  border: 1px solid var(--rule); background: var(--card); cursor: pointer; font-family: inherit;
  border-radius: var(--r-card);
}
.city-tile:hover { border-color: var(--accent); }
.city-photo { width: 100%; height: 62px; object-fit: cover; background: var(--rule-2); }
.city-glyph { display: grid; place-items: center; height: 62px; background: var(--paper); color: var(--accent); }
.city-glyph svg { width: 34px; height: 34px; }
.city-text { padding: 6px 8px 8px; }
.city-tile b { display: block; font-size: 12.5px; font-weight: 500; color: var(--ink); }
.city-tile .city-text > span { display: block; margin-top: 2px; font: 10px var(--mono); color: var(--ink-3); white-space: nowrap; }
.city-tile[aria-current="true"] { border-color: var(--accent); box-shadow: inset 0 0 0 2px var(--accent); }
.city-tile[aria-current="true"] b { color: var(--accent); }
.city-hero { display: flex; gap: 14px; align-items: flex-end; margin-bottom: 14px; }
.city-hero img { width: 190px; height: 108px; object-fit: cover; border: 1px solid var(--rule); }
.city-hero .glyph { width: 190px; height: 108px; display: grid; place-items: center; background: var(--paper); border: 1px solid var(--rule); }
.city-hero .glyph svg { width: 60px; height: 60px; }
.city-hero b { font-size: 22px; font-weight: 700; color: var(--ink); }
.city-hero span { display: block; font: 11px var(--mono); color: var(--ink-3); margin-top: 3px; }
.city-hero .stat { display: flex; gap: 14px; margin-top: 9px; font: 11.5px var(--mono); color: var(--ink-2); }
.city-hero .stat b { color: var(--ink); }

/* 卡片：工具回执长出来的形状 */
.deck { display: grid; grid-template-columns: repeat(auto-fill, minmax(268px, 1fr)); gap: 10px; padding: 16px 18px 20px; }
.deck-group { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px; padding: 6px 0 2px; }
.deck-group .g { color: var(--accent); display: inline-flex; }
.deck-group .g svg { width: 18px; height: 18px; display: block; }
.deck-group .g img { width: 22px; height: 22px; object-fit: cover; }
.deck-group .t { font-size: 12.5px; font-weight: 700; color: var(--ink); }
.deck-group .n { margin-left: auto; font: 10.5px var(--mono); color: var(--ink-3); }
.card {
  border: 1px solid var(--rule); background: var(--card);
  display: grid; grid-template-columns: 4px minmax(0, 1fr); overflow: hidden;
  border-radius: var(--r-card); box-shadow: var(--shadow);
}
.card .lampbar { background: var(--rule); }
.card.mark-ok .lampbar { background: var(--lamp-ok); }
.card.mark-hold .lampbar { background: var(--lamp-hold); }
.card-body { padding: 11px 13px 12px; min-width: 0; }
.card-top { display: flex; align-items: baseline; gap: 8px; }
.card-title { font-size: 13.5px; font-weight: 500; color: var(--ink); line-height: 1.5; }
.card-price { margin-left: auto; font: 500 13px var(--mono); color: var(--ink); white-space: nowrap; }
.card-meta { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 5px; font: 10.5px var(--mono); color: var(--ink-3); }
.card-note {
  margin-top: 6px; font-size: 12px; line-height: 1.6; color: var(--ink-2);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 7px; }
.tag { border: 1px solid var(--rule); padding: 1px 8px; font: 10px var(--mono); color: var(--ink-3); border-radius: 999px; }
.bar { height: 6px; background: var(--rule-2); margin-top: 8px; border-radius: 999px; overflow: hidden; }
/* 卡片是网格子项，空态那句要占满整行，不然会被压进一列里 */
.deck .blank, .orders .blank { grid-column: 1 / -1; }
.bar i { display: block; height: 100%; background: var(--accent); }

/* ============================ 看板：机场出港牌 ============================ */
.board-page { padding: 18px 20px 24px; }
.board-shell { background: var(--card); border: 1px solid var(--line-2); border-radius: 18px; overflow: hidden; box-shadow: var(--shadow); }
.board-top {
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  padding: 14px 18px; border-bottom: 1px solid var(--line);
  background: var(--sky);
}
.board-top .label {
  font: 10.5px var(--mono); letter-spacing: .1em; color: var(--dim-2);
}
.board-top .clock { margin-left: auto; font: 600 19px var(--mono); color: var(--accent-deep); font-variant-numeric: tabular-nums; }
.board-lamps { display: flex; gap: 26px; flex-wrap: wrap; padding: 16px 18px; border-bottom: 1px solid var(--line); }
.lamp-cell b { display: block; font: 600 30px var(--mono); line-height: 1.05; color: var(--text); }
.lamp-cell span { font: 10px var(--mono); color: var(--dim-2); }
.lamp-cell.ok b { color: var(--lamp-ok); }
.lamp-cell.hold b { color: var(--lamp-hold); }
.lamp-cell.no b { color: var(--lamp-no); }
.lamp-cell.info b { color: var(--accent-deep); }
.board-filter {
  display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
  padding: 11px 18px; border-bottom: 1px solid var(--line);
}
.seg {
  border: 1px solid var(--line-2); background: var(--card); color: var(--dim);
  font: 11.5px var(--mono); padding: 5px 13px; cursor: pointer; border-radius: 999px;
}
.seg:hover { border-color: var(--accent); color: var(--accent-deep); }
.seg[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
.board-count { margin-left: auto; font: 11px var(--mono); color: var(--dim-2); }
/* 表头 + 行：等宽数据列，右对齐，像真的航显 */
.board-head, .board-row {
  display: grid;
  grid-template-columns: 30px minmax(0, 2.1fr) 92px 96px 108px 84px;
  gap: 10px; align-items: center; padding: 0 18px;
}
.board-head {
  font: 10px var(--mono); letter-spacing: .08em; color: var(--dim-2);
  padding-top: 10px; padding-bottom: 9px; border-bottom: 1px solid var(--line);
}
.board-rows { max-height: 52vh; overflow-y: auto; }
.board-rows::-webkit-scrollbar { width: 8px; }
.board-rows::-webkit-scrollbar-thumb { background: var(--line-2); border-radius: 999px; }
.board-row {
  font: 13px var(--mono); color: var(--text);
  padding-top: 11px; padding-bottom: 11px;
  border-bottom: 1px solid var(--rule-2);
}
.board-row:nth-child(odd) { background: #f8fbff; }
.board-row:hover { background: var(--panel-2); }
.board-row .lampcell { display: flex; justify-content: center; }
.board-row .lampcell i { width: 10px; height: 10px; border-radius: 50%; }
.board-row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.board-row .kind { color: var(--dim); font-size: 11px; }
.board-row .city { color: var(--dim); font-size: 11.5px; }
.board-row .tier { color: var(--dim-2); font-size: 11px; }
.board-row .price { text-align: right; color: var(--accent-deep); }
.board-row .stat { font-size: 11px; color: var(--dim); }
.board-row .stat.ok { color: #0d8a61; }
.board-row .stat.hold { color: #a8621a; font-weight: 500; }
.board-row.is-booked .name { color: #0d8a61; font-weight: 500; }
/* 状态真变了才让那一行闪一下：像出港牌翻牌，不是整块屏乱抖 */
@keyframes flip { from { opacity: .2; } to { opacity: 1; } }
.lamp-ok { background: var(--lamp-ok); }
.lamp-hold { background: var(--lamp-hold); }
.lamp-off { background: #c3d2df; }
.board-empty { padding: 22px 18px; font: 12px var(--mono); color: var(--dim-2); }

/* 订单 / 运维页 */
.page-pad { padding: 18px 20px 24px; }
.orders { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 10px; }
.order { border: 1px solid var(--rule); background: var(--card); padding: 12px 13px; border-radius: var(--r-card); box-shadow: var(--shadow); }
.order.cancelled { background: var(--paper); }
.order.cancelled .order-title { text-decoration: line-through; color: var(--ink-3); }
.order-head { display: flex; align-items: baseline; gap: 8px; }
.order-title { font-size: 13.5px; font-weight: 500; color: var(--ink); }
.order-body { display: flex; flex-wrap: wrap; gap: 5px 16px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--rule-2); }
.order-actions { margin-top: 10px; }
.lamp-tag { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; font: 10.5px var(--mono); color: #0d8a61; }
.lamp-tag i { width: 8px; height: 8px; border-radius: 50%; background: var(--lamp-ok); }
.lamp-tag.off { color: var(--ink-3); }
.lamp-tag.off i { background: var(--ink-3); }
.lamp-tag.hold { color: #a8621a; }
.lamp-tag.hold i { background: var(--lamp-hold); }
.stack-item, .pref, .trace-item { border-bottom: 1px solid var(--rule); padding: 9px 14px; font-size: 12.5px; }
.trace-item { display: flex; justify-content: space-between; gap: 10px; color: var(--ink-2); }
.trace-item b { color: var(--ink); font-weight: 500; }
.ops-grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(280px, .7fr); gap: 16px; align-items: start; }
.audit-summary { display: grid; grid-template-columns: repeat(4, 1fr); border-bottom: 1px solid var(--rule); }
.audit-summary .cell { padding: 12px 8px; text-align: center; border-right: 1px solid var(--rule); }
.audit-summary .cell:last-child { border-right: 0; }
.audit-summary b { display: block; font: 600 20px var(--mono); color: var(--ink); }
.audit-summary span { font: 10.5px var(--mono); color: var(--ink-3); }
.audit-summary .warn b { color: #a8621a; }
.audit-item { padding: 9px 14px; border-bottom: 1px solid var(--rule-2); font-size: 12.5px; }
.audit-item:last-child { border-bottom: 0; }
.audit-row { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
.audit-who { font: 12px var(--mono); font-weight: 500; color: var(--ink); }
.audit-when { font: 10.5px var(--mono); color: var(--ink-3); }
.audit-what { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 7px; align-items: baseline; color: var(--ink-2); }

/* ============================ 响应式 ============================ */
@media (max-width: 1100px) {
  :root { --nav-w: 64px; }
  .nav-brand span, .nav-item .label, .nav-foot .who, .nav-item .tag { display: none; }
  .nav-item { justify-content: center; padding: 10px 0; }
  .nav-brand { padding: 14px 0; text-align: center; }
  .nav-brand b { font-size: 13px; }
  .page-split, .explore-wrap, .ops-grid { grid-template-columns: 1fr; }
  .city-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 780px) {
  .app { grid-template-columns: 1fr; height: auto; }
  /* 登录卡也要跟着收成一列：说明在上、表单在下，不要横向挤两栏 */
  .gate-card { grid-template-columns: 1fr; }
  .gate-side { border-right: 0; border-bottom: 1px solid var(--rule); padding: 24px 22px 20px; }
  .gate-body { min-height: 168px; }
  .gate-form { padding: 22px 22px 20px; }
  .nav { flex-direction: row; border-right: 0; border-bottom: 1px solid var(--line); overflow-x: auto; }
  .nav-list { flex-direction: row; padding: 6px; }
  .nav-foot { display: none; }
  .board-head, .board-row { grid-template-columns: 24px minmax(0, 2fr) 84px 92px; }
  /* 窄屏上只留「灯 + 名称 + 城市 + 单价」；类型和状态文字收起来，灯本身已经在说状态 */
  .board-row .tier, .board-head .tier, .board-row .kind, .board-head .kind,
  .board-row .stat, .board-head .stat { display: none; }
  .city-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .deck { grid-template-columns: 1fr; }
  .user { margin-left: 12%; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""



ICONS = {
    "chat": '<path d="M3 3h18v13H8l-5 4z" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    "trip": '<path d="M3 17l6-6 4 3 7-8" fill="none" stroke="currentColor" stroke-width="1.8"/>'
            '<circle cx="3" cy="17" r="2"/><circle cx="20" cy="6" r="2"/>',
    "explore": '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/>'
               '<path d="M15.5 8.5l-2 5.5-5.5 2 2-5.5z"/>',
    "board": '<rect x="3" y="4" width="18" height="16" fill="none" stroke="currentColor" stroke-width="1.8"/>'
             '<path d="M3 9h18M9 9v11M15 9v11" fill="none" stroke="currentColor" stroke-width="1.4"/>',
    "orders": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" fill="none" stroke="currentColor" stroke-width="1.8"/>'
              '<path d="M9 8h6M9 12h6" fill="none" stroke="currentColor" stroke-width="1.4"/>',
    "ops": '<path d="M3 12h4l2-6 3 12 2.5-8 2 2h4.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
}

PAGES = [
    ("chat", "对话", "和助手说话，敏感操作在这里签字"),
    ("trip", "行程", "地图、航段与我的行程概览"),
    ("explore", "探索", "挑个城市，直接翻景点 / 酒店 / 租车"),
    ("board", "看板", "全库库存实时航显"),
    ("orders", "订单", "已订 / 已取消，可在这里退单"),
    ("ops", "运维", "审计流水、状态栈与跨会话档案"),
]


def _nav_item(key: str, label: str) -> "air.Tag":
    """左侧导航的一项（图标 + 文字 + 计数位 + 新内容小点）。

    :param key: 页面 key（chat / trip / …），用作 id 与 data-page
    :param label: 导航上显示的中文名
    :return: Air 的 Button 标签
    """
    return air.Button(
        air.Span(air.Raw(  # 图标是纯几何 path，用 currentColor 跟随状态
            f'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">{ICONS[key]}</svg>'
        ), class_="ico"),
        air.Span(label, class_="label"),
        air.Span(id_=f"nav-tag-{key}", class_="tag"),
        air.Span(id_=f"nav-dot-{key}", class_="dot", hidden=True),
        class_="nav-item",
        id_=f"nav-{key}",
        type_="button",
        data_page=key,
    )


def _login_captcha(prefix: str):
    """图形验证码那一小块：题板 + 输入框。

    题板本身就是「换一张」的按钮——点它重新出题（比旁边再挂一个按钮少一行字、少一次瞄准）。
    不挂可见标签：图 + 输入框是个人都认得的形状，输入框靠 aria-label 与占位文字说明。
    """
    return air.Div(
        air.Button(
            id_=f"{prefix}-captcha-img",
            class_="captcha-img",
            type_="button",
            title="点一下换一张",
            aria_label="图形验证码，点一下换一张",
        ),
        air.Div(
            air.Input(
                id_=f"{prefix}-captcha-input",
                type_="text",
                placeholder="输入图中字符 · 不区分大小写",
                autocomplete="off",
                maxlength="6",
                aria_label="图形验证码",
            ),
            class_="field",
        ),
        id_=f"{prefix}-captcha",
        class_="captcha on" if prefix == "reg" else "captcha",
    )


def index():
    """页面骨架总入口（登录页 + 侧栏 + 六个分页）。

    :return: 完整 HTML 文档
    """
    return air.Html(
        air.Head(
            air.Meta(charset="utf-8"),
            air.Meta(name="viewport", content="width=device-width, initial-scale=1"),
            air.Title("Trip Assistant 旅行管家"),
            air.Link(
                rel="stylesheet",
                href="https://fonts.googleapis.com/css2?family=Azeret+Mono:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;700&display=swap",
            ),
            air.Style(CSS),
        ),
        air.Body(
            # ---------------- 登录 ----------------
            air.Div(
                air.Div(
                    air.Div(
                        air.Div(
                            air.Span("SIGN IN"),
                            air.Span("TRIP ASSISTANT"),
                            class_="stamp-top",
                        ),
                        # 标题块交给 flex 居中：左栏是「顶条 / 标题 / 提示」三段
                        air.Div(
                            air.H1("旅行管家 ", air.Em("工作台")),
                            air.P(
                                "一个账号一份档案。登录后读到的行程、对话、订单和偏好，"
                                "都由你自己那份档案决定。",
                                class_="lede",
                            ),
                            class_="gate-body",
                        ),
                        # 技术细节不铺在页面上，收进一个默认收起的提示框：想看再点开
                        air.Details(
                            air.Summary("这套登录怎么做的"),
                            air.Div(
                                air.Div(
                                    air.Div(air.B("口令"), air.Span("只存 ", air.Em("PBKDF2 哈希"), "，明文不落库")),
                                    air.Div(air.B("注册"), air.Span("要过 ", air.Em("图形验证码"), "（点题板换一张）；邮箱码那道暂时下线")),
                                    air.Div(air.B("会话"), air.Span("登录签发 ", air.Em("HS256 JWT"), "，放 HttpOnly Cookie")),
                                    air.Div(air.B("防爆破"), air.Span("连错 3 次要补图形码；退出即吊销令牌")),
                                    class_="gate-list",
                                ),
                                air.Div(
                                    "签名密钥来自 ", air.Code("TRIP_DESK_SECRET"),
                                    "；没配时用开发默认值，启动日志会提醒。",
                                    class_="gate-note",
                                ),
                                class_="gate-hint-body",
                            ),
                            class_="gate-hint",
                        ),
                        class_="gate-side",
                    ),
                    air.Div(
                        air.Div(
                            air.Button("登录", class_="tab", id_="tab-login", type_="button", aria_selected="true"),
                            air.Button("注册", class_="tab", id_="tab-register", type_="button", aria_selected="false"),
                            class_="tabs",
                            role_="tablist",
                        ),
                        air.Div(id_="login-error", class_="alert"),
                        air.Div(
                            air.Div(
                                air.Label("账号", for_="login-user"),
                                air.Input(id_="login-user", type_="text", placeholder="用户名或邮箱",
                                          autocomplete="username"),
                                class_="field",
                            ),
                            air.Div(
                                air.Label("密码", for_="login-pass"),
                                air.Input(id_="login-pass", type_="password", placeholder="••••••",
                                          autocomplete="current-password"),
                                class_="field",
                            ),
                            _login_captcha("login"),
                            air.Button("登录", class_="btn block", id_="login-submit", type_="button"),
                            id_="form-login",
                            class_="form",
                        ),
                        air.Div(
                            air.Div(
                                air.Label("用户名", for_="reg-user"),
                                air.Input(id_="reg-user", type_="text", placeholder="小写字母、数字、下划线",
                                          autocomplete="username"),
                                class_="field",
                            ),
                            air.Div(
                                air.Label("邮箱", for_="reg-email"),
                                air.Input(id_="reg-email", type_="email", placeholder="you@example.com",
                                          autocomplete="email"),
                                class_="field",
                            ),
                            _login_captcha("reg"),
                            # ------------------------------------------------------------------
                            # 邮箱验证码这块**暂时下线**（2026-09-20，演示环境没有邮件服务，用不上）。
                            # 恢复步骤：① 放开这里的注释；② 放开 static/app.js 里 sendEmailCode /
                            # startCooldown / noteCode 与它们的按钮绑定；③ 放开 web/api.py 里
                            # /api/auth/email/code 端点与 auth_register 里那段 verify()；
                            # ④ 把 tests 里 reg-code / send-code 的断言放回来。
                            # air.Div(
                            #     air.Div(
                            #         air.Label("邮箱验证码", for_="reg-code"),
                            #         air.Input(id_="reg-code", type_="text", placeholder="6 位数字",
                            #                   autocomplete="one-time-code", maxlength="6"),
                            #         class_="field",
                            #     ),
                            #     air.Button("发送验证码", class_="btn ghost small", id_="send-code", type_="button"),
                            #     class_="field-row",
                            # ),
                            # air.Div(id_="code-note", class_="field-note"),
                            air.Div(
                                air.Label("密码", for_="reg-pass"),
                                air.Input(id_="reg-pass", type_="password", placeholder="至少 6 位",
                                          autocomplete="new-password"),
                                class_="field",
                            ),
                            air.Div(
                                air.Label("绑定档案", for_="reg-pax"),
                                air.Select(id_="reg-pax"),
                                class_="field",
                            ),
                            air.Button("注册并登录", class_="btn block", id_="register-btn", type_="button"),
                            id_="form-register",
                            class_="form",
                            hidden=True,
                        ),
                        # 演示账号只在「登录」页签给：注册是自己填邮箱、过图形验证码的流程，
                        # 摆一排能一键进的账号只会让人误以为注册也要挑一个
                        air.Div(
                            air.Div("演示账号 · 点一下自动填好", class_="cap"),
                            air.Div(id_="login-demos"),
                            class_="demo",
                            id_="demo-block",
                        ),
                        class_="gate-form",
                    ),
                    class_="gate-card",
                ),
                id_="login",
                class_="gate",
            ),
            # ---------------- 工作台 ----------------
            air.Div(
                air.Nav(
                    air.Div(
                        air.B("旅行管家"),
                        air.Span("TRIP ASSISTANT"),
                        class_="nav-brand",
                    ),
                    air.Div(
                        *[_nav_item(key, label) for key, label, _ in PAGES],
                        class_="nav-list",
                    ),
                    air.Div(
                        air.Div("旅客 ", air.B("—", id_="pax-chip"), class_="who"),
                        air.Button("退出登录", id_="signout-btn", type_="button"),
                        class_="nav-foot",
                    ),
                    class_="nav",
                ),
                air.Div(
                    air.Header(
                        air.H2("对话", id_="page-title"),
                        air.Span("", id_="page-sub", class_="sub"),
                        air.Div(
                            air.Span("模型 ", air.B("—", id_="model-chip"), class_="chip"),
                            air.Span("模式 ", air.B("—", id_="mode-chip"), class_="chip", id_="mode-wrap"),
                            air.Span("会话 ", air.B("—", id_="thread-chip"), class_="chip"),
                            class_="chips",
                        ),
                        class_="topbar",
                    ),
                    # ---- 对话页 ----
                    air.Div(
                        air.Div(
                            air.Div(
                                air.Div(id_="sessions", class_="sessions"),
                                air.Button("＋ 新对话", class_="session-new", id_="session-new", type_="button"),
                                class_="session-bar",
                            ),
                            air.Div(
                                air.Span("智能体流程", class_="lead"),
                                air.Div(id_="graph", class_="flow-strip", style="padding:0;border:0;background:transparent"),
                                id_="flow-bar",
                                class_="flow-strip",
                            ),
                            air.Div(id_="chat"),
                            air.Div(
                                air.Div(
                                    air.Button("订成都 SUV", data_prompt="帮我在成都订一辆SUV，10月1日到10月3日"),
                                    air.Button("四类行情比价", data_prompt="帮我同时看看机票、酒店、租车和景点门票的行情"),
                                    air.Button("记住靠窗", data_prompt="记住我以后都想要靠窗的座位"),
                                    air.Button("回忆偏好", data_prompt="你还记得我的偏好吗？"),
                                    class_="quick",
                                ),
                                air.Div("空闲：等待你的下一个问题", id_="status"),
                                air.Div(
                                    air.Div(id_="approval-detail"),
                                    air.Div(
                                        air.Button("批准执行", class_="btn hold small", data_url="/api/approve/stream", id_="approve-btn"),
                                        air.Button("驳回，重新出方案", class_="btn no small", data_url="/api/reject/stream", id_="reject-btn"),
                                        class_="approve-actions",
                                    ),
                                    id_="approval",
                                ),
                                air.Div(
                                    air.Input(id_="msg", type_="text", placeholder="比如：帮我在成都订一辆SUV，附近有什么好玩的？"),
                                    air.Button("发送", class_="btn", id_="send-btn"),
                                    class_="inputrow",
                                ),
                                class_="chat-foot",
                            ),
                            class_="chat-wrap",
                        ),
                        id_="page-chat",
                        class_="page",
                        data_active="true",
                    ),
                    # ---- 行程页 ----
                    air.Div(
                        air.Div(
                            air.Div(
                                air.Div(
                                    air.Span("行程地图", class_="t"),
                                    air.Span("经纬度按公开边界线性投影", class_="n"),
                                    air.Span(id_="map-caption", class_="r"),
                                    class_="block-head",
                                ),
                                air.Div(air.Div("正在装入航段…", class_="blank"), id_="map", class_="route-map"),
                                class_="card-block",
                            ),
                            air.Div(
                                air.Div(
                                    air.Span("航段", class_="t"),
                                    air.Span("去程 / 回程各一条", class_="n"),
                                    class_="block-head",
                                ),
                                air.Div(air.Div("等待行程…", class_="blank"), id_="legs"),
                                class_="card-block",
                            ),
                            air.Div(
                                air.Div(air.Span("行程概览", class_="t"), class_="block-head"),
                                air.Div(id_="kpis", class_="kpis"),
                                air.Div(
                                    air.Span("有库存的城市", class_="n"),
                                    id_="city-chips",
                                    class_="chips-row",
                                ),
                                class_="card-block",
                            ),
                            class_="page-split",
                        ),
                        id_="page-trip",
                        class_="page",
                        data_active="false",
                    ),
                    # ---- 探索页 ----
                    air.Div(
                        air.Div(
                            air.Div(
                                air.Div(air.Span("城市", class_="t"), air.Span(id_="explore-caption", class_="r"), class_="block-head"),
                                air.Div(id_="explore-cities", class_="city-grid"),
                                class_="card-block",
                            ),
                            air.Div(air.Div(id_="explore", class_="deck"), class_="card-block"),
                            class_="explore-wrap",
                        ),
                        id_="page-explore",
                        class_="page",
                        data_active="false",
                    ),
                    # ---- 看板页：机场出港牌 ----
                    air.Div(
                        air.Div(
                            air.Div(
                                air.Span("INVENTORY BOARD · 库存航显", class_="label"),
                                air.Span("2026", class_="label", id_="board-date"),
                                air.Span("--:--:--", class_="clock", id_="board-clock"),
                                class_="board-top",
                            ),
                            air.Div(
                                air.Div(air.B("0", id_="lamp-total"), air.Span("库存总数"), class_="lamp-cell"),
                                air.Div(air.B("0", id_="lamp-booked"), air.Span("已订出"), class_="lamp-cell ok"),
                                air.Div(air.B("0", id_="lamp-open"), air.Span("可订空位"), class_="lamp-cell"),
                                air.Div(air.B("0", id_="lamp-hold"), air.Span("待签挂起"), class_="lamp-cell hold"),
                                air.Div(air.B("0", id_="lamp-flights"), air.Span("在售航班"), class_="lamp-cell info"),
                                class_="board-lamps",
                            ),
                            air.Div(
                                air.Button("全部", class_="seg", id_="seg-all", type_="button", aria_pressed="true", data_kind="all"),
                                air.Button("租车", class_="seg", id_="seg-car", type_="button", aria_pressed="false", data_kind="car"),
                                air.Button("酒店", class_="seg", id_="seg-hotel", type_="button", aria_pressed="false", data_kind="hotel"),
                                air.Button("门票", class_="seg", id_="seg-spot", type_="button", aria_pressed="false", data_kind="spot"),
                                air.Button("只看可订", class_="seg", id_="seg-open", type_="button", aria_pressed="false", data_only="1"),
                                air.Span("", id_="board-count", class_="board-count"),
                                class_="board-filter",
                            ),
                            air.Div(
                                air.Span(""), air.Span("名称", class_="name"), air.Span("城市", class_="city"),
                                air.Span("类型 / 档位", class_="kind"), air.Span("单价", class_="price"),
                                air.Span("状态", class_="stat"),
                                class_="board-head",
                            ),
                            air.Div(id_="board", class_="board-rows"),
                            class_="board-shell",
                        ),
                        id_="page-board",
                        class_="page board-page",
                        data_active="false",
                    ),
                    # ---- 订单页 ----
                    air.Div(
                        air.Div(
                            air.Div(
                                air.Div(
                                    air.Span("我的订单", class_="t"),
                                    air.Span("取消后库存自动释放", class_="n"),
                                    air.Span(id_="orders-caption", class_="r"),
                                    class_="block-head",
                                ),
                                air.Div(id_="orders", class_="orders"),
                                class_="card-block",
                            ),
                            air.Div(
                                air.Div(
                                    air.Span("本次结果", class_="t"),
                                    air.Span(id_="cards-caption", class_="n"),
                                    class_="block-head",
                                ),
                                air.Div(id_="cards", class_="deck"),
                                class_="card-block",
                            ),
                            air.Div(
                                air.Div(
                                    air.Span("审计流水", class_="t"),
                                    air.Span(id_="audit-caption", class_="n"),
                                    class_="block-head",
                                ),
                                air.Div(id_="audit-summary", class_="audit-summary"),
                                air.Div(id_="audit"),
                                class_="card-block",
                                id_="audit-block",
                            ),
                            class_="page-pad",
                            style="display:grid;gap:16px",
                        ),
                        id_="page-orders",
                        class_="page",
                        data_active="false",
                    ),
                    # ---- 运维页 ----
                    air.Div(
                        air.Div(
                            air.Div(
                                air.Div(air.Span("对话状态栈"), air.Span("dialog_state", class_="n"), class_="block-head"),
                                air.Div(id_="stack", class_="stack"),
                                class_="card-block",
                            ),
                            air.Div(
                                air.Div(air.Span("跨会话档案"), air.Span("Store", class_="n"), class_="block-head"),
                                air.Div(id_="prefs", class_="prefs"),
                                class_="card-block",
                            ),
                            air.Div(
                                air.Div(air.Span("节点时间线"), air.Span("最近的图节点", class_="n"), class_="block-head"),
                                air.Div(id_="trace", class_="trace"),
                                class_="card-block",
                            ),
                            class_="ops-grid",
                        ),
                        id_="page-ops",
                        class_="page page-pad",
                        data_active="false",
                    ),
                    class_="main",
                ),
                class_="app",
            ),
            air.Script(src="/static/app.js"),
        ),
        lang="zh-CN",
    )
