"""Frozen, bounded raw-intent diagnostic; no workflow, banking or final inputs.

Only the fixed authored files named below can be loaded. A run is exclusive and
its input/code/protocol fingerprints are saved before fitting or prediction.
Failures remain attempts; exception text and customer-message text never leave
the runner. Read docs/short_message_protocol.md before executing this script.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from bank_service.evaluation_metrics import score_routes  # noqa: E402
from bank_service.learned_routing import train_router  # noqa: E402
from bank_service.routing import IntentProposal, route_intent  # noqa: E402

LABELS = ("inquiry", "dispute_intake", "human_request", "unsupported")
SYSTEMS = ("keyword_baseline", "learned_v1", "learned_short_v2")
PROTOCOL = "docs/short_message_protocol.md"
TRAIN = "evaluation/routing_train.json"
CANDIDATE = "evaluation/routing_train_short_v2.json"
BATCHES = {
    "coverage": ("evaluation/routing_short_messages_v1.json", 48, "development_coverage_diagnostic"),
    "followup": ("evaluation/routing_short_followup_v1.json", 32, "development_followup_diagnostic"),
}
CODE_FILES = (
    "scripts/run_short_message_diagnostic.py", "bank_service/learned_routing.py",
    "bank_service/evaluation_metrics.py", "bank_service/routing.py",
    "bank_service/request_dates.py", "bank_service/records.py", "bank_service/selection.py",
    "bank_service/access.py", "bank_service/transactions.py", "bank_service/__init__.py",
)
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SHA256 = re.compile(r"[a-f0-9]{64}")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)),
            *(f"lpt{i}" for i in range(10))}
MAX_BYTES = 256 * 1024


class DiagnosticError(ValueError):
    """Only fixed codes, never inputs or exception text."""


def _require(condition, code):
    if not condition:
        raise DiagnosticError(code)


def _digest(body):
    return hashlib.sha256(body).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(_):
    raise DiagnosticError("nonfinite_json_value")


def checked_path(root, relative):
    """Reject symlinks/junctions and escapes before opening an allowlisted path."""
    root = Path(root).absolute()
    _require(root.resolve() == root and not root.is_symlink(), "project_path_redirected")
    path = root / relative
    _require(path.resolve() == path and not path.is_symlink(), "input_path_redirected")
    return path


def read_bounded(path):
    with path.open("rb") as stream:
        body = stream.read(MAX_BYTES + 1)
    _require(len(body) <= MAX_BYTES, "artifact_too_large")
    return body


def _json_artifact(root, relative):
    body = read_bounded(checked_path(root, relative))
    try:
        document = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError):
        raise DiagnosticError("invalid_json_artifact") from None
    return document, _digest(body)


def _normalized(text):
    folded = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", text).casefold())
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


def _identity(value):
    return isinstance(value, str) and IDENTITY.fullmatch(value) is not None


def _text(value, maximum=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return len(_normalized(value)) <= maximum


def validate_training(document, *, expected_count):
    _require(isinstance(document, dict) and set(document) == {
        "schema_version", "split", "provenance", "review_status", "examples"}, "invalid_training_schema")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1
             and document["split"] == "train" and document["provenance"] == "codex_authored"
             and document["review_status"] == "draft_pending_owner_and_portuguese_review",
             "invalid_training_metadata")
    examples = document["examples"]
    _require(isinstance(examples, list) and len(examples) == expected_count, "unexpected_training_population")
    identities, texts, families, labels = set(), set(), {}, set()
    for row in examples:
        _require(isinstance(row, dict) and set(row) == {"id", "family_id", "language", "text", "intent"},
                 "invalid_training_row")
        _require(_identity(row["id"]) and _identity(row["family_id"]), "invalid_training_identity")
        _require(row["language"] in ("es", "pt") and row["intent"] in LABELS
                 and _text(row["text"]), "invalid_training_value")
        _require(row["id"] not in identities, "duplicate_training_identity")
        key = (row["language"], _normalized(row["text"]))
        _require(key not in texts, "duplicate_training_text")
        _require(row["family_id"] not in families or families[row["family_id"]] == row["intent"],
                 "training_family_label_conflict")
        identities.add(row["id"])
        texts.add(key)
        families[row["family_id"]] = row["intent"]
        labels.add(row["intent"])
    _require(labels == set(LABELS), "training_classes_missing")
    _require(all(sum(row["language"] == language and row["intent"] == label for row in examples)
                     == expected_count // 8 for language in ("es", "pt") for label in LABELS),
             "unbalanced_training_population")
    return examples


def validate_cases(document, *, count, purpose):
    keys = {"schema_version", "purpose", "provenance", "review_status", "cases", "notes"}
    _require(isinstance(document, dict) and keys.issubset(document)
             and set(document).issubset(keys | {"state_cases"}), "invalid_diagnostic_schema")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1
             and document["purpose"] == purpose and document["provenance"] == "codex_authored"
             and document["review_status"] == "pending_owner_spanish_and_fluent_portuguese_review",
             "invalid_diagnostic_metadata")
    notes = document["notes"]
    _require(isinstance(notes, list) and 1 <= len(notes) <= 20
             and all(_text(note, 2000) for note in notes), "invalid_diagnostic_notes")
    cases = document["cases"]
    _require(isinstance(cases, list) and len(cases) == count, "unexpected_diagnostic_population")
    identities, texts, families = set(), set(), {}
    for row in cases:
        _require(isinstance(row, dict) and set(row) == {
            "case_id", "language", "family", "intent", "text", "origin"}, "invalid_diagnostic_row")
        _require(_identity(row["case_id"]) and _identity(row["family"]), "invalid_diagnostic_identity")
        _require(row["language"] in ("es", "pt") and row["intent"] in LABELS
                 and _text(row["text"]) and row["origin"] in ("authored", "owner_observed"),
                 "invalid_diagnostic_value")
        _require(row["case_id"] not in identities, "duplicate_diagnostic_identity")
        key = (row["language"], _normalized(row["text"]))
        _require(key not in texts, "duplicate_diagnostic_text")
        _require(row["family"] not in families or families[row["family"]] == row["intent"],
                 "diagnostic_family_label_conflict")
        identities.add(row["case_id"])
        texts.add(key)
        families[row["family"]] = row["intent"]
    _require(all(sum(row["language"] == language and row["intent"] == label for row in cases)
                     == count // 8 for language in ("es", "pt") for label in LABELS),
             "unbalanced_diagnostic_population")
    state_cases = document.get("state_cases", [])
    _require(isinstance(state_cases, list) and len(state_cases) <= 64, "invalid_state_cases")
    for row in state_cases:
        _require(isinstance(row, dict) and set(row) == {
            "case_id", "language", "family", "text", "origin", "expected_behavior"}, "invalid_state_case")
        _require(_identity(row["case_id"]) and _identity(row["family"])
                 and row["language"] in ("es", "pt") and row["origin"] == "authored"
                 and _text(row["text"]) and _text(row["expected_behavior"], 2000), "invalid_state_case")
        _require(row["case_id"] not in identities, "duplicate_diagnostic_identity")
        identities.add(row["case_id"])
    return cases, len(state_cases)


def load_inputs(root, *, batch, include_candidate):
    _require(batch in BATCHES and type(include_candidate) is bool, "invalid_run_configuration")
    relative, count, purpose = BATCHES[batch]
    diagnostic, diagnostic_hash = _json_artifact(root, relative)
    cases, state_count = validate_cases(diagnostic, count=count, purpose=purpose)
    original, original_hash = _json_artifact(root, TRAIN)
    training = {"learned_v1": validate_training(original, expected_count=96)}
    hashes = {relative: diagnostic_hash, TRAIN: original_hash}
    if include_candidate:
        candidate, candidate_hash = _json_artifact(root, CANDIDATE)
        training["learned_short_v2"] = validate_training(candidate, expected_count=144)
        original_rows = {row["id"]: row for row in training["learned_v1"]}
        candidate_rows = {row["id"]: row for row in training["learned_short_v2"]}
        _require(all(candidate_rows.get(identity) == row for identity, row in original_rows.items()),
                 "candidate_changed_original_training")
        hashes[CANDIDATE] = candidate_hash
    diagnostic_texts = {(row["language"], _normalized(row["text"])) for row in cases}
    _require(all(not diagnostic_texts.intersection(
        (row["language"], _normalized(row["text"])) for row in rows)
        for rows in training.values()), "diagnostic_training_overlap")
    return cases, training, hashes, state_count


def create_run_directory(root, run_name):
    _require(isinstance(run_name, str) and RUN_NAME.fullmatch(run_name) is not None
             and run_name.casefold() not in RESERVED, "invalid_run_name")
    parent = checked_path(root, ".local/short_message_runs")
    directory = parent / run_name
    _require(directory.resolve() == directory and not directory.exists()
             and not directory.is_symlink(), "output_exists_or_redirected")
    parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    return directory


def _write_new(path, document):
    body = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(body)


def code_hashes(root):
    return {relative: _digest(read_bounded(checked_path(root, relative))) for relative in CODE_FILES}


def component_attempt(router, text, language):
    """Exactly one raw call, no retries or confidence threshold."""
    try:
        proposal = router(text, language)
        valid = (isinstance(proposal, IntentProposal) and isinstance(proposal.intent, str)
                 and proposal.intent in LABELS and type(proposal.matched) is bool
                 and (proposal.matched or proposal.intent == "unsupported")
                 and type(proposal.confidence) in (int, float)
                 and math.isfinite(proposal.confidence) and 0 <= proposal.confidence <= 1)
        return (proposal, None) if valid else (None, "invalid_component_proposal")
    except Exception:
        return None, "component_execution_failed"


def execute_run(root, *, run_name, protocol_sha256, include_candidate=False, batch="coverage"):
    _require(isinstance(protocol_sha256, str) and SHA256.fullmatch(protocol_sha256) is not None,
             "invalid_protocol_hash")
    directory = create_run_directory(root, run_name)
    try:
        protocol_hash = _digest(read_bounded(checked_path(root, PROTOCOL)))
        _require(protocol_hash == protocol_sha256, "protocol_hash_mismatch")
        cases, training, input_hashes, state_count = load_inputs(
            root, batch=batch, include_candidate=include_candidate)
        systems = SYSTEMS if include_candidate else SYSTEMS[:2]
        _write_new(directory / "manifest.json", {
            "schema_version": 1, "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": protocol_hash, "input_sha256": input_hashes,
            "code_sha256": code_hashes(root), "runtime_python": platform.python_version(),
            "batch": batch, "systems": list(systems), "cases_per_system": len(cases),
            "state_cases_not_scored_as_intents": state_count,
            "manifest_saved_before_fit_and_prediction": True,
            "source_data_final_or_old_development_read": False,
            "component_only": True, "workflow_performance_assessed": False,
            "retry_policy": "none", "threshold_tuning": False,
            "review_status": "pending_owner_spanish_and_fluent_portuguese_review",
        })
        routers, model_details = {"keyword_baseline": route_intent}, {}
        for system, rows in training.items():
            try:
                model = train_router(rows)
                routers[system] = model.route_intent
                model_details[system] = {"status": "fitted", "training_rows": model.training_row_count,
                                         "training_sha256": model.training_hash,
                                         "vocabulary_size": model.vocabulary_size}
            except Exception:
                routers[system] = None
                model_details[system] = {"status": "failed", "error_code": "model_fit_failed"}
        _write_new(directory / "models.json", model_details)
        scored = {system: [] for system in systems}
        errors = 0
        with (directory / "outcomes.jsonl").open("x", encoding="utf-8", newline="\n") as output:
            for case in sorted(cases, key=lambda row: row["case_id"]):
                for system in systems:
                    router = routers[system]
                    proposal, error = ((None, "model_fit_failed") if router is None else
                                       component_attempt(router, case["text"], case["language"]))
                    errors += int(error is not None)
                    public = {"case_id": case["case_id"], "language": case["language"],
                              "family": case["family"], "gold_intent": case["intent"], "system": system,
                              "proposal": None if proposal is None else asdict(proposal), "error_code": error}
                    output.write(json.dumps(public, sort_keys=True, allow_nan=False) + "\n")
                    output.flush()
                    scored[system].append({"gold_intent": case["intent"], "language": case["language"],
                                           "family_id": case["family"], "prediction": proposal,
                                           "error": error is not None})
        summary = {"schema_version": 1, "component_only": True,
                   "workflow_performance_assessed": False,
                   "state_cases_not_scored_as_intents": state_count,
                   "systems": {system: score_routes(rows) for system, rows in scored.items()}}
        _write_new(directory / "summary.json", summary)
        result = {"status": "completed_with_errors" if errors else "completed", "run_name": run_name,
                  "batch": batch, "cases_per_system": len(cases), "systems": len(systems),
                  "attempts": len(cases) * len(systems), "errors": errors,
                  "state_cases_not_scored_as_intents": state_count}
        _write_new(directory / "status.json", result)
        return result
    except Exception as error:
        code = str(error) if isinstance(error, DiagnosticError) else "diagnostic_execution_failed"
        _write_new(directory / "failure.json", {"status": "failed", "error_code": code,
                                                "partial_artifacts_preserved": True})
        raise DiagnosticError(code) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--include-candidate", action="store_true")
    parser.add_argument("--batch", choices=tuple(BATCHES), default="coverage")
    arguments = parser.parse_args(argv)
    try:
        result = execute_run(ROOT, run_name=arguments.run_name, protocol_sha256=arguments.protocol_sha256,
                             include_candidate=arguments.include_candidate, batch=arguments.batch)
    except Exception as error:
        code = str(error) if isinstance(error, DiagnosticError) else "diagnostic_execution_failed"
        print(json.dumps({"status": "failed", "error_code": code}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return int(result["errors"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
