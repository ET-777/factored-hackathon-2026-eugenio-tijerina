"""Export the literal public-demo allowlist without traversing private inputs.

No deployment, Docker startup, provider call, credentials, or evaluation reads.
The manifest fingerprints working-tree bytes; the commit is ancestry metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


RUNTIME_MODULES = (
    "__init__.py", "__main__.py", "access.py", "actions.py", "case_store.py",
    "cohort_repository.py", "conversation.py", "demo.py", "demo_fixtures.py",
    "hosting.py", "learned_routing.py", "records.py", "request_dates.py",
    "responses.py", "route_loader.py", "routing.py", "selection.py",
    "transaction_references.py", "transactions.py", "web_app.py",
)
PACKAGE_FILES = tuple(sorted((
    "Dockerfile", ".dockerignore", "pyproject.toml", "docs/deployment.md",
    *(f"bank_service/{name}" for name in RUNTIME_MODULES),
    "bank_service/web/index.html", "bank_service/web/styles.css", "bank_service/web/app.js",
    "bank_service/resources/routing_train.json",
    "bank_service/resources/routing_train_short_v2.json",
)))
MANIFEST_NAME = "SHA256_MANIFEST.json"
MAX_FILE_BYTES = 5 * 1024 * 1024
DEFAULT_OUTPUT = Path(".local/deployment-package-v1")


class PackageError(ValueError):
    """A fixed diagnostic code; never disclose a path or input value."""


def _absolute(path: Path) -> Path:
    # Preserve lexical paths until all ancestors have been checked for redirects.
    return Path(os.path.abspath(os.fspath(path)))


def _check_unredirected(path: Path) -> None:
    """Check each existing component, including Windows junctions/reparse points."""
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise PackageError("path_unavailable") from None
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise PackageError("path_redirect_refused")
    try:
        if path.resolve(strict=False) != path:
            raise PackageError("path_redirect_refused")
    except (OSError, RuntimeError):
        raise PackageError("path_unavailable") from None


def _source_bytes(path: Path) -> bytes:
    _check_unredirected(path)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise PackageError("source_file_refused")
        if before.st_size > MAX_FILE_BYTES:
            raise PackageError("source_file_too_large")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                             | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                raise PackageError("source_changed")
            body = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
        _check_unredirected(path)
        current = path.lstat()
        if (len(body) > MAX_FILE_BYTES or len(body) != opened.st_size
                or (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns)
                or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)):
            raise PackageError("source_changed")
        return body
    except OSError:
        raise PackageError("source_file_unavailable") from None


def _source_commit(root: Path) -> str | None:
    # Invocation-local trust exception only; never change the user's Git config.
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root),
             "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def _destination_ready(destination: Path) -> None:
    _check_unredirected(destination)
    if destination.exists():
        if not destination.is_dir():
            raise PackageError("destination_must_be_directory")
        if next(destination.iterdir(), None) is not None:
            raise PackageError("destination_not_empty")


def export_package(output_dir: Path, *, source_root: Path | None = None) -> dict:
    """Copy only known safe files to a new or empty destination; never overwrite."""
    root = _absolute(source_root if source_root is not None else Path(__file__).parent.parent)
    destination = _absolute(output_dir)
    _check_unredirected(root)
    _destination_ready(destination)
    # Validate/read every literal input before creating or writing the destination.
    payloads = [(name, _source_bytes(root / name)) for name in PACKAGE_FILES]
    manifest = {
        "schema_version": 1,
        "package_kind": "fictional_hosted_demo",
        "source_commit": _source_commit(root),
        "source_snapshot": "allowlisted_working_tree_bytes",
        "files": [{"path": name, "bytes": len(body),
                   "sha256": hashlib.sha256(body).hexdigest()}
                  for name, body in payloads],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2)
                      + "\n").encode("utf-8")
    _destination_ready(destination)
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for name, body in (*payloads, (MANIFEST_NAME, manifest_bytes)):
            target = destination / name
            _check_unredirected(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            _check_unredirected(target)
            # Exclusive creation also refuses files inserted after the empty check.
            with target.open("xb") as stream:
                stream.write(body)
    except OSError:
        # Preserve partial evidence and refuse a subsequent overwrite.
        raise PackageError("destination_write_refused") from None
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="Owner-selected new or empty directory; no overwrite")
    args = parser.parse_args()
    root = _absolute(Path(__file__).parent.parent)
    output = args.output if args.output is not None else root / DEFAULT_OUTPUT
    try:
        manifest = export_package(output, source_root=root)
    except (PackageError, OSError):
        print("Demo package export refused; use an empty, unredirected destination "
              "and unchanged allowlisted source files.", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps({"status": "local_package_exported", "file_count": len(manifest["files"]),
                      "manifest": MANIFEST_NAME, "deployed": False}, sort_keys=True))


if __name__ == "__main__":
    main()
