"""Build a bounded private cohort from local CSV files.

Pipeline: read_source -> index_records -> select_cohort -> serialize_record
-> write_private_cohort. build_private_cohort connects these stages.

Only one explicit transaction file is in scope. Scan complete dimension files
within fixed caps, retaining only referenced keys. Resolve duplicates before
applying the cohort limit. No network, models, credentials, or final evaluation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypeAlias

from bank_service.records import (
    CustomerRecord,
    ProductRecord,
    RecordValidationError,
    TransactionRecord,
    parse_customer,
    parse_product,
    parse_transaction,
    required_text,
    validate_transaction_links,
)


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data" / "private_cohort"
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_KEPT_ROWS = 20_000
MAX_CUSTOMER_ROWS = 200_000
MAX_PRODUCT_ROWS = 500_000
MAX_TRANSACTION_ROWS = 10_000
MAX_COHORT_SIZE = 200
DEFAULT_COHORT_SIZE = 50

CUSTOMER_FIELDS = frozenset({"customer_id", "registration_date"})
PRODUCT_FIELDS = frozenset({"product_id", "customer_id", "currency", "opening_date"})
TRANSACTION_FIELDS = frozenset({
    "transaction_id", "customer_id", "product_id", "transaction_date", "process_date",
    "transaction_type", "amount", "currency", "transaction_status",
})

Record: TypeAlias = CustomerRecord | ProductRecord | TransactionRecord


class CohortBuildError(ValueError):
    """A build cannot complete; use fixed reason codes, never raw input values."""


@dataclass(frozen=True)
class SourceRef:
    file: str  # Relative POSIX path inside the selected source root.
    row_number: int  # Logical CSV record number, starting at 1 after the header.
    row_sha256: str  # SHA256 of canonical JSON containing ALL decoded CSV fields.


@dataclass(frozen=True)
class SourceRow:
    values: dict[str, str]  # Temporary private input; never serialize this object.
    source: SourceRef


@dataclass(frozen=True)
class SourceTable:
    file: str
    file_sha256: str  # Hash the exact bytes parsed, including header/BOM/newlines.
    byte_count: int
    row_count: int  # All scanned data rows, including rows excluded by keep_ids.
    rows: tuple[SourceRow, ...]  # Only retained rows; their numbers stay unchanged.


@dataclass(frozen=True)
class IndexedRecord:
    record: Record
    sources: tuple[SourceRef, ...]  # Retain every identical duplicate's reference.


@dataclass(frozen=True)
class QuarantineItem:
    reason: str  # Fixed code such as invalid_key, invalid_record, conflicting_id.
    source: SourceRef  # No rejected values, identifiers, or exception strings.


@dataclass(frozen=True)
class RecordIndex:
    records: dict[str, IndexedRecord]
    conflicted_ids: frozenset[str]
    quarantine: tuple[QuarantineItem, ...]
    duplicate_rows: int  # Sum of repetitions beyond the first of each raw row hash.


@dataclass(frozen=True)
class CohortSelection:
    customers: tuple[IndexedRecord, ...]
    products: tuple[IndexedRecord, ...]
    transactions: tuple[IndexedRecord, ...]
    quarantine: tuple[QuarantineItem, ...]


def read_source(
    path: Path,
    *,
    source_root: Path,
    key_field: str,
    required_fields: frozenset[str],
    max_rows: int,
    keep_ids: frozenset[str] | None = None,
    max_bytes: int = MAX_FILE_BYTES,
    max_kept_rows: int = MAX_KEPT_ROWS,
) -> SourceTable:
    """Read a complete bounded CSV or raise CohortBuildError; never truncate.

    keep_ids=None retains every row. An empty set retains none, but scanning,
    structural validation, hashing, and row/byte caps still cover the whole file.
    Keys are matched after stripping outer whitespace; other fields stay raw.
    """
    # bool is a subclass of int, so require an actual integer for each cap.
    if any(type(cap) is not int or cap <= 0 for cap in (max_rows, max_kept_rows, max_bytes)):
        raise CohortBuildError("invalid_cap")

    try:
        path = path.resolve()
        source_root = source_root.resolve()
        if not path.is_relative_to(source_root):
            raise CohortBuildError("input_path_outside_source_root")
        if not source_root.is_dir() or not path.is_file() or path.suffix.lower() != ".csv":
            raise CohortBuildError("invalid_input_path")

        before = path.stat()
        if before.st_size > max_bytes:
            raise CohortBuildError("file_too_large")
        with path.open("rb") as source:
            # One extra byte detects overflow without reading an unbounded file.
            path_bytes = source.read(max_bytes + 1)
        after = path.stat()
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, CohortBuildError):
            raise
        raise CohortBuildError("source_read_failed") from None

    if len(path_bytes) > max_bytes:
        raise CohortBuildError("file_too_large")
    if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            or len(path_bytes) != after.st_size):
        raise CohortBuildError("file_changed_during_read")

    relative_file = path.relative_to(source_root).as_posix()
    retained_rows = []
    row_count = 0
    try:
        with io.TextIOWrapper(io.BytesIO(path_bytes), encoding="utf-8-sig", newline="") as text:
            parser = csv.reader(text, strict=True)
            header = next(parser, None)
            if not header or any(not field.strip() for field in header):
                raise CohortBuildError("empty_header_field")
            if len(header) != len(set(header)):
                raise CohortBuildError("duplicate_header_fields")
            if key_field not in header or not required_fields.issubset(header):
                raise CohortBuildError("missing_required_fields")

            # csv.reader yields logical records, even when a cell spans lines.
            for row_number, cells in enumerate(parser, start=1):
                row_count = row_number
                if row_count > max_rows:
                    raise CohortBuildError("too_many_rows")
                if len(cells) != len(header):
                    raise CohortBuildError("row_width_mismatch")
                values = dict(zip(header, cells))
                if keep_ids is not None and values[key_field].strip() not in keep_ids:
                    continue
                if len(retained_rows) >= max_kept_rows:
                    raise CohortBuildError("too_many_retained_rows")

                json_bytes = json.dumps(
                    values, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                ).encode("utf-8")
                source_ref = SourceRef(relative_file, row_number, hashlib.sha256(json_bytes).hexdigest())
                # Attach this reference now, while it still belongs to this row.
                retained_rows.append(SourceRow(values=values, source=source_ref))
    except (csv.Error, UnicodeError):
        # Errors can arise during ANY iteration, not only when reading the header.
        raise CohortBuildError("csv_parse_error") from None

    return SourceTable(
        file=relative_file,
        file_sha256=hashlib.sha256(path_bytes).hexdigest(),
        byte_count=len(path_bytes),
        row_count=row_count,
        rows=tuple(retained_rows),
    )


def index_records(
    source: SourceTable,
    *,
    key_field: str,
    parser: Callable[[object], Record],
) -> RecordIndex:
    """Resolve every retained key before returning any eligible parsed records.

    Duplicate equality means identical complete decoded rows, not merely equal
    parsed allowlisted facts. Different versions of one key are all quarantined.
    """
    key_to_rows: dict[str, list[SourceRow]] = {}
    quarantine = []
    for row in source.rows:
        try:
            key_value = required_text(row.values, key_field)
        except RecordValidationError:
            quarantine.append(QuarantineItem("invalid_key", row.source))
            continue
        key_to_rows.setdefault(key_value, []).append(row)

    # Only after grouping all rows do we decide whether a key is unambiguous.
    parsed_records: dict[str, IndexedRecord] = {}
    conflicted_ids = set()
    # Count repeats even when the shared row has an invalid primary key.
    duplicate_rows = len(source.rows) - len({row.source.row_sha256 for row in source.rows})
    for key, rows in sorted(key_to_rows.items()):
        row_hashes = {row.source.row_sha256 for row in rows}
        if len(row_hashes) > 1:
            conflicted_ids.add(key)
            quarantine.extend(QuarantineItem("conflicting_id", row.source) for row in rows)
            continue

        try:
            record = parser(rows[0].values)
        except RecordValidationError:
            quarantine.extend(QuarantineItem("invalid_record", row.source) for row in rows)
            continue
        references = tuple(sorted(
            (row.source for row in rows), key=lambda ref: (ref.file, ref.row_number),
        ))
        parsed_records[key] = IndexedRecord(record=record, sources=references)

    return RecordIndex(
        records=parsed_records,
        conflicted_ids=frozenset(conflicted_ids),
        quarantine=tuple(sorted(quarantine, key=lambda item: (item.source.file, item.source.row_number))),
        duplicate_rows=duplicate_rows,
    )


def select_cohort(
    transactions: RecordIndex,
    customers: RecordIndex,
    products: RecordIndex,
    *,
    limit: int = DEFAULT_COHORT_SIZE,
) -> CohortSelection:
    """Validate all indexed candidates, then select lexicographically by ID.

    This function has no file I/O. The limit is applied only after validation;
    a valid row excluded by the size limit is not a quarantined row.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_COHORT_SIZE:
        raise CohortBuildError("invalid_limit")
    quarantine = list(transactions.quarantine + customers.quarantine + products.quarantine)
    valid_transactions = []
    for transaction in transactions.records.values():
        customer = customers.records.get(transaction.record.customer_id)
        product = products.records.get(transaction.record.product_id)
        reason = None
        if transaction.record.customer_id in customers.conflicted_ids:
            reason = "conflicting_customer"
        elif customer is None:
            reason = "missing_customer"
        elif transaction.record.product_id in products.conflicted_ids:
            reason = "conflicting_product"
        elif product is None:
            reason = "missing_product"
        else:
            try:
                validate_transaction_links(transaction.record, customer.record, product.record)
            except RecordValidationError:
                reason = "link_validation_failed"

        if reason is not None:
            quarantine.extend(QuarantineItem(reason, ref) for ref in transaction.sources)
        else:
            valid_transactions.append(transaction)

    valid_transactions.sort(key=lambda t: t.record.transaction_id)
    selected = valid_transactions[:limit]
    # These are linked IDs, not the keys of the transaction index itself.
    customer_ids = sorted({entry.record.customer_id for entry in selected})
    product_ids = sorted({entry.record.product_id for entry in selected})
    return CohortSelection(
        customers=tuple(customers.records[identifier] for identifier in customer_ids),
        products=tuple(products.records[identifier] for identifier in product_ids),
        transactions=tuple(selected),
        quarantine=tuple(sorted(quarantine, key=lambda item: (item.source.file, item.source.row_number))),
    )


