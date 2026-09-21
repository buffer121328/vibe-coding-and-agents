"""工牌规则：角色 × 部门 × 密级，逐格断言谁能看见谁。不调模型。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_lite.core.identity import (  # noqa: E402
    DEFAULT_USER_ID,
    DOC_POLICY,
    USERS,
    Actor,
    authorize_chunks,
    can_see,
    catalog_of,
    resolve_actor,
)


def _chunk(department="company", sensitivity="public", acl="employee", source="x.md"):
    return {"source": source, "department": department, "sensitivity": sensitivity, "acl": acl}


class ActorRuleTests(unittest.TestCase):
    def test_admin_has_no_filter(self):
        self.assertIsNone(resolve_actor("admin").visible_department_ids())

    def test_employee_sees_own_department_plus_company(self):
        self.assertEqual(resolve_actor("it_staff").visible_department_ids(), ("it", "company"))
        self.assertEqual(resolve_actor("hr_staff").visible_department_ids(), ("hr", "company"))

    def test_department_head_sees_own_department_plus_company(self):
        self.assertEqual(resolve_actor("finance_head").visible_department_ids(), ("finance", "company"))

    def test_company_department_actor_sees_only_company(self):
        actor = Actor("temp", "临时", "employee", "company")
        self.assertEqual(actor.visible_department_ids(), ("company",))

    def test_unknown_badge_falls_back_to_default(self):
        self.assertEqual(resolve_actor("ghost_user").user_id, DEFAULT_USER_ID)
        self.assertEqual(resolve_actor(None).user_id, DEFAULT_USER_ID)

    def test_actor_passes_through_when_already_an_actor(self):
        actor = resolve_actor("finance_head")
        self.assertIs(resolve_actor(actor), actor)

    def test_actors_are_frozen(self):
        actor = resolve_actor("it_staff")
        with self.assertRaises(Exception):
            actor.department = "finance"  # type: ignore[misc]


class CanSeeTableTests(unittest.TestCase):
    def test_employee_blocked_from_restricted(self):
        self.assertFalse(can_see(resolve_actor("it_staff"), _chunk("finance", "restricted", "restricted")))
        self.assertFalse(can_see(resolve_actor("hr_staff"), _chunk("it", "department")))

    def test_employee_allowed_on_public_and_own_department(self):
        self.assertTrue(can_see(resolve_actor("it_staff"), _chunk("company", "public")))
        self.assertTrue(can_see(resolve_actor("it_staff"), _chunk("it", "department")))

    def test_department_head_allowed_on_restricted(self):
        self.assertTrue(can_see(resolve_actor("finance_head"), _chunk("finance", "restricted", "restricted")))

    def test_admin_allowed_everywhere(self):
        for department in ("company", "finance", "it", "hr", "legal"):
            self.assertTrue(can_see(resolve_actor("admin"), _chunk(department, "restricted", "restricted")))

    def test_missing_metadata_defaults_to_company_public(self):
        self.assertTrue(can_see(resolve_actor("hr_staff"), {"source": "裸块.md"}))
        self.assertTrue(can_see(resolve_actor("hr_staff"), {"source": "裸块.md", "department": None}))


class AuthorizeTests(unittest.TestCase):
    def test_authorize_filters_before_scoring(self):
        chunks = [
            _chunk("company", "public", source="公开.md"),
            _chunk("it", "department", source="IT.md"),
            _chunk("finance", "restricted", "restricted", source="密级.md"),
        ]
        kept = [item["source"] for item in authorize_chunks(chunks, "hr_staff")]
        self.assertEqual(kept, ["公开.md"])

    def test_empty_result_is_legal(self):
        self.assertEqual(authorize_chunks([], "it_staff"), [])
        self.assertEqual(authorize_chunks([_chunk("finance", "restricted", "restricted")], "it_staff"), [])


class PolicyTableTests(unittest.TestCase):
    def test_every_seed_document_is_declared(self):
        for filename, policy in DOC_POLICY.items():
            with self.subTest(filename=filename):
                self.assertIn(policy["department"], {"company", "finance", "it", "hr"})
                self.assertIn(policy["sensitivity"], {"public", "department", "restricted"})
                self.assertIn(policy["acl"], {"employee", "restricted"})

    def test_restricted_acl_matches_sensitivity(self):
        for filename, policy in DOC_POLICY.items():
            with self.subTest(filename=filename):
                self.assertEqual(policy["acl"] == "restricted", policy["sensitivity"] == "restricted")

    def test_catalog_returns_a_copy(self):
        first = catalog_of("员工差旅管理制度.md")
        first["department"] = "hacked"
        self.assertEqual(catalog_of("员工差旅管理制度.md")["department"], "company")

    def test_all_demo_badges_resolve(self):
        self.assertEqual(set(USERS), {"admin", "finance_head", "it_staff", "hr_staff"})

    def test_every_seed_file_on_disk_is_in_the_policy_table(self):
        """data/docs 里的制度文件必须进 DOC_POLICY，不能靠「未知=公司公开」兜底。

        投毒 HTML 走隔离，不进这张表；其余后缀都是检索语料，漏登就会在工牌卡和
        目录页上数出两个数字。办公用品那篇是故意放的诱饵，更不能漏。
        """
        docs_dir = ROOT / "data" / "docs"
        on_disk = {path.name for path in docs_dir.iterdir() if path.is_file()}
        indexed = {name for name in on_disk if not name.lower().endswith(".html")}
        missing = indexed - set(DOC_POLICY)
        self.assertEqual(missing, set(), f"种子制度没进权限表：{missing}")
        self.assertIn("办公用品领用制度.md", DOC_POLICY)
        self.assertEqual(DOC_POLICY["办公用品领用制度.md"]["department"], "company")
        self.assertEqual(DOC_POLICY["办公用品领用制度.md"]["sensitivity"], "public")


if __name__ == "__main__":
    unittest.main()
