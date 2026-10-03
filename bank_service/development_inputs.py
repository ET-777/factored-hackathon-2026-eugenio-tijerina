"""Read-only validation of the reviewed authored development input bundle.

No routing, fitting, predictions, scoring, raw CSV/PDF reads, or final-case access.
``cohort_run`` is a direct child path of project/data/private_cohort; ``binding_run``
is a safe run-name string under project/data/routing_workloads. Only fixed authored
train/development files and evidence/routing_language_review.json may be read.

Review validation verifies the exact artifact/canonical-row commitments and stated
Spanish approval/PT-pending scope. It does not independently authenticate the
human conversation or claim Portuguese human validation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

from scripts import bind_routing_workload as binder


MAX_BINDING_BYTES = 2 * 1024 * 1024
MAX_REVIEW_BYTES = 256 * 1024
ROW_FIELDS = ("id", "family_id", "language", "text", "intent")
REVIEW_KEYS = {
    "schema_version", "review_date", "review_source", "owner_statement",
    "current_language_review_status", "approved_scope", "artifacts",
    "combined_spanish_review", "canonicalization", "approval_limits",
    "artifact_metadata_policy", "actions_in_this_review",
}
CANONICALIZATION = {
    "row_selection": "language_exactly_es",
    "row_fields": list(ROW_FIELDS),
    "row_order": "id_ascending",
    "encoding": "UTF-8",
    "json_sort_keys": True,
    "json_ensure_ascii": False,
    "json_separators": [",", ":"],
    "trailing_newline": False,
    "value_normalization": "none_exact_decoded_row_values",
}


class DevelopmentInputError(ValueError):
    """Fixed codes; private values and filenames are never interpolated."""


@dataclass(frozen=True, repr=False)
class DevelopmentInputs:
    """Validated snapshots; labels remain metadata, never inference context."""

    workloads: dict
    authored_hashes: dict
    records: dict
    cohort_hashes: dict
    binding_rows: list
    binding_hash: str
    review_hash: str


def _require(condition, code):
    if not condition:
        raise DevelopmentInputError(code)


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise DevelopmentInputError("invalid_json_value") from None


def _exact(actual, expected, code):
    # Serialized equality distinguishes True from 1 and 1.0 from 1, unlike ==.
    _require(_canonical(actual) == _canonical(expected), code)


def _fixed_path(root, relative):
    intended = root / relative
    _require(intended.resolve() == intended, "input_path_redirected")
    return intended


def _read_json(path, cap):
    try:
        body = binder._read_bounded(path, cap)
        document = binder._decode(body)
        _canonical(document)  # Also rejects finite-parser overflow (e.g. 1e400).
        return document, hashlib.sha256(body).hexdigest()
    except binder.BindingError:
        raise DevelopmentInputError("input_file_invalid") from None


def _checked_cohort_path(root, value):
    try:
        supplied = Path(value)
        intended = supplied if supplied.is_absolute() else root / supplied
        private_root = _fixed_path(root, "data/private_cohort")
        _require(intended.parent == private_root, "invalid_cohort_path")
        binder._validate_run_name(intended.name)
        _require(intended.resolve() == intended, "input_path_redirected")
        for name in ("manifest.json", "cohort.json", "quarantine.json"):
            path = intended / name
            _require(path.resolve() == path, "input_path_redirected")
            _require(path.is_file(), "cohort_input_unavailable")
        return intended
    except DevelopmentInputError:
        raise
    except (binder.BindingError, OSError, RuntimeError, TypeError, ValueError):
        raise DevelopmentInputError("invalid_cohort_path") from None


def _expected_binding(workloads, authored_hashes, records, cohort_hashes):
    rows, counts = binder.build_bindings(workloads, records)
    document = {
        "schema_version": 1,
        "status": "classification_context_only_no_workflow_executed",
        "review_status": binder.REVIEW_STATUS,
        "authored_artifacts": authored_hashes,
        "cohort_inputs": cohort_hashes,
        "cohort_records": len(records),
        "split_customer_and_transaction_disjointness": "enforced_across_bound_families",
        "unavailable_examples_retained": True,
        "scorer_metadata_is_system_input": False,
        "source_facts_asserted_by_authored_text": False,
        "routing_fitting_prediction_scoring_or_actions_executed": False,
        "summary": counts,
        "bindings": rows,
    }
    return document, rows


def _spanish_rows(document):
    return sorted(({field: row[field] for field in ROW_FIELDS}
                   for row in document["examples"] if row["language"] == "es"),
                  key=lambda row: row["id"])


def _review_artifact(split, rows, authored_hash):
    return {
        "artifact_review_status": binder.REVIEW_STATUS,
        "canonical_es_rows_sha256": hashlib.sha256(_canonical(rows)).hexdigest(),
        "es_examples": len(rows),
        "es_families": len({row["family_id"] for row in rows}),
        "es_intent_counts": dict(Counter(row["intent"] for row in rows)),
        "file_sha256": authored_hash["sha256"],
        "path": f"evaluation/routing_{split}.json",
    }


def _validate_review(review, workloads, authored_hashes):
    _require(isinstance(review, dict) and set(review) == REVIEW_KEYS, "invalid_review_schema")
    _require(type(review["schema_version"]) is int and review["schema_version"] == 1, "invalid_review_schema")
    _require(review["review_source"] == "explicit_owner_approval_in_project_conversation", "invalid_review_source")
    _require(isinstance(review["owner_statement"], str) and bool(review["owner_statement"].strip()), "invalid_review_source")
    try:
        _require(isinstance(review["review_date"], str)
                 and date.fromisoformat(review["review_date"]).isoformat() == review["review_date"],
                 "invalid_review_date")
    except (ValueError, TypeError):
        raise DevelopmentInputError("invalid_review_date") from None
    _exact(review["current_language_review_status"], {
        "spanish_owner_wording_and_intent_labels": "approved",
        "portuguese_fluent_human_review": "pending",
    }, "review_language_status_mismatch")
    _exact(review["canonicalization"], CANONICALIZATION, "review_canonicalization_mismatch")

    rows = {split: _spanish_rows(workloads[split]) for split in ("train", "development")}
    combined = sorted(rows["train"] + rows["development"], key=lambda row: row["id"])
    _require(bool(rows["train"]) and bool(rows["development"]), "review_scope_mismatch")
    expected_scope = {
        "language": "es", "fields": ["text", "intent"],
        "train_examples": len(rows["train"]), "development_examples": len(rows["development"]),
        "total_examples": len(combined), "reviewer_role": "project_owner",
        "independent_external_reviewer": False,
    }
    _exact(review["approved_scope"], expected_scope, "review_scope_mismatch")
    expected_artifacts = {split: _review_artifact(split, rows[split], authored_hashes[split])
                          for split in ("train", "development")}
    _exact(review["artifacts"], expected_artifacts, "review_artifact_commitment_mismatch")
    _exact(review["combined_spanish_review"], {
        "canonical_es_rows_sha256": hashlib.sha256(_canonical(combined)).hexdigest(),
        "es_examples": len(combined), "es_families": len({row["family_id"] for row in combined}),
    }, "combined_review_commitment_mismatch")

    limits = review["approval_limits"]
    _require(isinstance(limits, list) and bool(limits)
             and all(isinstance(item, str) and bool(item.strip()) for item in limits), "invalid_review_metadata")
    policy = review["artifact_metadata_policy"]
    _require(isinstance(policy, str) and bool(policy.strip()), "invalid_review_metadata")
    actions = review["actions_in_this_review"]
    _require(isinstance(actions, dict) and bool(actions)
             and all(isinstance(key, str) and bool(key) and value is False for key, value in actions.items()),
             "invalid_review_actions")


def load_development_inputs(project_root, cohort_run, binding_run):
    """Return hash-matched snapshots; reject the whole bundle on any mismatch.

    Reads only the fixed authored/review paths and bounded cohort/binding paths.
    Existing binding files are never rewritten. Typed full-document comparison
    verifies every stored context, scorer label, source reference, hash and count.
    """
    try:
        root = Path(project_root).resolve()
        try:
            binder._validate_run_name(binding_run)
        except binder.BindingError:
            raise DevelopmentInputError("invalid_binding_run") from None
        cohort_path = _checked_cohort_path(root, cohort_run)
        binding_path = _fixed_path(root, f"data/routing_workloads/{binding_run}/bindings.json")
        review_path = _fixed_path(root, "evidence/routing_language_review.json")
        workloads, authored_hashes = binder.load_workloads(root)
        records, cohort_hashes = binder.load_cohort_snapshot(cohort_path)
        expected_binding, expected_rows = _expected_binding(workloads, authored_hashes, records, cohort_hashes)
        binding, binding_hash = _read_json(binding_path, MAX_BINDING_BYTES)
        _exact(binding, expected_binding, "binding_document_mismatch")
        review, review_hash = _read_json(review_path, MAX_REVIEW_BYTES)
        _validate_review(review, workloads, authored_hashes)
        return DevelopmentInputs(workloads, authored_hashes, records, cohort_hashes,
                                 expected_rows, binding_hash, review_hash)
    except DevelopmentInputError:
        raise
    except binder.BindingError:
        raise DevelopmentInputError("binding_input_validation_failed") from None
    except (OSError, RuntimeError, TypeError, ValueError, KeyError, RecursionError):
        raise DevelopmentInputError("development_input_validation_failed") from None
