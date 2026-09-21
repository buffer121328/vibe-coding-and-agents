/* KnowledgeForge Lite · 控制台外壳 + 知识文档 + 评测治理
   对齐完整版 KnowledgeForge 的界面语言（antd 主题 + index.css）。
   与 workbench.js 分工：那边管智能问答，这边管壳层导航与两个治理视图。
   两个治理视图只对管理员开放——403 由服务端给出，页面只负责把原因说清楚。
   模型输出与用户输入一律当数据：只用 DOM 节点拼，不用 innerHTML。 */
(function () {
  "use strict";

  /* 控制台的记忆：当前工牌、当前视图，以及两个治理区各自的数据。
     两区数据分开存，是因为它们按角色各自开关——锁着的那区不能拿旧数据充数。 */
  const state = {
    userId: "it_staff",
    account: null,
    view: "qa",
    documents: [],
    docsLocked: false,
    summary: null,
    limits: { max_bytes: 8 * 1024 * 1024, suffixes: [".md"], chunk: { size: 400, overlap: 60 } },
    selectedDoc: "",
    cases: [],
    evalLocked: false,
    evalRunning: false,
    ragasRunning: false,
    results: {},
    evalSummary: null,
    selectedCase: "",
    reports: [],
    gate: 0.8,
  };

  /**
   * 按 id 取元素的小抄——全文件的 DOM 入口只有这一处，省得到处写长大的一串。
   * @param {string} id 页面元素的 id。
   * @returns {HTMLElement|null} 命中就返回节点；页面里没有这个 id 返回 null。
   */
  const $ = (id) => document.getElementById(id);
  const API = "/api";
  const VIEWS = { qa: "view-qa", docs: "view-docs", eval: "view-eval" };
  const NAV = { qa: "nav-qa", docs: "nav-docs", eval: "nav-eval" };
  const PAGE_NAMES = { qa: "智能问答", docs: "知识文档", eval: "评测治理" };

  /**
   * 造一个元素并顺手设好类名和文字。模型输出与用户输入一律当数据，
   * 所以全文件的节点都从这个口子长出来，而不是拼一段字符串塞给容器。
   * @param {string} tag 标签名，如 "div"、"span"。
   * @param {string} [className] 类名；不传就不设。
   * @param {string} [textContent] 文本内容；不传就留空，交给后续 appendChild 填。
   * @returns {HTMLElement} 新建的节点。
   */
  function el(tag, className, textContent) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (textContent !== undefined) node.textContent = textContent;
    return node;
  }

  /* JS 造出来的图标走服务端渲染的那份 sprite —— 图标定义只有 web/pages.py 一处。 */
  /**
   * 造一个图标节点，引用页面里那份 sprite——图标定义只有 web/pages.py 一处，
   * JS 造出来的图标也走同一份，免得两边各画一套慢慢长歪。
   * @param {string} name sprite 里的图标名，对应 `<use href="#i-名字">`。
   * @param {string} [className] 额外类名；不传就是 "icon"。
   * @returns {SVGElement} 造好的 svg 节点。
   */
  function ico(name, className) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", className || "icon");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  /**
   * 把对象拼成查询串，顺手丢掉空值——免得后端收到一堆 `a=&b=` 的空字段，
   * 也让调用处可以直接把可选项写成 undefined 而不用先判断。
   * @param {Object} params 键值对，值一般是字符串或数字。
   * @returns {string} 形如 `a=1&b=2`；一个有效字段都没有时返回空串。
   */
  function qs(params) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, value);
    });
    return search.toString();
  }

  /* 403 单独算一种错误：它不是"出错了"，而是"这张工牌进不来"。
     两者要分开，是因为处理方式相反——权限问题要把整块换成说明（说清要哪张牌），
     而别的错误只该在消息条上添一句，页面其余部分照旧能用。 */
  class Forbidden extends Error {}

  /**
   * 统一取数封装：403 抛 Forbidden 交给调用处换整块说明；
   * 其余非 2xx 把后端给的 detail 挖出来抛成人话，页面上直接显示原因。
   * @param {string} url 请求地址，查询串由调用方拼好。
   * @param {RequestInit} [options] fetch 的选项（method / body）；不传就是一次 GET。
   * @returns {Promise<*>} 解好的 JSON。
   */
  async function api(url, options) {
    const resp = await fetch(url, options);
    if (resp.status === 403) {
      let detail = "这一区需要管理员工牌";
      try {
        const payload = await resp.json();
        detail = payload.detail || detail;
      } catch (_err) { /* 保持默认文案 */ }
      throw new Forbidden(detail);
    }
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const payload = await resp.json();
        detail = payload.detail || payload.message || detail;
      } catch (_err) { /* 保持 statusText */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  /**
   * 读一条 SSE 流，每收到一帧就回调给调用方。
   * 手撸 fetch + ReadableStream 而不用 EventSource：评测接口是 POST 流，
   * EventSource 只发 GET，塞不了工牌，也没法按状态码分成"权限不足"和"请求失败"。
   * @param {string} url 流式接口地址。
   * @param {Function} onEvent 收到一帧时的回调，签名为 (event, payload) => void。
   * @returns {Promise<void>} 流读完即返回；403 抛 Forbidden，其余失败抛 Error。
   */
  async function streamSSE(url, onEvent) {
    const resp = await fetch(url, { method: "POST" });
    if (resp.status === 403) {
      let detail = "这一区需要管理员工牌";
      try {
        const payload = await resp.json();
        detail = payload.detail || detail;
      } catch (_err) { /* 默认文案 */ }
      throw new Forbidden(detail);
    }
    if (!resp.ok) throw new Error("请求失败：" + resp.status);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let index;
      while ((index = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, index);
        buf = buf.slice(index + 2);
        let event = "message";
        const dataLines = [];
        block.split("\n").forEach((line) => {
          if (line.startsWith("event:")) event = line.slice(6).trim() || "message";
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        });
        if (!dataLines.length) continue;
        onEvent(event, JSON.parse(dataLines.join("\n")));
      }
    }
  }

  /* ── 壳层：导航与视图切换 ─────────────────────────────── */

  /**
   * 换一页：把三块视图和三个导航项按名字对上，并补拉这一页要用的数据。
   * .is-on 和 hidden 两个都设，是因为 CSS 里 .view 自带 display 规则会盖掉 [hidden]，
   * 只靠其中一个都会漏出"两页同屏"的缝。
   * @param {string} name 视图名（qa / docs / eval）。
   * @returns {void}
   */
  function setView(name) {
    state.view = name;
    Object.entries(VIEWS).forEach(([key, id]) => {
      const node = $(id);
      if (node) {
        node.classList.toggle("is-on", key === name);
        node.hidden = key !== name;
      }
    });
    Object.entries(NAV).forEach(([key, id]) => {
      const button = $(id);
      if (button) button.classList.toggle("is-on", key === name);
    });
    const page = PAGE_NAMES[name] || name;
    if ($("page-name")) $("page-name").textContent = page;
    if ($("crumb-page")) $("crumb-page").textContent = page;
    closeNav();
    if (name === "docs") loadDocuments();
    if (name === "eval") loadEvaluation();
  }

  /**
   * 窄屏下拉出侧边导航（宽屏下那按钮不出现，走的是 sider-toggle 那条路）。
   * @returns {void}
   */
  function openNav() {
    document.body.classList.add("is-nav-open");
    $("scrim").hidden = false;
  }

  /**
   * 收起窄屏导航。切视图、点遮罩、按 Escape 都会走到这里，
   * 所以它得能对"本来就没开"的状态安全地重复执行。
   * @returns {void}
   */
  function closeNav() {
    document.body.classList.remove("is-nav-open");
    $("scrim").hidden = true;
  }

  /* ── 抽屉 ─────────────────────────────────────────────── */

  /**
   * 拉出右侧抽屉（qa / docs / eval 三个区共用一个壳）。
   * 只有传了 title 才改抬头那两行，这样"内容重新装一遍"的调用不必再重复念一次标题。
   * @param {string} name 抽屉标识（qa / docs / eval）。
   * @param {string} [title] 抽屉标题；不传就沿用上一次的。
   * @param {string} [sub] 标题下面那行小字（一般是文件名或工牌名）。
   * @returns {void}
   */
  function openDrawer(name, title, sub) {
    if (title && $(name + "-drawer-title")) {
      $(name + "-drawer-title").textContent = title;
      $(name + "-drawer-sub").textContent = sub || "—";
    }
    $(name + "-drawer").hidden = false;
  }

  /**
   * 收起抽屉。三个抽屉共用一个 Escape 处理，那里会把三个名字逐个念一遍，
   * 所以这里必须对"页面上没有这个抽屉""本来就没开"都无害——查不到就当没事，不抛错。
   * @param {string} name 抽屉标识（qa / docs / eval）。
   * @returns {void}
   */
  function closeDrawer(name) {
    const node = $(name + "-drawer");
    if (node) node.hidden = true;
  }

  /**
   * 取抽屉的内容容器并先擦干净——上一次的切块或用例详情不该留在新内容的下面。
   * @param {string} name 抽屉标识（qa / docs / eval）。
   * @returns {HTMLElement} 已清空的内容容器。
   */
  function drawerBody(name) {
    const body = $(name + "-drawer-body");
    body.textContent = "";
    return body;
  }

  /* ── 共享小件 ─────────────────────────────────────────── */

  /**
   * 字节数换成人看的大小。三档就够——文档最大也就几 MB，
   * 再往上加单位只会让人多花一秒去数零。
   * @param {number} value 字节数；空值按 0 处理。
   * @returns {string} 形如 "820 B"、"8.0 KB"、"2.3 MB"。
   */
  function fmtBytes(value) {
    const size = Number(value || 0);
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
    return (size / 1024 / 1024).toFixed(1) + " MB";
  }

  /**
   * 造一个状态小标签；配色由 kind 决定，不传就是中性灰。
   * @param {string} label 标签文字。
   * @param {string} [kind] 配色类名，如 "is-ok"、"is-bad"、"is-warn"。
   * @returns {HTMLElement} 标签节点。
   */
  function tag(label, kind) {
    return el("span", "tag" + (kind ? " " + kind : ""), label);
  }

  /**
   * 造一张统计卡：大数字 + 上面的标签 + 可选的一行小字。
   * @param {string} label 卡片标签，如 "已索引"。
   * @param {string|number} value 主数字。
   * @param {string} [kind] 配色类名，如 "is-ok"、"is-warn"；不传就是默认色。
   * @param {string} [foot] 底下那行补充说明；不传就不画。
   * @returns {HTMLElement} 卡片节点。
   */
  function statCard(label, value, kind, foot) {
    const card = el("div", "stat" + (kind ? " " + kind : ""));
    card.appendChild(el("div", "label", label));
    card.appendChild(el("div", "value", String(value)));
    if (foot) card.appendChild(el("div", "foot", foot));
    return card;
  }

  /**
   * 画"这一区需要管理员工牌"的整块说明。
   * 那颗按钮不是改本地状态，而是找工牌架上写着「公司管理员」的卡片替用户点一下——
   * 身份只有工牌架一处说得算；绕过它直接改 state，下一次 /whoami 就会把这个小动作冲掉。
   * @param {HTMLElement} target 承载说明的容器。
   * @param {string} [message] 具体原因（后端给的 detail）；不传就用一句通用说法。
   * @returns {void}
   */
  function renderLocked(target, message) {
    target.textContent = "";
    target.appendChild(el("h3", null, "这一区需要管理员工牌"));
    target.appendChild(el("p", null, message || "知识文档与评测治理按角色开放。切到「公司管理员」即可进入。"));
    const button = el("button", "btn is-primary", "切到公司管理员工牌");
    button.type = "button";
    button.addEventListener("click", () => {
      const card = [...document.querySelectorAll(".badge-card")]
        .find((item) => item.querySelector("b") && item.querySelector("b").textContent === "公司管理员");
      if (card) card.click();
    });
    target.appendChild(button);
  }

  /* ── 知识文档 ─────────────────────────────────────────── */

  /**
   * 画文档区顶部那排统计卡。summary 为空是个有意义的状态（这一区被锁着），
   * 所以显式画一句引导，而不是留一片空白让人以为页面坏了。
   * @param {Object|null} summary 文档总览（documents / indexed / quarantined / chunks / schema）。
   * @returns {void}
   */
  function renderDocsSummary(summary) {
    const target = $("docs-summary");
    target.textContent = "";
    if (!summary) {
      target.appendChild(el("div", "empty", "切到「公司管理员」工牌后，这里会显示文档总览。"));
      return;
    }
    target.appendChild(statCard("文档", summary.documents));
    target.appendChild(statCard("已索引", summary.indexed, "is-ok"));
    target.appendChild(statCard("已隔离", summary.quarantined, summary.quarantined ? "is-bad" : ""));
    target.appendChild(statCard("切块", summary.chunks));
    target.appendChild(statCard("索引 schema", summary.schema,
      summary.schema_stale ? "is-warn" : "", summary.schema_stale ? "需要重建索引" : ""));
  }

  /**
   * 状态 → 标签。判断顺序有讲究：隔离排在最前（它压根没进索引），
   * 然后才看索引里在不在，最后才轮到"待重建""未登记"这些边角状态。
   * @param {Object} row 一行文档登记记录（status / in_index）。
   * @returns {HTMLElement} 状态标签。
   */
  function statusTag(row) {
    if (row.status === "quarantined") return tag("已隔离", "is-bad");
    if (row.in_index) return tag("已索引", "is-ok");
    if (row.status === "stale") return tag("待重建", "is-warn");
    if (row.status === "unknown") return tag("未登记", "is-mute");
    return tag(row.status, "is-mute");
  }

  /**
   * 画文档登记簿（每次整表重画，以 state 为准）。
   * 隔离原因挂在条目下面另起一行，而不是塞进「状态」那一格：信号往往有好几条，
   * 塞进去会把这一行撑得比别的行高出一大截，表里所有列的线就全跟着错位，
   * 清单越长越看不清；想细看的人点开那一行就行，默认状态下每行一样高。
   * @returns {void}
   */
  function renderDocumentsTable() {
    const wrap = $("docs-table");
    wrap.textContent = "";
    const table = el("table", "grid");
    const head = el("tr");
    ["文件名", "部门", "密级", "块", "状态", "大小", "内容哈希", "操作"].forEach((label) => {
      head.appendChild(el("th", null, label));
    });
    table.appendChild(head);
    const tbody = el("tbody");
    state.documents.forEach((row) => {
      const line = el("tr", row.status === "quarantined" ? "is-bad" : "");
      const name = el("td");
      name.appendChild(el("span", "cell-name", row.source));
      if (row.accession) name.appendChild(el("span", "cell-meta", "登记号 " + String(row.accession).padStart(2, "0")));
      line.appendChild(name);
      line.appendChild(el("td", null, row.department_label || row.department));
      line.appendChild(el("td", null, row.sensitivity_label || row.sensitivity));
      line.appendChild(el("td", "num", String(row.chunks)));
      const statusCell = el("td");
      statusCell.appendChild(statusTag(row));
      line.appendChild(statusCell);
      line.appendChild(el("td", "num", fmtBytes(row.bytes)));
      line.appendChild(el("td", "num", row.hash_prefix || "—"));
      const actions = el("td", "actions");
      const group = el("div", "cell-actions");
      const view = el("button", "btn is-link", "查看分块");
      view.type = "button";
      view.addEventListener("click", () => openDocDetail(row.source));
      group.appendChild(view);
      const kill = el("button", "btn is-link is-danger", "删除");
      kill.type = "button";
      kill.addEventListener("click", () => {
        // 第一次点只上膛：真点错了还有 4 秒退路，也比弹窗打断手顺一点
        if (kill.dataset.armed === "1") deleteDocument(row.source);
        else {
          kill.dataset.armed = "1";
          kill.textContent = "确认删除？";
          setTimeout(() => {
            if (kill.dataset.armed === "1") {
              kill.dataset.armed = "0";
              kill.textContent = "删除";
            }
          }, 4000);
        }
      });
      group.appendChild(kill);
      actions.appendChild(group);
      line.appendChild(actions);
      tbody.appendChild(line);

      // 隔离原因单独一行：计数留在条目上，清单点开才展开
      // （不塞进状态格，是因为它会把那一行撑高，整张表的行高就再也对不齐了）
      if (row.signals && row.signals.length) {
        tbody.appendChild(signalRow(row.signals));
      }
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  /**
   * 造隔离信号的展开行：条目上只留一句"3 条扫描信号"，点开才列具体清单。
   * 默认收起 + 同步 aria-expanded，是因为这行跨满全表、内容长短不一，
   * 默认摊开会把整张登记簿顶下去；屏幕阅读器也得知道它是开是合。
   * @param {Array<string>} signals 扫描给出的信号描述列表。
   * @returns {HTMLElement} 一行跨满全表的展开行。
   */
  function signalRow(signals) {
    const line = el("tr", "sub-row");
    const cell = el("td");
    cell.colSpan = 8;
    const list = el("ul", "signal-list");
    list.hidden = true;
    signals.forEach((signal) => list.appendChild(el("li", null, signal)));
    const toggle = el("button", "disclosure", `${signals.length} 条扫描信号`);
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("click", () => {
      list.hidden = !list.hidden;
      toggle.setAttribute("aria-expanded", String(!list.hidden));
      toggle.textContent = list.hidden ? `${signals.length} 条扫描信号` : "收起信号";
    });
    cell.appendChild(toggle);
    cell.appendChild(list);
    line.appendChild(cell);
    return line;
  }

  /* 换工牌会连发两次请求（旧牌一次、新牌一次）。谁先回来不确定，
     所以要拿序号把过期的那次结果丢掉——否则旧牌的 403 可能盖掉新牌的数据。
     用法：发请求前 ++ 并存下这一刻的号，回来先比一次，号不等就整段作废
     （连错误也不写——旧牌那句"需要管理员工牌"对新牌来说是假的）。
     两个区各留一个序号，是因为两趟请求彼此独立，共用一个号会让先到的文档
     结果把还在飞的评测请求一起判成过期。 */
  let docsSeq = 0;
  let evalSeq = 0;

  /**
   * 拉文档区数据（登记簿 + 总览 + 切块参数上限）；403 就换整块说明。
   * @returns {Promise<void>} 无返回值；过期的那次响应会静默作废。
   */
  async function loadDocuments() {
    const seq = ++docsSeq;
    try {
      const payload = await api(`${API}/documents?` + qs({ user_id: state.userId }));
      if (seq !== docsSeq) return;
      state.documents = payload.documents || [];
      state.summary = payload.summary || null;
      state.limits = payload.limits || state.limits;
      state.docsLocked = false;
      $("docs-locked").hidden = true;
      // 只在实验台还空着时给默认值：已有输入时不动它，免得把用户手上调过的旋钮冲掉
      if (!$("lab-size").value) resetLabKnobs();
      renderDocsSummary(state.summary);
      renderDocumentsTable();
    } catch (err) {
      if (seq !== docsSeq) return;
      if (err instanceof Forbidden) {
        state.docsLocked = true;
        renderLocked($("docs-locked"), err.message);
        $("docs-locked").hidden = false;
        // 摘要卡留空：下面那块锁定面板已经把"为什么进不去、怎么进"说完了，
        // 同一屏上两句话说同一件事，读者只会怀疑是不是还有别的意思。
        $("docs-summary").textContent = "";
        $("docs-table").textContent = "";
        return;
      }
      setMessage("docs-message", "读文档区失败：" + err.message, "is-bad");
    }
  }

  /**
   * 写一行操作反馈。kind 决定这句话的分量：is-bad 是失败、is-warn 是"成了但有情况"、
   * is-ok 是成了。文案一律带上原因（"上传失败：xxx"而不是干巴巴一个"失败"），
   * 是因为这一区的报错多半来自权限和嵌入服务，不把原因说出来，用户根本不知道下一步点哪。
   * @param {string} id 显示反馈的元素 id。
   * @param {string} text 要显示的话；空值就清空这一行。
   * @param {string} [kind] 配色类名（is-bad / is-warn / is-ok）；不传就是中性灰。
   * @returns {void}
   */
  function setMessage(id, text, kind) {
    const node = $(id);
    if (!node) return;
    node.textContent = text || "";
    node.className = "msg" + (kind ? " " + kind : "");
  }

  /**
   * 上传并入库。一次可以拖多篇，走同一个请求——入库这趟要连着调嵌入接口，很慢，
   * 所以处理期间把按钮禁掉，免得用户以为没反应又点一次，把同一批文件入两遍。
   * @param {FileList|Array<File>} fileList 用户选中的文件；空列表直接返回。
   * @returns {Promise<void>} 无返回值；结果画在文档区的消息条上。
   */
  async function uploadDocuments(fileList) {
    const files = [...fileList];
    if (!files.length) return;
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    const button = $("docs-upload");
    button.disabled = true;
    setMessage("docs-message", `入库 ${files.length} 篇…（要调嵌入接口，稍等）`);
    try {
      const payload = await api(`${API}/documents/upload?` + qs({ user_id: state.userId }), {
        method: "POST",
        body: form,
      });
      setMessage("docs-message", payload.summary || "入库完成", payload.quarantined ? "is-warn" : "is-ok");
      if (payload.overview) {
        state.documents = payload.overview.documents || [];
        state.summary = payload.overview.summary || null;
        renderDocsSummary(state.summary);
        renderDocumentsTable();
      }
    } catch (err) {
      setMessage("docs-message", err instanceof Forbidden ? err.message : "上传失败：" + err.message, "is-bad");
    } finally {
      button.disabled = false;
      $("docs-file").value = "";
      $("docs-file-names").textContent = "";
    }
  }

  /**
   * 删一篇文档。后端会把源文件、索引、账本一起级联清掉，
   * 所以成功后直接拿返回的总览整表重画，而不是在本地数组里抹一行——
   * 账本上的计数、待重建标记都可能跟着变，以服务器说的为准。
   * @param {string} source 文档名（它就是这篇的主键）。
   * @returns {Promise<void>} 无返回值；结果画在消息条上。
   */
  async function deleteDocument(source) {
    try {
      const payload = await api(
        `${API}/documents/${encodeURIComponent(source)}?` + qs({ user_id: state.userId }),
        { method: "DELETE" },
      );
      if (payload.overview) {
        state.documents = payload.overview.documents || [];
        state.summary = payload.overview.summary || null;
        renderDocsSummary(state.summary);
        renderDocumentsTable();
      }
      setMessage("docs-message", `已删除 ${payload.source}：源文件移除，索引与账本级联清理`, "is-ok");
      // 删掉的正好是抽屉里那篇：抽屉留着只会显示已经不存在的内容，直接收掉
      if (state.selectedDoc === source) closeDrawer("docs");
    } catch (err) {
      setMessage("docs-message", "删除失败：" + err.message, "is-bad");
    }
  }

  /**
   * 打开一篇文档的分块：抽屉里逐块列正文。被隔离的文档只给扫描信号——
   * 它的切块不在索引里，硬画出来等于暗示"这些能搜到"。
   * 读完还要把正文灌进切块实验台（loadLabFromChunks）：两件事本是同一批内容，
   * 让人看完切块想调参数时不必再回头复制粘贴一遍。
   * @param {string} source 文档名。
   * @returns {Promise<void>} 无返回值；失败画在抽屉里。
   */
  async function openDocDetail(source) {
    state.selectedDoc = source;
    const box = drawerBody("docs");
    openDrawer("docs", "查看分块", source);
    box.appendChild(el("p", "hint", "正在读切块…"));
    try {
      const payload = await api(`${API}/documents/${encodeURIComponent(source)}/chunks?` + qs({ user_id: state.userId }));
      box.textContent = "";
      if (payload.status === "quarantined") {
        box.appendChild(el("h3", null, "这篇被隔离了"));
        box.appendChild(el("p", "hint",
          "投毒扫描命中，所以它的切块不在检索索引里。下面是扫描给出的信号："));
        const list = el("ul", "signal-list");
        (payload.signals || []).forEach((signal) => list.appendChild(el("li", null, signal)));
        box.appendChild(list);
        return;
      }
      if (!payload.chunks.length) {
        box.appendChild(el("div", "empty", "账本里有这篇，但索引里没有切块——可能需要重建索引。"));
        return;
      }
      payload.chunks.forEach((chunk) => {
        // 块号旁边的标题路径：切完块之后，"这块从文档哪一节切下来"就只存在这里了
        const title = el("h3", null, `第 ${chunk.chunk_index} 块 · ${chunk.text.length} 字`);
        if (chunk.heading) title.appendChild(el("span", "cell-meta", chunk.heading));
        box.appendChild(title);
        const pre = el("pre", "chunk-text");
        pre.textContent = chunk.text;
        box.appendChild(pre);
      });
      loadLabFromChunks(source, payload.chunks);
    } catch (err) {
      box.textContent = "";
      box.appendChild(el("p", "warn", "读切块失败：" + err.message));
    }
  }

  /* ── 切块实验台 ───────────────────────────────────────── */

  const LAB_TEXT_LIMIT = 8000;
  let labTimer = null;

  /**
   * 实验台旋钮的出厂值：跟当前生效的切块上限走。
   * 拿服务器给的 limits 而不是写死数字，是为了让"每块上限 400"这两个地方不会各说各话。
   * @returns {{size: number, overlap: number}} 每块字数上限与重叠字数。
   */
  function labDefaults() {
    const chunk = (state.limits && state.limits.chunk) || {};
    return { size: Number(chunk.size) || 400, overlap: Number(chunk.overlap) || 60 };
  }

  /**
   * 把两个旋钮拨回默认值——点了「复位」或者换了一篇文档时用。
   * @returns {void}
   */
  function resetLabKnobs() {
    const defaults = labDefaults();
    $("lab-size").value = String(defaults.size);
    $("lab-overlap").value = String(defaults.overlap);
  }

  /* 相邻两块真实重叠了多少字：从上一块尾巴和这一块开头比出来，不靠旋钮假设。
     重叠是切块器按原样复制过来的，所以"这一块开头 k 个字等于上一块结尾"是准的。 */
  /**
   * 量出这一块和上一块到底重叠了多少字：拿"这一块开头 k 个字"去比"上一块结尾"，
   * k 从大到小试，第一个对上的就是答案。
   * 为什么不直接信旋钮给的值：旋钮说的是"请求了多少"，正文里真重叠多少还取决于
   * 文本长度、后端是否截断、这一趟是不是真按参数切——两边一旦不一致，
   * 标错重叠比不标更误导人（读者会以为看到的重复是切块器干的，其实不是）。
   * @param {string} prev 上一块正文。
   * @param {string} cur 这一块正文。
   * @param {number} cap 最多试到多少字（也就是这次请求的重叠上限），免得白比一大圈。
   * @returns {number} 真实重叠字数；量不出来就是 0。
   */
  function overlapLength(prev, cur, cap) {
    const limit = Math.min(cap, prev.length, cur.length);
    for (let k = limit; k > 0; k -= 1) {
      if (prev.endsWith(cur.slice(0, k))) return k;
    }
    return 0;
  }

  /**
   * 画实验台那排读数（块数、平均字数、最长、每块上限、重叠）。
   * 上限与重叠跟默认值不一样时标黄：那是"你正在看非默认参数切出来的结果"的提示，
   * 免得把调参后的效果误当成系统本来的表现。
   * @param {Object} payload 一次切块的结果（chunks / chunk_size / overlap）。
   * @returns {void}
   */
  function renderLabStats(payload) {
    const box = $("lab-stats");
    box.textContent = "";
    if (!payload || !payload.chunks.length) return;
    const defaults = labDefaults();
    const counts = payload.chunks.map((chunk) => chunk.chars);
    const average = Math.round(counts.reduce((sum, value) => sum + value, 0) / counts.length);
    const changed = payload.chunk_size !== defaults.size || payload.overlap !== defaults.overlap;
    [
      ["块", payload.chunks.length, false],
      ["平均字数", average, false],
      ["最长", Math.max(...counts), false],
      ["每块上限", payload.chunk_size, changed],
      ["重叠", payload.overlap, changed],
    ].forEach(([label, value, warn]) => {
      const item = el("span", "reading" + (warn ? " is-warn" : ""));
      item.appendChild(el("b", null, String(value)));
      item.appendChild(el("span", null, label));
      box.appendChild(item);
    });
  }

  /**
   * 逐块画切块结果，并把"开头这一截是上一块的重叠"直接标在正文里。
   * 标出来是这一台最该回答的问题：重叠不是抽象数字，得让人看见哪几个字是重复的，
   * 才知道调大调小会带来什么。
   * @param {Object} payload 一次切块的结果（chunks 里每块带 text / chars / chunk_index）。
   * @returns {void}
   */
  function renderLabChunks(payload) {
    const box = $("lab-chunks");
    box.textContent = "";
    const cap = payload.overlap || 0;
    let previous = "";
    payload.chunks.forEach((chunk) => {
      const text = chunk.text || "";
      const card = el("article", "chunk-card");
      const head = el("div", "chunk-head");
      head.appendChild(el("span", "chunk-no", `第 ${chunk.chunk_index} 块`));
      head.appendChild(el("span", null, `${chunk.chars} 字`));
      const overlap = previous ? overlapLength(previous, text, cap) : 0;
      if (overlap > 0) head.appendChild(tag(`头 ${overlap} 字是上一块的重叠`, "is-warn"));
      card.appendChild(head);
      const body = el("p", "chunk-body");
      if (overlap > 0) {
        body.appendChild(el("mark", "chunk-hit", text.slice(0, overlap)));
        body.appendChild(document.createTextNode(text.slice(overlap)));
      } else {
        body.appendChild(document.createTextNode(text));
      }
      card.appendChild(body);
      box.appendChild(card);
      previous = text;
    });
  }

  /**
   * 拿实验台里的文本和两个旋钮调一次切块接口，把读数与分块画在下面。
   * 正文要截到 LAB_TEXT_LIMIT：它是走查询串传过去的，塞太长会被浏览器或网关截掉，
   * 那时结果会悄悄变成"只切了前半篇"，比明说一句"只切了前 8000 字"难判断得多。
   * 两个旋钮留空就是不传：让后端用它自己的默认值，而不是前端替它猜一个。
   * @returns {Promise<void>} 无返回值；结果画在实验台里，失败画在消息条上。
   */
  async function runLab() {
    const text = $("lab-text").value;
    if (!text.trim()) {
      setMessage("lab-message", "先粘一段文本，或在上面的表里点「查看分块」把正文带过来。", "is-warn");
      $("lab-stats").textContent = "";
      $("lab-chunks").textContent = "";
      return;
    }
    const size = Number($("lab-size").value) || undefined;
    const overlap = $("lab-overlap").value === "" ? undefined : Number($("lab-overlap").value);
    const source = state.selectedDoc || "切块预览.md";
    setMessage("lab-message", "切块中…");
    try {
      const payload = await api(`${API}/documents/${encodeURIComponent(source)}/chunks?` + qs({
        user_id: state.userId,
        text: text.slice(0, LAB_TEXT_LIMIT),
        chunk_size: size,
        overlap,
      }));
      renderLabStats(payload);
      renderLabChunks(payload);
      const clipped = text.length > LAB_TEXT_LIMIT ? `（只切了前 ${LAB_TEXT_LIMIT} 字）` : "";
      setMessage("lab-message", `切出 ${payload.chunks.length} 块${clipped}`, "is-ok");
    } catch (err) {
      setMessage("lab-message", err instanceof Forbidden ? err.message : "切块失败：" + err.message, "is-bad");
    }
  }

  /**
   * 敲字时防抖：停手 350ms 才真去切一次。
   * 切一趟要过嵌入接口，每敲一个字都发一遍既卡手又白烧算力，所以只留最后一版。
   * @returns {void}
   */
  function scheduleLab() {
    if (labTimer) clearTimeout(labTimer);
    labTimer = setTimeout(() => {
      labTimer = null;
      runLab();
    }, 350);
  }

  /* 把一篇文档的正文带进实验台，让「查看分块」和「调切块」接上。 */
  /**
   * 把一篇文档的切块正文灌进实验台并立刻切一遍。
   * 旋钮先复位：正文换了一篇，还沿用上一篇调过的参数，很容易把两份结果看成"同一套参数"下的差别。
   * @param {string} source 文档名；顺手记成当前选中文档，实验台后续请求都以它为准。
   * @param {Array<Object>} chunks 该文档的切块，取出 text 拼回整篇正文。
   * @returns {void}
   */
  function loadLabFromChunks(source, chunks) {
    state.selectedDoc = source;
    $("lab-source").textContent = "来源：" + source;
    $("lab-text").value = chunks.map((chunk) => chunk.text).join("\n\n");
    resetLabKnobs();
    runLab();
  }

  /* ── 评测治理 ─────────────────────────────────────────── */

  /**
   * 画评测区顶部那排统计卡。summary 为空代表"还没跑过"，
   * 这时要明说怎么跑、跑完会看到什么——留白会让人以为评测坏了，而不是还没开始。
   * @param {Object|null} summary 一次评测的汇总（total / passed / pass_rate / behavior_rate / hit_rate / avg_latency_ms）。
   * @returns {void}
   */
  function renderEvalSummary(summary) {
    const target = $("eval-summary");
    target.textContent = "";
    if (!summary) {
      target.appendChild(el("div", "empty",
        "还没跑过。点「运行门禁评测」跑一遍，通过率、行为符合率、检索命中率会出现在这里。"));
      return;
    }
    const pass = summary.passed_gate ? "is-ok" : "is-bad";
    target.appendChild(statCard("用例", summary.total));
    target.appendChild(statCard("通过", `${summary.passed}/${summary.total}`, pass,
      `门禁线 ${Math.round((summary.gate || state.gate) * 100)}%`));
    target.appendChild(statCard("通过率", Math.round((summary.pass_rate || 0) * 100) + "%", pass));
    target.appendChild(statCard("行为符合", Math.round((summary.behavior_rate || 0) * 100) + "%"));
    target.appendChild(statCard("检索命中", Math.round((summary.hit_rate || 0) * 100) + "%"));
    target.appendChild(statCard("平均耗时", summary.avg_latency_ms + "ms"));
  }

  /* 点一行用例：抽屉给这条的完整档案（期望/实际/引用/为什么没通过）。 */
  /**
   * 把一条用例的档案铺进抽屉：期望什么、实际引用了什么、命中多少、耗时、没通过的原因。
   * 还没跑过的用例也照样能点开看——那正是"这条到底想考什么"最该被看见的时候，
   * 所以没有 result 时画的是引导而不是空白。
   * @param {Object} item 用例定义（question / expect / expected_docs / actor_name / user_id）。
   * @param {Object} [result] 这条的跑分结果；不传就只画用例本身。
   * @returns {void}
   */
  function showCaseDetail(item, result) {
    const box = drawerBody("eval");
    openDrawer("eval", "用例详情", item.actor_name || item.user_id);
    const head = el("div", "answer-meta");
    if (result) head.appendChild(tag(result.passed ? "通过" : "未通过", result.passed ? "is-ok" : "is-bad"));
    head.appendChild(tag(item.expect === "refuse" ? "期望拒答" : "期望作答", "is-mute"));
    box.appendChild(head);
    box.appendChild(el("h3", null, item.question));

    const rows = [
      ["该召回的文档", (item.expected_docs || []).join("、") || "（无——拒答题本来就该空手而归）"],
      ["实际引用", (result && result.cited_docs || []).join("、") || "—"],
      ["检索命中", result && result.expected_docs && result.expected_docs.length
        ? Math.round((result.hit || 0) * 100) + "%" : "—"],
      ["证据资格", (result && result.evidence_status) || "—"],
      ["耗时", result ? result.latency_ms + "ms" : "—"],
    ];
    const list = el("dl", "detail-list");
    rows.forEach(([label, value]) => {
      list.appendChild(el("dt", null, label));
      list.appendChild(el("dd", null, value));
    });
    box.appendChild(list);
    if (!result) {
      box.appendChild(el("p", "hint", "点「运行门禁评测」跑一遍，这条的结果会填进来。"));
      return;
    }
    if (result.reason) box.appendChild(el("p", "hint", result.reason));
    if (result.warn) box.appendChild(el("p", "warn", result.warn));
    if (result.answer_preview) {
      box.appendChild(el("h3", null, "答案开头"));
      const pre = el("pre", "chunk-text");
      pre.textContent = result.answer_preview;
      box.appendChild(pre);
    }
  }

  /**
   * 记下选中的用例，并只翻选中态，不重画整表。
   * 点一下就该只动一下：整表重画会把滚动位置和行上的状态一起打乱，
   * 用户正看着的那条会跳走。
   * @param {string} caseId 用例 id。
   * @returns {void}
   */
  function selectCase(caseId) {
    state.selectedCase = caseId;
    document.querySelectorAll("#eval-table tbody tr").forEach((row) => {
      row.classList.toggle("is-selected", row.id === "eval-row-" + caseId);
    });
  }

  /**
   * 画评测用例表（整表重画）。每行的格子都跟跑分结果绑定，所以结果一到就直接体现出来；
   * 行本身可点，点开是这条的档案；已跑过且没通过的整行标红，扫一眼就能找到要看的几条。
   * @returns {void}
   */
  function renderCaseTable() {
    const wrap = $("eval-table");
    wrap.textContent = "";
    const table = el("table", "grid");
    const head = el("tr");
    ["用例", "期望", "实际", "命中", "引用出处", "耗时", "结论"].forEach((label) => {
      head.appendChild(el("th", null, label));
    });
    table.appendChild(head);
    const tbody = el("tbody");
    tbody.id = "eval-rows";
    state.cases.forEach((item) => {
      const result = state.results[item.id];
      const line = el("tr", "is-clickable");
      line.id = "eval-row-" + item.id;
      const title = el("td");
      title.appendChild(el("span", "cell-name", item.question));
      title.appendChild(el("span", "cell-meta", item.actor_name || item.user_id));
      line.appendChild(title);
      const expectCell = el("td");
      expectCell.appendChild(tag(item.expect === "refuse" ? "拒答" : "作答",
        item.expect === "refuse" ? "is-bad" : "is-ok"));
      line.appendChild(expectCell);
      line.appendChild(el("td", null, result ? result.status : "—"));
      line.appendChild(el("td", "num", result && result.expected_docs && result.expected_docs.length
        ? Math.round((result.hit || 0) * 100) + "%" : "—"));
      line.appendChild(el("td", null, result && result.cited_docs && result.cited_docs.length
        ? result.cited_docs.join("、") : "—"));
      line.appendChild(el("td", "num", result ? result.latency_ms + "ms" : "—"));
      const mark = el("td");
      mark.appendChild(result
        ? tag(result.passed ? "通过" : "未通过", result.passed ? "is-ok" : "is-bad")
        : tag("待跑", "is-mute"));
      line.appendChild(mark);
      if (result) line.classList.add(result.passed ? "" : "is-bad");
      if (state.selectedCase === item.id) line.classList.add("is-selected");
      line.addEventListener("click", () => {
        selectCase(item.id);
        showCaseDetail(item, state.results[item.id]);
      });
      tbody.appendChild(line);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  /**
   * 收下一条跑分结果（SSE 每回来一条调一次）。
   * 每次都整表重画，而不是就地改那一行的几个格子：行高、红标、选中态都跟"哪些格子有值"
   * 绑在一起，逐格改很容易和重画后的表对不上；整表也就几十行，重画的代价远小于状态不一致。
   * 选中态由 state.selectedCase 重新盖回去，所以重画不会把用户选的那条弄丢；
   * 命中当前选中的那条时，连抽屉里的详情一起刷新，让"跑着跑着详情也跟着长出来"。
   * @param {Object} result 一条跑分结果（case_id / passed / status / hit / cited_docs / latency_ms）。
   * @returns {void}
   */
  function applyCaseResult(result) {
    state.results[result.case_id] = result;
    const item = state.cases.find((entry) => entry.id === result.case_id);
    if (item) renderCaseTable();
    if (item && state.selectedCase === result.case_id) showCaseDetail(item, result);
  }

  /**
   * 画 Ragas 三张指标卡。averages 为空就画成待跑态（数值位给"—" + 一句说明），
   * 而不是干脆不画：三指标是这一区的固定栏目，位置得先在，
   * 用户才知道这里会出什么、要按哪个按钮去换它。数据到位后同一位子填上数字，页面不跳。
   * @param {Object|null} averages 三个指标的均值；不传或为空表示还没打分。
   * @returns {void}
   */
  function renderRagas(averages) {
    const panel = $("eval-ragas-panel");
    panel.textContent = "";
    const grid = el("div", "metrics");
    [
      ["faithfulness", "Faithfulness", "答案有没有编：每个陈述能否在资料里找到依据"],
      ["context_recall", "ContextRecall", "检索漏没漏：标准答案的要点召回了多少"],
      ["answer_relevancy", "AnswerRelevancy", "答非所问：答案是不是在回答这个问题"],
    ].forEach(([key, label, hint]) => {
      const metric = el("div", "metric" + (averages ? "" : " is-pending"));
      metric.appendChild(el("span", "value",
        averages && averages[key] !== undefined ? Number(averages[key]).toFixed(2) : "—"));
      metric.appendChild(el("span", "label", label));
      metric.appendChild(el("span", "hint", hint));
      grid.appendChild(metric);
    });
    panel.appendChild(grid);
    if (!averages) {
      panel.appendChild(el("p", "hint",
        "还没打分。点「跑 Ragas 三指标」——每条要调 3 次裁判模型，慢，所以它和门禁分开跑。"));
    }
  }

  /**
   * 画历史报告列表。报告是留档产物，点一条就整篇读进抽屉；
   * 一条都没有时给一句"跑一次就会留档"，免得人以为报告这东西本来就没有。
   * @returns {void}
   */
  function renderReports() {
    const box = $("eval-reports");
    box.textContent = "";
    if (!state.reports.length) {
      box.appendChild(el("div", "empty", "还没有报告。跑一次门禁评测就会在这里留档。"));
      return;
    }
    const list = el("div", "reports");
    state.reports.forEach((report) => {
      const row = el("div", "report");
      row.appendChild(el("span", "when", report.created_at.replace("T", " ").slice(0, 19)));
      row.appendChild(el("span", null, report.path));
      const spacer = el("span", "spacer");
      row.appendChild(spacer);
      row.appendChild(tag(`${report.passed}/${report.total}（${Math.round(report.pass_rate * 100)}%）`,
        report.pass_rate >= state.gate ? "is-ok" : "is-bad"));
      row.appendChild(tag(`命中 ${Math.round((report.hit_rate || 0) * 100)}%`, "is-info"));
      row.addEventListener("click", () => openReport(report.path));
      list.appendChild(row);
    });
    box.appendChild(list);
  }

  /**
   * 打开一份历史报告：抽屉里逐条列出当时的结论与原因。
   * 报告是"当时那一跑"的快照，所以只读不重跑——拿今天的索引去重跑，就不是这份报告了。
   * @param {string} name 报告文件名（同时是它在服务端的路径片段）。
   * @returns {Promise<void>} 无返回值；失败画在抽屉里。
   */
  async function openReport(name) {
    const box = drawerBody("eval");
    openDrawer("eval", "评测报告", name);
    box.appendChild(el("p", "hint", "正在读报告…"));
    try {
      const report = await api(`${API}/evaluation/reports/${encodeURIComponent(name)}?` + qs({ user_id: state.userId }));
      box.textContent = "";
      Object.values(report.cases || {}).forEach((item) => {
        const card = el("div", "ev-item");
        const head = el("div", "answer-meta");
        head.appendChild(tag(item.passed ? "通过" : "未通过", item.passed ? "is-ok" : "is-bad"));
        card.appendChild(head);
        card.appendChild(el("div", "name", item.question));
        if (item.reason) card.appendChild(el("div", "meta", item.reason));
        box.appendChild(card);
      });
    } catch (err) {
      box.textContent = "";
      box.appendChild(el("p", "warn", "读报告失败：" + err.message));
    }
  }

  /**
   * 拉评测区数据（用例 + 门禁线 + 历史报告）；403 就换整块说明。
   * 序号与文档区同一套道理：换工牌会连发两次请求，旧牌那次的 403 不能盖掉新牌的结果。
   * @returns {Promise<void>} 无返回值；过期的那次响应会静默作废。
   */
  async function loadEvaluation() {
    const seq = ++evalSeq;
    try {
      const payload = await api(`${API}/evaluation/cases?` + qs({ user_id: state.userId }));
      if (seq !== evalSeq) return;
      state.cases = payload.cases || [];
      state.gate = payload.gate || 0.8;
      state.evalLocked = false;
      $("eval-locked").hidden = true;
      renderEvalSummary(state.evalSummary || null);
      renderCaseTable();
      // 三指标归零回待跑态：上一张牌打的分不属于这张牌，留着会被当成这张牌的成绩
      renderRagas(null);
      await loadReports();
    } catch (err) {
      if (seq !== evalSeq) return;
      if (err instanceof Forbidden) {
        state.evalLocked = true;
        renderLocked($("eval-locked"), err.message);
        $("eval-locked").hidden = false;
        $("eval-table").textContent = "";
        $("eval-summary").textContent = "";
        // 旧牌的报告也要擦掉：锁着的页面上留着它，等于漏了上一张牌能看的东西
        renderReports();
        return;
      }
      setMessage("eval-message", "读评测用例失败：" + err.message, "is-bad");
    }
  }

  /**
   * 拉最近几份报告并画出来。读不到就当作"没有报告"，不往外抛——
   * 报告只是补充材料，不该因为它拉失败，把整个评测区的加载也拖断。
   * @returns {Promise<void>} 无返回值。
   */
  async function loadReports() {
    try {
      const payload = await api(`${API}/evaluation/reports?` + qs({ user_id: state.userId, limit: 8 }));
      state.reports = payload.reports || [];
    } catch (_err) {
      state.reports = [];
    }
    renderReports();
  }

  /**
   * 跑门禁评测：逐条走完整问答链路，结果随 SSE 一条条回来。
   * 开跑前先把上一轮结果清空——新旧混在一张表里，就分不清哪些是这一跑的；
   * state.evalRunning 拦住重复点击，因为这一趟很贵，点两下等于把黄金集跑两遍。
   * @returns {Promise<void>} 无返回值；进度与结论画在消息条与统计卡上。
   */
  async function runEvaluation() {
    if (state.evalRunning) return;
    state.evalRunning = true;
    state.results = {};
    renderCaseTable();
    const button = $("eval-run");
    button.disabled = true;
    setMessage("eval-message", "逐条跑黄金集…（每条都要过一次完整问答链路）");
    try {
      await streamSSE(`${API}/evaluation/run?` + qs({ user_id: state.userId }), (event, payload) => {
        if (event === "case") {
          applyCaseResult(payload);
          setMessage("eval-message",
            `已跑 ${Object.keys(state.results).length}/${state.cases.length}：${payload.question}`);
        }
        if (event === "summary") {
          state.evalSummary = payload.summary;
          renderEvalSummary(payload.summary);
          setMessage("eval-message",
            `完成：通过 ${payload.summary.passed}/${payload.summary.total}，报告已存 ${payload.report}`,
            payload.summary.passed_gate ? "is-ok" : "is-bad");
          loadReports();
        }
        if (event === "error") setMessage("eval-message", payload.message || "评测中断", "is-bad");
      });
    } catch (err) {
      setMessage("eval-message", err instanceof Forbidden ? err.message : "评测失败：" + err.message, "is-bad");
    } finally {
      state.evalRunning = false;
      button.disabled = false;
    }
  }

  /**
   * 跑 Ragas 三指标。每条要调 3 次裁判模型，比门禁慢得多，所以和门禁分开跑：
   * 门禁是必过的闸，三指标是想细看质量时才等的——绑在一起会把每次门禁都拖成乌龟。
   * 均值按累计平均边跑边算（第 n 条来时用 (前均值 × (n-1) + 本条) / n），
   * 于是不必等全部回来才出第一个数字，跑到一半也能看出大致水平。
   * @returns {Promise<void>} 无返回值；进度与均值画在消息条与三张指标卡上。
   */
  async function runRagas() {
    if (state.ragasRunning) return;
    state.ragasRunning = true;
    const button = $("eval-ragas");
    button.disabled = true;
    setMessage("eval-message", "逐条跑 Ragas 三指标…（每条要调 3 次裁判，比较慢）");
    const averages = { faithfulness: 0, context_recall: 0, answer_relevancy: 0 };
    let count = 0;
    try {
      await streamSSE(`${API}/evaluation/ragas?` + qs({ user_id: state.userId }), (event, payload) => {
        if (event === "case") {
          count += 1;
          ["faithfulness", "context_recall", "answer_relevancy"].forEach((key) => {
            averages[key] = (averages[key] * (count - 1) + Number(payload[key] || 0)) / count;
          });
          renderRagas(averages);
          setMessage("eval-message", `已打分 ${count}/${state.cases.length}：${payload.question}`);
        }
        if (event === "summary") {
          renderRagas(payload.averages);
          setMessage("eval-message", "Ragas 完成：三个指标见下", "is-ok");
        }
        if (event === "error") setMessage("eval-message", payload.message || "Ragas 打分失败", "is-bad");
      });
    } catch (err) {
      setMessage("eval-message", err instanceof Forbidden ? err.message : "Ragas 失败：" + err.message, "is-bad");
    } finally {
      state.ragasRunning = false;
      button.disabled = false;
    }
  }

  /* ── 账号 ─────────────────────────────────────────────── */

  /* 顶栏右上角：头像 + 显示名 + 角色·部门。完整版 Layout 的 user menu 同一套。
     访客没有账号，就老实写"访客"。 */
  /**
   * 读当前账号并画进顶栏；顺便把登录账号的角色定成初始工牌。
   * 身份来自账号，不是页面上的开关——所以这里不是"给个默认值"，
   * 而是把工牌对齐到账号自带的角色：登录进来的管理员一落地就在管理员工牌上，
   * 不用先被当成 IT 员工，再自己找地方切一次。
   * 读不到（未登录、演示模式）就按访客显示，绝不让顶栏空着。
   * @returns {Promise<void>} 无返回值。
   */
  async function loadAccount() {
    try {
      const info = await (await fetch("/api/auth/me")).json();
      const account = info.account;
      state.account = account;
      if (account) {
        $("account-avatar").textContent = (account.display_name || account.username).slice(0, 1);
        $("account-name").textContent = account.display_name;
        $("account-meta").textContent = `${account.role_label} · ${account.department_label}`;
        // 登录账号的角色就是初始工牌——身份来自账号，不是页面上的开关
        if (account.badge_id && account.badge_id !== state.userId) {
          state.userId = account.badge_id;
        }
      } else {
        $("account-avatar").textContent = "客";
        $("account-name").textContent = "访客";
        $("account-meta").textContent = "演示模式 · 未登录";
      }
    } catch (_err) {
      $("account-name").textContent = "访客";
      $("account-meta").textContent = "读不到账号信息";
    }
  }

  /**
   * 开关账号下拉菜单。force 是给"点页面别处收起"那处用的：
   * 那里要的是明确的"关"，如果再 toggle 一次，就会把刚关上的又打开。
   * @param {boolean} [force] true 强制展开、false 强制收起；不传就取反当前状态。
   * @returns {void}
   */
  function toggleAccountMenu(force) {
    const menu = $("account-menu");
    menu.hidden = force === undefined ? !menu.hidden : !force;
  }

  /**
   * 登出：先等服务端把会话清掉再跳登录页。
   * 顺序不能反——先跳的话，登录页那一刻其实还算登录着，回退键一按又回来了。
   * @returns {Promise<void>} 无返回值；页面会离开当前地址。
   */
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  /* ── 接线 ─────────────────────────────────────────────── */

  /**
   * 把控制台的按钮与快捷键接上。集中在一处，方便一眼看清这个视图有哪些入口。
   * @returns {void}
   */
  function bind() {
    Object.entries(NAV).forEach(([key, id]) => {
      const button = $(id);
      if (button) button.addEventListener("click", () => setView(key));
    });
    $("nav-open").addEventListener("click", openNav);
    $("account-menu").previousElementSibling.addEventListener("click", (event) => {
      // 这一下不能冒泡到 document：那里的"点别处收起"会立刻把刚打开的菜单关掉
      event.stopPropagation();
      toggleAccountMenu();
    });
    $("account-logout").addEventListener("click", () => logout());
    document.addEventListener("click", () => toggleAccountMenu(false));
    $("scrim").addEventListener("click", closeNav);
    ["qa", "docs", "eval"].forEach((name) => {
      const close = $(name + "-drawer-close");
      if (close) close.addEventListener("click", () => closeDrawer(name));
    });
    $("qa-open-catalog").addEventListener("click", () => {
      if (window.ForgeWorkbench && window.ForgeWorkbench.setTab) window.ForgeWorkbench.setTab("catalog");
      else openDrawer("qa");
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      // 三个抽屉共用这一处 Escape：谁开着就收谁，判断"哪个开着"反而多此一举
      // （closeDrawer 对没开的、页面上不存在的都无害），顺带把窄屏导航也收了
      ["qa", "docs", "eval"].forEach(closeDrawer);
      closeNav();
    });

    const input = $("docs-file");
    input.addEventListener("change", () => {
      // 选完只报文件名，不预览内容：正文以服务器为准，点「上传入库」才算真入库
      const names = [...input.files].map((file) => file.name);
      $("docs-file-names").textContent = names.length ? `已选：${names.join("、")}` : "";
    });
    $("docs-upload").addEventListener("click", () => uploadDocuments(input.files));
    $("docs-refresh").addEventListener("click", () => loadDocuments());
    const zone = document.querySelector(".dropzone");
    // 拖放必须先拦下浏览器默认动作：不拦的话松手时浏览器会直接打开或下载这个文件，
    // 页面当场被换掉。dragenter / dragover 一起挂，是为了让高亮不闪。
    ["dragenter", "dragover"].forEach((type) => {
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.add("is-over");
      });
    });
    ["dragleave", "drop"].forEach((type) => {
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.remove("is-over");
      });
    });
    // dataTransfer 只在拖放事件里有效，所以文件必须在 drop 这一刻就取出来交给上传
    zone.addEventListener("drop", (event) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) uploadDocuments(files);
    });

    // 文档区的两个选项卡
    [["list", "docs-panel-list"], ["upload", "docs-panel-upload"]].forEach(([key, panel]) => {
      $("docs-tab-" + key).addEventListener("click", () => {
        $("docs-tab-list").classList.toggle("is-on", key === "list");
        $("docs-tab-upload").classList.toggle("is-on", key === "upload");
        $("docs-panel-list").hidden = key !== "list";
        $("docs-panel-upload").hidden = key !== "upload";
      });
    });

    // 「复位」也是"拨回默认值再切一遍"，这样一按就能和上面的读数对上
    $("lab-apply").addEventListener("click", () => runLab());
    $("lab-reset").addEventListener("click", () => {
      resetLabKnobs();
      runLab();
    });
    // 三个输入都挂防抖：敲字时不必每一下都切一趟，停手了再跑
    ["lab-text", "lab-size", "lab-overlap"].forEach((id) => {
      $(id).addEventListener("input", scheduleLab);
    });

    $("eval-run").addEventListener("click", () => runEvaluation());
    $("eval-ragas").addEventListener("click", () => runRagas());
    // 刷新只重读报告列表：用例是固定的，想重跑要按「运行门禁评测」，那是两件事
    $("eval-refresh").addEventListener("click", () => loadReports());

    // 侧边栏收起：窄屏下它是抽屉，宽屏下缩成图标列
    $("sider-toggle").addEventListener("click", () => {
      const collapsed = document.body.classList.toggle("is-sider-collapsed");
      // 收起后按钮只剩图标，文字得跟着撤——留着会被挤成一列竖排的碎字
      $("sider-toggle").querySelector("span").textContent = collapsed ? "" : "收起导航";
    });

    // 工牌只有一份真相：工作台在 /whoami 之后广播，这里对齐。
    document.addEventListener("forge:badge-changed", (event) => {
      const next = event.detail && event.detail.userId;
      if (!next || next === state.userId) return;
      state.userId = next;
      // 上一张牌的跑分结果不属于这张牌，先清空；只重拉当前这一页，
      // 没开着的那页切过去时 setView 自己会拉，这里跟着拉等于白发两次请求还互相打架
      state.results = {};
      if (state.view === "docs") loadDocuments();
      if (state.view === "eval") loadEvaluation();
    });
  }

  /**
   * 启动：接线 → 读账号 → 开局停在问答页 → 先把两个治理区的空态摆上。
   * 空态要在这里先画一遍，是因为两个治理区切过去才拉数据：不等它们自己动手，
   * 页面上就已经写清"怎么才能进来、跑一遍会看到什么"，而不是先给人一片白。
   * @returns {void}
   */
  function boot() {
    bind();
    loadAccount();
    // 旋钮先填上 config 的默认值（拿不到也回落 400/60）：它们不该因为当前工牌
    // 进不去文档区就空着——实验台的输入框空着，看着像坏了。
    resetLabKnobs();
    setView("qa");
    renderRagas(null);
    renderReports();
  }

  document.addEventListener("DOMContentLoaded", boot);
  // 工作台要借控制台的抽屉与视图切换：两个闭包只通过这个出口打交道
  window.ForgeConsole = { setView, state, openDrawer, closeDrawer };
})();
