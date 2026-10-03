"""Analytical scorer examples only: no datasets, routers, models, or source I/O."""
from copy import deepcopy
import math
import unittest

from bank_service.evaluation_metrics import (
    ABSTAIN, LABELS, MetricsError, score_routes, summarize_latencies,
)
from bank_service.routing import IntentProposal


def row(gold="inquiry", prediction="inquiry", *, language="es", family="family", error=False):
    if isinstance(prediction, str):
        prediction = IntentProposal(prediction, 0.7, True)
    return {"gold_intent": gold, "language": language, "family_id": family,
            "prediction": prediction, "error": error}


class RouteMetricTests(unittest.TestCase):
    def test_analytical_confusion_rates_and_fixed_four_label_macro(self):
        rows = [
            row("inquiry", "inquiry", family="f1"),
            row("inquiry", "dispute_intake", language="pt", family="f1"),
            row("dispute_intake", "dispute_intake", family="f2"),
            row("dispute_intake", IntentProposal("unsupported", 0.0, False), language="pt", family="f2"),
            row("human_request", None, family="f3"),
            row("unsupported", "unsupported", language="pt", family="f4"),
            row("unsupported", IntentProposal("unsupported", math.nan, True), family="f4"),
            row("human_request", "inquiry", language="pt", family="f3"),
        ]
        output = score_routes(rows)
        overall = output["overall"]
        self.assertEqual((overall["attempts"], overall["correct"], overall["covered"],
                          overall["abstentions"], overall["errors"]), (8, 3, 5, 3, 2))
        self.assertEqual(overall["accuracy"], 3 / 8)
        self.assertEqual(overall["coverage"], 5 / 8)
        self.assertEqual(overall["error_rate"], 2 / 8)
        self.assertAlmostEqual(overall["macro_f1"], 5 / 12)
        self.assertEqual(overall["confusion"]["inquiry"]["dispute_intake"], 1)
        self.assertEqual(overall["confusion"]["unsupported"][ABSTAIN], 1)
        self.assertEqual(overall["per_intent"]["inquiry"]["precision"], 0.5)
        self.assertEqual(overall["per_intent"]["inquiry"]["recall"], 0.5)
        self.assertEqual(overall["per_intent"]["human_request"]["predicted"], 0)
        self.assertEqual(overall["per_intent"]["human_request"]["f1"], 0.0)
        self.assertAlmostEqual(overall["per_intent"]["unsupported"]["f1"], 2 / 3)
        self.assertEqual(output["by_language"]["es"]["accuracy"], 0.5)
        self.assertEqual(output["by_language"]["es"]["macro_f1"], 0.5)
        self.assertEqual(output["by_language"]["pt"]["accuracy"], 0.25)
        self.assertEqual(output["by_language"]["pt"]["macro_f1"], 0.25)
        self.assertEqual(overall["family_exact_all_correct"],
                         {"families": 4, "correct": 0, "incorrect": 4, "rate": 0.0})

    def test_unmatched_unsupported_is_abstention_not_correct_or_error(self):
        result = score_routes([row("unsupported", IntentProposal("unsupported", 0.0, False))])["overall"]
        self.assertEqual(result["correct"], 0)
        self.assertEqual(result["abstentions"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["confusion"]["unsupported"][ABSTAIN], 1)

    def test_explicit_error_overrides_even_a_correct_valid_proposal(self):
        result = score_routes([row(error=True)])["overall"]
        self.assertEqual((result["attempts"], result["correct"], result["errors"], result["abstentions"]),
                         (1, 0, 1, 1))
        self.assertEqual(result["coverage"], 0.0)

    def test_malformed_proposals_remain_in_denominator_as_abstention_errors(self):
        invalid = [None, {}, "not-a-proposal", IntentProposal("unknown", 0.5, True),
                   IntentProposal([], 0.5, True), IntentProposal("inquiry", math.inf, True),
                   IntentProposal("inquiry", -math.inf, True), IntentProposal("inquiry", math.nan, True),
                   IntentProposal("inquiry", -0.1, True), IntentProposal("inquiry", 1.1, True),
                   IntentProposal("inquiry", True, True), IntentProposal("inquiry", "0.9", True),
                   IntentProposal("inquiry", 10 ** 1000, True), IntentProposal("inquiry", 0.5, 1)]
        rows = [row(prediction=proposal) for proposal in invalid]
        # The row helper deliberately converts strings; use the invalid raw value.
        rows[2]["prediction"] = "not-a-proposal"
        result = score_routes(rows)["overall"]
        self.assertEqual(result["attempts"], len(invalid))
        self.assertEqual(result["errors"], len(invalid))
        self.assertEqual(result["abstentions"], len(invalid))
        self.assertEqual(result["correct"], 0)

    def test_confidence_does_not_apply_or_select_a_threshold(self):
        result = score_routes([row(prediction=IntentProposal("inquiry", 0.0, True))])["overall"]
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["macro_f1"], 0.25)

    def test_families_require_every_translation_attempt_to_be_correct(self):
        result = score_routes([
            row(family="a"), row(family="a", language="pt"),
            row(family="b"), row(family="b", language="pt", prediction=None),
        ])
        self.assertEqual(result["overall"]["family_exact_all_correct"],
                         {"families": 2, "correct": 1, "incorrect": 1, "rate": 0.5})
        self.assertEqual(result["by_language"]["es"]["family_exact_all_correct"]["rate"], 1.0)
        self.assertEqual(result["by_language"]["pt"]["family_exact_all_correct"]["rate"], 0.5)

    def test_empty_populations_have_no_claimed_aggregate_rate_and_fixed_matrix(self):
        output = score_routes([])
        self.assertEqual(output["labels"], list(LABELS))
        self.assertEqual(output["prediction_columns"], list(LABELS) + [ABSTAIN])
        for result in (output["overall"], *output["by_language"].values()):
            self.assertEqual(result["attempts"], 0)
            for key in ("accuracy", "coverage", "abstention_rate", "error_rate", "macro_f1"):
                self.assertIsNone(result[key])
            self.assertIsNone(result["family_exact_all_correct"]["rate"])
            self.assertEqual(len(result["confusion"]), 4)
            self.assertTrue(all(len(columns) == 5 and sum(columns.values()) == 0 for columns in result["confusion"].values()))
            self.assertTrue(all(m["support"] == 0 and m["f1"] == 0 for m in result["per_intent"].values()))
        self.assertIsNone(score_routes([row()])["by_language"]["pt"]["accuracy"])

    def test_invalid_gold_or_language_metadata_rejects_instead_of_dropping(self):
        for changes in ({"gold_intent": "PRIVATE-SYNTHETIC"}, {"gold_intent": []},
                        {"language": "en"}, {"language": None}, {"family_id": " "},
                        {"family_id": " padded "}, {"error": "PRIVATE-SYNTHETIC"}):
            item = row()
            item.update(changes)
            with self.subTest(), self.assertRaises(MetricsError) as caught:
                score_routes([row(), item])
            self.assertNotIn("PRIVATE-SYNTHETIC", str(caught.exception))
        missing_language = row()
        del missing_language["language"]
        with self.assertRaisesRegex(MetricsError, "^invalid_row_schema$"):
            score_routes([missing_language])

    def test_schema_and_container_validation(self):
        for value in (None, "bad", {}, 2):
            with self.subTest(), self.assertRaisesRegex(MetricsError, "^invalid_rows$"):
                score_routes(value)
        for value in (None, [], 3):
            with self.subTest(), self.assertRaisesRegex(MetricsError, "^invalid_row$"):
                score_routes([value])
        item = row()
        item["extra"] = "ignored values must not silently enter the contract"
        with self.assertRaisesRegex(MetricsError, "^invalid_row_schema$"):
            score_routes([item])

    def test_omitted_error_defaults_false_generator_allowed_and_inputs_unchanged(self):
        item = row()
        del item["error"]
        before = deepcopy(item)
        result = score_routes(iter([item]))
        self.assertEqual(result["overall"]["correct"], 1)
        self.assertEqual(item, before)


