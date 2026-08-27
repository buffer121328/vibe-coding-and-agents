"""
s02_react_loop.py - 8.2 ReAct 思考范式 (Thought-Action-Observation 闭环)
"""
import json
import re
from typing import List, Dict, Any, Tuple
from s01_env_setup import ZhipuGLMClient

# 预定义两个极简工具函数
def calculate(expression: str) -> str:
    """🧮 安全数学计算器（仅允许安全字符）"""
    try:
        # 仅允许安全字符
        allowed = set("0123456789+-*/(). %")
        if not all(c in allowed for c in expression):
            return "错误：包含不安全的计算字符"
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"

def search_weather(city: str) -> str:
    """🌤️ 模拟城市天气查询（内置常用城市数据库）"""
    weather_db = {
        "北京": "晴，气温 22°C，微风",
        "上海": "阴转多云，气温 24°C，湿度 65%",
        "深圳": "雷阵雨，气温 28°C，注意带伞",
        "杭州": "微雨，气温 20°C，西湖风景绝佳",
    }
    return weather_db.get(city.strip(), f"未查询到【{city}】的天气信息，默认晴朗 25°C")

REACT_SYSTEM_PROMPT = """你是一个具备 ReAct (Reason + Act) 思考范式的智能助手。
解决问题时，你必须严格遵循以下格式进行逐步推演：

Thought: 思考当前需要做什么，分析已知信息
Action: 选择调用的工具，格式为 工具名[参数]（支持工具: calculate[表达式], search_weather[城市名]）
Observation: 工具返回的真实结果（此部分由环境提供，不要自己编造）
... (Thought/Action/Observation 可以重复多次)
Thought: 我现在知道了最终答案
Final Answer: 最终给用户的完整回答

示例：
Question: 北京和深圳的气温加起来是多少？
Thought: 我需要先查北京的气温，再查深圳的气温，最后相加。
Action: search_weather[北京]
Observation: 晴，气温 22°C，微风
Thought: 北京是 22°C。接下来查深圳的气温。
Action: search_weather[深圳]
Observation: 雷阵雨，气温 28°C，注意带伞
Thought: 深圳是 28°C。现在计算 22 + 28。
Action: calculate[22 + 28]
Observation: 50
Thought: 我现在知道了最终答案。
Final Answer: 北京气温 22°C，深圳气温 28°C，两者气温之和为 50°C。
"""

