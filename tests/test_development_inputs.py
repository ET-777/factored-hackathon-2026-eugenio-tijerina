"""Development-input validation with authored synthetic temporary files only."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_service.development_inputs import DevelopmentInputError, load_development_inputs
from bank_service import development_inputs as inputs
from scripts import bind_routing_workload as binder


def canonical_hash(value):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def authored_workload(split, intent):
    return {
        "schema_version": 1, "split": split, "provenance": "codex_authored",
        "review_status": binder.REVIEW_STATUS,
        "examples": [{"id": f"{split}-synthetic-{language}", "family_id": f"{split}-synthetic-family",
                      "language": language, "text": f"{split}: ¿Cuál? {language}", "intent": intent}
                     for language in ("es", "pt")],
    }


class DevelopmentInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="factored-development-inputs-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.binding_run = "synthetic-routing"
        self.cohort = self.root / "data/private_cohort/synthetic-cohort"
        self.cohort.mkdir(parents=True)
        self.documents = {"train": authored_workload("train", "inquiry"),
                          "development": authored_workload("development", "human_request")}
        for split, document in self.documents.items():
            self.write_json(self.root / f"evaluation/routing_{split}.json", document)
        payload = {"customers": [], "products": [], "transactions": []}
        for number in (1, 2):
            owner, product, transaction = (f"SYNTHETIC-{kind}-{number}" for kind in ("CUSTOMER", "PRODUCT", "TRANSACTION"))
            def sources(file):
                return [{"file": file, "row_number": number, "row_sha256": "a" * 64}]
            payload["customers"].append({"record": {"customer_id": owner, "registration_date": "2026-01-01T00:00:00"},
                                         "sources": sources("customers.csv")})
            payload["products"].append({"record": {"product_id": product, "customer_id": owner, "currency": "USD", "opening_date": "2026-01-02"},
                                        "sources": sources("products.csv")})
            payload["transactions"].append({"record": {
                "transaction_id": transaction, "customer_id": owner, "product_id": product,
                "transaction_date": "2026-06-16T12:00:00", "process_date": "2026-06-17",
                "transaction_type": "Purchase", "amount": "10.00", "currency": "USD",
                "transaction_status": "Approved", "merchant_name": None,
            }, "sources": sources("transactions/synthetic.csv")})
        manifest = {"schema_version": 1, "requested_size": 50, "selected_size": 2,
                    "process_dates": ["2026-06-17"],
                    "sources": [{"file": name, "row_count": 10, "byte_count": 100, "file_sha256": "b" * 64}
                                for name in ("customers.csv", "products.csv", "transactions/synthetic.csv")]}
        for name, value in (("manifest.json", manifest), ("cohort.json", payload), ("quarantine.json", [])):
            self.write_json(self.cohort / name, value)
        binder.create_bindings(self.cohort, self.binding_run, project_root=self.root)
        self.binding_path = self.root / f"data/routing_workloads/{self.binding_run}/bindings.json"
        self.review_path = self.root / "evidence/routing_language_review.json"
        self.review = self.make_review()
        self.write_json(self.review_path, self.review)

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def make_review(self):
        rows = {split: sorted([deepcopy(row) for row in document["examples"] if row["language"] == "es"],
                              key=lambda row: row["id"])
                for split, document in self.documents.items()}
        artifacts = {}
        for split in ("train", "development"):
            relative = f"evaluation/routing_{split}.json"
            artifacts[split] = {
                "artifact_review_status": binder.REVIEW_STATUS,
                "canonical_es_rows_sha256": canonical_hash(rows[split]),
                "es_examples": len(rows[split]), "es_families": len({row["family_id"] for row in rows[split]}),
                "es_intent_counts": dict(Counter(row["intent"] for row in rows[split])),
                "file_sha256": hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), "path": relative,
            }
        combined = sorted(rows["train"] + rows["development"], key=lambda row: row["id"])
        return {
            "schema_version": 1, "review_date": "2026-10-03",
            "review_source": "explicit_owner_approval_in_project_conversation",
            "owner_statement": "Synthetic owner evidence, not real approval.",
            "current_language_review_status": {"spanish_owner_wording_and_intent_labels": "approved",
                                               "portuguese_fluent_human_review": "pending"},
            "approved_scope": {"language": "es", "fields": ["text", "intent"],
                               "train_examples": 1, "development_examples": 1, "total_examples": 2,
                               "reviewer_role": "project_owner", "independent_external_reviewer": False},
            "artifacts": artifacts,
            "combined_spanish_review": {"canonical_es_rows_sha256": canonical_hash(combined),
                                        "es_examples": 2, "es_families": 2},
            "canonicalization": {
                "row_selection": "language_exactly_es", "row_fields": ["id", "family_id", "language", "text", "intent"],
                "row_order": "id_ascending", "encoding": "UTF-8", "json_sort_keys": True,
                "json_ensure_ascii": False, "json_separators": [",", ":"],
                "trailing_newline": False, "value_normalization": "none_exact_decoded_row_values",
            },
            "approval_limits": ["Synthetic test evidence only."],
            "artifact_metadata_policy": "Keep the draft artifact review status unchanged.",
            "actions_in_this_review": {"fitting": False, "scoring": False},
        }

    def load(self, **changes):
        arguments = {"project_root": self.root, "cohort_run": self.cohort, "binding_run": self.binding_run}
        arguments.update(changes)
        return load_development_inputs(**arguments)

    def test_valid_snapshots_and_exact_file_hashes_without_writes(self):
        paths = [self.binding_path, self.review_path, self.cohort / "cohort.json",
                 self.root / "evaluation/routing_train.json", self.root / "evaluation/routing_development.json"]
        before = {path: path.read_bytes() for path in paths}
        result = self.load()
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(result.binding_rows), 4)
        self.assertEqual(result.workloads, self.documents)
        self.assertEqual(result.binding_hash, hashlib.sha256(before[self.binding_path]).hexdigest())
        self.assertEqual(result.review_hash, hashlib.sha256(before[self.review_path]).hexdigest())
        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        self.assertNotIn("SYNTHETIC-CUSTOMER", repr(result))

    def test_review_artifact_file_hash_mismatch(self):
        self.review["artifacts"]["train"]["file_sha256"] = "0" * 64
        self.write_json(self.review_path, self.review)
        with self.assertRaisesRegex(DevelopmentInputError, "^review_artifact_commitment_mismatch$"):
            self.load()

    def test_per_artifact_and_combined_canonical_hash_mismatch(self):
        original = deepcopy(self.review)
        for target, code in (("artifact", "review_artifact_commitment_mismatch"), ("combined", "combined_review_commitment_mismatch")):
            changed = deepcopy(original)
            destination = changed["artifacts"]["development"] if target == "artifact" else changed["combined_spanish_review"]
            destination["canonical_es_rows_sha256"] = "0" * 64
            self.write_json(self.review_path, changed)
            with self.subTest(target=target), self.assertRaisesRegex(DevelopmentInputError, f"^{code}$"):
                self.load()

    def test_exact_row_value_change_requires_new_canonical_approval_even_if_file_hash_updated(self):
        self.documents["train"]["examples"][0]["text"] += " "
        path = self.root / "evaluation/routing_train.json"
        self.write_json(path, self.documents["train"])
        self.review["artifacts"]["train"]["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write_json(self.review_path, self.review)
        binder.create_bindings(self.cohort, "new-synthetic-bindings", project_root=self.root)
        with self.assertRaisesRegex(DevelopmentInputError, "^review_artifact_commitment_mismatch$"):
            self.load(binding_run="new-synthetic-bindings")

    def test_context_reference_snapshot_label_and_summary_tampering_rejected(self):
        original = self.read_json(self.binding_path)
        for mutate in (
            lambda d: d["bindings"][0]["system_context"].update(trusted_customer_id="PRIVATE-SYNTHETIC-MARKER"),
            lambda d: d["bindings"][0]["source_references"][0].update(row_number=8),
            lambda d: d["bindings"][0].update(snapshot_hash="0" * 64),
            lambda d: d["bindings"][0]["scorer_metadata"].update(intent="unsupported"),
            lambda d: d["summary"]["train"].update(bound_examples=0),
            lambda d: d.update(schema_version=True),
            lambda d: d.update(extra="PRIVATE-SYNTHETIC-MARKER"),
        ):
            changed = deepcopy(original)
            mutate(changed)
            self.write_json(self.binding_path, changed)
            with self.subTest(), self.assertRaisesRegex(DevelopmentInputError, "^binding_document_mismatch$") as caught:
                self.load()
            self.assertNotIn("PRIVATE-SYNTHETIC-MARKER", str(caught.exception))

    def test_review_scope_language_and_canonicalization_are_not_silently_changed(self):
        original = deepcopy(self.review)
        for mutate, code in (
            (lambda r: r["approved_scope"].update(train_examples=True), "review_scope_mismatch"),
            (lambda r: r["current_language_review_status"].update(spanish_owner_wording_and_intent_labels="pending"), "review_language_status_mismatch"),
            (lambda r: r["current_language_review_status"].update(portuguese_fluent_human_review="approved"), "review_language_status_mismatch"),
            (lambda r: r["canonicalization"].update(value_normalization="NFKC"), "review_canonicalization_mismatch"),
            (lambda r: r["actions_in_this_review"].update(scoring=True), "invalid_review_actions"),
            (lambda r: r.update(schema_version=True), "invalid_review_schema"),
            (lambda r: r.update(review_source="PRIVATE-SYNTHETIC-MARKER"), "invalid_review_source"),
        ):
            changed = deepcopy(original)
            mutate(changed)
            self.write_json(self.review_path, changed)
            with self.subTest(), self.assertRaisesRegex(DevelopmentInputError, f"^{code}$"):
                self.load()

    def test_duplicate_keys_nonfinite_json_and_limits_rejected(self):
        original = self.binding_path.read_bytes()
        for body in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e400}', b" " * (inputs.MAX_BINDING_BYTES + 1)):
            self.binding_path.write_bytes(body)
            with self.subTest(), self.assertRaises(DevelopmentInputError):
                self.load()
        self.binding_path.write_bytes(original)
        self.review_path.write_bytes(b" " * (inputs.MAX_REVIEW_BYTES + 1))
        with self.assertRaisesRegex(DevelopmentInputError, "^input_file_invalid$"):
            self.load()

    def test_non_cohort_paths_rejected_before_workload_or_cohort_reads(self):
        for relative in ("evaluation/sealed/synthetic", "data/source/synthetic.csv", "references/synthetic.pdf", "data/private_cohort/child/grandchild"):
            with self.subTest(relative=relative), patch.object(binder, "load_workloads") as workload_loader, patch.object(binder, "load_cohort_snapshot") as cohort_loader:
                with self.assertRaisesRegex(DevelopmentInputError, "^invalid_cohort_path$"):
                    self.load(cohort_run=self.root / relative)
                workload_loader.assert_not_called()
                cohort_loader.assert_not_called()

    def test_invalid_binding_run_does_not_reach_any_input_loader(self):
        for value in ("../other", "synthetic.csv", "CON", Path("data/routing_workloads/run"), "a/b"):
            with self.subTest(), patch.object(binder, "load_workloads") as loader:
                with self.assertRaisesRegex(DevelopmentInputError, "^invalid_binding_run$"):
                    self.load(binding_run=value)
                loader.assert_not_called()

    def test_private_review_and_cohort_redirections_rejected_without_alternate_reads(self):
        original_resolve = Path.resolve
        for target in (self.binding_path, self.review_path, self.cohort,
                       self.cohort / "cohort.json", self.cohort / "manifest.json", self.cohort / "quarantine.json"):
            def redirected(path, *args, **kwargs):
                if path == target:
                    return self.root / "other-inside-project" / target.name
                return original_resolve(path, *args, **kwargs)
            with self.subTest(), patch.object(Path, "resolve", redirected), patch.object(binder, "load_workloads") as loader:
                with self.assertRaisesRegex(DevelopmentInputError, "^input_path_redirected$"):
                    self.load()
                loader.assert_not_called()

    def test_authored_path_redirection_is_rejected_by_fixed_loader(self):
        original_resolve = Path.resolve
        target = self.root / "evaluation/routing_train.json"
        def redirected(path, *args, **kwargs):
            if path == target:
                return self.root / "other-inside-project/train.json"
            return original_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", redirected), patch.object(binder, "load_cohort_snapshot") as cohort_loader:
            with self.assertRaisesRegex(DevelopmentInputError, "^binding_input_validation_failed$"):
                self.load()
            cohort_loader.assert_not_called()

    def test_absent_review_fails_closed(self):
        self.review_path.unlink()
        with self.assertRaisesRegex(DevelopmentInputError, "^input_file_invalid$"):
            self.load()


if __name__ == "__main__":
    unittest.main()
