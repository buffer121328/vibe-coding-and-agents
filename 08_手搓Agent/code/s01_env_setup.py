"""
s01_env_setup.py - 8.1 环境基建与模型接入（主力智谱 glm-5.3-flash + 火山方舟 deepseek-v4-flash 跨厂商灾备）
"""
import os
from typing import Generator, Dict, Any, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class ZhipuGLMClient:
    """🚀 双引擎高可用客户端封装器：主力智谱 GLM-5.3-Flash + 火山方舟 DeepSeek-V4-Flash 灾备（底层基于 OpenAI 兼容协议）

    主力引擎：智谱 GLM-5.3-Flash（默认 ZHIPU_MODEL，1M 上下文，超低成本）
    灾备引擎：火山方舟 DeepSeek-V4-Flash（默认 ARK_FALLBACK_MODEL，跨厂商无缝降级）

    主力引擎超时或异常时，可自动降级至火山方舟灾备引擎，保障 Agent 任务持续稳定。
    """
    def __init__(
        self,
        api_key: Optional[str] = None,                 # 智谱 API Key（默认读取 ZHIPU_API_KEY，兼容旧 KEY 变量）
        base_url: Optional[str] = None,                # 智谱 API 网关（默认读取 ZHIPU_BASE_URL）
        default_model: Optional[str] = None,           # 首选模型名称（默认读取 ZHIPU_MODEL）
        fallback_api_key: Optional[str] = None,        # 灾备引擎 Key（默认读取 ARK_API_KEY）
        fallback_base_url: Optional[str] = None,       # 灾备引擎网关（默认读取 ARK_BASE_URL）
        fallback_model: Optional[str] = None,          # 灾备模型名称（默认读取 ARK_FALLBACK_MODEL）
        timeout: float = 60.0,                         # 超时时间（秒）
    ):
        self.timeout = float(timeout or os.getenv("TIMEOUT_SECONDS", "60"))

        # —— 首选模型配置 ——
        self.api_key = (
            api_key 
            or os.getenv("ZHIPU_API_KEY") 
            or os.getenv("MIMO_API_KEY") 
            or os.getenv("ARK_API_KEY", "")
        )
        self.base_url = (
            base_url 
            or os.getenv("ZHIPU_BASE_URL") 
            or "https://open.bigmodel.cn/api/paas/v4/"
        )
        self.default_model = (
            default_model 
            or os.getenv("ZHIPU_MODEL") 
            or os.getenv("ZHIPU_MODEL_ENDPOINT") 
            or "glm-5.3-flash"
        )

        # —— 灾备引擎配置（默认：火山方舟 DeepSeek-V4-Flash 跨厂商降级）——
        self.fallback_api_key = (
            fallback_api_key
            or os.getenv("ARK_FALLBACK_API_KEY")
            or os.getenv("ARK_API_KEY")
            or self.api_key
        )
        self.fallback_base_url = (
            fallback_base_url
            or os.getenv("ARK_FALLBACK_BASE_URL")
            or os.getenv("ARK_BASE_URL")
            or self.base_url
        )
        self.fallback_model = (
            fallback_model
            or os.getenv("ARK_FALLBACK_MODEL")
            or os.getenv("ZHIPU_FALLBACK_MODEL")
            or "deepseek-v4-flash"
        )

        self._init_clients()

    def _init_clients(self):
        """🔧 初始化客户端实例"""
        self.client = None
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=2,
            )
        self.fallback_client = None
        if self.fallback_api_key:
            self.fallback_client = OpenAI(
                api_key=self.fallback_api_key,
                base_url=self.fallback_base_url,
                timeout=self.timeout,
                max_retries=2,
            )

    def update_config(
        self,
        api_key: str,
        endpoint: Optional[str] = None,
        base_url: Optional[str] = None,
        fallback_api_key: Optional[str] = None,
        fallback_endpoint: Optional[str] = None,
        fallback_base_url: Optional[str] = None,
    ):
        """⚙️ 动态更新配置（供 Web UI 交互使用）"""
        if api_key:
            self.api_key = api_key.strip()
        if endpoint:
            self.default_model = endpoint.strip()
        if base_url:
            self.base_url = base_url.strip()
        if fallback_api_key is not None:
            self.fallback_api_key = fallback_api_key.strip()
        if fallback_endpoint is not None:
            self.fallback_model = fallback_endpoint.strip()
        if fallback_base_url is not None:
            self.fallback_base_url = fallback_base_url.strip()
        self._init_clients()

    @staticmethod
    def parse_usage(response) -> Dict[str, Any]:
        """🧮 解析响应 usage：token 消耗 + 上下文缓存命中统计

        智谱上下文缓存为自动隐式生效，命中量读取 usage.prompt_tokens_details.cached_tokens；
        流式响应中 usage 只出现在最后一个 chunk（需 stream_options.include_usage=True）。
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        total = getattr(usage, "total_tokens", 0) or 0
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details:
            cached = getattr(details, "cached_tokens", 0) or 0
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "cached_tokens": cached,
            "cache_hit_rate": round(cached / prompt * 100, 2) if prompt else 0.0,
        }

    def _log_usage(self, response, model: str):
        """🪵 打印 token 消耗与缓存命中率"""
        u = self.parse_usage(response)
        if not u:
            return
        print(
            f"📊 Token 消耗 [{model}] 输入 {u['prompt_tokens']} / 输出 {u['completion_tokens']} / 总计 {u['total_tokens']}"
            f" | 缓存命中 {u['cached_tokens']}（命中率 {u['cache_hit_rate']}%）"
        )

    def _build_chat_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Optional[str],
        response_format: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
        reasoning_effort: Optional[str] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        include_usage: bool = True,
    ) -> Any:
        """🔧 组装 Chat Completions 请求参数（含 GLM 专属扩展字段）"""
        kwargs: Any = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens                  # 限制输出长度，防止模型无上限生成导致超时/卡死
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if response_format:
            kwargs["response_format"] = response_format            # 结构化输出: {"type": "json_object"}
        extra_body: Dict[str, Any] = {}
        if thinking is not None:
            extra_body["thinking"] = thinking                      # 思考模式: {"type": "enabled", "clear_thinking": False}
        if reasoning_effort:
            extra_body["reasoning_effort"] = reasoning_effort      # 思考等级: low / high / max (GLM-5.3)
        if extra_body:
            kwargs["extra_body"] = extra_body                      # GLM 专属参数需走 extra_body
        if stream:
            kwargs["stream"] = True
            if include_usage:
                kwargs["stream_options"] = {"include_usage": True} # 让流式末尾 chunk 带回 usage
        return kwargs

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model_endpoint: Optional[str] = None,
        temperature: float = 0.6,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        response_format: Optional[Dict[str, Any]] = None,
        thinking: Optional[Dict[str, Any]] = None,
        reasoning_effort: Optional[str] = None,
        max_tokens: Optional[int] = None,
        show_usage: bool = True,
    ) -> Any:
        """💬 标准同步对话（支持工具调用 / 结构化输出 / 思考模式 / Token 统计）"""
        target_model = model_endpoint or self.default_model

        if not self.client:
            raise ValueError("❌ 未配置 ZHIPU_API_KEY！请在 .env 文件中设置或通过界面输入。")

        try:
            kwargs = self._build_chat_kwargs(
                target_model, messages, temperature, tools, tool_choice,
                response_format=response_format, thinking=thinking,
                reasoning_effort=reasoning_effort, max_tokens=max_tokens,
            )
            resp = self.client.chat.completions.create(**kwargs)
            if show_usage:
                self._log_usage(resp, target_model)
            return resp
        except Exception as e:
            print(f"⚠️ 主力引擎 ({target_model}) 调用失败: {e}")
            if self.fallback_client and self.fallback_model and self.fallback_model != target_model:
                try:
                    print(f"🔄 正在自动降级至灾备引擎 ({self.fallback_model})...")
                    kwargs = self._build_chat_kwargs(
                        self.fallback_model, messages, temperature, tools, tool_choice,
                        response_format=response_format, thinking=thinking,
                        reasoning_effort=reasoning_effort, max_tokens=max_tokens,
                    )
                    resp = self.fallback_client.chat.completions.create(**kwargs)
                    if show_usage:
                        self._log_usage(resp, self.fallback_model)
                    return resp
                except Exception as fallback_err:
                    raise RuntimeError(f"❌ 灾备引擎也调用失败: {fallback_err}") from e
            raise e

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model_endpoint: Optional[str] = None,
        temperature: float = 0.6,
        thinking: Optional[Dict[str, Any]] = None,
        reasoning_effort: Optional[str] = None,
        include_usage: bool = True,
    ) -> Generator[str, None, None]:
        """🔤 流式打字机输出（逐字吐出正文，末尾自动打印 Token/缓存统计）"""
        target_model = model_endpoint or self.default_model

        if not self.client:
            raise ValueError("❌ 未配置 ZHIPU_API_KEY！请在 .env 文件中设置或通过界面输入。")

        try:
            kwargs = self._build_chat_kwargs(
                target_model, messages, temperature, None, None,
                thinking=thinking, reasoning_effort=reasoning_effort,
                stream=True, include_usage=include_usage,
            )
            stream = self.client.chat.completions.create(**kwargs)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                elif include_usage and getattr(chunk, "usage", None):
                    self._log_usage(chunk, target_model)   # 最后一个 chunk 携带 usage
            return
        except Exception as e:
            print(f"⚠️ 主力引擎流式调用异常: {e}")
            if self.fallback_client and self.fallback_model and self.fallback_model != target_model:
                print(f"🔄 切换到灾备引擎 ({self.fallback_model}) 流式输出...")
                kwargs["model"] = self.fallback_model
                stream = self.fallback_client.chat.completions.create(**kwargs)
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                    elif include_usage and getattr(chunk, "usage", None):
                        self._log_usage(chunk, self.fallback_model)
                return
            raise e

# 保持向后兼容性别名
ArkDeepSeekClient = ZhipuGLMClient

if __name__ == "__main__":
    client = ZhipuGLMClient()
    print(f"正在测试智谱 BigModel 连接 (主力模型: {client.default_model} → Base URL: {client.base_url})")
    print(f"灾备引擎: {client.fallback_model} → Base URL: {client.fallback_base_url}")
    try:
        res = client.chat([{"role": "user", "content": "你好，请用一句话介绍你自己"}])
        print("回复:", res.choices[0].message.content)
    except Exception as e:
        print("自测提醒 (若未配置Key属正常):", e)

    print("\n--- 流式打字机测试 (需 API Key) ---")
    try:
        print("流式回复:", end=" ", flush=True)
        for piece in client.chat_stream([{"role": "user", "content": "用一句话介绍你自己"}]):
            print(piece, end="", flush=True)
        print()
    except Exception as e:
        print("自测提醒 (若未配置Key属正常):", e)
