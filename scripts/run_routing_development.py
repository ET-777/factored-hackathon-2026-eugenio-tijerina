"""One frozen local development comparison; outputs fixed codes/aggregates only.

No final cases, source CSV/PDFs, external providers, publication or deployment.
Read docs/development_protocol.md before using this development-only runner.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from bank_service.development_driver import WorkflowDriverError, run_workflow  # noqa: E402
from bank_service.development_inputs import load_development_inputs  # noqa: E402
from bank_service.evaluation_metrics import score_routes, summarize_latencies  # noqa: E402
from bank_service.learned_routing import train_router  # noqa: E402
from bank_service.routing import IntentProposal, route_intent  # noqa: E402
from scripts.bind_routing_workload import (  # noqa: E402
    RUN_PATTERN, RESERVED_NAMES, SHA256, _read_bounded,
)

PROTOCOL = "docs/development_protocol.md"
SYSTEMS = ("keyword_baseline", "learned_candidate")
FIXED_NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class DevelopmentRunError(ValueError):
    """Only fixed codes may leave this CLI."""


def _require(condition, code):
    if not condition:
        raise DevelopmentRunError(code)


def _digest(body):
    return hashlib.sha256(body).hexdigest()


def _write_new(path, document):
    body = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(body)


def create_run_directory(project_root, run_name):
    _require(isinstance(run_name, str) and RUN_PATTERN.fullmatch(run_name) is not None
             and run_name.casefold() not in RESERVED_NAMES, "invalid_run_name")
    project_root = Path(project_root).resolve()
    intended = project_root / ".local/evaluation_runs"
    _require(intended.resolve() == intended, "output_path_redirected")
    run_dir = intended / run_name
    _require(run_dir.resolve() == run_dir and not run_dir.exists()
             and not run_dir.is_symlink(), "output_exists_or_redirected")
    intended.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(exist_ok=False)
    return run_dir


def code_hashes(project_root):
    """Hash the implementation allowlist only; never inspect final/source files."""
    paths = sorted((project_root / "bank_service").glob("*.py"))
    paths += [project_root / relative for relative in (
        "scripts/bind_routing_workload.py", "scripts/run_routing_development.py",
    )]
    hashes = {}
    for path in paths:
        _require(path.resolve() == path, "code_path_redirected")
        hashes[path.relative_to(project_root).as_posix()] = _digest(_read_bounded(path, 256 * 1024))
    return hashes


def _valid_prediction(proposal):
    return (isinstance(proposal, IntentProposal)
            and proposal.intent in ("inquiry", "dispute_intake", "human_request", "unsupported")
            and type(proposal.matched) is bool
            and type(proposal.confidence) in (int, float)
            and math.isfinite(proposal.confidence) and 0 <= proposal.confidence <= 1)


def component_attempt(router, text, language):
    start = time.perf_counter()
    try:
        proposal = router(text, language)
        valid = _valid_prediction(proposal)
        return proposal if valid else None, not valid, time.perf_counter() - start
    except Exception:
        return None, True, time.perf_counter() - start


def workflow_attempt(example, entry, records, router, *, workdir, now):
    try:
        return run_workflow(example, entry, records, router, workdir=workdir, now=now)
    except Exception as error:
        # Setup/cleanup faults must retain this attempt and all later pairs.
        # No scored duration or persisted count can be verified in this path.
        code = "workflow_driver_failure" if isinstance(error, WorkflowDriverError) else "unexpected_workflow_failure"
        return {"status": "execution_failed", "completion_pass": False,
                "checks": {"expected_branch": False, "readback_verified": False},
                "status_trace": [code], "scored_actions": None, "elapsed_ms": None,
                "cases_created": None, "error_code": code}


def _check_counts(rows):
    names = sorted({name for row in rows for name in row["workflow"]["checks"]})
    result = {}
    for name in names:
        values = [row["workflow"]["checks"].get(name) for row in rows]
        applicable = sum(type(value) is bool for value in values)
        passed = sum(value is True for value in values)
        not_applicable = sum(name in row["workflow"]["checks"]
                             and row["workflow"]["checks"][name] is None for row in rows)
        result[name] = {"applicable": applicable, "passed": passed,
                        "failed": applicable - passed, "not_applicable": not_applicable,
                        "unassessed": len(values) - applicable - not_applicable,
                        "rate": passed / applicable if applicable else None}
    return result


def _workflow_population(rows):
    total = len(rows)
    complete = sum(row["workflow"]["completion_pass"] is True for row in rows)
    return {"attempts": total, "completed": complete, "incomplete": total - complete,
            "completion_rate": complete / total if total else None,
            "execution_errors": sum(row["workflow"]["status"] == "execution_failed" for row in rows),
            "unavailable_bindings": sum(row["binding_available"] is False for row in rows),
            "checks": _check_counts(rows),
            "latency": summarize_latencies([
                None if row["workflow"]["elapsed_ms"] is None else row["workflow"]["elapsed_ms"] / 1000
                for row in rows]),
            "by_intent": {label: {"attempts": sum(row["gold_intent"] == label for row in rows),
                                  "completed": sum(row["gold_intent"] == label
                                                   and row["workflow"]["completion_pass"] is True for row in rows)}
                          for label in ("inquiry", "dispute_intake", "human_request", "unsupported")}}


def summarize_results(rows):
    identities = [(row["example_id"], row["system"]) for row in rows]
    _require(len(set(identities)) == len(identities), "duplicate_result_attempt")
    populations = [{row["example_id"] for row in rows if row["system"] == system} for system in SYSTEMS]
    _require(populations[0] == populations[1] and bool(populations[0])
             and all(row["system"] in SYSTEMS for row in rows), "unpaired_result_population")
    result = {}
    for system in SYSTEMS:
        selected = [row for row in rows if row["system"] == system]
        scoring = [{"gold_intent": row["gold_intent"], "language": row["language"],
                    "family_id": row["family_id"],
                    "prediction": None if row["proposal"] is None else IntentProposal(**row["proposal"]),
                    "error": row["component_error"]} for row in selected]
        result[system] = {"component": score_routes(scoring),
                          "component_latency": {"overall": summarize_latencies([row["component_seconds"] for row in selected]),
                                                "by_language": {language: summarize_latencies([row["component_seconds"] for row in selected if row["language"] == language]) for language in ("es", "pt")}},
                          "workflow": {"overall": _workflow_population(selected),
                                       "by_language": {language: _workflow_population([row for row in selected if row["language"] == language]) for language in ("es", "pt")}}}
    paired = {}
    index = {(row["example_id"], row["system"]): row for row in rows}
    for language in ("es", "pt"):
        baseline = result[SYSTEMS[0]]["component"]["by_language"][language]
        learned = result[SYSTEMS[1]]["component"]["by_language"][language]
        only_baseline = only_learned = 0
        for row in rows:
            if row["system"] != SYSTEMS[0] or row["language"] != language:
                continue
            pair = [index[(row["example_id"], system)] for system in SYSTEMS]
            correct = [not item["component_error"] and item["proposal"] is not None
                       and item["proposal"]["matched"] is True
                       and item["proposal"]["intent"] == item["gold_intent"] for item in pair]
            only_baseline += int(correct == [True, False])
            only_learned += int(correct == [False, True])
        paired[language] = {"component_correct_delta": learned["correct"] - baseline["correct"],
                            "macro_f1_delta": learned["macro_f1"] - baseline["macro_f1"],
                            "baseline_only_correct": only_baseline, "learned_only_correct": only_learned,
                            "workflow_completed_delta": result[SYSTEMS[1]]["workflow"]["by_language"][language]["completed"] - result[SYSTEMS[0]]["workflow"]["by_language"][language]["completed"]}
    invariant_names = ("packet_grounded", "consent_verified", "readback_verified",
                       "no_write_before_confirmation", "idempotent_confirmation")
    candidate_invariant_failures = sum(
        row["workflow"]["checks"].get(name) is False
        for row in rows if row["system"] == SYSTEMS[1] for name in invariant_names)
    development_criteria_met = (
        paired["es"]["macro_f1_delta"] >= 0.05
        and paired["es"]["component_correct_delta"] >= 1
        and all(paired[language]["workflow_completed_delta"] >= 0 for language in ("es", "pt"))
        and candidate_invariant_failures == 0)
    return {"systems": result, "paired_by_language": paired,
            "candidate_consideration": {"development_criteria_met": development_criteria_met,
                                        "observed_confirmation_receipt_invariant_failures": candidate_invariant_failures,
                                        "portuguese_fluent_human_review_complete": False,
                                        "human_output_review_complete": False,
                                        "final_evaluation_complete": False,
                                        "default_router_changed": False}}


def run_comparison(*, project_root, cohort_run, binding_run, run_name, protocol_sha256):
    project_root = Path(project_root).resolve()
    _require(isinstance(protocol_sha256, str) and SHA256.fullmatch(protocol_sha256) is not None,
             "invalid_protocol_hash")
    protocol_path = project_root / PROTOCOL
    _require(protocol_path.resolve() == protocol_path, "protocol_path_redirected")
    actual_protocol = _digest(_read_bounded(protocol_path, 256 * 1024))
    _require(actual_protocol == protocol_sha256, "protocol_hash_mismatch")
    inputs = load_development_inputs(project_root, cohort_run, binding_run)
    examples = sorted(inputs.workloads["development"]["examples"], key=lambda row: row["id"])
    _require(len(examples) == 32 and all(sum(row["language"] == language for row in examples) == 16
                                      for language in ("es", "pt")), "unexpected_development_population")
    fingerprints = code_hashes(project_root)
    run_dir = create_run_directory(project_root, run_name)
    manifest = {"schema_version": 1, "protocol_version": "development-v1", "protocol_sha256": actual_protocol,
                "started_at_utc": datetime.now(timezone.utc).isoformat(), "fixed_scenario_clock": FIXED_NOW.isoformat(),
                "code_sha256": fingerprints, "authored_artifacts": inputs.authored_hashes,
                "bindings_sha256": inputs.binding_hash, "spanish_review_sha256": inputs.review_hash,
                "cohort_sha256": {name: value for name, value in inputs.cohort_hashes.items() if name in ("manifest.json", "cohort.json")},
                "source_csv_pdf_or_final_read": False, "protocol_saved_before_fit_and_prediction": True,
                "development_examples_per_system": len(examples), "component_attempts_per_system": 32,
                "workflow_attempts_per_system": 32, "retry_policy": "none",
                "review_status": {"es": "owner_wording_and_labels_approved_output_review_pending",
                                  "pt": "provisional_fluent_human_review_pending"},
                "runtime": {"python": platform.python_version(), "os": platform.system(),
                            "os_release": platform.release(), "machine": platform.machine(),
                            "processor": platform.processor(), "logical_cpu_count": os.cpu_count()},
                "api_calls": 0, "api_charges": 0, "local_hardware_electricity_cost_measured": False}
    _write_new(run_dir / "manifest.json", manifest)
    model = train_router(inputs.workloads["train"]["examples"])
    _write_new(run_dir / "model_manifest.json", {"canonical_training_sha256": model.training_hash,
                                              "training_rows": model.training_row_count,
                                              "vocabulary_size": model.vocabulary_size,
                                              "alpha": 1, "ngrams": [3, 4, 5], "confidence_calibrated": False})
    bindings = {row["example_id"]: row for row in inputs.binding_rows if row["split"] == "development"}
    rows = []
    routers = {SYSTEMS[0]: route_intent, SYSTEMS[1]: model.route_intent}
    with (run_dir / "outcomes.jsonl").open("x", encoding="utf-8", newline="\n") as output:
        for index, example in enumerate(examples):
            order = SYSTEMS if index % 2 == 0 else tuple(reversed(SYSTEMS))
            for system in order:
                proposal, error, seconds = component_attempt(routers[system], example["text"], example["language"])
                binding = bindings[example["id"]]
                context = binding["system_context"]
                entry = None if context is None else inputs.records[context["target_transaction_id"]]
                workdir = run_dir / f"case-{index:03d}-{system}"
                workdir.mkdir(exist_ok=False)
                if entry is None:
                    workflow = {"status": "unavailable_binding", "completion_pass": False, "checks": {},
                                "status_trace": [], "scored_actions": 0, "elapsed_ms": None,
                                "cases_created": 0, "error_code": "binding_unavailable"}
                else:
                    workflow = workflow_attempt(example, entry, inputs.records,
                                                None if system == SYSTEMS[0] else model,
                                                workdir=workdir, now=FIXED_NOW)
                row = {"example_id": example["id"], "family_id": example["family_id"],
                       "language": example["language"], "gold_intent": example["intent"], "system": system,
                       "binding_available": entry is not None,
                       "proposal": None if proposal is None else asdict(proposal),
                       "component_error": error, "component_seconds": seconds, "workflow": workflow}
                output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                output.flush()
                rows.append(row)
    _require(len(rows) == 64, "incomplete_result_population")
    _require(code_hashes(project_root) == fingerprints, "implementation_changed_during_run")
    reloaded = load_development_inputs(project_root, cohort_run, binding_run)
    _require(reloaded.authored_hashes == inputs.authored_hashes and reloaded.cohort_hashes == inputs.cohort_hashes
             and reloaded.binding_hash == inputs.binding_hash and reloaded.review_hash == inputs.review_hash,
             "inputs_changed_during_run")
    _require(_digest(_read_bounded(protocol_path, 256 * 1024)) == actual_protocol, "protocol_changed_during_run")
    summary = {"schema_version": 1, "status": "development_comparison_completed",
               "finished_at_utc": datetime.now(timezone.utc).isoformat(),
               "manifest_sha256": _digest((run_dir / "manifest.json").read_bytes()),
               "model_manifest_sha256": _digest((run_dir / "model_manifest.json").read_bytes()),
               "outcomes_sha256": _digest((run_dir / "outcomes.jsonl").read_bytes()),
               "manifest": manifest, "model": {"training_rows": model.training_row_count,
                                              "vocabulary_size": model.vocabulary_size,
                                              "canonical_training_sha256": model.training_hash},
               "limitations": ["development_only_not_final", "authored_correlated_balanced_requests",
                               "spanish_owner_labels_not_independent_review", "portuguese_human_review_pending",
                               "preselected_record_context_not_discovery_or_authentication",
                               "mechanical_checks_not_semantic_or_comprehensive_safety_review",
                               "in_process_latency_not_deployed_latency", "original_source_files_not_rehashed"],
               **summarize_results(rows)}
    _write_new(run_dir / "summary.json", summary)
    return summary


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise DevelopmentRunError("invalid_arguments")


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("--cohort-run", required=True, type=Path)
        parser.add_argument("--binding-run", default="authored-routing-v1")
        parser.add_argument("--run-name", required=True)
        parser.add_argument("--protocol-sha256", required=True)
        args = parser.parse_args(argv)
        result = run_comparison(project_root=ROOT, cohort_run=args.cohort_run,
                                binding_run=args.binding_run, run_name=args.run_name,
                                protocol_sha256=args.protocol_sha256)
        print(json.dumps({"status": result["status"], "paired_by_language": result["paired_by_language"]}, sort_keys=True))
        return 0
    except Exception:
        # Preserve a partially created run; never expose private exception text.
        print('{"status":"development_comparison_failed","code":"run_failed_review_private_manifest"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
