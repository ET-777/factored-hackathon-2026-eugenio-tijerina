"""Frozen TRAIN-only grouped comparison of NBv2 and three logistic settings.

The CLI accepts no data path or model search choices. Its exclusive ignored run
manifest precedes every fit. Text and exception contents never enter outputs;
fit/prediction failures remain in all planned out-of-fold denominators.
Read docs/linear_routing_protocol.md and freeze its hash before execution.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import platform
import re
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from bank_service.evaluation_metrics import score_routes, summarize_latencies  # noqa: E402
from bank_service.learned_routing import train_router  # noqa: E402
from bank_service.linear_routing import train_linear_router  # noqa: E402
from bank_service.route_loader import _read_training  # noqa: E402
from bank_service.routing import IntentProposal  # noqa: E402
from scripts.run_short_message_diagnostic import (  # noqa: E402
    LABELS, _json_artifact, checked_path, read_bounded, validate_training,
)

PROTOCOL = "docs/linear_routing_protocol.md"
TRAIN = "evaluation/routing_train.json"
CANDIDATE = "evaluation/routing_train_short_v2.json"
GROUPING = "evaluation/linear_routing_groups_v1.json"
SYSTEMS = ("learned_short_v2", "linear_c_0_1", "linear_c_1", "linear_c_10")
REGULARIZATION = {"linear_c_0_1": 0.1, "linear_c_1": 1.0, "linear_c_10": 10.0}
CODE_FILES = (
    "scripts/run_linear_routing_experiment.py", "scripts/run_short_message_diagnostic.py",
    "bank_service/linear_routing.py", "bank_service/learned_routing.py",
    "bank_service/route_loader.py", "bank_service/evaluation_metrics.py",
    "bank_service/routing.py", "bank_service/request_dates.py", "bank_service/records.py",
    "bank_service/selection.py", "bank_service/access.py", "bank_service/transactions.py",
    "bank_service/__init__.py", "pyproject.toml",
)
PACKAGE_NAMES = ("scikit-learn", "numpy", "scipy", "joblib", "threadpoolctl")
RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SHA256 = re.compile(r"[a-f0-9]{64}")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)),
            *(f"lpt{i}" for i in range(10))}

class ExperimentError(ValueError):
    """Fixed codes only, with no input or exception text."""


def _require(condition, code):
    if not condition:
        raise ExperimentError(code)


def _digest(body):
    return hashlib.sha256(body).hexdigest()


def load_inputs(root):
    """Read only the two fixed TRAIN artifacts and validate without fitting."""
    originals, original_hash = _json_artifact(root, TRAIN)
    candidate, candidate_hash = _json_artifact(root, CANDIDATE)
    original_rows = validate_training(originals, expected_count=96)
    rows = validate_training(candidate, expected_count=144)
    # Retain the preview loader's strict metadata, JSON and redirect guards.
    _require(_read_training(checked_path(root, TRAIN)) == original_rows
             and _read_training(checked_path(root, CANDIDATE)) == rows,
             "training_changed_during_load")
    original_by_id = {row["id"]: row for row in original_rows}
    candidate_by_id = {row["id"]: row for row in rows}
    _require(all(candidate_by_id.get(identity) == row
                 for identity, row in original_by_id.items()),
             "candidate_changed_original_training")
    additions = [row for row in rows if row["id"] not in original_by_id]
    _require(len(additions) == 48 and Counter((row["language"], row["intent"]) for row in additions)
             == Counter({(language, label): 6 for language in ("es", "pt") for label in LABELS}),
             "invalid_short_training_additions")
    _require(len({row["family_id"] for row in rows}) == 24
             and all(len({row["family_id"] for row in rows if row["intent"] == label}) == 6
                     for label in LABELS), "unexpected_training_families")
    return sorted(rows, key=lambda row: row["id"]), {TRAIN: original_hash, CANDIDATE: candidate_hash}


def assign_folds(rows, document):
    """Validate the fixed independently reviewed metadata map; never fit or tune."""
    _require(isinstance(document, dict) and set(document) == {
        "schema_version", "purpose", "source", "reviewer", "grouping_notes", "clusters"},
             "invalid_grouping_schema")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1
             and document["purpose"] == "train_only_grouped_cross_validation"
             and document["source"] == CANDIDATE
             and isinstance(document["reviewer"], str) and bool(document["reviewer"].strip())
             and isinstance(document["grouping_notes"], list)
             and all(isinstance(note, str) and 0 < len(note) <= 2000 for note in document["grouping_notes"]),
             "invalid_grouping_metadata")
    families = {row["family_id"] for row in rows}
    _require(isinstance(document["clusters"], list) and len(document["clusters"]) == 15,
             "unexpected_grouping_population")
    family_clusters, mapping, labels = {}, {}, Counter()
    for cluster in document["clusters"]:
        _require(isinstance(cluster, dict) and set(cluster) == {"id", "intent", "fold", "rows", "families"},
                 "invalid_grouping_cluster")
        identity, label, fold = cluster["id"], cluster["intent"], cluster["fold"]
        _require(isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", identity)
                 and identity not in mapping and label in LABELS
                 and type(fold) is int and fold in range(3)
                 and type(cluster["rows"]) is int and 0 < cluster["rows"] <= 144
                 and isinstance(cluster["families"], list) and 1 <= len(cluster["families"]) <= 6,
                 "invalid_grouping_cluster")
        for family in cluster["families"]:
            _require(isinstance(family, str) and family in families and family not in family_clusters,
                     "grouping_population_mismatch")
            family_clusters[family] = identity
        members = [row for row in rows if row["family_id"] in cluster["families"]]
        _require(len(members) == cluster["rows"]
                 and all(row["intent"] == label for row in members)
                 and set(row["language"] for row in members) == {"es", "pt"},
                 "grouping_count_or_label_mismatch")
        labels[label] += 1
        mapping[identity] = fold
    _require(set(family_clusters) == families and labels == Counter({
        "dispute_intake": 4, "inquiry": 3, "human_request": 3, "unsupported": 5}),
             "grouping_population_mismatch")
    audit = []
    for fold in range(3):
        held_out = [row for row in rows if mapping[family_clusters[row["family_id"]]] == fold]
        fitted = [row for row in rows if mapping[family_clusters[row["family_id"]]] != fold]
        _require(len(held_out) == 48 and Counter(row["language"] for row in held_out)
                 == Counter({"es": 24, "pt": 24}), "unexpected_fold_population")
        for population in (held_out, fitted):
            _require(set(row["intent"] for row in population) == set(LABELS)
                     and set(row["language"] for row in population) == {"es", "pt"}
                     and all(any(row["intent"] == label and row["language"] == language
                                 for row in population) for label in LABELS for language in ("es", "pt")),
                     "fold_class_or_language_missing")
        audit.append({"fold": fold, "training_rows": len(fitted), "held_out_rows": len(held_out),
                      "held_out_class_counts": dict(Counter(row["intent"] for row in held_out)),
                      "held_out_language_counts": dict(Counter(row["language"] for row in held_out)),
                      "held_out_class_language_counts": {
                          label: {language: sum(row["intent"] == label and row["language"] == language
                                               for row in held_out) for language in ("es", "pt")}
                          for label in LABELS},
                      "held_out_clusters": sorted(cluster for cluster, value in mapping.items() if value == fold),
                      "family_or_cluster_crosses_folds": False})
    return dict(sorted(family_clusters.items())), dict(sorted(mapping.items())), audit


def create_run_directory(root, run_name):
    _require(isinstance(run_name, str) and RUN_NAME.fullmatch(run_name) is not None
             and run_name.casefold() not in RESERVED, "invalid_run_name")
    parent = checked_path(root, ".local/linear_routing_runs")
    directory = parent / run_name
    _require(directory.resolve() == directory and not directory.exists()
             and not directory.is_symlink(), "output_exists_or_redirected")
    parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    return directory


def _write_new(path, document):
    with path.open("xb") as stream:
        stream.write((json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2,
                                 allow_nan=False) + "\n").encode("utf-8"))


def package_versions():
    versions = {}
    for package in PACKAGE_NAMES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def component_attempt(router, text, language):
    """Call exactly once; sanitize failures and measure only raw routing."""
    start = perf_counter()
    try:
        proposal = router(text, language)
        elapsed = perf_counter() - start
        valid = (isinstance(proposal, IntentProposal) and isinstance(proposal.intent, str)
                 and proposal.intent in LABELS and type(proposal.matched) is bool
                 and (proposal.matched or proposal.intent == "unsupported")
                 and type(proposal.confidence) in (int, float)
                 and math.isfinite(proposal.confidence) and 0 <= proposal.confidence <= 1)
        return (proposal, None, elapsed) if valid else (None, "invalid_component_proposal", elapsed)
    except Exception:
        return None, "component_execution_failed", perf_counter() - start


def _metric_row(outcome, *, grouped=False):
    proposal = None if outcome["prediction"] is None else IntentProposal(
        outcome["prediction"], outcome["confidence"], outcome["matched"])
    return {"gold_intent": outcome["gold_intent"], "language": outcome["language"],
            "family_id": outcome["cluster_id"] if grouped else outcome["family_id"],
            "prediction": proposal, "error": outcome["error_code"] is not None}


def _correct(outcome):
    return (outcome["error_code"] is None and outcome["matched"] is True
            and outcome["prediction"] == outcome["gold_intent"])


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
                           "semantic_group_scores": score_routes([_metric_row(row, grouped=True) for row in population]),
                           "fold_variation": variation,
                           "prediction_latency": summarize_latencies([row["prediction_seconds"] for row in population]),
                           "fit_latency": summarize_latencies([detail["fit_seconds"] for detail in fit_details
                                                                if detail["system"] == system])}
        if system != SYSTEMS[0]:
            pairs = Counter((_correct(reference[row["id"]]), _correct(row)) for row in population)
            systems[system]["paired_vs_nb_v2"] = {
                "attempts": len(population), "both_correct": pairs[True, True],
                "both_incorrect": pairs[False, False], "linear_only_correct": pairs[False, True],
                "nb_only_correct": pairs[True, False],
                "net_correct_difference": pairs[False, True] - pairs[True, False],
                "accuracy_difference": pooled["overall"]["accuracy"]
                    - score_routes([_metric_row(row) for row in reference.values()])["overall"]["accuracy"],
                "macro_f1_difference": pooled["overall"]["macro_f1"]
                    - score_routes([_metric_row(row) for row in reference.values()])["overall"]["macro_f1"]}
    selected = min(REGULARIZATION, key=lambda system: (
        -systems[system]["pooled_out_of_fold"]["overall"]["macro_f1"],
        -systems[system]["pooled_out_of_fold"]["overall"]["correct"], REGULARIZATION[system]))
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
            "selection": {"system": selected, "regularization": REGULARIZATION.get(selected),
                          "rule": "highest_pooled_macro_f1_then_correct_then_smallest_C",
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
        versions = package_versions()
        _write_new(directory / "manifest.json", {
            "schema_version": 1, "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": protocol_hash, "input_sha256": input_hashes, "grouping_sha256": grouping_hash,
            "code_sha256": {relative: _digest(read_bounded(checked_path(root, relative))) for relative in CODE_FILES},
            "runtime_python": platform.python_version(), "package_versions": versions,
            "systems": list(SYSTEMS), "cases_per_system": len(rows), "planned_attempts": len(rows) * len(SYSTEMS),
            "training_families": 24, "semantic_clusters": len(mapping),
            "family_cluster_mapping": family_clusters, "cluster_fold_mapping": mapping, "fold_audit": audit,
            "row_fold_mapping": {row["id"]: mapping[family_clusters[row["family_id"]]] for row in rows},
            "manifest_saved_before_fit_and_prediction": True, "train_only": True,
            "source_data_final_or_old_development_read": False, "component_only": True,
            "workflow_performance_assessed": False, "retry_policy": "none", "threshold_tuning": False,
            "ngram_search": False, "regularization_values": list(REGULARIZATION.values()),
            "parameters": {"NB": {"character_ngrams": [3, 4, 5], "alpha": 1.0},
                           "linear": {"character_ngrams": [3, 4, 5], "penalty": "l2", "solver": "lbfgs",
                                      "max_iter": 1000, "feature_fitting": "inside_each_fold"}},
            "selection_rule": "highest_pooled_macro_f1_then_correct_then_smallest_C",
            "consideration_criteria": {"execution_errors": 0, "reference_execution_errors": 0, "minimum_macro_f1_gain": 0.05,
                                       "minimum_correct_gain": 4, "language_regression_allowed": False},
            "review_status": "portuguese_fluent_human_review_pending",
        })
        _require(all(version is not None for version in versions.values()), "model_packages_missing")
        outcomes, fit_details, errors = [], [], 0
        with (directory / "outcomes.jsonl").open("x", encoding="utf-8", newline="\n") as output:
            for fold in range(3):
                fitted = [row for row in rows if mapping[family_clusters[row["family_id"]]] != fold]
                held_out = [row for row in rows if mapping[family_clusters[row["family_id"]]] == fold]
                for system in SYSTEMS:
                    start = perf_counter()
                    try:
                        model = (train_router(fitted) if system == SYSTEMS[0]
                                 else train_linear_router(fitted, regularization=REGULARIZATION[system]))
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
