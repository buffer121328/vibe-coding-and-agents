"""config.py —— 全局配置。

蒸馏来源：完整版 shared/config + infrastructure 配置装配。
对应教程：11.13（服务化配置管理）。旋钮分三类：
- 索引时旋钮（CHUNK_* / EMBED_MODEL）改完必须重建索引；
- 检索时旋钮（TOP_K / RRF_K / CONTEXT_BUDGET / ENABLE_REWRITE / ENABLE_GRAPH）改完立即生效；
- 评测旋钮（JUDGE_MAX_TOKENS / JUDGE_RELEVANCY_STRICTNESS / PASS_RATE_GATE）只影响打分与门禁，不碰检索链路；
- 思考旋钮（THINKING_MODE）同时作用于问答生成和 Ragas 裁判。课堂默认关掉思考——裁判要快和稳，不需要推理链。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# 密钥与端点一律走 .env（教程 11.13：真实配置不进代码、不进镜像）
# 兼容两个位置：本目录（docker compose 也从这里读）或上一级 code/ 目录
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")
DOCS_DIR = BASE_DIR / "data" / "docs"           # 种子知识库（象征性文档）
RUNTIME_DIR = BASE_DIR / "runtime"              # 一切运行产物都落在这里（已 gitignore）
CHROMA_DIR = RUNTIME_DIR / "chroma"             # 向量库持久化目录
CHUNKS_JSON = RUNTIME_DIR / "chunks.json"       # BM25 语料（与向量库同源）
DOCSTORE_JSON = RUNTIME_DIR / "docstore.json"   # 内容哈希账本（增量同步用，11.13）
CONVERSATIONS_DB = RUNTIME_DIR / "conversations.sqlite"  # 会话柜：刷新不丢，按工牌隔离
TENANT_ID = os.getenv("FORGE_LITE_TENANT", "lite")  # 课堂单租户；完整版按公司拆库

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY") or os.getenv("MIMO_API_KEY") or ""
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL") or os.getenv("ARK_BASE_URL") or os.getenv("MIMO_BASE_URL") or ""

CHAT_MODEL = os.getenv("FORGE_LITE_CHAT_MODEL") or os.getenv("CHAT_MODEL") or os.getenv("MIMO_MODEL") or "gpt-4o-mini"
EMBED_MODEL = os.getenv("FORGE_LITE_EMBED_MODEL") or os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small"

# 对话模型和它的端点必须成对，否则会出现「拿 A 家的模型名去请求 B 家的端点」这种
# 静默错配：报错只说「模型不支持」，不会说端点配错了（11.13 配置漂移的典型）。
# 规则见 resolve_chat_endpoint：模型来自 MIMO_* 时，端点与密钥也跟着走 MIMO_*。
def resolve_chat_endpoint(
    forge_model: str | None,
    generic_model: str | None,
    mimo_model: str | None,
    forge_base: str | None,
    forge_key: str | None,
    generic_base: str | None,
    generic_key: str | None,
    mimo_base: str | None,
    mimo_key: str | None,
) -> tuple[str, str]:
    """决定对话该用哪个端点，把「模型名」和「端点 + 密钥」绑成一对返回。显式 FORGE_LITE_CHAT_* 永远优先。

    这条纪律的由来：模型名取自一处、端点取自另一处，是「配了却用不对」的
    头号来源——错误表现为模型不支持，实际错在端点。成对解析，不留交叉。

    九个参数按「三家来源 × 模型/端点/密钥」摆开，三家的优先级从高到低：
    ``forge_*``（``FORGE_LITE_CHAT_*``，点名要用的那一路）> ``mimo_*``
    （MiMo，课程默认的首选）> ``generic_*``（通用 OpenAI 兼容通道，方舟 DeepSeek
    这类备选走这里）。

    - ``forge_model`` 是显式指定的对话模型名；``forge_base`` 是它的端点地址，
      ``forge_key`` 是它的密钥。只要 ``forge_base`` / ``forge_key`` 里任意一个非空，
      就按「显式赢」这一档处理。
    - ``generic_model`` 是通用通道的模型名（如 ``gpt-4o-mini``、方舟的 deepseek 型号）；
      ``generic_base`` / ``generic_key`` 是它的端点和密钥，也就是回落的兜底。
    - ``mimo_model`` 是 MiMo 的模型名；``mimo_base`` / ``mimo_key`` 是 MiMo 的端点和密钥。
      它单独一个名字的意义在于：只有「配了 MiMo 模型、又没配另外两家的模型名」时，
      端点与密钥才跟着 MiMo 走——否则就成了拿 MiMo 的模型名去请求方舟端点。

    返回 ``(base, key)`` 二元组，两者永远同源；三家都没配时返回 ``("", "")``，
    交给上层去报「没配模型」，而不是在这里抛异常（导入 config 就崩会连没 Key
    的离线走查都跑不起来）。注意把模型名和端点一起看：模型取自 MIMO_* 时，
    端点与密钥也必须跟着走 MIMO_*。
    """
    if forge_base or forge_key:
        return (
            forge_base or (mimo_base if mimo_model and not forge_model and not generic_model else generic_base) or "",
            forge_key or (mimo_key if mimo_model and not forge_model and not generic_model else generic_key) or "",
        )
    if mimo_model and not forge_model and not generic_model:
        return (mimo_base or generic_base or "", mimo_key or generic_key or "")
    return (generic_base or "", generic_key or "")


CHAT_API_BASE, CHAT_API_KEY = resolve_chat_endpoint(
    os.getenv("FORGE_LITE_CHAT_MODEL"),
    os.getenv("CHAT_MODEL"),
    os.getenv("MIMO_MODEL"),
    os.getenv("FORGE_LITE_CHAT_BASE"),
    os.getenv("FORGE_LITE_CHAT_KEY"),
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    os.getenv("MIMO_BASE_URL"),
    os.getenv("MIMO_API_KEY"),
)

CHUNK_SIZE = int(os.getenv("FORGE_LITE_CHUNK_SIZE", "400"))
CHUNK_OVERLAP = int(os.getenv("FORGE_LITE_CHUNK_OVERLAP", "60"))
TOP_K = int(os.getenv("FORGE_LITE_TOP_K", "6"))
RRF_K = int(os.getenv("FORGE_LITE_RRF_K", "60"))          # RRF 融合常数（11.5）
CONTEXT_BUDGET = int(os.getenv("FORGE_LITE_CONTEXT_BUDGET", "1800"))  # 喂给模型的字符预算（11.5）
ENABLE_REWRITE = os.getenv("FORGE_LITE_ENABLE_REWRITE", "1").strip().lower() not in {"0", "false", "no"}
ENABLE_GRAPH = os.getenv("FORGE_LITE_ENABLE_GRAPH", "1").strip().lower() not in {"0", "false", "no"}
DEFAULT_USER_ID = os.getenv("FORGE_LITE_USER", "it_staff")  # 演示工牌，见 identity.USERS
EMBED_BATCH_SIZE = int(os.getenv("FORGE_LITE_EMBED_BATCH", "10"))  # 方舟等端点单次最多 10 条
PASS_RATE_GATE = float(os.getenv("FORGE_LITE_PASS_RATE", "0.8"))  # 11.9 回归门禁
# 思考模式：蒸馏自完整版 ``LLM_THINKING_MODE``。MiMo 默认开隐性思考，
# reasoning_tokens 计入 completion，一条裁判可能要几分钟。检索问答按提示词
# 走路就行，裁判更只要快和稳——所以课堂默认关掉。
# 取值 ``disabled`` / ``default``（跟随厂商）；也认完整版那个环境变量名。
_THINKING_RAW = (
    os.getenv("FORGE_LITE_THINKING_MODE")
    or os.getenv("LLM_THINKING_MODE")
    or "disabled"
).strip().lower()
THINKING_MODE = _THINKING_RAW if _THINKING_RAW in {"disabled", "default"} else "disabled"
# Ragas 裁判单次生成的上限。ragas 默认 1024，会被裁判的结构化输出撑爆
# （IncompleteOutputException）。关思考之后额度主要给 JSON 答案，8192 仍留着
# 防截断；真要开思考再靠它兜推理 token。
JUDGE_MAX_TOKENS = int(os.getenv("FORGE_LITE_JUDGE_MAX_TOKENS", "8192"))
# AnswerRelevancy 内部会按 strictness 连问几次「这个问题还能怎么问」。
# 官方默认 3，课堂默认 1：裁判如果是推理模型，三次就是三倍墙钟。
# 要更稳的分数再调回 3（``FORGE_LITE_JUDGE_RELEVANCY_STRICTNESS``）。
JUDGE_RELEVANCY_STRICTNESS = max(1, min(5, int(os.getenv("FORGE_LITE_JUDGE_RELEVANCY_STRICTNESS", "1"))))


def thinking_extra_body() -> dict:
    """MiMo 关思考时要塞进请求体的那一截，开着就返回空字典。

    没有参数。完整版写在 ``qa_dependencies._generation_model_kwargs``：
    ``extra_body={"thinking": {"type": "disabled"}}``。ChatOpenAI 和 ragas 的
    ``llm_factory`` 都认 ``extra_body``，原样透给 OpenAI 兼容端点。
    ``default`` 模式不传这个字段，跟着厂商走（MiMo 默认开思考）。
    返回的是一份新字典，调用方可以直接 ``**`` 展开。
    """
    if THINKING_MODE == "disabled":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}


# 索引形状版本：它标记"这份索引是怎么造出来的"，由各零件的版本拼成，而不是手写一个数字。
# 已收进来的两轴：
#   acl-v2        部门/密级元数据（11.13）
#   CHUNKER_VERSION  切块策略（11.4，见 chunking.py）
# 任何一轴变了，INDEX_SCHEMA 就变，全库增量同步会判定为过期并重建（11.13）。
# 评价里那个"内容哈希没变就跳过"的快路径，前提正是"造索引的方法也没变"。
from .core.chunking import CHUNKER_VERSION

INDEX_SCHEMA = f"acl-v2+{CHUNKER_VERSION}"
