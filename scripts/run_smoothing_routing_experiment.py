"""Frozen TRAIN-only grouped comparison of NBv2 and NB smoothing alpha 0.1/10.

Fixed inputs and parameters only. An exclusive ignored manifest precedes fits;
all failed fits and predictions remain attempts, without text or exception logs.
Read docs/smoothing_routing_protocol.md before executing this experiment.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from bank_service.evaluation_metrics import score_routes, summarize_latencies  # noqa: E402
from bank_service.learned_routing import train_router  # noqa: E402
from bank_service.smoothing_routing import train_smoothed_router  # noqa: E402
from scripts.run_linear_routing_experiment import (  # noqa: E402
    CANDIDATE, CODE_FILES as LINEAR_CODE_FILES, ExperimentError, GROUPING, LABELS,
    RESERVED, RUN_NAME, SHA256, TRAIN,
    _correct, _digest, _json_artifact, _metric_row, _require, _write_new,
    assign_folds, checked_path, component_attempt, load_inputs, read_bounded,
)

PROTOCOL = "docs/smoothing_routing_protocol.md"
SYSTEMS = ("learned_short_v2", "nb_alpha_0_1", "nb_alpha_10")
SMOOTHING = {"nb_alpha_0_1": 0.1, "nb_alpha_10": 10.0}
CODE_FILES = ("scripts/run_smoothing_routing_experiment.py", "bank_service/smoothing_routing.py",
              *LINEAR_CODE_FILES)


def create_run_directory(root, run_name):
    _require(isinstance(run_name, str) and RUN_NAME.fullmatch(run_name) is not None
             and run_name.casefold() not in RESERVED, "invalid_run_name")
    parent = checked_path(root, ".local/smoothing_routing_runs")
    directory = parent / run_name
    _require(directory.resolve() == directory and not directory.exists()
             and not directory.is_symlink(), "output_exists_or_redirected")
    parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    return directory


def summarize_outcomes(outcomes, fit_details):
    systems = {}
    reference = {row["id"]: row for row in outcomes if row["system"] == SYSTEMS[0]}
    for system in SYSTEMS:
        population = [row for row in outcomes if row["system"] == system]
        pooled = score_routes([_metric_row(row) for row in population])
        folds = {str(fold): score_routes([_metric_row(row) for row in population if row["fold"] == fold])
                 for fold in range(3)}
        variation = {}
        for metric in ("accuracy", "macro_f1", "coverage", "error_rate"):
            values = [folds[str(fold)]["overall"][metric] for fold in range(3)]
            mean = math.fsum(values) / 3
            variation[metric] = {"min": min(values), "max": max(values),
                                 "unweighted_mean": mean,
                                 "population_stddev": math.sqrt(math.fsum((value - mean) ** 2 for value in values) / 3)}
        systems[system] = {"pooled_out_of_fold": pooled, "by_fold": folds,
                           "unsupported_recall": {"overall": pooled["overall"]["per_intent"]["unsupported"]["recall"],
                                                  "by_language": {language: pooled["by_language"][language]["per_intent"]["unsupported"]["recall"]
                                                                  for language in ("es", "pt")}},
                           "semantic_group_scores": score_routes([_metric_row(row, grouped=True) for row in population]),
                           "fold_variation": variation,
                           "prediction_latency": summarize_latencies([row["prediction_seconds"] for row in population]),
                           "fit_latency": summarize_latencies([detail["fit_seconds"] for detail in fit_details
                                                                if detail["system"] == system])}
        if system != SYSTEMS[0]:
            pairs = Counter((_correct(reference[row["id"]]), _correct(row)) for row in population)
            systems[system]["paired_vs_nb_v2"] = {
                "attempts": len(population), "both_correct": pairs[True, True],
                "both_incorrect": pairs[False, False], "challenger_only_correct": pairs[False, True],
                "nb_only_correct": pairs[True, False],
                "net_correct_difference": pairs[False, True] - pairs[True, False],
                "accuracy_difference": pooled["overall"]["accuracy"]
                    - score_routes([_metric_row(row) for row in reference.values()])["overall"]["accuracy"],
                "macro_f1_difference": pooled["overall"]["macro_f1"]
                    - score_routes([_metric_row(row) for row in reference.values()])["overall"]["macro_f1"]}
    selected = min(SMOOTHING, key=lambda system: (
        -systems[system]["pooled_out_of_fold"]["overall"]["macro_f1"],
        -systems[system]["pooled_out_of_fold"]["overall"]["correct"], SMOOTHING[system]))
    incumbent = systems[SYSTEMS[0]]["pooled_out_of_fold"]
    challenger = systems[selected]["pooled_out_of_fold"]
    gain = challenger["overall"]["macro_f1"] - incumbent["overall"]["macro_f1"]
    correct_gain = challenger["overall"]["correct"] - incumbent["overall"]["correct"]
    criteria = {"zero_errors": challenger["overall"]["errors"] == 0,
                "reference_zero_errors": incumbent["overall"]["errors"] == 0,
                "macro_f1_gain_at_least_0_05": gain >= 0.05,
                "correct_gain_at_least_4": correct_gain >= 4,
                "no_language_accuracy_or_macro_f1_regression": all(
                    challenger["by_language"][language][metric] >= incumbent["by_language"][language][metric]
                    for language in ("es", "pt") for metric in ("accuracy", "macro_f1"))}
    return {"schema_version": 1, "train_only": True, "component_only": True,
            "workflow_performance_assessed": False, "independent_evaluation": False,
            "primary_score": "pooled_out_of_fold_macro_f1", "systems": systems,
            "selection": {"system": selected, "alpha": SMOOTHING.get(selected),
                          "rule": "highest_pooled_macro_f1_then_correct_then_smallest_alpha",
                          "consideration_criteria": criteria,
                          "consideration_passed": all(criteria.values()),
                          "macro_f1_gain": gain, "correct_gain": correct_gain,
                          "selection_on_train_only": True, "automatic_promotion": False}}


def execute_run(root, *, run_name, protocol_sha256):
    _require(isinstance(protocol_sha256, str) and SHA256.fullmatch(protocol_sha256) is not None,
             "invalid_protocol_hash")
    directory = create_run_directory(root, run_name)
    try:
        protocol_hash = _digest(read_bounded(checked_path(root, PROTOCOL)))
        _require(protocol_hash == protocol_sha256, "protocol_hash_mismatch")
        rows, input_hashes = load_inputs(root)
        grouping, grouping_hash = _json_artifact(root, GROUPING)
        family_clusters, mapping, audit = assign_folds(rows, grouping)
        _write_new(directory / "manifest.json", {
            "schema_version": 1, "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": protocol_hash, "input_sha256": input_hashes, "grouping_sha256": grouping_hash,
            "code_sha256": {relative: _digest(read_bounded(checked_path(root, relative))) for relative in CODE_FILES},
            "runtime_python": platform.python_version(), "dependency_profile": "standard_library_only",
            "systems": list(SYSTEMS), "cases_per_system": len(rows), "planned_attempts": len(rows) * len(SYSTEMS),
            "training_families": 24, "semantic_clusters": len(mapping),
            "family_cluster_mapping": family_clusters, "cluster_fold_mapping": mapping, "fold_audit": audit,
            "row_fold_mapping": {row["id"]: mapping[family_clusters[row["family_id"]]] for row in rows},
            "manifest_saved_before_fit_and_prediction": True, "train_only": True,
            "source_data_final_or_old_development_read": False, "component_only": True,
            "workflow_performance_assessed": False, "retry_policy": "none", "threshold_tuning": False,
            "ngram_search": False, "alpha_values": list(SMOOTHING.values()),
            "parameters": {"incumbent": {"character_ngrams": [3, 4, 5], "alpha": 1.0,
                                           "empirical_class_priors": True},
                           "challengers": {"character_ngrams": [3, 4, 5], "alpha_values": list(SMOOTHING.values()),
                                           "empirical_class_priors": True, "feature_fitting": "inside_each_fold"}},
            "selection_rule": "highest_pooled_macro_f1_then_correct_then_smallest_alpha",
            "consideration_criteria": {"execution_errors": 0, "reference_execution_errors": 0, "minimum_macro_f1_gain": 0.05,
                                       "minimum_correct_gain": 4, "language_regression_allowed": False},
            "review_status": "portuguese_fluent_human_review_pending",
        })
        outcomes, fit_details, errors = [], [], 0
        with (directory / "outcomes.jsonl").open("x", encoding="utf-8", newline="\n") as output:
            for fold in range(3):
                fitted = [row for row in rows if mapping[family_clusters[row["family_id"]]] != fold]
                held_out = [row for row in rows if mapping[family_clusters[row["family_id"]]] == fold]
                for system in SYSTEMS:
                    start = perf_counter()
                    try:
                        model = (train_router(fitted) if system == SYSTEMS[0]
                                 else train_smoothed_router(fitted, alpha=SMOOTHING[system]))
                        fit_seconds = perf_counter() - start
                        router = model.route_intent
                        detail = {"fold": fold, "system": system, "status": "fitted", "fit_seconds": fit_seconds,
                                  "training_rows": model.training_row_count, "training_sha256": model.training_hash,
                                  "vocabulary_size": model.vocabulary_size}
                    except Exception:
                        router = None
                        detail = {"fold": fold, "system": system, "status": "failed", "fit_seconds": perf_counter() - start,
                                  "error_code": "model_fit_failed", "training_rows": len(fitted)}
                    fit_details.append(detail)
                    for row in held_out:
                        proposal, error, seconds = ((None, "model_fit_failed", None) if router is None else
                                                   component_attempt(router, row["text"], row["language"]))
                        errors += int(error is not None)
                        public = {"id": row["id"], "family_id": row["family_id"],
                                  "cluster_id": family_clusters[row["family_id"]], "fold": fold,
                                  "language": row["language"], "gold_intent": row["intent"], "system": system,
                                  "prediction": None if proposal is None else proposal.intent,
                                  "confidence": None if proposal is None else proposal.confidence,
                                  "matched": None if proposal is None else proposal.matched,
                                  "error_code": error, "prediction_seconds": seconds}
                        output.write(json.dumps(public, sort_keys=True, allow_nan=False) + "\n")
                        output.flush()
                        outcomes.append(public)
        _write_new(directory / "models.json", fit_details)
        _require(len(outcomes) == len(rows) * len(SYSTEMS), "incomplete_attempt_population")
        _write_new(directory / "summary.json", summarize_outcomes(outcomes, fit_details))
        result = {"status": "completed_with_errors" if errors else "completed", "run_name": run_name,
                  "train_only": True, "cases_per_system": len(rows), "systems": len(SYSTEMS),
                  "attempts": len(outcomes), "fits": len(fit_details), "errors": errors}
        _write_new(directory / "status.json", result)
        return result
    except Exception as error:
        code = str(error) if isinstance(error, ExperimentError) else "experiment_execution_failed"
        _write_new(directory / "failure.json", {"status": "failed", "error_code": code,
                                                "partial_artifacts_preserved": True})
        raise ExperimentError(code) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    arguments = parser.parse_args(argv)
    try:
        result = execute_run(ROOT, run_name=arguments.run_name, protocol_sha256=arguments.protocol_sha256)
    except Exception as error:
        code = str(error) if isinstance(error, ExperimentError) else "experiment_execution_failed"
        print(json.dumps({"status": "failed", "error_code": code}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return int(result["errors"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
