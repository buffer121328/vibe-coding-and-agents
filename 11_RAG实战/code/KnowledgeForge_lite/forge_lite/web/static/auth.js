/* KnowledgeForge Lite · 登录/注册页
   只有这一个页面用得到：完整版 pages/Login.tsx 的同款流程。
   表单值一律当数据，只用 DOM 节点拼，不用 innerHTML。 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  /* 页面状态：当前在哪个选项卡、可选角色、演示账号列表。 */
  /* 页面状态：当前在哪个选项卡。 */
  const state = { tab: "login" };

  /**
   * 切换登录 / 注册选项卡。
   * @param {string} tab 目标选项卡，`"login"` 或 `"register"`。
   */
  function setTab(tab) {
    state.tab = tab;
    $("auth-tab-login").classList.toggle("is-on", tab === "login");
    $("auth-tab-register").classList.toggle("is-on", tab === "register");
    $("auth-pane-login").hidden = tab !== "login";
    $("auth-pane-register").hidden = tab !== "register";
    $("auth-submit").textContent = tab === "login" ? "登录" : "注册并进入";
    message("");
  }

  /**
   * 在表单下方写一行提示。
   * @param {string} text 要显示的话；传空串就是清掉。
   * @param {string} [kind] 语气后缀：`is-ok` 成功、`is-bad` 失败、`is-warn` 提醒。
   */
  function message(text, kind) {
    const node = $("auth-message");
    node.textContent = text || "";
    node.className = "msg" + (kind ? " " + kind : "");
  }

  /**
   * POST 一个 JSON 接口，非 2xx 就抛错。
   * @param {string} url 接口路径。
   * @param {object} [body] 请求体；不传则发空 POST（登出、访客都走这条）。
   * @returns {Promise<object>} 解析好的响应体。
   */
  async function post(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let payload = {};
    try {
      payload = await resp.json();
    } catch (_err) { /* 服务端偶尔不回 JSON */ }
    if (!resp.ok) throw new Error(payload.detail || "请求失败：" + resp.status);
    return payload;
  }

  /**
   * 提交当前选项卡的表单：登录或注册。成功后跳回控制台，失败留在原地显示原因。
   * 表单值从页面上现取，所以不接参数。
   */
  async function submit() {
    const button = $("auth-submit");
    button.disabled = true;
    message(state.tab === "login" ? "正在登录…" : "正在创建账号…");
    try {
      if (state.tab === "login") {
        await post("/api/auth/login", {
          username: $("auth-username").value,
          password: $("auth-password").value,
        });
      } else {
        await post("/api/auth/register", {
          username: $("reg-username").value,
          password: $("reg-password").value,
          display_name: $("reg-display").value,
          identity: $("reg-identity").value,
        });
      }
      message("好了，正在进入…", "is-ok");
      window.location.href = "/";
    } catch (err) {
      message(err.message, "is-bad");
      button.disabled = false;
    }
  }

  /* 演示账号：点一下就填进表单。课堂上省一轮打字，学生也能直接看四种权限。 */
  /**
   * 页面启动：接线交互、填好默认选项卡。
   */
  async function boot() {
    $("auth-tab-login").addEventListener("click", () => setTab("login"));
    $("auth-tab-register").addEventListener("click", () => setTab("register"));
    $("auth-submit").addEventListener("click", submit);
    $("auth-guest").addEventListener("click", async () => {
      await post("/api/auth/guest");
      window.location.href = "/";
    });
    ["auth-username", "auth-password"].forEach((id) => {
      $(id).addEventListener("keydown", (event) => {
        if (event.key === "Enter") submit();
      });
    });
    setTab("login");
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
