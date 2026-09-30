"""Read-only check of Git-eligible files; never print source credentials or rows.

With --dictionary, compare exact credential values loaded in memory against all
eligible bytes. This is a scoped guard, not a complete general-purpose secret scan.
Requires the audit script's optional pypdf dependency for --dictionary only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path)
    args = parser.parse_args()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    try:
        listed = subprocess.run(
            [*git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        print(json.dumps({"ok": False, "reason": "git_inventory_unavailable"}))
        return 1
    paths = sorted(set(p.decode("utf-8") for p in listed.split(b"\0") if p))
    secrets = []
    if args.dictionary:
        try:
            from audit_subset import load_access
            access = load_access(args.dictionary)
            secrets = [access[name].encode("utf-8") for name in ("access", "secret")]
            if any(len(value) < 12 for value in secrets):
                raise ValueError("invalid credential shape")
        except Exception:
            # No raw parser/credential exceptions may reach output.
            print(json.dumps({"ok": False, "reason": "credential_check_unavailable"}))
            return 1
    excluded_roots = ("data/", "tmp/", "evaluation/final_private/", ".local/", "artifacts/")
    excluded_suffixes = {".pdf", ".csv", ".tsv", ".parquet", ".pem", ".key", ".sqlite", ".db", ".duckdb", ".zip"}
    violations = set()
    for relative in paths:
        path = ROOT / relative
        if (relative.startswith(excluded_roots) or path.suffix.lower() in excluded_suffixes
                or path.name.startswith(".env") or path.is_symlink()):
            violations.add(relative)
        if not path.is_file():
            violations.add(relative)
            continue
        body = path.read_bytes()
        if any(value in body for value in secrets):
            violations.add(relative)
        # Generic AWS access IDs and private-key blocks; report only counts.
        if re.search(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", body) or re.search(
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", body
        ):
            violations.add(relative)
    probes = [".env", "credentials/access.json", "source.pdf", "tmp/extracted.txt",
              "data/audit/sample.json", "evaluation/final_private/cases.json",
              ".streamlit/secrets.toml", "artifacts/model.joblib"]
    probe_result = subprocess.run(
        [*git, "check-ignore", "--stdin", "-z"], input=("\0".join(probes) + "\0").encode("utf-8"),
        capture_output=True, cwd=ROOT,
    )
    missing_exclusions = set(probes) - set(probe_result.stdout.decode("utf-8").split("\0"))
    result = {
        "ok": not violations and not missing_exclusions,
        "git_eligible_files_checked": len(paths),
        "credential_values_compared_in_memory": len(secrets),
        "violating_file_count": len(violations),
        "exclusion_probes_passed": len(probes) - len(missing_exclusions),
        "exclusion_probes_total": len(probes),
        "scope": "eligible working-tree files only; Git history is not scanned",
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
