// 旅行管家工作台：左侧导航分页（对话 / 行程 / 探索 / 看板 / 订单 / 运维），
// 登录（图形码 + 邮箱码）、生成式卡片、会话历史、订单、审计都在这里接住。
// 看板按机场出港牌排：等宽数据列 + 信号灯 + 大字计数 + 类型筛选。

// 把任意文本变成「放哪儿都安全」的 HTML 片段。
// 注意 textContent → innerHTML 这条常用写法只转义 < > &，**不动引号**：
// 于是 `esc(x)` 的结果一旦被放进属性里（data-x="…"），一个引号就能提前闭合属性、
// 再塞一个 onmouseover 之类的事件处理器进来。这里补上两种引号，
// 让它在文本位置和属性位置都成立——代价是文本里的引号变成实体，显示出来仍是引号。
function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function shortId(id) {
  return id ? id.slice(0, 8) : "—";
}

function pad2(n) {
  return n < 10 ? "0" + n : String(n);
}

// 极简 Markdown：只覆盖模型实际会用的几种（代码块 / 标题 / 列表 / 粗体 / 行内码）
function md(src) {
  let s = String(src == null ? "" : src).replace(/\r\n/g, "\n");
  const fences = [];
  s = s.replace(/```[\w-]*\n?([\s\S]*?)```/g, (_, code) => {
    fences.push("<pre><code>" + esc(code.replace(/\n$/, "")) + "</code></pre>");
    return "\u0000F" + (fences.length - 1) + "\u0000";
  });
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  s = s.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  s = s.replace(/^[ \t]*[-*] (.+)$/gm, "<li>$1</li>");
  s = s.replace(/(?:<li>.*<\/li>\n?)+/g, (block) => "<ul>" + block.replace(/\n/g, "") + "</ul>");
  s = s.split(/\n{2,}/).map((block) => {
    const t = block.trim();
    if (!t) return "";
    if (/^<(h\d|ul|ol|pre|blockquote)/.test(t)) return t;
    return "<p>" + t.replace(/\n/g, "<br>") + "</p>";
  }).join("");
  s = s.replace(/\u0000F(\d+)\u0000/g, (_, i) => fences[Number(i)] || "");
  return s;
}

// 图里的节点 -> 流程条上点亮哪一格
const GATE_MAP = {
  fetch_user_info: "fetch_user_info",
  primary_assistant: "primary_assistant",
  primary_assistant_tools: "primary_assistant",
  enter_update_flight: "update_flight",
  update_flight: "update_flight",
  update_flight_safe_tools: "update_flight",
  update_flight_approval: "approval",
  update_flight_sensitive_tools: "update_flight",
  enter_book_hotel: "book_hotel",
  book_hotel: "book_hotel",
  book_hotel_safe_tools: "book_hotel",
  book_hotel_approval: "approval",
  book_hotel_sensitive_tools: "book_hotel",
  enter_book_excursion: "book_excursion",
  book_excursion: "book_excursion",
  book_excursion_safe_tools: "book_excursion",
  book_excursion_approval: "approval",
  book_excursion_sensitive_tools: "book_excursion",
  book_car_rental: "book_car_rental",
  enter_book_car_rental: "book_car_rental",
  book_car_rental_safe_tools: "book_car_rental",
  book_car_rental_approval: "approval",
  book_car_rental_sensitive_tools: "book_car_rental",
  multi_quote: "multi_quote",
  entry: "multi_quote",
  quote_worker: "multi_quote",
  aggregate: "multi_quote",
  leave_skill: "leave_skill",
};

const GRAPH_STRIP = [
  { id: "fetch_user_info", title: "档案" },
  { id: "primary_assistant", title: "主助理" },
  { id: "multi_quote", title: "比价" },
  {
    id: "skills",
    children: [
      { id: "update_flight", title: "航班" },
      { id: "book_hotel", title: "酒店" },
      { id: "book_car_rental", title: "租车" },
      { id: "book_excursion", title: "门票" },
    ],
  },
  { id: "approval", title: "审批" },
  { id: "leave_skill", title: "交还" },
];

// 城市名 -> 机场三字码。模型可能给中文也可能给英文，两边都收。
const CITY_HINT = {
  Chengdu: "CTU", 成都: "CTU", 双流: "CTU", 天府: "CTU",
  Beijing: "PEK", 北京: "PEK", 首都: "PEK", 大兴: "PKX",
  Shanghai: "SHA", 上海: "SHA", 虹桥: "SHA", 浦东: "PVG",
  Sanya: "SYX", 三亚: "SYX",
  Xian: "XIY", 西安: "XIY",
  Guangzhou: "CAN", 广州: "CAN",
  Hangzhou: "HGH", 杭州: "HGH",
  Kunming: "KMG", 昆明: "KMG",
  Xiamen: "XMN", 厦门: "XMN",
  Chongqing: "CKG", 重庆: "CKG",
  Lijiang: "LJG", 丽江: "LJG",
  Qingdao: "TAO", 青岛: "TAO",
  Harbin: "HRB", 哈尔滨: "HRB",
  Lhasa: "LXA", 拉萨: "LXA",
  Wuhan: "WUH", 武汉: "WUH",
  Shenzhen: "SZX", 深圳: "SZX",
};

// 库里存英文城市名（LIKE 匹配用），界面显示中文
const CITY_CN = {
  Beijing: "北京", Chengdu: "成都", Shanghai: "上海", Sanya: "三亚",
  Xian: "西安", Guangzhou: "广州", Hangzhou: "杭州", Kunming: "昆明",
  Xiamen: "厦门", Chongqing: "重庆", Lijiang: "丽江", Qingdao: "青岛",
  Harbin: "哈尔滨", Lhasa: "拉萨", Wuhan: "武汉", Shenzhen: "深圳",
};

const TIER_CN = {
  Luxury: "豪华", Upscale: "高档", Midscale: "舒适",
  Economy: "经济", Midsize: "中型", SUV: "SUV",
};

// 库里存的是英文（城市、档位），卡片上要显示中文
function cn(value) {
  const s = String(value == null ? "" : value);
  return CITY_CN[s] || TIER_CN[s] || s;
}

const KIND_CN = { car: "租车", hotel: "酒店", spot: "门票", flight: "航班", compare: "比价" };
const KIND_GLYPH = { flight: "✈", hotel: "▤", car: "◆", spot: "◉" };

let live = null;
let thinkingLog = [];
// 当前会话 id：每个请求都带上它（X-Thread-Id），服务端就不用把「现在在哪条会话上」
// 记进程全局——同一账号开两个标签页也能各聊各的。
let threadId = "";

function apiHeaders(extra) {
  const head = Object.assign({ "X-Thread-Id": threadId || "" }, extra || {});
  return head;
}

function thinkingFromTurns(turns) {
  const last = (turns || []).slice(-1)[0];
  return last && last.thinking ? last.thinking.slice() : [];
}

function mergeThinking(server) {
  const fromServer = thinkingFromTurns(server);
  if (fromServer.length >= thinkingLog.length) return fromServer;
  return thinkingLog;
}

// ---------------------------------------------------------------- 分页导航

const PAGE_META = {
  chat: ["对话", "和助手说话，写操作在这里签字"],
  trip: ["行程", "地图、航段与行程概览"],
  explore: ["探索", "挑个城市，直接翻景点 / 酒店 / 租车"],
  board: ["看板", "全库库存实时航显"],
  orders: ["订单", "已订 / 已取消，可在这里退单"],
  ops: ["运维", "审计流水、状态栈与跨会话档案"],
};
const PAGES = Object.keys(PAGE_META);

