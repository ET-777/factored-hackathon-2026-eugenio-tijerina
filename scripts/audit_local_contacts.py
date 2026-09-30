"""Read-only, stdlib audit of the three complete local contact CSV directories.

Writes aggregate-only public evidence and an ignored input-file manifest. Never
prints source text, identifiers, row samples, credentials, or unexpected labels.
No network, PDF, model, evaluation-fixture, or source-writing code is used.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("call_transcripts", "complaints", "call_center_interactions")
KEYS = {"call_transcripts": "transcript_id", "complaints": "complaint_id", "call_center_interactions": "interaction_id"}
COLUMNS = {
    "call_center_interactions": "interaction_id interaction_date process_date customer_id agent_id interaction_type channel contact_reason reason_category duration_seconds wait_time_seconds was_resolved requires_followup detected_sentiment sentiment_score customer_detected_accent agent_used_accent was_escalated mentioned_products has_transcript has_recording".split(),
    "call_transcripts": "transcript_id interaction_id process_date customer_id agent_id full_text customer_text agent_text detected_language detected_accent accent_confidence detected_keywords mentioned_entities detected_intents main_topics transcription_model audio_quality duration_seconds".split(),
    "complaints": "complaint_id creation_date process_date customer_id case_type category subcategory reception_channel affected_product_id related_branch_id origin_interaction_id description claimed_amount currency priority status assigned_agent_id assignment_date first_response_date resolution_date closing_date sla_breached resolution_days resolution compensation_granted resolution_satisfaction is_repeat_complainer".split(),
}
ALLOWED = set("False True true false 0 1 Transaccional Queja Producto Técnico Comercial Retención Complaint Claim Request Suggestion Service Technical Fees Branch Transactions Open Resolved Escalated Closed Rejected Medium Low High Critical es pt en consulta_general USD COP ARS MXN mexican colombian argentine neutral".split()) | {"In Process", "Calidad de servicio", "Problema con app", "Cobro indebido", "Cargo no reconocido", "Atención en sucursal"}
CATEGORY_COLUMNS = {
    "call_center_interactions": ("reason_category", "contact_reason", "was_resolved", "requires_followup", "was_escalated", "has_transcript"),
    "call_transcripts": ("detected_language", "detected_intents", "main_topics"),
    "complaints": ("case_type", "category", "subcategory", "status", "currency", "priority"),
}
NULL = "[null]"
WITHHELD = "[unrecognized value withheld]"


class AuditError(Exception):
    """Only safe, content-free categories are emitted."""


def is_null(value):
    return value is None or value.strip().casefold() in ("", "null", "none", "nan")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).digest()


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def public_label(value):
    return NULL if is_null(value) else value if value in ALLOWED else WITHHELD


def truth(value):
    return value.strip().casefold() in ("true", "1")


def false(value):
    return value.strip().casefold() in ("false", "0")


def valid_date(value):
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except (ValueError, TypeError):
        return None


def pct(numerator, denominator):
    return round(100 * numerator / denominator, 6) if denominator else None


def serial(value):
    if isinstance(value, (dict, Counter)):
        return {str(k): serial(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def text_profile(groups, rows, null_rows):
    conflicting = [counts for counts in groups.values() if len(counts) > 1]
    mode_count = sum(max(counts.values()) for counts in groups.values())
    labeled_rows = sum(sum(counts.values()) for counts in groups.values())
    return {
        "all_rows": rows, "null_or_blank_text_rows": null_rows,
        "normalized_nonblank_text_groups": len(groups),
        "rows_with_nonblank_text_and_topic": labeled_rows,
        "duplicate_excess_text_rows": labeled_rows - len(groups),
        "groups_with_conflicting_main_topics": len(conflicting),
        "rows_in_conflicting_groups": sum(sum(c.values()) for c in conflicting),
        "sum_of_per_text_group_majority_topic_counts": mode_count,
        "empirical_mode_label_agreement_pct": pct(mode_count, labeled_rows),
        "interpretation": "Empirical upper bound for one deterministic topic label per normalized text; descriptive label-conflict count, not trained or held-out model performance.",
    }


def scan(data_root: Path, max_seconds: int):
    started = time.monotonic()
    input_files, tables = [], {}
    transcript_refs = defaultdict(Counter)
    complaint_refs = defaultdict(Counter)
    text_groups = {name: defaultdict(Counter) for name in ("customer_text", "full_text")}
    text_month_groups = defaultdict(lambda: defaultdict(Counter))
    text_nulls = Counter()
    joins = Counter()
    reference_parent_duplicates = Counter()
    matched_transcript_parent_keys, matched_complaint_parent_keys = set(), set()
    for table in TABLES:
        paths = sorted((data_root / table).rglob("*.csv"))
        if not paths:
            raise AuditError("required_table_has_no_csv_files")
        profile = {"files": len(paths), "bytes": 0, "rows": 0, "malformed_rows": 0,
                   "null_counts": Counter(), "categories": {c: Counter() for c in CATEGORY_COLUMNS[table]},
                   "monthly": {}, "yearly": {}, "schema_versions": Counter(),
                   "schema_mismatch_files": 0, "files_with_transaction_id_column": 0,
                   "process_date_min": None, "process_date_max": None,
                   "invalid_process_date_rows": 0, "process_partition_date_mismatch_rows": 0,
                   "primary_key_null_rows": 0, "primary_key_duplicate_excess_rows": 0,
                   "exact_duplicate_excess_rows": 0, "columns": COLUMNS[table],
                   "category_first_last_seen": {}, "quality": Counter()}
        keys, row_hashes = set(), set()
        for path in paths:
            if time.monotonic() - started > max_seconds:
                raise AuditError("local_audit_runtime_cap_reached")
            before = path.stat()
            blob = path.read_bytes()  # One daily CSV partition at a time.
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise AuditError("source_file_changed_during_read")
            relative = path.relative_to(data_root).as_posix()
            sha256 = hashlib.sha256(blob).hexdigest()
            input_files.append({"relative_path": relative, "bytes": len(blob), "sha256": sha256})
            profile["bytes"] += len(blob)
            try:
                reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig"), newline=""), strict=True)
                fields = reader.fieldnames
                if not fields or len(fields) != len(set(fields)):
                    raise AuditError("invalid_csv_header")
                schema_hash = hashlib.sha256(json.dumps(fields).encode()).hexdigest()
                profile["schema_versions"][schema_hash] += 1
                if fields != COLUMNS[table]:
                    profile["schema_mismatch_files"] += 1
                if "transaction_id" in fields:
                    profile["files_with_transaction_id_column"] += 1
                if not set(COLUMNS[table]).issubset(fields):
                    raise AuditError("required_column_missing_from_csv")
                partition_match = re.search(r"year=(\d{4})/month=(\d{2})/day=(\d{2})/", relative)
                partition_day = "-".join(partition_match.groups()) if partition_match else None
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        profile["malformed_rows"] += 1
                        continue
                    profile["rows"] += 1
                    rowhash = digest(json.dumps([row[c] for c in fields], ensure_ascii=False, separators=(",", ":")))
                    if rowhash in row_hashes:
                        profile["exact_duplicate_excess_rows"] += 1
                    row_hashes.add(rowhash)
                    key = row[KEYS[table]]
                    keyhash = digest(key)
                    duplicate_key = keyhash in keys
                    if is_null(key):
                        profile["primary_key_null_rows"] += 1
                    else:
                        if duplicate_key:
                            profile["primary_key_duplicate_excess_rows"] += 1
                        keys.add(keyhash)
                    for column in COLUMNS[table]:
                        if is_null(row[column]):
                            profile["null_counts"][column] += 1
                    day = valid_date(row["process_date"])
                    if day:
                        profile["process_date_min"] = min(profile["process_date_min"] or day, day)
                        profile["process_date_max"] = max(profile["process_date_max"] or day, day)
                        if partition_day and day != partition_day:
                            profile["process_partition_date_mismatch_rows"] += 1
                    else:
                        profile["invalid_process_date_rows"] += 1
                    month = day[:7] if day else "invalid_date"
                    year = day[:4] if day else "invalid_date"
                    monthly = profile["monthly"].setdefault(month, {"rows": 0, "null_counts": Counter(), "categories": {c: Counter() for c in CATEGORY_COLUMNS[table]}, "quality": Counter()})
                    yearly = profile["yearly"].setdefault(year, {"rows": 0, "categories": {c: Counter() for c in CATEGORY_COLUMNS[table]}, "quality": Counter()})
                    monthly["rows"] += 1
                    yearly["rows"] += 1
                    for column in COLUMNS[table]:
                        if is_null(row[column]):
                            monthly["null_counts"][column] += 1
                    for column in CATEGORY_COLUMNS[table]:
                        label = public_label(row[column])
                        profile["categories"][column][label] += 1
                        monthly["categories"][column][label] += 1
                        yearly["categories"][column][label] += 1
                        tracking = profile["category_first_last_seen"].setdefault(column, {}).setdefault(label, {"first_process_date": day, "last_process_date": day})
                        if day:
                            tracking["first_process_date"] = min(tracking["first_process_date"] or day, day)
                            tracking["last_process_date"] = max(tracking["last_process_date"] or day, day)
                    quality = profile["quality"]
                    if table == "call_transcripts":
                        if not is_null(row["interaction_id"]):
                            transcript_refs[digest(row["interaction_id"])][(digest(row["customer_id"]), digest(row["agent_id"]), row["main_topics"])] += 1
                        for field in ("customer_text", "full_text"):
                            if is_null(row[field]):
                                text_nulls[field] += 1
                            elif not is_null(row["main_topics"]):
                                text_hash = digest(normalized(row[field]))
                                text_groups[field][text_hash][row["main_topics"]] += 1
                                if field == "customer_text":
                                    text_month_groups[month][text_hash][row["main_topics"]] += 1
                    elif table == "complaints":
                        if not is_null(row["origin_interaction_id"]):
                            complaint_refs[digest(row["origin_interaction_id"])][digest(row["customer_id"])] += 1
                        if row["subcategory"] == "Cargo no reconocido":
                            quality["unrecognized_charge_rows"] += 1
                            monthly["quality"]["unrecognized_charge_rows"] += 1
                            yearly["quality"]["unrecognized_charge_rows"] += 1
                        if row["subcategory"] == "Cobro indebido":
                            quality["undue_charge_rows"] += 1
                            monthly["quality"]["undue_charge_rows"] += 1
                            yearly["quality"]["undue_charge_rows"] += 1
                    else:
                        same_reason = row["contact_reason"] == row["reason_category"]
                        quality["contact_reason_equals_category_rows"] += int(same_reason)
                        if row["reason_category"] == "Transaccional":
                            for bucket in (quality, monthly["quality"], yearly["quality"]):
                                bucket["transactional_rows"] += 1
                                bucket["transactional_unresolved_rows"] += int(false(row["was_resolved"]))
                                bucket["transactional_escalated_rows"] += int(truth(row["was_escalated"]))
                                bucket["transactional_followup_rows"] += int(truth(row["requires_followup"]))
                                bucket["transactional_any_unresolved_escalated_followup_rows"] += int(false(row["was_resolved"]) or truth(row["was_escalated"]) or truth(row["requires_followup"]))
                        for refs, seen, prefix in ((transcript_refs, matched_transcript_parent_keys, "transcript"), (complaint_refs, matched_complaint_parent_keys, "complaint_origin")):
                            matches = refs.get(keyhash)
                            if not matches:
                                continue
                            if keyhash in seen:
                                reference_parent_duplicates[prefix] += 1
                                continue
                            seen.add(keyhash)
                            owner = digest(row["customer_id"])
                            for entry, count in matches.items():
                                joins[prefix + "_rows_matched_to_interaction"] += count
                                if prefix == "transcript":
                                    joins["transcript_matching_customer_rows"] += count * (entry[0] == owner)
                                    joins["transcript_matching_agent_rows"] += count * (entry[1] == digest(row["agent_id"]))
                                    joins["transcript_matching_topic_reason_rows"] += count * (entry[2] == row["reason_category"])
                                    joins["transcript_parent_has_transcript_true_rows"] += count * truth(row["has_transcript"])
                                else:
                                    joins["complaint_origin_matching_customer_rows"] += count * (entry == owner)
            except (UnicodeError, csv.Error):
                raise AuditError("csv_parse_failure") from None
        profile["primary_key_distinct_nonnull"] = len(keys)
        for col in COLUMNS[table]:
            profile["null_counts"].setdefault(col, 0)
        tables[table] = profile
        print(f"Completed {table}: {profile['rows']} rows, {len(paths)} files; source contents withheld.", flush=True)
    transcript_rows = tables["call_transcripts"]["rows"]
    joins["transcript_rows"] = transcript_rows
    joins["transcript_nonnull_interaction_rows"] = sum(sum(c.values()) for c in transcript_refs.values())
    joins["transcript_unmatched_nonnull_interaction_rows"] = joins["transcript_nonnull_interaction_rows"] - joins["transcript_rows_matched_to_interaction"]
    joins["complaint_rows"] = tables["complaints"]["rows"]
    joins["complaint_nonnull_origin_interaction_rows"] = sum(sum(c.values()) for c in complaint_refs.values())
    joins["complaint_unmatched_nonnull_origin_rows"] = joins["complaint_nonnull_origin_interaction_rows"] - joins["complaint_origin_rows_matched_to_interaction"]
    manifest = {"schema_version": 1, "source_root": str(data_root), "files": input_files}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    public_input_records = sorted(input_files, key=lambda x: x["relative_path"])
    corpus_hash = hashlib.sha256(json.dumps(public_input_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    summary = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "scope": "All local CSV files in call_center_interactions, call_transcripts, complaints; no other tables or final evaluation cases read.",
               "input_files": len(input_files), "input_bytes": sum(r["bytes"] for r in input_files),
               "input_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(), "ordered_input_corpus_sha256": corpus_hash,
               "hash_definition": "SHA256 of compact UTF-8 JSON sorted by relative_path, records with relative_path/bytes/sha256; detailed manifest is ignored locally.",
               "elapsed_seconds": round(time.monotonic() - started, 3), "tables": tables,
               "joins": joins, "reference_parent_duplicate_excess_rows": reference_parent_duplicates,
               "text_label_quality": {field: text_profile(groups, transcript_rows, text_nulls[field]) for field, groups in text_groups.items()},
               "monthly_customer_text_quality": {month: text_profile(groups, tables['call_transcripts']['monthly'][month]['rows'], tables['call_transcripts']['monthly'][month]['null_counts']['customer_text']) for month, groups in text_month_groups.items()},
               "limitations": ["Local bytes only; not compared to remote source or organizer checksums.", "Stored detected_language is not independent linguistic annotation.", "Topic conflict bounds are descriptive in-sample properties, not trained-model results.", "Process dates define month/year cuts; event timezone and late-arrival semantics are not established.", "No customer/product dimension ownership join performed here.", "Only reviewed categorical labels may appear in public output; unknown labels are withheld.", "Checks prove byte stability during individual reads, not source immutability after the audit."]}
    return serial(summary), manifest_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT.parent / "Data")
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        data_root = args.data_root.resolve()
        if data_root == ROOT or ROOT in data_root.parents:
            raise AuditError("source_must_be_outside_project_output_tree")
        summary, manifest = scan(data_root, args.max_seconds)
        (ROOT / "data/local_review").mkdir(parents=True, exist_ok=True)
        (ROOT / "evidence").mkdir(exist_ok=True)
        (ROOT / "data/local_review/contacts_manifest.json").write_bytes(manifest)
        (ROOT / "evidence/local_contacts_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("PASS: aggregate summary and ignored reproducibility manifest written. No source text or identifiers printed.")
        return 0
    except (AuditError, OSError) as exc:
        code = str(exc) if isinstance(exc, AuditError) else "local_filesystem_error"
        print("FAIL: " + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