class ReActAgent:
    """🔄 ReAct 思考范式智能体：Thought-Action-Observation 单步试错自愈闭环"""
    def __init__(self, client: ZhipuGLMClient, max_steps: int = 6):
        self.client = client
        self.max_steps = max_steps
        self.tools = {
            "calculate": calculate,
            "search_weather": search_weather,
        }

    def run_stream(self, query: str):
        """🎯 流式运行 ReAct 思考循环，实时 yield (当前答案/推演进度, 思考轨迹步数)"""
        prompt = f"{REACT_SYSTEM_PROMPT}\n\nQuestion: {query}\n"
        steps_log = []

        yield "🧠 正在启动 ReAct 思考推演...", []

        for step in range(self.max_steps):
            yield f"🧠 [第 {step + 1} 步] 正在分析当前已知信息并决策下一步...", list(steps_log)
            
            # 调用大模型生成下一步
            response = self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, # 低温保证严格格式
            )
            output = response.choices[0].message.content.strip()
            prompt += output + "\n"

            # 解析 Thought
            thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)", output, re.DOTALL)
            thought = thought_match.group(1).strip() if thought_match else ""

            # 判断是否已经得到 Final Answer
            if "Final Answer:" in output:
                final_answer = output.split("Final Answer:")[-1].strip()
                steps_log.append({"step": step + 1, "thought": thought, "action": "完成", "observation": "达成目标"})
                yield final_answer, steps_log
                return

            # 解析 Action: tool_name[param]
            action_match = re.search(r"Action:\s*(\w+)\[(.*?)\]", output)
            if action_match:
                tool_name, tool_arg = action_match.group(1), action_match.group(2)
                
                # 执行工具
                if tool_name in self.tools:
                    obs = self.tools[tool_name](tool_arg)
                else:
                    obs = f"错误：未定义的工具 {tool_name}"
                
                obs_str = f"Observation: {obs}\n"
                prompt += obs_str
                steps_log.append({
                    "step": step + 1,
                    "thought": thought,
                    "action": f"{tool_name}[{tool_arg}]",
                    "observation": obs
                })
                yield f"⚡ [第 {step + 1} 步完成] 执行 `{tool_name}[{tool_arg}]` ➔ 获得结果: {obs}", list(steps_log)
            else:
                # 格式不匹配时的自愈提示
                prompt += "Observation: 请严格按照 Action: 工具名[参数] 或 Final Answer: 格式输出！\n"
                steps_log.append({"step": step + 1, "thought": thought, "action": "格式解析失败", "observation": "触发自愈重试"})
                yield f"⚠️ [第 {step + 1} 步] 格式未对齐，正在触发自愈重试...", list(steps_log)

        yield "抱歉，达到了最大思考步数限制，未能得出答案。", steps_log

    def run(self, query: str) -> Tuple[str, List[Dict[str, str]]]:
        """🎯 运行 ReAct 思考循环，返回 (最终答案, 思考轨迹步数)"""
        prompt = f"{REACT_SYSTEM_PROMPT}\n\nQuestion: {query}\n"
        steps_log = []

        for step in range(self.max_steps):
            # 调用大模型生成下一步
            response = self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, # 低温保证严格格式
            )
            output = response.choices[0].message.content.strip()
            prompt += output + "\n"

            # 解析 Thought
            thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)", output, re.DOTALL)
            thought = thought_match.group(1).strip() if thought_match else ""

            # 判断是否已经得到 Final Answer
            if "Final Answer:" in output:
                final_answer = output.split("Final Answer:")[-1].strip()
                steps_log.append({"step": step + 1, "thought": thought, "action": "完成", "observation": "达成目标"})
                return final_answer, steps_log

            # 解析 Action: tool_name[param]
            action_match = re.search(r"Action:\s*(\w+)\[(.*?)\]", output)
            if action_match:
                tool_name, tool_arg = action_match.group(1), action_match.group(2)
                
                # 执行工具
                if tool_name in self.tools:
                    obs = self.tools[tool_name](tool_arg)
                else:
                    obs = f"错误：未定义的工具 {tool_name}"
                
                obs_str = f"Observation: {obs}\n"
                prompt += obs_str
                steps_log.append({
                    "step": step + 1,
                    "thought": thought,
                    "action": f"{tool_name}[{tool_arg}]",
                    "observation": obs
                })
            else:
                # 格式不匹配时的自愈提示
                prompt += "Observation: 请严格按照 Action: 工具名[参数] 或 Final Answer: 格式输出！\n"
                steps_log.append({"step": step + 1, "thought": thought, "action": "格式解析失败", "observation": "触发自愈重试"})

        return "抱歉，达到了最大思考步数限制，未能得出答案。", steps_log

if __name__ == "__main__":
    # 🧪 纯函数自测：不依赖网络与 API Key
    print("--- 工具函数自测 ---")
    print("calculate('2 + 3 * 4') =", calculate("2 + 3 * 4"))
    print("calculate 危险输入 =", calculate("__import__('os').system('ls')"))
    print("search_weather('北京') =", search_weather("北京"))
    print("search_weather('拉萨') =", search_weather("拉萨"))

    print("\n--- ReAct 闭环测试 (需 API Key) ---")
    client = ZhipuGLMClient()
    agent = ReActAgent(client)
    ans, logs = agent.run("请问上海和杭州的气温相差多少度？")
    print("最终答案:", ans)
    print("思考轨迹:", json.dumps(logs, ensure_ascii=False, indent=2))
