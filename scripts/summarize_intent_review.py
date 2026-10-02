"""Publish aggregate counts from an explicitly bound private draft label review.

No source wording, group IDs, row references or free-text rationale is exported.
This produces feasibility evidence, never model performance or human validation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LABELS = ("inquiry", "dispute_intake", "human_request", "unsupported", "uncertain", "unusable")


class ReviewError(ValueError):
    """Fixed content-free codes only."""


def _count(value):
    if type(value) is not int or value < 0:
        raise ReviewError("invalid_count")
    return value


def build_summary(inventory: dict, review: dict, inventory_sha256: str) -> dict:
    if not isinstance(inventory, dict) or not isinstance(review, dict):
        raise ReviewError("invalid_document")
    if review.get("inventory_sha256") != inventory_sha256:
        raise ReviewError("review_inventory_mismatch")
    if inventory.get("source_labels_used") is not False or inventory.get("keyword_router_used") is not False:
        raise ReviewError("annotation_input_contamination")
    if review.get("human_review_status") != "pending":
        raise ReviewError("unsupported_review_status")
    groups, annotations = inventory.get("groups"), review.get("groups")
    if not isinstance(groups, list) or not isinstance(annotations, list) or not 1 <= len(groups) <= 64:
        raise ReviewError("invalid_groups")
    by_id = {}
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("group_id"), str):
            raise ReviewError("invalid_group")
        identity = group["group_id"]
        if not re.fullmatch(r"SRC-[a-f0-9]{64}", identity) or identity in by_id:
            raise ReviewError("invalid_group_identity")
        by_id[identity] = group
    seen, families, totals, weighted = set(), defaultdict(set), Counter(), Counter()
    request_hashes, tail_rows = set(), 0
    for item in annotations:
        if not isinstance(item, dict):
            raise ReviewError("invalid_annotation")
        identity, label, family = item.get("group_id"), item.get("label"), item.get("family_id")
        if not isinstance(identity, str) or identity not in by_id or identity in seen:
            raise ReviewError("annotation_coverage_mismatch")
        if not isinstance(label, str) or label not in LABELS:
            raise ReviewError("invalid_label")
        if not isinstance(family, str) or not re.fullmatch(r"FAM-[A-Z0-9-]{1,60}", family):
            raise ReviewError("invalid_family")
        group = by_id[identity]
        text, end = group.get("representative_customer_text"), item.get("first_request_end")
        if not isinstance(text, str) or type(end) is not int or not 0 < end <= len(text):
            raise ReviewError("invalid_request_span")
        count = _count(group.get("subset_row_count"))
        if not count:
            raise ReviewError("empty_text_group")
        request_hashes.add(hashlib.sha256(text[:end].encode("utf-8")).hexdigest())
        tail_rows += count if text[end:].strip() else 0
        seen.add(identity)
        totals[label] += 1
        weighted[label] += count
        families[label].add(family)
    if seen != set(by_id):
        raise ReviewError("annotation_coverage_mismatch")
    counts = inventory.get("summary")
    if not isinstance(counts, dict):
        raise ReviewError("invalid_inventory_summary")
    if sum(weighted.values()) != _count(counts.get("nonblank_customer_text_rows")):
        raise ReviewError("row_reconciliation_failed")
    if len(groups) != _count(counts.get("distinct_text_groups")) or (
        counts["nonblank_customer_text_rows"] + _count(counts.get("missing_customer_text_rows"))
        != _count(counts.get("rows_read"))
    ):
        raise ReviewError("row_reconciliation_failed")
    languages = counts.get("known_language_rows")
    if not isinstance(languages, dict):
        raise ReviewError("invalid_language_summary")
    language_counts = {code: _count(languages.get(code)) for code in ("es", "pt", "en")}
    other_language_rows = _count(counts.get("other_language_rows"))
    missing_language_rows = _count(counts.get("missing_language_rows"))
    if sum(language_counts.values()) + other_language_rows + missing_language_rows != counts["rows_read"]:
        raise ReviewError("row_reconciliation_failed")
    return {
        "schema_version": 1,
        "scope": "fixed_seven_partition_source_intent_feasibility",
        "inventory_sha256": inventory_sha256,
        "review_status": "Codex draft labels; human validation pending",
        "source_labels_used": False,
        "keyword_router_predictions_used": False,
        "subset": {key: _count(counts.get(key)) for key in (
            "files_read", "bytes_read", "rows_read", "nonblank_customer_text_rows",
            "missing_customer_text_rows", "distinct_text_groups")},
        "stored_language_rows": language_counts,
        "other_language_rows": other_language_rows,
        "missing_language_rows": missing_language_rows,
        "class_support": {label: {
            "normalized_text_groups": totals[label],
            "reviewed_families": len(families[label]),
            "subset_rows": weighted[label],
        } for label in LABELS},
        "distinct_reviewed_first_request_spans": len(request_hashes),
        "rows_with_appended_customer_followups": tail_rows,
        "distinct_reviewed_families": len(set().union(*families.values())),
        "performance_results": None,
        "limitations": [
            "Counts describe a fixed local subset, not full-corpus class prevalence.",
            "Codex semantic annotations and family assignments are not human-validated labels.",
            "Repeated rows and appended followups are not independent first-turn examples.",
            "No model fitting, splits, threshold selection or final scoring were performed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.run_name):
            raise ReviewError("invalid_run_name")
        private_root = (ROOT / "data/intent_review").resolve()
        run = (private_root / args.run_name).resolve(strict=True)
        if not run.is_relative_to(private_root) or any((run / name).is_symlink() for name in ("inventory.json", "labels.json")):
            raise ReviewError("private_path_escape")
        inventory_path, labels_path = run / "inventory.json", run / "labels.json"
        if inventory_path.stat().st_size > 2 * 1024 * 1024 or labels_path.stat().st_size > 1024 * 1024:
            raise ReviewError("private_document_too_large")
        inventory_bytes, review_bytes = inventory_path.read_bytes(), labels_path.read_bytes()
        summary = build_summary(json.loads(inventory_bytes), json.loads(review_bytes), hashlib.sha256(inventory_bytes).hexdigest())
        summary["review_sha256"] = hashlib.sha256(review_bytes).hexdigest()
        destination = ROOT / "evidence/source_intent_inventory_summary.json"
        if destination.is_symlink():
            raise ReviewError("public_output_symlink")
        destination.parent.mkdir(exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(summary, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        print("PASS: aggregate-only intent feasibility summary written.")
        return 0
    except (ReviewError, OSError, ValueError, TypeError, KeyError):
        print("FAIL: intent_review_summary_refused")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
