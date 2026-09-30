"""Read-only local source audit. Public output is aggregate-only; no source writes.

Uses stdlib Python and a private on-disk key index under ignored data/local_review.
It never reads evaluation/final_private, credentials, PDFs, or the network.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TX_COLUMNS = "transaction_id transaction_date process_date product_id customer_id transaction_type transaction_category amount currency amount_usd channel branch_id merchant_name merchant_category transaction_country transaction_city transaction_status response_code is_fraud fraud_score latitude longitude".split()
TX_REQUIRED = "transaction_id transaction_date process_date product_id customer_id transaction_type amount currency channel transaction_country transaction_status is_fraud".split()
PUBLIC_VALUES = set("Withdrawal Transfer Purchase Payment Deposit Adjustment USD COP ARS MXN Approved Declined Pending Reversed México Mexico Colombia Argentina Spain USA Brazil False True Active Inactive Suspended Closed Blocked".split())
DIM_COUNT_FIELDS = "rows malformed_rows null_primary_keys duplicate_key_excess_rows exact_duplicate_excess_rows additional_conflicting_versions invalid_temporal_date_rows".split()
TX_COUNT_FIELDS = "rows malformed_rows owner_comparison_eligible_rows transaction_timestamps_without_timezone event_date_differs_from_process_date duplicate_key_excess_rows exact_duplicate_excess_rows additional_conflicting_versions required_field_missing_rows null_primary_key_rows customer_reference_missing_rows customer_reference_ambiguous_rows product_reference_missing_rows product_reference_ambiguous_rows transaction_product_owner_mismatch_rows transaction_product_currency_mismatch_rows product_owner_customer_missing_rows product_owner_customer_ambiguous_rows invalid_transaction_date_rows invalid_process_date_rows transaction_before_current_product_opening_rows transaction_before_current_customer_registration_rows amount_missing_rows amount_invalid_rows amount_usd_invalid_rows purchase_rows purchase_merchant_missing_rows rows_with_one_or_more_checked_issues rows_without_checked_issues_before_conflicting_id_quarantine".split()


def explicit_counts(counts, fields):
    return {**{field: 0 for field in fields}, **dict(counts)}


def null(value):
    return value.strip().casefold() in ("", "null", "none", "nan")


def category(value):
    return value if value in PUBLIC_VALUES else "[unrecognized value withheld]"


def row_hash(row):
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode()).digest()


def file_metadata(path, base):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("source_changed_during_hash")
    return {"relative_path": path.relative_to(base).as_posix(), "size_bytes": after.st_size, "mtime_ns": after.st_mtime_ns, "sha256": digest.hexdigest()}


def date_or_none(value):
    try:
        return dt.datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return None


def load_dimension(path, base, table, primary, required):
    metadata = file_metadata(path, base)
    records, alternate_hashes, conflicting = {}, defaultdict(set), set()
    counts, nulls, enums = Counter(), Counter(), defaultdict(Counter)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        header = reader.fieldnames
        if not header or primary not in header or not set(required).issubset(header):
            raise RuntimeError("required_dimension_columns_missing")
        for row in reader:
            counts["rows"] += 1
            if None in row or any(v is None for v in row.values()):
                counts["malformed_rows"] += 1
                continue
            for field in required:
                nulls[field] += null(row[field])
            identifier = row[primary]
            temporal_field = "opening_date" if table == "products" else "registration_date"
            counts["invalid_temporal_date_rows"] += date_or_none(row[temporal_field]) is None
            if null(identifier):
                counts["null_primary_keys"] += 1
                continue
            digest = row_hash([row[c] for c in header])
            if identifier in records:
                counts["duplicate_key_excess_rows"] += 1
                if digest == records[identifier]["digest"] or digest in alternate_hashes[identifier]:
                    counts["exact_duplicate_excess_rows"] += 1
                else:
                    counts["additional_conflicting_versions"] += 1
                    alternate_hashes[identifier].add(digest)
                    conflicting.add(identifier)
            else:
                records[identifier] = {"digest": digest}
                if table == "products":
                    records[identifier].update(owner=row["customer_id"], currency=row["currency"], opening_date=date_or_none(row["opening_date"]))
                else:
                    records[identifier]["registration_date"] = date_or_none(row["registration_date"])
            for field in (("currency", "product_status") if table == "products" else ("country", "customer_status")):
                enums[field][category(row[field])] += 1
    if (path.stat().st_size, path.stat().st_mtime_ns) != (metadata["size_bytes"], metadata["mtime_ns"]):
        raise RuntimeError("source_changed_during_dimension_scan")
    summary = {"rows": counts["rows"], "column_names": header, "counts": explicit_counts(counts, DIM_COUNT_FIELDS), "distinct_nonnull_primary_keys": len(records), "conflicting_primary_keys": len(conflicting), "required_null_counts": dict(nulls), "categories": dict(enums)}
    return records, conflicting, summary, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    base = args.source.resolve()
    started = time.monotonic()
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    session = ROOT / "data" / "local_review" / ("transactions_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
    session.mkdir(parents=True, exist_ok=False)
    customer_required = "customer_id document_number document_type first_name last_name date_of_birth city state country segment registration_date registration_branch_id customer_status last_updated accepts_marketing".split()
    product_required = "product_id customer_id product_type product_number currency current_balance opening_date opening_branch_id product_status opening_channel has_linked_app last_updated".split()
    customers, bad_customers, customer_summary, customer_meta = load_dimension(base / "customers.csv", base, "customers", "customer_id", customer_required)
    products, bad_products, product_summary, product_meta = load_dimension(base / "products.csv", base, "products", "product_id", product_required)
    product_summary["owner_customer_missing_distinct_products"] = sum(p["owner"] not in customers for p in products.values())
    product_summary["owner_customer_ambiguous_distinct_products"] = sum(p["owner"] in bad_customers for p in products.values())
    print(json.dumps({"phase": "dimensions_complete", "customers": customer_summary["rows"], "products": product_summary["rows"], "conflicting_customers": len(bad_customers), "conflicting_products": len(bad_products), "products_with_missing_owner_customer": product_summary["owner_customer_missing_distinct_products"]}), flush=True)
    manifest = {"audit_started_at_utc": started_utc, "source_directory": str(base), "files": [customer_meta, product_meta]}
    database = sqlite3.connect(session / "transaction_key_index.sqlite")
    database.execute("PRAGMA journal_mode=OFF")
    database.execute("PRAGMA synchronous=OFF")
    database.execute("PRAGMA temp_store=MEMORY")
    database.execute("CREATE TABLE seen (id TEXT PRIMARY KEY, digest BLOB NOT NULL) WITHOUT ROWID")
    insert = database.cursor()
    lookup = database.cursor()
    tx_conflicts, tx_alternate_hashes = set(), defaultdict(set)
    totals, nulls, categories = Counter(), Counter(), defaultdict(Counter)
    by_year, by_date = defaultdict(Counter), defaultdict(Counter)
    schema_counts = Counter()
    money_by_currency = defaultdict(Counter)
    files = sorted((base / "transactions").rglob("*.csv"))
    if not files:
        raise RuntimeError("no_transaction_csvs")
    for file_number, path in enumerate(files, 1):
        before = path.stat()
        body = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("source_changed_during_transaction_read")
        manifest["files"].append({"relative_path": path.relative_to(base).as_posix(), "size_bytes": len(body), "mtime_ns": after.st_mtime_ns, "sha256": hashlib.sha256(body).hexdigest()})
        reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader)
        schema_counts[hashlib.sha256(json.dumps(header).encode()).hexdigest()] += 1
        if header != TX_COLUMNS:
            raise RuntimeError("transaction_schema_differs_from_audited_schema")
        index = {c: i for i, c in enumerate(header)}
        required_indices = [(field, index[field]) for field in TX_REQUIRED]
        for row in reader:
            totals["rows"] += 1
            if len(row) != len(header):
                totals["malformed_rows"] += 1
                continue
            get = lambda field: row[index[field]]
            process_date = date_or_none(get("process_date")) or "[invalid date]"
            year = process_date[:4] if process_date != "[invalid date]" else "unknown"
            day_counts, year_counts = by_date[process_date], by_year[year]
            day_counts["rows"] += 1
            year_counts["rows"] += 1
            issues = []
            missing_required = False
            for field, field_index in required_indices:
                if null(row[field_index]):
                    nulls[field] += 1
                    missing_required = True
            if missing_required:
                issues.append("required_field_missing_rows")
            identifier = get("transaction_id")
            digest = row_hash(row)
            if null(identifier):
                issues.append("null_primary_key_rows")
            else:
                insert.execute("INSERT OR IGNORE INTO seen (id, digest) VALUES (?, ?)", (identifier, digest))
                if insert.rowcount == 0:
                    totals["duplicate_key_excess_rows"] += 1
                    first_digest = lookup.execute("SELECT digest FROM seen WHERE id=?", (identifier,)).fetchone()[0]
                    if first_digest == digest or digest in tx_alternate_hashes[identifier]:
                        totals["exact_duplicate_excess_rows"] += 1
                    else:
                        totals["additional_conflicting_versions"] += 1
                        tx_conflicts.add(identifier)
                        tx_alternate_hashes[identifier].add(digest)
            customer_id, product_id = get("customer_id"), get("product_id")
            customer = customers.get(customer_id)
            product = products.get(product_id)
            if customer is None:
                issues.append("customer_reference_missing_rows")
            if customer_id in bad_customers:
                issues.append("customer_reference_ambiguous_rows")
            if product is None:
                issues.append("product_reference_missing_rows")
            if product_id in bad_products:
                issues.append("product_reference_ambiguous_rows")
            if product is not None and product_id not in bad_products:
                totals["owner_comparison_eligible_rows"] += 1
                if product["owner"] != customer_id:
                    issues.append("transaction_product_owner_mismatch_rows")
                if product["currency"] != get("currency"):
                    issues.append("transaction_product_currency_mismatch_rows")
                if product["owner"] not in customers:
                    issues.append("product_owner_customer_missing_rows")
                elif product["owner"] in bad_customers:
                    issues.append("product_owner_customer_ambiguous_rows")
            event_date = None
            try:
                timestamp = dt.datetime.fromisoformat(get("transaction_date"))
                event_date = timestamp.date().isoformat()
                totals["transaction_timestamps_without_timezone"] += timestamp.tzinfo is None
                totals["event_date_differs_from_process_date"] += event_date != process_date
            except ValueError:
                issues.append("invalid_transaction_date_rows")
            if process_date == "[invalid date]":
                issues.append("invalid_process_date_rows")
            if event_date and product and product.get("opening_date") and event_date < product["opening_date"]:
                issues.append("transaction_before_current_product_opening_rows")
            if event_date and customer and customer.get("registration_date") and event_date < customer["registration_date"]:
                issues.append("transaction_before_current_customer_registration_rows")
            for field in ("currency", "transaction_type", "transaction_status", "transaction_country", "is_fraud"):
                value = category(get(field))
                categories[field][value] += 1
                if field in ("currency", "is_fraud", "transaction_status"):
                    year_counts[field + ":" + value] += 1
                    day_counts[field + ":" + value] += 1
            currency = category(get("currency"))
            for field in ("amount", "amount_usd"):
                value = get(field)
                if null(value):
                    money_by_currency[currency][field + "_missing"] += 1
                    if field == "amount":
                        issues.append("amount_missing_rows")
                    continue
                try:
                    number = Decimal(value)
                    if not number.is_finite():
                        raise InvalidOperation
                    money_by_currency[currency][field + "_valid"] += 1
                    money_by_currency[currency][field + "_negative"] += number < 0
                    money_by_currency[currency][field + "_zero"] += number == 0
                except InvalidOperation:
                    money_by_currency[currency][field + "_invalid"] += 1
                    issues.append(field + "_invalid_rows")
            if get("transaction_type") == "Purchase":
                totals["purchase_rows"] += 1
                if null(get("merchant_name")):
                    totals["purchase_merchant_missing_rows"] += 1
            if issues:
                totals["rows_with_one_or_more_checked_issues"] += 1
            else:
                totals["rows_without_checked_issues_before_conflicting_id_quarantine"] += 1
            for issue in issues:
                totals[issue] += 1
                day_counts[issue] += 1
                year_counts[issue] += 1
        if file_number % 100 == 0 or file_number == len(files):
            database.commit()
            print(json.dumps({"phase": "transactions", "files_complete": file_number, "files_total": len(files), "rows": totals["rows"], "owner_mismatch_rows": totals["transaction_product_owner_mismatch_rows"], "missing_product_rows": totals["product_reference_missing_rows"], "currency_mismatch_rows": totals["transaction_product_currency_mismatch_rows"], "elapsed_seconds": round(time.monotonic()-started, 1)}), flush=True)
    distinct_ids = database.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
    database.close()
    manifest["source_set_sha256"] = hashlib.sha256("\n".join(f["relative_path"] + "\t" + f["sha256"] for f in manifest["files"]).encode()).hexdigest()
    (session / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {
        "audit_started_at_utc": started_utc, "scope": "Complete local customers.csv, products.csv and all discovered transaction CSV files; no source modifications or network access.",
        "source_files": len(manifest["files"]), "transaction_files": len(files), "source_bytes": sum(f["size_bytes"] for f in manifest["files"]),
        "source_set_sha256": manifest["source_set_sha256"], "duration_seconds": round(time.monotonic()-started, 2),
        "customers": customer_summary, "products": product_summary,
        "transactions": {"counts": explicit_counts(totals, TX_COUNT_FIELDS), "distinct_nonnull_primary_keys": distinct_ids, "conflicting_primary_keys": len(tx_conflicts), "required_null_counts": {field: nulls[field] for field in TX_REQUIRED}, "column_names": TX_COLUMNS, "distinct_header_schemas": len(schema_counts), "categories": dict(categories), "money_by_currency": dict(money_by_currency), "by_year": dict(sorted(by_year.items())), "by_process_date": dict(sorted(by_date.items()))},
        "limitations": ["Current dimension snapshots do not provide historical ownership or currency-validity intervals; mismatches are cross-file inconsistencies, not proof of fraudulent transactions.", "Counts include exact duplicate source rows; duplicate and conflicting IDs are reported separately.", "Rows without checked issues is not a production-ready cohort: it precedes retrospective quarantine of every row with a conflicting transaction ID and excludes unchecked policy/business rules.", "No complaint records, evaluation final set, source policies, model performance, or real banking action APIs were inspected by this script."]
    }
    destination = ROOT / "evidence" / "local_transactions_summary.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": "complete", "transaction_rows": totals["rows"], "distinct_transaction_ids": distinct_ids, "owner_mismatch_rows": totals["transaction_product_owner_mismatch_rows"], "conflicting_transaction_ids": len(tx_conflicts), "duration_seconds": summary["duration_seconds"]}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"status": "audit_stopped", "reason": "local_audit_error_redacted"}), flush=True)
        sys.exit(2)