class LatencyMetricTests(unittest.TestCase):
    def test_nearest_rank_percentile_uses_observed_not_attempt_count(self):
        samples = list(range(1, 21)) + [None, None]
        before = list(samples)
        result = summarize_latencies(iter(samples))
        self.assertEqual(result["attempts"], 22)
        self.assertEqual(result["observed"], 20)
        self.assertEqual(result["missing"], 2)
        self.assertEqual(result["coverage"], 20 / 22)
        self.assertEqual(result["median"], 10.5)
        self.assertEqual(result["p95"], 19.0)
        self.assertEqual(samples, before)

    def test_empty_all_missing_singleton_and_zero_latency(self):
        empty = summarize_latencies([])
        self.assertEqual(empty["attempts"], 0)
        self.assertIsNone(empty["coverage"])
        self.assertIsNone(empty["median"])
        self.assertIsNone(empty["p95"])
        missing = summarize_latencies([None, None])
        self.assertEqual(missing["attempts"], 2)
        self.assertEqual(missing["coverage"], 0.0)
        self.assertIsNone(missing["p95"])
        self.assertEqual(summarize_latencies([0])["median"], 0.0)
        self.assertEqual(summarize_latencies([0.07])["p95"], 0.07)

    def test_finite_large_durations_do_not_overflow_the_median(self):
        result = summarize_latencies([1.0e308, 1.0e308])
        self.assertEqual(result["median"], 1.0e308)
        self.assertTrue(math.isfinite(result["median"]))
        self.assertTrue(math.isfinite(result["p95"]))

    def test_invalid_durations_do_not_disappear_or_become_zero(self):
        for value in (True, False, -0.1, math.nan, math.inf, -math.inf, "PRIVATE-SYNTHETIC", [], 10 ** 1000):
            with self.subTest(), self.assertRaisesRegex(MetricsError, "^invalid_latency$") as caught:
                summarize_latencies([0.1, value])
            self.assertNotIn("PRIVATE-SYNTHETIC", str(caught.exception))
        for values in (None, "0.1", {}, 7):
            with self.subTest(), self.assertRaisesRegex(MetricsError, "^invalid_latencies$"):
                summarize_latencies(values)


if __name__ == "__main__":
    unittest.main()
