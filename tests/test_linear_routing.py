"""Toy-only experimental mechanics; no project workload or evaluation reads."""
import copy
from dataclasses import replace
import math
import unittest
from unittest.mock import patch

from bank_service.learned_routing import INTENTS, TrainingDataError, train_router
from bank_service.linear_routing import REGULARIZATION_VALUES, train_linear_router
from bank_service.routing import IntentProposal, RoutingError


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


class LinearRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = toy_rows()
        try:
            cls.model = train_linear_router(cls.rows)
        except TrainingDataError as error:
            if str(error) == "linear_dependency_unavailable":
                raise unittest.SkipTest("Optional linear-router dependencies are not installed") from None
            raise

    def test_all_bounded_c_choices_learn_novel_class_cues(self):
        for regularization in REGULARIZATION_VALUES:
            model = train_linear_router(self.rows, regularization)
            for cue, expected in (
                ("lumora", "inquiry"), ("bravex", "dispute_intake"),
                ("zelphi", "human_request"), ("torvik", "unsupported"),
            ):
                with self.subTest(regularization=regularization, cue=cue):
                    proposal = model.route_intent(cue + " novamente", "pt")
                    self.assertEqual(proposal.intent, expected)
                    self.assertTrue(proposal.matched)
                    self.assertTrue(math.isfinite(proposal.confidence))
                    self.assertGreater(proposal.confidence, 0.25)
                    self.assertLessEqual(proposal.confidence, 1.0)

    def test_metadata_and_predictions_are_independent_of_authored_order(self):
        reversed_model = train_linear_router(list(reversed(self.rows)))
        reference = train_router(self.rows)
        self.assertEqual(self.model.training_hash, reference.training_hash)
        self.assertEqual(self.model.training_hash, reversed_model.training_hash)
        self.assertEqual(self.model.vocabulary_size, reference.vocabulary_size)
        self.assertEqual(self.model.training_row_count, 8)
        self.assertEqual(dict(self.model.language_counts), {"es": 4, "pt": 4})
        self.assertEqual(dict(self.model.class_counts), dict.fromkeys(INTENTS, 2))
        self.assertEqual(self.model.classes, tuple(self.model._estimator.classes_))
        for cue in ("lumora", "bravex", "zelphi", "torvik"):
            self.assertEqual(self.model.route_intent(cue, "es"), reversed_model.route_intent(cue, "es"))
        self.assertEqual(self.rows, toy_rows())

    def test_training_and_inference_share_unicode_accent_case_and_spacing(self):
        expected = self.model.route_intent("lumora lumora uno", "es")
        self.assertEqual(self.model.route_intent("  ＬÚＭＯＲＡ\t lumora  UNO  ", "es"), expected)

    def test_assent_and_unknown_vocabulary_abstain(self):
        for text in ("sí", "sim", "yes", "ok", "confirmo lumora", "acepto bravex", "☄☄☄☄"):
            with self.subTest(text=text):
                self.assertEqual(self.model.route_intent(text, "pt"), IntentProposal("unsupported", 0.0, False))

    def test_equal_top_scores_abstain_without_a_tuned_confidence_threshold(self):
        rows = [{
            "id": f"TOY-{index}", "family_id": f"TOY-FAM-{index}",
            "language": "es", "text": "common " + "abcd"[index] * 3, "intent": intent,
        } for index, intent in enumerate(INTENTS)]
        proposal = train_linear_router(rows).route_intent("common", "es")
        self.assertFalse(proposal.matched)
        self.assertEqual(proposal.intent, "unsupported")
        self.assertAlmostEqual(proposal.confidence, 0.25)

    def test_request_validation_keeps_incumbent_error_contract(self):
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

    def test_invalid_regularization_and_malformed_rows_fail_before_linear_fit(self):
        for regularization in (True, None, "1.0", 0, 1, 10, 0.5, float("nan"), float("inf")):
            with self.subTest(regularization=regularization):
                with self.assertRaisesRegex(TrainingDataError, "^invalid_linear_regularization$"):
                    train_linear_router(self.rows, regularization)
        rows = copy.deepcopy(self.rows)
        rows[0]["PRIVATE-CANARY"] = "PRIVATE-CANARY"
        with patch("sklearn.linear_model.LogisticRegression.fit") as fit:
            with self.assertRaisesRegex(TrainingDataError, "^invalid_training_row$"):
                train_linear_router(rows)
            fit.assert_not_called()
        incomplete = [row for row in self.rows if row["intent"] != "human_request"]
        with self.assertRaisesRegex(TrainingDataError, "^training_classes_missing$"):
            train_linear_router(incomplete)

    def test_fit_and_inference_errors_do_not_expose_supplied_text(self):
        with patch("sklearn.linear_model.LogisticRegression.fit", side_effect=ValueError("PRIVATE-CANARY")):
            with self.assertRaisesRegex(TrainingDataError, "^linear_training_failed$"):
                train_linear_router(self.rows)
        with patch.object(self.model._estimator, "decision_function", side_effect=ValueError("PRIVATE-CANARY")):
            with self.assertRaisesRegex(RoutingError, "^linear_inference_failed$"):
                self.model.route_intent("lumora", "es")

    def test_nonfinite_estimator_output_is_refused(self):
        with patch.object(self.model._estimator, "decision_function", return_value=[[float("nan")] * 4]):
            with self.assertRaisesRegex(RoutingError, "^linear_inference_failed$"):
                self.model.route_intent("lumora", "es")

    def test_unconverged_fit_is_refused_with_no_retry(self):
        from sklearn.exceptions import ConvergenceWarning
        with patch("sklearn.linear_model.LogisticRegression.fit", side_effect=ConvergenceWarning("PRIVATE-CANARY")) as fit:
            with self.assertRaisesRegex(TrainingDataError, "^linear_fit_not_converged$"):
                train_linear_router(self.rows)
            self.assertEqual(fit.call_count, 1)

    def test_class_selection_uses_estimator_order(self):
        classes = tuple(reversed(self.model.classes))
        reordered = replace(self.model, classes=classes)
        with patch.object(self.model._estimator, "decision_function", return_value=[[3.0, 0.0, -1.0, -2.0]]):
            self.assertEqual(reordered.route_intent("lumora", "es").intent, classes[0])


if __name__ == "__main__":
    unittest.main()
