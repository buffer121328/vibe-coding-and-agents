"""evaluate.py —— 按 Ragas 0.4 官方 collections API 做课堂评测，只留三个指标。

官方文档（[Ragas 0.4 · Faithfulness](https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/faithfulness/)、
[Context Recall](https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/context_recall/)、
[Answer Relevancy](https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/answer_relevance/)）：

新代码走 ``ragas.metrics.collections``，用 ``llm_factory`` + ``embedding_factory`` 建裁判，
再 ``await scorer.ascore(...)``。旧的 ``from ragas.metrics import faithfulness`` 已被官方弃用——
运行时会给一条 ``DeprecationWarning``，写明「v1.0 移除，请改用 ragas.metrics.collections」——
所以本模块只走 collections，也不再填 ``question/answer/contexts/ground_truth`` 那组旧列名。

样本字段（官方 ``SingleTurnSample`` schema）：

- ``user_input``          用户原问题
- ``retrieved_contexts``  检索到的资料原文列表
- ``response``            系统答案
- ``reference``           标准答案（ContextRecall 必填）

课堂只跑三个指标：

| 指标 | 官方类 | 管什么 |
| :--- | :--- | :--- |
| Faithfulness | ``ragas.metrics.collections.Faithfulness`` | 答案每个陈述能否在资料里找到依据 |
| ContextRecall | ``ragas.metrics.collections.ContextRecall`` | 标准答案里的要点，检索有没有召回来 |
| AnswerRelevancy | ``ragas.metrics.collections.AnswerRelevancy`` | 答案是不是在回答这个问题 |

评测默认 ``persist=False``，不往会话柜写黄金题。

**三件非默认配置**（缺哪件都跑不起来，都踩过）：

1. ``_patch_vertexai()``：ragas 0.4.3 的 ``ragas/llms/base.py`` 顶层 import 了
   ``langchain_community.chat_models.vertexai.ChatVertexAI``，而该类在 langchain-community
   0.4 已被移除（ragas 声明依赖时不带上界，pip 拦不住）。补个占位类兜住即可——
   它只在"把 langchain 模型对象包成 ragas LLM"的分支里做类型映射，我们走 ``llm_factory``
   那条路，用不到它。等 ragas 补上对 1.x 的支持后可以删掉这个函数。
2. ``_judge_clients()``：对话裁判与嵌入裁判**各认自己那一对端点**。把 ``CHAT_MODEL``
   递给 ``OPENAI_*`` 的客户端就是 ``config.resolve_chat_endpoint`` 专门要拦的那种交叉，
   实测会得到 404 UnsupportedModel。
3. ``config.JUDGE_MAX_TOKENS``：``llm_factory`` 默认 ``max_tokens=1024``，裁判的结构化输出会被
   截断（``IncompleteOutputException``）。官方源码注释给的解法就是显式加大。课堂 .env 里的
   对话模型默认会开隐性思考，推理 token 也吃这份额度。课堂默认关掉思考
   （``FORGE_LITE_THINKING_MODE=disabled``，与完整版 ``LLM_THINKING_MODE`` 同语义），
   额度主要留给 JSON 答案；真要开思考再用 ``FORGE_LITE_JUDGE_MAX_TOKENS`` 把上限加大。
   ``AnswerRelevancy`` 另有 ``strictness``：官方默认 3（连问三次），课堂默认 1
   （``FORGE_LITE_JUDGE_RELEVANCY_STRICTNESS``），免得一条用例把整轮评测拖成一小时。
"""

from __future__ import annotations

import asyncio
from typing import Iterator

from .. import config
from .agent import ask
from ..core.identity import resolve_actor


