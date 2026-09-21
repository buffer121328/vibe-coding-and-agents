import os

# 可选：自动加载项目根目录的 .env 文件（需要 pip install python-dotenv）
# 没装 dotenv 也不影响运行 —— 环境变量照常从系统读取
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from langchain_community.tools import TavilySearchResults
from langchain_openai import ChatOpenAI

# 推荐使用环境变量管理敏感信息（参见根目录 .env.example），避免硬编码在代码中
# 注意：model 与 base_url 必须配套 —— 默认给出一套自洽的 OpenAI 官方配置。
# 如果你要切换到 Claude / DeepSeek / Qwen 等兼容 OpenAI 协议的服务，
# 请同时设置 OPENAI_MODEL_NAME 和 OPENAI_API_BASE 两个变量（详见 .env.example 注释）
llm = ChatOpenAI(
    temperature=0,
    model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
    api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here"),
    base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
)

# 全网搜索工具（可选）：没配、空着、或仍是模板占位符，都跳过初始化，主流程不受影响。
# 以前只认 "your-tavily-api-key-here" 这一种占位，.env.example 里的 "tvly-xxxx"
# 会被当成真 Key，启动就去连 Tavily。
_TAVILY_UNSET = {"", "your-tavily-api-key-here", "tvly-xxxx"}
tavily_api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
tavily_tool = None
if tavily_api_key not in _TAVILY_UNSET:
    os.environ["TAVILY_API_KEY"] = tavily_api_key
    tavily_tool = TavilySearchResults(max_results=1)