function currentPage() {
  // 路由用 "#/board" 这种带斜杠的英文 key（chat / trip / explore / board / orders / ops）：
  // 页面里有 id="board" 这类元素，直接写 #board 浏览器会当成锚点跳过去，把顶栏顶出视口
  const hash = (location.hash || "").replace(/^#\/?/, "");
  return PAGES.indexOf(hash) >= 0 ? hash : "chat";
}

function showPage(name) {
  if (PAGES.indexOf(name) < 0) name = "chat";
  PAGES.forEach((key) => {
    const page = document.getElementById("page-" + key);
    const nav = document.getElementById("nav-" + key);
    const on = key === name;
    if (page) page.dataset.active = on ? "true" : "false";
    if (nav) {
      nav.setAttribute("aria-current", on ? "page" : "false");
      if (on) {
        const dot = document.getElementById("nav-dot-" + key);
        if (dot) dot.hidden = true;
      }
    }
  });
  const title = document.getElementById("page-title");
  const sub = document.getElementById("page-sub");
  if (title) title.textContent = PAGE_META[name][0];
  if (sub) sub.textContent = PAGE_META[name][1];
  if (name === "board") paintClock();
  const want = "#/" + name;
  if (location.hash !== want) {
    // 自己点进来算一次跳转（能按返回）；首次落地直接换地址，不塞历史
    if (PAGES.indexOf((location.hash || "").replace(/^#\/?/, "")) >= 0) location.hash = want;
    else history.replaceState(null, "", want);
  }
}

// 导航右侧的小格子：放“几单 / 几段”这类计数；小圆点表示有新东西没看
function navTag(key, text) {
  const el = document.getElementById("nav-tag-" + key);
  if (el) el.textContent = text == null ? "" : String(text);
}

function navDot(key, on) {
  const el = document.getElementById("nav-dot-" + key);
  if (!el) return;
  if (on && currentPage() === key) {
    el.hidden = true;
    return;
  }
  el.hidden = !on;
}

function paintClock() {
  const d = new Date();
  const clock = document.getElementById("board-clock");
  if (clock) clock.textContent = pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
  const date = document.getElementById("board-date");
  if (date) date.textContent = String(d.getFullYear());
}

function startClock() {
  paintClock();
  setInterval(paintClock, 1000);
}

// ---------------------------------------------------------------- 对话

// 工具过程：默认收起，抬头只放「几步 + 状态徽章」。
function thinkingHtml(items, streaming) {
  if (!items || !items.length) return "";
  const calls = items.filter((x) => x.type === "call").length;
  const results = items.filter((x) => x.type === "result").length;
  let state = "running";
  let label = "执行中";
  if (!streaming) {
    state = results >= calls && calls > 0 ? "done" : "running";
    label = state === "done" ? "已完成" : "未回执";
  }
  const rows = items
    .map((step) => {
      if (step.type === "call") {
        const args = step.args && Object.keys(step.args).length
          ? "<pre>" + esc(JSON.stringify(step.args, null, 2)) + "</pre>"
          : "";
        return '<div class="thinking-row"><b>调用 ' + esc(step.name) + "</b>" + args + "</div>";
      }
      if (step.type === "result") {
        return (
          '<div class="thinking-row"><b>回执 ' +
          esc(step.name || "tool") +
          "</b><pre>" +
          esc(step.content || "") +
          "</pre></div>"
        );
      }
      return '<div class="thinking-row"><pre>' + esc(step.content || "") + "</pre></div>";
    })
    .join("");
  return (
    '<details class="thinking"' +
    (streaming ? " open" : "") +
    '><summary><span class="tname">工具过程</span>' +
    '<span class="steps">' + calls + " 次调用</span>" +
    '<span class="badge ' + state + '">' + label + "</span></summary>" +
    '<div class="thinking-body">' + rows + "</div></details>"
  );
}

function answerHtml(text, streaming) {
  if (streaming) {
    return (
      '<div class="bubble answer" id="live-answer">' +
      (text ? esc(text) : "正在回答…") +
      "</div>"
    );
  }
  if (!text) return "";
  return '<div class="bubble answer md">' + md(text) + "</div>";
}

function turnHtml(turn, streaming) {
  const user = turn.user ? '<div class="bubble user">' + esc(turn.user) + "</div>" : "";
  return (
    '<div class="turn">' +
    user +
    thinkingHtml(turn.thinking, streaming) +
    answerHtml(turn.answer, streaming) +
    "</div>"
  );
}

// 起手卡：四张可点的短句，比一段说明文字更省事
const STARTERS = [
  { k: "景点", q: "成都有哪些必去的景点？先给我看看都有什么" },
  { k: "酒店", q: "帮我看看三亚 10 月 1 日到 3 日有哪些酒店，直接列出价格" },
  { k: "租车", q: "帮我在成都订一辆SUV，10月1日到10月3日" },
  { k: "四类比价", q: "帮我同时看看机票、酒店、租车和景点门票的行情" },
];

function emptyHint() {
  return (
    '<div class="empty-hint">' +
    '<div class="hint-note">挑一句直接问，或者自己在下面打字</div>' +
    '<div class="starters">' +
    STARTERS.map(
      (item) =>
        '<button class="starter" data-prompt="' + esc(item.q) + '">' +
        '<span class="k">' + esc(item.k) + "</span>" +
        '<span class="q">' + esc(item.q) + "</span></button>"
    ).join("") +
    "</div></div>"
  );
}

function renderChat(data) {
  const chat = document.getElementById("chat");
  const turns = ((data && data.turns) || []).map((t, idx, arr) => {
    if (idx !== arr.length - 1) return t;
    return Object.assign({}, t, { thinking: mergeThinking(arr) });
  });
  if (!turns.length && !live) {
    chat.innerHTML = emptyHint();
    return;
  }
  // 快照只发最近几十轮；被截断时照实说一句，别让人以为历史没了
  const cut = data && data.history_truncated
    ? '<div class="hint-note">只显示最近的一段，完整历史留在对话存档里</div>'
    : "";
  chat.innerHTML = cut + turns.map((t) => turnHtml(t, false)).join("");
  chat.scrollTop = chat.scrollHeight;
}

function paintLive() {
  const chat = document.getElementById("chat");
  if (!live) return;
  const html =
    '<div class="turn" id="live-turn">' +
    (live.user ? '<div class="bubble user">' + esc(live.user) + "</div>" : "") +
    thinkingHtml(live.thinking, true) +
    answerHtml(live.answer, true) +
    "</div>";
  const liveEl = document.getElementById("live-turn");
  if (liveEl) liveEl.outerHTML = html;
  else chat.insertAdjacentHTML("beforeend", html);
  chat.scrollTop = chat.scrollHeight;
}

// ---------------------------------------------------------------- 行程页

function pendingCityCodes(pending) {
  const codes = new Set();
  const payload = pending && pending.payload;
  const calls = (payload && payload.tool_calls) || [];
  const blob = JSON.stringify(payload || {}).toLowerCase();
  calls.forEach((c) => {
    const args = c.args || {};
    const loc = args.location || args.city || "";
    if (CITY_HINT[loc]) codes.add(CITY_HINT[loc]);
  });
  Object.entries(CITY_HINT).forEach(([city, code]) => {
    if (blob.includes(String(city).toLowerCase()) || blob.includes(code.toLowerCase())) {
      codes.add(code);
    }
  });
  if (!codes.size && /car|hotel|excursion|租车|酒店|景点|门票/.test(blob)) {
    codes.add("CTU");
  }
  return codes;
}

function renderMap(data) {
  const host = document.getElementById("map");
  if (!host) return;
  const itin = data.itinerary || {};
  const airports = itin.airports || [];
  const legs = itin.legs || [];
  const caption = document.getElementById("map-caption");
  const pendingCodes = pendingCityCodes(data.pending);

  const byCode = {};
  airports.forEach((a) => {
    if (a && a.code) byCode[a.code] = a;
  });

  host.innerHTML = data.route
    ? data.route +
      '<div class="route-credit">底图：Wikimedia Commons《China edcp location map》· CC BY-SA 3.0</div>' +
      '<div class="route-legend">小点 省会城市 · 大点 可订城市 · 弧线 我的航段</div>'
    : '<div class="blank">这张行程图暂时画不出来。</div>';

  const legsHost = document.getElementById("legs");
  if (legsHost) {
    if (!legs.length) {
      legsHost.innerHTML = '<div class="blank">还没有行程航段。登录后会自动从你的机票里读出去程和回程。</div>';
    } else {
      legsHost.innerHTML = legs
        .map((leg, idx) => {
          const hold = pendingCodes.has(leg.from) || pendingCodes.has(leg.to);
          const from = byCode[leg.from] || {};
          const to = byCode[leg.to] || {};
          const tag = idx === 0 ? "去程" : idx === 1 ? "回程" : "航段 " + (idx + 1);
          const ks = [
            ["航班", leg.flight_no || "—"],
            ["起飞", leg.depart || "—"],
            ["到达", leg.arrive || "—"],
            ["座位", leg.seat || "—"],
            ["舱位", leg.fare || "—"],
          ];
          return (
            '<div class="leg">' +
            '<div class="leg-mark"><i></i><span></span></div>' +
            "<div>" +
            '<div class="leg-top">' +
            '<span class="pair">' + esc(leg.from) + "<em>→</em>" + esc(leg.to) + "</span>" +
            '<span class="city">' + esc([from.city, to.city].filter(Boolean).join(" · ")) + "</span>" +
            '<span class="lamp' + (hold ? " hold" : "") + '"><i></i>' + (hold ? "待签" : tag) + "</span>" +
            "</div>" +
            '<div class="leg-meta">' +
            ks.map(([k, v]) => '<span class="kv"><i>' + esc(k) + "</i><b>" + esc(v) + "</b></span>").join("") +
            "</div></div></div>"
          );
        })
        .join("");
    }
  }

  if (caption) {
    caption.textContent = legs.length
      ? legs.map((l) => l.flight_no + " " + l.from + "→" + l.to).join("  ·  ")
      : "等待行程";
  }

  // 行程概览 + 有库存的城市
  const b = data.board || {};
  const cars = b.cars || {};
  const hotels = b.hotels || {};
  const trips = b.trips || {};
  const flights = b.flights || {};
  const ids = pendingIdsByLane(data.pending);
  const kpis = document.getElementById("kpis");
  if (kpis) {
    const cell = (value, label, warn) =>
      '<div class="kpi' + (warn ? " warn" : "") + '"><b>' + esc(String(value)) + "</b><span>" + esc(label) + "</span></div>";
    kpis.innerHTML =
      cell(flights.legs || 0, "我的航段", false) +
      cell((cars.booked || 0) + " / " + (cars.total || 0), "租车已订", ids.cars.size > 0) +
      cell((hotels.booked || 0) + " / " + (hotels.total || 0), "酒店已订", ids.hotels.size > 0) +
      cell((trips.booked || 0) + " / " + (trips.total || 0), "门票已订", ids.trips.size > 0);
  }
  const chipHost = document.getElementById("city-chips");
  if (chipHost) {
    const used = new Set();
    legs.forEach((leg) => {
      if (leg.from) used.add(leg.from);
      if (leg.to) used.add(leg.to);
    });
    const rest = airports.filter((a) => a && a.code && !used.has(a.code));
    const shown = rest.slice(0, 9);
    const more = rest.length > shown.length
      ? '<span class="city-more">还有 ' + (rest.length - shown.length) + " 个城市</span>"
      : "";
    chipHost.innerHTML = shown.length
      ? '<span class="n">有库存的城市</span>' +
        shown
          .map((a) =>
            '<span class="city-chip' + (pendingCodes.has(a.code) ? " hold" : "") + '">' +
            esc(a.code + " " + (a.city || "")) + "</span>")
          .join("") +
        more
      : '<span class="n">暂无库存城市</span>';
  }
}

// ---------------------------------------------------------------- 生成式卡片

function cardHtml(item) {
  const cls = "card" + (item.booked ? " mark-ok" : item.hold ? " mark-hold" : "");
  const meta = [item.code, item.tag, item.when]
    .filter(Boolean)
    .map((x) => "<span>" + esc(cn(x)) + "</span>")
    .join("");
  const tags = (item.keywords || [])
    .map((k) => '<span class="tag">' + esc(k) + "</span>")
    .join("");
  const note = item.note && item.keywords ? '<div class="card-note">' + esc(item.note) + "</div>" : "";
  const bar = typeof item.bar === "number"
    ? '<div class="bar"><i style="width:' + Math.max(0, Math.min(100, item.bar)) + '%"></i></div>'
    : "";
  return (
    '<div class="' + cls + '">' +
    '<div class="lampbar"></div>' +
    '<div class="card-body">' +
    '<div class="card-top">' +
    '<span class="card-title">' + esc(item.title || item.code || "—") + "</span>" +
    '<span class="card-price">' + esc(item.price || item.note || "") + "</span>" +
    "</div>" +
    (meta ? '<div class="card-meta">' + meta + "</div>" : "") +
    (tags ? '<div class="card-tags">' + tags + "</div>" : "") +
    note +
    bar +
    "</div></div>"
  );
}

function deckHtml(groups) {
  return (groups || [])
    .map((g) => {
      const glyph = g.kind_art || g.art || "";
      const head =
        '<div class="deck-group">' +
        (g.photo
          ? '<span class="g"><img src="' + esc(g.photo) + '" alt=""></span>'
          : glyph
            ? '<span class="g">' + glyph + "</span>"
            : "") +
        '<span class="t">' + esc(g.label) + (g.city ? " · " + esc(g.city) : "") + "</span>" +
        '<span class="n">' + (g.shown != null ? g.shown + " / " + g.total : "") + "</span>" +
        "</div>";
      const cards = (g.items || [])
        .map((it) => cardHtml(Object.assign({ kind: g.kind }, it)))
        .join("");
      return head + cards;
    })
    .join("");
}

function renderCards(groups) {
  const host = document.getElementById("cards");
  if (!host) return;
  const list = groups || [];
  const cap = document.getElementById("cards-caption");
  if (!list.length) {
    if (cap) cap.textContent = "由工具回执生成";
    host.innerHTML =
      '<div class="blank">这里会长出<b>卡片</b>。' +
      "问一句「成都有哪些酒店」，查到几家就长几张；问四类行情，会多一张比价条形。" +
      "查什么长什么，不用你翻文字。</div>";
    return;
  }
  const items = list.reduce((n, g) => n + g.items.length, 0);
  if (cap) cap.textContent = list.length + " 组 · " + items + " 项";
  markCardsDot(list);
  host.innerHTML = deckHtml(list);
}

let cardsStamp = "";

function markCardsDot(list) {
  const stamp = JSON.stringify(
    (list || []).map((g) => [g.kind, g.city, g.shown, g.total, (g.items || []).length])
  );
  if (stamp === cardsStamp) return;
  cardsStamp = stamp;
  const nav = document.getElementById("nav-orders");
  if (nav && currentPage() !== "orders") navDot("orders", true);
}

// ---------------------------------------------------------------- 探索页

let exploreCity = "";
let cityData = null;

function renderExploreCities(cities) {
  const host = document.getElementById("explore-cities");
  if (!host) return;
  const list = cities || [];
  const cap = document.getElementById("explore-caption");
  if (cap) cap.textContent = list.length ? list.length + " 个城市" : "暂无库存";
  if (!list.length) {
    host.innerHTML = '<div class="blank">业务库里还没有库存。</div>';
    return;
  }
  // 城市卡：有实景照就用照片（真实目的地照片比任何插画都直观），
  // 没抓到照片的城市回退到几何标记，两者共用同一套卡片尺寸。
  host.innerHTML = list
    .map((c) => {
      const on = c.city === exploreCity;
      const face = c.photo
        ? '<img class="city-photo" src="' + esc(c.photo) + '" alt="' + esc((c.cn || c.city) + " 实景") + '" loading="lazy">'
        : '<span class="city-glyph">' + c.art + "</span>";
      return (
        '<button class="city-tile" data-city="' + esc(c.city) + '"' +
        (on ? ' aria-current="true"' : "") + ">" +
        face +
        '<span class="city-text"><b>' + esc(c.cn || c.city) + "</b>" +
        "<span>" + c.spots + " 景 · " + c.hotels + " 宿 · " + c.cars + " 车</span></span>" +
        "</button>"
      );
    })
    .join("");
  host.querySelectorAll(".city-tile").forEach((b) => {
    b.addEventListener("click", () => loadCity(b.dataset.city));
  });
}

function renderExplore(data) {
  const host = document.getElementById("explore");
  if (!host) return;
  if (!data || !data.city) {
    host.innerHTML =
      '<div class="blank">左边挑一个城市，这里会摊开它的<b>景点 / 酒店 / 租车</b>。' +
      "不用先跟模型说话。</div>";
    return;
  }
  const hero = data.photo
    ? '<img src="' + esc(data.photo) + '" alt="' + esc((data.cn || data.city) + " 实景") + '">'
    : '<span class="glyph">' + (data.art || "") + "</span>";
  const stat = [
    ["景点", (data.spots || []).length],
    ["酒店", (data.hotels || []).length],
    ["租车", (data.cars || []).length],
  ]
    .map(([k, v]) => "<span>" + esc(k) + " <b>" + v + "</b></span>")
    .join("");
  const groups = [
    { kind: "spot", label: "景点", items: data.spots || [] },
    { kind: "hotel", label: "酒店", items: data.hotels || [] },
    { kind: "car", label: "租车", items: data.cars || [] },
  ].filter((g) => g.items.length);
  host.innerHTML =
    '<div class="city-hero">' + hero +
    "<div><b>" + esc(data.cn || data.city) + "</b>" +
    "<span>" + esc(data.city) + "</span>" +
    '<div class="stat">' + stat + "</div></div></div>" +
    deckHtml(groups);
}

function loadCity(city) {
  exploreCity = city;
  const cap = document.getElementById("explore-caption");
  if (cap) cap.textContent = "正在翻开…";
  fetch("/api/explore?city=" + encodeURIComponent(city))
    .then((r) => r.json())
    .then((data) => {
      cityData = data;
      renderExploreCities((window.__snap && window.__snap.explore) || []);
      renderExplore(cityData);
    })
    .catch(() => {
      if (cap) cap.textContent = "翻不开这个城市";
    });
}

// ---------------------------------------------------------------- 看板（出港牌）

// 一屏里的筛选状态：按类型 + 只看可订
let boardKind = "all";
let boardOnlyOpen = false;

// 上一次看到的状态，状态真变了才让那一行闪一下
let boardSeen = {};

function pendingIdsByLane(pending) {
  const out = { cars: new Set(), hotels: new Set(), trips: new Set() };
  const calls = (pending && pending.payload && pending.payload.tool_calls) || [];
  calls.forEach((c) => {
    const name = String(c.name || "").toLowerCase();
    const args = c.args || {};
    if (name.includes("car") || name.includes("rental")) {
      if (args.rental_id != null) out.cars.add(String(args.rental_id));
    } else if (name.includes("hotel")) {
      if (args.hotel_id != null) out.hotels.add(String(args.hotel_id));
    } else if (name.includes("excursion") || name.includes("trip")) {
      if (args.trip_id != null) out.trips.add(String(args.trip_id));
    }
  });
  return out;
}

function boardRows(data) {
  const b = data.board || {};
  const ids = pendingIdsByLane(data.pending);
  const mine = new Set();
  ((data.itinerary || {}).legs || []).forEach((leg) => {
    [leg.from, leg.to].forEach((code) => {
      if (code) mine.add(code);
    });
  });
  const rows = [];
  [["cars", "car", "租车", ids.cars], ["hotels", "hotel", "酒店", ids.hotels], ["trips", "spot", "门票", ids.trips]]
    .forEach(([key, kind, label, holdSet]) => {
      ((b[key] || {}).items || []).forEach((it) => {
        const code = CITY_HINT[it.location];
        rows.push({
          kind: kind,
          label: label,
          id: it.id,
          name: it.name,
          city: CITY_CN[it.location] || it.location || "",
          tier: TIER_CN[it.tier] || "",
          price: it.price,
          booked: Boolean(it.booked),
          hold: holdSet.has(String(it.id)),
          mine: mine.has(code),
        });
      });
    });
  // 排法：我行程要去的城市优先，其次按城市、类型、编号
  rows.sort((x, y) =>
    Number(y.mine) - Number(x.mine) ||
    x.city.localeCompare(y.city, "zh") ||
    x.kind.localeCompare(y.kind) ||
    Number(x.id) - Number(y.id)
  );
  return rows;
}

function boardRowHtml(r) {
  const key = r.kind + ":" + r.id;
  const state = r.hold ? "待签" : r.booked ? "已订" : "可订";
  const lamp = r.hold ? "lamp-hold" : r.booked ? "lamp-ok" : "lamp-off";
  const changed = boardSeen[key] !== undefined && boardSeen[key] !== state;
  boardSeen[key] = state;
  return (
    '<div class="board-row' + (r.booked ? " is-booked" : "") + '"' +
    (changed ? ' style="animation: flip .5s ease-out"' : "") + ">" +
    '<span class="lampcell"><i class="' + lamp + '"></i></span>' +
    '<span class="name">' + esc(r.name) + "</span>" +
    '<span class="city">' + esc(r.city) + "</span>" +
    '<span class="kind">' + esc(r.label) + (r.tier ? " · " + esc(r.tier) : "") + "</span>" +
    '<span class="price">' + (r.price ? "¥" + esc(String(r.price)) : "—") + "</span>" +
    '<span class="stat ' + (r.hold ? "hold" : r.booked ? "ok" : "") + '">' + esc(state) + "</span>" +
    "</div>"
  );
}

function renderBoard(data) {
  const host = document.getElementById("board");
  if (!host) return;
  const b = data.board || {};
  const ids = pendingIdsByLane(data.pending);
  const rows = boardRows(data);
  const shown = rows.filter(
    (r) => (boardKind === "all" || r.kind === boardKind) && (!boardOnlyOpen || !r.booked)
  );

  // 抬头大字：库存总数 / 已订 / 可订 / 待签 / 在售航班
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value);
  };
  const total = rows.length;
  const booked = rows.filter((r) => r.booked).length;
  const hold = ids.cars.size + ids.hotels.size + ids.trips.size;
  set("lamp-total", total);
  set("lamp-booked", booked);
  set("lamp-open", total - booked);
  set("lamp-hold", hold);
  set("lamp-flights", (b.flights || {}).total || 0);
  const count = document.getElementById("board-count");
  if (count) count.textContent = "显示 " + shown.length + " / " + total + " 条";

  host.innerHTML = shown.length
    ? shown.map(boardRowHtml).join("")
    : '<div class="board-empty">这个筛选下没有库存。</div>';

  // 侧栏上的计数：看板总件数、行程航段、订单单数在各自渲染里写
  navTag("board", total + "件");
}

function switchBoardKind(which) {
  boardKind = which;
  ["all", "car", "hotel", "spot"].forEach((k) => {
    const btn = document.getElementById("seg-" + k);
    if (btn) btn.setAttribute("aria-pressed", k === which ? "true" : "false");
  });
  if (window.__snap) renderBoard(window.__snap);
}

function toggleOnlyOpen() {
  boardOnlyOpen = !boardOnlyOpen;
  const btn = document.getElementById("seg-open");
  if (btn) btn.setAttribute("aria-pressed", boardOnlyOpen ? "true" : "false");
  if (window.__snap) renderBoard(window.__snap);
}

// ---------------------------------------------------------------- 会话列表

function renderSessions(items) {
  const host = document.getElementById("sessions");
  if (!host) return;
  if (!items || !items.length) {
    host.innerHTML = '<span class="n">还没有对话，发一句话就会自动建一条</span>';
    return;
  }
  host.innerHTML = items
    .map(
      (s) =>
        '<span class="session-chip" data-thread="' + esc(s.thread_id) + '"' +
        (s.active ? ' aria-current="true"' : "") + ">" +
        '<span class="st">' + esc(s.title) + "</span>" +
        '<span class="sn">' + esc(String(s.turns || 0)) + "轮</span>" +
        '<button class="sx" data-act="rename" title="改名" aria-label="改名">✎</button>' +
        (s.active ? "" : '<button class="sx" data-act="delete" title="删除" aria-label="删除">×</button>') +
        "</span>"
    )
    .join("");
  host.querySelectorAll(".session-chip").forEach((chip) => {
    const thread = chip.dataset.thread;
    chip.addEventListener("click", (e) => {
      const act = e.target && e.target.dataset ? e.target.dataset.act : "";
      if (act === "rename") {
        e.stopPropagation();
        startRename(chip, thread);
        return;
      }
      if (act === "delete") {
        e.stopPropagation();
        deleteSession(thread);
        return;
      }
      if (chip.getAttribute("aria-current") !== "true") openSession(thread);
    });
  });
}

function startRename(chip, thread) {
  const label = chip.querySelector(".st");
  const old = label ? label.textContent : "";
  const input = document.createElement("input");
  input.value = old;
  chip.replaceChild(input, label);
  input.focus();
  input.select();
  let done = false;
  const restore = () => renderSessions((window.__snap && window.__snap.sessions) || []);
  const commit = () => {
    if (done) return;
    done = true;
    const title = input.value.trim();
    if (!title || title === old) {
      restore();
      return;
    }
    fetch("/api/sessions/" + encodeURIComponent(thread), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.detail || "改名失败");
        render(data);
      })
      .catch((err) => {
        document.getElementById("status").textContent = "改名失败：" + err.message;
        restore();
      });
  };
  input.addEventListener("blur", commit);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") {
      done = true;
      restore();
    }
  });
}

