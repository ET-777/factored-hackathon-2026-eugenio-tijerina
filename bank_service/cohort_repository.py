from collections.abc import Callable, Mapping
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import TypeVar

from bank_service.records import (
    CustomerRecord,
    ProductRecord,
    RecordValidationError,
    TransactionRecord,
    parse_customer,
    parse_product,
    parse_transaction,
    validate_transaction_links,
)
from bank_service.transactions import SourceReference, SourcedTransaction


# Local loader limits, independent of values supplied by a manifest.
MAX_RECORDS_PER_TABLE = 200
MAX_COHORT_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
RecordType = TypeVar("RecordType", CustomerRecord, ProductRecord, TransactionRecord)


class CohortLoadError(ValueError):
    """Invalid or incomplete cohort; messages must not include private values."""


def _parse_sources(
    value: object,
    *,
    source_rows: Mapping[str, int],
    expected_file: str,
) -> tuple[SourceReference, ...]:
    """Convert a record's source list into checked runtime references.

    source_rows maps validated relative filenames to scanned CSV row counts.
    expected_file identifies the table this record belongs to.
    """
    if not isinstance(value, list) or not value:
        raise CohortLoadError("invalid_source_reference")

    references = []
    seen = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise CohortLoadError("invalid_source_reference")

        file = item.get("file")
        row_number = item.get("row_number")
        row_sha256 = item.get("row_sha256")

        if not isinstance(file, str) or file != expected_file or file not in source_rows:
            raise CohortLoadError("invalid_source_reference")

        # bool is an int subclass, but True is not a valid row number.
        if type(row_number) is not int or not 1 <= row_number <= source_rows[file]:
            raise CohortLoadError("invalid_source_reference")

        if not isinstance(row_sha256, str) or not SHA256_PATTERN.fullmatch(row_sha256):
            raise CohortLoadError("invalid_source_reference")

        identity = (file, row_number)
        if identity in seen:
            raise CohortLoadError("invalid_source_reference")
        seen.add(identity)
        references.append(SourceReference(file, row_number, row_sha256))

    return tuple(references)


def _manifest_sources(value: object) -> tuple[dict[str, int], str]:
    """Validate table names before using them as provenance lookup keys."""
    if not isinstance(value, list) or len(value) != 3:
        raise CohortLoadError("invalid_manifest")

    source_rows = {}
    for source in value:
        if not isinstance(source, Mapping):
            raise CohortLoadError("invalid_manifest")
        file = source.get("file")
        row_count = source.get("row_count")
        if (not isinstance(file, str) or not file or file != file.strip()
                or "\\" in file or any(ord(char) < 32 for char in file)):
            raise CohortLoadError("invalid_manifest")
        path = PurePosixPath(file)
        # Inspect the raw components too: PurePath normalizes away '.' and '//'.
        if (path.is_absolute() or PureWindowsPath(file).drive
                or any(part in ("", ".", "..") for part in file.split("/"))
                or path.as_posix() != file or path.suffix != ".csv"):
            raise CohortLoadError("invalid_manifest")
        if type(row_count) is not int or row_count < 0 or file in source_rows:
            raise CohortLoadError("invalid_manifest")
        source_rows[file] = row_count

    dimension_files = {"customers.csv", "products.csv"}
    if not dimension_files.issubset(source_rows):
        raise CohortLoadError("invalid_manifest")
    transaction_file = next(iter(set(source_rows) - dimension_files))
    return source_rows, transaction_file


def _parse_table(
    entries: list,
    *,
    parser: Callable[[object], RecordType],
    key_field: str,
    source_rows: Mapping[str, int],
    expected_file: str,
) -> tuple[dict[str, RecordType], dict[str, tuple[SourceReference, ...]]]:
    """Apply the same envelope, uniqueness, and provenance checks to each table."""
    records = {}
    sources_by_id = {}
    used_rows = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("record"), Mapping):
            raise CohortLoadError("invalid_cohort")
        try:
            record = parser(entry["record"])
        except RecordValidationError:
            raise CohortLoadError("invalid_cohort") from None
        identifier = getattr(record, key_field)
        if identifier in records:
            raise CohortLoadError("duplicate_record_id")
        references = _parse_sources(
            entry.get("sources"), source_rows=source_rows, expected_file=expected_file,
        )
        for reference in references:
            identity = (reference.file, reference.row_number)
            if identity in used_rows:
                raise CohortLoadError("invalid_source_reference")
            used_rows.add(identity)
        records[identifier] = record
        sources_by_id[identifier] = references
    return records, sources_by_id


