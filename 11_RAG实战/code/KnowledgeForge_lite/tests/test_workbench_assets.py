"""工作台资产契约：页面 DOM、JS 行为、CSS 设计 token 三者必须对得上。"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.contracts import API_PATHS, DOM_IDS  # noqa: E402
from forge_lite.web.pages import render_chat_page  # noqa: E402


STATIC = ROOT / "forge_lite" / "web" / "static"
CSS = "\n".join(path.read_text(encoding="utf-8") for path in sorted(STATIC.glob("*.css")))
JS = "\n".join(path.read_text(encoding="utf-8") for path in sorted(STATIC.glob("*.js")))
WORKBENCH_JS = (STATIC / "workbench.js").read_text(encoding="utf-8")
HTML = str(render_chat_page())


class DomContractTests(unittest.TestCase):
    def test_every_contract_id_exists_in_page(self):
        for key, value in DOM_IDS.items():
            with self.subTest(key=key):
                self.assertIn(f'id="{value}"', HTML)

    def test_every_contract_id_is_used_by_js(self):
        for key, value in DOM_IDS.items():
            with self.subTest(key=key):
                self.assertTrue(
                    f'"{value}"' in JS or f"'{value}'" in JS or f'("{value}")' in JS,
                    f"JS 没有引用 {value}",
                )

    def test_page_has_shell_and_three_views(self):
        for token in ("shell", "sider", "header", "content"):
            with self.subTest(token=token):
                self.assertTrue(
                    re.search(rf'class="[^"]*\b{token}\b[^"]*"', HTML),
                    f"页面缺少 {token} 外壳",
                )
        for view in ("view-qa", "view-docs", "view-eval"):
            with self.subTest(view=view):
                self.assertIn(f'id="{view}"', HTML)

    def test_page_marks_badge_label(self):
        self.assertIn("演示工牌", HTML)


class JsBehaviourTests(unittest.TestCase):
    def test_calls_every_read_endpoint(self):
        for key in ("conversations", "catalog", "chunks", "graph", "prompts", "health"):
            path = API_PATHS[key].replace("{conversation_id}", "").replace("{run_id}", "")
            with self.subTest(path=path):
                self.assertIn(path.split("?")[0], JS)

    def test_calls_trace_endpoint(self):
        self.assertIn("/trace", JS)

    def test_export_uses_filename_header(self):
        self.assertIn("Content-Disposition", JS)
        self.assertIn("download", JS)

    def test_stores_only_pointer_and_badge(self):
        self.assertIn('const KEY_USER = "forge-lite-user"', JS)
        self.assertIn('const KEY_CONV = "forge-lite-conv"', JS)
        touched = re.findall(r"localStorage\.(?:setItem|removeItem)\(([^,)]+)", JS)
        self.assertEqual({item.strip() for item in touched}, {"KEY_USER", "KEY_CONV"})

    def test_render_answer_uses_text_content(self):
        self.assertIn("document.createTextNode", JS)
        # 只查真正的赋值用法；注释里提到 innerHTML 不算
        self.assertIsNone(re.search(r"\.innerHTML\s*=", JS))
        self.assertIsNone(re.search(r"insertAdjacentHTML", JS))

    def test_keeps_original_query_visible_via_queries_list(self):
        self.assertIn("trace.queries", JS)

    def test_no_third_party_framework_import(self):
        for forbidden in ("react", "vue", "jquery", "cdn.jsdelivr"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, JS.lower())


class ConsoleViewTests(unittest.TestCase):
    """控制台三视图：文档区（含切块实验台）与评测区。"""

    def test_chunk_text_wraps(self):
        """档案正文很长，pre 默认不换行会被抽屉裁掉——这条是那个 bug 的回归。"""
        self.assertIn(".chunk-text", CSS)
        block = CSS.split(".chunk-text", 1)[1].split("}", 1)[0]
        self.assertIn("pre-wrap", block)
        self.assertIn("overflow-wrap: anywhere", block)

    def test_lab_panel_is_wired(self):
        self.assertIn('class="card-body lab"', HTML)
        for token in ("lab-text", "lab-size", "lab-overlap", "lab-apply", "lab-reset", "lab-chunks"):
            with self.subTest(token=token):
                self.assertIn(f'id="{token}"', HTML)
                self.assertIn(f'"{token}"', JS)

    def test_lab_marks_overlap_visibly(self):
        """重叠是切块最该被看见的事，样式上要能标出来。"""
        self.assertIn("chunk-hit", JS)
        self.assertIn(".chunk-hit", CSS)
        self.assertIn("overlapLength", JS)

    def test_eval_view_has_no_raw_markdown(self):
        """页面上不该出现没渲染的 ** —— 导语是纯文本节点，星号会原样显示出来。"""
        for match in re.findall(r"[\u4e00-\u9fff][^<>\n]{0,40}\*\*", HTML):
            with self.subTest(fragment=match):
                self.fail(f"正文里有未渲染的 Markdown 标记：{match}")


class ConsoleConsistencyTests(unittest.TestCase):
    """控制台与完整版共用一套界面语言：标签、两行首列、描边标签、抽屉。"""

    def test_status_is_a_tag_not_a_pill(self):
        """完整版的状态用 antd Tag（描边小标签），Lite 照做——旧的圆角胶囊已退场。"""
        self.assertNotIn('"pill ', JS)
        self.assertIn(".tag", CSS)
        self.assertIn("is-ok", CSS)
        self.assertIn("border-radius: 4px", CSS)

    def test_table_first_column_is_two_line(self):
        """完整版表格首列是「名称 + 来源」两行，Lite 的登记号也走同一条副行。"""
        self.assertIn("cell-name", JS)
        self.assertIn("cell-meta", JS)
        self.assertIn(".cell-name", CSS)
        self.assertIn(".cell-meta", CSS)

    def test_quarantine_signals_are_a_disclosure_row(self):
        """计数留在条目上，清单点开才展开。"""
        self.assertIn("signalRow", JS)
        self.assertIn("disclosure", JS)
        self.assertIn('setAttribute("aria-expanded"', JS)
        self.assertIn(".sub-row", CSS)

    def test_drawer_is_the_detail_surface(self):
        """完整版用 Drawer 看分块与用例详情，Lite 用同一套。"""
        for name in ("qa", "docs", "eval"):
            with self.subTest(name=name):
                self.assertIn(f'id="{name}-drawer"', HTML)
        self.assertIn(".drawer-body", CSS)
        self.assertIn("openDrawer", JS)

    def test_pending_cells_are_muted(self):
        """还没跑出来的破折号不该和真实数据一样响。"""
        self.assertIn("is-pending", JS)
        self.assertIn(".is-pending", CSS)

    def test_view_switch_uses_is_on_not_hidden_alone(self):
        """[hidden] 会被 .qa 这类带 display 的规则盖掉，视图切换必须靠 .is-on。"""
        self.assertIn(".view { display: none", CSS)
        self.assertIn(".view.is-on", CSS)
        self.assertIn(".view[hidden] { display: none", CSS)


class BadgeSyncTests(unittest.TestCase):
    """控制台视图与工牌架是两个独立闭包，工牌必须由一处广播、两边对齐。

    曾经的真 bug：管理员刷新页面后，头部显示「公司管理员」，文档区却说
    「当前工牌：IT 员工」并锁着——因为工作台记得 localStorage 里的牌，
    控制台却自己写死 it_staff，谁也没告诉它。
    """

    def test_workbench_announces_settled_badge(self):
        """工作台在 /whoami 校验完工牌之后必须广播一次最终身份。"""
        boot = WORKBENCH_JS.split("async function boot()", 1)[1]
        announce = boot.find('dispatchEvent(new CustomEvent("forge:badge-changed"')
        settle = boot.find("renderRack()")
        self.assertGreater(announce, -1, "boot 里没有广播最终工牌，控制台会一直按默认牌走")
        self.assertGreater(announce, settle, "广播必须发生在工牌定下来之后")

    def test_console_listener_is_idempotent(self):
        """控制台收到同一张牌时不该白白重载。"""
        listener = JS.split('addEventListener("forge:badge-changed"', 1)[1].split("});", 1)[0]
        self.assertIn("next === state.userId", listener)

    def test_console_drops_stale_responses(self):
        """换牌连发两次请求，先回来的可能是旧牌——过期结果必须丢掉。"""
        self.assertIn("docsSeq", JS)
        self.assertIn("evalSeq", JS)


class CssTokenTests(unittest.TestCase):
    def test_palette_tokens_match_the_full_version(self):
        """Lite 的配色必须和完整版 frontend/src/main.tsx 的 antd theme 一致。"""
        for token, value in (
            ("--primary", "#155eef"),
            ("--success", "#17b26a"),
            ("--warning", "#f79009"),
            ("--error", "#f04438"),
            ("--canvas", "#f5f7fa"),
            ("--border-2", "#eaecf0"),
            ("--text", "#101828"),
            ("--sider", "#101828"),
        ):
            with self.subTest(token=token):
                self.assertIn(f"{token}: {value}", CSS)
        self.assertIn("--r: 8px", CSS)
        self.assertIn("--r-lg: 12px", CSS)

    def test_motion_is_short_and_respects_reduced_motion(self):
        self.assertIn("prefers-reduced-motion", CSS)

    def test_focus_visible_is_themed(self):
        self.assertIn(":focus-visible", CSS)

    def test_responsive_breakpoint_switches_to_drawer_nav(self):
        """窄屏把侧边栏改成抽屉，和完整版 Sider/Drawer 的切换同一个断点。"""
        self.assertIn("@media (max-width: 991px)", CSS)
        self.assertIn("translateX(-100%)", CSS)
        self.assertIn("is-nav-open", CSS)

    def test_no_mvp_css_import(self):
        self.assertNotIn("mvp.css", HTML)
        self.assertNotIn("mvp.css", CSS)

    def test_external_fonts_are_https(self):
        for match in re.findall(r"https?://[^\"')\s]+", HTML):
            with self.subTest(url=match):
                self.assertTrue(match.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
