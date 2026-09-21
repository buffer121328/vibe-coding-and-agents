"""demo.py —— 无 API Key 的离线走查：把机器里「不用模型也能看见」的部分全展开。

蒸馏来源：完整版 README 的 quickstart 与评测对照。
对应教程：11.15。课堂常见尴尬：学生还没配好 Key，就先看不到任何效果。
这份走查把四块**确定性**能力摊开——不需要网络，也就能在课前一分钟验证装对了：

1. 工牌 × 文档的可见矩阵（谁看得见什么）；
2. 证据资格（哪块资料够答、哪块只配当背景、哪块冲突）；
3. 会话柜（写一格、读回来、换工牌打不开、导出 Markdown）；
4. 图谱邻接与审计账（第三路和事后翻账）。

跑法：``python scripts/06_demo.py``
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from ..data.acl_matrix import EXPECTED_MATRIX, assert_expected, matrix
from ..store.conversations import ConversationError, ConversationStore
from ..core.evidence import qualify, status_label
from .export import render_markdown
from .graph_view import neighborhood
from ..core.identity import USERS, resolve_actor
from ..core.labels import DEPARTMENT_LABELS, ROLE_LABELS, SENSITIVITY_LABELS


PRINTER = {"source": "运维故障案例.md", "chunk_index": 0,
           "text": "打印机显示 E3：关闭电源取出卡纸，检查进纸传感器复位后重新上电，仍报错找行政部报修。"}
TRAVEL = {"source": "员工差旅管理制度.md", "chunk_index": 0,
          "text": "一线城市住宿标准为每人每天不超过 500 元。返回工作地后 5 个工作日内提交报销单。"}
TRAVEL_OLD = {"source": "差旅旧版.md", "chunk_index": 0,
              "text": "一线城市住宿标准为每人每天不超过 300 元。"}
PAY = {"source": "财务薪酬密级.md", "chunk_index": 0,
       "text": "P6 薪酬带宽年薪为 35 万至 45 万元。"}
FLUFF = {"source": "员工差旅管理制度.md", "chunk_index": 1,
         "text": "差旅要厉行节约，住宿应当符合标准，具体口径见财务另行通知。"}


def _line(char: str = "─", width: int = 64) -> str:
    """画一条分隔线，长度固定好让板书对齐。

    ``char`` 是要重复的字符（默认细线 ``─``，大段之间用 ``═`` 区分层级），
    ``width`` 是重复几次（默认 64，按终端常见宽度留出的板书宽度）。返回拼好的字符串，
    不直接打印——打印交给上层走 ``emit``，这样测试才收得到。写成一个函数而不是到处写
    ``"─" * 64``，是为了让所有段落的宽度只在这一处定义，改一处全篇对齐。
    """
    return char * width


def _title(text: str, emit: Callable[[str], None] = print) -> None:
    """打一段小标题，上下各一条双线。

    ``text`` 是标题正文（如「① 工牌先裁可见范围（11.13）」），``emit`` 是打印函数，
    默认内置 ``print``，测试传入收集器来抓输出。

    小标题也要走 ``emit``——测试和重定向才能收到，不能直接 print。
    """
    emit("")
    emit(_line("═"))
    emit(f"  {text}")
    emit(_line("═"))


def print_acl_matrix(emit: Callable[[str], None] = print) -> list[str]:
    """工牌 × 文档：把矩阵打成表格，顺手核对课堂标准答案。

    ``emit`` 是打印函数，默认内置 ``print``，测试传收集器来抓这四段板书的文字。

    返回 ``assert_expected`` 给出的不一致清单：空列表表示矩阵与课堂标准答案
    完全一致，非空则每条是一句「谁 × 哪篇：期望 vs 实际」的人话，可直接念给学生听。
    返回而不是在这里断言，是为了让 ``run_all`` 能把结论汇进摘要、测试能自己决定怎么用。
    """
    _title("① 工牌先裁可见范围（11.13）", emit)
    table = matrix()
    docs = sorted({doc for row in table.values() for doc in row})
    header = "工牌".ljust(14) + "".join(doc[:10].ljust(12) for doc in docs)
    emit(header)
    emit(_line())
    for user_id, row in table.items():
        actor = resolve_actor(user_id)
        cells = "".join(("可见" if row.get(doc) else "裁掉").ljust(12) for doc in docs)
        emit(f"{actor.display_name[:6].ljust(14)}{cells}")
    emit("")
    for actor in USERS.values():
        hidden = [doc for doc, seen in table[actor.user_id].items() if not seen]
        emit(
            f"  {actor.display_name}（{ROLE_LABELS.get(actor.role, actor.role)} / "
            f"{DEPARTMENT_LABELS.get(actor.department, actor.department)}）："
            + ("不过滤部门" if actor.visible_department_ids() is None else f"看不见 {len(hidden)} 篇")
        )
    mismatches = assert_expected(EXPECTED_MATRIX)
    emit("")
    emit(f"  矩阵与课堂标准答案比对：{'全部一致 ✅' if not mismatches else '❌ ' + '；'.join(mismatches)}")
    return mismatches


def print_evidence(emit: Callable[[str], None] = print) -> None:
    """证据资格：同一个问题喂不同的资料，看资格结论怎么变。

    ``emit`` 是打印函数，默认内置 ``print``。五个案例共用一套打印逻辑，
    讲课时改案例只改上面那张 tuple，不用动下半段——结论（放行 / 拦截）由
    ``qualify`` 现算，不写死在文案里，免得逻辑改了板书还印着旧结论。

    没有返回值：这一段只放映结论，需要断言的部分在 ``tests/test_demo_walkthrough.py``
    里另走一遍 ``qualify``。
    """
    _title("② 生成前先给证据打资格（11.8 / 11.12）", emit)
    cases = (
        ("差旅上限（资料齐全）", "去上海出差住一晚住宿费上限是多少？", [TRAVEL]),
        ("差旅上限（只有口风，没有数字）", "住宿上限是多少元？", [FLUFF]),
        ("差旅上限（两版数字打架）", "一线城市住宿上限是多少元？", [TRAVEL, TRAVEL_OLD]),
        ("薪酬带宽（高风险 + 冲突）", "P6 薪酬带宽是多少？", [PAY, {"source": "薪酬口传.md", "chunk_index": 0,
                                                                    "text": "P6 薪酬带宽年薪为 80 万元。"}]),
        ("库外问题（一条都没召到）", "公司年终奖一般发几个月工资？", []),
    )
    for label, question, chunks in cases:
        result = qualify(question, chunks)
        flag = "放行生成" if result.allows_generation() else "拦截，不生成"
        emit(f"  ▸ {label}")
        emit(f"      问题：{question}")
        emit(f"      结论：{status_label(result.response_status)}（{result.state}）→ {flag}"
             + (f"，覆盖率 {result.coverage:.2f}" if result.coverage else ""))
        if result.reason_codes:
            emit(f"      理由：{'、'.join(result.reason_codes)}")
        for slot in result.missing:
            emit(f"      缺：{slot.description}")
        emit("")


def print_sessions(emit: Callable[[str], None] = print, tmp_root: str | None = None) -> None:
    """会话柜：写一格、换工牌读不到、导出 Markdown。用临时库，不碰课堂 runtime。

    ``emit`` 是打印函数，默认内置 ``print``；``tmp_root`` 是放这个临时库的目录，
    传 None（默认）就现开一个 ``mkdtemp`` 并在这段走查结束时删掉，传了路径就原地保留
    ——测试要靠它去翻库文件，课前走查则不该在机器上留垃圾。

    没有返回值：它演示的是「关掉再打开，会话还在」这条行为，输出本身就是结论。
    """
    _title("③ 会话柜：刷新不丢，工牌隔离（11.13）", emit)
    root = Path(tmp_root) if tmp_root else Path(tempfile.mkdtemp())
    store = ConversationStore(root / "demo_conversations.sqlite")
    conv_id, run_id = store.record_answer("it_staff", "去上海出差住一晚能报多少？", {
        "answer": "一线城市住宿上限 500 元 [1]。",
        "status": "ok",
        "intent": "factoid",
        "routes": "bm25+dense+graph",
        "warn": "",
        "citations": [{"marker": "[1]", "doc_id": "员工差旅管理制度.md#0"}],
        "contexts": ["一线城市住宿标准为每人每天不超过 500 元。"],
        "queries": ["去上海出差住一晚能报多少？"],
        "actor": {"user_id": "it_staff", "name": "IT 员工", "role": "employee", "department": "it"},
    })
    emit(f"  写入一格：{conv_id}（run {run_id}）")
    emit(f"  关闭再打开同一库文件……")
    store.close()
    reopened = ConversationStore(root / "demo_conversations.sqlite")
    page = reopened.list_conversations("it_staff")
    emit(f"  IT 员工看到 {len(page.items)} 格：{page.items[0].title if page.items else '（空）'}")
    hr_page = reopened.list_conversations("hr_staff")
    emit(f"  人事员工看到 {len(hr_page.items)} 格 —— 指针不是权限")
    try:
        reopened.get_conversation(conv_id, "hr_staff")
        emit("  ❌ 人事居然打开了 IT 的会话")
    except ConversationError as exc:
        emit(f"  人事读取被拒：{exc}")
    markdown = render_markdown(reopened.get_conversation(conv_id, "it_staff"))
    first_lines = [line for line in markdown.splitlines() if line.strip()][:3]
    emit("  导出 Markdown 前三行：")
    for line in first_lines:
        emit(f"      {line}")
    reopened.close()
    if tmp_root is None:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def print_graph_and_audit(emit: Callable[[str], None] = print) -> None:
    """图谱邻接：同一句问，换工牌看到的边数不一样。

    ``emit`` 是打印函数，默认内置 ``print``。三张工牌各查一次「P6薪酬带宽」，
    边数随工牌变而变——这一段的看点正是「图没变，视野变了」，所以先把
    被裁掉的条数也印出来，而不是只报可见的那几条。

    没有返回值：它只放映对比，断言在 ``tests/test_demo_walkthrough.py``。
    """
    _title("④ 图谱作为第三路召回（11.7）", emit)
    for user_id in ("it_staff", "finance_head", "admin"):
        actor = resolve_actor(user_id)
        view = neighborhood("P6薪酬带宽", user_id)
        emit(f"  {actor.display_name}：可见邻接 {len(view.edges)} 条，被工牌裁掉 {view.hidden} 条")
        for edge in view.edges[:3]:
            emit(f"      {edge.head} --{edge.relation}--> {edge.tail}（{edge.source}）")
    finance = neighborhood("一线城市住宿标准", "hr_staff")
    emit(f"  人事查「一线城市住宿标准」：{len(finance.edges)} 条（公司公开事实，人人可见）")


def run_all(emit: Callable[[str], None] = print) -> dict[str, object]:
    """一次跑完四段走查，返回结果摘要，供测试断言。

    ``emit`` 是打印函数，默认内置 ``print``；四段各自还会再收到一次，由它们自己
    继续往下传，所以这里传同一次就会串成一份完整板书。

    返回 ``{"acl_mismatches": [...]}``：只有工牌矩阵这一段有可判定的对错，
    值就是 ``print_acl_matrix`` 给的不一致清单（空列表 = 全过），其余三段是演示
    性质，结论在输出里而不在返回值里。
    """
    emit("KnowledgeForge Lite 离线走查（不需要 API Key / 不访问网络）")
    mismatches = print_acl_matrix(emit)
    print_evidence(emit)
    print_sessions(emit)
    print_graph_and_audit(emit)
    emit("")
    emit(_line("═"))
    emit("  走查结束：以上四段全部离线复现；需要模型的部分（作答质量）交给 Ragas 评测。")
    emit(_line("═"))
    return {"acl_mismatches": mismatches}


if __name__ == "__main__":
    run_all()