function sessionAction(url, options, okMessage) {
  const opts = Object.assign({}, options || {});
  opts.headers = apiHeaders(opts.headers);
  fetch(url, opts)
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) throw new Error(data.detail || "操作失败");
      live = null;
      thinkingLog = [];
      render(data);
      if (okMessage) document.getElementById("status").textContent = okMessage;
    })
    .catch((err) => {
      document.getElementById("status").textContent = "操作失败：" + err.message;
    });
}

function openSession(thread) {
  sessionAction("/api/sessions/" + encodeURIComponent(thread) + "/open", { method: "POST" }, "已切换到这条对话");
}

function deleteSession(thread) {
  sessionAction("/api/sessions/" + encodeURIComponent(thread), { method: "DELETE" }, "已删除这条对话");
}

function newSession() {
  sessionAction("/api/sessions", { method: "POST" }, "已开启新对话");
}

// ---------------------------------------------------------------- 订单

const KIND_ORDER = ["flight", "hotel", "car", "spot"];

// 日期区间：同一天就不重复写日期（2026-09-21 06:30 → 09:10）
function whenRange(start, end) {
  if (!start && !end) return "";
  if (!end) return String(start);
  const a = String(start);
  const b = String(end);
  if (a.slice(0, 10) === b.slice(0, 10)) return a + " → " + b.slice(11);
  return a + " → " + b;
}

