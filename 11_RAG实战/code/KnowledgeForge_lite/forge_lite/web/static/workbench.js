/* KnowledgeForge Lite · 受控档案室工作台
   浏览器只记两样：当前工牌、当前会话号。正文、引用、轨迹都以服务器为准。
   一条纪律贯穿全文件：模型输出永远当数据——用 DOM 节点拼，不用 innerHTML。 */
(function () {
  "use strict";

  const KEY_USER = "forge-lite-user";
  const KEY_CONV = "forge-lite-conv";
  const ROUTE_LABELS = { bm25: "关键词", dense: "向量", vector: "向量", graph: "图谱", hybrid: "融合" };
  const TAB_IDS = { catalog: "tab-catalog", chunk: "tab-chunk", trace: "tab-trace" };

  const state = {
    userId: "it_staff",
    conversationId: "",
    conversations: [],
    messages: [],
    badges: [],
    badgeIndex: 0,
    catalog: [],
    catalogHidden: 0,
    prompts: [],
    empty: null,
    asking: false,
    filter: "",
    service: "unknown",
    tab: "catalog",
    tabMemo: { chunk: null, trace: null },
  };

  /**
   * 按 id 取元素的小抄——全文件的 DOM 入口只有这一处，省得到处写长大的一串。
   * @param {string} id 页面元素的 id。
   * @returns {HTMLElement|null} 命中就返回节点，页面里没有这个 id 就返回 null。
   */
  const $ = (id) => document.getElementById(id);

  /* ── 指针：只记工牌和会话号 ─────────────────────────── */

  /**
   * 把"当前工牌"和"当前会话号"这两个指针写进本地存储，刷新后还能回到原处。
   * 只记指针不记正文——正文以服务器为准。
   * @returns {void}
   */
  function remember() {
    try {
      localStorage.setItem(KEY_USER, state.userId);
      if (state.conversationId) localStorage.setItem(KEY_CONV, state.conversationId);
      else localStorage.removeItem(KEY_CONV);
    } catch (_err) {
      /* 隐私模式记不住指针，会话仍在服务器上 */
    }
  }

  /**
   * 从本地存储把上次的工牌和会话号读回来；读不到（无痕模式、首次来访）就回落到默认工牌。
   * @returns {void}
   */
  function recall() {
    try {
      state.userId = localStorage.getItem(KEY_USER) || "it_staff";
      state.conversationId = localStorage.getItem(KEY_CONV) || "";
    } catch (_err) {
      state.userId = "it_staff";
      state.conversationId = "";
    }
  }

  /* ── 通用小件 ───────────────────────────────────────── */

  /**
   * 统一取数封装：非 2xx 时把后端给的 detail 挖出来抛成 Error，页面上直接显示人话；
   * 204 表示"成功但没有正文"，返回 null 而不是硬解 JSON。
   * @param {string} url 请求地址，查询串由调用方拼好。
   * @param {RequestInit} [options] fetch 的选项（method / headers / body）；不传就是一次 GET。
   * @returns {Promise<*>} 解好的 JSON；204 时返回 null。
   */
  async function api(url, options) {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const payload = await resp.json();
        detail = payload.detail || payload.message || detail;
      } catch (_err) { /* 保持 statusText */ }
      throw new Error(detail);
    }
    if (resp.status === 204) return null;
    return resp.json();
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

  /**
   * 造一个元素并顺手设好类名和文字。不用模板串拼 HTML 的纪律，就是从这个小件开始的。
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

  /**
   * 把一段纯文本按 **加粗** 拆开，强调处给 <strong>、其余原样落成文本节点。
   * @param {HTMLElement} target 要填充的容器。
   * @param {string} text 带 Markdown 加粗标记的文本（引文原文就是这个形态）。
   * @returns {void}
   */
  function appendInline(target, text) {
    // 只认 **加粗**：引文里的强调直接给 <strong>，其余原样
    String(text || "").split(/(\*\*[^*]+\*\*)/).forEach((part) => {
      const bold = part.match(/^\*\*([^*]+)\*\*$/);
      if (bold) target.appendChild(el("strong", null, bold[1]));
      else if (part) target.appendChild(document.createTextNode(part));
    });
  }

  /**
   * 状态 → 徽标颜色的映射。
   * 受控响应（证据不足、证据冲突、需人工复核）单独占一档：它们和"答得不太准"不是一回事，
   * 而是"这段内容本来就不该被当成答案读"，所以要给比普通警告更扎眼的颜色；
   * 拒答直接标红，其他一律按正常通过。分档的依据只有一条：读者该不该信这条答案。
   * @param {Object} payload 一条回答的载荷。
   * @param {string} [payload.status] 运行状态，refuse 表示拒答、regen 表示正在过门禁。
   * @param {string} [payload.response_status] 响应分类，受控响应在这里区分。
   * @returns {string} 类名：is-bad / is-warn / is-mute / is-ok 之一。
   */
  function stampClass(payload) {
    const status = payload.status || "";
    if (status === "refuse") return "is-bad";
    const response = payload.response_status || "";
    if (response === "partially_answered") return "is-warn";
    if (response === "human_review_required" || response === "conflicting_evidence") return "is-warn";
    if (status === "regen") return "is-mute";
    return "is-ok";
  }

  /**
   * 状态 → 徽标文案。后端给了 response_label 就用后端的（那是它自己定的说法，
   * 前端不该替它改口），只有拿不到标签时才按 status 兜一个词。
   * @param {Object} payload 一条回答的载荷。
   * @param {string} [payload.response_label] 后端给的状态文案。
   * @param {string} [payload.status] 运行状态。
   * @returns {string} 徽标文案；认不出来时返回空串，上层就不画这个标签。
   */
  function stampText(payload) {
    if (payload.response_label) return payload.response_label;
    if (payload.status === "refuse") return "已拒答";
    if (payload.status === "regen") return "正在过门禁";
    return payload.status === "ok" ? "已回答" : "";
  }

  /* ── 工牌架：先看清权限，再选身份 ───────────────────── */

  /**
   * 画工牌架：每张牌写明角色、看得见几篇、被裁掉几篇，点一下换身份。
   * 左右方向键也能在牌之间走：工牌是单选项（role="radio"），键盘用户不该被逼着用鼠标。
   * @returns {void}
   */
  function renderRack() {
    const rack = $("badge-rack");
    rack.textContent = "";
    state.badges.forEach((badge, index) => {
      const card = el("button", "badge-card");
      card.type = "button";
      card.setAttribute("role", "radio");
      card.setAttribute("aria-checked", String(badge.user_id === state.userId));
      card.tabIndex = badge.user_id === state.userId ? 0 : -1;
      card.appendChild(el("b", null, badge.name));
      card.appendChild(el("span", "role",
        (badge.role_label || badge.role) + " · " + (badge.department_label || badge.department)));
      const counts = el("span", "counts");
      counts.appendChild(el("i", null, "可见 " + (badge.visible_docs || []).length + " 篇"));
      if ((badge.hidden_docs || []).length) {
        counts.appendChild(el("i", "hidden", "裁掉 " + badge.hidden_docs.length + " 篇"));
      }
      card.appendChild(counts);
      card.title = badge.blurb || "";
      card.addEventListener("click", () => switchBadge(badge.user_id));
      card.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        event.preventDefault();
        state.badgeIndex = (index + (event.key === "ArrowRight" ? 1 : -1) + state.badges.length) % state.badges.length;
        const next = state.badges[state.badgeIndex];
        switchBadge(next.user_id);
      });
      rack.appendChild(card);
    });
  }

  /* ── 左栏：会话柜 ───────────────────────────────────── */

  /**
   * 画左栏的会话柜列表，当前开着的格子高亮；一条会话都没有时给一句带路的空态。
   * @returns {void}
   */
  function renderDrawers() {
    const box = $("drawers");
    box.textContent = "";
    if (!state.conversations.length) {
      box.appendChild(el("div", "empty",
        "还没有会话。问一句就会新开一格——会话存在服务器上，刷新不丢。"));
      return;
    }
    state.conversations.forEach((item) => {
      const row = el("button", "conv-item" + (item.id === state.conversationId ? " is-on" : ""));
      row.type = "button";
      row.appendChild(el("span", "title", item.title || "新会话"));
      const meta = el("span", "when", (item.updated_at || "").replace("T", " ").slice(5, 16));
      row.appendChild(meta);
      row.addEventListener("click", () => openConversation(item.id));
      box.appendChild(row);
    });
  }

  /* ── 中栏：问答纸 ───────────────────────────────────── */

  /* 受控响应：证据不足 / 冲突 / 需人工时，"答案"本身就不该被当成答案读，
     所以不用散文体，直接在气泡里给一条警示。完整版 ChatHistory 是同一处理。 */
  const CONTROLLED = new Set([
    "insufficient_evidence", "needs_clarification",
    "conflicting_evidence", "human_review_required", "source_unavailable",
  ]);

  /**
   * 这条回答是不是"受控响应"。命中就说明正文里那句话不是结论，只是警示的载体，
   * 渲染时不能再按普通答案处理。
   * @param {Object} payload 一条回答的载荷。
   * @param {string} [payload.response_status] 后端给的响应分类。
   * @returns {boolean} 属于受控响应返回 true，载荷缺失按 false 处理。
   */
  function isControlled(payload) {
    return Boolean(payload && CONTROLLED.has(payload.response_status || ""));
  }

  /**
   * 把答案正文画进气泡。受控响应换成警示框；正常答案按 [数字] 切成可点的引用角标。
   * 为什么要切：角标是答案和证据之间唯一的桥，整段当纯文本渲染的话读者只能自己数第几条，
   * 点不开就等于没有引用。流式中间帧会反复调它，所以每次都先清空再整段重画。
   * @param {HTMLElement} target 答案容器。
   * @param {string} answer 答案正文；流式时是半截的。
   * @param {Object} [payload] 该回答的载荷；中间帧还没有载荷，此时按普通答案渲染。
   * @returns {void}
   */
  function renderAnswerInto(target, answer, payload) {
    target.textContent = "";
    if (isControlled(payload)) {
      const box = el("div", "alert " + (payload.response_status === "conflicting_evidence" ? "is-bad" : "is-warn"));
      box.appendChild(el("h4", null, stampText(payload) || "受控响应"));
      box.appendChild(el("span", null, answer || ""));
      target.appendChild(box);
      return;
    }
    String(answer || "").split(/(\[\d+\])/).forEach((part) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (match) {
        const cite = el("button", "cite", match[1]);
        cite.type = "button";
        cite.title = "看第 " + match[1] + " 条的出处";
        cite.setAttribute("aria-label", "打开出处 " + match[1]);
        cite.addEventListener("click", () => openCitation(Number(match[1])));
        target.appendChild(cite);
      } else if (part) {
        appendInline(target, part);
      }
    });
  }

  /**
   * 画答案上方那排小标签：状态、意图、走的路由、执行人、告警。
   * @param {HTMLElement} meta 标签容器。
   * @param {Object} payload 该回答的载荷；没有就不画。
   * @returns {void}
   */
  function renderMeta(meta, payload) {
    meta.textContent = "";
    if (!payload) return;
    // 实时载荷带 route_chips；会话柜里的历史消息只有 routes 字符串
    const chips = payload.route_chips
      || String(payload.routes || "").split("+").map((item) => item.trim()).filter(Boolean)
        .map((id) => ({ id, label: ROUTE_LABELS[id] || id }));
    const status = stampText(payload);
    if (status) meta.appendChild(el("span", "tag " + stampClass(payload), status));
    const intentLabel = payload.intent_label || payload.intent;
    if (intentLabel) meta.appendChild(el("span", "tag is-warn", intentLabel));
    chips.forEach((item) => meta.appendChild(el("span", "tag is-info", item.label || item.id)));
    const actorLabel = typeof payload.actor === "string"
      ? payload.actor
      : (payload.actor && (payload.actor.name || payload.actor.user_id)) || "";
    if (actorLabel) meta.appendChild(el("span", "tag is-mute", actorLabel));
    if (payload.warn) meta.appendChild(el("span", "tag is-warn", payload.warn));
  }

  /**
   * 造一个图标节点，引用页面里那份 sprite——图标定义只有 web/pages.py 一处，
   * JS 造出来的图标也走同一份，避免两边各画一套慢慢长歪。
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
   * 造一个折叠面板（推理步骤 / 引用来源都靠它收起来）。完整版答案下方那两个 chip 是同一件事。
   * 默认收起：证据是"想深究时能看到"，不是每次都摊在答案前面。
   * @param {string} title 面板标题，显示在按钮上。
   * @param {Function} build 回调，收到面板体容器后往里塞内容，签名为 (body) => void。
   * @param {boolean} [open] 初始是否展开；不传按收起。
   * @returns {HTMLElement} 面板外壳（按钮 + 面板体）。
   */
  function fold(title, build, open) {
    const wrap = el("div");
    const button = el("button", "fold");
    button.type = "button";
    button.setAttribute("aria-expanded", String(Boolean(open)));
    button.appendChild(ico("chevron", "chev"));
    button.appendChild(el("span", null, title));
    const body = el("div", "fold-body");
    body.hidden = !open;
    button.addEventListener("click", () => {
      body.hidden = !body.hidden;
      button.setAttribute("aria-expanded", String(!body.hidden));
    });
    build(body);
    wrap.appendChild(button);
    wrap.appendChild(body);
    return wrap;
  }

  /**
   * 答案的下半部分：状态标签、折叠面板、反馈。流式回答落定后要整块重画，
   * 所以它单独成一个函数，appendTurn 和 askQuestion 都调它。
   * 引用来源和推理步骤都做成折叠面板：它们是想深究才看的证据，
   * 一跑攒下来的条数又可能很长，摊开在气泡下面会把答案本身淹掉。
   * @param {HTMLElement} host 承载这些附加块的空容器。
   * @param {Object} [payload] 该回答的载荷；缺失时什么都不画。
   * @returns {void}
   */
  function renderAnswerExtras(host, payload) {
    host.textContent = "";
    if (!payload) return;
    const meta = el("div", "answer-meta");
    renderMeta(meta, payload);
    host.appendChild(meta);

    const folds = el("div", "folds");
    const citations = payload.citations || [];
    if (citations.length) {
      folds.appendChild(fold(`引用来源 (${citations.length})`, (target) => {
        const list = el("div", "ev-list");
        citations.forEach((item) => list.appendChild(citationCard(item)));
        target.appendChild(list);
      }));
    }
    if (payload.run_id) {
      folds.appendChild(fold("推理步骤", (target) => {
        const list = el("div", "ev-list");
        (payload.queries || [payload.question]).filter(Boolean).forEach((query, index) => {
          list.appendChild(el("div", "ev-item",
            (index === 0 ? "原问题：" : "改写 " + index + "：") + query));
        });
        const button = el("button", "btn is-sm", "打开检索轨迹");
        button.type = "button";
        button.addEventListener("click", () => {
          setTab("trace");
          openTrace(payload.run_id);
        });
        target.appendChild(list);
        target.appendChild(button);
      }));
    }
    if (folds.children.length) host.appendChild(folds);

    const feedback = el("div", "feedback");
    [["thumbs-up", "有帮助"], ["thumbs-down", "没帮助"], ["flag", "报告问题"]].forEach(([name, label]) => {
      const button = el("button");
      button.type = "button";
      button.title = label;
      button.setAttribute("aria-label", label);
      button.appendChild(ico(name));
      button.addEventListener("click", () => {
        if (name === "flag") button.classList.toggle("is-on");
        else {
          feedback.querySelectorAll("button").forEach((item) => item.classList.remove("is-on"));
          button.classList.add("is-on");
        }
      });
      feedback.appendChild(button);
    });
    host.appendChild(feedback);
  }

  /**
   * 造一只头像：提问方和回答方各一个图标，鼠标悬停能看到名字。
   * @param {string} role 发言角色，"user" 是提问方，其余按回答方画。
   * @param {string} [name] 悬停提示里显示的名字；不传就不设提示。
   * @returns {HTMLElement} 头像节点。
   */
  function avatar(role, name) {
    const node = el("div", "turn-avatar");
    node.appendChild(ico(role === "user" ? "user" : "robot", "icon"));
    if (name) node.title = name;
    return node;
  }

  /**
   * 往转写区追加一段对话（一方发言），并返回三样把手给调用方：
   * turn（整段）、body（答案正文容器）、extras（答案下方的附加块容器）。
   * extras 单独留空一块，是因为流式回答落定时正文已经画好了，
   * 只有状态标签、引用这些附加块需要补画/重画——不分开就得把整个气泡推倒重来。
   * @param {string} role 发言角色："user" 或 "assistant"。
   * @param {string} content 正文；流式起步时可以是空串。
   * @param {Object} [payload] 该回答的载荷；用户那侧为 null，此时只画纯文本气泡。
   * @returns {{turn: HTMLElement, body: (HTMLElement|null), extras: HTMLElement}} 三个可继续操作的节点。
   */
  function appendTurn(role, content, payload) {
    const box = $("transcript");
    const hint = box.querySelector(".empty");
    if (hint) box.textContent = "";
    const turn = el("article", "turn is-" + role);
    turn.appendChild(avatar(role));

    const body = el("div", "turn-body");
    const bubble = el("div", "bubble");
    if (role === "user") {
      bubble.textContent = content;
    } else {
      const inner = el("div", "answer-body");
      if (payload && payload.status === "regen" && !content) inner.textContent = "正在过门禁…";
      else renderAnswerInto(inner, content, payload);
      bubble.appendChild(inner);
      if (isControlled(payload)) bubble.classList.add("is-controlled");
    }
    body.appendChild(bubble);
    const extras = el("div");
    if (role !== "user") body.appendChild(extras);
    turn.appendChild(body);
    box.appendChild(turn);
    if (role !== "user" && payload) renderAnswerExtras(extras, payload);
    scrollTranscript();
    return { turn, body: role === "user" ? null : bubble.querySelector(".answer-body"), extras };
  }

  /**
   * 造一张引用小卡，只写「[角标] 文档名」和一个跳去原文的按钮——
   * 这里只给线索，真要读原文就点进去调档。
   * @param {Object} item 一条引用记录。
   * @param {string|number} [item.marker] 引用角标编号；没有就不带前缀。
   * @param {string} [item.doc_id] 出处文档名。
   * @returns {HTMLElement} 引用卡节点。
   */
  function citationCard(item) {
    const card = el("div", "ev-item");
    card.appendChild(el("div", "name", (item.marker ? "[" + item.marker + "] " : "") + (item.doc_id || "")));
    const button = el("button", "btn is-link is-sm", "看这块原文");
    button.type = "button";
    button.addEventListener("click", () => {
      setTab("chunk");
      openChunk(item.doc_id, "");
    });
    card.appendChild(button);
    return card;
  }

  /**
   * 把转写区滚到底。流式吐字时每来一段都要跟着走，别让用户自己追着看。
   * @returns {void}
   */
  function scrollTranscript() {
    const box = $("transcript");
    box.scrollTop = box.scrollHeight;
  }

  /**
   * 画空会话的引导页：不是干巴巴一句"暂无数据"，而是一张能直接点的问题对照表——
   * 当前工牌能问什么、该看见什么结果、换张牌又会变成什么样，
   * 让人一眼看懂"同一句话换个身份问，答案不一样"这件事。
   * @returns {void}
   */
  function renderEmpty() {
    const box = $("transcript");
    box.textContent = "";
    const empty = el("div", "empty");
    empty.appendChild(el("strong", null, (state.empty && state.empty.title) || "从一格空会话开始"));
    empty.appendChild(el("p", null, (state.empty && state.empty.body)
      || "会话存在服务器上，刷新不会丢。换工牌会换一排会话——IT 打不开财务的。"));
    const mine = (state.prompts || []).filter((item) => item.user_id === state.userId).slice(0, 5);
    const others = (state.prompts || []).filter((item) => item.user_id !== state.userId).slice(0, 2);
    const table = el("table", "grid");
    const headRow = el("tr");
    ["问一句", "该看见什么", "换工牌对照"].forEach((label) => headRow.appendChild(el("th", null, label)));
    table.appendChild(headRow);
    const tbody = el("tbody");
    (mine.concat(others)).forEach((item) => {
      const row = el("tr");
      const ask = el("td");
      const btn = el("button", "btn is-link", item.question);
      btn.type = "button";
      btn.addEventListener("click", () => {
        $("q").value = item.question;
        $("q").focus();
        askQuestion();
      });
      ask.appendChild(btn);
      row.appendChild(ask);
      const expect = el("td");
      expect.appendChild(el("span", "tag " + (item.expect === "refuse" ? "is-bad" : "is-ok"),
        item.expect === "refuse" ? "拒答" : "作答"));
      expect.appendChild(el("span", "cell-meta", item.lesson || ""));
      row.appendChild(expect);
      row.appendChild(el("td", null, item.user_id === state.userId ? "当前工牌" : "换到 " + (item.actor_name || item.user_id)));
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    empty.appendChild(table);
    box.appendChild(empty);
  }

  /**
   * 把整段历史消息重画一遍（换会话、换工牌时用）；一条都没有就走空态引导。
   * @returns {void}
   */
  function renderTranscript() {
    const box = $("transcript");
    box.textContent = "";
    if (!state.messages.length) {
      renderEmpty();
      return;
    }
    state.messages.forEach((msg) => appendTurn(msg.role, msg.content, msg));
  }

  /* ── 右栏：证据抽屉（目录 / 出处 / 轨迹） ───────────── */

  /* 切换证据页。``reveal`` 控制要不要把抽屉拉出来——
     数据到位时（加载目录、换工牌）只刷新内容，不该擅自弹开抽屉。 */
  /**
   * 切换证据抽屉的那一页（目录 / 出处 / 轨迹），内容重新按记忆里的节点装回去。
   * @param {string} tab 目标页，取 "catalog" / "chunk" / "trace"。
   * @param {boolean} [reveal] 要不要顺手把抽屉拉出来；传 false 表示"数据到位了，只换内容"，
   *   不弹开抽屉——加载目录、换工牌都会调到这里，那时用户没要求看抽屉，擅自弹开会打断他手上的事。
   * @returns {void}
   */
  function setTab(tab, reveal) {
    state.tab = tab;
    Object.entries(TAB_IDS).forEach(([name, id]) => {
      const button = $(id);
      if (button) button.classList.toggle("is-on", name === tab);
    });
    if (reveal !== false && window.ForgeConsole && window.ForgeConsole.openDrawer) {
      window.ForgeConsole.openDrawer("qa");
    }
    const body = $("evidence-body");
    body.textContent = "";
    if (tab === "chunk") {
      if (state.tabMemo.chunk) body.appendChild(state.tabMemo.chunk);
      else body.appendChild(el("div", "empty", "点答案里的蓝色角标，这里打开对应的原文切块。"));
      return;
    }
    if (tab === "trace") {
      if (state.tabMemo.trace) body.appendChild(state.tabMemo.trace);
      else body.appendChild(el("div", "empty",
        "问一句之后，这里能看这一跑改了哪些查询、哪几路各召回什么。"));
      return;
    }
    renderCatalogInto(body);
  }

  /**
   * 把"这张工牌看得见的文档"清单画进抽屉：点一条就打开它的全文分块。
   * @param {HTMLElement} body 抽屉内容容器，调用方已经清空过。
   * @returns {void}
   */
  function renderCatalogInto(body) {
    body.appendChild(el("p", "hint",
      "这张工牌看得见的文档。看不见的不会出现在这里——权限在打分前就裁过了。"));
    const list = el("div", "ev-list");
    state.catalog.forEach((doc) => {
      const card = el("button", "ev-item");
      card.type = "button";
      card.style.textAlign = "left";
      card.style.cursor = "pointer";
      card.appendChild(el("div", "name", doc.source));
      card.appendChild(el("div", "meta",
        doc.department + " · " + doc.sensitivity + " · " + doc.chunk_count + " 块"));
      card.addEventListener("click", () => openDocument(doc.source));
      list.appendChild(card);
    });
    body.appendChild(list);
    // 裁掉的文档没有名字，只有条数——列出名字本身就是泄露
    if (state.catalogHidden > 0) {
      body.appendChild(el("p", "muted",
        "这张工牌另裁掉 " + state.catalogHidden + " 篇：内容与标题都不可见。"));
    }
  }

  /**
   * 先把出处页的节点记下来，再刷这一页。
   * 记下来是为了切走再切回来时内容还在，不用重新调档；
   * 只在当前正好停在出处页时才立刻重画，否则等于偷偷改了一个用户没在看的页面。
   * @param {HTMLElement} node 出处页要展示的节点。
   * @returns {void}
   */
  function setChunkView(node) {
    state.tabMemo.chunk = node;
    if (state.tab === "chunk") setTab("chunk");
  }

  /**
   * 点答案里的引用角标 [n] 时调它：从最近一条回答的引用记录里找出第 n 条，打开那块原文。
   * 找不到就明说"这一跑没记过 [n]"——角标点了没反应，比给出否定答案更让人心里没底。
   * @param {number} marker 引用角标编号（不含方括号）。
   * @returns {void}
   */
  function openCitation(marker) {
    const last = [...state.messages].reverse().find((msg) => msg.role === "assistant");
    let citations = (last && last.citations) || [];
    if (!citations.length && state.lastDone) citations = state.lastDone.citations || [];
    const hit = citations.find((item) => String(item.marker || "").replace(/[\[\]]/g, "") === String(marker));
    if (!hit || !hit.doc_id) {
      const note = el("p", "warn", "这一跑的引用记录里没有 [" + marker + "]。");
      setChunkView(note);
      setTab("chunk");
      return;
    }
    openChunk(hit.doc_id, (last && last.content) || "");
  }

  /**
   * 打开一块原文：拿到切块正文并高亮命中片段，顺手补一段图谱邻接当参照。
   * @param {string} docId 文档名。
   * @param {string} [needle] 要高亮的答案片段；只截前 40 个字去匹配，
   *   整段答案拿去匹配基本不可能命中，后端也不是全文搜索引擎。
   * @returns {Promise<void>} 无返回值；失败信息画在抽屉里而不往外抛。
   */
  async function openChunk(docId, needle) {
    const wrap = el("div");
    wrap.appendChild(el("p", "hint", "正在调档…"));
    setChunkView(wrap);
    setTab("chunk");
    try {
      const payload = await api("/api/chunks?" + qs({
        doc_id: docId, user_id: state.userId, highlight: needle ? needle.slice(0, 40) : "",
      }));
      wrap.textContent = "";
      wrap.appendChild(el("h3", null, payload.source + " · 第 " + payload.chunk_index + " 块"));
      const pre = el("pre", "chunk-text");
      const span = el("span");
      if (payload.highlight && payload.highlight.hit) {
        appendInline(span, payload.highlight.before || "");
        span.appendChild(el("mark", "chunk-hit", payload.highlight.hit));
        appendInline(span, payload.highlight.after || "");
      } else {
        appendInline(span, payload.text || "");
      }
      pre.appendChild(span);
      wrap.appendChild(pre);
      const entity = (payload.source || "").replace(/\.md$/, "");
      try {
        const graph = await api("/api/graph?" + qs({ entity, user_id: state.userId }));
        if (graph.edges && graph.edges.length) {
          wrap.appendChild(el("p", "hint", "图谱邻接（这张工牌看得见的边）："));
          const list = el("div", "ev-list");
          graph.edges.forEach((edge) => {
            list.appendChild(el("div", "ev-item",
              edge.head + " — " + edge.relation + " → " + edge.tail));
          });
          wrap.appendChild(list);
        }
      } catch (_err) { /* 图谱预览失败不挡原文 */ }
    } catch (err) {
      wrap.textContent = "";
      wrap.appendChild(el("p", "warn", "打不开这块：" + err.message));
    }
  }

  /**
   * 打开一篇文档的全部切块——目录里点一条走的就是这里，一次给全，方便通读。
   * @param {string} source 文档名。
   * @returns {Promise<void>} 无返回值；失败信息画在抽屉里。
   */
  async function openDocument(source) {
    const wrap = el("div");
    setChunkView(wrap);
    setTab("chunk");
    try {
      const payload = await api("/api/chunks?" + qs({ source, user_id: state.userId }));
      wrap.textContent = "";
      (payload.chunks || []).forEach((chunk) => {
        wrap.appendChild(el("h3", null, "第 " + chunk.chunk_index + " 块"));
        const pre = el("pre", "chunk-text");
        const span = el("span");
        appendInline(span, chunk.text);
        pre.appendChild(span);
        wrap.appendChild(pre);
      });
    } catch (err) {
      wrap.textContent = "";
      wrap.appendChild(el("p", "warn", err.message));
    }
  }

  /**
   * 画"各路召回"表：每一行是一条融合结果，横向列出它在各路检索里排第几。
   * 只取前 8 行——这张表是用来看"同一块东西在不同路里名次差多少"的，
   * 榜单拖到几十行反而看不出结构。
   * @param {HTMLElement} container 要挂进去的容器。
   * @param {Object} trace 轨迹载荷。
   * @param {Array} [trace.lanes] 融合后的行；空数组时直接不画表。
   * @returns {void}
   */
  function renderLanes(container, trace) {
    const rows = trace.lanes || [];
    if (!rows.length) return;
    const table = el("table", "grid");
    const head = el("tr");
    ["融合", "出处", "各路召回"].forEach((label) => head.appendChild(el("th", null, label)));
    table.appendChild(head);
    const tbody = el("tbody");
    rows.slice(0, 8).forEach((row) => {
      const line = el("tr");
      line.appendChild(el("td", "num", String(row.fused_rank || "")));
      line.appendChild(el("td", null, row.doc_id || "（未标注）"));
      const lanes = el("td");
      const laneWrap = el("div", "lane");
      (row.lanes || []).forEach((lane) => {
        const chip = el("span", "lane-item" + (lane.id === row.primary ? " is-main" : ""));
        chip.appendChild(document.createTextNode(lane.label || lane.id));
        if (lane.rank) {
          chip.appendChild(document.createTextNode(" · "));
          chip.appendChild(el("b", null, "第 " + lane.rank + " 名"));
        }
        laneWrap.appendChild(chip);
      });
      lanes.appendChild(laneWrap);
      line.appendChild(lanes);
      tbody.appendChild(line);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  /**
   * 打开一跑的检索轨迹：这一跑改写过哪些查询、各路召回什么、经过哪些环节。
   * 读完顺手记进 tabMemo，切走再切回来不用重新拉。
   * @param {string} runId 这一跑的执行 id；空值直接返回（没有它拉不到轨迹）。
   * @returns {Promise<void>} 无返回值；读不到就在抽屉里显示原因。
   */
  async function openTrace(runId) {
    if (!runId) return;
    const wrap = el("div");
    wrap.appendChild(el("p", "hint", "正在读轨迹…"));
    state.tabMemo.trace = wrap;
    setTab("trace");
    try {
      const trace = await api("/api/runs/" + encodeURIComponent(runId) + "/trace?" + qs({ user_id: state.userId }));
      wrap.textContent = "";
      wrap.appendChild(el("div", "answer-meta",
        el("span", "tag is-mute", trace.status_label || "-"),
        el("span", "tag " + (trace.evidence_label && trace.evidence_label.includes("不足") ? "is-bad" : "is-info"),
          "证据 " + (trace.evidence_label || "未评估")),
        el("span", "tag is-info", "路由 " + ((trace.route_labels || []).join(" + ") || "无"))));
      if ((trace.queries || []).length) {
        const list = el("ol", "signal-list");
        trace.queries.forEach((query) => list.appendChild(el("li", null, query)));
        wrap.appendChild(list);
      }
      renderLanes(wrap, trace);
      if ((trace.steps || []).length) {
        const steps = el("table", "grid");
        const head = el("tr");
        ["环节", "说明"].forEach((label) => head.appendChild(el("th", null, label)));
        steps.appendChild(head);
        const tbody = el("tbody");
        trace.steps.forEach((step) => {
          const row = el("tr");
          row.appendChild(el("td", null, step.title || step.lane));
          row.appendChild(el("td", null, step.detail || ""));
          tbody.appendChild(row);
        });
        steps.appendChild(tbody);
        wrap.appendChild(steps);
      }
      if (trace.warn) wrap.appendChild(el("p", "warn", trace.warn));
    } catch (err) {
      wrap.textContent = "";
      wrap.appendChild(el("p", "warn", "读不到轨迹：" + err.message));
    }
  }

  /* ── 会话动作 ───────────────────────────────────────── */

  /**
   * 拉当前工牌的会话列表。本地记着的那个会话号可能已经不属于这张牌（换牌、被删），
   * 所以对不上就清掉，改开最近更新的一格。
   * @returns {Promise<void>} 无返回值。
   */
  async function loadConversations() {
    const page = await api("/api/conversations?" + qs({ user_id: state.userId, limit: 50 }));
    state.conversations = page.items || [];
    const ids = new Set(state.conversations.map((item) => item.id));
    if (state.conversationId && !ids.has(state.conversationId)) state.conversationId = "";
    if (!state.conversationId && state.conversations.length) state.conversationId = state.conversations[0].id;
    remember();
    renderDrawers();
  }

  /**
   * 打开一格会话，把服务器上的历史消息取回来重画。
   * 消息的 payload 会被摊平到消息本身上（下面那个展开），
   * 这样渲染时不用到处写 msg.payload.xxx。
   * @param {string} id 会话 id。
   * @returns {Promise<void>} 无返回值。
   */
  async function openConversation(id) {
    state.conversationId = id;
    remember();
    renderDrawers();
    const detail = await api("/api/conversations/" + encodeURIComponent(id) + "?" + qs({ user_id: state.userId }));
    state.messages = (detail.messages || []).map((msg) => ({ ...msg, ...(msg.payload || {}) }));
    renderTranscript();
  }

  /**
   * 新开一格空会话，并立刻把光标送进提问框——开新格子的人下一步一定是打字。
   * @returns {Promise<void>} 无返回值。
   */
  async function createConversation() {
    const record = await api("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: state.userId, title: "新会话" }),
    });
    state.conversationId = record.id;
    state.messages = [];
    remember();
    await loadConversations();
    renderTranscript();
    $("q").focus();
  }

  /**
   * 删掉一格会话。删的要是当前这格，就把它从指针上摘掉，另外挑一格最近的顶上。
   * @param {string} id 要删的会话 id。
   * @returns {Promise<void>} 无返回值。
   */
  async function deleteConversation(id) {
    await api("/api/conversations/" + encodeURIComponent(id) + "?" + qs({ user_id: state.userId }), { method: "DELETE" });
    if (state.conversationId === id) {
      state.conversationId = "";
      state.messages = [];
    }
    await loadConversations();
    if (state.conversationId) await openConversation(state.conversationId);
    else renderTranscript();
  }

  /**
   * 把当前会话导成 Markdown 下载下来。走 fetch 拿 blob 再点一个临时链接触发下载，
   * 是因为普通链接带不了工牌参数，后端认不出这人有没有权限导这一格；
   * 文件名以后端给的 Content-Disposition 为准，它才是权威。
   * @returns {Promise<void>} 无返回值；没有当前会话就什么都不做。
   */
  async function exportConversation() {
    if (!state.conversationId) return;
    const url = "/api/conversations/" + encodeURIComponent(state.conversationId) + "/export?" + qs({ user_id: state.userId, format: "md" });
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("导出失败");
      const blob = await resp.blob();
      const matched = (resp.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/);
      const link = el("a");
      link.href = URL.createObjectURL(blob);
      link.download = matched ? matched[1] : "conversation.md";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
    } catch (err) {
      $("status").textContent = "导出失败：" + err.message;
    }
  }

  /* ── 问答：先验证，再分片 ───────────────────────────── */

  /**
   * 从流式缓冲里一块块切出 SSE 帧。返回没切完的尾巴——
   * 网络分片可能从半截帧断开，那半截必须留到下一轮跟新字节拼起来，不能直接丢。
   * @param {string} buf 已解出的文本缓冲。
   * @param {Function} onFrame 收到完整帧时的回调，签名为 (event, payload) => void；
   *   只处理带 data 的帧，注释行和心跳直接跳过。
   * @returns {string} 剩下没成帧的尾巴，交回调用方续到下一轮。
   */
  function parseSSEBuffer(buf, onFrame) {
    let rest = buf;
    while (true) {
      const index = rest.indexOf("\n\n");
      if (index < 0) return rest;
      const block = rest.slice(0, index);
      rest = rest.slice(index + 2);
      let event = "message";
      const dataLines = [];
      block.split("\n").forEach((line) => {
        if (line.startsWith("event:")) event = line.slice(6).trim() || "message";
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      });
      if (!dataLines.length) continue;
      onFrame(event, JSON.parse(dataLines.join("\n")));
    }
  }

  /**
   * 提问并消费流式回答：先把问题落进转写区，再摆一个空回答气泡（先显示"正在过门禁"），
   * 边收边往气泡里补字；收到 done 帧后整块重画答案下半部分（标签、引用、推理步骤）。
   * 用 fetch + ReadableStream 手撸，而不图省事上 EventSource：EventSource 只发 GET，
   * 塞不了请求体——问题正文、工牌、会话号都得往后端送，而且它还不能自定义失败处理。
   * @returns {Promise<void>} 无返回值；失败信息以一条拒答气泡的形式留在转写区。
   */
  async function askQuestion() {
    if (state.asking) return;
    const input = $("q");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    state.asking = true;
    $("ask-btn").disabled = true;
    appendTurn("user", question, null);
    const live = appendTurn("assistant", "", { status: "regen" });
    let answer = "";
    let done = {};
    try {
      const resp = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, user_id: state.userId, conversation_id: state.conversationId || null }),
      });
      if (!resp.ok) throw new Error("问答接口失败");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done: finished, value } = await reader.read();
        if (finished) break;
        buf += decoder.decode(value, { stream: true });
        buf = parseSSEBuffer(buf, (event, payload) => {
          if (event === "message" && payload.delta) {
            answer += payload.delta;
            renderAnswerInto(live.body, answer);
            scrollTranscript();
          }
          if (event === "done") done = payload;
          if (event === "error") throw new Error(payload.message || "问答失败");
        });
      }
      renderAnswerInto(live.body, answer, done);
      if (done && isControlled(done)) live.body.parentElement.classList.add("is-controlled");
      live.extras.textContent = "";
      renderAnswerExtras(live.extras, done);
      state.lastDone = done;
      state.conversationId = done.conversation_id || state.conversationId;
      remember();
      await loadConversations();
      if (state.conversationId) {
        const detail = await api("/api/conversations/" + encodeURIComponent(state.conversationId) + "?" + qs({ user_id: state.userId }));
        state.messages = (detail.messages || []).map((msg) => ({ ...msg, ...(msg.payload || {}) }));
      }
      // 新一跑有明细就顺手刷新轨迹页；没展开过就不打扰
      if (state.tabMemo.trace && done.run_id) await openTrace(done.run_id);
    } catch (err) {
      live.body.textContent = "请求失败：" + err.message;
      renderAnswerExtras(live.extras, { status: "refuse", response_label: "请求失败" });
    } finally {
      state.asking = false;
      $("ask-btn").disabled = false;
      $("q").focus();
    }
  }

  /* ── 启动 ───────────────────────────────────────────── */

  /**
   * 探一下后端还活着没有，顺便把状态写进底栏。探不通就记成 down，
   * 但不挡启动——页面骨架得先立起来，用户至少能看到是服务连不上，而不是白屏。
   * @returns {Promise<void>} 无返回值。
   */
  async function pingService() {
    try {
      const health = await api("/health");
      state.service = health && health.status === "ok" ? "ok" : "degraded";
    } catch (_err) {
      state.service = "down";
    }
    if (state.service !== "ok") {
      $("status").textContent = state.service === "down" ? "服务连不上。" : "服务状态异常。";
    }
  }

  /**
   * 取课堂用的示例问题与空态文案——空态引导里那张对照表的数据源。
   * @returns {Promise<void>} 无返回值。
   */
  async function loadClassroom() {
    const payload = await api("/classroom/prompts?" + qs({ user_id: state.userId }));
    state.prompts = payload.prompts || [];
    state.empty = payload.empty || null;
  }

  /**
   * 取这张工牌看得见的文档清单，底部状态栏顺带报一句"可见几篇 / 裁掉几篇"。
   * @returns {Promise<void>} 无返回值。
   */
  async function loadCatalog() {
    const payload = await api("/api/catalog?" + qs({ user_id: state.userId }));
    state.catalog = payload.documents || [];
    state.catalogHidden = payload.hidden_count || 0;
    // 可见/裁掉的数字由问答区顶上那条权限对照条展示（选中的那张牌上就写着），
    // 这里不再重复一遍——同一页面上同一个数字出现两次，读者会开始怀疑哪个是对的。
    if (state.tab === "catalog") setTab("catalog", false);
  }

  /**
   * 换工牌：换了身份就等于换了个人，上一张牌的会话、出处页、轨迹页全部作废，
   * 全清掉再按新身份重新拉一遍数据。
   * @param {string} userId 要切过去的工牌 id；跟当前一样就直接返回。
   * @returns {Promise<void>} 无返回值。
   */
  async function switchBadge(userId) {
    if (userId === state.userId) return;
    state.userId = userId;
    state.conversationId = "";
    state.messages = [];
    state.tabMemo = { chunk: null, trace: null };
    remember();
    renderRack();
    setTab("catalog", false);
    // 通知控制台视图（文档区 / 评测区按角色开放，换工牌后必须跟着刷新）
    document.dispatchEvent(new CustomEvent("forge:badge-changed", { detail: { userId } }));
    await Promise.all([loadClassroom(), loadCatalog(), loadConversations()]);
    if (state.conversationId) await openConversation(state.conversationId);
    else renderTranscript();
  }

  /**
   * 把页面上的按钮和快捷键接上。集中在一处，方便一眼看清这个视图有哪些入口。
   * @returns {void}
   */
  function bindInteractions() {
    $("new-conv").addEventListener("click", () => createConversation());
    $("export-conv").addEventListener("click", () => exportConversation());
    Object.entries(TAB_IDS).forEach(([name, id]) => {
      $(id).addEventListener("click", () => setTab(name));
    });
    $("ask-form").addEventListener("submit", (event) => {
      event.preventDefault();
      askQuestion();
    });
    $("q").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        askQuestion();
      }
    });
  }

  /**
   * 启动：读回指针 → 探服务 → 拿工牌 → 画界面 → 装交互 → 拉数据。
   * 顺序不能乱：工牌必须先定下来，后面所有取数都带着它去问权限。
   * @returns {Promise<void>} 无返回值；启动失败由调用处（DOMContentLoaded）兜住并写进转写区。
   */
  async function boot() {
    recall();
    await pingService();
    const who = await api("/whoami");
    state.badges = who.badges || (who.users || []).map((user) => ({ ...user, visible_docs: [], hidden_docs: [] }));
    if (!state.badges.some((badge) => badge.user_id === state.userId)) state.userId = "it_staff";
    state.badgeIndex = Math.max(0, state.badges.findIndex((badge) => badge.user_id === state.userId));
    renderRack();
    // 工牌到这一步才算定下来：localStorage 里记的那张可能被 /whoami 驳回、回落成默认。
    // 控制台视图（文档区 / 评测区）是独立的一块，默认按 it_staff 起步——它必须知道
    // 最终是哪张牌，否则「刷新页面后管理员被当成访客」，两个管理区都进不去。
    document.dispatchEvent(new CustomEvent("forge:badge-changed", { detail: { userId: state.userId } }));
    bindInteractions();
    await Promise.all([loadClassroom(), loadCatalog(), loadConversations()]);
    if (state.conversationId) await openConversation(state.conversationId);
    else renderTranscript();
  }

  window.ForgeWorkbench = { setTab, state };

  /**
   * 启动入口：等 DOM 就绪再跑（这时所有 id 都才在页面上）。
   * boot 中途失败会把原因写进转写区——白屏比一句错误信息难排查得多。
   * @returns {void}
   */
  document.addEventListener("DOMContentLoaded", () => {
    boot().catch((err) => {
      $("transcript").textContent = "工作台启动失败：" + err.message;
    });
  });
})();
