"""Toy model mechanics only; no authored project workload or private/final data."""
import copy
import math
import unittest
from unittest.mock import patch

from bank_service import learned_routing
from bank_service.learned_routing import TrainingDataError, train_router
from bank_service.routing import IntentProposal, RoutingError, route_intent


def toy_rows():
    rows = []
    for intent, cue in (
        ("inquiry", "lumora"), ("dispute_intake", "bravex"),
        ("human_request", "zelphi"), ("unsupported", "torvik"),
    ):
        for language, suffix in (("es", "uno"), ("pt", "dois")):
            rows.append({
                "id": f"TOY-{intent}-{language}", "family_id": f"TOY-FAMILY-{intent}",
                "language": language, "text": f"{cue} {cue} {suffix}", "intent": intent,
            })
    return rows


class LearnedRoutingTests(unittest.TestCase):
    def setUp(self):
        self.rows = toy_rows()
        self.model = train_router(self.rows)

    def test_supervision_learns_a_cue_missing_from_keyword_baseline(self):
        self.assertEqual(route_intent("lumora", "es"), IntentProposal("unsupported", 0.0, False))
        proposal = self.model.route_intent("lumora novamente", "pt")
        self.assertEqual(proposal.intent, "inquiry")
        self.assertTrue(proposal.matched)
        self.assertGreater(proposal.confidence, 0.25)
        for cue, expected in (("bravex", "dispute_intake"), ("zelphi", "human_request"), ("torvik", "unsupported")):
            with self.subTest(cue=cue):
                self.assertEqual(self.model.route_intent(cue, "es").intent, expected)

    def test_authored_order_does_not_change_predictions_or_training_hash(self):
        reversed_model = train_router(list(reversed(self.rows)))
        self.assertEqual(reversed_model.training_hash, self.model.training_hash)
        self.assertRegex(self.model.training_hash, r"^[a-f0-9]{64}$")
        self.assertEqual(reversed_model.class_counts, self.model.class_counts)
        self.assertEqual(self.model.training_row_count, 8)
        self.assertEqual(dict(self.model.language_counts), {"es": 4, "pt": 4})
        for text in ("lumora", "bravex novamente", "zelphi uno", "torvik torvik"):
            with self.subTest(text=text):
                self.assertEqual(reversed_model.route_intent(text, "es"), self.model.route_intent(text, "es"))

    def test_training_and_inference_share_unicode_accent_case_and_spacing(self):
        normalized = self.model.route_intent("lumora lumora uno", "es")
        self.assertEqual(self.model.route_intent("  ＬÚＭＯＲＡ\t lumora  UNO  ", "es"), normalized)

    def test_unseen_features_abstain_and_tied_class_scores_do_not_choose_a_label(self):
        self.assertEqual(self.model.route_intent("☄☄☄☄", "pt"), IntentProposal("unsupported", 0.0, False))
        rows = []
        for index, intent in enumerate(learned_routing.INTENTS):
            rows.append({"id": f"TOY-{index}", "family_id": f"TOY-FAM-{index}", "language": "es", "text": "common " + "abcd"[index] * 3, "intent": intent})
        tied = train_router(rows).route_intent("common", "es")
        self.assertEqual(tied.intent, "unsupported")
        self.assertFalse(tied.matched)
        self.assertAlmostEqual(tied.confidence, 0.25)

    def test_assent_abstains_even_when_the_text_has_learned_features(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["text"] = "sim sim sim"
        model = train_router(rows)
        for text in ("sí", "sim", "yes", "ok", "confirmo", "confirmo la disputa", "acepto crear el caso"):
            with self.subTest(text=text):
                self.assertEqual(model.route_intent(text, "pt"), IntentProposal("unsupported", 0.0, False))

    def test_model_scores_are_finite_bounded_for_short_and_long_inputs(self):
        for text in ("lumora", "zelphi uno", ("bravex " * 140).strip()):
            with self.subTest(length=len(text)):
                proposal = self.model.route_intent(text, "es")
                self.assertIsInstance(proposal.confidence, float)
                self.assertTrue(math.isfinite(proposal.confidence))
                self.assertGreaterEqual(proposal.confidence, 0.0)
                self.assertLessEqual(proposal.confidence, 1.0)

    def test_inference_errors_are_compatible_fixed_routing_codes(self):
        for text, language, code in (
            (None, "es", "invalid_request"), (True, "pt", "invalid_request"),
            (" ", "es", "invalid_request"), ("\ud800", "es", "invalid_request"),
            ("lumora", "en", "unsupported_language"), ("lumora", [], "unsupported_language"),
            ("x" * 1001, "es", "request_too_long"), ("ﬄ" * 334, "pt", "request_too_long"),
        ):
            with self.subTest(code=code):
                with self.assertRaises(RoutingError) as caught:
                    self.model.route_intent(text, language)
                self.assertEqual(str(caught.exception), code)

    def test_training_sequence_bounds_and_required_class_coverage(self):
        for rows in (None, "PRIVATE-TEXT", {}, iter(self.rows), [], self.rows * 33):
            with self.subTest(container=type(rows).__name__):
                with self.assertRaisesRegex(TrainingDataError, "^invalid_training_rows$"):
                    train_router(rows)
        incomplete = [row for row in self.rows if row["intent"] != "human_request"]
        with self.assertRaisesRegex(TrainingDataError, "^training_classes_missing$"):
            train_router(incomplete)

    def test_known_field_contract_rejects_missing_or_extra_values(self):
        for change in ("missing", "extra", "not_mapping"):
            rows = copy.deepcopy(self.rows)
            if change == "missing":
                del rows[0]["family_id"]
            elif change == "extra":
                rows[0]["PRIVATE-CANARY"] = "PRIVATE-CANARY"
            else:
                rows[0] = "PRIVATE-CANARY"
            with self.subTest(change=change):
                with self.assertRaisesRegex(TrainingDataError, "^invalid_training_row$"):
                    train_router(rows)

    def test_training_types_values_and_text_bounds_use_safe_errors(self):
        for field, value, code in (
            ("id", True, "invalid_training_identity"), ("family_id", "../private", "invalid_training_identity"),
            ("language", "en", "invalid_training_language"), ("language", [], "invalid_training_language"),
            ("intent", "PRIVATE-CANARY", "invalid_training_intent"), ("intent", [], "invalid_training_intent"),
            ("text", None, "invalid_training_text"), ("text", " ", "invalid_training_text"),
            ("text", "x" * 1001, "invalid_training_text"), ("text", "\ud800", "invalid_training_text"),
        ):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            with self.subTest(field=field, code=code):
                with self.assertRaises(TrainingDataError) as caught:
                    train_router(rows)
                self.assertEqual(str(caught.exception), code)
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_duplicate_identity_normalized_text_and_family_conflicts_are_refused(self):
        for mutation, code in (
            ("identity", "duplicate_training_identity"),
            ("text", "duplicate_training_text"),
            ("family", "training_family_label_conflict"),
        ):
            rows = copy.deepcopy(self.rows)
            if mutation == "identity":
                rows[2]["id"] = rows[0]["id"]
            elif mutation == "text":
                rows[2]["text"] = "  " + rows[0]["text"].upper() + "  "
            else:
                rows[2]["family_id"] = rows[0]["family_id"]
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(TrainingDataError, "^" + code + "$"):
                    train_router(rows)

    def test_vocabulary_bound_refuses_without_truncating_training_rows(self):
        with patch.object(learned_routing, "MAX_VOCABULARY", 1):
            with self.assertRaisesRegex(TrainingDataError, "^vocabulary_limit_exceeded$"):
                train_router(self.rows)
        self.assertEqual(self.rows, toy_rows())


if __name__ == "__main__":
    unittest.main()
