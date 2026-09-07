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
from types import SimpleNamespace
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
    """🔍 联网搜索工具：只返回实际抓取结果，失败时明确报错。"""

    BASE_URL = "https://html.duckduckgo.com/html/?q={query}"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    def search(self, query: str, max_results: int = 5) -> str:
        """执行一次联网搜索；网络失败或页面结构变化时绝不伪造结果。"""
        if not query.strip():
            return "❌ 搜索失败：查询词不能为空。"
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
            return "❌ 搜索失败：搜索服务返回了空结果，不能据此声称获得了实时信息。"
        except Exception as exc:
            return f"❌ 搜索失败：{type(exc).__name__}。请稍后重试或改用可信搜索 API；本工具不会生成虚假兜底内容。"


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

    def chat_stream(
        self,
        user_input: str,
        deep_think: bool = False,
        active_skills: Optional[List[str]] = None,
    ):
        """🔤 流式对话主循环（8.1 chat_stream 接入）：逐字 yield 正文 delta，工具调用轮静默执行

        与 chat() 完全同一套机制（压缩/门禁/Hooks/熔断/存档/事件），区别仅在模型决策阶段：
        - 无工具调用的最终回答轮：逐字 yield 正文增量，结束时经 StopIteration.value 返回最终结果字典
          （调用方用 `for ... in` 迭代后取 `gen.return` 或捕获 StopIteration.value，与 Web 端线程封装一致）；
        - 工具轮：s01 的流式只吐正文 delta、不透出 tool_calls 片段，故正文为空时做一次非流式重放
          拿到结构化 tool_calls，再走与 chat() 完全一致的执行链，状态变化经 EventBus 广播。
        """
        active_skills = active_skills or []
        loop_guard = LoopGuard()
        self.bus.emit(AgentEvent("agent_start", content=f"🎬 开始对话：{user_input[:50]}"))

        # 1. 首次对话时组装 System Prompt（与 chat() 一致）
        if not self.messages:
            base_sys = (
                "你是用户的个人 AI 助手，由 GLM 驱动，采用 ReAct 思考范式（Thought-Action-Observation）。"
                "你拥有联网搜索、终端执行、文件查看/编辑与长期记忆能力。需要最新信息时可调用 web_search；"
                "回答要清晰、有条理、并给出判断依据。"
            )
            self.messages.append({"role": "system",
                                  "content": self.skill_loader.assemble_system_prompt(base_sys, active_skills, self.memory)})

        # 2. 深度思考前置规划
        if deep_think:
            think = self.deep_think(user_input)
            self.bus.emit(AgentEvent("deep_think", content=think))
            self.messages.append({"role": "system", "content": f"【🧠 深度思考前置规划】\n{think}"})

        self.messages.append({"role": "user", "content": user_input})

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        latest_model = self.client.default_model

        while True:
            # 3.1 上下文水位检查（8.8）
            self.messages, compressed, info = self.context_mgr.check_and_compress(self.messages)
            if compressed:
                self.bus.emit(AgentEvent("compact", content=info))

            # 3.2 模型决策（流式）：正文增量逐字 yield；usage 由 s01 内部消费，Token 走字符估算兜底
            t0 = time.perf_counter()
            content_parts: List[str] = []
            first_token = True

            for delta in self.client.chat_stream(messages=self.messages, tools=self.registry.get_schemas(), temperature=0.5):
                if first_token:
                    self.bus.emit(AgentEvent("llm_call", content="(stream)", latency_ms=(time.perf_counter() - t0) * 1000))
                    first_token = False
                # delta 为 str（正文增量）时逐字转发；usage 由 s01 末尾 _log_usage 打印，这里走字符估算兜底
                if isinstance(delta, str):
                    content_parts.append(delta)
                    yield delta

            latency_ms = (time.perf_counter() - t0) * 1000
            content_text = "".join(content_parts)

            # Token 统计：流式 usage 被 s01 内部消费，这里按字符估算兜底，保证徽章不缺失
            if not first_token:
                est = max(len(content_text) // 3, 1)
                total_completion_tokens += est
                total_prompt_tokens += sum(len(str(m.get("content", ""))) // 3 for m in self.messages)

            # 3.3 判定本轮是否有工具调用：s01 的 chat_stream 只吐正文 delta、不透出 tool_calls 片段，
            # 因此只要本轮正文为空（模型把输出全部给了工具调用），就做一次非流式重放拿结构化 tool_calls。
            if content_text.strip():
                msg = SimpleNamespace(content=content_text, tool_calls=None)
            else:
                resp = self.client.chat(
                    messages=self.messages,
                    tools=self.registry.get_schemas(),
                    temperature=0.5,
                    show_usage=False,
                )
                msg = resp.choices[0].message
                u = ZhipuGLMClient.parse_usage(resp)
                if u:
                    total_prompt_tokens += u.get("prompt_tokens", 0)
                    total_completion_tokens += u.get("completion_tokens", 0)
                    total_cached_tokens += u.get("cached_tokens", 0)
            self.messages.append(self._msg_to_dict(msg))
            if first_token:
                self.bus.emit(AgentEvent("llm_call", content="(empty)", latency_ms=latency_ms))

            # 3.4 无工具调用 -> 流式正文已逐字吐给调用方，收尾返回（与 chat() 同构）
            if not msg.tool_calls:
                final_text = polish_markdown(msg.content) if msg.content else "任务已完成"
                self.bus.emit(AgentEvent("finish", content=final_text))
                self._persist_session()

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
                    "usage": {"model": latest_model,
                              "prompt_tokens": total_prompt_tokens,
                              "completion_tokens": total_completion_tokens,
                              "total_tokens": tot_tokens,
                              "cached_tokens": total_cached_tokens,
                              "cache_hit_rate": hit_rate},
                    "trace": [e.to_dict() for e in self.bus.history],
                    "steps": loop_guard.total_steps,
                    "deep_think": deep_think,
                    "session_id": self.session_id,
                }

            # 3.5 工具轮：拿到结构化 tool_calls 后走与 chat() 完全一致的执行链（熔断/门禁/Hooks/截断/事件）
            self.bus.emit(AgentEvent("llm_call", content=msg.content or "", latency_ms=latency_ms))

            for tc in msg.tool_calls:
                t_name = tc.function.name
                try:
                    t_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    t_args = {}

                is_safe, guard_msg = loop_guard.record_and_check(t_name, t_args)
                if not is_safe:
                    self.bus.emit(AgentEvent("error", content=guard_msg))
                    self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": guard_msg})
                    continue

                processed_args = self.hooks.run_pre_tool(t_name, t_args)
                target_fn = self.registry.tools.get(t_name)
                if target_fn:
                    gate = self.guard.check_and_execute(t_name, processed_args, target_fn, interactive_prompt=False)
                    raw_res = str(gate.get("result", gate.get("message")))
                    gate_status = f"[{gate['risk'].upper()}] {gate['message']}"
                else:
                    raw_res = f"❌ 未找到工具: {t_name}"
                    gate_status = "[ERROR] 未找到对应工具"

                self.bus.emit(AgentEvent("permission_gate", tool_name=t_name, content=gate_status))
                hooked_res = self.hooks.run_post_tool(t_name, processed_args, raw_res)
                truncated_res = self.context_mgr.truncate_tool_result(hooked_res)
                self.bus.emit(AgentEvent("tool_call", tool_name=t_name, content=str(processed_args)))
                self.bus.emit(AgentEvent("tool_result", tool_name=t_name, content=truncated_res))
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": truncated_res})

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


# ========== 4️⃣ CLI 实时状态层：EventBus 通配订阅，让终端实时看到状态流转（🧠→⚙️→✅→🏁） ==========
from rich import markup as _markup

# CLI 专用会话仓库：存档落盘 sessions/ 目录，供 /sessions 与 /resume 使用（8.11）
_CLI_STORE = None


def _cli_store():
    global _CLI_STORE
    if _CLI_STORE is None:
        _CLI_STORE = SessionStore(storage_dir="sessions")
    return _CLI_STORE

# 事件类型 → (emoji, 状态文案)：MiniAgent 每跑一步都会 bus.emit，订阅后即可实时打印
EVENT_STATUS_MAP: Dict[str, Tuple[str, str]] = {
    "agent_start":     ("🚀", "开始处理"),
    "deep_think":      ("🧠", "深度思考"),
    "llm_call":        ("🤔", "模型思考中"),
    "tool_call":       ("⚙️", "调用工具"),
    "tool_result":     ("✅", "工具返回"),
    "permission_gate": ("🛡️", "权限门禁"),
    "compact":         ("🗜️", "上下文压缩"),
    "error":           ("❌", "错误"),
    "finish":          ("🏁", "完成"),
}


def _one_line(text: str, limit: int = 88) -> str:
    """把多行文本压成单行并截断，用于状态行展示"""
    flat = " ".join(str(text).split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def make_status_printer(console):
    """📡 构造 EventBus 通配订阅回调：每条事件实时打印一行状态（不改 MiniAgent 核心逻辑）"""
    def on_event(event: AgentEvent) -> None:
        emoji, label = EVENT_STATUS_MAP.get(event.event_type, ("🔔", event.event_type))
        # finish 只报完成不重复答案（完整回答随后渲染）；detail 需转义，防止 [工具名] 被 rich 当样式标签吞掉
        if event.event_type == "finish":
            detail = ""
        elif event.event_type == "tool_call":
            detail = f"{event.tool_name} → {_markup.escape(_one_line(event.content))}"
        elif event.event_type == "tool_result":
            detail = f"{event.tool_name} ← {_markup.escape(_one_line(event.content, 60))}"
        elif event.event_type == "llm_call":
            detail = f"耗时 {event.latency_ms:.0f}ms" if event.latency_ms else ""
        else:
            detail = _markup.escape(_one_line(event.content))
        console.print(f"  {emoji} [bold]{label}[/bold] {detail}".rstrip())
    return on_event


REPL_LOGO = r"""[bold green]███╗   ███╗██╗███╗   ██╗██╗
████╗ ████║██║████╗  ██║██║
██╔████╔██║██║██╔██╗ ██║██║
██║╚██╔╝██║██║██║╚██╗██║██║
██║ ╚═╝ ██║██║██║ ╚████║██║
╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝

 █████╗  ██████╗ ███████╗███╗   ██╗████████╗
██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝[/bold green]
[dim]个人 Mini-Agent · 会联网搜索、会深度思考的对话助手（8.13 综合实战）[/dim]

💡 输入 [bold]/[/bold] 即弹出命令菜单，[bold]↑↓[/bold] 翻历史记录，[bold]Tab[/bold] 补全
"""

# /help 完整命令清单（启动横幅保持极简，命令细节交给 / 菜单与 /help）
REPL_HELP = """\
📖 [bold]命令清单[/bold]
  [bold]普通问题[/bold]        直接对话回答
  [bold]/deep 问题[/bold]      开启深度思考后回答
  [bold]/search 问题[/bold]    强制先联网搜索再回答
  [bold]/sessions[/bold]       列出全部历史会话存档
  [bold]/resume <编号|ID>[/bold]  恢复指定会话继续对话（断点续跑）
  [bold]/clear[/bold]          开启全新会话（旧会话自动存档，长期记忆保留）
  [bold]/help[/bold]           显示本帮助
  [bold]/quit[/bold]           退出对话
"""

# / 命令菜单：输入 / 时弹出候选列表（prompt_toolkit 补全器数据源）
REPL_COMMANDS = [
    ("/deep ", "开启深度思考后回答，例：/deep 如何从零学好 Agent？"),
    ("/search ", "强制先联网搜索再回答，例：/search 最新科技新闻"),
    ("/sessions", "列出全部历史会话存档"),
    ("/resume ", "恢复指定会话继续对话，例：/resume 1 或 /resume <session_id>"),
    ("/clear", "清空会话上下文重新开始（长期记忆保留）"),
    ("/help", "显示帮助"),
    ("/quit", "退出对话"),
]


def _build_prompt_session():
    """⌨️ 构建 prompt_toolkit 输入会话：/ 命令菜单 + 输入历史（↑↓ 翻阅）；终端不支持时优雅降级"""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.styles import Style

        completer = WordCompleter(
            [cmd for cmd, _ in REPL_COMMANDS],
            meta_dict={cmd: desc for cmd, desc in REPL_COMMANDS},
            sentence=True,       # 补全对象是整条命令前缀（含 /deep 后的空格）
            match_middle=False,
        )
        style = Style.from_dict({"completion-menu.completion": "bg:#1e3a5f #ffffff",
                                 "completion-menu.meta-completion": "bg:#1e3a5f #94a3b8"})
        return PromptSession(history=FileHistory(".s13_repl_history"),
                             completer=completer, auto_suggest=AutoSuggestFromHistory(),
                             style=style), True
    except Exception:
        return None, False   # 非交互终端（管道/无 TTY）自动退回内置 input()


def interactive_repl(client: ZhipuGLMClient) -> None:
    """💬 交互式命令行对话（REPL）：/ 命令菜单补全 + 会话存档恢复 + 流式打字机输出"""
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.table import Table
    from rich.live import Live

    console = Console()
    agent = MiniAgent(client, session_store=_cli_store())
    agent.bus.subscribe("*", make_status_printer(console))
    console.print(REPL_LOGO)

    prompt_session, fancy = _build_prompt_session()

    def _ask() -> str:
        if fancy:
            return prompt_session.prompt("👤 You> ").strip()
        return input("👤 You> ").strip()

    while True:
        try:
            user_input = _ask()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold green]👋 再见！期待下次对话。[/bold green]")
            break

        if not user_input:
            continue

        head, _, rest = user_input.partition(" ")
        rest = rest.strip()
        head = head.lower()

        if head in ("/quit", "/exit", "/q"):
            console.print("[bold green]👋 再见！期待下次对话。[/bold green]")
            break
        if head == "/clear":
            agent = MiniAgent(client, session_store=_cli_store())
            agent.bus.subscribe("*", make_status_printer(console))
            console.print("🧹 [bold]已开启全新会话[/bold]（旧会话已存档至 sessions/，可用 /sessions 查看；长期记忆保留）")
            continue
        if head == "/help":
            console.print(REPL_HELP)
            continue
        if head == "/sessions":
            rows = [(s["session_id"], s["title"], s["message_count"], s["created_at"])
                    for s in _cli_store().list_sessions()]
            if not rows:
                console.print("📭 暂无会话存档（对话结束后会自动写入 sessions/ 目录）")
                continue
            table = Table(title="🗂️ 历史会话存档（sessions/）", show_lines=False)
            table.add_column("#", justify="right", style="bold")
            table.add_column("Session ID", style="cyan")
            table.add_column("标题（首条提问）", overflow="fold")
            table.add_column("消息数", justify="right")
            table.add_column("创建时间")
            for i, (sid, title, cnt, created) in enumerate(rows, 1):
                table.add_row(str(i), sid, title, str(cnt), created)
            console.print(table)
            console.print("[dim]💡 用 /resume <编号> 恢复对应会话继续对话[/dim]")
            continue
        if head == "/resume":
            summaries = _cli_store().list_sessions()
            if not summaries:
                console.print("📭 暂无会话存档，无法恢复")
                continue
            # 参数支持序号（/resume 1）或完整 session_id（/resume abc123）
            target = None
            if rest.isdigit() and 1 <= int(rest) <= len(summaries):
                target = summaries[int(rest) - 1]["session_id"]
            else:
                target = rest
            node = _cli_store().load(target)
            if node is None:
                console.print(f"❌ 未找到会话：[bold]{rest}[/bold]（可用 /sessions 查看编号）")
                continue
            agent = MiniAgent(client, session_store=_cli_store(), session_id=node.session_id)
            agent.bus.subscribe("*", make_status_printer(console))
            console.print(f"📂 [bold]已恢复会话[/bold] [cyan]{node.session_id}[/cyan]（{node.title}，共 {len(node.messages)} 条消息），继续对话吧！")
            continue
        if head in ("/deep", "/search") and not rest:
            console.print("💡 请在命令后跟上问题，例如：[bold]/deep 如何从零学好 Agent 开发？[/bold]")
            continue

        # 解析命令前缀 -> (问题, 是否深度思考, 是否强制联网)
        if head == "/deep":
            question, deep, force_search = rest, True, False
        elif head == "/search":
            question, deep, force_search = rest, False, True
        else:
            question, deep, force_search = user_input, False, False

        # 强制联网：注入一条 system 消息，让模型优先调用 web_search（与 Gradio 工作台同款逻辑）
        if force_search and not any(
            m.get("content", "").startswith("用户要求你优先调用 web_search") for m in agent.messages
        ):
            agent.messages.append({
                "role": "system",
                "content": "用户要求你优先调用 web_search 联网检索后再回答。请在获取到搜索结果后直接总结输出最终答案，不要重复搜索。",
            })

        console.print()
        try:
            # 流式对话：先实时打印 EventBus 状态行，再用 rich Live 打字机逐字渲染回答
            res = None
            gen = agent.chat_stream(question, deep_think=deep)
            with Live(console=console, refresh_per_second=12, vertical_overflow="ellipsis") as live:
                buf = ""
                while True:
                    try:
                        delta = next(gen)
                        if isinstance(delta, str):
                            buf += delta
                            live.update(Markdown(buf))
                    except StopIteration as e:
                        res = e.value
                        break
            live.update(Markdown(polish_markdown(res["final_answer"])))
        except Exception as exc:
            console.print(f"[bold red]❌ 本轮执行出错：{type(exc).__name__}: {exc}[/bold red]")
            continue
        console.print(f"[dim]{res['usage_badge']}[/dim]" if res.get("usage_badge") else "")
        console.print()


if __name__ == "__main__":
    import argparse

    from rich.console import Console
    from rich.markdown import Markdown

    parser = argparse.ArgumentParser(description="8.13 个人 Mini-Agent：会联网搜索、会深度思考的对话助手")
    parser.add_argument("--repl", "-i", action="store_true",
                        help="进入交互式命令行对话（默认运行一条单轮演示问题）")
    args = parser.parse_args()

    console = Console()
    client = ZhipuGLMClient()

    if args.repl:
        interactive_repl(client)
    else:
        # 单轮演示模式：跑一条写死的演示问题，实时打印状态流转
        agent = MiniAgent(client)
        agent.bus.subscribe("*", make_status_printer(console))
        console.print("[bold green]🤖 Mini-Agent 初始化完成！正在运行单轮演示…[/bold green]")
        console.print("[dim]💡 提示：运行 uv run python s13_mini_agent.py --repl 可进入交互式多轮对话[/dim]\n")
        res = agent.chat("请帮我检索 2026 年前端开发趋势并给出 3 点核心建议", deep_think=True)
        console.print("🤖 [bold]Agent>[/bold]")
        console.print(Markdown(res["final_answer"]))
        if res.get("usage_badge"):
            console.print(f"[dim]{res['usage_badge']}[/dim]")
