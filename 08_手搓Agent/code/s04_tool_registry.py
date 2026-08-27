"""
s04_tool_registry.py - 8.4 工具注册与分发机制 (@tool 装饰器与 JSON Schema 生成)
"""
import inspect
import json
from typing import Callable, Dict, Any, List, Optional
from s01_env_setup import ZhipuGLMClient

def python_type_to_json_type(py_type: Any) -> str:
    """🔢 Python 类型映射到 JSON Schema 类型"""
    if py_type in (int, float):
        return "number" if py_type is float else "integer"
    elif py_type is bool:
        return "boolean"
    elif py_type is list:
        return "array"
    elif py_type is dict:
        return "object"
    return "string"

class ToolRegistry:
    """🧰 通用工具注册与分发路由中心（@tool 装饰器 + Dispatch Map 分发）"""
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

    def register(self, func: Callable) -> Callable:
        """🪄 @tool 装饰器：自动从函数签名与 docstring 提取 JSON Schema"""
        name = func.__name__
        doc = inspect.getdoc(func) or "没有提供函数说明"
        sig = inspect.signature(func)

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            param_type = param.annotation if param.annotation != inspect.Parameter.empty else str
            properties[param_name] = {
                "type": python_type_to_json_type(param_type),
                "description": f"参数 {param_name}",
            }
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": doc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

        self.tools[name] = func
        self.schemas.append(schema)
        return func

    def get_schemas(self) -> List[Dict[str, Any]]:
        """📋 获取所有已注册工具的 JSON Schema 列表"""
        return self.schemas

    def dispatch(self, name: str, arguments: Dict[str, Any]) -> str:
        """🚏 根据工具名与参数字典执行工具调用（Dispatch Map 路由）"""
        if name not in self.tools:
            return f"❌ 错误：工具 [{name}] 未在注册表中定义"
        try:
            func = self.tools[name]
            result = func(**arguments)
            return str(result)
        except Exception as e:
            return f"❌ 工具执行异常 [{name}]: {e}"

# 创建全局注册表实例
registry = ToolRegistry()

# 示例注册工具
@registry.register
def get_user_info(user_id: int) -> str:
    """👤 根据用户 ID 查询员工档案信息"""
    mock_users = {
        101: "张三 (架构师 - 基础架构部)",
        102: "李四 (资深前端 - Vibe Studio)",
        103: "王五 (算法专家 - 智能体实验室)",
    }
    return mock_users.get(user_id, "未找到该用户")

@registry.register
def calculate_salary(base: float, bonus: float, tax_rate: float = 0.1) -> str:
    """💰 计算员工税后净收入"""
    total = (base + bonus) * (1 - tax_rate)
    return f"税后净收入: {total:.2f} 元"

