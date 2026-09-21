"""课堂证据资格：空库拒答、数字冲突、高风险转人工、部分证据才许生成。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.core.evidence import (  # noqa: E402
    STATUS_ANSWERED,
    STATUS_CONFLICT,
    STATUS_INSUFFICIENT,
    STATUS_REVIEW,
    STATUS_UNAVAILABLE,
    EvidencePolicy,
    coverage,
    has_material_conflict,
    qualify,
    split_routes,
    status_label,
)


TRAVEL = {
    "source": "员工差旅管理制度.md",
    "chunk_index": 0,
    "text": "一线城市住宿标准为每人每天不超过 500 元。返回后 5 个工作日内提交报销单。",
}
PAY = {
    "source": "财务薪酬密级.md",
    "chunk_index": 0,
    "text": "P6 薪酬带宽年薪为 35 万至 45 万元。",
}
FAQ = {
    "source": "产品FAQ.md",
    "chunk_index": 0,
    "text": "Forge 免费版每月 100 次问答、500 条文档切块。",
}
CONFLICTING_CAP = {
    "source": "差旅旧版.md",
    "chunk_index": 0,
    "text": "一线城市住宿标准为每人每天不超过 300 元。",
}


class EvidenceQualifierTests(unittest.TestCase):
    def test_empty_is_insufficient_not_an_outage(self):
        assessment = qualify("住宿上限？", [])
        self.assertEqual(assessment.response_status, STATUS_INSUFFICIENT)
        self.assertFalse(assessment.allows_generation())

    def test_all_branches_down_is_unavailable(self):
        assessment = qualify("住宿上限？", [], {"bm25": "unavailable", "dense": "unavailable", "graph": "unavailable"})
        self.assertEqual(assessment.response_status, STATUS_UNAVAILABLE)

    def test_direct_travel_cap_allows_generation(self):
        assessment = qualify("去上海出差住一晚住宿费上限是多少？", [TRAVEL])
        self.assertTrue(assessment.allows_generation())
        self.assertIn(assessment.response_status, {STATUS_ANSWERED, "partially_answered"})
        self.assertTrue(assessment.supporting_ids)

    def test_amount_conflict_stops_automatic_answer(self):
        self.assertTrue(has_material_conflict("住宿上限是多少元？", [TRAVEL, CONFLICTING_CAP]))
        assessment = qualify("一线城市住宿上限是多少元？", [TRAVEL, CONFLICTING_CAP])
        self.assertEqual(assessment.response_status, STATUS_CONFLICT)
        self.assertFalse(assessment.allows_generation())

    def test_high_risk_conflict_requires_review(self):
        other = {"source": "薪酬口传.md", "chunk_index": 0, "text": "P6 薪酬带宽年薪为 80 万元。"}
        assessment = qualify("P6 薪酬带宽是多少？", [PAY, other])
        self.assertEqual(assessment.response_status, STATUS_REVIEW)

    def test_missing_amount_in_chunk_is_capped(self):
        fluffy = {"source": "员工差旅管理制度.md", "chunk_index": 1,
                  "text": "差旅要节约，住宿应当符合标准，具体见财务另行通知。"}
        assessment = qualify("住宿上限是多少元？", [fluffy])
        self.assertFalse(assessment.allows_generation() and assessment.response_status == STATUS_ANSWERED)

    def test_provenance_missing_source_is_invalid(self):
        assessment = qualify("额度？", [{"source": "", "chunk_index": 0, "text": "每月 100 次"}])
        self.assertFalse(assessment.allows_generation())

    def test_coverage_is_token_overlap(self):
        score = coverage("住宿 上限 500 元", TRAVEL["text"])
        self.assertGreater(score, 0.3)

    def test_split_routes_deduplicates(self):
        chips = split_routes("bm25+dense+graph+bm25")
        self.assertEqual([item["id"] for item in chips], ["bm25", "dense", "graph"])
        self.assertEqual(status_label("refuse"), "已拒答")

    def test_policy_rejects_unsorted_thresholds(self):
        with self.assertRaises(ValueError):
            EvidencePolicy(background_threshold=0.8, gray_zone_lower=0.2,
                           gray_zone_upper=0.3, direct_threshold=0.4)

    def test_faq_quota_is_answerable(self):
        assessment = qualify("Forge 免费版每月有多少次问答额度？", [FAQ])
        self.assertTrue(assessment.allows_generation())

    def test_printer_e3_is_answerable(self):
        """黄金集 printer-e3：资料写着处理步骤，资格必须放行，不能把锅甩给模型分级。"""
        printer = {
            "source": "运维故障案例.md",
            "chunk_index": 0,
            "text": "办公区打印机面板显示 E3，无法打印。关闭电源，打开后盖取出卡纸；"
                    "检查进纸传感器是否复位；重新上电，若仍报 E3，联系行政部报修。",
        }
        assessment = qualify("打印机显示 E3 怎么处理？", [printer])
        self.assertTrue(assessment.allows_generation())


if __name__ == "__main__":
    unittest.main()
