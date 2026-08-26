"""AI 能力服务：OpenAI 兼容接口封装（阶段七：智能摘要提炼与自动打标）

环境变量（全部在函数内动态读取，便于测试注入与热切换）：
    LLM_API_KEY    必填；未配置时 AI 能力整体禁用（博客主流程不受影响）
    LLM_BASE_URL   默认 https://api.deepseek.com，一行可切换其他兼容厂商
    LLM_MODEL      默认 deepseek-chat
"""
import json
import os

from openai import OpenAI

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

_client: OpenAI | None = None


def ai_enabled() -> bool:
    """未配置 LLM_API_KEY 时返回 False（优雅降级开关）"""
    return bool(os.getenv("LLM_API_KEY", ""))


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        )
    return _client


def provider_name() -> str:
    """根据 base_url 推断供应商名，用于 /api/ai/status 展示"""
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
    if "deepseek" in base_url:
        return "DeepSeek"
    if "openai" in base_url:
        return "OpenAI"
    if "dashscope" in base_url or "aliyun" in base_url:
        return "通义千问"
    if "moonshot" in base_url:
        return "Moonshot"
    return base_url


def _chat_json(system: str, user: str) -> dict:
    """要求模型返回纯 JSON 对象；解析失败抛 ValueError，由上层兜底"""
    resp = get_client().chat.completions.create(
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    return json.loads(resp.choices[0].message.content)


def generate_all(title: str, content: str, category: str = "") -> dict:
    """一次性产出 {summary, tags, title_suggestion, category_suggestion}"""
    system = (
        "你是中文技术博客的编辑助手。严格只输出 JSON 对象，不要输出任何解释或 Markdown。"
        "字段说明："
        "summary：根据正文提炼约 100 字的中文导读（吸引读者、点明主旨，不含 HTML）；"
        "tags：根据正文内容提取 3~5 个标签，放入字符串数组；"
        "title_suggestion：一个更吸引人的标题；"
        "category_suggestion：一个合适的分类名。"
    )
    user = f"标题：{title}\n现有分类：{category}\n正文：\n{content[:4000]}"
    return _chat_json(system, user)
