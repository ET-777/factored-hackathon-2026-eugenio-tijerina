"""Cohort loading contracts exercised only with independent synthetic fixtures."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from bank_service import cohort_repository as repository
from bank_service.access import AccessDenied, Permission, TrustedSession
from bank_service.transactions import SourceReference, get_transaction


TRANSACTION_FILE = "transactions/synthetic.csv"
MONEY = "0.1000000000000000000000000001"


def source_reference(file, row_number=1, digest="a" * 64):
    return {"file": file, "row_number": row_number, "row_sha256": digest}


def cohort_fixture():
    payload = {
        "customers": [{
            "record": {"customer_id": "SYNTH-C-1", "registration_date": "2026-01-01T09:00:00"},
            "sources": [source_reference("customers.csv")],
        }],
        "products": [{
            "record": {"product_id": "SYNTH-P-1", "customer_id": "SYNTH-C-1",
                       "currency": "USD", "opening_date": "2026-02-01"},
            "sources": [source_reference("products.csv")],
        }],
        "transactions": [{
            "record": {
                "transaction_id": "SYNTH-T-1", "customer_id": "SYNTH-C-1",
                "product_id": "SYNTH-P-1", "transaction_date": "2026-06-16T12:30:45.123456",
                "process_date": "2026-06-17", "transaction_type": "Purchase",
                "amount": MONEY, "currency": "USD", "transaction_status": "Approved",
                "merchant_name": None,
            },
            "sources": [source_reference(TRANSACTION_FILE, 4), source_reference(TRANSACTION_FILE, 2)],
        }],
    }
    manifest = {
        "schema_version": 1, "selected_size": 1, "requested_size": 50,
        "process_dates": ["2026-06-17"],
        "sources": [{"file": file, "row_count": 8}
                    for file in ("customers.csv", "products.csv", TRANSACTION_FILE)],
    }
    return payload, manifest


def add_second_transaction(payload, manifest):
    second = deepcopy(payload["transactions"][0])
    second["record"]["transaction_id"] = "SYNTH-T-2"
    second["record"]["process_date"] = "2026-06-18"
    second["sources"] = [source_reference(TRANSACTION_FILE, 5, "b" * 64)]
    payload["transactions"].append(second)
    manifest["selected_size"] = 2
    manifest["process_dates"] = ["2026-06-17", "2026-06-18"]


class SourceReferenceTests(unittest.TestCase):
    def test_references_preserve_order_hashes_and_runtime_types(self):
        references = [source_reference(TRANSACTION_FILE, 4), source_reference(TRANSACTION_FILE, 2)]
        before = deepcopy(references)

        result = repository._parse_sources(
            references, source_rows={TRANSACTION_FILE: 8}, expected_file=TRANSACTION_FILE,
        )

        self.assertEqual(result, (SourceReference(TRANSACTION_FILE, 4, "a" * 64),
                                  SourceReference(TRANSACTION_FILE, 2, "a" * 64)))
        self.assertEqual(references, before)

    def test_rejects_invalid_reference_shapes_values_and_repeated_rows(self):
        good = source_reference(TRANSACTION_FILE)
        cases = [None, {}, [], [None], ["text"]]
        for field, values in (
            ("file", [None, "products.csv", "missing.csv"]),
            ("row_number", [True, 0, -1, 9, "1", 1.0]),
            ("row_sha256", [None, "a" * 63, "A" * 64, "g" * 64]),
        ):
            cases.extend([{**good, field: value}] for value in values)
        cases.append([good, {**good, "row_sha256": "b" * 64}])
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(repository.CohortLoadError):
                repository._parse_sources(
                    value, source_rows={TRANSACTION_FILE: 8, "products.csv": 8},
                    expected_file=TRANSACTION_FILE,
                )


class CohortParserTests(unittest.TestCase):
    def test_preserves_exact_facts_provenance_and_input(self):
        for timestamp in ("2026-06-16T12:30:45.123456", "2026-06-16T12:30:45.123456-05:00"):
            with self.subTest(timestamp=timestamp):
                payload, manifest = cohort_fixture()
                payload["transactions"][0]["record"]["transaction_date"] = timestamp
                before = deepcopy((payload, manifest))

                result = repository.parse_cohort(MappingProxyType(payload), MappingProxyType(manifest))

                self.assertEqual(set(result), {"SYNTH-T-1"})
                entry = result["SYNTH-T-1"]
                self.assertEqual(entry.record.amount, Decimal(MONEY))
                self.assertEqual(entry.record.transaction_date.isoformat(), timestamp)
                self.assertIsNone(entry.record.merchant_name)
                self.assertEqual(entry.sources, (
                    SourceReference(TRANSACTION_FILE, 4, "a" * 64),
                    SourceReference(TRANSACTION_FILE, 2, "a" * 64),
                ))
                self.assertEqual((payload, manifest), before)

    def test_rejects_bad_container_and_envelope_shapes(self):
        payload, manifest = cohort_fixture()
        for bad_payload, bad_manifest in ((None, manifest), ([], manifest), (payload, None), (payload, [])):
            with self.subTest(payload_type=type(bad_payload), manifest_type=type(bad_manifest)):
                with self.assertRaises(repository.CohortLoadError):
                    repository.parse_cohort(bad_payload, bad_manifest)
        for table in ("customers", "products", "transactions"):
            for value in (None, {}, [], [None], [{}], [{"record": [], "sources": []}]):
                with self.subTest(table=table, value=value):
                    changed = deepcopy(payload)
                    changed[table] = value
                    with self.assertRaises(repository.CohortLoadError):
                        repository.parse_cohort(changed, manifest)

    def test_rejects_inexact_or_inconsistent_versions_and_counts(self):
        payload, manifest = cohort_fixture()
        changes = [
            {"schema_version": value} for value in (True, 1.0, "1", 0, 2)
        ] + [
            {field: value} for field in ("selected_size", "requested_size")
            for value in (True, 1.0, "1", 0, -1, 201)
        ] + [{"selected_size": 2}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(repository.CohortLoadError):
                repository.parse_cohort(payload, {**manifest, **change})
        add_second_transaction(payload, manifest)
        manifest["requested_size"] = 1
        with self.assertRaises(repository.CohortLoadError):
            repository.parse_cohort(payload, manifest)

    def test_rejects_exports_above_local_record_limit(self):
        payload, manifest = cohort_fixture()
        template = payload["transactions"][0]
        payload["transactions"] = []
        for number in range(201):
            entry = deepcopy(template)
            entry["record"]["transaction_id"] = f"SYNTH-T-{number}"
            entry["sources"] = [source_reference(TRANSACTION_FILE, number + 1)]
            payload["transactions"].append(entry)
        manifest.update(selected_size=201, requested_size=201)
        manifest["sources"][2]["row_count"] = 201

        with self.assertRaises(repository.CohortLoadError):
            repository.parse_cohort(payload, manifest)

    def test_rejects_ambiguous_or_noncanonical_manifest_sources(self):
        payload, manifest = cohort_fixture()
        malformed = [None, {}, [], manifest["sources"][:2], manifest["sources"] + [manifest["sources"][0]],
                     [manifest["sources"][0], manifest["sources"][0], manifest["sources"][2]],
                     [None, manifest["sources"][1], manifest["sources"][2]],
                     [manifest["sources"][0], {"file": "other.csv", "row_count": 8}, manifest["sources"][2]]]
        for file in ("", "/outside.csv", "C:/outside.csv", "C:outside.csv", "part\\file.csv",
                     "../outside.csv", "./part.csv", "part/../file.csv", "part//file.csv",
                     "part/./file.csv", "part.json"):
            sources = deepcopy(manifest["sources"])
            sources[2]["file"] = file
            malformed.append(sources)
        for row_count in (True, -1, "8", 8.0):
            sources = deepcopy(manifest["sources"])
            sources[0]["row_count"] = row_count
            malformed.append(sources)
        for index, sources in enumerate(malformed):
            with self.subTest(case=index), self.assertRaises(repository.CohortLoadError):
                repository.parse_cohort(payload, {**manifest, "sources": sources})

    def test_rejects_duplicate_record_ids_even_with_distinct_source_rows(self):
        for table in ("customers", "products", "transactions"):
            with self.subTest(table=table):
                payload, manifest = cohort_fixture()
                duplicate = deepcopy(payload[table][0])
                duplicate["sources"] = [{**duplicate["sources"][0], "row_number": 7}]
                payload[table].append(duplicate)
                if table == "transactions":
                    manifest["selected_size"] = 2
                with self.assertRaises(repository.CohortLoadError):
                    repository.parse_cohort(payload, manifest)

    def test_reparses_values_and_rejects_broken_links_without_raw_error_text(self):
        marker = "SYNTHETIC_PRIVATE_VALUE"
        cases = (
            ("transactions", "amount", marker),
            ("transactions", "customer_id", marker),
            ("transactions", "product_id", marker),
            ("products", "customer_id", marker),
            ("products", "currency", "COP"),
            ("products", "opening_date", "2026-06-17"),
            ("customers", "registration_date", "2026-06-17T00:00:00"),
        )
        for table, field, value in cases:
            with self.subTest(table=table, field=field):
                payload, manifest = cohort_fixture()
                payload[table][0]["record"][field] = value
                with self.assertRaises(repository.CohortLoadError) as caught:
                    repository.parse_cohort(payload, manifest)
                self.assertNotIn(marker, str(caught.exception))

    def test_rejects_unused_dimensions(self):
        for table, key in (("customers", "customer_id"), ("products", "product_id")):
            with self.subTest(table=table):
                payload, manifest = cohort_fixture()
                unused = deepcopy(payload[table][0])
                unused["record"][key] = "SYNTH-UNUSED"
                unused["sources"][0]["row_number"] = 7
                payload[table].append(unused)
                with self.assertRaises(repository.CohortLoadError):
                    repository.parse_cohort(payload, manifest)

    def test_rejects_wrong_table_refs_and_source_rows_reused_across_records(self):
        payload, manifest = cohort_fixture()
        payload["transactions"][0]["sources"] = [source_reference("products.csv")]
        with self.assertRaises(repository.CohortLoadError):
            repository.parse_cohort(payload, manifest)
        for table in ("customers", "products", "transactions"):
            with self.subTest(reused_table=table):
                payload, manifest = cohort_fixture()
                add_second_transaction(payload, manifest)
                customer = deepcopy(payload["customers"][0])
                customer["record"]["customer_id"] = "SYNTH-C-2"
                customer["sources"][0]["row_number"] = 6
                product = deepcopy(payload["products"][0])
                product["record"].update(product_id="SYNTH-P-2", customer_id="SYNTH-C-2")
                product["sources"][0]["row_number"] = 6
                payload["customers"].append(customer)
                payload["products"].append(product)
                payload["transactions"][1]["record"].update(customer_id="SYNTH-C-2", product_id="SYNTH-P-2")
                payload[table][1]["sources"] = deepcopy(payload[table][0]["sources"])
                with self.assertRaises(repository.CohortLoadError):
                    repository.parse_cohort(payload, manifest)

    def test_process_dates_match_sorted_unique_parsed_transaction_dates(self):
        payload, manifest = cohort_fixture()
        add_second_transaction(payload, manifest)
        self.assertEqual(len(repository.parse_cohort(payload, manifest)), 2)
        for dates in (None, [], ["2026-06-17"], ["2026-06-18", "2026-06-17"],
                      ["2026-06-17", "2026-06-18", "2026-06-18"], ["2026-06-17", "2026-06-19"]):
            with self.subTest(dates=dates), self.assertRaises(repository.CohortLoadError):
                repository.parse_cohort(payload, {**manifest, "process_dates": dates})


class TemporaryRepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="factored-repository-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_run(self, name="run", omitted=None):
        run = self.root / name
        run.mkdir()
        payload, manifest = cohort_fixture()
        for filename, value in (("cohort.json", payload), ("manifest.json", manifest)):
            if filename != omitted:
                (run / filename).write_text(json.dumps(value), encoding="utf-8")
        if omitted != "quarantine.json":
            # Intentionally invalid JSON: existence is required, contents are unused.
            (run / "quarantine.json").write_bytes(b"\xffSYNTHETIC_QUARANTINE_NOT_FOR_READING")
        return run


class JsonReaderTests(TemporaryRepositoryTests):
    def test_reads_only_up_to_cap_plus_one_and_accepts_exact_cap(self):
        body = b'{"synthetic": true}'
        read_sizes = []

        class BoundedStream(io.BytesIO):
            def read(self, size=-1):
                read_sizes.append(size)
                if size != len(body) + 1:
                    raise AssertionError("Reader must request the cap plus one byte")
                return super().read(size)

        with patch.object(Path, "open", return_value=BoundedStream(body)):
            self.assertEqual(repository._read_json(self.root / "synthetic.json", max_bytes=len(body)),
                             {"synthetic": True})
        self.assertEqual(read_sizes, [len(body) + 1])
        path = self.root / "oversized.json"
        path.write_bytes(body)
        with self.assertRaises(repository.CohortLoadError):
            repository._read_json(path, max_bytes=len(body) - 1)

    def test_rejects_duplicate_json_keys_at_any_depth(self):
        for body in (b'{"key":1,"key":2}', b'{"nested":{"key":1,"key":2}}',
                     b'[{"key":1,"key":2}]'):
            with self.subTest(body=body):
                path = self.root / "duplicates.json"
                path.write_bytes(body)
                with self.assertRaises(repository.CohortLoadError):
                    repository._read_json(path, max_bytes=1024)

    def test_rejects_nonfinite_json_constants_and_overflow(self):
        for constant in ("NaN", "Infinity", "-Infinity", "1e400", "-1e400"):
            with self.subTest(constant=constant):
                path = self.root / "constant.json"
                path.write_text('{"value":' + constant + '}', encoding="utf-8")
                with self.assertRaises(repository.CohortLoadError):
                    repository._read_json(path, max_bytes=1024)

    def test_bad_json_encoding_recursion_and_io_use_safe_errors(self):
        marker = "SYNTHETIC_PRIVATE_VALUE"
        for body in (b"\xff", marker.encode(), b"[" * 5000 + b"]" * 5000):
            with self.subTest(length=len(body)):
                path = self.root / "malformed.json"
                path.write_bytes(body)
                with self.assertRaises(repository.CohortLoadError) as caught:
                    repository._read_json(path, max_bytes=20_000)
                self.assertNotIn(marker, str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
        with self.assertRaises(repository.CohortLoadError) as caught:
            repository._read_json(self.root / marker, max_bytes=1024)
        self.assertNotIn(marker, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


class CohortLoaderTests(TemporaryRepositoryTests):
    def test_loaded_repository_uses_guarded_lookup_and_preserves_every_file(self):
        run = self.write_run()
        (run / "unrelated.csv").write_bytes(b"SYNTHETIC_FILE_NOT_FOR_LOADING")
        before = {path.name: path.read_bytes() for path in run.iterdir()}
        with patch.object(repository, "_read_json", wraps=repository._read_json) as read:
            records = repository.load_private_cohort(run)
        self.assertEqual({call.args[0].name for call in read.call_args_list}, {"cohort.json", "manifest.json"})
        self.assertEqual(read.call_count, 2)
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        owner = TrustedSession("SYNTH-C-1", now + timedelta(minutes=5),
                               frozenset({Permission.READ_TRANSACTION}))
        other = TrustedSession("SYNTH-OTHER", owner.expires_at, owner.permissions)
        result = get_transaction(owner, "SYNTH-T-1", records=records, now=now)
        self.assertIs(result, records["SYNTH-T-1"])
        self.assertEqual(result.record.amount, Decimal(MONEY))
        self.assertEqual([source.row_number for source in result.sources], [4, 2])
        for session, identifier in ((other, "SYNTH-T-1"), (owner, "SYNTH-MISSING")):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                get_transaction(session, identifier, records=records, now=now)
        self.assertEqual({path.name: path.read_bytes() for path in run.iterdir()}, before)

    def test_rejects_missing_completion_files_and_nonregular_artifacts(self):
        for filename in ("manifest.json", "cohort.json", "quarantine.json"):
            for directory_instead in (False, True):
                with self.subTest(filename=filename, directory_instead=directory_instead):
                    run = self.write_run(f"missing-{filename}-{directory_instead}", omitted=filename)
                    if directory_instead:
                        (run / filename).mkdir()
                    with self.assertRaises(repository.CohortLoadError):
                        repository.load_private_cohort(run)
        with self.assertRaises(repository.CohortLoadError):
            repository.load_private_cohort(self.root / "absent")

    def test_rejects_an_artifact_resolving_outside_selected_run(self):
        run = self.write_run()
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        original_resolve = Path.resolve

        def resolve_with_escape(path, *args, **kwargs):
            if path == run / "manifest.json":
                return original_resolve(outside, *args, **kwargs)
            return original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve_with_escape):
            with patch.object(repository, "_read_json") as read:
                with self.assertRaises(repository.CohortLoadError):
                    repository.load_private_cohort(run)
                read.assert_not_called()

    def test_applies_independent_manifest_and_cohort_byte_caps(self):
        for filename, cap in (("manifest.json", repository.MAX_MANIFEST_BYTES),
                              ("cohort.json", repository.MAX_COHORT_BYTES)):
            with self.subTest(filename=filename):
                run = self.write_run(f"oversized-{filename}")
                path = run / filename
                path.write_bytes(path.read_bytes() + b" " * cap)
                with self.assertRaises(repository.CohortLoadError):
                    repository.load_private_cohort(run)


if __name__ == "__main__":
    unittest.main()
