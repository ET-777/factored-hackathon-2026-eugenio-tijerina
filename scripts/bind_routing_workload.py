"""Create private source context anchors, without routing or executing a workflow.

Only the fixed authored train/development artifacts and an explicitly supplied,
bounded cohort run are read. Final cases, raw CSVs, models and PDFs are not read.
CLI output contains aggregate counts or fixed error codes, never private values.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from bank_service.cohort_repository import (  # noqa: E402
    CohortLoadError, MAX_COHORT_BYTES, MAX_MANIFEST_BYTES,
    MAX_RECORDS_PER_TABLE, load_private_cohort, parse_cohort,
)
from bank_service.records import TransactionRecord  # noqa: E402
from bank_service.transactions import SourceReference, SourcedTransaction  # noqa: E402

MAX_ARTIFACT_BYTES = 256 * 1024
MAX_EXAMPLES = 256
LABELS = frozenset({"inquiry", "dispute_intake", "human_request", "unsupported"})
REVIEW_STATUS = "draft_pending_owner_and_portuguese_review"
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
RUN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"{p}{n}" for p in ("com", "lpt") for n in range(1, 10)}
ARTIFACT_KEYS = {"schema_version", "split", "provenance", "review_status", "examples"}
EXAMPLE_KEYS = {"id", "family_id", "language", "text", "intent"}


class BindingError(ValueError):
    """Internal callers use fixed codes; private input is never interpolated."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise BindingError("invalid_arguments")


def _require(condition, code):
    if not condition:
        raise BindingError(code)


def _normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "invalid_json")
        result[key] = value
    return result


def _reject_number(value):
    raise BindingError("invalid_json")


def _decode(body):
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_number)
    except BindingError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise BindingError("invalid_json") from None


def _read_bounded(path, limit):
    try:
        with path.open("rb") as stream:
            body = stream.read(limit + 1)
        _require(len(body) <= limit, "input_limit_exceeded")
        return body
    except OSError:
        raise BindingError("input_unavailable") from None


def validate_workload(document, split):
    _require(isinstance(document, dict) and set(document) == ARTIFACT_KEYS, "invalid_workload")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1,
             "invalid_workload")
    _require(document["split"] == split and document["provenance"] == "codex_authored"
             and document["review_status"] == REVIEW_STATUS, "invalid_workload")
    examples = document["examples"]
    _require(isinstance(examples, list) and 0 < len(examples) <= MAX_EXAMPLES, "invalid_workload")
    ids, texts, families = set(), set(), {}
    for example in examples:
        _require(isinstance(example, dict) and set(example) == EXAMPLE_KEYS, "invalid_example")
        for field in ("id", "family_id"):
            _require(isinstance(example[field], str) and ID_PATTERN.fullmatch(example[field]) is not None,
                     "invalid_example")
        _require(example["id"] not in ids, "duplicate_example_id")
        ids.add(example["id"])
        _require(isinstance(example["language"], str) and example["language"] in ("es", "pt"),
                 "invalid_example")
        _require(isinstance(example["intent"], str) and example["intent"] in LABELS, "invalid_example")
        text = example["text"]
        _require(isinstance(text, str) and 0 < len(text) <= 1000 and bool(text.strip()), "invalid_example")
        _require(not any(unicodedata.category(c) == "Cs" or ord(c) < 32 for c in text), "invalid_example")
        normalized = _normalize(text)
        _require(normalized not in texts, "duplicate_example_text")
        texts.add(normalized)
        family = example["family_id"]
        _require(family not in families or families[family] == example["intent"], "inconsistent_family_label")
        families[family] = example["intent"]
    return {"ids": ids, "texts": texts, "families": set(families)}


def validate_workload_pair(workloads):
    _require(isinstance(workloads, dict) and set(workloads) == {"train", "development"}, "invalid_workload_pair")
    groups = [validate_workload(workloads[split], split) for split in ("train", "development")]
    for group in ("ids", "texts", "families"):
        _require(not groups[0][group] & groups[1][group], "cross_split_overlap")


