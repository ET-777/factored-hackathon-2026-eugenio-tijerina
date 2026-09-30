"""Verify the sealed evaluation and split boundaries without printing final inputs.

This is an integrity check, not a model run, evaluation score, or credential scan.
Only Python's standard library is used. Exit 2 means the check failed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unicodedata


class EvaluationError(Exception):
    """A deliberately content-free integrity failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationError(message)


def read_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise EvaluationError(f"Cannot read valid {label} JSON; no contents printed.") from None


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def validate_cases(document, split: str):
    require(isinstance(document, dict), f"Invalid {split} document shape.")
    require(document.get("schema_version") == 1, f"Invalid {split} schema version.")
    require(document.get("synthetic_only") is True, f"Invalid {split} provenance flag.")
    require(document.get("split") == split, f"Invalid {split} declaration.")
    cases = document.get("cases")
    require(isinstance(cases, list) and bool(cases), f"Missing {split} cases.")
    ids, families, customers, products, transactions, utterances = (set() for _ in range(6))
    for case in cases:
        require(isinstance(case, dict), f"Invalid {split} case shape.")
        case_id = case.get("id")
        require(isinstance(case_id, str) and bool(case_id.strip()), f"Invalid {split} case ID.")
        require(case_id not in ids, f"Duplicate {split} case ID.")
        ids.add(case_id)
        require(case.get("split") == split, f"Misassigned {split} case.")
        require(case.get("language") in ("es", "pt"), f"Invalid {split} language.")
        for field in ("category", "scenario_family_id", "provenance"):
            require(isinstance(case.get(field), str) and bool(case[field].strip()), f"Invalid {split} case metadata.")
        families.add(case["scenario_family_id"])
        session = case.get("session")
        require(isinstance(session, dict), f"Invalid {split} session.")
        owner = session.get("authenticated_customer_id")
        require(isinstance(owner, str) and bool(owner), f"Invalid {split} session owner.")
        customers.add(owner)
        for field in ("authorized_product_ids", "authorized_account_ids"):
            values = session.get(field)
            require(isinstance(values, list) and bool(values) and all(isinstance(v, str) and bool(v) for v in values), f"Invalid {split} authorization list.")
        products.update(session["authorized_product_ids"])
        snapshots = case.get("record_snapshots")
        require(isinstance(snapshots, dict), f"Invalid {split} snapshots.")
        records = snapshots.get("transactions")
        require(isinstance(records, list) and bool(records), f"Invalid {split} transaction snapshots.")
        for record in records:
            require(isinstance(record, dict), f"Invalid {split} transaction shape.")
            for field, target in (("customer_id", customers), ("product_id", products), ("transaction_id", transactions)):
                value = record.get(field)
                require(isinstance(value, str) and bool(value), f"Invalid {split} record identifier.")
                target.add(value)
        turns = case.get("user_turns")
        require(isinstance(turns, list) and bool(turns) and all(isinstance(t, str) and bool(t.strip()) for t in turns), f"Invalid {split} user turns.")
        utterances.update(normalized(turn) for turn in turns)
        expected = case.get("expected")
        require(isinstance(expected, dict), f"Invalid {split} expected result.")
        require(expected.get("intent") in ("inquiry", "dispute_intake", "human_request", "unsupported"), f"Invalid {split} intent label.")
        require(expected.get("response_language") == case["language"], f"Invalid {split} response language.")
        require(type(expected.get("authorized_mutation_count")) is int and expected["authorized_mutation_count"] >= 0, f"Invalid {split} mutation count.")
    return cases, {"case_ids": ids, "scenario_families": families, "customers": customers, "products": products, "transactions": transactions, "literal_user_turns": utterances}


def verify_repository_boundary(root: Path, private_path: Path) -> None:
    # Git is optional for a downloaded source archive. Never modify global config.
    if not (root / ".git").exists():
        print("Git boundary: unavailable in source archive; verify exclusions before publishing.")
        return
    prefix = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root)]
    relative = private_path.relative_to(root).as_posix()
    try:
        ignored = subprocess.run(prefix + ["check-ignore", "-q", "--", relative], capture_output=True, check=False)
        tracked = subprocess.run(prefix + ["ls-files", "--", "evaluation/final_private/"], capture_output=True, check=False)
    except OSError:
        raise EvaluationError("Git executable unavailable; cannot verify private-file exclusion.") from None
    require(ignored.returncode == 0, "Final cases must be ignored by Git.")
    require(tracked.returncode == 0 and not tracked.stdout.strip(), "Private evaluation files are tracked or Git verification failed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        manifest = read_json(root / "evaluation/final_manifest.json", "manifest")
        require(isinstance(manifest, dict) and manifest.get("schema_version") == 1, "Invalid manifest schema.")
        require(manifest.get("case_file") == "evaluation/final_private/cases.json", "Unexpected final case path.")
        private_path = root / "evaluation/final_private/cases.json"
        try:
            digest = hashlib.sha256(private_path.read_bytes()).hexdigest()
        except OSError:
            raise EvaluationError("Local final cases unavailable; sealed evaluation cannot be verified from the public repository alone.") from None
        require(digest == manifest.get("sha256"), "Final case hash differs from the sealed commitment.")
        dev, dev_sets = validate_cases(read_json(root / "evaluation/development.json", "development"), "development")
        final, final_sets = validate_cases(read_json(private_path, "private final"), "final")
        for group in dev_sets:
            require(not dev_sets[group].intersection(final_sets[group]), f"Development/final overlap in {group}.")
        require(len(final) == manifest.get("case_count"), "Final case count differs from manifest.")
        for field, key in (("language", "language_counts"), ("category", "category_counts")):
            require(dict(Counter(c[field] for c in final)) == manifest.get(key), "Final aggregate counts differ from manifest.")
        require(dict(Counter(c["expected"]["intent"] for c in final)) == manifest.get("intent_counts"), "Final intent counts differ from manifest.")
        eligible = [c for c in final if c["session"]["pending_action"] is None]
        require(len(eligible) == manifest.get("component_case_count"), "Final component count differs from manifest.")
        require(dict(Counter(c["expected"]["intent"] for c in eligible)) == manifest.get("component_intent_counts"), "Final component intent counts differ from manifest.")
        verify_repository_boundary(root, private_path)
        print(f"PASS: {len(dev)} development cases; {len(final)} sealed final cases; SHA256 verified.")
        print("PASS: disjoint customer/product/transaction/scenario-family IDs and literal user turns.")
        print("PASS: private final inputs remain ignored and untracked when Git is present.")
        print("No model, baseline, workflow, paid API, or evaluation scoring was run.")
        return 0
    except EvaluationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