def parse_cohort(
    payload: object,
    manifest: object,
) -> dict[str, SourcedTransaction]:
    """Validate decoded JSON and return a complete transaction repository.

    Pure function: no file reads, prints, source-data changes, or authorization.
    Reject the whole payload on any error; never return a partial repository.
    """
    if not isinstance(payload, Mapping):
        raise CohortLoadError("invalid_cohort")
    if (not isinstance(manifest, Mapping) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1):
        raise CohortLoadError("invalid_manifest")

    if not all(
        isinstance(payload.get(key), list) and 0 < len(payload[key]) <= MAX_RECORDS_PER_TABLE
        for key in ("customers", "products", "transactions")
    ):
        raise CohortLoadError("invalid_cohort")
    requested_size = manifest.get("requested_size")
    selected_size = manifest.get("selected_size")
    if (type(requested_size) is not int or type(selected_size) is not int
            or not 1 <= selected_size <= requested_size <= MAX_RECORDS_PER_TABLE):
        raise CohortLoadError("invalid_manifest")

    if selected_size != len(payload["transactions"]):
        raise CohortLoadError("invalid_cohort")

    source_rows, transaction_file = _manifest_sources(manifest.get("sources"))
    customers, _ = _parse_table(
        payload["customers"], parser=parse_customer, key_field="customer_id",
        source_rows=source_rows, expected_file="customers.csv",
    )
    products, _ = _parse_table(
        payload["products"], parser=parse_product, key_field="product_id",
        source_rows=source_rows, expected_file="products.csv",
    )
    transactions, transaction_sources = _parse_table(
        payload["transactions"], parser=parse_transaction, key_field="transaction_id",
        source_rows=source_rows, expected_file=transaction_file,
    )

    # Validate every link before making any repository available to the caller.
    for transaction in transactions.values():
        try:
            validate_transaction_links(
                transaction, customers.get(transaction.customer_id), products.get(transaction.product_id),
            )
        except RecordValidationError:
            raise CohortLoadError("invalid_record_links") from None

    if (set(customers) != {record.customer_id for record in transactions.values()}
            or set(products) != {record.product_id for record in transactions.values()}):
        raise CohortLoadError("unused_dimension_records")
    process_dates = sorted({record.process_date.isoformat() for record in transactions.values()})
    if manifest.get("process_dates") != process_dates:
        raise CohortLoadError("invalid_manifest")

    return {
        identifier: SourcedTransaction(record, transaction_sources[identifier])
        for identifier, record in transactions.items()
    }


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    """json.loads calls this for every object, including nested record objects."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise CohortLoadError("invalid_json_file")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise CohortLoadError("invalid_json_file")


def _finite_json_float(value: str) -> float:
    # parse_constant handles NaN/Infinity, but not overflowing numbers like 1e400.
    parsed = float(value)
    if not math.isfinite(parsed):
        raise CohortLoadError("invalid_json_file")
    return parsed


def _read_json(path: Path, *, max_bytes: int) -> object:
    """Read one bounded UTF-8 JSON snapshot without exposing raw errors."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise CohortLoadError("invalid_json_file")
    try:
        with path.open("rb") as stream:
            body = stream.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise CohortLoadError("invalid_json_file")
        return json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant, parse_float=_finite_json_float,
        )
    except CohortLoadError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        # ValueError also covers Python's integer-digit cap in json.loads.
        raise CohortLoadError("invalid_json_file") from None


def load_private_cohort(
    run_dir: Path,
) -> dict[str, SourcedTransaction]:
    """Read a completed cohort run and pass it to parse_cohort.

    run_dir comes from trusted server configuration, never a chat/browser input.
    File loading neither creates TrustedSession objects nor exposes the repository
    directly to callers; transaction reads still go through get_transaction.
    """
    try:
        run_dir = Path(run_dir).resolve()
        if not run_dir.is_dir():
            raise CohortLoadError("incomplete_cohort")
        files = {}
        for name in ("manifest.json", "cohort.json", "quarantine.json"):
            path = (run_dir / name).resolve()
            if not path.is_relative_to(run_dir) or not path.is_file():
                raise CohortLoadError("incomplete_cohort")
            files[name] = path
    except CohortLoadError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise CohortLoadError("incomplete_cohort") from None

    manifest = _read_json(files["manifest.json"], max_bytes=MAX_MANIFEST_BYTES)
    payload = _read_json(files["cohort.json"], max_bytes=MAX_COHORT_BYTES)
    return parse_cohort(payload, manifest)
