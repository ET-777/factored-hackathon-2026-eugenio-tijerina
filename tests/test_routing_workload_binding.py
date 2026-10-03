"""Binding contracts using only authored synthetic data and temporary files."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, datetime
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_service.actions import _snapshot
from bank_service.cohort_repository import load_private_cohort
from bank_service.records import TransactionRecord
from bank_service.transactions import SourceReference, SourcedTransaction
from scripts import bind_routing_workload as binder


def source_entry(number, *, owner=None, kind="Purchase", status="Approved"):
    record = TransactionRecord(
        f"SYNTH-T-{number}", owner or f"SYNTH-C-{number}", f"SYNTH-P-{number}",
        datetime(2026, 6, 16, 12, 30), date(2026, 6, 17), kind,
        Decimal("12.3000000000000001"), "USD", status, "SYNTHETIC-MERCHANT",
    )
    return SourcedTransaction(record, (SourceReference("transactions/synthetic.csv", number, "a" * 64),))


def repository(*entries):
    return {entry.record.transaction_id: entry for entry in entries}


def workload(split, families):
    examples = []
    for family, intent in families:
        for language in ("es", "pt"):
            examples.append({"id": f"{family}-{language}", "family_id": family,
                             "language": language, "text": f"Authored {split} {family} {language}", "intent": intent})
    return {"schema_version": 1, "split": split, "provenance": "codex_authored",
            "review_status": binder.REVIEW_STATUS, "examples": examples}


def workload_pair(train=None, development=None):
    return {"train": workload("train", train or [("tr-inquiry", "inquiry")]),
            "development": workload("development", development or [("dev-human", "human_request")])}


class BindingTests(unittest.TestCase):
    def test_constrained_matching_moves_withdrawal_to_preserve_purchase_owner(self):
        docs = workload_pair(
            [("tr-context", "inquiry"), ("tr-purchase", "dispute_intake")],
            [("dev-cash-not-dispensed", "dispute_intake"), ("dev-purchase", "dispute_intake")],
        )
        records = repository(source_entry(1, owner="A", kind="Withdrawal"),
                             source_entry(2, owner="A"), source_entry(3, owner="B", kind="Withdrawal"),
                             source_entry(4, owner="C", status="Pending"), source_entry(5, owner="D", kind="Deposit"))
        before = deepcopy((docs, records))
        rows, counts = binder.build_bindings(docs, records)
        self.assertEqual((docs, records), before)
        self.assertEqual(sum(c["unavailable_examples"] for c in counts.values()), 0)
        by_family = {row["family_id"]: row for row in rows}
        self.assertEqual(len({r["system_context"]["trusted_customer_id"] for r in by_family.values()}), 4)
        self.assertEqual(len({r["system_context"]["target_transaction_id"] for r in by_family.values()}), 4)
        cash = by_family["dev-cash-not-dispensed"]
        self.assertEqual(records[cash["system_context"]["target_transaction_id"]].record.transaction_type, "Withdrawal")
        self.assertFalse(cash["scorer_metadata"]["expected_synthetic_intake_eligible"])
        for family in ("tr-purchase", "dev-purchase"):
            self.assertTrue(by_family[family]["scorer_metadata"]["expected_synthetic_intake_eligible"])
        for family in by_family:
            translations = [row for row in rows if row["family_id"] == family]
            self.assertEqual(translations[0]["system_context"], translations[1]["system_context"])

    def test_record_iteration_order_does_not_change_assignments(self):
        docs = workload_pair()
        records = repository(source_entry(3), source_entry(2), source_entry(1))
        self.assertEqual(binder.build_bindings(docs, records),
                         binder.build_bindings(docs, dict(reversed(list(records.items())))))

    def test_unavailable_examples_remain_with_null_anchor_and_eligibility(self):
        docs = workload_pair([("tr-dispute", "dispute_intake")],
                             [("dev-cash-not-dispensed", "dispute_intake")])
        rows, counts = binder.build_bindings(docs, repository(source_entry(1, kind="Withdrawal")))
        self.assertEqual(len(rows), 4)
        self.assertEqual(counts["train"]["unavailable_examples"], 2)
        for row in rows[:2]:
            self.assertEqual(row["binding_status"], "binding_unavailable")
            self.assertIsNone(row["system_context"])
            self.assertIsNone(row["snapshot_hash"])
            self.assertIsNone(row["scorer_metadata"]["expected_synthetic_intake_eligible"])
            self.assertEqual(row["source_references"], [])

    def test_multiple_transactions_for_one_customer_cannot_anchor_two_families(self):
        rows, counts = binder.build_bindings(workload_pair(), repository(
            source_entry(1, owner="SHARED-SYNTHETIC"), source_entry(2, owner="SHARED-SYNTHETIC")))
        self.assertEqual(sum(c["bound_families"] for c in counts.values()), 1)
        self.assertEqual(sum(r["binding_status"] == "binding_unavailable" for r in rows), 2)

    def test_declined_and_reversed_purchases_are_not_intake_eligible(self):
        docs = workload_pair([("tr-dispute", "dispute_intake")])
        for status in ("Declined", "Reversed"):
            with self.subTest(status=status):
                rows, counts = binder.build_bindings(docs, repository(source_entry(1, status=status)))
                self.assertEqual(counts["train"]["bound_examples"], 0)
                self.assertFalse(rows[-1]["scorer_metadata"]["expected_synthetic_intake_eligible"])

    def test_snapshot_matches_runtime_and_scorer_label_is_separate(self):
        docs = workload_pair([("tr-unsupported", "unsupported")])
        records = repository(source_entry(1), source_entry(2))
        rows, _ = binder.build_bindings(docs, records)
        for row in rows:
            context = row["system_context"]
            self.assertEqual(set(context), {"trusted_customer_id", "target_transaction_id"})
            entry = records[context["target_transaction_id"]]
            self.assertEqual(row["snapshot_hash"], _snapshot(entry)[0])
            self.assertEqual(row["source_references"], [asdict(r) for r in entry.sources])
            self.assertTrue(row["scorer_metadata"]["eligibility_is_not_action_authorization"])
            self.assertNotIn("text", row)
            self.assertNotIn("amount", row)

    def test_rejects_missing_or_excessive_repository(self):
        invalid = ({}, [], repository(*(source_entry(n) for n in range(1, 202))), {"bad": source_entry(1)})
        for records in invalid:
            with self.subTest(kind=type(records).__name__), self.assertRaisesRegex(binder.BindingError, "^invalid_cohort$"):
                binder.build_bindings(workload_pair(), records)


class WorkloadValidationTests(unittest.TestCase):
    def test_rejects_extra_keys_bool_schema_unknown_labels_and_malformed_examples(self):
        original = workload_pair()
        variants = []
        for mutate in (
            lambda d: d["train"].update(extra="SYNTHETIC_PRIVATE_MARKER"),
            lambda d: d["train"].update(schema_version=True),
            lambda d: d["train"].update(review_status="approved"),
            lambda d: d["train"].update(examples=[]),
            lambda d: d["train"]["examples"][0].update(intent="SYNTHETIC_PRIVATE_MARKER"),
            lambda d: d["train"]["examples"][0].update(language="en"),
            lambda d: d["train"]["examples"][0].update(id="ID-ñ"),
            lambda d: d["train"]["examples"][0].update(text=" " * 2),
            lambda d: d["train"]["examples"][0].update(text="x" * 1001),
            lambda d: d["train"]["examples"][0].update(text=["SYNTHETIC_PRIVATE_MARKER"]),
            lambda d: d["train"]["examples"][0].update(extra="value"),
            lambda d: d["train"]["examples"][1].update(intent="dispute_intake"),
        ):
            doc = deepcopy(original)
            mutate(doc)
            variants.append(doc)
        for document in variants:
            with self.subTest(), self.assertRaises(binder.BindingError) as caught:
                binder.validate_workload_pair(document)
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", str(caught.exception))

    def test_rejects_cross_split_ids_families_and_normalized_text(self):
        for field in ("id", "family_id", "text"):
            document = workload_pair()
            source = document["train"]["examples"][0][field]
            document["development"]["examples"][0][field] = source.upper() + " " if field == "text" else source
            with self.subTest(field=field), self.assertRaisesRegex(binder.BindingError, "^cross_split_overlap$"):
                binder.validate_workload_pair(document)

    def test_duplicate_json_key_and_nonfinite_constant_rejected(self):
        for body in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.subTest(), self.assertRaisesRegex(binder.BindingError, "^invalid_json$"):
                binder._decode(body)


class BindingFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="factored-routing-bindings-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_artifacts(self):
        (self.root / "evaluation").mkdir()
        docs = workload_pair()
        for split, document in docs.items():
            (self.root / f"evaluation/routing_{split}.json").write_text(json.dumps(document), encoding="utf-8")

    def write_cohort(self):
        run = self.root / "synthetic-cohort"
        run.mkdir()
        records = repository(source_entry(1), source_entry(2))
        customers, products, transactions = [], [], []
        for entry in records.values():
            r = entry.record
            source = lambda name: [{"file": name, "row_number": entry.sources[0].row_number, "row_sha256": "a" * 64}]
            customers.append({"record": {"customer_id": r.customer_id, "registration_date": "2026-01-01T00:00:00"}, "sources": source("customers.csv")})
            products.append({"record": {"product_id": r.product_id, "customer_id": r.customer_id,
                                          "currency": r.currency, "opening_date": "2026-01-02"}, "sources": source("products.csv")})
            values = {k: (v.isoformat() if isinstance(v, (date, datetime)) else str(v) if isinstance(v, Decimal) else v) for k, v in asdict(r).items()}
            transactions.append({"record": values, "sources": [asdict(ref) for ref in entry.sources]})
        payload = {"customers": customers, "products": products, "transactions": transactions}
        manifest = {"schema_version": 1, "selected_size": 2, "requested_size": 50,
                    "process_dates": ["2026-06-17"],
                    "sources": [{"file": file, "row_count": 10, "byte_count": 100, "file_sha256": "b" * 64}
                                for file in ("customers.csv", "products.csv", "transactions/synthetic.csv")]}
        for name, document in (("manifest.json", manifest), ("cohort.json", payload), ("quarantine.json", [])):
            (run / name).write_text(json.dumps(document), encoding="utf-8")
        return run, records

    def test_end_to_end_synthetic_binding_calls_loader_and_hashes_inputs(self):
        self.write_artifacts()
        run, records = self.write_cohort()
        with patch.object(binder, "load_private_cohort", wraps=load_private_cohort) as loader:
            summary = binder.create_bindings(run, "synthetic-run", project_root=self.root)
        loader.assert_called_once_with(run)
        self.assertEqual(summary["status"], "bindings_created_no_execution")
        self.assertEqual(summary["counts"]["development"]["unavailable_examples"], 0)
        path = self.root / "data/routing_workloads/synthetic-run/bindings.json"
        output = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(output["review_status"], binder.REVIEW_STATUS)
        self.assertFalse(output["scorer_metadata_is_system_input"])
        self.assertFalse(output["routing_fitting_prediction_scoring_or_actions_executed"])
        self.assertEqual(len(output["cohort_inputs"]["manifest.json"]["sha256"]), 64)
        self.assertEqual(len(output["bindings"]), 4)
        self.assertEqual(load_private_cohort(run), records)

    def test_loader_result_must_match_hashed_cohort_bytes(self):
        run, records = self.write_cohort()
        first = next(iter(records))
        records[first] = replace(records[first], record=replace(records[first].record, amount=Decimal("7")))
        with patch.object(binder, "load_private_cohort", return_value=records):
            with self.assertRaisesRegex(binder.BindingError, "^cohort_snapshot_mismatch$"):
                binder.load_cohort_snapshot(run)

    def test_cohort_changed_during_loader_rejected(self):
        run, _ = self.write_cohort()
        def change_then_load(path):
            with (path / "cohort.json").open("a", encoding="utf-8") as stream:
                stream.write(" ")
            return load_private_cohort(path)
        with patch.object(binder, "load_private_cohort", side_effect=change_then_load):
            with self.assertRaisesRegex(binder.BindingError, "^cohort_changed_during_read$"):
                binder.load_cohort_snapshot(run)

    def test_authored_input_byte_cap(self):
        self.write_artifacts()
        (self.root / "evaluation/routing_train.json").write_bytes(b" " * (binder.MAX_ARTIFACT_BYTES + 1))
        with self.assertRaisesRegex(binder.BindingError, "^input_limit_exceeded$"):
            binder.load_workloads(self.root)

    def test_fixed_workload_rejects_file_and_directory_redirection(self):
        self.write_artifacts()
        root = self.root.resolve()
        original_resolve = Path.resolve
        # Mock the resolved targets rather than require Windows symlink privilege.
        # Both destinations remain inside the project: containment alone fails.
        for redirected_base in (root / "evaluation/routing_train.json", root / "evaluation"):
            def redirected(path, *args, **kwargs):
                if path.is_relative_to(redirected_base):
                    return root / "alternate-input" / path.relative_to(redirected_base)
                return original_resolve(path, *args, **kwargs)
            with self.subTest(), patch.object(Path, "resolve", redirected), patch.object(binder, "_read_bounded") as read:
                with self.assertRaisesRegex(binder.BindingError, "^input_path_redirected$"):
                    binder.load_workloads(self.root)
                read.assert_not_called()

    def test_private_output_rejects_redirected_parent_within_project(self):
        root = self.root.resolve()
        original_resolve = Path.resolve
        for redirected_base in (root / "data", root / "data/routing_workloads"):
            def redirected(path, *args, **kwargs):
                if path.is_relative_to(redirected_base):
                    return root / "public-output" / path.relative_to(redirected_base)
                return original_resolve(path, *args, **kwargs)
            with self.subTest(), patch.object(Path, "resolve", redirected):
                with self.assertRaisesRegex(binder.BindingError, "^output_path_redirected$"):
                    binder.write_private_bindings(self.root, "synthetic-run", {"private": "SYNTHETIC"})
            self.assertFalse((root / "public-output").exists())
            self.assertFalse((root / "data").exists())

    def test_run_directory_rejects_in_project_redirection(self):
        root = self.root.resolve()
        intended = root / "data/routing_workloads/synthetic-run"
        original_resolve = Path.resolve
        def redirected(path, *args, **kwargs):
            if path == intended:
                return intended.parent / "another-run"
            return original_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", redirected):
            with self.assertRaisesRegex(binder.BindingError, "^output_path_redirected$"):
                binder.write_private_bindings(self.root, "synthetic-run", {})
        self.assertFalse((root / "data").exists())

    def test_exclusive_run_preserves_existing_bytes(self):
        path = binder.write_private_bindings(self.root, "existing", {"synthetic": "first"})
        before = path.read_bytes()
        with self.assertRaisesRegex(binder.BindingError, "^output_exists$"):
            binder.write_private_bindings(self.root, "existing", {"synthetic": "replacement"})
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_output_name_does_not_create_directories(self):
        for name in ("../escape", "../routing_workloads-other/run", "C:/private", "a/b", "a\\b", "CON", "COM1", "ñ", "", "x" * 65):
            with self.subTest(name=name), self.assertRaisesRegex(binder.BindingError, "^invalid_run_name$"):
                binder.write_private_bindings(self.root, name, {})
        self.assertFalse((self.root / "data").exists())

    def test_cli_failures_do_not_echo_private_argument_or_exception(self):
        for args in (["--cohort-run", "SYNTHETIC_PRIVATE_MARKER", "--run-name", "../private"],
                     ["--unknown", "SYNTHETIC_PRIVATE_MARKER"]):
            out, err = io.StringIO(), io.StringIO()
            with patch("sys.stdout", out), patch("sys.stderr", err):
                self.assertEqual(binder.main(args), 2)
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", out.getvalue() + err.getvalue())
        out, err = io.StringIO(), io.StringIO()
        with patch.object(binder, "create_bindings", side_effect=OSError("SYNTHETIC_PRIVATE_MARKER")), patch("sys.stdout", out), patch("sys.stderr", err):
            self.assertEqual(binder.main(["--cohort-run", "SYNTHETIC_PRIVATE_MARKER", "--run-name", "valid"]), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(json.loads(err.getvalue())["code"], "unexpected_binding_error")

    def test_cohort_loader_failure_is_sanitized(self):
        run, _ = self.write_cohort()
        with patch.object(binder, "load_private_cohort", side_effect=ValueError("SYNTHETIC_PRIVATE_MARKER")):
            with self.assertRaisesRegex(binder.BindingError, "^cohort_validation_failed$") as caught:
                binder.load_cohort_snapshot(run)
        self.assertTrue(caught.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
