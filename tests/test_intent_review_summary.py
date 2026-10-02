"""Synthetic checks for privacy, label coverage and provenance binding."""
import copy
import json
import unittest

from scripts.summarize_intent_review import build_summary, ReviewError


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.identity = "SRC-" + "a" * 64
        self.inventory = {
            "source_labels_used": False, "keyword_router_used": False,
            "groups": [{"group_id": self.identity, "representative_customer_text": "PRIVATE CANARY. Later reply.", "subset_row_count": 3}],
            "summary": {"files_read": 1, "bytes_read": 100, "rows_read": 3,
                        "nonblank_customer_text_rows": 3, "missing_customer_text_rows": 0, "distinct_text_groups": 1,
                        "known_language_rows": {"es": 3, "pt": 0, "en": 0},
                        "other_language_rows": 0, "missing_language_rows": 0},
        }
        self.review = {"inventory_sha256": "bound-hash", "human_review_status": "pending", "groups": [
            {"group_id": self.identity, "label": "unsupported", "family_id": "FAM-PRIVATE",
             "first_request_end": len("PRIVATE CANARY."), "rationale": "PRIVATE rationale"}]}

    def test_public_summary_omits_private_text_and_identity(self):
        summary = build_summary(self.inventory, self.review, "bound-hash")
        serialized = json.dumps(summary)
        self.assertNotIn("PRIVATE", serialized)
        self.assertNotIn(self.identity, serialized)
        self.assertEqual(summary["class_support"]["unsupported"]["subset_rows"], 3)
        self.assertEqual(summary["rows_with_appended_customer_followups"], 3)
        self.assertIsNone(summary["performance_results"])

    def test_stale_review_is_rejected(self):
        with self.assertRaisesRegex(ReviewError, "review_inventory_mismatch"):
            build_summary(self.inventory, self.review, "different-hash")

    def test_missing_or_duplicate_annotations_do_not_change_denominator(self):
        for groups in ([], self.review["groups"] * 2):
            review = copy.deepcopy(self.review)
            review["groups"] = groups
            with self.assertRaisesRegex(ReviewError, "annotation_coverage_mismatch"):
                build_summary(self.inventory, review, "bound-hash")

    def test_contamination_and_inconsistent_row_totals_are_rejected(self):
        contaminated = copy.deepcopy(self.inventory)
        contaminated["source_labels_used"] = True
        with self.assertRaisesRegex(ReviewError, "annotation_input_contamination"):
            build_summary(contaminated, self.review, "bound-hash")
        inconsistent = copy.deepcopy(self.inventory)
        inconsistent["summary"]["nonblank_customer_text_rows"] = 4
        with self.assertRaisesRegex(ReviewError, "row_reconciliation_failed"):
            build_summary(inconsistent, self.review, "bound-hash")


if __name__ == "__main__":
    unittest.main()