class FunctionCallingAgent:
    """🤖 基于原生 Function Calling 协议的智能体（工具握手闭环）"""
    def __init__(self, client: ZhipuGLMClient, tool_registry: ToolRegistry):
        self.client = client
        self.registry = tool_registry

    def chat_with_tools_stream(self, user_prompt: str):
        """🌊 流式进行带工具支持的多轮调用对话（实时 yield 进度）"""
        schemas = self.registry.get_schemas()
        messages = [
            {"role": "system", "content": "你是一个严谨的助理，善于调用工具完成精确查询和计算。"},
            {"role": "user", "content": user_prompt}
        ]
        logs = []

        yield "🤖 [第一轮] 正在提交指令，大模型决策是否调用工具...", schemas, []

        # 第一轮：提交用户问题与工具集
        response = self.client.chat(
            messages=messages,
            tools=schemas,
        )
        msg = response.choices[0].message

        # 如果模型决定调用工具
        if msg.tool_calls:
            # 记录 assistant 的调用意图
            messages.append(msg)
            for tool_call in msg.tool_calls:
                t_name = tool_call.function.name
                t_args = json.loads(tool_call.function.arguments)
                logs.append({"call_id": tool_call.id, "tool": t_name, "args": t_args})
                yield f"🛠️ [工具调度] 正在执行 `{t_name}({t_args})`...", schemas, list(logs)

                # 执行工具分发
                result = self.registry.dispatch(t_name, t_args)
                logs.append({"call_id": tool_call.id, "result": result})
                yield f"✔ [工具完成] `{t_name}` 返回: {str(result)[:60]}", schemas, list(logs)

                # 将工具执行结果作为 tool 角色消息回填
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            yield "✍️ [第二轮] 正在根据工具执行结果整合生成最终回答...", schemas, list(logs)

            # 第二轮：模型根据工具结果生成最终回答
            final_res = self.client.chat(messages=messages)
            final_answer = final_res.choices[0].message.content
        else:
            final_answer = msg.content

        yield final_answer, schemas, logs

    def chat_with_tools(self, user_prompt: str) -> Dict[str, Any]:
        """💬 进行带工具支持的多轮调用对话（含工具结果回填）"""
        messages = [
            {"role": "system", "content": "你是一个严谨的助理，善于调用工具完成精确查询和计算。"},
            {"role": "user", "content": user_prompt}
        ]
        logs = []

        # 第一轮：提交用户问题与工具集
        response = self.client.chat(
            messages=messages,
            tools=self.registry.get_schemas(),
        )
        msg = response.choices[0].message

        # 如果模型决定调用工具
        if msg.tool_calls:
            # 记录 assistant 的调用意图
            messages.append(msg)
            for tool_call in msg.tool_calls:
                t_name = tool_call.function.name
                t_args = json.loads(tool_call.function.arguments)
                logs.append({"call_id": tool_call.id, "tool": t_name, "args": t_args})

                # 执行工具分发
                result = self.registry.dispatch(t_name, t_args)
                logs.append({"call_id": tool_call.id, "result": result})

                # 将工具执行结果作为 tool 角色消息回填
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            # 第二轮：模型根据工具结果生成最终回答
            final_res = self.client.chat(messages=messages)
            final_answer = final_res.choices[0].message.content
        else:
            final_answer = msg.content

        return {
            "answer": final_answer,
            "logs": logs,
            "schemas": self.registry.get_schemas()
        }

if __name__ == "__main__":
    # 🧪 纯函数自测：类型映射 / Schema 生成 / 分发路由（不依赖网络与 API Key）
    print("--- 1. Python 类型 → JSON Schema 类型映射 ---")
    print("int ->", python_type_to_json_type(int))
    print("float ->", python_type_to_json_type(float))
    print("bool ->", python_type_to_json_type(bool))
    print("list ->", python_type_to_json_type(list))
    print("dict ->", python_type_to_json_type(dict))
    print("str ->", python_type_to_json_type(str))

    print("\n--- 2. @tool Schema 生成自测 ---")
    schemas = registry.get_schemas()
    calc_schema = next(s for s in schemas if s["function"]["name"] == "calculate_salary")
    user_schema = next(s for s in schemas if s["function"]["name"] == "get_user_info")
    print("calculate_salary 必填参数（tax_rate 带默认值不纳入）:", calc_schema["function"]["parameters"]["required"])
    print("get_user_info 必填参数:", user_schema["function"]["parameters"]["required"])

    print("\n--- 3. 分发路由自测 (Dispatch Map) ---")
    print(registry.dispatch("get_user_info", {"user_id": 101}))
    print(registry.dispatch("calculate_salary", {"base": 20000, "bonus": 5000}))
    print(registry.dispatch("unknown_tool", {}))
    print(registry.dispatch("calculate_salary", {"base": "不是数字", "bonus": 5000}))  # 类型错误 -> 异常捕获

    print("\n--- 4. 真实 Function Calling 测试 (需 API Key) ---")
    client = ZhipuGLMClient()
    agent = FunctionCallingAgent(client, registry)
    res = agent.chat_with_tools("请查询用户 102 的基本信息，并帮他计算基本工资 20000 加上奖金 5000 的税后收入（税率 15%）")
    print("最终回答:\n", res["answer"])
    print("工具调用记录:\n", json.dumps(res["logs"], ensure_ascii=False, indent=2))
