"""Strict read-only inputs for a separately authorized source-grounded benchmark.

Only the new fixed final_workflow_v1 paths and committed private-cohort snapshot
are readable here. The original sealed final, raw source files and PDFs are never
consulted. This module validates commitments; it performs no fitting or scoring.
Human language review and permission to score are separate runner gates.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from string import Formatter

from bank_service.access import Permission
from scripts import bind_routing_workload as binder


CASE_PATH = "data/final_workflow_v1/cases.json"
MANIFEST_PATH = "data/final_workflow_v1/manifest.json"
COHORT_RUN = "data/private_cohort/june17-v1"
MAX_CASE_BYTES = 512 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
CASE_FIELDS = frozenset({
    "id", "family_id", "language", "stratum", "intent", "component_text",
    "record_role", "permissions", "scenario", "steps", "expected",
})
EXPECTED_FIELDS = frozenset({
    "terminal", "writes", "purpose", "requires_record", "required_unknown",
    "required_statuses", "expected_error",
})
INTENTS = frozenset({"inquiry", "dispute_intake", "human_request", "unsupported"})
TERMINALS = frozenset({
    "answered", "intake", "handoff", "no_match", "unsupported", "declined",
    "cancelled", "access_denied", "write_failed", "assent_pending",
})
STATUSES = frozenset({
    "answered", "needs_filters", "needs_currency", "no_match", "ambiguous",
    "intake_offered", "intake_declined", "intake_ineligible", "confirmation_required",
    "action_verified", "unsupported", "greeting", "currency_interpretation",
    "date_interpreted", "cancelled", "language_changed", "access_denied",
    "handoff_unavailable", "handoff_offered", "handoff_declined", "needs_handoff_context",
    "handoff_context_cancelled", "case_unverified", "session_case_receipts", "needs_request",
})
PLACEHOLDERS = frozenset({"amount", "currency", "date_dmy", "date_iso", "transaction_id"})
PERMISSIONS = frozenset(permission.value for permission in Permission)
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,79}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MANIFEST_FIELDS = frozenset({
    "schema_version", "benchmark_id", "cases_sha256", "cases_bytes", "counts",
    "cohort_run", "cohort_inputs", "family_bindings",
})
BINDING_FIELDS = frozenset({"trusted_customer_id", "target_transaction_id", "snapshot_hash"})


class FinalWorkflowInputError(ValueError):
    """Fixed sanitized codes; no private inputs are interpolated."""


@dataclass(frozen=True, repr=False)
class FinalWorkflowInputs:
    cases: list[dict]
    records: Mapping
    family_bindings: Mapping
    cases_hash: str
    manifest_hash: str
    cohort_hashes: dict


def _require(condition, code):
    if not condition:
        raise FinalWorkflowInputError(code)


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise FinalWorkflowInputError("invalid_json_value") from None


def _exact(actual, expected, code):
    _require(_canonical(actual) == _canonical(expected), code)


def _text(value, code, *, placeholders=False):
    _require(isinstance(value, str) and 0 < len(value) <= 1000 and bool(value.strip()), code)
    try:
        value.encode("utf-8")
        if placeholders:
            for _, name, spec, conversion in Formatter().parse(value):
                _require(name is None or name in PLACEHOLDERS and not spec and conversion is None,
                         "invalid_placeholder")
    except FinalWorkflowInputError:
        raise
    except (UnicodeError, ValueError):
        raise FinalWorkflowInputError(code) from None


def _step(step):
    _require(isinstance(step, dict) and isinstance(step.get("kind"), str), "invalid_step")
    kind = step["kind"]
    if kind == "message":
        _require(set(step) == {"kind", "text"}, "invalid_step")
        _text(step["text"], "invalid_step_text", placeholders=True)
    elif kind in {"select_target", "select_foreign", "confirm_again", "cancel"}:
        _require(set(step) == {"kind"}, "invalid_step")
    elif kind in {"respond_offer", "confirm"}:
        key = "prepare" if kind == "respond_offer" else "confirmed"
        _require(set(step) == {"kind", key} and type(step[key]) is bool, "invalid_step")
    elif kind == "advance_clock":
        _require(set(step) == {"kind", "seconds"} and type(step["seconds"]) is int
                 and 1 <= step["seconds"] <= 1800, "invalid_step")
    elif kind == "set_fault":
        _require(set(step) == {"kind", "name"} and step["name"] == "write_failure", "invalid_step")
    else:
        raise FinalWorkflowInputError("invalid_step")


def _expected(expected):
    _require(isinstance(expected, dict) and set(expected) == EXPECTED_FIELDS, "invalid_expected")
    _require(isinstance(expected["terminal"], str) and expected["terminal"] in TERMINALS,
             "invalid_expected")
    _require(type(expected["writes"]) is int and expected["writes"] in (0, 1), "invalid_expected")
    _require(type(expected["requires_record"]) is bool, "invalid_expected")
    _require(expected["required_unknown"] is None or expected["required_unknown"] == "channel",
             "invalid_expected")
    if expected["purpose"] is not None:
        _text(expected["purpose"], "invalid_expected", placeholders=True)
    statuses = expected["required_statuses"]
    _require(isinstance(statuses, list) and len(statuses) <= 16
             and all(isinstance(value, str) and value in STATUSES for value in statuses)
             and len(set(statuses)) == len(statuses), "invalid_expected")
    error = expected["expected_error"]
    _require(error is None or isinstance(error, str) and ERROR_CODE.fullmatch(error) is not None,
             "invalid_expected")


def expected_counts(cases):
    """Return exact fixed counts used by the artifact commitment."""
    return {
        "cases": len(cases), "families": len({case["family_id"] for case in cases}),
        "service": sum(case["stratum"] == "service" for case in cases),
        "simulated_safety": sum(case["stratum"] == "simulated_safety" for case in cases),
        "by_language": dict(Counter(case["language"] for case in cases)),
        "service_intents": dict(Counter(case["intent"] for case in cases if case["stratum"] == "service")),
    }


def validate_cases(document):
    """Validate exactly 32 service and 16 simulated-safety bilingual cases."""
    _require(isinstance(document, dict) and set(document) == {"schema_version", "cases"}, "invalid_cases_document")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1,
             "invalid_cases_document")
    cases = document["cases"]
    _require(isinstance(cases, list) and len(cases) == 48, "invalid_case_count")
    identities, families, components = set(), {}, set()
    for case in cases:
        _require(isinstance(case, dict) and set(case) == CASE_FIELDS, "invalid_case_schema")
        for key in ("id", "family_id", "scenario"):
            _require(isinstance(case[key], str) and IDENTITY.fullmatch(case[key]) is not None, "invalid_case_identity")
        _require(case["id"] not in identities, "duplicate_case_id")
        identities.add(case["id"])
        _require(isinstance(case["language"], str) and case["language"] in {"es", "pt"}, "invalid_case_language")
        _require(isinstance(case["stratum"], str) and case["stratum"] in {"service", "simulated_safety"}, "invalid_case_stratum")
        if case["stratum"] == "service":
            _require(isinstance(case["intent"], str) and case["intent"] in INTENTS, "invalid_case_intent")
            _text(case["component_text"], "invalid_component_text", placeholders=True)
            key = (case["language"], binder._normalize(case["component_text"]))
            _require(key not in components, "duplicate_component_text")
            components.add(key)
        else:
            _require(case["intent"] is None and case["component_text"] is None, "invalid_safety_component")
        _require(isinstance(case["record_role"], str) and case["record_role"] in {"eligible_purchase", "withdrawal", "any"}, "invalid_record_role")
        permissions = case["permissions"]
        _require(isinstance(permissions, list) and 1 <= len(permissions) <= 3
                 and all(isinstance(value, str) and value in PERMISSIONS for value in permissions)
                 and len(set(permissions)) == len(permissions)
                 and Permission.READ_TRANSACTION.value in permissions, "invalid_case_permissions")
        steps = case["steps"]
        _require(isinstance(steps, list) and 1 <= len(steps) <= 16, "invalid_steps")
        for step in steps:
            _step(step)
        if case["stratum"] == "service":
            _require(sum(step["kind"] == "message" and step["text"] == case["component_text"]
                         for step in steps) == 1, "component_message_mismatch")
        _expected(case["expected"])
        families.setdefault(case["family_id"], []).append(case)
    _exact(expected_counts(cases), {
        "cases": 48, "families": 24, "service": 32, "simulated_safety": 16,
        "by_language": {"es": 24, "pt": 24}, "service_intents": dict.fromkeys(sorted(INTENTS), 8),
    }, "case_distribution_mismatch")
    strata = Counter()
    for pair in families.values():
        _require(len(pair) == 2 and {case["language"] for case in pair} == {"es", "pt"}, "invalid_family_languages")
        for key in ("stratum", "intent", "record_role", "scenario"):
            _exact(pair[0][key], pair[1][key], "inconsistent_family_metadata")
        _require(set(pair[0]["permissions"]) == set(pair[1]["permissions"]), "inconsistent_family_metadata")
        for key in EXPECTED_FIELDS - {"purpose"}:
            _exact(pair[0]["expected"][key], pair[1]["expected"][key], "inconsistent_family_expected")
        _require((pair[0]["expected"]["purpose"] is None) == (pair[1]["expected"]["purpose"] is None),
                 "inconsistent_family_expected")
        shapes = [[{key: value for key, value in step.items() if key != "text"}
                   for step in case["steps"]] for case in pair]
        _exact(shapes[0], shapes[1], "inconsistent_family_steps")
        strata[pair[0]["stratum"]] += 1
    _exact(dict(strata), {"service": 16, "simulated_safety": 8}, "family_distribution_mismatch")
    return cases


def _fixed_path(root, relative):
    intended = root / relative
    _require(intended.resolve() == intended, "input_path_redirected")
    return intended


def _read_json(path, cap):
    try:
        body = binder._read_bounded(path, cap)
        document = binder._decode(body)
        _canonical(document)
        return document, hashlib.sha256(body).hexdigest(), len(body)
    except binder.BindingError:
        raise FinalWorkflowInputError("input_file_invalid") from None


def load_final_inputs(project_root):
    """Read only the fixed new benchmark and its committed bounded cohort."""
    try:
        root = Path(project_root).resolve()
        cases_doc, cases_hash, cases_bytes = _read_json(_fixed_path(root, CASE_PATH), MAX_CASE_BYTES)
        cases = validate_cases(cases_doc)
        manifest, manifest_hash, _ = _read_json(_fixed_path(root, MANIFEST_PATH), MAX_MANIFEST_BYTES)
        _require(isinstance(manifest, dict) and set(manifest) == MANIFEST_FIELDS, "invalid_manifest")
        _require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1
                 and manifest["benchmark_id"] == "final_workflow_v1", "invalid_manifest")
        _exact(manifest["cases_sha256"], cases_hash, "cases_commitment_mismatch")
        _exact(manifest["cases_bytes"], cases_bytes, "cases_commitment_mismatch")
        _exact(manifest["counts"], expected_counts(cases), "manifest_counts_mismatch")
        _require(manifest["cohort_run"] == COHORT_RUN, "invalid_cohort_path")
        cohort_path = _fixed_path(root, COHORT_RUN)
        for name in ("manifest.json", "cohort.json", "quarantine.json"):
            _fixed_path(root, COHORT_RUN + "/" + name)
        records, cohort_hashes = binder.load_cohort_snapshot(cohort_path)
        _exact(manifest["cohort_inputs"], cohort_hashes, "cohort_commitment_mismatch")
        bindings = manifest["family_bindings"]
        _require(isinstance(bindings, dict) and set(bindings) == {case["family_id"] for case in cases}, "invalid_family_bindings")
        targets = set()
        for family, binding in bindings.items():
            _require(isinstance(binding, dict) and set(binding) == BINDING_FIELDS, "invalid_family_binding")
            target, owner, snapshot = (binding["target_transaction_id"], binding["trusted_customer_id"], binding["snapshot_hash"])
            _require(isinstance(target, str) and isinstance(owner, str) and isinstance(snapshot, str)
                     and SHA256.fullmatch(snapshot) is not None and target in records, "invalid_family_binding")
            _require(target not in targets, "duplicate_binding_target")
            targets.add(target)
            entry = records[target]
            _require(entry.record.customer_id == owner and binder._snapshot_hash(entry) == snapshot,
                     "binding_snapshot_mismatch")
            role = next(case["record_role"] for case in cases if case["family_id"] == family)
            _require(role == "any" or role == "eligible_purchase" and binder._eligible(entry)
                     or role == "withdrawal" and entry.record.transaction_type == "Withdrawal", "binding_role_mismatch")
        return FinalWorkflowInputs(cases, records, bindings, cases_hash, manifest_hash, cohort_hashes)
    except FinalWorkflowInputError:
        raise
    except binder.BindingError:
        raise FinalWorkflowInputError("cohort_validation_failed") from None
    except (OSError, RuntimeError, TypeError, ValueError, KeyError, RecursionError):
        raise FinalWorkflowInputError("final_input_validation_failed") from None