function orderHtml(o) {
  const cancelled = o.status === "cancelled";
  const when = whenRange(o.start_date, o.end_date);
  return (
    '<div class="order' + (cancelled ? " cancelled" : "") + '">' +
    '<div class="order-head"><span class="order-title">' + esc(o.title) + "</span>" +
    '<span class="lamp-tag' + (cancelled ? " off" : "") + '"><i></i>' +
    (cancelled ? "已取消" : "已确认") + "</span></div>" +
    '<div class="order-body">' +
    (o.location ? '<span class="kv"><i>城市</i><b>' + esc(o.location) + "</b></span>" : "") +
    (when ? '<span class="kv"><i>日期</i><b>' + esc(when) + "</b></span>" : "") +
    '<span class="kv"><i>金额</i><b>' + esc(o.amount ? "¥" + o.amount : "—") + "</b></span>" +
    "</div>" +
    (cancelled
      ? ""
      : '<div class="order-actions"><button class="btn ghost small" data-order="' +
        esc(String(o.id)) + '">取消订单</button></div>') +
    "</div>"
  );
}

function renderOrders(payload) {
  const host = document.getElementById("orders");
  if (!host) return;
  const data = payload || {};
  const items = data.items || [];
  const counts = data.counts || {};
  const cap = document.getElementById("orders-caption");
  if (cap) {
    cap.textContent = data.owner_view
      ? "运营视图 · 全部订单"
      : "共 " + (counts.all || 0) + " 单 · 合计 ¥" + (counts.amount || 0);
  }
  navTag("orders", (counts.all || 0) + "单");
  if (!items.length) {
    host.innerHTML =
      '<div class="blank">还没有订单。说一句「帮我在成都订一辆SUV」，' +
      "批准之后这里就会出现一张单据。</div>";
    return;
  }
  const groups = {};
  items.forEach((o) => {
    (groups[o.kind] = groups[o.kind] || []).push(o);
  });
  host.innerHTML = KIND_ORDER.filter((k) => groups[k])
    .map((kind) => {
      const list = groups[kind];
      const confirmed = list.filter((o) => o.status !== "cancelled").length;
      return (
        '<div class="order-group"><h4><span>' + esc(list[0].kind_label) + "</span><span>" +
        confirmed + " / " + list.length + "</span></h4>" +
        list.map(orderHtml).join("") +
        "</div>"
      );
    })
    .join("");
  // 取消按钮认 data-order（按 class 找的话，类名一改就点不动了）
  host.querySelectorAll("button[data-order]").forEach((b) => {
    b.addEventListener("click", () => {
      b.disabled = true;
      b.textContent = "取消中…";
      sessionAction(
        "/api/orders/cancel",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ order_id: Number(b.dataset.order) }),
        },
        "订单已取消，库存已释放"
      );
    });
  });
}