def serialize_record(entry: IndexedRecord) -> dict:
    """Return {"record": allowlisted fields, "sources": source-reference dicts}."""
    # Convert the allowlisted record, never SourceRow (which holds raw fields).
    if not isinstance(entry.record, (CustomerRecord, ProductRecord, TransactionRecord)):
        raise CohortBuildError("unsupported_record_type") from None
    # Preserve exact money values and naive timestamps without inventing a zone.
    record_dict = asdict(entry.record)
    record_dict = {k: (v.isoformat() if isinstance(v, (date, datetime)) else str(v) if isinstance(v, Decimal) else v)
                   for k, v in record_dict.items()}
    sources_list = [{"file": source.file, "row_number": source.row_number, "row_sha256": source.row_sha256}
                    for source in entry.sources]
    return {"record": record_dict, "sources": sources_list}


def write_private_cohort(
    output_dir: Path,
    *,
    cohort: dict,
    quarantine: list[dict],
    manifest: dict,
    private_root: Path = PRIVATE_ROOT,
) -> None:
    """Write JSON-ready payloads only into a fresh child of private_root.

    private_root is injectable for synthetic temporary-directory tests. The CLI
    always uses PRIVATE_ROOT. A manifest is the completion marker for a run.
    """
    try:
        output_exists = output_dir.exists() or output_dir.is_symlink()
        output_dir = output_dir.resolve()
        private_root = private_root.resolve()
    except (OSError, RuntimeError, ValueError):
        raise CohortBuildError("invalid_output_path") from None

    if output_dir == private_root or not output_dir.is_relative_to(private_root):
        raise CohortBuildError("output_dir_outside_private_root") from None
    if output_exists:
        raise CohortBuildError("output_dir_already_exists") from None

    try:
        output_dir.mkdir(parents=True, exist_ok=False)
        # Exclusive creation preserves any file created by another process.
        for filename, payload in (
            ("cohort.json", cohort),
            ("quarantine.json", quarantine),
            ("manifest.json.tmp", manifest),
        ):
            with (output_dir / filename).open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, sort_keys=True, ensure_ascii=False,
                          indent=2, allow_nan=False)
                stream.write("\n")

        # Publishing the closed temporary file is the final successful operation.
        manifest_path = output_dir / "manifest.json"
        if manifest_path.exists() or manifest_path.is_symlink():
            raise CohortBuildError("output_manifest_already_exists")
        (output_dir / "manifest.json.tmp").rename(manifest_path)
    except CohortBuildError:
        raise
    except (OSError, TypeError, ValueError):
        # Leave partial files for inspection, without a completion marker.
        raise CohortBuildError("output_write_failed") from None
    


