"""Bounded read-only audit of the organizer's S3 CSVs; credentials stay in memory.

Requires pypdf only for the credential-bearing local dictionary. Source objects,
samples, and the detailed manifest are deliberately stored under ignored data/.
The public summary contains aggregate statistics and schemas, never raw rows.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import decimal
import hashlib
import hmac
import io
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "data" / "audit"
MAX_REQUESTS = 12
MAX_BYTES = 20 * 1024 * 1024
RANGE_BYTES = 1024 * 1024
ROW_CAP = 500
TARGETS = ("transactions", "call_center_interactions", "complaints", "call_transcripts")
DOCUMENTED_COLUMNS = {
    "transactions": "transaction_id transaction_date process_date product_id customer_id transaction_type transaction_category amount currency amount_usd channel branch_id merchant_name merchant_category transaction_country transaction_city transaction_status response_code is_fraud fraud_score latitude longitude".split(),
    "call_center_interactions": "interaction_id interaction_date process_date customer_id agent_id interaction_type channel contact_reason reason_category duration_seconds wait_time_seconds was_resolved requires_followup detected_sentiment sentiment_score customer_detected_accent agent_used_accent was_escalated mentioned_products has_transcript has_recording".split(),
    "complaints": "complaint_id creation_date process_date customer_id case_type category subcategory reception_channel affected_product_id related_branch_id origin_interaction_id description claimed_amount currency priority status assigned_agent_id assignment_date first_response_date resolution_date closing_date sla_breached resolution_days resolution compensation_granted resolution_satisfaction is_repeat_complainer".split(),
    "call_transcripts": "transcript_id interaction_id process_date customer_id agent_id full_text customer_text agent_text detected_language detected_accent accent_confidence detected_keywords mentioned_entities detected_intents main_topics transcription_model audio_quality duration_seconds".split(),
}
# Explicit publication allowlist: never pass arbitrary source strings through
# an aggregate as a category. Unexpected values are counted but not printed.
PUBLIC_CATEGORIES = set("Withdrawal Transfer Purchase Payment Deposit Adjustment USD COP ARS MXN Approved Declined Pending Reversed México Mexico Colombia Argentina Spain USA Brazil False True Transaccional Queja Producto Técnico Comercial Retención mexican colombian argentine neutral Complaint Claim Request Suggestion Service Technical Fees Branch Transactions Open Resolved Escalated Closed Rejected Medium Low High Critical es pt consulta_general".split()) | {"In Process", "Calidad de servicio", "Problema con app", "Cobro indebido", "Cargo no reconocido", "Atención en sucursal"}


class AuditError(Exception):
    """Contains only a safe, constant error category."""


def load_access(dictionary: Path) -> dict[str, str]:
    from pypdf import PdfReader
    lines = [s.strip() for s in PdfReader(dictionary).pages[1].extract_text().splitlines()]
    labels = {"bucket": "Bucket Name", "region": "Region", "access": "Access Key ID", "secret": "Secret Access Key"}
    values = {}
    for name, label in labels.items():
        matches = [i for i, s in enumerate(lines) if s.casefold() == label.casefold()]
        if len(matches) != 1 or matches[0] + 1 == len(lines):
            raise AuditError("dictionary_access_layout_unrecognized")
        values[name] = lines[matches[0] + 1]
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", values["bucket"]):
        raise AuditError("invalid_source_bucket")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d", values["region"]):
        raise AuditError("invalid_source_region")
    return values


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuditError("source_redirect_refused")


class Reader:
    def __init__(self, access: dict[str, str], ledger: dict):
        self._access = access
        self.ledger = ledger
        self._host = f"{access['bucket']}.s3.{access['region']}.amazonaws.com"
        self._opener = urllib.request.build_opener(NoRedirect)

    def get(self, key: str = "", query: dict[str, str] | None = None, *, ranged: bool = False):
        if self.ledger["request_count"] >= MAX_REQUESTS:
            raise AuditError("request_budget_exhausted")
        cap = min(RANGE_BYTES, MAX_BYTES - self.ledger["response_bytes"])
        if cap <= 0:
            raise AuditError("byte_budget_exhausted")
        now = dt.datetime.now(dt.timezone.utc)
        amz_date, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        uri = "/" + urllib.parse.quote(key, safe="/-_.~")
        qs = "&".join(urllib.parse.quote(k, safe="-_.~") + "=" + urllib.parse.quote(v, safe="-_.~") for k, v in sorted((query or {}).items()))
        empty_hash = hashlib.sha256(b"").hexdigest()
        headers = {"host": self._host, "x-amz-content-sha256": empty_hash, "x-amz-date": amz_date}
        if ranged:
            headers["range"] = f"bytes=0-{cap-1}"
        signed = ";".join(sorted(headers))
        canonical = "GET\n" + uri + "\n" + qs + "\n" + "".join(k + ":" + headers[k] + "\n" for k in sorted(headers)) + "\n" + signed + "\n" + empty_hash
        scope = f"{date}/{self._access['region']}/s3/aws4_request"
        to_sign = "AWS4-HMAC-SHA256\n" + amz_date + "\n" + scope + "\n" + hashlib.sha256(canonical.encode()).hexdigest()
        signing_key = ("AWS4" + self._access["secret"]).encode()
        for term in (date, self._access["region"], "s3", "aws4_request"):
            signing_key = hmac.new(signing_key, term.encode(), hashlib.sha256).digest()
        signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = f"AWS4-HMAC-SHA256 Credential={self._access['access']}/{scope}, SignedHeaders={signed}, Signature={signature}"
        req = urllib.request.Request("https://" + self._host + uri + ("?" + qs if qs else ""), headers=headers, method="GET")
        self.ledger["request_count"] += 1
        self.save()
        try:
            with self._opener.open(req, timeout=25) as resp:
                status = resp.status
                length = int(resp.headers.get("Content-Length", "0"))
                if ranged and status != 206:
                    raise AuditError("range_not_honored")
                if length > cap:
                    raise AuditError("response_exceeds_cap")
                body = resp.read(cap)
                self.ledger["response_bytes"] += len(body)
                self.ledger["successful_source_requests"] = self.ledger.get("successful_source_requests", 0) + 1
                self.save()
                return body, {"status": status, "etag": resp.headers.get("ETag"), "last_modified": resp.headers.get("Last-Modified"), "content_range": resp.headers.get("Content-Range"), "bytes_read": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        except urllib.error.HTTPError as error:
            self.ledger["failed_source_requests"] = self.ledger.get("failed_source_requests", 0) + 1
            self.save()
            raise AuditError(f"source_http_{error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            self.ledger["failed_source_requests"] = self.ledger.get("failed_source_requests", 0) + 1
            self.save()
            raise AuditError("source_network_unavailable") from None

    def save(self):
        PRIVATE.mkdir(parents=True, exist_ok=True)
        (PRIVATE / "request_ledger.json").write_text(json.dumps(self.ledger, indent=2) + "\n", encoding="utf-8")

    def list(self, prefix: str = "", delimiter: str | None = None):
        query = {"list-type": "2", "max-keys": "40", "prefix": prefix}
        if delimiter:
            query["delimiter"] = delimiter
        body, metadata = self.get(query=query)
        root = ET.fromstring(body)
        ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        objects = [{"key": n.findtext("s:Key", namespaces=ns), "size": int(n.findtext("s:Size", namespaces=ns)), "etag": n.findtext("s:ETag", namespaces=ns)} for n in root.findall("s:Contents", ns)]
        prefixes = [n.text for n in root.findall("s:CommonPrefixes/s:Prefix", ns)]
        return {"prefix": prefix, "objects": objects, "prefixes": prefixes, "truncated_listing": root.findtext("s:IsTruncated", namespaces=ns) == "true", "response": metadata}


def parse_prefix(body: bytes, limit: int = ROW_CAP):
    # Cut only the transport tail, then strict CSV parsing also rejects an
    # unterminated quoted record containing embedded newlines.
    cut = body.rfind(b"\n")
    if cut < 0:
        raise AuditError("no_complete_csv_line")
    text = body[:cut+1].decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    columns = next(reader)
    if not columns or len(set(columns)) != len(columns):
        raise AuditError("invalid_csv_header")
    rows, malformed = [], 0
    try:
        for values in reader:
            if len(values) != len(columns):
                malformed += 1
                continue
            rows.append(dict(zip(columns, values)))
            if len(rows) >= limit:
                break
    except csv.Error:
        # A ranged prefix can end inside a quoted multi-line record.
        malformed += 1
    return columns, rows, malformed


def profile(table: str, columns: list[str], rows: list[dict], malformed: int) -> dict:
    null = lambda v: v is None or v.strip().casefold() in ("", "null", "none", "nan")
    n = len(rows)
    result = {"rows": n, "columns": columns, "column_count": len(columns), "discarded_malformed_or_partial_records": malformed,
              "null_counts": {c: sum(null(r[c]) for r in rows) for c in columns},
              "exact_duplicate_rows": n - len({tuple(r[c] for c in columns) for r in rows})}
    result["documented_schema_comparison"] = {"missing_columns": sorted(set(DOCUMENTED_COLUMNS[table]) - set(columns)), "additional_columns": sorted(set(columns) - set(DOCUMENTED_COLUMNS[table]))}
    primary = {"transactions": "transaction_id", "call_center_interactions": "interaction_id", "complaints": "complaint_id", "call_transcripts": "transcript_id"}[table]
    if primary in columns:
        vals = [r[primary] for r in rows if not null(r[primary])]
        result["primary_key"] = {"column": primary, "nulls": n-len(vals), "duplicate_excess_rows": len(vals)-len(set(vals))}
    result["date_ranges"] = {}
    for col in columns:
        if col.endswith("_date"):
            valid, invalid = [], 0
            for r in rows:
                if null(r[col]):
                    continue
                try:
                    valid.append(dt.datetime.fromisoformat(r[col]))
                except ValueError:
                    invalid += 1
            result["date_ranges"][col] = {"min": min(valid).isoformat() if valid else None, "max": max(valid).isoformat() if valid else None, "invalid": invalid}
    categorical = {"transactions": ("transaction_type", "currency", "transaction_status", "transaction_country", "is_fraud"),
                   "call_center_interactions": ("contact_reason", "reason_category", "was_resolved", "requires_followup", "was_escalated", "has_transcript", "customer_detected_accent"),
                   "complaints": ("case_type", "category", "subcategory", "currency", "status", "priority"),
                   "call_transcripts": ("detected_language", "detected_accent", "detected_intents", "main_topics")}[table]
    result["categories"] = {c: dict(collections.Counter(r[c] if r[c] in PUBLIC_CATEGORIES else "[unrecognized value withheld]" for r in rows if not null(r[c])).most_common()) for c in categorical if c in columns}
    result["numeric"] = {}
    for col in ("amount", "amount_usd", "claimed_amount", "fraud_score", "duration_seconds", "wait_time_seconds"):
        if col not in columns:
            continue
        values, invalid = [], 0
        for r in rows:
            if null(r[col]):
                continue
            try:
                value = decimal.Decimal(r[col])
                if value.is_finite():
                    values.append(value)
                else:
                    invalid += 1
            except decimal.InvalidOperation:
                invalid += 1
        result["numeric"][col] = {"count": len(values), "invalid": invalid, "negative": sum(v < 0 for v in values), "zero": sum(v == 0 for v in values), "min": str(min(values)) if values else None, "max": str(max(values)) if values else None}
    return result


def cross_checks(data: dict[str, list[dict]]) -> dict:
    interactions = {r["interaction_id"]: r for r in data.get("call_center_interactions", [])}
    transcripts = data.get("call_transcripts", [])
    complaints = data.get("complaints", [])
    transactions = data.get("transactions", [])
    matched = [r for r in transcripts if r["interaction_id"] in interactions]
    result = {
        "transcript_interaction_join": {"transcript_rows": len(transcripts), "matched_in_sample": len(matched),
            "matching_customer_among_matches": sum(r["customer_id"] == interactions[r["interaction_id"]]["customer_id"] for r in matched),
            "matching_agent_among_matches": sum(r["agent_id"] == interactions[r["interaction_id"]]["agent_id"] for r in matched),
            "matching_topic_reason_among_matches": sum(r["main_topics"] == interactions[r["interaction_id"]]["reason_category"] for r in matched)},
        "contact_reason_equals_reason_category_rows": sum(r["contact_reason"] == r["reason_category"] for r in interactions.values()),
        "complaint_origin_interaction_nonblank_rows": sum(bool(r["origin_interaction_id"].strip()) for r in complaints),
        "customer_product_ownership_joins": "not verified; dimension tables not sampled",
        "text_label_repetition": {},
    }
    for col in ("customer_text", "full_text"):
        groups = collections.defaultdict(collections.Counter)
        for r in transcripts:
            groups[r[col].strip().casefold()][r["main_topics"]] += 1
        conflicts = [counts for counts in groups.values() if len(counts) > 1]
        result["text_label_repetition"][col] = {
            "normalization": "strip plus Unicode casefold",
            "unique_text_groups": len(groups), "groups_with_multiple_topics": len(conflicts),
            "rows_in_conflicting_groups": sum(sum(counts.values()) for counts in conflicts),
            "sum_of_group_majority_counts": sum(max(counts.values()) for counts in groups.values()),
            "rows": len(transcripts),
            "interpretation": "Descriptive exact-repeat label conflict; not a measured model score or generalization estimate.",
        }
    result["transaction_calendar_day_minus_process_date"] = dict(collections.Counter(str((dt.datetime.fromisoformat(r["transaction_date"]).date() - dt.datetime.fromisoformat(r["process_date"]).date()).days) for r in transactions))
    result["transaction_timestamps_without_timezone"] = sum(dt.datetime.fromisoformat(r["transaction_date"]).tzinfo is None for r in transactions)
    result["complaint_timestamp_consistency"] = {
        col + "_before_creation": sum(bool(r[col].strip()) and dt.datetime.fromisoformat(r[col]) < dt.datetime.fromisoformat(r["creation_date"]) for r in complaints)
        for col in ("assignment_date", "first_response_date", "resolution_date", "closing_date")
    }
    result["complaint_timestamp_consistency"]["closed_missing_closing_date"] = sum(r["status"] == "Closed" and not r["closing_date"].strip() for r in complaints)
    purchases = [r for r in transactions if r["transaction_type"] == "Purchase"]
    result["purchase_merchant_completeness"] = {"purchase_rows": len(purchases), "merchant_name_missing": sum(not r["merchant_name"].strip() for r in purchases)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--offline", action="store_true", help="Recompute aggregate profile from ignored local samples; no credentials or network.")
    args = parser.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    ledger_file = PRIVATE / "request_ledger.json"
    ledger = json.loads(ledger_file.read_text()) if ledger_file.exists() else {"request_count": 0, "response_bytes": 0, "request_cap": MAX_REQUESTS, "byte_cap": MAX_BYTES}
    if args.offline:
        tables, data = {}, {}
        manifest_path = PRIVATE / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        for table in TARGETS:
            sample_path = PRIVATE / (table + ".csv")
            if sample_path.exists():
                sample_bytes = sample_path.read_bytes()
                expected_hash = manifest.get("tables", {}).get(table, {}).get("sample_sha256")
                if expected_hash is None or hashlib.sha256(sample_bytes).hexdigest() != expected_hash:
                    raise AuditError("local_sample_fingerprint_mismatch")
                columns, rows, malformed = parse_prefix(sample_bytes)
                tables[table] = profile(table, columns, rows, malformed)
                data[table] = rows
        summary = {"access_verified": bool(tables), "audited_at_utc": manifest.get("audited_at_utc"), "selection": "Up to the first 500 complete CSV rows of the lexicographically first listed source object per table; not random or representative.", "source_request_count": ledger["request_count"], "successful_source_requests": ledger.get("successful_source_requests"), "failed_source_requests": ledger.get("failed_source_requests"), "source_response_bytes": ledger["response_bytes"], "sample_rows_total": sum(v["rows"] for v in tables.values()), "tables": tables, "cross_checks": cross_checks(data)}
        destination = ROOT / "evidence" / "audit_summary.json"
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "offline_profile_complete", "rows": {k: v["rows"] for k, v in tables.items()}}))
        return
    if not args.dictionary:
        raise AuditError("dictionary_path_required")
    reader = Reader(load_access(args.dictionary), ledger)
    if args.discover:
        listing = reader.list(args.prefix, "/")
        (PRIVATE / ("listing_" + hashlib.sha256(args.prefix.encode()).hexdigest()[:10] + ".json")).write_text(json.dumps(listing, indent=2) + "\n")
        print(json.dumps({"status": "listing_access_verified", "prefixes": listing["prefixes"], "object_count": len(listing["objects"]), "truncated_listing": listing["truncated_listing"], "request_count": ledger["request_count"]}))
        return
    manifest = {"version": 1, "audited_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "selection": "first lexicographic object, first complete 500 rows", "row_cap_per_table": ROW_CAP, "range_bytes": RANGE_BYTES, "tables": {}}
    for table in TARGETS:
        listing = reader.list(args.prefix.rstrip("/") + "/" + table + "/")
        candidates = [o for o in listing["objects"] if o["key"].endswith(".csv")]
        if not candidates:
            manifest["tables"][table] = {"status": "no_csv_in_bounded_listing", "listing": listing}
            continue
        obj = min(candidates, key=lambda o: o["key"])
        body, meta = reader.get(obj["key"], ranged=True)
        columns, rows, malformed = parse_prefix(body)
        sample_path = PRIVATE / (table + ".csv")
        with sample_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        manifest["tables"][table] = {"source_object": obj, "source_response": meta, "listing_truncated": listing["truncated_listing"], "sample_sha256": hashlib.sha256(sample_path.read_bytes()).hexdigest(), "rows": len(rows), "discarded_malformed_or_partial_records": malformed}
        (PRIVATE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"table": table, "rows": len(rows), "columns": columns, "bytes_read": len(body)}))
    reader.save()


if __name__ == "__main__":
    try:
        main()
    except AuditError as error:
        print(json.dumps({"status": "audit_stopped", "reason": str(error)}))
        sys.exit(2)
    except Exception:
        # Do not dump exception values or tracebacks: upstream libraries can
        # include credential-bearing source text, URLs, or request headers.
        print(json.dumps({"status": "audit_stopped", "reason": "unexpected_local_error_redacted"}))
        sys.exit(2)
