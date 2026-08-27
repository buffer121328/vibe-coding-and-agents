"""
s10_subagents.py - 8.10 Subagents 子代理协作与上下文隔离 (DeepResearch 多智能体流水线)
"""
import time
import concurrent.futures
from typing import Dict, Any, Optional, Callable
from s01_env_setup import ZhipuGLMClient

class Subagent:
    """👥 独立的子代理执行单元 (拥有隔离独立的 messages 上下文，带超时保护)"""
    def __init__(self, name: str, role_prompt: str, client: ZhipuGLMClient, timeout: float = 30.0):
        self.name = name
        self.role_prompt = role_prompt
        self.client = client
        self.timeout = timeout

    def run(self, task_input: str) -> str:
        """🎯 开启完全隔离的全新对话并返回纯净文本产出（超时自动降级，不拖垮整条流水线）"""
        isolated_messages = [
            {"role": "system", "content": self.role_prompt},
            {"role": "user", "content": task_input}
        ]

        def _call():
            response = self.client.chat(messages=isolated_messages, temperature=0.5)
            return response.choices[0].message.content.strip()

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(_call)
            return future.result(timeout=self.timeout)
        except concurrent.futures.TimeoutError:
            return (f"⚠️ [子代理「{self.name}」调用超时（>{self.timeout:.0f}s），"
                    "该阶段已跳过，后续阶段将基于已有部分结果继续]")
        except Exception as e:
            return f"⚠️ [子代理「{self.name}」调用异常: {e}]"
        finally:
            # wait=False：超时立即返回，不阻塞等待仍在后台运行的慢调用
            pool.shutdown(wait=False)

