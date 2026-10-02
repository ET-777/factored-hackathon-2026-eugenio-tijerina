"""Inventory a fixed small customer-text subset into an ignored private artifact.

No labels, router predictions, agent responses or outcomes are used. This script
prints aggregate counts or fixed error codes only. Source text and provenance
remain in data/intent_review/<new-run>/inventory.json. Counts describe parsed
subset rows, never the complete source corpus.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
START_DATE = date(2023, 6, 17)
MAX_FILES = 7
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1500
MAX_GROUPS = 64
MAX_SECONDS = 30
MAX_TEXT_CHARACTERS = 8192
MAX_METADATA_CHARACTERS = 32
MAX_CSV_FIELD_CHARACTERS = 65536
MAX_COLUMNS = 64
COLUMNS = ("customer_text", "detected_language", "process_date")
CAPS = {
    "files": MAX_FILES, "total_source_bytes": MAX_BYTES, "parsed_rows": MAX_ROWS,
    "distinct_text_groups": MAX_GROUPS, "seconds": MAX_SECONDS,
    "customer_text_characters": MAX_TEXT_CHARACTERS,
    "metadata_characters": MAX_METADATA_CHARACTERS,
    "csv_field_characters": MAX_CSV_FIELD_CHARACTERS, "columns": MAX_COLUMNS,
}


class InventoryError(Exception):
    """Fixed codes only; source content and filesystem exceptions are withheld."""


def normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _missing(value: str) -> bool:
    return value.strip().casefold() in ("", "null", "none", "nan")


def selected_partitions() -> tuple[tuple[str, str], ...]:
    """Generate exactly seven paths; do not enumerate the dataset directory."""
    result = []
    for offset in range(MAX_FILES):
        day = START_DATE + timedelta(days=offset)
        relative = (
            f"call_transcripts/year={day:%Y}/month={day:%m}/day={day:%d}/"
            f"call_transcripts_{day:%Y%m%d}.csv"
        )
        result.append((relative, day.isoformat()))
    return tuple(result)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _check_runtime(started: float) -> None:
    if time.monotonic() - started > MAX_SECONDS:
        raise InventoryError("runtime_limit_exceeded")


def _fingerprint(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _source_path(source_root: Path, relative: str) -> Path:
    path = source_root / relative
    try:
        resolved = path.resolve(strict=True)
        if not _inside(resolved, source_root):
            raise InventoryError("source_path_escape")
        for component in (path, *path.parents):
            if component == source_root:
                break
            if component.is_symlink():
                raise InventoryError("source_symlink_rejected")
        if not stat.S_ISREG(path.stat().st_mode):
            raise InventoryError("source_not_regular_file")
        return resolved
    except (OSError, RuntimeError):
        raise InventoryError("source_file_unavailable") from None


def _read_source(path: Path, remaining_bytes: int, started: float) -> tuple[bytes, tuple[int, ...]]:
    try:
        before = path.stat()
        if before.st_size > remaining_bytes:
            raise InventoryError("byte_limit_exceeded")
        fingerprint = _fingerprint(before)
        chunks = []
        bytes_left = before.st_size
        with path.open("rb") as stream:
            if _fingerprint(os.fstat(stream.fileno())) != fingerprint:
                raise InventoryError("source_file_changed")
            while bytes_left:
                _check_runtime(started)
                chunk = stream.read(min(65536, bytes_left))
                if not chunk:
                    raise InventoryError("source_file_changed")
                chunks.append(chunk)
                bytes_left -= len(chunk)
            if _fingerprint(os.fstat(stream.fileno())) != fingerprint:
                raise InventoryError("source_file_changed")
        if _fingerprint(path.stat()) != fingerprint:
            raise InventoryError("source_file_changed")
        return b"".join(chunks), fingerprint
    except OSError:
        raise InventoryError("source_read_failed") from None


def _private_run(project_root: Path, run_name: str) -> Path:
    if (
        not isinstance(run_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_name)
        or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", run_name, re.IGNORECASE)
    ):
        raise InventoryError("invalid_run_name")
    path = project_root / "data" / "intent_review" / run_name
    try:
        if not _inside(path.resolve(), project_root / "data" / "intent_review"):
            raise InventoryError("private_output_path_escape")
        for component in (path, path.parent, path.parent.parent):
            if component.is_symlink():
                raise InventoryError("private_output_symlink_rejected")
        if path.exists():
            raise InventoryError("run_directory_exists")
        return path
    except (OSError, RuntimeError):
        raise InventoryError("private_output_unavailable") from None


def _rows(blob: bytes):
    try:
        text = blob.decode("utf-8-sig")
        if "\x00" in text:
            raise InventoryError("invalid_csv")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if (
            not header or len(header) > MAX_COLUMNS or len(header) != len(set(header))
            or any(not name or len(name) > 128 for name in header)
            or not set(COLUMNS).issubset(header)
        ):
            raise InventoryError("invalid_csv_header")
        indices = [header.index(column) for column in COLUMNS]
        number = 1
        for row in reader:
            number += 1  # Logical CSV row, matching the existing cohort reference convention.
            if len(row) != len(header):
                raise InventoryError("malformed_csv_row")
            selected = tuple(row[index] for index in indices)
            if len(selected[0]) > MAX_TEXT_CHARACTERS or any(
                len(value) > MAX_METADATA_CHARACTERS for value in selected[1:]
            ):
                raise InventoryError("selected_field_too_large")
            yield number, selected
    except UnicodeError:
        raise InventoryError("invalid_source_encoding") from None
    except csv.Error:
        raise InventoryError("invalid_csv") from None


def inventory(source_root: Path, run_name: str, *, project_root: Path = ROOT) -> dict:
    """Write one new private inventory; return only an aggregate-safe summary."""
    started = time.monotonic()
    try:
        project_root = Path(project_root).resolve(strict=True)
        raw_source = Path(source_root)
        if raw_source.is_symlink():
            raise InventoryError("source_symlink_rejected")
        source_root = raw_source.resolve(strict=True)
        if not source_root.is_dir() or not project_root.is_dir():
            raise InventoryError("invalid_source_root")
        if _inside(source_root, project_root) or _inside(project_root, source_root):
            raise InventoryError("source_must_be_outside_project")
    except (OSError, RuntimeError, TypeError, ValueError):
        raise InventoryError("invalid_source_root") from None
    output_dir = _private_run(project_root, run_name)
    groups, inputs, original_files = {}, [], []
    summary = {
        "files_read": 0, "bytes_read": 0, "rows_read": 0,
        "nonblank_customer_text_rows": 0, "missing_customer_text_rows": 0,
        "distinct_text_groups": 0, "row_cap_reached": False,
        "known_language_rows": {"es": 0, "pt": 0, "en": 0},
        "other_language_rows": 0, "missing_language_rows": 0,
    }
    previous_field_limit = csv.field_size_limit(MAX_CSV_FIELD_CHARACTERS)
    try:
        for relative, partition_date in selected_partitions():
            _check_runtime(started)
            if summary["rows_read"] >= MAX_ROWS:
                break
            path = _source_path(source_root, relative)
            resolved_before = path
            blob, fingerprint = _read_source(path, MAX_BYTES - summary["bytes_read"], started)
            if _source_path(source_root, relative) != resolved_before:
                raise InventoryError("source_file_changed")
            original_files.append((relative, resolved_before, fingerprint))
            info = {
                "relative_path": relative, "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(), "rows_read": 0,
                "complete_file_rows_scanned": False,
            }
            inputs.append(info)
            summary["files_read"] += 1
            summary["bytes_read"] += len(blob)
            rows = _rows(blob)
            while summary["rows_read"] < MAX_ROWS:
                _check_runtime(started)
                try:
                    row_number, (text, language, process_date) = next(rows)
                except StopIteration:
                    info["complete_file_rows_scanned"] = True
                    break
                try:
                    parsed_date = date.fromisoformat(process_date)
                except ValueError:
                    raise InventoryError("invalid_process_date") from None
                if parsed_date.isoformat() != process_date or process_date != partition_date:
                    raise InventoryError("process_date_partition_mismatch")
                summary["rows_read"] += 1
                info["rows_read"] += 1
                stored_language = None if _missing(language) else language.strip()
                if stored_language is None:
                    summary["missing_language_rows"] += 1
                elif stored_language in summary["known_language_rows"]:
                    summary["known_language_rows"][stored_language] += 1
                else:
                    summary["other_language_rows"] += 1
                if _missing(text):
                    summary["missing_customer_text_rows"] += 1
                    continue
                summary["nonblank_customer_text_rows"] += 1
                normalized = normalized_text(text)
                if len(normalized) > MAX_TEXT_CHARACTERS:
                    raise InventoryError("normalized_text_too_large")
                text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                if text_hash not in groups:
                    if len(groups) >= MAX_GROUPS:
                        raise InventoryError("group_limit_exceeded")
                    groups[text_hash] = {
                        "group_id": "SRC-" + text_hash, "text_sha256": text_hash,
                        "normalized_customer_text": normalized, "representative_customer_text": text,
                        "representative_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "subset_row_count": 0, "source_languages": set(), "process_dates": set(),
                        "first_occurrence_refs": [], "provisional_label": None,
                    }
                group = groups[text_hash]
                if group["normalized_customer_text"] != normalized:
                    raise InventoryError("text_hash_collision")
                group["subset_row_count"] += 1
                group["source_languages"].add(stored_language)
                group["process_dates"].add(process_date)
                if not any(ref["relative_path"] == relative for ref in group["first_occurrence_refs"]):
                    selected_hash = hashlib.sha256(json.dumps(
                        dict(zip(COLUMNS, (text, language, process_date))),
                        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                    ).encode("utf-8")).hexdigest()
                    group["first_occurrence_refs"].append({
                        "relative_path": relative, "row_number": row_number,
                        "process_date": process_date, "detected_language": stored_language,
                        "selected_fields_sha256": selected_hash,
                    })
        summary["row_cap_reached"] = summary["rows_read"] >= MAX_ROWS
        summary["distinct_text_groups"] = len(groups)
        for relative, resolved_before, original in original_files:
            _check_runtime(started)
            try:
                current = _source_path(source_root, relative)
                if current != resolved_before or _fingerprint(current.stat()) != original:
                    raise InventoryError("source_file_changed")
            except OSError:
                raise InventoryError("source_file_changed") from None
        private_groups = []
        for key in sorted(groups):
            group = groups[key]
            group["source_languages"] = sorted(group["source_languages"], key=lambda value: value or "")
            group["process_dates"] = sorted(group["process_dates"])
            private_groups.append(group)
        payload = {
            "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "bounded_local_customer_text_subset", "caps": CAPS,
            "requested_daily_partitions": [path for path, _ in selected_partitions()],
            "source_columns_used": list(COLUMNS), "source_labels_used": False,
            "keyword_router_used": False, "label_status": "absent_pending_semantic_review",
            "normalization": "NFKC + casefold + whitespace collapse",
            "summary": summary, "input_files": inputs, "groups": private_groups,
        }
        _check_runtime(started)
        # Revalidate the private destination, then reserve a new directory and
        # exclusively create the artifact. Existing runs are never overwritten.
        output_dir = _private_run(project_root, run_name)
        try:
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(exist_ok=False)
            with (output_dir / "inventory.json").open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
        except FileExistsError:
            raise InventoryError("run_directory_exists") from None
        except OSError:
            raise InventoryError("private_output_write_failed") from None
        return dict(summary)
    finally:
        csv.field_size_limit(previous_field_limit)


class _SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise InventoryError("invalid_cli_arguments")


def main(argv=None) -> int:
    parser = _SafeParser(description="Create a bounded private customer-text inventory.")
    parser.add_argument("--source", type=Path, default=ROOT.parent / "Data")
    parser.add_argument("--run-name", required=True)
    try:
        args = parser.parse_args(argv)
        summary = inventory(args.source, args.run_name, project_root=ROOT)
        print(json.dumps({"status": "completed", **summary}, sort_keys=True))
        return 0
    except InventoryError as error:
        print(json.dumps({"status": "refused", "error": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