// ---------------------------------------------------------------- 审计

const ACTION_LABEL = {
  login: "登录",
  logout: "退出登录",
  register: "注册",
  approve: "批准执行",
  reject: "驳回",
  book: "下单",
  cancel: "退单",
  update: "改期",
  session_new: "新建对话",
  session_open: "切换对话",
  session_rename: "重命名对话",
  session_delete: "删除对话",
};

function renderAudit(payload) {
  const host = document.getElementById("audit");
  const sumHost = document.getElementById("audit-summary");
  if (!host || !sumHost) return;
  const data = payload || {};
  const items = data.items || [];
  const s = data.summary || {};
  const byAction = s.by_action || {};
  const cap = document.getElementById("audit-caption");
  if (cap) cap.textContent = data.owner_view ? "运营视图 · 全部流水" : "只看得到自己的操作";
  sumHost.innerHTML =
    '<div class="cell"><b>' + (s.total || 0) + "</b><span>流水条数</span></div>" +
    '<div class="cell"><b>' + (byAction.approve || 0) + "</b><span>批准</span></div>" +
    '<div class="cell"><b>' + (byAction.book || 0) + "</b><span>下单</span></div>" +
    '<div class="cell' + (s.failures ? " warn" : "") + '"><b>' + (s.failures || 0) + "</b><span>驳回/失败</span></div>";
  if (!items.length) {
    host.innerHTML = '<div class="blank">还没有流水记录。</div>';
    return;
  }
  host.innerHTML = items
    .map(
      (i) =>
        '<div class="audit-item"><div class="audit-row">' +
        '<span class="audit-who">' + esc(i.actor || "—") + "</span>" +
        '<span class="audit-when">' + esc(i.at) + "</span></div>" +
        '<div class="audit-what"><span class="badge ' + (i.result === "ok" ? "done" : "denied") + '">' +
        esc(i.result) + "</span>" + esc(ACTION_LABEL[i.action] || i.action) +
        (i.target ? " · " + esc(i.target) : "") +
        (i.detail && i.detail.title ? " · " + esc(i.detail.title) : "") +
        "</div></div>"
    )
    .join("");
}