class DeepResearchPipeline:
    """
    🚀 四专家协同深度研究与报告流水线
    1. 规划者 (Planner) ➔ 2. 检索研究员 (Researcher) ➔ 3. 审查员 (Critic) ➔ 4. 终稿撰写员 (Writer)
    每个子代理调用均带超时保护，全程输出带时间戳的进度日志。
    """
    def __init__(self, client: ZhipuGLMClient, timeout: float = 30.0):
        self.client = client
        self.timeout = timeout
        self.planner = Subagent(
            name="研究规划师",
            role_prompt="你是一位资深研究规划专家。请将用户给出的宏观研究主题拆解为 2 个关键研究核心议题，用纯文本逐行输出，不要带任何无关废话。",
            client=client,
            timeout=timeout,
        )
        self.researcher = Subagent(
            name="深度检索研究员",
            role_prompt="你是一位博学严谨的技术分析员。请针对具体研究议题给出详尽的原理机制、技术优缺点与实际落地场景分析。",
            client=client,
            timeout=timeout,
        )
        self.critic = Subagent(
            name="批判审查员",
            role_prompt="你是一位尖锐犀利的同行评审专家。请审查研究员提供的报告草稿，指出其中的漏洞、未考虑的极端情况，并提出补充建议。",
            client=client,
            timeout=timeout,
        )
        self.writer = Subagent(
            name="终极主笔撰写员",
            role_prompt="你是一位顶级科技杂志主编。请综合前序研究与评审意见，撰写一份结构精美、文笔生动、条理清晰的终极 Markdown 深度分析报告。",
            client=client,
            timeout=timeout,
        )

    @staticmethod
    def _log(message: str, callback: Optional[Callable[[str], None]] = None) -> None:
        """🪵 输出带时间戳的进度日志（终端直接打印，UI 可通过 callback 同步）"""
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(line, flush=True)
        if callback:
            callback(line)

    def _run_stage(self, stage_name, start_msg, agent: Subagent, task_input: str,
                   timeline: list, callback=None) -> str:
        """🎬 执行单个子代理阶段：打进度日志 → 调用（带超时）→ 记录耗时与产出"""
        self._log(start_msg, callback)
        t0 = time.time()
        output = agent.run(task_input)
        elapsed = time.time() - t0
        self._log(f"✔ {agent.name}完成（耗时 {elapsed:.1f}s，产出 {len(output)} 字）", callback)
        timeline.append({"agent": agent.name, "stage": stage_name, "content": output})
        return output

    def execute_research_stream(self, topic: str):
        """🌊 流式执行四专家多智能体协作研究，实时 yield (状态日志, 时间线, 阶段报告 Markdown)"""
        timeline = []
        logs = []
        t_start = time.time()

        def _format_status(new_msg: str):
            logs.append(f"[{time.strftime('%H:%M:%S')}] {new_msg}")
            return "\n".join(logs)

        # 1. 规划师
        yield _format_status("🎯 [1/4 研究规划师] 正在拆解宏观研究课题..."), list(timeline), "*(规划师正在拆解核心研究议题...)*"
        t0 = time.time()
        plan_output = self.planner.run(f"研究课题：{topic}")
        timeline.append({"agent": self.planner.name, "stage": "课题拆解", "content": plan_output})
        yield _format_status(f"✔ 规划师完成（耗时 {time.time()-t0:.1f}s）"), list(timeline), f"### 🎯 规划师拆解议题\n\n{plan_output}"

        # 2. 深度检索研究员
        yield _format_status("🔍 [2/4 深度检索研究员] 正在针对拆解议题深入推演与技术调研..."), list(timeline), f"### 🎯 规划师拆解议题\n\n{plan_output}\n\n*(研究员正在深入调研分析...)*"
        t0 = time.time()
        research_output = self.researcher.run(f"课题：{topic}\n核心议题：\n{plan_output}")
        timeline.append({"agent": self.researcher.name, "stage": "深度技术推演", "content": research_output})
        yield _format_status(f"✔ 深度检索研究员完成（耗时 {time.time()-t0:.1f}s）"), list(timeline), f"### 🔍 深度调研成果\n\n{research_output}"

        # 3. 批判审查员
        yield _format_status("🧐 [3/4 批判审查员] 正在审查漏洞、挑刺与提出补充建议..."), list(timeline), f"### 🔍 深度调研成果\n\n{research_output}\n\n*(审查员正在挑刺与漏洞排查...)*"
        t0 = time.time()
        critic_output = self.critic.run(f"课题：{topic}\n研究内容：\n{research_output}")
        timeline.append({"agent": self.critic.name, "stage": "同行批判审查", "content": critic_output})
        yield _format_status(f"✔ 批判审查员完成（耗时 {time.time()-t0:.1f}s）"), list(timeline), f"### 🧐 审查评审意见\n\n{critic_output}"

        # 4. 终极主笔撰写员
        yield _format_status("✍️ [4/4 终极主笔撰写员] 正在综合各方意见，汇总撰写终极分析报告..."), list(timeline), "*(主笔正在撰写终极 Markdown 分析研报...)*"
        t0 = time.time()
        writer_input = f"课题：{topic}\n【研究内容】：\n{research_output}\n\n【审查意见】：\n{critic_output}\n"
        final_report = self.writer.run(writer_input)
        timeline.append({"agent": self.writer.name, "stage": "终极交付报告", "content": final_report})
        
        total_time = time.time() - t_start
        yield _format_status(f"🏁 四专家协同流水线已圆满完成！（总耗时 {total_time:.1f}s）"), list(timeline), final_report

    def execute_research(self, topic: str, callback=None) -> Dict[str, Any]:
        """🚀 执行端到端多智能体协作研究（返回时间线 + 终稿，全程进度日志 + 超时保护）"""
        timeline = []
        t_start = time.time()

        # 1. 规划
        plan_output = self._run_stage(
            "课题拆解", "🎯 规划师正在拆解研究课题...", self.planner,
            f"研究课题：{topic}", timeline, callback)

        # 2. 深度研究
        research_output = self._run_stage(
            "深度技术推演", "🔍 研究员正在针对拆解议题深入推演...", self.researcher,
            f"课题：{topic}\n核心议题：\n{plan_output}", timeline, callback)

        # 3. 评审与挑刺
        critic_output = self._run_stage(
            "同行批判审查", "🧐 审查员正在挑刺与漏洞排查...", self.critic,
            f"课题：{topic}\n研究内容：\n{research_output}", timeline, callback)

        # 4. 终稿撰写
        writer_input = f"""
课题：{topic}
【研究内容】：
{research_output}

【审查意见】：
{critic_output}
"""
        final_report = self._run_stage(
            "终极交付报告", "✍️ 主编正在汇总生成终极分析报告...", self.writer,
            writer_input, timeline, callback)

        self._log(f"🏁 全流程完成，总耗时 {time.time() - t_start:.1f}s", callback)

        return {
            "topic": topic,
            "timeline": timeline,
            "final_report": final_report,
        }

if __name__ == "__main__":
    # 🧪 Mock 自测：不依赖网络与 API Key，验证 4 阶段流水线与上下文隔离
    class MockResponse:
        def __init__(self, content):
            self.content = content
        @property
        def choices(self):
            return [type("M", (), {"message": self})()]

    class MockLLM:
        def __init__(self):
            self.calls = []
        def chat(self, messages, **kwargs):
            self.calls.append([m["role"] for m in messages])
            return MockResponse(f"[模拟产出] 收到 {len(messages)} 条上下文消息")

    print("--- Mock 流水线自测 ---")
    mock_llm = MockLLM()
    mock_res = DeepResearchPipeline(mock_llm).execute_research("测试课题")
    print("阶段时间线:", [t["stage"] for t in mock_res["timeline"]])
    print("4 个子代理各次消息数（上下文完全隔离，恒为 2 条）:", [len(c) for c in mock_llm.calls])
    print("最终报告已生成:", bool(mock_res["final_report"]))

    print("\n--- 真实 DeepResearch 流水线测试 (需 API Key) ---")
    client = ZhipuGLMClient()
    pipeline = DeepResearchPipeline(client)
    res = pipeline.execute_research("Agent Harness 工程在 2026 年的核心演进趋势")
    print("--- 终极深度研究报告 ---\n", res["final_report"])
