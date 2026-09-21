"""离线走查测试：四段讲稿必须能跑完，且断言与工牌规则一致。不调模型、不联网。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.service.demo import (  # noqa: E402
    print_acl_matrix,
    print_evidence,
    print_graph_and_audit,
    print_sessions,
    run_all,
)


class Collector:
    def __init__(self):
        self.lines = []

    def __call__(self, text):
        self.lines.append(str(text))

    @property
    def text(self):
        return "\n".join(self.lines)


class AclSectionTests(unittest.TestCase):
    def test_matrix_section_reports_all_consistent(self):
        sink = Collector()
        mismatches = print_acl_matrix(sink)
        self.assertEqual(mismatches, [])
        self.assertIn("全部一致", sink.text)
        self.assertIn("财务", sink.text)

    def test_admin_row_prints_no_filter_note(self):
        sink = Collector()
        print_acl_matrix(sink)
        self.assertIn("不过滤部门", sink.text)


class EvidenceSectionTests(unittest.TestCase):
    def test_conflict_and_empty_cases_are_blocked(self):
        sink = Collector()
        print_evidence(sink)
        text = sink.text
        self.assertIn("证据冲突", text)
        self.assertIn("拦截，不生成", text)
        self.assertIn("放行生成", text)
        self.assertIn("zero_results", text)


class SessionSectionTests(unittest.TestCase):
    def test_sessions_survive_reopen_and_reject_foreign_badge(self):
        with tempfile.TemporaryDirectory() as tmp:
            sink = Collector()
            print_sessions(sink, tmp_root=tmp)
        text = sink.text
        self.assertIn("IT 员工看到 1 格", text)
        self.assertIn("人事员工看到 0 格", text)
        self.assertIn("人事读取被拒", text)
        self.assertIn("# 去上海出差住一晚能报多少？", text)


class GraphSectionTests(unittest.TestCase):
    """图谱这段要证明的是"换工牌就换可见的边"，而不是某个具体的条数。

    条数取决于图存储里有多少三元组——种子垫底是 6 条，跑过 ``05_build_graph.py``
    之后是模型抽出来的几十条。断言写死数字，会让"图变丰富了"这种好事把测试弄红。
    所以这里断言的是**关系**：裁掉的条数因工牌而异，且密级那条事实只在有权限的牌下出现。
    """

    def test_badge_changes_visible_edges(self):
        sink = Collector()
        print_graph_and_audit(sink)
        text = sink.text
        self.assertIn("IT 员工：可见邻接", text)
        self.assertIn("财务负责人：可见邻接", text)
        self.assertIn("被工牌裁掉", text)
        # 权限差异：IT 员工看不到财务密级那条事实，财务负责人看得到
        it_line = next(ln for ln in text.splitlines() if ln.startswith("  IT 员工：可见邻接"))
        finance_line = next(ln for ln in text.splitlines() if ln.startswith("  财务负责人：可见邻接"))
        self.assertNotEqual(it_line, finance_line, "两张工牌看到的边不该一样")
        self.assertIn("P6薪酬带宽 --年薪为--> 35万至45万元", text)


class RunAllTests(unittest.TestCase):
    def test_run_all_returns_summary_and_prints_sections(self):
        sink = Collector()
        with tempfile.TemporaryDirectory() as tmp:
            import forge_lite.service.demo as demo
            original = demo.print_sessions

            def scoped(emit=print, tmp_root=None):
                return original(emit, tmp_root=tmp)

            demo.print_sessions = scoped
            try:
                summary = run_all(sink)
            finally:
                demo.print_sessions = original
        self.assertEqual(summary["acl_mismatches"], [])
        for marker in ("① 工牌先裁可见范围", "② 生成前先给证据打资格", "③ 会话柜", "④ 图谱作为第三路召回"):
            self.assertIn(marker, sink.text)
        self.assertIn("走查结束", sink.text)


if __name__ == "__main__":
    unittest.main()
