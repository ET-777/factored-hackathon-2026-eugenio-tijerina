"""Toy-only smoothing mechanics; no project workload or evaluation reads."""
import copy
from dataclasses import FrozenInstanceError
import math
import unittest

from bank_service import learned_routing
from bank_service.learned_routing import INTENTS, TrainingDataError, train_router
from bank_service.routing import IntentProposal, RoutingError
from bank_service.smoothing_routing import ALPHA_VALUES, train_smoothed_router


def toy_rows():
    return [{
        "id": f"TOY-{index}", "family_id": f"TOY-FAMILY-{index}",
        "language": "es", "text": character * 3, "intent": intent,
    } for index, (intent, character) in enumerate(zip(INTENTS, "abcd"))]


class SmoothingRoutingTests(unittest.TestCase):
    def setUp(self):
        self.rows = toy_rows()

    def test_exact_alpha_one_parity_for_predictions_and_metadata(self):
        baseline = train_router(self.rows)
        candidate = train_smoothed_router(self.rows, 1.0)
        for text in ("aaa", "bbb", "ccc", "ddd", "aaa bbb", "aaab", "sí", "sim", "☄☄☄"):
            for language in ("es", "pt"):
                with self.subTest(text=text, language=language):
                    self.assertEqual(candidate.route_intent(text, language), baseline.route_intent(text, language))
        for name in (
            "training_hash", "training_row_count", "vocabulary_size", "class_counts", "language_counts",
            "_vocabulary", "_feature_counts", "_log_denominators", "_log_priors",
        ):
            self.assertEqual(getattr(candidate, name), getattr(baseline, name))

    def test_closed_form_six_feature_example_and_smoothing_effect(self):
        # Each distinct three-letter text has six unique padded 3-5 grams.
        # Uniform priors and equal count totals cancel denominators. For "aaa",
        # the winning-class odds against each other class are ((1+a)/a)**6.
        confidences = []
        for alpha in ALPHA_VALUES:
            model = train_smoothed_router(self.rows, alpha)
            self.assertEqual(model.vocabulary_size, 24)
            odds = ((1.0 + alpha) / alpha) ** 6
            proposal = model.route_intent("aaa", "es")
            self.assertEqual(proposal.intent, INTENTS[0])
            self.assertTrue(proposal.matched)
            self.assertAlmostEqual(proposal.confidence, odds / (odds + 3.0), places=14)
            confidences.append(proposal.confidence)
        self.assertGreater(confidences[0], confidences[1])
        self.assertGreater(confidences[1], confidences[2])

    def test_order_independence_and_training_preservation(self):
        original = copy.deepcopy(self.rows)
        for alpha in ALPHA_VALUES:
            forward = train_smoothed_router(self.rows, alpha)
            backward = train_smoothed_router(list(reversed(self.rows)), alpha)
            self.assertEqual(forward, backward)
            self.assertEqual(forward.route_intent("aaa", "es"), backward.route_intent("aaa", "es"))
        self.assertEqual(self.rows, original)

    def test_instances_are_immutable_and_do_not_modify_incumbent_alpha(self):
        baseline = train_router(self.rows)
        saved = baseline.route_intent("aaa", "es")
        for alpha in ALPHA_VALUES:
            candidate = train_smoothed_router(self.rows, alpha)
            self.assertEqual(candidate.alpha, alpha)
            with self.assertRaises(FrozenInstanceError):
                candidate.alpha = 1.0
            with self.assertRaises(TypeError):
                candidate.class_counts[INTENTS[0]] = 999
            with self.assertRaises(TypeError):
                candidate._feature_counts[0]["aaa"] = 999
            self.assertEqual(learned_routing.ALPHA, 1.0)
            self.assertEqual(train_router(self.rows).route_intent("aaa", "es"), saved)

    def test_assent_unknown_and_equal_top_scores_abstain(self):
        for alpha in ALPHA_VALUES:
            model = train_smoothed_router(self.rows, alpha)
            for text in ("sí", "sim", "yes", "ok", "confirmo aaa", "acepto bbb", "☄☄☄☄"):
                with self.subTest(alpha=alpha, text=text):
                    self.assertEqual(model.route_intent(text, "pt"), IntentProposal("unsupported", 0.0, False))
            proposal = model.route_intent("aaa bbb", "es")
            self.assertFalse(proposal.matched)
            self.assertEqual(proposal.intent, "unsupported")
            self.assertTrue(math.isfinite(proposal.confidence))

    def test_normalization_and_request_validation_are_shared(self):
        for alpha in ALPHA_VALUES:
            model = train_smoothed_router(self.rows, alpha)
            self.assertEqual(model.route_intent("  ＡÁＡ  ", "es"), model.route_intent("aaa", "es"))
            for text, language, code in (
                (None, "es", "invalid_request"), (True, "pt", "invalid_request"),
                (" ", "es", "invalid_request"), ("\ud800", "es", "invalid_request"),
                ("aaa", "en", "unsupported_language"), ("aaa", [], "unsupported_language"),
                ("x" * 1001, "es", "request_too_long"), ("ﬄ" * 334, "pt", "request_too_long"),
            ):
                with self.subTest(alpha=alpha, code=code):
                    with self.assertRaises(RoutingError) as caught:
                        model.route_intent(text, language)
                    self.assertEqual(str(caught.exception), code)

    def test_only_declared_float_alphas_are_accepted(self):
        for alpha in (True, False, None, "1.0", 0, 1, 10, 0.0, -1.0, 0.5, float("nan"), float("inf")):
            with self.subTest(alpha=alpha):
                with self.assertRaisesRegex(TrainingDataError, "^invalid_smoothing_alpha$"):
                    train_smoothed_router(self.rows, alpha)

    def test_training_validation_and_sanitized_errors_match_incumbent(self):
        malformed = copy.deepcopy(self.rows)
        malformed[0]["PRIVATE-CANARY"] = "PRIVATE-CANARY"
        duplicate = copy.deepcopy(self.rows)
        duplicate[1]["id"] = duplicate[0]["id"]
        for rows, code in (
            (None, "invalid_training_rows"),
            (malformed, "invalid_training_row"),
            (duplicate, "duplicate_training_identity"),
            (self.rows[:-1], "invalid_training_rows"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(TrainingDataError, "^" + code + "$"):
                    train_smoothed_router(rows)


if __name__ == "__main__":
    unittest.main()