// ---------------------------------------------------------------- 运维：状态栈 / 档案 / 时间线

function renderSide(data) {
  const stack = document.getElementById("stack");
  if (stack) {
    const states = data.dialog_state || [];
    stack.innerHTML = states.length
      ? states.map((name, i) => '<div class="stack-item">' + (i + 1) + ". " + esc(name) + "</div>").join("")
      : '<div class="stack-item">主助理值班（栈空）</div>';
  }

  const prefs = document.getElementById("prefs");
  if (prefs) {
    prefs.innerHTML = (data.prefs || []).length
      ? data.prefs
          .map((p) => '<div class="pref"><b>' + esc(p.key) + "</b> " + esc(p.value) + "</div>")
          .join("")
      : '<div class="pref">（暂无档案）</div>';
  }

  const trace = document.getElementById("trace");
  if (trace) {
    const items = data.trace || [];
    trace.innerHTML = items.length
      ? items
          .slice()
          .reverse()
          .map((t) => {
            const ns = t.namespace && t.namespace.length ? " · 子图" : "";
            return '<div class="trace-item"><b>' + esc(t.label) + esc(ns) + "</b><span>" + esc(t.at) + "</span></div>";
          })
          .join("")
      : '<div class="trace-item">还没有节点走过</div>';
  }
}

// ---------------------------------------------------------------- 智能体流程条

function nodeState(id, data, currentNode) {
  const visited = new Set();
  (data.trace || []).forEach((item) => {
    const gate = GATE_MAP[item.node];
    if (gate) visited.add(gate);
  });
  if (data.pending && id === "approval") return "hold";
  if (currentNode && GATE_MAP[currentNode] === id) return "on";
  if (visited.has(id)) return "done";
  return "idle";
}

function nodeHtml(n, data, currentNode) {
  const state = nodeState(n.id, data, currentNode);
  return '<span class="node ' + state + '" data-node="' + esc(n.id) + '">' + esc(n.title) + "</span>";
}

function renderRadar(data, currentNode) {
  const host = document.getElementById("graph");
  if (!host) return;
  const parts = [];
  GRAPH_STRIP.forEach((item, idx) => {
    if (idx) parts.push('<span class="join" aria-hidden="true"></span>');
    if (item.children) {
      parts.push(
        '<div class="cluster">' +
          item.children.map((n) => nodeHtml(n, data, currentNode)).join("") +
          "</div>"
      );
    } else {
      parts.push(nodeHtml(item, data, currentNode));
    }
  });
  host.innerHTML = parts.join("");
  const cap = document.getElementById("flow-bar");
  if (cap && cap.firstElementChild) {
    cap.firstElementChild.textContent = data.pending ? "审批闸门挂起，等待签字" : "智能体流程";
  }
}

// ---------------------------------------------------------------- 抬头与审批

// 审批卡：字段化，不是把 interrupt 的原始 JSON 丢给用户。
function approvalHtml(pending) {
  const payload = (pending && pending.payload) || {};
  const calls = payload.tool_calls || [];
  const rows = calls
    .map((c) => {
      const fields = [
        ["动作", c.action || c.name],
        ["对象", [c.target, c.city].filter(Boolean).join(" · ")],
        ["日期", c.when || ""],
        ["金额", c.amount || ""],
      ].filter(([, v]) => v);
      return (
        '<div class="approve-item">' +
        fields
          .map(([k, v]) => '<span class="kv"><i>' + esc(k) + "</i><b>" + esc(v) + "</b></span>")
          .join("") +
        "</div>"
      );
    })
    .join("");
  const total = payload.total
    ? '<span class="kv"><i>合计</i><b>' + esc(payload.total) + "</b></span>"
    : "";
  return (
    '<div class="approve-head"><span class="lamp"><i></i>待审批</span>' +
    '<span class="approve-path">' + esc(payload.domain || pending.path || "") + "</span>" +
    (total ? '<span class="approve-total">' + total + "</span>" : "") +
    "</div>" +
    (rows || '<div class="approve-item"><span class="kv"><i>动作</i><b>' +
      esc(calls.map((c) => c.name).join(", ") || "—") + "</b></span></div>")
  );
}

function renderChrome(data) {
  document.getElementById("status").textContent = data.status || "";
  const approval = document.getElementById("approval");
  approval.classList.toggle("on", Boolean(data.pending));
  const detail = document.getElementById("approval-detail");
  const statusEl = document.getElementById("status");
  if (data.pending) {
    detail.innerHTML = approvalHtml(data.pending);
    statusEl.classList.add("hold");
  } else {
    detail.innerHTML = "";
    statusEl.classList.remove("hold");
  }
  document.getElementById("model-chip").textContent = data.model || "—";
  const modeWrap = document.getElementById("mode-wrap");
  const modeChip = document.getElementById("mode-chip");
  if (data.live) {
    modeChip.textContent = "真实模型";
    modeWrap.classList.add("live");
    modeWrap.classList.remove("demo");
  } else {
    modeChip.textContent = "未配 Key";
    modeWrap.classList.add("demo");
    modeWrap.classList.remove("live");
  }
  document.getElementById("thread-chip").textContent = shortId(data.thread_id);
  const pax = document.getElementById("pax-chip");
  if (pax) pax.textContent = data.passenger_id || "—";
  // 有挂起就去看板页点个小点：那边会标「待签」
  navDot("board", Boolean(data.pending));
}