def build_private_cohort(
    source_root: Path,
    transaction_file: Path,
    output_dir: Path,
    *,
    limit: int = DEFAULT_COHORT_SIZE,
) -> dict:
    """Orchestrate the helpers; return aggregate counts only, never source rows."""
    if type(limit) is not int or not 1 <= limit <= MAX_COHORT_SIZE:
        raise CohortBuildError("invalid_limit")

    # Reject an unusable destination before scanning inputs. The writer repeats
    # these checks immediately before creating files.
    try:
        output_exists = output_dir.exists() or output_dir.is_symlink()
        output_dir = output_dir.resolve()
        private_root = PRIVATE_ROOT.resolve()
    except (OSError, RuntimeError, ValueError):
        raise CohortBuildError("invalid_output_path") from None
    if output_dir == private_root or not output_dir.is_relative_to(private_root):
        raise CohortBuildError("output_dir_outside_private_root")
    if output_exists:
        raise CohortBuildError("output_dir_already_exists")

    # Only these three explicit inputs are in scope; never discover partitions.
    try:
        source_root = source_root.resolve()
        transaction_file = (source_root / transaction_file).resolve()
        customers_file = (source_root / "customers.csv").resolve()
        products_file = (source_root / "products.csv").resolve()
        inputs = (customers_file, products_file, transaction_file)
        if any(not path.is_relative_to(source_root) for path in inputs):
            raise CohortBuildError("input_path_outside_source_root")
        if (not source_root.is_dir() or len(set(inputs)) != 3
                or any(not path.is_file() or path.suffix.lower() != ".csv" for path in inputs)):
            raise CohortBuildError("invalid_input_path")
        sizes = [path.stat().st_size for path in inputs]
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, CohortBuildError):
            raise
        raise CohortBuildError("source_read_failed") from None
    if any(size > MAX_FILE_BYTES for size in sizes):
        raise CohortBuildError("file_too_large")
    if sum(sizes) > MAX_TOTAL_BYTES:
        raise CohortBuildError("total_input_bytes_exceeded")

    transaction_source = read_source(
        transaction_file,
        source_root=source_root,
        key_field="transaction_id",
        required_fields=TRANSACTION_FIELDS,
        max_rows=MAX_TRANSACTION_ROWS,
        max_bytes=MAX_FILE_BYTES,
        max_kept_rows=MAX_KEPT_ROWS,
    )
    transaction_index = index_records(
        transaction_source,
        key_field="transaction_id",
        parser=parse_transaction,
    )
    # Collect links from every indexed transaction before applying the limit.
    customer_ids = frozenset(t.record.customer_id for t in transaction_index.records.values())
    product_ids = frozenset(t.record.product_id for t in transaction_index.records.values())
    customer_source = read_source(
        customers_file,
        source_root=source_root,
        key_field="customer_id",
        required_fields=CUSTOMER_FIELDS,
        max_rows=MAX_CUSTOMER_ROWS,
        keep_ids=customer_ids,
        max_bytes=MAX_FILE_BYTES,
        max_kept_rows=MAX_KEPT_ROWS,
    )
    customer_index = index_records(
        customer_source,
        key_field="customer_id",
        parser=parse_customer,
    )
    product_source = read_source(
        products_file,
        source_root=source_root,
        key_field="product_id",
        required_fields=PRODUCT_FIELDS,
        max_rows=MAX_PRODUCT_ROWS,
        keep_ids=product_ids,
        max_bytes=MAX_FILE_BYTES,
        max_kept_rows=MAX_KEPT_ROWS,
    )
    product_index = index_records(
        product_source,
        key_field="product_id",
        parser=parse_product,
    )
    sources_and_indexes = (
        (customer_source, customer_index),
        (product_source, product_index),
        (transaction_source, transaction_index),
    )
    # Files may have grown after preflight; account for the actual snapshots.
    if sum(source.byte_count for source, _ in sources_and_indexes) > MAX_TOTAL_BYTES:
        raise CohortBuildError("total_input_bytes_exceeded")
    cohort_selection = select_cohort(
        transactions=transaction_index,
        customers=customer_index,
        products=product_index,
        limit=limit,
    )
    if not cohort_selection.transactions:
        raise CohortBuildError("no_valid_cohort") from None
    cohort = {
        "customers": [serialize_record(entry) for entry in cohort_selection.customers],
        "products": [serialize_record(entry) for entry in cohort_selection.products],
        "transactions": [serialize_record(entry) for entry in cohort_selection.transactions],
    }
    quarantine_counts = Counter(item.source.file for item in cohort_selection.quarantine)
    try:
        adapter_hash = hashlib.sha256((ROOT / "bank_service" / "records.py").read_bytes()).hexdigest()
        builder_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        raise CohortBuildError("code_fingerprint_failed") from None

    # Count each rejection against its own source, not against every input file.
    cohort_manifest = {
        "schema_version": 1,
        "sources": [
            {
                "file": source.file,
                "file_sha256": source.file_sha256,
                "byte_count": source.byte_count,
                "row_count": source.row_count,
                "retained_row_count": len(source.rows),
                "duplicate_rows": index.duplicate_rows,
                "conflicted_id_count": len(index.conflicted_ids),
                "quarantined_row_count": quarantine_counts[source.file],
            }
            for source, index in sorted(sources_and_indexes, key=lambda pair: pair[0].file)
        ],
        "requested_size": limit,
        "selected_size": len(cohort_selection.transactions),
        "process_dates": sorted({t.record.process_date.isoformat() for t in cohort_selection.transactions}),
        "limits": {
            "max_file_bytes": MAX_FILE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_transaction_rows": MAX_TRANSACTION_ROWS,
            "max_customer_rows": MAX_CUSTOMER_ROWS,
            "max_product_rows": MAX_PRODUCT_ROWS,
            "max_kept_rows": MAX_KEPT_ROWS,
            "max_cohort_size": MAX_COHORT_SIZE,
        },
        "adapter_sha256": adapter_hash,
        "builder_sha256": builder_hash,
        "scope": {
            "transaction_file_count": 1,
            "dimension_keys": "referenced_only",
            "unretained_dimension_checks": "structure_only",
            "historical_snapshot": True,
            "calendar_date_checks_only": True,
            "timezone_verified": False,
            "global_uniqueness_verified": False,
        },
    }
    # Publish only after validation; the manifest marks a completed run.
    write_private_cohort(
        output_dir=output_dir,
        cohort=cohort,
        quarantine=[asdict(item) for item in cohort_selection.quarantine],
        manifest=cohort_manifest,
        private_root=PRIVATE_ROOT,
    )
    return {
        "customers": len(cohort_selection.customers),
        "products": len(cohort_selection.products),
        "transactions": len(cohort_selection.transactions),
        "quarantined_rows": len(cohort_selection.quarantine),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--transaction-file", type=Path, required=True,
                        help="One CSV path relative to --source; never a glob.")
    parser.add_argument("--run-name", required=True,
                        help="Fresh child directory name under data/private_cohort.")
    parser.add_argument("--limit", type=int, default=DEFAULT_COHORT_SIZE)
    args = parser.parse_args(argv)
    try:
        counts = build_private_cohort(
            args.source, args.transaction_file, PRIVATE_ROOT / args.run_name,
            limit=args.limit,
        )
    except CohortBuildError:
        print("Cohort build failed; no completed cohort was confirmed.")
        return 1
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