def load_workloads(project_root):
    project_root = Path(project_root).resolve()
    workloads, hashes = {}, {}
    for split in ("train", "development"):
        relative = f"evaluation/routing_{split}.json"
        intended_path = project_root / relative
        path = intended_path.resolve()
        _require(path.is_relative_to(project_root), "input_path_outside_project")
        _require(path == intended_path, "input_path_redirected")
        body = _read_bounded(path, MAX_ARTIFACT_BYTES)
        workloads[split] = _decode(body)
        hashes[split] = {"artifact": relative, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
    validate_workload_pair(workloads)
    return workloads, hashes


def load_cohort_snapshot(run_dir):
    """Match loader results to exact bounded input bytes before binding."""
    try:
        run_dir = Path(run_dir).resolve()
        paths = {name: (run_dir / name).resolve() for name in ("manifest.json", "cohort.json")}
        _require(all(path.parent == run_dir for path in paths.values()), "invalid_cohort_path")
        limits = {"manifest.json": MAX_MANIFEST_BYTES, "cohort.json": MAX_COHORT_BYTES}
        before = {name: _read_bounded(path, limits[name]) for name, path in paths.items()}
        records = load_private_cohort(run_dir)
        _require(0 < len(records) <= MAX_RECORDS_PER_TABLE, "invalid_cohort")
        after = {name: _read_bounded(path, limits[name]) for name, path in paths.items()}
        _require(before == after, "cohort_changed_during_read")
        manifest, payload = _decode(before["manifest.json"]), _decode(before["cohort.json"])
        _require(parse_cohort(payload, manifest) == records, "cohort_snapshot_mismatch")
        source_hashes = []
        for source in manifest["sources"]:
            sha = source.get("file_sha256")
            byte_count = source.get("byte_count")
            _require(isinstance(sha, str) and SHA256.fullmatch(sha) is not None
                     and type(byte_count) is int and byte_count >= 0, "missing_cohort_source_hash")
            source_hashes.append({"file": source["file"], "sha256": sha,
                                  "bytes": byte_count, "row_count": source["row_count"]})
        hashes = {name: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
                  for name, body in before.items()}
        hashes["original_source_hashes_from_manifest"] = source_hashes
        hashes["original_source_files_rehashed"] = False
        return records, hashes
    except BindingError:
        raise
    except (CohortLoadError, OSError, RuntimeError, TypeError, ValueError, KeyError):
        raise BindingError("cohort_validation_failed") from None


def _snapshot_hash(entry):
    """Same canonical record+source digest as the runtime action snapshot."""
    values = {}
    for key, value in asdict(entry.record).items():
        if isinstance(value, Decimal):
            _require(value.is_finite(), "invalid_cohort")
            values[key] = str(value)
        elif isinstance(value, (date, datetime)):
            values[key] = value.isoformat()
        elif value is None or isinstance(value, str):
            values[key] = value
        else:
            raise BindingError("invalid_cohort")
    body = json.dumps({"record": values, "sources": [asdict(ref) for ref in entry.sources]},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _eligible(entry):
    return entry.record.transaction_type == "Purchase" and entry.record.transaction_status in ("Approved", "Pending")


def _constraint(family, intent):
    if "cash-not-dispensed" in family:
        _require(intent == "dispute_intake", "invalid_family_constraint")
        return "withdrawal"
    return "eligible_purchase" if intent == "dispute_intake" else "context_only"


def build_bindings(workloads, records):
    """Pure deterministic matching; every example survives unavailable anchors."""
    validate_workload_pair(workloads)
    _require(isinstance(records, Mapping) and 0 < len(records) <= MAX_RECORDS_PER_TABLE, "invalid_cohort")
    for key, entry in records.items():
        _require(isinstance(entry, SourcedTransaction) and isinstance(entry.record, TransactionRecord)
                 and key == entry.record.transaction_id and isinstance(entry.sources, tuple)
                 and bool(entry.sources) and all(isinstance(ref, SourceReference) for ref in entry.sources),
                 "invalid_cohort")
    families = {}
    for split in ("train", "development"):
        for example in workloads[split]["examples"]:
            family = example["family_id"]
            families.setdefault(family, {"split": split, "intent": example["intent"],
                                         "constraint": _constraint(family, example["intent"])})
    candidates = {}
    for family, meta in families.items():
        candidates[family] = {}
        for entry in sorted(records.values(), key=lambda e: (e.record.customer_id, e.record.transaction_id)):
            constraint = meta["constraint"]
            compatible = (constraint == "context_only"
                          or constraint == "withdrawal" and entry.record.transaction_type == "Withdrawal"
                          or constraint == "eligible_purchase" and _eligible(entry))
            if compatible:
                candidates[family].setdefault(entry.record.customer_id, entry)

    # Customer-level augmenting matching avoids an arbitrary early choice consuming
    # the only compatible owner for a later family. One owner implies one record,
    # making both customer and transaction anchors disjoint across all families.
    owner_family, family_owner = {}, {}

    def assign(family, visited):
        for owner in sorted(candidates[family]):
            if owner in visited:
                continue
            visited.add(owner)
            previous = owner_family.get(owner)
            if previous is None or assign(previous, visited):
                owner_family[owner] = family
                family_owner[family] = owner
                return True
        return False

    priority = {"withdrawal": 0, "eligible_purchase": 1, "context_only": 2}
    ordered = sorted(families, key=lambda f: (priority[families[f]["constraint"]],
                                             0 if families[f]["split"] == "train" else 1, f))
    for family in ordered:
        assign(family, set())
    rows = []
    for split in ("train", "development"):
        for example in workloads[split]["examples"]:
            family = example["family_id"]
            owner = family_owner.get(family)
            entry = candidates[family][owner] if owner is not None else None
            available = entry is not None
            rows.append({
                "example_id": example["id"], "family_id": family, "language": example["language"], "split": split,
                "binding_status": "bound_context_only" if available else "binding_unavailable",
                "binding_code": "compatible_disjoint_anchor" if available else "no_disjoint_compatible_anchor",
                "system_context": ({"trusted_customer_id": entry.record.customer_id,
                                    "target_transaction_id": entry.record.transaction_id} if available else None),
                "source_references": [asdict(ref) for ref in entry.sources] if available else [],
                "snapshot_hash": _snapshot_hash(entry) if available else None,
                "scorer_metadata": {"intent": example["intent"],
                                    "expected_synthetic_intake_eligible": _eligible(entry) if available else None,
                                    "eligibility_is_not_action_authorization": True,
                                    "authored_allegations_unverified": True,
                                    "constraint": families[family]["constraint"]},
            })
    counts = {split: {"examples": sum(row["split"] == split for row in rows),
                      "families": sum(meta["split"] == split for meta in families.values()),
                      "bound_examples": sum(row["split"] == split and row["system_context"] is not None for row in rows),
                      "unavailable_examples": sum(row["split"] == split and row["system_context"] is None for row in rows),
                      "bound_families": sum(meta["split"] == split and family in family_owner for family, meta in families.items())}
              for split in ("train", "development")}
    return rows, counts


def _validate_run_name(value):
    _require(isinstance(value, str) and RUN_PATTERN.fullmatch(value) is not None
             and value.casefold() not in RESERVED_NAMES, "invalid_run_name")


def write_private_bindings(project_root, run_name, document):
    _validate_run_name(run_name)
    try:
        project_root = Path(project_root).resolve()
        intended_private_root = project_root / "data/routing_workloads"
        private_root = intended_private_root.resolve()
        _require(private_root.is_relative_to(project_root) and private_root != project_root,
                 "output_path_outside_project")
        _require(private_root == intended_private_root, "output_path_redirected")
        run_dir = private_root / run_name
        _require(run_dir.resolve() == run_dir, "output_path_redirected")
        _require(not run_dir.exists() and not run_dir.is_symlink(), "output_exists")
        body = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
        private_root.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(exist_ok=False)
        with (run_dir / "bindings.json").open("xb") as stream:
            stream.write(body)
        return run_dir / "bindings.json"
    except BindingError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError, RuntimeError):
        raise BindingError("output_write_failed") from None


def create_bindings(cohort_run, run_name, *, project_root=ROOT):
    _validate_run_name(run_name)
    project_root = Path(project_root).resolve()
    workloads, authored_hashes = load_workloads(project_root)
    records, cohort_hashes = load_cohort_snapshot(cohort_run)
    rows, counts = build_bindings(workloads, records)
    document = {"schema_version": 1, "status": "classification_context_only_no_workflow_executed",
                "review_status": REVIEW_STATUS, "authored_artifacts": authored_hashes,
                "cohort_inputs": cohort_hashes, "cohort_records": len(records),
                "split_customer_and_transaction_disjointness": "enforced_across_bound_families",
                "unavailable_examples_retained": True,
                "scorer_metadata_is_system_input": False,
                "source_facts_asserted_by_authored_text": False,
                "routing_fitting_prediction_scoring_or_actions_executed": False,
                "summary": counts, "bindings": rows}
    write_private_bindings(project_root, run_name, document)
    return {"status": "bindings_created_no_execution", "cohort_records": len(records), "counts": counts}


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("--cohort-run", type=Path, required=True)
        parser.add_argument("--run-name", required=True)
        args = parser.parse_args(argv)
        result = create_bindings(args.cohort_run, args.run_name)
        print(json.dumps(result, sort_keys=True))
        return 0
    except BindingError as error:
        print(json.dumps({"status": "binding_failed", "code": str(error)}), file=sys.stderr)
        return 2
    except Exception:
        # Final CLI privacy boundary: unexpected exceptions must not expose a
        # traceback containing private paths, identifiers, or source values.
        print('{"status":"binding_failed","code":"unexpected_binding_error"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
