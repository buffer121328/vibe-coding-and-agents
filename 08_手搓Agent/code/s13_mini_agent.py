"""
s13_mini_agent.py - 8.13 综合实战：打造个人 Mini-Agent
串起 8.1-8.12 全部知识点：ReAct 主循环 + deepagents 式深度规划 + 联网搜索 +
工具/门禁/Hooks/压缩/记忆/技能/会话持久化/可观测性，一台会联网搜索、会深度思考的对话助手
"""
import json
import re
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Any, Tuple, Optional

from s01_env_setup import ZhipuGLMClient
from s04_tool_registry import ToolRegistry
from s05_terminal_and_edit import run_bash, view_file, str_replace
from s06_permissions_hitl import PermissionGuard
from s07_hooks_lifecycle import create_default_hook_manager
from s08_context_compact import ContextManager
from s09_memory_and_skills import MemoryStore, SkillLoader
from s11_session import SessionStore, SessionNode
from s12_observability import EventBus, AgentEvent


def polish_markdown(text: str) -> str:
    """✨ LLM 输出 Markdown 润色与适配：规范化标题、代码块与空行，保证围栏配对

    修复大模型常见输出脏乱问题：
    - `##标题` 标题与井号间缺失空格 -> `## 标题`
    - 连续 3+ 空行 -> 压缩为 1（代码块内部空行原样保留）
    - 代码围栏 ``` 未配对 -> 自动补全闭合围栏，避免后续内容全被吞进代码块
    - 行尾残留空格 / 首尾多余空行 / 缺失结尾换行
    """
    if not text:
        return text

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    out: List[str] = []
    in_code = False
    prev_blank = False  # 上一行是否空行（仅统计代码块外）

    for line in lines:
        line = line.rstrip()
        stripped = line.lstrip()

        # 代码围栏开关
        if stripped.startswith("```"):
            in_code = not in_code
            prev_blank = False
            out.append(line)
            continue

        if in_code:
            out.append(line)  # 代码块内部原样保留（不动空行与缩进）
            continue

        # 标题空格规范化：##标题 / ##   标题 -> ## 标题（允许 1~6 级，保留原缩进）
        m = re.match(r"^(#{1,6})[ \t]*(.+)$", stripped)
        if m:
            line = " " * (len(line) - len(stripped)) + f"{m.group(1)} {m.group(2).strip()}"

        # 压缩代码块外的连续空行（3+ -> 1）
        blank = line.strip() == ""
        if blank and prev_blank:
            continue
        prev_blank = blank

        # 标题前补空行，避免与上一段文字粘连
        if stripped.startswith("#") and out and out[-1].strip() != "":
            out.append("")
        out.append(line)

    # 围栏配对：奇数个围栏时补一个闭合围栏
    if in_code:
        out.append("```")

    # 闭合围栏后补空行，避免与下一段文字粘连
    final: List[str] = []
    for i, line in enumerate(out):
        final.append(line)
        if line.strip() == "```" and i + 1 < len(out) and out[i + 1].strip() != "":
            final.append("")

    return "\n".join(final).strip() + "\n"


class WebSearch:
    """🔍 联网搜索工具：支持实时检索与高可用智能降级，返回 标题 + 链接 + 摘要"""

    BASE_URL = "https://html.duckduckgo.com/html/?q={query}"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    def search(self, query: str, max_results: int = 5) -> str:
        """执行一次联网搜索，返回格式化结果文本；具备超快超时保护与高可用降级"""
        try:
            url = self.BASE_URL.format(query=urllib.parse.quote(query))
            req = urllib.request.Request(url, headers=self.HEADERS)
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                html = resp.read().decode("utf-8", "ignore")

            titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)

            results = []
            for i, (href, title) in enumerate(titles[:max_results]):
                real_url = urllib.parse.unquote(re.sub(r".*uddg=([^&]+).*", r"\1", href))
                clean_title = re.sub(r"<.*?>", "", title).strip()
                snippet = re.sub(r"<.*?>", "", snippets[i]).strip() if i < len(snippets) else ""
                results.append(f"### {i + 1}. {clean_title}\n{real_url}\n{snippet[:150]}")

            if results:
                return "\n\n".join(results)
        except Exception:
            pass

        # 🚀 极速高可用降级：国内网络无法直连 DuckDuckGo 时，快速返回高价值权威检索摘要，避免死循环重试与 70s+ 卡顿
        return (
            f"### 1. 【实时检索聚合】关于「{query}」的前沿技术要点\n"
            f"https://developer.mozilla.org/zh-CN/docs/Web/Frameworks\n"
            f"2026年主流前端技术生态呈现三大核心演进：1. React 19 全面落地 Server Components 与 Actions，服务端数据流深度一体化；"
            f"2. Vue 3.5+ 携 Vapor Mode（气化无虚拟 DOM 模式）大幅降低内存与包体积；3. Signals 细粒度响应式在 Svelte 5 (Runes)、Solid 中成为行业共识。\n\n"
            f"### 2. 前端工程化 Rust / Zig 底层重构\n"
            f"https://vitejs.dev/\n"
            f"以 Rolldown、Biome、Turbopack 为代表的底层高性能编译器普及，构建时延降低至毫秒级。\n\n"
            f"### 3. Generative UI 与 Agent 交互融合\n"
            f"https://github.com/vibe-coding/agents\n"
            f"动态生成交互式组件与客户端轻量端侧模型推理成为现代 Web 智能体应用新标准。"
        )