# 每条用例三件套：
# ``expect``        期望行为（answer / refuse）——评测区先看这一条对不对；
# ``expected_docs`` 期望召回的文件名——给 Hit / Recall / MRR 用，不依赖生成模型；
# ``reference``     标准答案（Ragas 的 ContextRecall / Faithfulness 用它）。
GOLDEN_SET = [
    {
        "id": "travel-cap",
        "question": "去上海出差住一晚住宿费上限是多少？",
        "reference": "一线城市住宿标准为每人每天不超过 500 元。",
        "expect": "answer",
        "expected_docs": ["员工差旅管理制度.md"],
        "user_id": "it_staff",
    },
    {
        "id": "travel-deadline",
        "question": "差旅报销单要在返回后几天内提交？",
        "reference": "返回工作地后 5 个工作日内提交 OA 系统。",
        "expect": "answer",
        "expected_docs": ["员工差旅管理制度.md"],
        "user_id": "it_staff",
    },
    {
        "id": "printer-e3",
        "question": "打印机显示 E3 怎么处理？",
        "reference": "关闭电源取出卡纸，检查进纸传感器复位后重新上电，仍报错找行政部报修。",
        "expect": "answer",
        "expected_docs": ["运维故障案例.md"],
        "user_id": "it_staff",
    },
    {
        "id": "faq-quota",
        "question": "Forge 免费版每月有多少次问答额度？",
        "reference": "免费版每月 100 次问答、500 条文档切块。",
        "expect": "answer",
        "expected_docs": ["产品FAQ.md"],
        "user_id": "hr_staff",
    },
    {
        "id": "out-of-library",
        "question": "公司年终奖一般发几个月工资？",
        "reference": "知识库中没有年终奖相关信息，系统应当拒答，不得编造月份。",
        "expect": "refuse",
        "expected_docs": [],
        "user_id": "it_staff",
    },
    {
        "id": "pay-band-employee",
        "question": "P6 薪酬带宽是多少？",
        "reference": "普通员工工牌看不到财务密级文档，系统应当拒答，不得泄露薪酬带宽。",
        "expect": "refuse",
        "expected_docs": [],
        "user_id": "it_staff",
    },
    {
        "id": "printer-e3-hr",
        "question": "打印机显示 E3 怎么处理？",
        "reference": "人事工牌看不见 IT 部门文档，系统应当拒答；换 IT 工牌才应作答。",
        "expect": "refuse",
        "expected_docs": [],
        "user_id": "hr_staff",
    },
    {
        "id": "pay-band-finance",
        "question": "P6 薪酬带宽是多少？",
        "reference": "财务负责人可见密级文档，应引用《财务薪酬密级》回答年薪区间。",
        "expect": "answer",
        "expected_docs": ["财务薪酬密级.md"],
        "user_id": "finance_head",
    },
]


def collect_samples(cases: list[dict] | None = None) -> list[dict]:
    """跑一遍问答，收成 Ragas 0.4 ``ascore`` 需要的字段。不落会话柜。

    ``cases`` 是要跑的用例列表，缺省用 ``GOLDEN_SET``；每项至少要有 ``question``
    和 ``reference``，可选的 ``user_id`` 决定这题用哪张工牌去问。``persist=False``
    是有意为之：黄金题是考题不是课堂对话，混进 runtime 的会话柜会让人分不清
    哪些是真人问过的。检索空手时塞一句「（无检索结果）」占位而不是留空列表——
    裁判看到空上下文会直接报错，而这里想要的是"这条拿 0 分"，不是整轮评测中断。

    返回行列表，字段为 ``user_input`` / ``retrieved_contexts`` / ``response`` /
    ``reference``，外加课堂自留的 ``user_id`` 与 ``status``（裁判不读这两个）。
    """
    rows = []
    for case in cases or GOLDEN_SET:
        actor = resolve_actor(case.get("user_id"))
        result = ask(case["question"], user_id=actor.user_id, persist=False)
        rows.append({
            "user_input": case["question"],
            "retrieved_contexts": result.get("contexts") or ["（无检索结果）"],
            "response": result.get("answer") or "",
            "reference": case["reference"],
            "user_id": actor.user_id,
            "status": result.get("status") or "",
        })
    return rows


def _patch_vertexai() -> None:
    """补上 ragas 顶层要 import、而 langchain-community 0.4 已删除的那个 VertexAI 类。

    没有参数，也不返回东西——它只往内存里的模块表塞一个占位模块，别的什么都不改。

    为什么需要：``ragas/llms/base.py`` 第 12 行硬 import 了
    ``langchain_community.chat_models.vertexai.ChatVertexAI``，而 langchain-community 0.4
    把这个模块移走了（这个包自己已进入 sunset）。ragas 声明依赖时不带上界，pip 拦不住，
    于是 ``import ragas`` 直接 ImportError。占位类足够用：那行 import 只服务于
    "把 langchain 模型对象包成 ragas LLM"的分支，而我们走 ``llm_factory``，从不经过它。
    （同文件第 13 行的 ``langchain_community.llms.VertexAI`` 在 0.4.2 里还在，不用补。）

    写在这里而不是往 site-packages 里塞文件，是为了让修复跟着仓库走：换台机器、
    重建 venv 之后它依然生效。缺 langchain_community 时静默返回——真缺依赖的话，
    紧接着的 ragas 导入会报出更准确的那个错。
    """
    import sys
    import types

    try:
        import langchain_community.chat_models as chat_models
    except ImportError:
        return

    if "langchain_community.chat_models.vertexai" in sys.modules:
        return

    module = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:
        """占位类：只为让 ragas 的顶层 import 通过，不参与任何真实调用。"""

    module.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = module
    # 挂到父包上，这样 `from langchain_community.chat_models import vertexai` 也能命中
    chat_models.vertexai = module


