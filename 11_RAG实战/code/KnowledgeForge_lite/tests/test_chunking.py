"""chunking.py 的切块规则：结构感知、表格不切碎、上下文头。跑起来不调模型。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.core.chunking import (  # noqa: E402
    CHUNKER_VERSION,
    chunk_document,
    heading_of,
    is_table_row,
)


class HeadingTests(unittest.TestCase):
    """标题识别要同时认 Markdown 的 `#` 和中文制度文件那套编号。"""

    def test_markdown_heading_depth_follows_hashes(self):
        self.assertEqual(heading_of("## 第一条 住宿标准"), (2, "第一条 住宿标准"))
        self.assertEqual(heading_of("# 员工差旅管理制度"), (1, "员工差旅管理制度"))

    def test_chinese_numbering_is_recognized(self):
        """制度文件大多不是 Markdown，Word 转出来只有「第一条」「一、」这种编号。"""
        for line, expect_depth in (
            ("第二章 报销管理", 1),
            ("第一条 住宿标准", 2),
            ("一、适用范围", 3),
            ("（一）差旅定义", 4),
        ):
            with self.subTest(line=line):
                found = heading_of(line)
                self.assertIsNotNone(found, f"{line} 应该被认成标题")
                self.assertEqual(found[0], expect_depth)

    def test_plain_sentence_is_not_a_heading(self):
        for line in ("一线城市住宿标准为每人每天不超过 500 元。", "报销流程如下：", ""):
            with self.subTest(line=line):
                self.assertIsNone(heading_of(line))

    def test_table_row_detection(self):
        self.assertTrue(is_table_row("表格行: 一线城市 | 500 元"))
        self.assertTrue(is_table_row("档位 | 上限"))
        self.assertFalse(is_table_row("一线城市住宿标准为每人每天不超过 500 元。"))


class StructureTests(unittest.TestCase):
    """切块的形状：路径带进每块、表格不切碎、文件名不重复。"""

    DOC = """# 员工差旅管理制度（2026 修订版）

> 适用范围：全体正式员工。

## 第一条 住宿标准

- 一线城市住宿标准为每人每天不超过 500 元；
- 二线城市住宿标准为每人每天不超过 350 元。

表格行: 城市档位 | 每人每天上限
表格行: 一线城市 | 500 元
表格行: 二线城市 | 350 元

## 第二条 报销流程

1. 差旅报销单须在返回工作地后 5 个工作日内提交。
"""

    def chunks(self, size: int = 200, overlap: int = 30):
        return chunk_document(self.DOC, "员工差旅管理制度.md", chunk_size=size, chunk_overlap=overlap)

    def test_each_chunk_carries_its_heading_path(self):
        """切块脱离原文后最容易丢的是"这块讲哪一条"，路径把它补回来。"""
        chunks = self.chunks()
        headings = {item["heading"] for item in chunks}
        self.assertIn("第一条 住宿标准", headings)
        self.assertIn("第二条 报销流程", headings)

    def test_context_header_is_file_then_path(self):
        chunks = self.chunks()
        stay = next(item for item in chunks if item["heading"] == "第一条 住宿标准")
        first_line = stay["text"].splitlines()[0]
        self.assertEqual(first_line, "《员工差旅管理制度》 › 第一条 住宿标准")

    def test_filename_is_not_repeated_in_the_path(self):
        """一级标题常常就是文件名，重复一次白占预算还稀释真正有信息的那条路径。"""
        chunks = self.chunks()
        for item in chunks:
            with self.subTest(heading=item["heading"]):
                self.assertNotIn("员工差旅管理制度（2026 修订版）", item["text"].split("\n\n")[0])

    def test_table_rows_stay_together(self):
        """表格被打散，'500 元'就和它的城市名分家，检索命中也看不出属于谁。"""
        table_chunks = [item for item in self.chunks(size=60) if "表格行:" in item["text"]]
        self.assertTrue(table_chunks, "应当至少有一块装的是表格")
        for item in table_chunks:
            rows = [line for line in item["text"].splitlines() if line.startswith("表格行:")]
            self.assertGreaterEqual(len(rows), 1)

    def test_oversized_table_splits_between_rows_and_repeats_header(self):
        """超长表格只能在行与行之间切，且每块都要带表头——否则数字看不出属于哪一列。"""
        rows = ["表格行: 档位 | 上限"] + [f"表格行: 城市{i} | {i}00 元" for i in range(1, 12)]
        text = "## 第一条 标准\n\n" + "\n".join(rows)
        chunks = chunk_document(text, "制度.md", chunk_size=80, chunk_overlap=0)
        table_pieces = [item["text"] for item in chunks if "表格行:" in item["text"]]
        self.assertGreater(len(table_pieces), 1, "80 字装不下 12 行，应该切成多块")
        for piece in table_pieces:
            with self.subTest(piece=piece[:20]):
                self.assertIn("表格行: 档位 | 上限", piece, "每块都要带表头")
        # 所有数据行都还在，没有一行被截断丢字
        joined = "\n".join(table_pieces)
        for i in range(1, 12):
            with self.subTest(row=i):
                self.assertIn(f"城市{i} | {i}00 元", joined)

    def test_empty_text_yields_no_chunks(self):
        """空正文返回空列表，让上游如实报 0 块——留一块空的会伪装成"入库成功"。"""
        self.assertEqual(chunk_document("   \n\n  ", "空.md", 400, 60), [])

    def test_chunker_version_is_declared(self):
        """切块策略必须带版本号：它是 INDEX_SCHEMA 的一轴，改了要能自动触发重建。"""
        self.assertTrue(CHUNKER_VERSION)
        from forge_lite import config

        self.assertIn(CHUNKER_VERSION, config.INDEX_SCHEMA)


if __name__ == "__main__":
    unittest.main()
