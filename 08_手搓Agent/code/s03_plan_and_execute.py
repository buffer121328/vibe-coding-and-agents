"""
s03_plan_and_execute.py - 8.3 Plan and Execute 规划范式 (TodoItem 状态机与结构化规划)
"""
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from s01_env_setup import ZhipuGLMClient

class TodoItem(BaseModel):
    """📋 任务清单节点（Todo 状态机：pending / in_progress / completed / failed）"""
    id: int = Field(description="任务编号，从1开始递增")
    title: str = Field(description="任务简要标题")
    detail: str = Field(description="执行该任务的具体操作细节")
    status: str = Field(default="pending", description="状态: pending | in_progress | completed | failed")
    result: Optional[str] = Field(default="", description="任务执行后的产出结果")

class PlanAndExecuteAgent:
    """📋 Plan-and-Execute 规划范式智能体：TodoItem 状态机与结构化任务拆解"""
    def __init__(self, client: ZhipuGLMClient):
        self.client = client
        self.todos: List[TodoItem] = []

    def create_plan(self, goal: str) -> List[TodoItem]:
        """📝 第一阶段：宏观意图拆解与生成任务清单"""
        prompt = f"""你是一个高级任务规划专家。请将用户的最终目标拆解为 3~5 个顺序递进、清晰明确的子任务。
                        输出必须是纯 JSON 数组，每个对象包含 id, title, detail 字段。严禁包含 markdown 格式以外的废话！

                        目标：{goal}

                        输出示例：
                        [
                        {{"id": 1, "title": "搜集背景资料", "detail": "查找关于目标领域的核心概念与最新进展"}},
                        {{"id": 2, "title": "提炼技术对比矩阵", "detail": "梳理各技术方案的优缺点并列成对比表"}},
                        {{"id": 3, "title": "生成总结报告", "detail": "汇总分析结果并输出 Markdown 交付物"}}
                        ]
                        """
        response = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},   # 结构化输出：让模型稳定吐出纯 JSON
        )
        content = response.choices[0].message.content.strip()

        try:
            raw_items = json.loads(content)
            self.todos = [TodoItem(**item) for item in raw_items]
        except Exception as e:
            # 降级容错（json_object 模式下正常不会触发，仍保留作保险）
            self.todos = [
                TodoItem(id=1, title="解析目标需求", detail=goal),
                TodoItem(id=2, title="执行核心步骤", detail="调用大模型推演具体解决方案"),
                TodoItem(id=3, title="汇总交付结果", detail="整理并输出最终报告"),
            ]
        return self.todos

    def execute_step(self, item: TodoItem, context: str) -> str:
        """⚙️ 第二阶段：单步执行与状态流转"""
        item.status = "in_progress"
        exec_prompt = f"""你正在执行一个大型项目中的具体子任务。
                            前置任务已产出如下上下文背景：
                            {context}

                            当前任务 #{item.id}：{item.title}
                            任务要求：{item.detail}

                            请针对当前任务，给出详尽、高质量的执行产出："""
        
        response = self.client.chat(
            messages=[{"role": "user", "content": exec_prompt}],
            temperature=0.6,
            max_tokens=1000,   # 限制单步输出长度，防止模型无上限生成导致看起来卡死/超时
            reasoning_effort="low",   # GLM-5.3 始终思考、不支持关闭思考，用 low 把"思考token"压到最低以提速
        )
        output = response.choices[0].message.content.strip()
        item.result = output
        item.status = "completed"
        return output

    def run_all_stream(self, goal: str):
        """🌊 完整规划并流式实时推送进度与产出至前端"""
        yield "🎯 正在进行宏观意图拆解并生成任务清单...", [], "*(正在进行意图拆解与子任务规划...)*"
        
        todos = self.create_plan(goal)
        current_todos = [t.model_dump() for t in self.todos]
        yield f"📋 已拆解生成 {len(todos)} 项子任务，开始逐步执行...", current_todos, "*(已完成宏观规划，开始执行子任务...)*"

        accumulated_context = f"## 🎯 全局最终目标: {goal}\n\n"
        for item in self.todos:
            item.status = "in_progress"
            current_todos = [t.model_dump() for t in self.todos]
            yield f"▶ 正在执行子任务 #{item.id}: {item.title} ...", current_todos, accumulated_context + f"\n\n> ⏳ 正在执行步骤 #{item.id}：{item.title}..."
            
            res = self.execute_step(item, accumulated_context)
            accumulated_context += f"### 步骤 {item.id}：{item.title}\n\n{res}\n\n---\n\n"
            current_todos = [t.model_dump() for t in self.todos]
            yield f"✔ 子任务 #{item.id}: {item.title} 完成", current_todos, accumulated_context

        yield f"✅ 规划与所有 {len(self.todos)} 个子任务已全部执行完成！", [t.model_dump() for t in self.todos], accumulated_context

    def run_all(self, goal: str, progress_callback=None) -> Dict[str, Any]:
        """🚀 完整规划并全自动执行（输出 Todo 状态机与交付汇总）"""
        todos = self.create_plan(goal)
        if progress_callback:
            progress_callback(todos, "已完成宏观规划，开始逐项执行...")

        accumulated_context = f"全局最终目标: {goal}\n"
        for item in self.todos:
            print(f"▶ 正在执行子任务 #{item.id}: {item.title} ...")
            if progress_callback:
                progress_callback(self.todos, f"正在执行子任务 #{item.id}: {item.title}")
            res = self.execute_step(item, accumulated_context)
            accumulated_context += f"\n【步骤 {item.id} - {item.title} 产出】:\n{res}\n"
            print(f"✔ 子任务 #{item.id} 完成")

        return {
            "goal": goal,
            "todos": [t.model_dump() for t in self.todos],
            "final_summary": accumulated_context,
        }

if __name__ == "__main__":
    # 🧪 Mock 自测：不依赖网络与 API Key，验证 TodoItem 状态机与执行流水线
    class MockResponse:
        def __init__(self, content):
            self.content = content
        @property
        def choices(self):
            return [type("M", (), {"message": self})()]

    class MockLLM:
        """🤖 假应答：规划阶段返回 JSON 清单，执行阶段返回固定产出"""
        def chat(self, messages, **kwargs):
            if kwargs.get("response_format"):
                return MockResponse('[{"id":1,"title":"买食材","detail":"去超市采购"},'
                                    '{"id":2,"title":"做菜","detail":"下锅炒熟"},'
                                    '{"id":3,"title":"装盘","detail":"摆盘上桌"}]')
            return MockResponse("完成：已产出高质量执行结果。")

    print("--- Mock 状态机自测 ---")
    mock_agent = PlanAndExecuteAgent(MockLLM())
    mock_res = mock_agent.run_all("策划一顿晚餐")
    todos = mock_res["todos"]
    print("Todo 数量:", len(todos))
    print("全部流转为 completed:", all(t["status"] == "completed" for t in todos))
    print("全部写入执行产出:", all(t["result"] for t in todos))
    print("首个子任务产出摘要:", todos[0]["result"][:30])

    print("\n--- 真实 LLM 规划与执行测试 (需 API Key) ---")
    client = ZhipuGLMClient()
    agent = PlanAndExecuteAgent(client)
    res = agent.run_all("帮我策划一顿简单健康的周末晚餐")
    print("规划与执行结果:\n", json.dumps(res, ensure_ascii=False, indent=2))