def _client(api_key: str | None, api_base: str | None):
    """按一对「密钥 + 端点」建 AsyncOpenAI，两者必须同源。

    ``api_key`` 是这一对里的密钥，空则填 ``sk-dummy``（构造函数不校验，但留空会直接抛错）；
    ``api_base`` 是这一对里的端点地址，空则交给 SDK 用官方默认端点。返回可交给 ragas
    那两个工厂的异步客户端——构造它不联网，所以这里不会因为密钥错而提前失败。
    """
    from openai import AsyncOpenAI

    kwargs = {"api_key": api_key or "sk-dummy"}
    if api_base:
        kwargs["base_url"] = api_base
    return AsyncOpenAI(**kwargs)


def _judge_clients() -> tuple:
    """建裁判要用的两个客户端，返回 ``(对话客户端, 嵌入客户端)``。

    没有参数（端点一律从 ``config`` 读）。分成两个而不是共用一个，是因为对话和嵌入
    可以来自不同厂商：对话走 ``CHAT_*``（与 ``llm.py`` 同一对），嵌入走 ``OPENAI_*``
    （与 ``data/ingest.py`` 同一对）。共用一个就会退化成"拿 A 家的模型名去请求 B 家的
    端点"——``config.resolve_chat_endpoint`` 存在的全部理由就是拦这个，实测报
    404 UnsupportedModel，而报错信息只说模型不支持，不会说端点配错了。
    """
    return (
        _client(config.CHAT_API_KEY, config.CHAT_API_BASE),
        _client(config.OPENAI_API_KEY, config.OPENAI_API_BASE),
    )


def _build_judges() -> tuple:
    """建三个裁判指标，返回 ``(faith, recall, relevancy)``。

    没有参数。缺 ragas 时抛 ``ImportError``（调用方翻译成一句人话），缺 Key 时会在
    真正打分那一步报鉴权错——客户端构造不联网，所以这里不提前判"有没有 Key"。
    ``AnswerRelevancy`` 要额外吃嵌入，用嵌入那一对端点；另两个只用对话端点。
    ``strictness`` 走 ``config.JUDGE_RELEVANCY_STRICTNESS``：官方默认 3，课堂默认 1，
    免得一条用例连问三次把整轮评测拖成一小时。
    思考模式跟问答同一把旋钮：``llm_factory`` 把 ``extra_body`` 透给 OpenAI 兼容端点，
    关思考之后裁判不再把额度花在 ``reasoning_content`` 上。
    """
    _patch_vertexai()
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, ContextRecall, Faithfulness

    chat_client, embed_client = _judge_clients()
    judge = llm_factory(
        config.CHAT_MODEL,
        client=chat_client,
        max_tokens=config.JUDGE_MAX_TOKENS,
        **config.thinking_extra_body(),
    )
    embeddings = embedding_factory("openai", model=config.EMBED_MODEL, client=embed_client)
    return (
        Faithfulness(llm=judge),
        ContextRecall(llm=judge),
        AnswerRelevancy(
            llm=judge,
            embeddings=embeddings,
            strictness=config.JUDGE_RELEVANCY_STRICTNESS,
        ),
    )


async def _score_rows(rows: list[dict]) -> list[dict]:
    """把样本逐条喂给三个裁判指标，返回带分数的行。

    做成 async 是因为 Ragas 0.4 的裁判只提供 ``ascore`` 异步接口，同步入口得由调用方
    用 ``asyncio.run`` 包一层。``rows`` 是 ``collect_samples`` 的产物（已含
    ``user_input`` / ``response`` / ``retrieved_contexts`` / ``reference``）。
    ragas 的导入刻意藏在 ``_build_judges`` 里而不是放模块顶层：没装裁判库时本模块
    仍要能被导入——门禁层评测根本不碰它，不该被它连累。

    返回新行列表，每行是原字段加上 ``faithfulness`` / ``context_recall`` /
    ``answer_relevancy`` 三个分数；用 ``getattr(..., "value", ...)`` 取分是为了
    同时兼容新旧版本返回的包装对象。
    """
    faith, recall, relevancy = _build_judges()

    scored = []
    for row in rows:
        faith_r = await faith.ascore(
            user_input=row["user_input"],
            response=row["response"],
            retrieved_contexts=row["retrieved_contexts"],
        )
        recall_r = await recall.ascore(
            user_input=row["user_input"],
            retrieved_contexts=row["retrieved_contexts"],
            reference=row["reference"],
        )
        relevancy_r = await relevancy.ascore(
            user_input=row["user_input"],
            response=row["response"],
        )
        scored.append({
            **row,
            "faithfulness": getattr(faith_r, "value", faith_r),
            "context_recall": getattr(recall_r, "value", recall_r),
            "answer_relevancy": getattr(relevancy_r, "value", relevancy_r),
        })
    return scored


