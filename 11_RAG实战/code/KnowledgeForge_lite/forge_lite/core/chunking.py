"""chunking.py —— 切块：结构感知 + 表格整块保留（教程 11.4）。

蒸馏来源：完整版 workflow 的切块阶段 + LangChain 的几种 splitter 取舍。
对应教程：11.2（迟切块/上下文头）、11.4（切块策略怎么选）。

Lite 的切块比"按字数递归切"多做两件事，都是**先读懂结构再下刀**：

1. **按标题切**：制度文件天然有层级（第 X 条 → 一、 → （一））。按层级切出来的块
   各自属于一个小节，再把「《文件名》 › 第 X 条」这条路径拼在每块前面——
   切块脱离原文后，"这块讲的是哪一条"就丢了，而这条线索只要几行代码就能补回来。
   这是 11.2 讲的"迟切块"的退化路径：不调模型，零成本。
2. **表格不切碎**：``表格行: 一线城市 | 500 元`` 这种行被打散到两个块里，
   「500 元」就和它的城市名分了家；检索命中「500」时看不到它是哪个档位的。
   所以表格行是**不可分割的最小单位**，超长表格只在行与行之间切，且每块补上表头。

不做什么：不改 ``CHUNK_SIZE`` 的语义（它仍是"每块最多多少字"，只是下刀位置变聪明了），
也不引入 ParentDocumentRetriever——那是 11.4 的进阶，需要多存一层父块索引，
课堂版先把"结构感知"这条主线走通。
"""

from __future__ import annotations

import re

# 切块策略版本。**改了本文件的切块行为就把它加一**——它不是文档，是开关：
# config.INDEX_SCHEMA 由它拼出来，版本一变，全库的 `unchanged` 判定整体失效，
# 下次入库会把所有文档重新切、重新嵌入。
#
# 为什么要这么设计：切块策略改了但没人记得手动改版本号，增量同步就会认为
# "内容哈希没变，跳过"——于是 BM25 语料用新切法、向量库还留着旧切块的向量，
# 两路索引对"一块是什么"的理解不一致。这比索引过期更糟：它不报错，只是悄悄不匹配。
# 把版本号放在切块代码旁边，改的人顺手就改了，不必记得另一个文件里还有个常量。
CHUNKER_VERSION = "structure-v1"

# Markdown 标题：`#` 到 `######`
_HEADING_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# 中文层级标题。三档，深度递增：
#   第X章 / 第X节   → 深度 1
#   第X条           → 深度 2
#   一、            → 深度 3
#   （一）          → 深度 4
# 不要求文档是 Markdown——制度文件本来就是这么排版的，Word 转出来也是这样。
_HEADING_CN = (
    (1, re.compile(r"^(第[一二三四五六七八九十百零〇]+[章节])\s*(.*)$")),
    (2, re.compile(r"^(第[一二三四五六七八九十百零〇]+条)\s*(.*)$")),
    (3, re.compile(r"^([一二三四五六七八九十]+、)\s*(.*)$")),
    (4, re.compile(r"^(（[一二三四五六七八九十]+）)\s*(.*)$")),
)
# 表格行：docx 走 ``_table_line`` 产出 ``表格行: …``，HTML 走 ``|`` 分隔
_TABLE_ROW = re.compile(r"^\s*(?:表格行:|[^|\n]*\|[^|\n]*)")


def is_table_row(line: str) -> bool:
    """这一行是不是表格行。

    ``line`` 是正文的一行。判据两条：显式的 ``表格行:`` 前缀（docx 解析器加的），
    或者行内有 ``|`` 分隔符（HTML 表格转出来的形状）。

    只看有没有 ``|`` 会把"用竖线排版"的普通文本误判成表格——但那种写法在制度文件里
    基本只出现在表格上，误判的代价（少切一刀）远小于漏判（把表格拦腰截断）。
    """
    return bool(_TABLE_ROW.match(line))


def heading_of(line: str) -> tuple[int, str] | None:
    """这一行是不是标题；是的话返回 ``(深度, 标题文本)``，不是返回 ``None``。

    ``line`` 是正文的一行。深度从 1 开始，数字越大层级越深。

    Markdown 的 ``#`` 直接把个数当深度；中文那几种按"章 → 条 → 一、 → （一）"
    排深度，两套混用时按深度对齐，不要求文档只用一种写法。
    """
    md = _HEADING_MD.match(line)
    if md:
        return len(md.group(1)), md.group(2).strip()
    for depth, pattern in _HEADING_CN:
        match = pattern.match(line.strip())
        if match:
            title = " ".join(part for part in match.groups() if part).strip()
            if title:
                return depth, title
    return None


