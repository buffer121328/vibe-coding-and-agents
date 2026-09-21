"""证据资格矩阵：状态 × 高风险 × 降级 × 缺槽位，逐格断言。不调模型。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.core.evidence import (  # noqa: E402
    STATUS_ANSWERED,
    STATUS_CLARIFY,
    STATUS_CONFLICT,
    STATUS_INSUFFICIENT,
    STATUS_PARTIAL,
    STATUS_REVIEW,
    STATUS_UNAVAILABLE,
    EvidencePolicy,
    EvidenceQualifier,
    MissingSlot,
    is_high_risk,
    needs_clarification,
    status_label,
)


TRAVEL = {"source": "员工差旅管理制度.md", "chunk_index": 0,
          "text": "一线城市住宿标准为每人每天不超过 500 元。返回工作地后 5 个工作日内提交报销单。"}
FAQ = {"source": "产品FAQ.md", "chunk_index": 0,
       "text": "Forge 免费版每月 100 次问答、500 条文档切块。"}
SECRET = {"source": "财务薪酬密级.md", "chunk_index": 0,
          "text": "P6 薪酬带宽年薪为 35 万至 45 万元。"}
OTHER_PAY = {"source": "薪酬口传.md", "chunk_index": 0, "text": "P6 薪酬带宽年薪为 80 万元。"}
VERSION = {"source": "制度.md", "chunk_index": 0, "text": "现行版本为 2026 年 1 月生效。"}
NO_VERSION = {"source": "制度.md", "chunk_index": 0, "text": "报销流程须按公司规定执行。"}


class AllowMatrixTests(unittest.TestCase):
    CASES = (
        ("住宿上限问题 + 齐全资料", "去上海出差住一晚住宿费上限是多少？", [TRAVEL], True),
        ("FAQ 额度问题 + FAQ 资料", "Forge 免费版每月有多少次问答额度？", [FAQ], True),
        ("薪酬问题 + 密级资料（不冲突）", "P6 薪酬带宽是多少？", [SECRET], True),
        ("薪酬问题 + 两份矛盾", "P6 薪酬带宽是多少？", [SECRET, OTHER_PAY], False),
        ("没有候选", "公司年终奖一般发几个月工资？", [], False),
    )

    def test_allow_generation_matrix(self):
        for label, question, chunks, expected in self.CASES:
            with self.subTest(label=label):
                self.assertEqual(qualify_allows(question, chunks), expected)


def qualify_allows(question, chunks):
    return EvidenceQualifier().assess(question, chunks).allows_generation()


class RefusalReasonTests(unittest.TestCase):
    def test_zero_results_is_not_an_outage(self):
        result = EvidenceQualifier().assess("年终奖几个月？", [])
        self.assertEqual(result.response_status, STATUS_INSUFFICIENT)
        self.assertIn("zero_results", result.reason_codes)

    def test_partial_outage_is_recorded_on_full_answer(self):
        result = EvidenceQualifier().assess(
            "住宿上限是多少元？", [TRAVEL],
            {"bm25": "success", "dense": "success", "graph": "unavailable"},
        )
        self.assertTrue(result.allows_generation())
        self.assertIn("partial_dependency_unavailable", result.reason_codes)

    def test_invalid_provenance_when_source_missing(self):
        result = EvidenceQualifier().assess("额度？", [{"chunk_index": 0, "text": "每月 100 次"}])
        self.assertEqual(result.state, "invalid_provenance")
        self.assertIn("invalid_context_provenance", result.reason_codes)

    def test_high_risk_partial_goes_to_review(self):
        shrink = {"source": "员工差旅管理制度.md", "chunk_index": 2,
                  "text": "薪酬相关事项按公司薪酬制度执行，具体情况向人力咨询。"}
        result = EvidenceQualifier().assess("薪酬住宿补贴标准是多少元？", [shrink])
        self.assertIn(result.response_status, {STATUS_REVIEW, STATUS_INSUFFICIENT, STATUS_CONFLICT})
        self.assertFalse(result.allows_generation())

    def test_clarification_requested_when_version_unknown(self):
        self.assertTrue(needs_clarification("现行版本是哪一版？", NO_VERSION["text"]))
        self.assertFalse(needs_clarification("现行版本是哪一版？", VERSION["text"]))
        result = EvidenceQualifier().assess("现行版本是哪一版？", [NO_VERSION])
        self.assertEqual(result.response_status, STATUS_CLARIFY)

    def test_partial_evidence_lists_missing_slot(self):
        thin = {"source": "员工差旅管理制度.md", "chunk_index": 3,
                "text": "报销单须在返回工作地后按时提交，具体时限见差旅制度。"}
        result = EvidenceQualifier().assess("差旅报销单要在返回后几天内提交？", [thin])
        if result.response_status == STATUS_PARTIAL:
            self.assertTrue(result.missing)
            self.assertEqual(result.missing[0].field, "unsupported_question_parts")


class PolicyTests(unittest.TestCase):
    def test_thresholds_must_be_ordered(self):
        with self.assertRaises(ValueError):
            EvidencePolicy(background_threshold=0.9, gray_zone_lower=0.1,
                           gray_zone_upper=0.2, direct_threshold=0.3)

    def test_thresholds_must_be_probabilities(self):
        with self.assertRaises(ValueError):
            EvidencePolicy(direct_threshold=1.5)

    def test_candidate_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            EvidencePolicy(candidate_limit=0)
        with self.assertRaises(ValueError):
            EvidencePolicy(candidate_limit=51)

    def test_assessment_carries_policy_version(self):
        result = EvidenceQualifier().assess("住宿上限？", [TRAVEL])
        self.assertTrue(result.policy_version)
        self.assertTrue(result.calibration_version)

    def test_high_risk_marker_table(self):
        self.assertTrue(is_high_risk("P6 薪酬带宽是多少？"))
        self.assertFalse(is_high_risk("去上海出差住一晚能报多少？"))

    def test_status_labels_cover_every_state(self):
        for status in (STATUS_ANSWERED, STATUS_PARTIAL, STATUS_INSUFFICIENT,
                       STATUS_CLARIFY, STATUS_CONFLICT, STATUS_REVIEW, STATUS_UNAVAILABLE):
            self.assertNotEqual(status_label(status), status)

    def test_missing_slot_serializes(self):
        self.assertEqual(MissingSlot("f", "说明").as_dict(), {"field": "f", "description": "说明"})


if __name__ == "__main__":
    unittest.main()


class TieredPolicyConflictTests(unittest.TestCase):
    """同一篇文件里的多个数字是分档，不是证据冲突——这条由评测区抓出来的。"""

    TIERED = [
        {"source": "员工差旅管理制度.md", "chunk_index": 0,
         "text": "一线城市（北京、上海、广州、深圳）住宿标准为每人每天不超过 500 元；"},
        {"source": "员工差旅管理制度.md", "chunk_index": 1,
         "text": "二线城市住宿标准为每人每天不超过 350 元；同城合住每人标准可上浮 20%。"},
    ]

    def test_same_document_tiers_are_not_a_conflict(self):
        from forge_lite.core.evidence import has_material_conflict, qualify
        question = "去上海出差住一晚住宿费上限是多少？"
        self.assertFalse(has_material_conflict(question, self.TIERED))
        result = EvidenceQualifier().assess(question, self.TIERED)
        self.assertTrue(result.allows_generation())
        self.assertNotIn("material_conflict", result.reason_codes)

    def test_two_documents_disagreeing_is_still_a_conflict(self):
        from forge_lite.core.evidence import has_material_conflict
        other = {"source": "差旅旧版.md", "chunk_index": 0,
                 "text": "一线城市住宿标准为每人每天不超过 300 元。"}
        self.assertTrue(has_material_conflict("一线城市住宿上限是多少元？", self.TIERED + [other]))

    def test_tiered_with_overlap_is_not_a_conflict(self):
        from forge_lite.core.evidence import has_material_conflict
        relaxed = {"source": "补充通知.md", "chunk_index": 0,
                   "text": "住宿上限维持 500 元，另有 350 元的二线标准。"}
        self.assertFalse(has_material_conflict("住宿上限是多少元？", self.TIERED + [relaxed]))

    def test_days_tiering_also_ignores_same_source(self):
        from forge_lite.core.evidence import has_material_conflict
        tiers = [
            {"source": "员工差旅管理制度.md", "chunk_index": 0, "text": "报销单须在 5 个工作日内提交。"},
            {"source": "员工差旅管理制度.md", "chunk_index": 1, "text": "特殊情况可延长至 10 个工作日。"},
        ]
        self.assertFalse(has_material_conflict("报销单要在返回后几天内提交？", tiers))