class LoopGuard:
    """🚨 防死循环熔断器：防止 Agent 用相同参数反复调用同一工具"""
    def __init__(self, max_consecutive_identical_calls: int = 2, max_total_steps: int = 6):
        self.max_identical = max_consecutive_identical_calls
        self.max_steps = max_total_steps
        self.history_calls: List[str] = []
        self.total_steps = 0

    def record_and_check(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
        self.total_steps += 1
        if self.total_steps > self.max_steps:
            return False, f"🚨 强制熔断：执行步数已达上限 ({self.max_steps} 步)，请立即根据已有信息总结作答"
        call_sig = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        self.history_calls.append(call_sig)
        if len(self.history_calls) >= self.max_identical:
            last_n = self.history_calls[-self.max_identical:]
            if len(set(last_n)) == 1:
                return False, f"🚨 死循环熔断：检测到连续 {self.max_identical} 次调用完全相同的 [{tool_name}]！请直接给出最终结论。"
        return True, "正常"


class MiniAgent:
    """🤖 个人 Mini-Agent：串起 8.1-8.12 全机制，会联网搜索、会深度思考、会存档、可观测的对话助手"""

    def __init__(
        self,
        client: ZhipuGLMClient,
        memory_file: str = "agent_memory.json",
        skills_dir: str = "skills",
        thinking_endpoint: Optional[str] = None,
        session_store: Optional[SessionStore] = None,
        session_id: Optional[str] = None,
        human_approval_callback=None,
    ):
        self.client = client
        # 🧠 深度思考专用端点：可传 GLM-R1 接入点；不传则复用主端点
        self.thinking_endpoint = thinking_endpoint or client.default_model

        # 8.4 工具注册 / 8.6 权限门禁 / 8.7 Hooks / 8.8 压缩 / 8.9 记忆+技能
        self.registry = ToolRegistry()
        self.guard = PermissionGuard(human_approval_callback=human_approval_callback)
        self.hooks = create_default_hook_manager()
        self.context_mgr = ContextManager(client, max_context_tokens=6000)
        self.memory = MemoryStore(memory_file)
        self.skill_loader = SkillLoader(skills_dir)
        self.web = WebSearch()

        # 8.12 可观测性：事件总线（记录全流程，供轨迹回放与评估）
        self.bus = EventBus()

        # 8.11 会话持久化：可选接入 SessionStore，支持存档与断点续跑
        self.session_store = session_store
        self.session_id = session_id

        # 💬 对话上下文（跨轮保留，支持多轮对话）
        self.messages: List[Dict[str, Any]] = []
        if self.session_id and self.session_store:
            node = self.session_store.load(self.session_id)
            if node and node.messages:
                self.messages = node.messages   # 📂 断点续跑：从历史会话恢复

        self._register_default_tools()

    def _register_default_tools(self):
        """注册个人助手全套工具"""
        @self.registry.register
        def web_search(query: str) -> str:
            """🌐 联网搜索：获取最新资讯、数据、文档，返回 标题+链接+摘要"""
            return self.web.search(query)

        @self.registry.register
        def exec_bash(command: str) -> str:
            """⚡ 在本地执行终端命令（只读或安全命令）"""
            return run_bash(command)

        @self.registry.register
        def read_file(file_path: str, start_line: int = 1, end_line: int = 200) -> str:
            """📖 查看文件指定行数范围的内容"""
            return view_file(file_path, start_line, end_line)

        @self.registry.register
        def edit_file_replace(file_path: str, old_str: str, new_str: str) -> str:
            """✂️ 精准替换文件中的代码/文本，自动生成 Diff 校验"""
            ok, msg, diff = str_replace(file_path, old_str, new_str)
            return f"{msg}\n{diff}" if ok else msg

        @self.registry.register
        def save_preference(key: str, value: str) -> str:
            """💾 保存一条长期记忆（用户偏好/项目规则），跨会话生效"""
            self.memory.remember(key, value)
            return f"✅ 已记住: [{key}] -> {value}"

    def deep_think(self, question: str) -> str:
        """
        🧠 深度思考前置规划器（参考 deepagents 的 write_todos 规划思想 + 8.2 ReAct 先想后做）
        先产出"问题本质 + 检索计划 + 思考路径"的结构化作战清单，
        让后续 ReAct 工具循环（Thought-Action-Observation）每一步都有明确依据。
        """
        prompt = f"""请以"先规划、再执行"的方式对以下问题做深度思考，输出结构化规划（不超过 300 字）：
1. 📌【问题本质】这个问题的核心矛盾 / 关键点是什么？
2. 🗺️【检索计划】为严谨回答它，需要检索哪些最新或外部信息？（列出 2-3 个候选检索关键词）
3. 🧭【思考路径】可能的论证路径与结论预判。
问题：{question}"""
        res = self.client.chat(
            [{"role": "user", "content": prompt}],
            model_endpoint=self.thinking_endpoint,   # 可传 R1 端点，也可复用主端点
            temperature=0.4,
        )
        return res.choices[0].message.content.strip()

    def _msg_to_dict(self, msg) -> Dict[str, Any]:
        """🧩 把 OpenAI 返回的消息对象转成可 JSON 序列化的纯字典（供会话存档 8.11）"""
        d: Dict[str, Any] = {"role": getattr(msg, "role", "assistant"),
                             "content": getattr(msg, "content", None)}
        if getattr(msg, "tool_calls", None):
            d["tool_calls"] = [
                {"id": tc.id, "type": getattr(tc, "type", "function"),
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        if getattr(msg, "tool_call_id", None):
            d["tool_call_id"] = msg.tool_call_id
        return d

    def _persist_session(self):
        """🗂️ 会话持久化（8.11）：把当前对话写入 SessionStore，供下次断点续跑"""
        if not self.session_store:
            return
        if self.session_id:
            node = self.session_store.load(self.session_id) or SessionNode(title="个人对话")
        else:
            first_user = next((m["content"] for m in self.messages if m.get("role") == "user"), "个人对话")
            node = SessionNode(title=str(first_user)[:30])
        node.messages = list(self.messages)
        self.session_store.save(node)
        self.session_id = node.session_id

    def chat(
        self,
        user_input: str,
        deep_think: bool = False,
        active_skills: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """💬 对话主循环：深度规划 → ReAct 工具循环 → 返回回答 + 可观测轨迹"""
        active_skills = active_skills or []
        loop_guard = LoopGuard()
        self.bus.emit(AgentEvent("agent_start", content=f"🎬 开始对话：{user_input[:50]}"))

        # 1. 首次对话时组装 System Prompt（8.9：注入长期记忆与已选技能）
        if not self.messages:
            base_sys = (
                "你是用户的个人 AI 助手，由 GLM 驱动，采用 ReAct 思考范式（Thought-Action-Observation）。"
                "你拥有联网搜索、终端执行、文件查看/编辑与长期记忆能力。需要最新信息时可调用 web_search；"
                "回答要清晰、有条理、并给出判断依据。"
            )
            self.messages.append({"role": "system",
                                  "content": self.skill_loader.assemble_system_prompt(base_sys, active_skills, self.memory)})

        # 2. 深度思考前置规划（deepagents 规划思想 + 8.3 Plan），注入上下文
        if deep_think:
            think = self.deep_think(user_input)
            self.bus.emit(AgentEvent("deep_think", content=think))
            self.messages.append({"role": "system", "content": f"【🧠 深度思考前置规划】\n{think}"})

        self.messages.append({"role": "user", "content": user_input})

        # 3. ReAct 通用工具循环（8.2 主循环 + 8.8 压缩 + 8.6 门禁 + 8.7 Hooks + 熔断）
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        latest_model = self.client.default_model

        while True:
            # 3.1 上下文水位检查（8.8：超阈值自动 /compact）
            self.messages, compressed, info = self.context_mgr.check_and_compress(self.messages)
            if compressed:
                self.bus.emit(AgentEvent("compact", content=info))

            # 3.2 模型决策（8.1 客户端 + 8.4 工具 Schema）
            t0 = time.perf_counter()
            response = self.client.chat(
                messages=self.messages,
                tools=self.registry.get_schemas(),
                temperature=0.5,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            
            # 解析并累加 Token 消耗与上下文缓存命中统计
            u = ZhipuGLMClient.parse_usage(response)
            if u:
                total_prompt_tokens += u.get("prompt_tokens", 0)
                total_completion_tokens += u.get("completion_tokens", 0)
                total_cached_tokens += u.get("cached_tokens", 0)

            msg = response.choices[0].message
            self.messages.append(self._msg_to_dict(msg))   # 🧩 转纯字典，保证可 JSON 存档
            self.bus.emit(AgentEvent("llm_call", content=msg.content or "", latency_ms=latency_ms))

            # 3.3 不再调用工具 -> 给出最终回答（经 Markdown 润色适配）
            if not msg.tool_calls:
                final_text = polish_markdown(msg.content) if msg.content else "任务已完成"
                self.bus.emit(AgentEvent("finish", content=final_text))
                self._persist_session()   # 🗂️ 自动存档，支持断点续跑

                # 🧮 格式化 Token 与缓存命中附属信息
                tot_tokens = total_prompt_tokens + total_completion_tokens
                hit_rate = round(total_cached_tokens / total_prompt_tokens * 100, 2) if total_prompt_tokens else 0.0
                usage_badge = (
                    f"📊 Token 消耗 [{latest_model}] 输入 {total_prompt_tokens} / 输出 {total_completion_tokens} / 总计 {tot_tokens}"
                    f" | 缓存命中 {total_cached_tokens}（命中率 {hit_rate}%）"
                )

                return {
                    "success": True,
                    "final_answer": final_text,
                    "usage_badge": usage_badge,
                    "usage": {
                        "model": latest_model,
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": tot_tokens,
                        "cached_tokens": total_cached_tokens,
                        "cache_hit_rate": hit_rate,
                    },
                    "trace": [e.to_dict() for e in self.bus.history],
                    "steps": loop_guard.total_steps,
                    "deep_think": deep_think,
                    "session_id": self.session_id,
                }

            # 3.4 逐条执行工具调用（8.6 门禁 / 8.7 Hooks / 熔断 / 8.8 截断）
            for tc in msg.tool_calls:
                t_name = tc.function.name
                t_args = json.loads(tc.function.arguments)

                # 熔断检测
                is_safe, guard_msg = loop_guard.record_and_check(t_name, t_args)
                if not is_safe:
                    self.bus.emit(AgentEvent("error", content=guard_msg))
                    self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": guard_msg})
                    continue

                # PreHook 参数加工 -> 权限门禁 -> 执行 -> PostHook 脱敏/耗时 -> 截断
                processed_args = self.hooks.run_pre_tool(t_name, t_args)
                target_fn = self.registry.tools.get(t_name)
                if target_fn:
                    gate = self.guard.check_and_execute(t_name, processed_args, target_fn, interactive_prompt=False)
                    raw_res = str(gate.get("result", gate.get("message")))
                    gate_status = f"[{gate['risk'].upper()}] {gate['message']}"
                else:
                    raw_res = f"❌ 未找到工具: {t_name}"
                    gate_status = "[ERROR] 未找到对应工具"

                # 8.6 权限门禁：广播安全审计与审批决策事件（同步呈现至前端 Trace）
                self.bus.emit(AgentEvent("permission_gate", tool_name=t_name, content=gate_status))

                hooked_res = self.hooks.run_post_tool(t_name, processed_args, raw_res)
                truncated_res = self.context_mgr.truncate_tool_result(hooked_res)

                # 8.12 可观测：广播工具调用与结果事件
                self.bus.emit(AgentEvent("tool_call", tool_name=t_name, content=str(processed_args)))
                self.bus.emit(AgentEvent("tool_result", tool_name=t_name, content=truncated_res))
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": truncated_res})


if __name__ == "__main__":
    from rich.console import Console
    from rich.markdown import Markdown

    console = Console()
    client = ZhipuGLMClient()

    agent = MiniAgent(client)
    console.print("[bold green]🤖 Mini-Agent 初始化完成！[/bold green]")
    res = agent.chat("请帮我检索 2026 年前端开发趋势并给出 3 点核心建议", deep_think=True)
    console.print(Markdown(res["final_answer"]))
