"""Inventory user-provided CSVs without printing records or changing the source.

Headers and filesystem metadata only. This does not certify a complete download
or count CSV records. Detailed file provenance stays in ignored data/local_review.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def inventory(source: Path) -> tuple[dict, dict]:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Source must be a directory")
    groups = collections.defaultdict(list)
    for path in sorted(source.rglob("*.csv")):
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("Source contains an unsupported linked CSV")
        relative = path.relative_to(source)
        table = relative.parts[0] if len(relative.parts) > 1 else path.stem
        groups[table].append(path)
    if not groups:
        raise ValueError("No source CSV files found")
    summary = {
        "method": "All local CSV file metadata and header inspection; no record counting or full-source completeness certification.",
        "source_provenance": "User-provided local Data directory, described by user as full organizer dataset download.",
        "tables": {},
    }
    files = []
    for table, paths in sorted(groups.items()):
        headers = collections.Counter()
        dates = []
        total_bytes = 0
        empty_headers = 0
        for path in paths:
            before = path.stat()
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                header = next(csv.reader(stream, strict=True), [])
            if not header:
                empty_headers += 1
            headers[tuple(header)] += 1
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Source changed during inventory")
            total_bytes += before.st_size
            match = re.search(r"_(\d{8})\.csv$", path.name)
            if match:
                dates.append(dt.datetime.strptime(match[1], "%Y%m%d").date())
            files.append({
                "relative_path": path.relative_to(source).as_posix(),
                "bytes": before.st_size,
                "mtime_ns": before.st_mtime_ns,
                "header_sha256": hashlib.sha256(json.dumps(header, ensure_ascii=False).encode()).hexdigest(),
            })
        unique_dates = set(dates)
        first, last = (min(dates), max(dates)) if dates else (None, None)
        expected_days = (last - first).days + 1 if first else None
        summary["tables"][table] = {
            "file_count": len(paths), "bytes": total_bytes,
            "empty_header_files": empty_headers,
            "header_variants": [{"columns": list(header), "file_count": count} for header, count in sorted(headers.items())],
            "partition_dates": {
                "first": first.isoformat() if first else None,
                "last": last.isoformat() if last else None,
                "distinct_dates": len(unique_dates),
                "missing_dates_within_observed_range": expected_days - len(unique_dates) if first else None,
                "duplicate_date_files": len(dates) - len(unique_dates),
                "basis": "Date suffix in filename, not event timestamps or processing date fields",
            },
        }
    summary["table_count"] = len(groups)
    summary["file_count"] = len(files)
    summary["bytes"] = sum(f["bytes"] for f in files)
    manifest_bytes = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    summary["metadata_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    summary["fingerprint_scope"] = "Names, byte sizes, modification times and header hashes; not full-content hashes"
    return summary, {"source_root": str(source), "files": files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT.parent / "Data")
    args = parser.parse_args()
    summary, manifest = inventory(args.source)
    private = ROOT / "data" / "local_review"
    private.mkdir(parents=True, exist_ok=True)
    (private / "inventory_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ROOT / "evidence" / "local_inventory.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"tables": summary["table_count"], "files": summary["file_count"], "bytes": summary["bytes"],
                      "header_variant_counts": {k: len(v["header_variants"]) for k, v in summary["tables"].items()}}, indent=2))


if __name__ == "__main__":
    main()
