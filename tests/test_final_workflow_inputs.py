"""Fresh-benchmark input contracts using synthetic disposable files only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_service.access import Permission
from bank_service import final_workflow_inputs as inputs
from scripts import bind_routing_workload as binder


def toy_cases():
    cases = []
    for number in range(24):
        service = number < 16
        intent = sorted(inputs.INTENTS)[number // 4] if service else None
        for language in ("es", "pt"):
            text = f"Fabricated cue {number} {language} {{transaction_id}}"
            cases.append({
                "id": f"TOY-CASE-{number}-{language}", "family_id": f"TOY-FAMILY-{number}",
                "language": language, "stratum": "service" if service else "simulated_safety",
                "intent": intent, "component_text": text if service else None,
                "record_role": "any", "permissions": [permission.value for permission in Permission],
                "scenario": f"TOY-SCENARIO-{number}", "steps": [{"kind": "message", "text": text}],
                "expected": {"terminal": "answered", "writes": 0, "purpose": None,
                             "requires_record": True, "required_unknown": None,
                             "required_statuses": ["answered"], "expected_error": None},
            })
    return {"schema_version": 1, "cases": cases}


class FinalCaseValidationTests(unittest.TestCase):
    def test_fixed_population_and_language_family_contract(self):
        doc = toy_cases()
        cases = inputs.validate_cases(doc)
        self.assertEqual(cases, doc["cases"])
        self.assertEqual(inputs.expected_counts(cases), {
            "cases": 48, "families": 24, "service": 32, "simulated_safety": 16,
            "by_language": {"es": 24, "pt": 24},
            "service_intents": dict.fromkeys(inputs.INTENTS, 8),
        })

    def test_bad_schema_duplicates_distribution_and_family_mismatches(self):
        for mutate, code in (
            (lambda d: d.update(schema_version=True), "invalid_cases_document"),
            (lambda d: d["cases"].pop(), "invalid_case_count"),
            (lambda d: d["cases"][0].update(extra="PRIVATE-CANARY"), "invalid_case_schema"),
            (lambda d: d["cases"][1].update(id=d["cases"][0]["id"]), "duplicate_case_id"),
            (lambda d: d["cases"][0].update(intent="unknown"), "invalid_case_intent"),
            (lambda d: d["cases"][32].update(component_text="PRIVATE-CANARY"), "invalid_safety_component"),
            (lambda d: d["cases"][0].update(language="en"), "invalid_case_language"),
            (lambda d: d["cases"][1].update(scenario="Different"), "inconsistent_family_metadata"),
            (lambda d: d["cases"][1]["expected"].update(writes=1), "inconsistent_family_expected"),
            (lambda d: d["cases"][1]["steps"].append({"kind": "cancel"}), "inconsistent_family_steps"),
        ):
            document = toy_cases()
            mutate(document)
            with self.subTest(code=code):
                with self.assertRaisesRegex(inputs.FinalWorkflowInputError, "^" + code + "$") as caught:
                    inputs.validate_cases(document)
                self.assertNotIn("PRIVATE-CANARY", str(caught.exception))

    def test_strict_boolean_numeric_permission_and_text_boundaries(self):
        for mutate in (
            lambda c: c.update(permissions=[]),
            lambda c: c.update(permissions=[Permission.CREATE_SIMULATED_INTAKE.value]),
            lambda c: c.update(permissions=[Permission.READ_TRANSACTION.value] * 2),
            lambda c: c.update(permissions=["PRIVATE-CANARY"]),
            lambda c: c.update(component_text=" "),
            lambda c: c.update(component_text="x" * 1001),
            lambda c: c.update(component_text="\ud800"),
            lambda c: c["expected"].update(writes=True),
            lambda c: c["expected"].update(requires_record=1),
            lambda c: c["expected"].update(required_statuses=["invented_status"]),
            lambda c: c["expected"].update(expected_error="PRIVATE CANARY"),
            lambda c: c.update(steps=[{"kind": "respond_offer", "prepare": 1}]),
            lambda c: c.update(steps=[{"kind": "confirm", "confirmed": "yes"}]),
            lambda c: c.update(steps=[{"kind": "advance_clock", "seconds": True}]),
            lambda c: c.update(steps=[{"kind": "advance_clock", "seconds": 1801}]),
            lambda c: c.update(steps=[{"kind": "set_fault", "name": "arbitrary_fault"}]),
            lambda c: c.update(steps=[{"kind": "select_target", "id": "PRIVATE-CANARY"}]),
            lambda c: c.update(steps=[{"kind": "cancel"}] * 17),
        ):
            document = toy_cases()
            mutate(document["cases"][0])
            with self.subTest(mutation=mutate):
                with self.assertRaises(inputs.FinalWorkflowInputError) as caught:
                    inputs.validate_cases(document)
                self.assertNotIn("PRIVATE-CANARY", str(caught.exception))

    def test_template_fields_are_limited_and_cannot_access_attributes(self):
        for text in ("{private}", "{amount.__class__}", "{amount[0]}", "{amount!r}", "{amount:20}", "{}", "{"):
            document = toy_cases()
            document["cases"][0]["steps"][0]["text"] = text
            with self.subTest(template=text):
                with self.assertRaises(inputs.FinalWorkflowInputError):
                    inputs.validate_cases(document)
        document = toy_cases()
        for case in document["cases"]:
            case["steps"].append({"kind": "message", "text": "{amount} {currency} {date_dmy} {date_iso} {transaction_id}"})
        inputs.validate_cases(document)

    def test_component_probe_must_belong_to_exactly_one_message_even_after_context(self):
        document = toy_cases()
        for case in document["cases"]:
            case["steps"].insert(0, {"kind": "select_target"})
        inputs.validate_cases(document)
        for duplicate in (False, True):
            changed = deepcopy(document)
            case = changed["cases"][0]
            if duplicate:
                case["steps"].append({"kind": "message", "text": case["component_text"]})
            else:
                case["component_text"] = "A disconnected fabricated routing probe"
            with self.subTest(duplicate=duplicate):
                with self.assertRaisesRegex(inputs.FinalWorkflowInputError, "^component_message_mismatch$"):
                    inputs.validate_cases(changed)

    def test_all_fixed_script_operations_are_supported_with_paired_shapes(self):
        document = toy_cases()
        steps = [
            {"kind": "message", "text": "Toy message"}, {"kind": "select_target"},
            {"kind": "select_foreign"}, {"kind": "respond_offer", "prepare": False},
            {"kind": "confirm", "confirmed": True}, {"kind": "confirm_again"},
            {"kind": "cancel"}, {"kind": "advance_clock", "seconds": 1800},
            {"kind": "set_fault", "name": "write_failure"},
        ]
        for case in document["cases"]:
            case["steps"] = deepcopy(steps)
            case["steps"][0]["text"] = (case["component_text"] if case["stratum"] == "service"
                                          else f"Safety {case['id']}")
        inputs.validate_cases(document)


class FinalInputLoaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="factored-final-input-toys-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.document = toy_cases()
        payload = {"customers": [], "products": [], "transactions": []}
        for number in range(24):
            owner, product, transaction = (f"TOY-{kind}-{number}" for kind in ("OWNER", "PRODUCT", "TRANSACTION"))
            def sources(file):
                return [{"file": file, "row_number": number + 1, "row_sha256": "a" * 64}]
            payload["customers"].append({"record": {"customer_id": owner, "registration_date": "2026-01-01T00:00:00"}, "sources": sources("customers.csv")})
            payload["products"].append({"record": {"product_id": product, "customer_id": owner, "currency": "USD", "opening_date": "2026-01-02"}, "sources": sources("products.csv")})
            payload["transactions"].append({"record": {
                "transaction_id": transaction, "customer_id": owner, "product_id": product,
                "transaction_date": "2026-06-16T12:00:00", "process_date": "2026-06-17",
                "transaction_type": "Purchase", "amount": "10.00", "currency": "USD",
                "transaction_status": "Approved", "merchant_name": None,
            }, "sources": sources("transactions/toy.csv")})
        cohort_manifest = {
            "schema_version": 1, "requested_size": 50, "selected_size": 24,
            "process_dates": ["2026-06-17"],
            "sources": [{"file": file, "row_count": 24, "byte_count": 100, "file_sha256": "b" * 64}
                        for file in ("customers.csv", "products.csv", "transactions/toy.csv")],
        }
        cohort = self.root / inputs.COHORT_RUN
        for name, value in (("cohort.json", payload), ("manifest.json", cohort_manifest), ("quarantine.json", [])):
            self.write(cohort / name, value)
        records, hashes = binder.load_cohort_snapshot(cohort)
        case_path = self.root / inputs.CASE_PATH
        self.write(case_path, self.document)
        body = case_path.read_bytes()
        self.manifest = {
            "schema_version": 1, "benchmark_id": "final_workflow_v1",
            "cases_sha256": hashlib.sha256(body).hexdigest(), "cases_bytes": len(body),
            "counts": inputs.expected_counts(self.document["cases"]),
            "cohort_run": inputs.COHORT_RUN, "cohort_inputs": hashes,
            "family_bindings": {
                f"TOY-FAMILY-{number}": {
                    "trusted_customer_id": records[f"TOY-TRANSACTION-{number}"].record.customer_id,
                    "target_transaction_id": f"TOY-TRANSACTION-{number}",
                    "snapshot_hash": binder._snapshot_hash(records[f"TOY-TRANSACTION-{number}"]),
                } for number in range(24)
            },
        }
        self.write(self.root / inputs.MANIFEST_PATH, self.manifest)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_valid_bundle_is_read_only_hash_bound_and_uses_fixed_paths(self):
        paths = [path for path in self.root.rglob("*.json")]
        before = {path: path.read_bytes() for path in paths}
        with patch.object(binder, "_read_bounded", wraps=binder._read_bounded) as reads:
            result = inputs.load_final_inputs(self.root)
        self.assertEqual(len(result.cases), 48)
        self.assertEqual(len(result.records), 24)
        self.assertEqual(len(result.family_bindings), 24)
        self.assertEqual(result.cases_hash, self.manifest["cases_sha256"])
        self.assertEqual(result.manifest_hash, hashlib.sha256(before[self.root / inputs.MANIFEST_PATH]).hexdigest())
        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        self.assertNotIn("TOY-OWNER", repr(result))
        self.assertTrue(all(call.args[0].is_relative_to(self.root) for call in reads.call_args_list))
        self.assertFalse(any("final_private" in str(call.args[0]) for call in reads.call_args_list))

    def test_file_commitments_and_exact_typed_counts_cannot_be_forged(self):
        for mutate, code in (
            (lambda m: m.update(cases_sha256="0" * 64), "cases_commitment_mismatch"),
            (lambda m: m.update(cases_bytes=float(m["cases_bytes"])), "cases_commitment_mismatch"),
            (lambda m: m["counts"].update(cases=True), "manifest_counts_mismatch"),
            (lambda m: m["cohort_inputs"]["cohort.json"].update(sha256="0" * 64), "cohort_commitment_mismatch"),
            (lambda m: m.update(cohort_run="evaluation/final_private"), "invalid_cohort_path"),
            (lambda m: m.update(extra="PRIVATE-CANARY"), "invalid_manifest"),
        ):
            manifest = deepcopy(self.manifest)
            mutate(manifest)
            self.write(self.root / inputs.MANIFEST_PATH, manifest)
            with self.subTest(code=code):
                with self.assertRaisesRegex(inputs.FinalWorkflowInputError, "^" + code + "$"):
                    inputs.load_final_inputs(self.root)

    def test_binding_owner_snapshot_target_role_and_coverage_are_enforced(self):
        for mutate, code in (
            (lambda m: m["family_bindings"]["TOY-FAMILY-0"].update(trusted_customer_id="PRIVATE-CANARY"), "binding_snapshot_mismatch"),
            (lambda m: m["family_bindings"]["TOY-FAMILY-0"].update(snapshot_hash="0" * 64), "binding_snapshot_mismatch"),
            (lambda m: m["family_bindings"]["TOY-FAMILY-0"].update(target_transaction_id="NOT-EXISTING"), "invalid_family_binding"),
            (lambda m: m["family_bindings"].update({"TOY-FAMILY-1": deepcopy(m["family_bindings"]["TOY-FAMILY-0"])}), "duplicate_binding_target"),
            (lambda m: m["family_bindings"].pop("TOY-FAMILY-0"), "invalid_family_bindings"),
        ):
            manifest = deepcopy(self.manifest)
            mutate(manifest)
            self.write(self.root / inputs.MANIFEST_PATH, manifest)
            with self.subTest(code=code):
                with self.assertRaisesRegex(inputs.FinalWorkflowInputError, "^" + code + "$") as caught:
                    inputs.load_final_inputs(self.root)
                self.assertNotIn("PRIVATE-CANARY", str(caught.exception))
        document = deepcopy(self.document)
        for case in document["cases"][:2]:
            case["record_role"] = "withdrawal"
        self.write(self.root / inputs.CASE_PATH, document)
        body = (self.root / inputs.CASE_PATH).read_bytes()
        manifest = deepcopy(self.manifest)
        manifest.update(cases_sha256=hashlib.sha256(body).hexdigest(), cases_bytes=len(body))
        self.write(self.root / inputs.MANIFEST_PATH, manifest)
        with self.assertRaisesRegex(inputs.FinalWorkflowInputError, "^binding_role_mismatch$"):
            inputs.load_final_inputs(self.root)

    def test_duplicate_json_keys_and_oversized_artifacts_are_refused(self):
        path = self.root / inputs.MANIFEST_PATH
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(inputs.FinalWorkflowInputError, "^input_file_invalid$"):
            inputs.load_final_inputs(self.root)
        path.write_bytes(b" " * (inputs.MAX_MANIFEST_BYTES + 1))
        with self.assertRaisesRegex(inputs.FinalWorkflowInputError, "^input_file_invalid$"):
            inputs.load_final_inputs(self.root)


if __name__ == "__main__":
    unittest.main()