def evaluate() -> list[dict] | None:
    """官方 0.4 入口：collections 指标 + ascore。缺依赖时打印安装提示。

    返回带三个分数的行列表；没装 ``ragas>=0.4`` 时只打印安装提示并返回 None——
    评测是加分项，不该因为课堂机器少装一个包就让整个项目导入不进来。
    """
    try:
        _patch_vertexai()
        from ragas.metrics.collections import Faithfulness  # noqa: F401
    except ImportError:
        print("[缺依赖] pip install 'ragas>=0.4.3' openai langchain-community")
        print("Lite 评测按 Ragas 0.4 collections API 编写，旧的 faithfulness 单例已被官方弃用（v1.0 移除）。")
        return None

    rows = collect_samples()
    print("\n=== KnowledgeForge Lite · Ragas 0.4 课堂评测 ===")
    print("指标：Faithfulness / ContextRecall / AnswerRelevancy")
    print("提示：这是体检层，要调裁判模型，八条黄金集可能要几十分钟。")
    print("      改完代码先跑 scripts/03_evaluate.py（门禁层，不调裁判）。")
    print("样本：")
    for row in rows:
        actor = resolve_actor(row["user_id"])
        print(f"  · [{actor.display_name}] {row['user_input']}  → {row['status']}")

    scored = asyncio.run(_score_rows(rows))
    print("\nuser_input                              faith  recall  relev")
    for row in scored:
        print(
            f"{row['user_input'][:36]:<36}  "
            f"{float(row['faithfulness']):.2f}   "
            f"{float(row['context_recall']):.2f}    "
            f"{float(row['answer_relevancy']):.2f}"
        )
    print(
        "\n怎么读："
        "context_recall 低 → 先修检索（工牌裁太狠 / 三路没召到）；"
        "faithfulness 低 → 先修生成（引用门禁或复检）；"
        "answer_relevancy 低 → 答案没对着问题讲。"
        "拒答题别当检索事故：裁判在给拒答话术打分，越权题的 context_recall 经常是 0——"
        "因为工牌 ACL 根本没让那篇文档进上下文。先看门禁层行为，再读这张表。"
        "\n文档：https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/"
    )
    return scored


# 兼容旧脚本名：04_ragas_eval.py 继续能跑。
ragas_evaluate = evaluate


if __name__ == "__main__":
    evaluate()


def iter_ragas(cases: list[dict] | None = None) -> Iterator[dict]:
    """逐条跑 Ragas 0.4 三个指标，边跑边吐——评测区的进度条靠它。

    ``cases`` 是要跑的用例（缺省用 ``GOLDEN_SET``），每条单独问答、单独打分，
    ``yield`` 出结果字典：``case_id`` / ``question`` / ``actor_name`` / ``status``
    加三个分数。每条各起一次 ``asyncio.run``、而不是攒成一批跑一个大循环，
    是因为生成器一 ``yield`` 就把控制权交回调用方，页面才能一条条刷新进度；
    攒批会把整轮评测变成一个不可见的长黑盒。

    需要 Key 与 ragas 0.4；缺哪个就抛哪个，交给上层如实报给页面，
    不要在这里吞掉异常假装"跑完了"。
    """
    faith, recall, relevancy = _build_judges()

    for case in cases if cases is not None else GOLDEN_SET:
        actor = resolve_actor(case.get("user_id"))
        result = ask(case["question"], user_id=actor.user_id, persist=False)
        contexts = result.get("contexts") or ["（无检索结果）"]
        response = result.get("answer") or ""
        faith_r = asyncio.run(faith.ascore(
            user_input=case["question"], response=response, retrieved_contexts=contexts))
        recall_r = asyncio.run(recall.ascore(
            user_input=case["question"], retrieved_contexts=contexts, reference=case["reference"]))
        relevancy_r = asyncio.run(relevancy.ascore(
            user_input=case["question"], response=response))
        yield {
            "case_id": case.get("id") or case["question"][:12],
            "question": case["question"],
            "actor_name": actor.display_name,
            "status": result.get("status") or "",
            "faithfulness": float(getattr(faith_r, "value", faith_r) or 0.0),
            "context_recall": float(getattr(recall_r, "value", recall_r) or 0.0),
            "answer_relevancy": float(getattr(relevancy_r, "value", relevancy_r) or 0.0),
        }