def _sections(text: str) -> list[tuple[list[str], str]]:
    """把正文按标题切成小节，返回 ``[(标题路径, 正文)]``。

    ``text`` 是清洗后的正文。

    标题本身**留在正文里**——它是这一节的第一行，检索时"第 X 条"这几个字也该被搜到。
    路径只用来给块补上下文，不替代正文。

    没有标题的正文算一节，路径为空列表。
    """
    stack: list[tuple[int, str]] = []      # (深度, 标题)
    body: list[str] = []
    sections: list[tuple[list[str], str]] = []

    def flush() -> None:
        """把攒下的行收成一小节。没有参数——它闭包读 ``body`` 与 ``stack``。"""
        if body:
            sections.append(([title for _depth, title in stack], "\n".join(body)))
            body.clear()

    for line in (text or "").splitlines():
        found = heading_of(line)
        if found is None:
            body.append(line)
            continue
        flush()
        depth, title = found
        # 同级或更浅的标题把栈里比它深的都弹掉，保证路径是一条合法的祖先链
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, title))
        body.append(line)
    flush()
    return sections


def _segments(body: str) -> list[tuple[str, list[str]]]:
    """把一节正文拆成"可自由切的文字"和"不可拆的表格"两类片段，保持原顺序。

    ``body`` 是一节的正文。返回 ``[("text", [行…]) | ("table", [行…])]``。

    相邻的表格行合成一个片段，所以一张表是一整段，切的时候要么整段留在一块里，
    要么只在行与行之间下刀——绝不会从某一行中间断开。
    """
    segments: list[tuple[str, list[str]]] = []
    buffer: list[str] = []
    kind = "text"

    def flush() -> None:
        """把攒下的同类行收成一个片段。没有参数——它闭包读 ``buffer`` 与 ``kind``。"""
        if buffer:
            segments.append((kind, list(buffer)))
            buffer.clear()

    for line in (body or "").splitlines():
        line_kind = "table" if is_table_row(line) else "text"
        if line_kind != kind:
            flush()
            kind = line_kind
        buffer.append(line)
    flush()
    return segments


def _split_table(rows: list[str], chunk_size: int) -> list[str]:
    """把一张表按行切成若干块，每块都带上表头。

    ``rows`` 是表格行的列表（第一行通常是表头）；``chunk_size`` 是每块的字数上限。

    表头复制的理由：一块只剩数据行、没有表头，读者（和人）就看不出「500」是哪一列。
    返回块文本列表；表格本身不超限时原样返回一条。
    """
    if not rows:
        return []
    header = rows[0] if is_table_row(rows[0]) else ""
    # 表头看起来不像表头（比如整张表没有表头行）就不复制，免得把数据行重复一遍
    body_rows = rows[1:] if header else rows

    blocks: list[str] = []
    current: list[str] = []
    size = len(header) if header else 0
    for row in body_rows:
        if current and size + len(row) + 1 > chunk_size:
            blocks.append("\n".join(([header] if header else []) + current))
            current, size = [], len(header) if header else 0
        current.append(row)
        size += len(row) + 1
    if current:
        blocks.append("\n".join(([header] if header else []) + current))
    return blocks


def chunk_document(
    text: str,
    source_name: str,
    chunk_size: int,
    chunk_overlap: int,
    splitter=None,
) -> list[dict]:
    """把一篇文档切成块，每块带自己的标题路径。

    ``text`` 是清洗后的正文；``source_name`` 是文件名，用来拼上下文头；
    ``chunk_size`` / ``chunk_overlap`` 是字数旋钮（索引时旋钮，改完要重建索引）；
    ``splitter`` 是可选的递归切块器，不传就现建一个——测试传假的进来可以绕开依赖。

    返回 ``[{"text": 带上下文头的块正文, "heading": 标题路径}]``：

    - ``text`` 的形状是 ``《文件名》 › 第 X 条\\n\\n正文``。文件名给"这是哪篇"，
      标题路径给"这篇的哪一条"——两者都是切块脱离原文后最容易丢的线索，而补它们是零成本的；
    - ``heading`` 单独留一份，文档区的切块预览和评测都能拿去解释"这块从哪来"。

    表格行整段不切（见 ``_split_table``）；文字部分交给递归切块器，它按
    ``\\n\\n → \\n → 。 → ，`` 的顺序下刀，尽量落在句边界上。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if splitter is None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )

    stem = source_name.rsplit(".", 1)[0]
    header = f"《{stem}》"
    chunks: list[dict] = []

    for raw_path, body in _sections(text):
        # 一级标题常常就是文件名（`# 员工差旅管理制度（2026 修订版）`），
        # 留着会让上下文头变成「《员工差旅管理制度》 › 员工差旅管理制度（2026 修订版）」
        # ——同一件事说两遍，白占预算还稀释真正有信息量的那条路径。
        path = list(raw_path)
        while path and (path[0] in stem or stem in path[0]):
            path.pop(0)

        # 上下文头的第二段：标题路径。没有标题就只留《文件名》
        prefix = header + (" › " + " › ".join(path) if path else "")
        heading = " › ".join(path)

        for kind, lines in _segments(body):
            pieces = (_split_table(lines, chunk_size) if kind == "table"
                      else [piece for piece in splitter.split_text("\n".join(lines)) if piece.strip()])
            for piece in pieces:
                if not piece.strip():
                    continue
                chunks.append({"text": f"{prefix}\n\n{piece}", "heading": heading})

    if not chunks:
        # 正文全是空白（或在清洗后什么都不剩）：留一块空的会把"入库成功但零内容"
        # 伪装成正常结果，这里返回空列表让上游如实报 0 块。
        return []
    return chunks
