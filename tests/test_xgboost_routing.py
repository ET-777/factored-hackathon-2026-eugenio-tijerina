"""Toy-only XGBoost mechanics; no project workload or evaluation reads."""
import copy
import math
import unittest
from unittest.mock import patch

from bank_service.learned_routing import INTENTS, TrainingDataError, train_router
from bank_service.routing import IntentProposal, RoutingError
from bank_service.xgboost_routing import MAX_DEPTH_VALUES, train_xgboost_router


def toy_rows():
    rows = []
    for intent, cue in (
        ("inquiry", "lumora"), ("dispute_intake", "bravex"),
        ("human_request", "zelphi"), ("unsupported", "torvik"),
    ):
        for language in ("es", "pt"):
            for variant in range(8):
                rows.append({
                    "id": f"TOY-{intent}-{language}-{variant}",
                    "family_id": f"TOY-FAMILY-{intent}", "language": language,
                    "text": f"{cue} {cue} {cue} {cue} {language} variant {variant}",
                    "intent": intent,
                })
    return rows


class XGBoostValidationTests(unittest.TestCase):
    def test_invalid_depth_and_rows_fail_before_optional_dependencies(self):
        rows = toy_rows()
        for max_depth in (True, None, "1", 1.0, 0, 3, float("nan"), float("inf")):
            with self.subTest(max_depth=max_depth):
                with self.assertRaisesRegex(TrainingDataError, "^invalid_xgboost_max_depth$"):
                    train_xgboost_router(rows, max_depth)
        malformed = copy.deepcopy(rows)
        malformed[0]["PRIVATE-CANARY"] = "PRIVATE-CANARY"
        with self.assertRaisesRegex(TrainingDataError, "^invalid_training_row$"):
            train_xgboost_router(malformed)
        incomplete = [row for row in rows if row["intent"] != "human_request"]
        with self.assertRaisesRegex(TrainingDataError, "^training_classes_missing$"):
            train_xgboost_router(incomplete)


class XGBoostRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = toy_rows()
        try:
            cls.models = {depth: train_xgboost_router(cls.rows, depth) for depth in MAX_DEPTH_VALUES}
        except TrainingDataError as error:
            if str(error) == "xgboost_dependency_unavailable":
                raise unittest.SkipTest("Optional XGBoost-router dependencies are not installed") from None
            raise
        cls.model = cls.models[1]

    def test_both_fixed_configurations_learn_fabricated_cues(self):
        for depth, model in self.models.items():
            for cue, expected in (
                ("lumora", "inquiry"), ("bravex", "dispute_intake"),
                ("zelphi", "human_request"), ("torvik", "unsupported"),
            ):
                with self.subTest(max_depth=depth, cue=cue):
                    proposal = model.route_intent(cue + " novamente", "pt")
                    self.assertEqual(proposal.intent, expected)
                    self.assertTrue(proposal.matched)
                    self.assertTrue(math.isfinite(proposal.confidence))
                    self.assertGreater(proposal.confidence, 0.25)
                    self.assertLessEqual(proposal.confidence, 1.0)

    def test_fixed_training_parameters_and_label_encoding(self):
        for depth, model in self.models.items():
            actual = model._estimator.get_params()
            for name, expected in {
                "n_estimators": 100, "learning_rate": 0.1, "max_depth": depth,
                "min_child_weight": 2, "reg_lambda": 10, "reg_alpha": 0,
                "subsample": 1, "colsample_bytree": 1,
                "objective": "multi:softprob", "num_class": 4,
                "random_state": 0, "n_jobs": 1, "tree_method": "hist", "device": "cpu",
            }.items():
                with self.subTest(max_depth=depth, parameter=name):
                    self.assertEqual(actual[name], expected)
            self.assertEqual(tuple(model._estimator.classes_), (0, 1, 2, 3))
            self.assertEqual(model.classes, INTENTS)
            self.assertIsNone(actual.get("early_stopping_rounds"))

    def test_metadata_and_predictions_are_independent_of_authored_order(self):
        reversed_model = train_xgboost_router(list(reversed(self.rows)))
        reference = train_router(self.rows)
        self.assertEqual(self.model.training_hash, reference.training_hash)
        self.assertEqual(self.model.training_hash, reversed_model.training_hash)
        self.assertEqual(self.model.vocabulary_size, reference.vocabulary_size)
        self.assertEqual(self.model.training_row_count, 64)
        self.assertEqual(dict(self.model.language_counts), {"es": 32, "pt": 32})
        self.assertEqual(dict(self.model.class_counts), dict.fromkeys(INTENTS, 16))
        for cue in ("lumora", "bravex", "zelphi", "torvik"):
            self.assertEqual(self.model.route_intent(cue, "es"), reversed_model.route_intent(cue, "es"))
        self.assertEqual(self.rows, toy_rows())

    def test_training_and_inference_share_unicode_accent_case_and_spacing(self):
        expected = self.model.route_intent("lumora lumora es", "es")
        self.assertEqual(self.model.route_intent("  ＬÚＭＯＲＡ\t lumora  ES  ", "es"), expected)

    def test_assent_and_unknown_vocabulary_abstain(self):
        for text in ("sí", "sim", "yes", "ok", "confirmo lumora", "acepto bravex", "☄☄☄☄"):
            with self.subTest(text=text):
                self.assertEqual(self.model.route_intent(text, "pt"), IntentProposal("unsupported", 0.0, False))

    def test_equal_top_probabilities_abstain_without_a_tuned_threshold(self):
        with patch.object(self.model._estimator, "predict_proba", return_value=[[0.3, 0.3, 0.2, 0.2]]):
            self.assertEqual(self.model.route_intent("lumora", "es"), IntentProposal("unsupported", 0.3, False))
        with patch.object(self.model._estimator, "predict_proba", return_value=[[0.251, 0.25, 0.25, 0.249]]):
            self.assertEqual(self.model.route_intent("lumora", "es"), IntentProposal(INTENTS[0], 0.251, True))

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

    def test_fit_and_inference_errors_do_not_expose_supplied_text(self):
        with patch("xgboost.XGBClassifier.fit", side_effect=ValueError("PRIVATE-CANARY")) as fit:
            with self.assertRaisesRegex(TrainingDataError, "^xgboost_training_failed$"):
                train_xgboost_router(self.rows)
            self.assertEqual(fit.call_count, 1)
        with patch.object(self.model._estimator, "predict_proba", side_effect=ValueError("PRIVATE-CANARY")):
            with self.assertRaisesRegex(RoutingError, "^xgboost_inference_failed$"):
                self.model.route_intent("lumora", "es")

    def test_malformed_probability_outputs_are_refused(self):
        import numpy as np
        for output in (
            [], [0.25, 0.25, 0.25, 0.25], [[0.25] * 4, [0.25] * 4],
            [[0.5, 0.5]], [[float("nan")] * 4], [[float("inf"), 0.0, 0.0, 0.0]],
            [[-0.1, 0.4, 0.4, 0.3]], [[1.1, 0.0, 0.0, 0.0]],
            [[0.1, 0.1, 0.1, 0.1]], [["PRIVATE-CANARY", 0.0, 0.0, 0.0]],
            np.full((1, 4, 1), 0.25),
        ):
            with self.subTest(output=output):
                with patch.object(self.model._estimator, "predict_proba", return_value=output):
                    with self.assertRaisesRegex(RoutingError, "^xgboost_inference_failed$"):
                        self.model.route_intent("lumora", "es")

    def test_numeric_probabilities_map_back_to_sorted_intents(self):
        for index, intent in enumerate(INTENTS):
            probabilities = [0.1] * 4
            probabilities[index] = 0.7
            with self.subTest(intent=intent):
                with patch.object(self.model._estimator, "predict_proba", return_value=[probabilities]):
                    self.assertEqual(self.model.route_intent("lumora", "es").intent, intent)


if __name__ == "__main__":
    unittest.main()
