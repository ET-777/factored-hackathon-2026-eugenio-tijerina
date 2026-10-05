"""Freeze or execute one separately reviewed, owner-local workflow comparison.

Fixed paths only; no original final, raw source, provider, publishing or tuning.
Run --freeze only after the owner review record exists. --run-name consumes an
exclusive execution claim before fitting, retaining interruption evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from bank_service.evaluation_metrics import score_routes, summarize_latencies
from bank_service.final_workflow_driver import _template, run_final_workflow
from bank_service.final_workflow_inputs import load_final_inputs
from bank_service.final_workflow_scoring import CHECK_NAMES, SAFETY_CHECKS, score_final_workflow
from bank_service.learned_routing import train_router
from bank_service.routing import IntentProposal, route_intent
from scripts.bind_routing_workload import _decode, _read_bounded
from scripts.run_linear_routing_experiment import load_inputs
from scripts.run_routing_development import component_attempt

PROTOCOL = "docs/final_workflow_protocol.md"
PRIVATE = "data/final_workflow_v1"
SYSTEMS = ("keyword_baseline", "learned_short_v2")
NOW = datetime(2026, 10, 4, 18, tzinfo=timezone.utc)
RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}


class FinalRunError(ValueError):
    """Fixed error codes only."""


def require(condition, code):
    if not condition:
        raise FinalRunError(code)


def path(root, relative):
    intended = root / relative
    require(intended.resolve() == intended, "path_redirected")
    return intended


def digest(root, relative):
    return hashlib.sha256(_read_bounded(path(root, relative), 512 * 1024)).hexdigest()


def read_json(root, relative):
    return _decode(_read_bounded(path(root, relative), 512 * 1024))


def write_new(destination, document):
    body = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with destination.open("xb") as stream:
        stream.write(body)


def code_hashes(root):
    files = sorted((root / "bank_service").glob("*.py"))
    files += sorted((root / "bank_service/web").glob("*"))
    files += sorted((root / "tests").glob("*.py"))
    files += [root / relative for relative in (
        "scripts/run_final_workflow.py", "scripts/bind_routing_workload.py",
        "scripts/run_linear_routing_experiment.py", "scripts/run_short_message_diagnostic.py",
        "scripts/run_routing_development.py", "pyproject.toml",
    )]
    return {file.relative_to(root).as_posix(): digest(root, file.relative_to(root).as_posix())
            for file in files if file.is_file()}


def review_commitments(root):
    # Read hashes before final words; no fit or prediction may precede this gate.
    hashes = {name: digest(root, PRIVATE + "/" + name) for name in (
        "cases.json", "manifest.json", "owner_review_es.md", "development_output_review_es.md", "author_notes.json")}
    review = read_json(root, PRIVATE + "/owner_review.json")
    fields = {"schema_version", "spanish_cases_wording_labels_approved", "spanish_development_outputs_handoff_approved",
              "cases_sha256", "spanish_review_sha256", "development_output_review_sha256",
              "portuguese_status", "owner_approval_evidence"}
    require(isinstance(review, dict) and set(review) == fields and type(review["schema_version"]) is int
            and review["schema_version"] == 1, "invalid_owner_review")
    require(review["spanish_cases_wording_labels_approved"] is True
            and review["spanish_development_outputs_handoff_approved"] is True
            and review["portuguese_status"] == "provisional_fluent_review_pending"
            and isinstance(review["owner_approval_evidence"], str)
            and 0 < len(review["owner_approval_evidence"]) <= 2000, "owner_review_pending")
    require(review["cases_sha256"] == hashes["cases.json"]
            and review["spanish_review_sha256"] == hashes["owner_review_es.md"]
            and review["development_output_review_sha256"] == hashes["development_output_review_es.md"],
            "owner_review_commitment_changed")
    hashes["owner_review.json"] = digest(root, PRIVATE + "/owner_review.json")
    return hashes


def freeze(root):
    root = Path(root).resolve()
    reviews = review_commitments(root)
    inputs = load_final_inputs(root)
    _, training_hashes = load_inputs(root)  # Validation only; no fitted features.
    document = {"schema_version": 1, "benchmark_id": "final_workflow_v1", "status": "frozen_before_prediction",
                "created_at_utc": datetime.now(timezone.utc).isoformat(), "protocol_sha256": digest(root, PROTOCOL),
                "code_sha256": code_hashes(root), "train_sha256": training_hashes,
                "case_sha256": inputs.cases_hash, "manifest_sha256": inputs.manifest_hash,
                "cohort_sha256": inputs.cohort_hashes, "review_sha256": reviews,
                "clock": NOW.isoformat(), "systems": list(SYSTEMS), "component_attempts_per_system": 32,
                "workflow_attempts_per_system": 48, "retry_policy": "none",
                "candidate_parameters": {"alpha": 1, "character_ngrams": [3, 4, 5], "empirical_priors": True},
                "portuguese_status": "provisional_fluent_review_pending", "source_raw_or_old_final_read": False}
    write_new(path(root, PRIVATE + "/freeze.json"), document)
    return document


def checked_freeze(root, freeze_sha256):
    require(isinstance(freeze_sha256, str) and re.fullmatch(r"[a-f0-9]{64}", freeze_sha256), "invalid_freeze_hash")
    require(digest(root, PRIVATE + "/freeze.json") == freeze_sha256, "freeze_hash_mismatch")
    frozen = read_json(root, PRIVATE + "/freeze.json")
    require(isinstance(frozen, dict) and frozen.get("status") == "frozen_before_prediction"
            and frozen.get("benchmark_id") == "final_workflow_v1", "invalid_freeze")
    require(frozen.get("review_sha256") == review_commitments(root), "review_changed_since_freeze")
    require(frozen.get("protocol_sha256") == digest(root, PROTOCOL)
            and frozen.get("code_sha256") == code_hashes(root), "implementation_changed_since_freeze")
    rows, train_hashes = load_inputs(root)
    require(frozen.get("train_sha256") == train_hashes, "training_changed_since_freeze")
    inputs = load_final_inputs(root)
    require(frozen.get("case_sha256") == inputs.cases_hash and frozen.get("manifest_sha256") == inputs.manifest_hash
            and frozen.get("cohort_sha256") == inputs.cohort_hashes, "workload_changed_since_freeze")
    require(frozen.get("clock") == NOW.isoformat() and frozen.get("systems") == list(SYSTEMS)
            and frozen.get("retry_policy") == "none"
            and frozen.get("component_attempts_per_system") == 32
            and frozen.get("workflow_attempts_per_system") == 48
            and frozen.get("candidate_parameters") == {"alpha": 1, "character_ngrams": [3, 4, 5], "empirical_priors": True},
            "frozen_parameters_changed")
    return frozen, rows, inputs


def create_directory(root, run_name):
    require(isinstance(run_name, str) and RUN_NAME.fullmatch(run_name) is not None
            and run_name.casefold() not in RESERVED, "invalid_run_name")
    parent = path(root, ".local/final_workflow_runs")
    directory = path(root, ".local/final_workflow_runs/" + run_name)
    require(not directory.exists(), "run_already_exists")
    parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    return directory


def failed_workflow(code):
    return {"status": "execution_failed", "driver_error": code, "cleanup_error": None,
            "status_trace": [], "http_errors": [], "http_requests": 0, "steps_completed": 0,
            "cases_created": None, "elapsed_seconds": None,
            "private_observations": {}}


def _correct(row):
    return (not row["component_error"] and row["proposal"] is not None
            and row["proposal"]["matched"] is True and row["proposal"]["intent"] == row["gold_intent"])


def population(rows):
    check_counts = {}
    for name in CHECK_NAMES:
        counts = Counter(row["workflow"]["checks"].get(name, "unassessed") for row in rows)
        applicable = counts["pass"] + counts["fail"]
        check_counts[name] = {"applicable": applicable, "passed": counts["pass"], "failed": counts["fail"],
                              "not_applicable": counts["not_applicable"], "unassessed": counts["unassessed"],
                              "rate": counts["pass"] / applicable if applicable else None}
    completed = sum(row["workflow"]["completion_pass"] is True for row in rows)
    transfers = sum(row["workflow"]["completion_pass"] is True and row["expected_terminal"] == "handoff" for row in rows)
    automatic = sum(row["workflow"]["completion_pass"] is True and row["expected_terminal"] in {"answered", "intake"} for row in rows)
    return {"attempts": len(rows), "completed": completed, "incomplete": len(rows) - completed,
            "completion_rate": completed / len(rows) if rows else None, "checks": check_counts,
            "execution_errors": sum(row["workflow"]["status"] == "execution_failed" for row in rows),
            "automated_answer_or_intake_completed": automatic, "verified_ticket_transfers_completed": transfers,
            "unnecessary_persisted_transfers": sum(row["expected_terminal"] != "handoff"
                                                   and row["workflow"].get("persisted_handoffs", 0) > 0 for row in rows),
            "latency": summarize_latencies([row["workflow"]["elapsed_seconds"] for row in rows]),
            "by_terminal": {name: {"attempts": sum(row["expected_terminal"] == name for row in rows),
                                    "completed": sum(row["expected_terminal"] == name and row["workflow"]["completion_pass"] is True for row in rows)}
                            for name in sorted({row["expected_terminal"] for row in rows})}}


def summarize(rows):
    require(len(rows) == 96 and len({(r["id"], r["system"]) for r in rows}) == 96, "incomplete_or_duplicate_population")
    require(all(sum(r["system"] == system and r["language"] == lang for r in rows) == 24
                for system in SYSTEMS for lang in ("es", "pt")), "invalid_result_population")
    systems = {}
    for system in SYSTEMS:
        selected = [r for r in rows if r["system"] == system]
        service = [r for r in selected if r["stratum"] == "service"]
        require(len(service) == 32, "invalid_component_population")
        systems[system] = {"component": score_routes([
            {"gold_intent": r["gold_intent"], "language": r["language"], "family_id": r["family_id"],
             "prediction": IntentProposal(**r["proposal"]) if r["proposal"] else None, "error": r["component_error"]}
            for r in service]),
            "component_latency": summarize_latencies([r["component_seconds"] for r in service]),
            "workflow": {"overall": population(selected), "by_language": {
                language: {stratum: population([r for r in selected if r["language"] == language and r["stratum"] == stratum])
                           for stratum in ("service", "simulated_safety")} for language in ("es", "pt")}}}
    index = {(r["id"], r["system"]): r for r in rows}
    require({r["id"] for r in rows if r["system"] == SYSTEMS[0]}
            == {r["id"] for r in rows if r["system"] == SYSTEMS[1]}, "unpaired_results")
    paired = {}
    for lang in ("es", "pt"):
        base, candidate = [systems[s]["component"]["by_language"][lang] for s in SYSTEMS]
        pairs = [(r, index[(r["id"], SYSTEMS[1])]) for r in rows
                 if r["system"] == SYSTEMS[0] and r["language"] == lang and r["stratum"] == "service"]
        paired[lang] = {"macro_f1_delta": candidate["macro_f1"] - base["macro_f1"],
                        "correct_delta": candidate["correct"] - base["correct"],
                        "baseline_only_correct": sum(_correct(b) and not _correct(c) for b, c in pairs),
                        "candidate_only_correct": sum(_correct(c) and not _correct(b) for b, c in pairs),
                        "baseline_only_workflow_completed": sum(b["workflow"]["completion_pass"] and not c["workflow"]["completion_pass"] for b, c in pairs),
                        "candidate_only_workflow_completed": sum(c["workflow"]["completion_pass"] and not b["workflow"]["completion_pass"] for b, c in pairs),
                        "service_completion_delta": systems[SYSTEMS[1]]["workflow"]["by_language"][lang]["service"]["completed"]
                        - systems[SYSTEMS[0]]["workflow"]["by_language"][lang]["service"]["completed"]}
    safety = systems[SYSTEMS[1]]["workflow"]["overall"]["checks"]
    safe = all(safety[name]["failed"] == 0 and safety[name]["unassessed"] == 0 and safety[name]["applicable"] == 48 for name in SAFETY_CHECKS)
    criteria = {"spanish_service_completions_at_least_12": systems[SYSTEMS[1]]["workflow"]["by_language"]["es"]["service"]["completed"] >= 12,
                "zero_observed_and_unassessed_safety_failures": safe,
                "no_language_service_completion_regression": all(paired[lang]["service_completion_delta"] >= 0 for lang in ("es", "pt")),
                "routing_gain_target": paired["es"]["macro_f1_delta"] >= .05 and paired["es"]["correct_delta"] >= 1,
                "workflow_gain_target": paired["es"]["service_completion_delta"] >= 2}
    return {"systems": systems, "paired_by_language": paired, "criteria": criteria,
            "engineering_targets_met": all(criteria[k] for k in ("spanish_service_completions_at_least_12", "zero_observed_and_unassessed_safety_failures", "no_language_service_completion_regression")),
            "portuguese_fluent_review_complete": False, "final_output_human_review_complete": False,
            "mechanical_scoring_complete": True, "default_router_changed": False}


def _execute(root, run_name, freeze_sha256, progress):
    root = Path(root).resolve()
    frozen, training, inputs = checked_freeze(root, freeze_sha256)
    require(not path(root, PRIVATE + "/execution_claim.json").exists(), "benchmark_already_claimed")
    directory = create_directory(root, run_name)
    progress["directory"] = directory
    # Global exclusive claim prevents a second attempt under another run name.
    write_new(path(root, PRIVATE + "/execution_claim.json"), {
        "schema_version": 1, "run_name": run_name, "freeze_sha256": freeze_sha256,
        "claimed_at_utc": datetime.now(timezone.utc).isoformat(), "retry_policy": "none"})
    write_new(directory / "manifest.json", {**frozen, "freeze_sha256": freeze_sha256,
        "runtime": {"python": platform.python_version(), "os": platform.platform(), "machine": platform.machine()},
        "planned_workflow_attempts": 96, "planned_component_attempts": 64,
        "manifest_saved_before_fit_and_prediction": True, "external_inference_calls": 0,
        "external_inference_charges": 0, "local_compute_cost_measured": False})
    try:
        model = train_router(training)
        model_info = {"status": "fitted", "rows": model.training_row_count, "training_hash": model.training_hash,
                      "vocabulary_size": model.vocabulary_size, "alpha": 1, "confidence_calibrated": False}
    except Exception:
        model, model_info = None, {"status": "failed", "error": "candidate_fit_failed"}
    write_new(directory / "model_manifest.json", model_info)
    rows = []
    with (directory / "outcomes.jsonl").open("x", encoding="utf-8", newline="\n") as public:
        for number, case in enumerate(sorted(inputs.cases, key=lambda c: c["id"])):
            try:
                binding = inputs.family_bindings[case["family_id"]]
                entry = inputs.records[binding["target_transaction_id"]]
                foreign = next((e for _, e in sorted(inputs.records.items()) if e.record.customer_id != entry.record.customer_id), None)
            except Exception:
                entry, foreign = None, None
            for system in (SYSTEMS if number % 2 == 0 else tuple(reversed(SYSTEMS))):
                proposal, error, seconds = None, False, None
                if case["stratum"] == "service":
                    if entry is None or system == SYSTEMS[1] and model is None:
                        error = True
                    else:
                        try:
                            text = _template(case["component_text"], entry)
                            proposal, error, seconds = component_attempt(route_intent if system == SYSTEMS[0] else model.route_intent,
                                                                        text, case["language"])
                        except Exception:
                            proposal, error, seconds = None, True, None
                if entry is None:
                    observation = failed_workflow("binding_unavailable")
                elif system == SYSTEMS[1] and model is None:
                    observation = failed_workflow("candidate_fit_failed")
                else:
                    try:
                        observation = run_final_workflow(case, entry, inputs.records, None if system == SYSTEMS[0] else model,
                                                         foreign_entry=foreign, now=NOW)
                    except Exception:
                        observation = failed_workflow("unexpected_driver_failure")
                try:
                    score = score_final_workflow(case, entry, inputs.records, observation)
                except Exception:
                    score = {"completion_pass": False, "checks": dict.fromkeys(CHECK_NAMES, "unassessed"),
                             "scoring_error": "unexpected_scoring_failure"}
                private = observation.pop("private_observations")
                write_new(directory / f"private-{number:03d}-{system}.json", private)
                row = {"id": case["id"], "family_id": case["family_id"], "language": case["language"],
                       "stratum": case["stratum"], "gold_intent": case["intent"], "system": system,
                       "expected_terminal": case["expected"]["terminal"], "proposal": asdict(proposal) if proposal else None,
                       "component_error": error, "component_seconds": seconds,
                       "workflow": {**observation, **score,
                                    "persisted_handoffs": sum(s.get("kind") == "handoff" for s in private.get("stored_cases", []))}}
                public.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                public.flush()
                rows.append(row)
                progress["observed"] = len(rows)
    checked_freeze(root, freeze_sha256)  # Fail if any relevant input changed during execution.
    summary = {"schema_version": 1, "status": "mechanical_comparison_complete_human_output_review_pending",
               "freeze_sha256": freeze_sha256, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
               "outcomes_sha256": hashlib.sha256((directory / "outcomes.jsonl").read_bytes()).hexdigest(),
               **summarize(rows)}
    write_new(directory / "summary.json", summary)
    return summary


def execute(root, run_name, freeze_sha256):
    progress = {"observed": 0}
    try:
        return _execute(root, run_name, freeze_sha256, progress)
    except (Exception, KeyboardInterrupt):
        if "directory" in progress:
            try:
                write_new(progress["directory"] / "failure.json", {
                    "schema_version": 1, "status": "failed_or_interrupted_no_retry",
                    "planned_workflow_attempts": 96, "observed_workflow_rows": progress["observed"],
                    "error": "final_run_did_not_complete", "partial_evidence_preserved": True})
            except Exception:
                pass  # Disk failure cannot justify printing private exception contents.
        raise


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise FinalRunError("invalid_arguments")


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__)
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--freeze", action="store_true")
        group.add_argument("--run-name")
        parser.add_argument("--freeze-sha256")
        args = parser.parse_args(argv)
        if args.freeze:
            require(args.freeze_sha256 is None, "invalid_arguments")
            freeze(ROOT)
            print(json.dumps({"status": "frozen_before_prediction", "freeze_sha256": digest(ROOT, PRIVATE + "/freeze.json")}))
        else:
            result = execute(ROOT, args.run_name, args.freeze_sha256)
            print(json.dumps({"status": result["status"], "paired_by_language": result["paired_by_language"], "criteria": result["criteria"]}))
        return 0
    except Exception as error:
        print(json.dumps({"status": "refused_or_failed", "error": str(error) if isinstance(error, FinalRunError) else "final_workflow_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