function render(data, currentNode) {
  window.__snap = data;
  const identity = data.identity || {};
  if (identity.authed === false) {
    threadId = "";
    renderAccounts(data.accounts);
    showLogin();
    return;
  }
  if (data.thread_id) threadId = data.thread_id;
  hideLogin();
  if (!live) renderChat(data);
  renderChrome(data);
  renderSide(data);
  renderRadar(data, currentNode);
  renderMap(data);
  renderBoard(data);
  renderSessions(data.sessions);
  renderOrders(data.orders);
  renderAudit(data.audit);
  renderCards(data.cards);
  renderExploreCities(data.explore);
  renderExplore(cityData);
  navTag("trip", ((data.itinerary || {}).legs || []).length + "段");
  navTag("explore", (data.explore || []).length + "城");
}

// ---------------------------------------------------------------- 登录 / 注册

let signedIn = false;
// let codeTimer = null;   // 邮箱验证码下线期间用不到，恢复时一起放回来（见「邮箱验证码」那一段）

function showAlert(message, kind) {
  const box = document.getElementById("login-error");
  if (!box) return;
  box.textContent = message || "";
  box.classList.toggle("on", Boolean(message));
  box.classList.toggle("good", kind === "good");
  box.classList.toggle("bad", kind !== "good");
}

function showLogin(message) {
  const screen = document.getElementById("login");
  if (!screen) return;
  signedIn = false;
  screen.hidden = false;
  setBusy(false);
  showAlert(message || "", "bad");
}

function hideLogin() {
  const screen = document.getElementById("login");
  if (screen) screen.hidden = true;
  signedIn = true;
  showAlert("");
}

function switchTab(which) {
  const isLogin = which !== "register";
  document.getElementById("tab-login").setAttribute("aria-selected", isLogin ? "true" : "false");
  document.getElementById("tab-register").setAttribute("aria-selected", isLogin ? "false" : "true");
  document.getElementById("form-login").hidden = !isLogin;
  document.getElementById("form-register").hidden = isLogin;
  // 演示账号只服务「登录」：注册要自己填邮箱、过图形验证码，摆一排一键进的账号只会误导
  const demos = document.getElementById("demo-block");
  if (demos) demos.hidden = !isLogin;
  showAlert("");
  if (!isLogin) {
    const wrap = document.getElementById("reg-captcha");
    if (wrap && !wrap.dataset.captchaId) loadCaptcha("reg");
  }
}

function renderAccounts(accounts) {
  const host = document.getElementById("login-demos");
  if (host) {
    host.innerHTML = (accounts || [])
      .map(
        (a) =>
          '<button type="button" class="demo-card" data-user="' + esc(a.username) +
          '" data-pass="' + esc(a.username === "ops" ? "ops12345" : a.username + "123") + '">' +
          "<b>" + esc(a.username) + "</b>" +
          "<span>" + esc(a.route) + "</span>" +
          "<em>" + esc(a.username === "ops" ? "ops12345" : a.username + "123") + "</em></button>"
      )
      .join("");
    host.querySelectorAll(".demo-card").forEach((b) => {
      b.addEventListener("click", () => {
        switchTab("login");
        document.getElementById("login-user").value = b.dataset.user || "";
        document.getElementById("login-pass").value = b.dataset.pass || "";
        submitLogin();
      });
    });
  }
  const select = document.getElementById("reg-pax");
  if (select) {
    select.innerHTML = (accounts || [])
      .map(
        (a) =>
          '<option value="' + esc(a.passenger_id) + '">' + esc(a.passenger_id) + " · " + esc(a.route) + "</option>"
      )
      .join("");
  }
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || "请求失败");
    err.status = res.status;
    err.captchaRequired = res.headers.get("X-Captcha-Required") === "1";
    throw err;
  }
  return data;
}

function enterDesk(data) {
  live = null;
  thinkingLog = [];
  boardSeen = {};
  cardsStamp = "";
  hideLogin();
  render(data);
}

// ---- 图形验证码 ----

async function loadCaptcha(prefix) {
  const wrap = document.getElementById(prefix + "-captcha");
  const box = document.getElementById(prefix + "-captcha-img");
  const input = document.getElementById(prefix + "-captcha-input");
  if (box) box.disabled = true;          // 出题期间点不动，也当作「正在换」的反馈
  try {
    const res = await fetch("/api/auth/captcha");
    const data = await res.json();
    if (box) box.innerHTML = data.svg;
    if (wrap) wrap.dataset.captchaId = data.captcha_id;
    if (input) input.value = "";
  } catch (err) {
    if (box) box.innerHTML = '<span class="n">加载失败，点一下重试</span>';
  } finally {
    if (box) box.disabled = false;
  }
}

function captchaPayload(prefix) {
  const wrap = document.getElementById(prefix + "-captcha");
  const input = document.getElementById(prefix + "-captcha-input");
  return {
    captcha_id: (wrap && wrap.dataset.captchaId) || "",
    captcha_text: ((input && input.value) || "").trim(),
  };
}

function showCaptcha(prefix) {
  const wrap = document.getElementById(prefix + "-captcha");
  if (wrap) wrap.classList.add("on");
  return loadCaptcha(prefix);
}

// ---- 邮箱验证码：暂时下线（2026-09-20） ----
// 演示环境没有邮件服务，注册这一道改成只过图形验证码（那个还在，见 submitRegister）。
// 要恢复：放开下面四个函数、DOMContentLoaded 里 send-code / reg-code 两行绑定，
// 以及 web/present/views.py 里注册表单那段注释；后端同步放开 web/api.py 的 /api/auth/email/code。
// let codeTimer = null;

// function noteCode(message, kind) {
//   const note = document.getElementById("code-note");
//   if (!note) return;
//   note.textContent = message || "";
//   note.className = "field-note" + (kind ? " " + kind : "");
// }

// function startCooldown(seconds) {
//   if (codeTimer) clearInterval(codeTimer);
//   let left = seconds;
//   const btn = document.getElementById("send-code");
//   const tick = () => {
//     if (left <= 0) {
//       clearInterval(codeTimer);
//       codeTimer = null;
//       if (btn) {
//         btn.disabled = false;
//         btn.textContent = "发送验证码";
//       }
//       noteCode("验证码 10 分钟内有效。", "");
//       return;
//     }
//     if (btn) {
//       btn.disabled = true;
//       btn.textContent = left + " 秒后可重发";
//     }
//     left -= 1;
//   };
//   tick();
//   codeTimer = setInterval(tick, 1000);
// }

// async function sendEmailCode() {
//   const email = (document.getElementById("reg-email").value || "").trim();
//   if (!email) {
//     showAlert("先填邮箱，再发验证码。", "bad");
//     return;
//   }
//   const cap = captchaPayload("reg");
//   if (!cap.captcha_text) {
//     showAlert("先填图形验证码，再发邮箱验证码。", "bad");
//     return;
//   }
//   const btn = document.getElementById("send-code");
//   if (btn) btn.disabled = true;
//   try {
//     const data = await postJson("/api/auth/email/code", {
//       email,
//       purpose: "register",
//       captcha_id: cap.captcha_id,
//       captcha_text: cap.captcha_text,
//     });
//     showAlert("");
//     noteCode(
//       data.dev_mode
//         ? "本地没配 SMTP，验证码是 " + data.dev_code + "（生产请关掉这个兜底）"
//         : "验证码已发到 " + data.email + "，10 分钟内有效。",
//       data.dev_mode ? "warn" : "ok"
//     );
//     startCooldown(data.cooldown || 60);
//   } catch (err) {
//     showAlert(err.message || "发送失败", "bad");
//     await loadCaptcha("reg");
//     if (btn) btn.disabled = false;
//   }
// }

async function submitLogin() {
  const account = (document.getElementById("login-user").value || "").trim();
  const password = document.getElementById("login-pass").value || "";
  if (!account || !password) {
    showAlert("账号和密码都要填。", "bad");
    return;
  }
  const btn = document.getElementById("login-submit");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "登录中…";
  }
  try {
    const payload = { account, password };
    const cap = captchaPayload("login");
    if (cap.captcha_text) Object.assign(payload, cap);
    enterDesk(await postJson("/api/auth/login", payload));
  } catch (err) {
    showAlert(err.message || "登录失败", "bad");
    if (err.captchaRequired) await showCaptcha("login");
    else await loadCaptcha("login");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "登录";
    }
  }
}

async function submitRegister() {
  const username = (document.getElementById("reg-user").value || "").trim();
  const email = (document.getElementById("reg-email").value || "").trim();
  const password = document.getElementById("reg-pass").value || "";
  const passengerId = document.getElementById("reg-pax").value || "";
  // 邮箱验证码暂时下线（见 web/present/views.py 里的说明），现在注册这一道是图形验证码
  const cap = captchaPayload("reg");
  if (!username || !email || !password) {
    showAlert("用户名、邮箱、密码都要填。", "bad");
    return;
  }
  if (!cap.captcha_text) {
    showAlert("先填图形验证码。", "bad");
    return;
  }
  const btn = document.getElementById("register-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "注册中…";
  }
  try {
    enterDesk(
      await postJson("/api/auth/register", {
        username,
        email,
        password,
        passenger_id: passengerId,
        ...cap,
      })
    );
  } catch (err) {
    showAlert(err.message || "注册失败", "bad");
    // 只有验证码本身失效/填错才换题：密码太短之类的便宜错误不烧题，用户不必重看一遍
    if (/图形验证码/.test(err.message || "")) await loadCaptcha("reg");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "注册并登录";
    }
  }
}

function signOut() {
  exploreCity = "";
  cityData = null;
  live = null;
  thinkingLog = [];
  boardSeen = {};
  cardsStamp = "";
  window.__snap = null;
  fetch("/api/auth/logout", { method: "POST" })
    .then((r) => r.json())
    .then((data) => render(data))
    .catch(() => {})
    .finally(() => showLogin("已退出登录。"));
}

// ---------------------------------------------------------------- 流式对话

function ingestMessages(messages) {
  if (!messages) return;
  messages.forEach((m) => {
    if (m.role === "assistant" && m.tool_calls && m.tool_calls.length) {
      m.tool_calls.forEach((c) => {
        thinkingLog.push({ type: "call", name: c.name, args: c.args || {} });
        if (live) live.thinking.push({ type: "call", name: c.name, args: c.args || {} });
      });
    } else if (m.role === "tool") {
      const row = { type: "result", name: m.name || "tool", content: m.content || "" };
      thinkingLog.push(row);
      if (live) live.thinking.push(row);
    } else if (m.role === "assistant" && m.content && live && !live.sawToken) {
      live.answer = m.content;
    }
  });
  if (live) paintLive();
}

function setBusy(flag) {
  document.body.classList.toggle("busy", Boolean(flag));
  ["send-btn", "approve-btn", "reject-btn", "msg", "session-new"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = flag;
  });
}

async function consumeSSE(url, body) {
  setBusy(true);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      if (res.status === 401) {
        signedIn = false;
        window.__snap = null;
        showLogin("会话已过期，请重新登录。");
        return;
      }
      const text = await res.text();
      throw new Error(text || "HTTP " + res.status);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop();
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "node") {
          document.getElementById("status").textContent = "正在执行：" + event.label;
          renderRadar(window.__snap || { trace: [], pending: null }, event.node);
          ingestMessages(event.messages || []);
        } else if (event.type === "token") {
          if (live) {
            live.sawToken = true;
            live.answer = (live.answer || "") + (event.text || "");
            paintLive();
          }
        } else if (event.type === "snapshot") {
          const fromServer = thinkingFromTurns(event.turns);
          if (fromServer.length > thinkingLog.length) thinkingLog = fromServer;
          live = null;
          render(event);
        } else if (event.type === "error") {
          document.getElementById("status").textContent = "调度失败：" + event.message;
        }
      }
    }
  } catch (err) {
    document.getElementById("status").textContent = "调度失败：" + err.message;
  } finally {
    setBusy(false);
  }
}

function send(text) {
  if (!signedIn) {
    showLogin("请先登录。");
    return;
  }
  const input = document.getElementById("msg");
  const message = (text != null ? text : input.value).trim();
  if (!message) return;
  input.value = "";
  const chat = document.getElementById("chat");
  if (chat.querySelector(".empty-hint")) chat.innerHTML = "";
  thinkingLog = [];
  live = { user: message, thinking: [], answer: "", sawToken: false };
  paintLive();
  consumeSSE("/api/chat/stream", { message });
}

// ---------------------------------------------------------------- 启动

function assignEnter(id, handler) {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handler();
    });
  }
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("send-btn").addEventListener("click", () => send());
  document.getElementById("msg").addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });

  document.getElementById("login-submit").addEventListener("click", () => submitLogin());
  document.getElementById("register-btn").addEventListener("click", () => submitRegister());
  // 邮箱验证码暂时下线：下面这行的 send-code 按钮已随表单一起注释掉
  // document.getElementById("send-code").addEventListener("click", () => sendEmailCode());
  document.getElementById("tab-login").addEventListener("click", () => switchTab("login"));
  document.getElementById("tab-register").addEventListener("click", () => switchTab("register"));
  // 题板本身就是「换一张」的按钮：点图重新出题
  document.getElementById("login-captcha-img").addEventListener("click", () => loadCaptcha("login"));
  document.getElementById("reg-captcha-img").addEventListener("click", () => loadCaptcha("reg"));
  assignEnter("login-pass", submitLogin);
  assignEnter("login-captcha-input", submitLogin);
  assignEnter("reg-pass", submitRegister);
  assignEnter("reg-captcha-input", submitRegister);

  document.getElementById("signout-btn").addEventListener("click", () => signOut());
  document.getElementById("session-new").addEventListener("click", () => newSession());

  // 左侧导航切页；地址栏带 #看板 这类锚点，刷新还能停在原页
  document.querySelectorAll(".nav-item[data-page]").forEach((b) => {
    b.addEventListener("click", () => showPage(b.dataset.page));
  });
  window.addEventListener("hashchange", () => showPage(currentPage()));

  // 看板筛选
  ["all", "car", "hotel", "spot"].forEach((k) => {
    const btn = document.getElementById("seg-" + k);
    if (btn) btn.addEventListener("click", () => switchBoardKind(k));
  });
  const onlyOpen = document.getElementById("seg-open");
  if (onlyOpen) onlyOpen.addEventListener("click", toggleOnlyOpen);

  document.querySelectorAll("button[data-url]").forEach((b) => {
    b.addEventListener("click", () => {
      thinkingLog = thinkingFromTurns((window.__snap && window.__snap.turns) || []);
      live = { user: "", thinking: thinkingLog.slice(), answer: "", sawToken: false };
      paintLive();
      consumeSSE(b.dataset.url, {});
    });
  });
  // 起手卡与快捷指令都是动态渲染的，统一用事件委托接住
  document.addEventListener("click", (e) => {
    const prompt = e.target.closest("[data-prompt]");
    if (prompt) send(prompt.dataset.prompt);
  });

  startClock();
  showPage(currentPage());

  // 先问登录状态：未登录停在登录页，已登录才拉快照
  fetch("/api/auth/me")
    .then((r) => r.json())
    .then((data) => {
      render(data);
      if ((data.identity || {}).authed === false) loadCaptcha("reg");
    })
    .catch(() => showLogin("工作台连不上，稍后再试。"));
});
