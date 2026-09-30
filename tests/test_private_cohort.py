"""Private-cohort acceptance tests using synthetic rows and temporary files only."""

import csv
import hashlib
import io
import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from bank_service.records import parse_customer, parse_product, parse_transaction
from scripts import build_private_cohort as builder


def transaction_row(identifier="DEMO-TX-A", **changes):
    return {
        "transaction_id": identifier,
        "customer_id": "DEMO-CUSTOMER-A",
        "product_id": "DEMO-PRODUCT-A",
        "transaction_date": "2026-06-16 12:30:45",
        "process_date": "2026-06-17",
        "transaction_type": "Purchase",
        "amount": "123.45",
        "currency": "USD",
        "transaction_status": "Approved",
        "merchant_name": "",
        **changes,
    }


def customer_row(identifier="DEMO-CUSTOMER-A", **changes):
    return {"customer_id": identifier, "registration_date": "2026-01-01 09:00:00", **changes}


def product_row(identifier="DEMO-PRODUCT-A", **changes):
    return {
        "product_id": identifier, "customer_id": "DEMO-CUSTOMER-A",
        "currency": "USD", "opening_date": "2026-02-01", **changes,
    }


def source_table(rows, filename):
    """In-memory source fixture for index tests; real byte hashes are tested below."""
    wrapped = []
    for number, row in enumerate(rows, 1):
        digest = hashlib.sha256(json.dumps(
            row, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        wrapped.append(builder.SourceRow(dict(row), builder.SourceRef(filename, number, digest)))
    return builder.SourceTable(filename, "a" * 64, 0, len(rows), tuple(wrapped))


def indexes(transactions, customers=None, products=None):
    if customers is None:
        customers = [customer_row()]
    if products is None:
        products = [product_row()]
    return (
        builder.index_records(source_table(transactions, "transactions.csv"),
                              key_field="transaction_id", parser=parse_transaction),
        builder.index_records(source_table(customers, "customers.csv"),
                              key_field="customer_id", parser=parse_customer),
        builder.index_records(source_table(products, "products.csv"),
                              key_field="product_id", parser=parse_product),
    )


class TemporaryCohortTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="factored-cohort-tests-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.private = self.root / "private"

    def write_bytes(self, name, body):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def write_csv(self, name, rows):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return self.write_bytes(name, stream.getvalue().encode("utf-8"))

    def read_small(self, path, **changes):
        options = {
            "source_root": self.source, "key_field": "id",
            "required_fields": frozenset({"id", "note"}), "max_rows": 10,
        }
        options.update(changes)
        return builder.read_source(path, **options)


class SourceReaderTests(TemporaryCohortTestCase):
    def test_accepts_exact_caps_and_header_only_file(self):
        body = b"id,note\nA,one\nB,two\n"
        table = self.read_small(self.write_bytes("exact.csv", body),
                                max_rows=2, max_kept_rows=2, max_bytes=len(body))
        self.assertEqual(table.row_count, 2)
        self.assertEqual(len(table.rows), 2)
        empty = self.read_small(self.write_bytes("empty.csv", b"id,note\n"))
        self.assertEqual(empty.row_count, 0)
        self.assertEqual(empty.rows, ())

    def test_rejects_noninteger_caps(self):
        path = self.write_bytes("small.csv", b"id,note\nA,one\n")
        for name in ("max_rows", "max_kept_rows", "max_bytes"):
            for cap in (True, 1.5, "10", None):
                with self.subTest(name=name, cap=cap), self.assertRaises(builder.CohortBuildError):
                    self.read_small(path, **{name: cap})

    def test_rejects_sibling_source_prefix_and_bad_extra_header(self):
        sibling = self.root / "source-other"
        sibling.mkdir()
        outside = sibling / "small.csv"
        outside.write_bytes(b"id,note\nA,one\n")
        with self.assertRaises(builder.CohortBuildError):
            self.read_small(outside)
        for body in (b"id,note, \nA,one,extra\n", b"id,note\nA,\xff\n"):
            with self.subTest(body=body), self.assertRaises(builder.CohortBuildError):
                self.read_small(self.write_bytes("bad.csv", body))

    def test_read_is_bounded_even_if_file_grows_after_stat(self):
        body = b"id,note\nA,one\n"
        path = self.write_bytes("growing.csv", body)
        sizes = []

        class TrackingStream(io.BytesIO):
            def read(self, size=-1):
                sizes.append(size)
                return super().read(size)

        # Simulate growth between stat and open without touching any real input.
        with patch.object(Path, "open", return_value=TrackingStream(body + b"x" * 1000)):
            with self.assertRaisesRegex(builder.CohortBuildError, "^file_too_large$"):
                self.read_small(path, max_bytes=len(body))
        self.assertEqual(sizes, [len(body) + 1])

    def test_source_io_error_is_fixed_and_suppresses_raw_context(self):
        path = self.write_bytes("small.csv", b"id,note\nA,one\n")
        with patch.object(Path, "open", side_effect=OSError("SYNTHETIC_PRIVATE_MARKER")):
            with self.assertRaises(builder.CohortBuildError) as caught:
                self.read_small(path)
        self.assertEqual(str(caught.exception), "source_read_failed")
        self.assertTrue(caught.exception.__suppress_context__)

    def test_hashes_parsed_bytes_and_numbers_logical_csv_rows(self):
        body = b'\xef\xbb\xbfid,note\n A ,"line one\nline two"\nB,second\n'
        path = self.write_bytes("small.csv", body)

        result = self.read_small(path)

        self.assertEqual(result.file, "small.csv")
        self.assertEqual(result.file_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(result.byte_count, len(body))
        self.assertEqual(result.row_count, 2)
        self.assertEqual([row.source.row_number for row in result.rows], [1, 2])
        self.assertEqual(result.rows[0].values, {"id": " A ", "note": "line one\nline two"})
        expected_hash = hashlib.sha256(json.dumps(
            result.rows[0].values, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        self.assertEqual(result.rows[0].source.row_sha256, expected_hash)
        self.assertEqual(path.read_bytes(), body)

    def test_key_filter_still_scans_to_eof_and_preserves_row_numbers(self):
        path = self.write_bytes("small.csv", b"id,note\n A ,first\nB,unused\nA,later\n")

        result = self.read_small(path, keep_ids=frozenset({"A"}))

        self.assertEqual(result.row_count, 3)
        self.assertEqual([row.source.row_number for row in result.rows], [1, 3])
        self.assertNotEqual(result.rows[0].source.row_sha256, result.rows[1].source.row_sha256)

    def test_empty_key_filter_keeps_no_rows_but_reports_full_source(self):
        body = b"id,note\nA,first\nB,second\n"
        path = self.write_bytes("small.csv", body)

        result = self.read_small(path, keep_ids=frozenset())

        self.assertEqual(result.rows, ())
        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.file_sha256, hashlib.sha256(body).hexdigest())

    def test_caps_abort_instead_of_returning_a_partial_source(self):
        body = b"id,note\nA,first\nA,second\nB,third\n"
        path = self.write_bytes("small.csv", body)
        for caps in ({"max_rows": 2}, {"max_bytes": len(body) - 1}, {"max_kept_rows": 1}):
            with self.subTest(caps=caps), self.assertRaises(builder.CohortBuildError):
                self.read_small(path, keep_ids=frozenset({"A"}), **caps)

    def test_rejects_bad_headers_width_and_incomplete_csv(self):
        for body in (
            b"id,id\nA,B\n", b"id,\nA,B\n", b"other,note\nA,B\n",
            b"id,note\nA,one,extra\n", b'id,note\nA,"unfinished\n',
        ):
            with self.subTest(body=body), self.assertRaises(builder.CohortBuildError):
                self.read_small(self.write_bytes("bad.csv", body))

        # Even an unneeded key must undergo structural validation before filtering.
        path = self.write_bytes("filtered.csv", b"id,note\nA,valid\nB,bad,extra\n")
        with self.assertRaises(builder.CohortBuildError):
            self.read_small(path, keep_ids=frozenset({"A"}))

    def test_rejects_a_file_outside_the_source_root(self):
        outside = self.root / "outside.csv"
        outside.write_bytes(b"id,note\nA,one\n")

        with self.assertRaises(builder.CohortBuildError):
            self.read_small(outside)


class RecordIndexTests(unittest.TestCase):
    def test_identical_invalid_keys_are_counted_and_both_quarantined(self):
        invalid = transaction_row(" ")
        result = builder.index_records(source_table([invalid, dict(invalid)], "transactions.csv"),
                                       key_field="transaction_id", parser=parse_transaction)
        self.assertEqual(result.records, {})
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual([item.reason for item in result.quarantine], ["invalid_key", "invalid_key"])

    def test_identical_duplicates_keep_one_record_and_all_references(self):
        row = transaction_row()
        source = source_table([row, dict(row)], "transactions.csv")

        result = builder.index_records(source, key_field="transaction_id", parser=parse_transaction)

        self.assertEqual(set(result.records), {"DEMO-TX-A"})
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual([ref.row_number for ref in result.records["DEMO-TX-A"].sources], [1, 2])
        self.assertEqual(result.quarantine, ())
        self.assertEqual(source.rows[0].values, row)

    def test_differing_versions_quarantine_every_occurrence_before_parsing(self):
        for second in (
            transaction_row(amount="999.00", note="original ignored field"),
            transaction_row(amount="not-a-decimal", note="original ignored field"),
            transaction_row(note="changed ignored field"),
        ):
            with self.subTest(changed_fields=list(second)):
                original = transaction_row(note="original ignored field")
                source = source_table([original, second, dict(original)], "transactions.csv")

                result = builder.index_records(source, key_field="transaction_id", parser=parse_transaction)

                self.assertEqual(result.records, {})
                self.assertEqual(result.conflicted_ids, frozenset({"DEMO-TX-A"}))
                self.assertEqual(result.duplicate_rows, 1)
                self.assertEqual(len(result.quarantine), 3)
                self.assertEqual({item.reason for item in result.quarantine}, {"conflicting_id"})

    def test_invalid_rows_use_safe_quarantine_metadata(self):
        marker = "SYNTHETIC_PRIVATE_MARKER"
        source = source_table([
            transaction_row(" "), transaction_row("DEMO-BAD", amount=marker),
        ], "transactions.csv")

        result = builder.index_records(source, key_field="transaction_id", parser=parse_transaction)

        self.assertEqual(result.records, {})
        self.assertEqual({item.reason for item in result.quarantine}, {"invalid_key", "invalid_record"})
        payload = json.dumps([asdict(item) for item in result.quarantine])
        self.assertNotIn(marker, payload)
        self.assertNotIn("DEMO-BAD", payload)


class CohortSelectionTests(unittest.TestCase):
    def test_selection_is_sorted_and_includes_only_referenced_dimensions(self):
        rows = [transaction_row("DEMO-TX-C"), transaction_row("DEMO-TX-A"), transaction_row("DEMO-TX-B")]
        for ordered in (rows, list(reversed(rows))):
            with self.subTest(first=ordered[0]["transaction_id"]):
                inputs = indexes(
                    ordered,
                    customers=[customer_row(), customer_row("DEMO-UNUSED-CUSTOMER")],
                    products=[product_row(), product_row("DEMO-UNUSED-PRODUCT")],
                )

                result = builder.select_cohort(*inputs, limit=2)

                self.assertEqual([entry.record.transaction_id for entry in result.transactions], ["DEMO-TX-A", "DEMO-TX-B"])
                self.assertEqual([entry.record.customer_id for entry in result.customers], ["DEMO-CUSTOMER-A"])
                self.assertEqual([entry.record.product_id for entry in result.products], ["DEMO-PRODUCT-A"])
                self.assertEqual(result.quarantine, ())

    def test_late_malformed_duplicate_is_excluded_before_selection_limit(self):
        inputs = indexes([
            transaction_row("DEMO-TX-A"), transaction_row("DEMO-TX-B"),
            transaction_row("DEMO-TX-A", amount="invalid"),
        ])

        result = builder.select_cohort(*inputs, limit=1)

        self.assertEqual([entry.record.transaction_id for entry in result.transactions], ["DEMO-TX-B"])
        self.assertEqual(len(result.quarantine), 2)

    def test_missing_and_conflicted_dimensions_reject_dependent_transactions(self):
        cases = (
            ([], [product_row()], "missing_customer"),
            ([customer_row()], [], "missing_product"),
            ([customer_row(), customer_row(registration_date="invalid")], [product_row()], "conflicting_customer"),
            ([customer_row()], [product_row(), product_row(opening_date="invalid")], "conflicting_product"),
        )
        for customers, products, reason in cases:
            with self.subTest(reason=reason):
                result = builder.select_cohort(*indexes([transaction_row()], customers, products), limit=1)

                self.assertEqual(result.transactions, ())
                self.assertIn(reason, {item.reason for item in result.quarantine})

        # Both missing references still reject the transaction once, customer first.
        result = builder.select_cohort(*indexes([transaction_row()], [], []), limit=1)
        self.assertEqual(len(result.quarantine), 1)
        self.assertEqual(result.quarantine[0].reason, "missing_customer")

    def test_link_validation_failures_are_quarantined(self):
        for product in (
            product_row(customer_id="DEMO-OTHER-CUSTOMER"),
            product_row(currency="COP"),
            product_row(opening_date="2026-06-17"),
        ):
            with self.subTest(product=product):
                result = builder.select_cohort(*indexes([transaction_row()], products=[product]), limit=1)

                self.assertEqual(result.transactions, ())
                self.assertEqual({item.reason for item in result.quarantine}, {"link_validation_failed"})

    def test_rejects_invalid_cohort_limits(self):
        inputs = indexes([transaction_row()])
        for limit in (0, -1, True, builder.MAX_COHORT_SIZE + 1):
            with self.subTest(limit=limit), self.assertRaises(builder.CohortBuildError):
                builder.select_cohort(*inputs, limit=limit)


class SerializationAndOutputTests(TemporaryCohortTestCase):
    def test_serializes_exact_values_and_source_references(self):
        source = builder.SourceRef("transactions.csv", 2, "b" * 64)
        money = "0.1000000000000000000000000001"
        record = parse_transaction(transaction_row(amount=money))

        result = builder.serialize_record(builder.IndexedRecord(record, (source,)))

        self.assertEqual(result["record"]["amount"], money)
        self.assertEqual(result["record"]["transaction_date"], "2026-06-16T12:30:45")
        self.assertEqual(result["record"]["process_date"], "2026-06-17")
        self.assertIsNone(result["record"]["merchant_name"])
        self.assertEqual(result["sources"], [asdict(source)])
        json.dumps(result)  # Must already be JSON-ready, without default=str.
        for parsed, field, expected in (
            (parse_customer(customer_row()), "registration_date", "2026-01-01T09:00:00"),
            (parse_product(product_row()), "opening_date", "2026-02-01"),
        ):
            with self.subTest(field=field):
                payload = builder.serialize_record(builder.IndexedRecord(parsed, (source,)))
                self.assertEqual(payload["record"][field], expected)

    def test_writes_three_json_files_into_a_fresh_private_run(self):
        run = self.private / "run-one"
        cohort = {"transactions": []}
        manifest = {"schema_version": 1}

        builder.write_private_cohort(run, cohort=cohort, quarantine=[], manifest=manifest, private_root=self.private)

        self.assertEqual({path.name for path in run.iterdir()}, {"cohort.json", "quarantine.json", "manifest.json"})
        self.assertEqual(json.loads((run / "cohort.json").read_text(encoding="utf-8")), cohort)
        self.assertEqual(json.loads((run / "quarantine.json").read_text(encoding="utf-8")), [])
        self.assertEqual(json.loads((run / "manifest.json").read_text(encoding="utf-8")), manifest)

    def test_refuses_output_escape_root_and_overwrite(self):
        existing = self.private / "existing"
        existing.mkdir(parents=True)
        sentinel = existing / "keep.txt"
        sentinel.write_text("preserve this", encoding="utf-8")
        outside = self.root / "outside"
        for target in (outside, self.private, existing):
            with self.subTest(target=target.name), self.assertRaises(builder.CohortBuildError):
                builder.write_private_cohort(target, cohort={}, quarantine=[], manifest={}, private_root=self.private)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve this")
        self.assertFalse(outside.exists())

    def test_incomplete_output_has_no_completion_manifest(self):
        for label, cohort, manifest in (
            ("bad-cohort", {"bad": object()}, {}),
            ("bad-manifest", {}, {"bad": object()}),
        ):
            with self.subTest(case=label):
                run = self.private / label
                with self.assertRaises(builder.CohortBuildError):
                    builder.write_private_cohort(run, cohort=cohort, quarantine=[], manifest=manifest, private_root=self.private)

                self.assertFalse((run / "manifest.json").exists())


class CohortBuildTests(TemporaryCohortTestCase):
    def create_source_files(self, transactions):
        self.write_csv("customers.csv", [customer_row()])
        self.write_csv("products.csv", [product_row()])
        self.write_csv("transactions/selected.csv", transactions)
        # This unrelated partition must never be discovered or read by the builder.
        self.write_bytes("transactions/unselected.csv", b"not,a,valid,transaction,header\n")

    def test_build_uses_one_partition_and_preserves_source_files(self):
        self.create_source_files([transaction_row("DEMO-TX-B"), transaction_row("DEMO-TX-A")])
        before = {path: path.read_bytes() for path in self.source.rglob("*.csv")}
        run = self.private / "one"
        with patch.object(builder, "PRIVATE_ROOT", self.private), patch.object(builder, "write_private_cohort") as write:
            counts = builder.build_private_cohort(self.source, Path("transactions/selected.csv"), run, limit=1)

        self.assertEqual(counts, {"customers": 1, "products": 1, "transactions": 1, "quarantined_rows": 0})
        write.assert_called_once()
        cohort = write.call_args.kwargs["cohort"]
        self.assertEqual([entry["record"]["transaction_id"] for entry in cohort["transactions"]], ["DEMO-TX-A"])
        manifest = write.call_args.kwargs["manifest"]
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["requested_size"], 1)
        self.assertEqual(manifest["selected_size"], 1)
        self.assertEqual(manifest["process_dates"], ["2026-06-17"])
        sources = {source["file"]: source for source in manifest["sources"]}
        self.assertEqual(set(sources), {"customers.csv", "products.csv", "transactions/selected.csv"})
        for relative, source in sources.items():
            body = before[self.source / relative]
            self.assertEqual(source["file_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(source["byte_count"], len(body))
            self.assertEqual(source["row_count"], 2 if relative.startswith("transactions/") else 1)
            self.assertEqual(source["retained_row_count"], source["row_count"])
            self.assertEqual(source["duplicate_rows"], 0)
            self.assertEqual(source["conflicted_id_count"], 0)
            self.assertEqual(source["quarantined_row_count"], 0)
            self.assertNotIn("rows", source)
        self.assertEqual(manifest["scope"], {
            "transaction_file_count": 1, "dimension_keys": "referenced_only",
            "unretained_dimension_checks": "structure_only",
            "historical_snapshot": True, "calendar_date_checks_only": True,
            "timezone_verified": False, "global_uniqueness_verified": False,
        })
        self.assertEqual(manifest["limits"]["max_total_bytes"], builder.MAX_TOTAL_BYTES)
        self.assertEqual(manifest["adapter_sha256"], hashlib.sha256((builder.ROOT / "bank_service/records.py").read_bytes()).hexdigest())
        self.assertEqual(manifest["builder_sha256"], hashlib.sha256(Path(builder.__file__).read_bytes()).hexdigest())
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_source_cap_failure_prevents_publication(self):
        self.create_source_files([transaction_row("DEMO-TX-A"), transaction_row("DEMO-TX-B")])
        for caps in ({"MAX_TRANSACTION_ROWS": 1}, {"MAX_TOTAL_BYTES": 1}):
            with self.subTest(caps=caps), \
                 patch.object(builder, "PRIVATE_ROOT", self.private), \
                 patch.multiple(builder, **caps), \
                 patch.object(builder, "write_private_cohort") as write:
                with self.assertRaises(builder.CohortBuildError):
                    builder.build_private_cohort(self.source, Path("transactions/selected.csv"), self.private / "one", limit=1)
                write.assert_not_called()

    def test_invalid_destination_or_limit_fails_before_reading(self):
        existing = self.private / "existing"
        existing.mkdir(parents=True)
        for output, limit in ((existing, 1), (self.private, 1),
                              (self.root / "private-other" / "run", 1),
                              (self.private / "new", True), (self.private / "new", 0)):
            with self.subTest(output=output.name, limit=limit), \
                 patch.object(builder, "PRIVATE_ROOT", self.private), \
                 patch.object(builder, "read_source") as read:
                with self.assertRaises(builder.CohortBuildError):
                    builder.build_private_cohort(self.source, Path("missing.csv"), output, limit=limit)
                read.assert_not_called()

    def test_actual_combined_byte_count_is_rechecked_before_output(self):
        self.create_source_files([transaction_row()])
        actual_read = builder.read_source

        def inflated_snapshot(*args, **kwargs):
            return replace(actual_read(*args, **kwargs), byte_count=builder.MAX_TOTAL_BYTES)

        with patch.object(builder, "PRIVATE_ROOT", self.private), \
             patch.object(builder, "read_source", side_effect=inflated_snapshot), \
             patch.object(builder, "write_private_cohort") as write:
            with self.assertRaisesRegex(builder.CohortBuildError, "^total_input_bytes_exceeded$"):
                builder.build_private_cohort(self.source, Path("transactions/selected.csv"),
                                             self.private / "oversize", limit=1)
            write.assert_not_called()

    def test_complete_build_is_reproducible_and_counts_quarantine_by_file(self):
        marker = "SYNTHETIC_REJECTED_PRIVATE_VALUE"
        self.write_csv("customers.csv", [
            customer_row(), customer_row("DEMO-CUSTOMER-C"),
            customer_row("DEMO-CUSTOMER-C", registration_date=marker),
            customer_row("DEMO-UNUSED", registration_date="not semantically checked"),
        ])
        self.write_csv("products.csv", [
            product_row(), product_row("DEMO-PRODUCT-C", customer_id="DEMO-CUSTOMER-C"),
            product_row("DEMO-UNUSED", opening_date="not semantically checked"),
        ])
        self.write_csv("transactions/selected.csv", [
            transaction_row("DEMO-TX-B"), transaction_row("DEMO-TX-A"),
            transaction_row("DEMO-TX-C", customer_id="DEMO-CUSTOMER-C", product_id="DEMO-PRODUCT-C"),
            transaction_row("DEMO-TX-D", amount=marker),
            transaction_row("DEMO-TX-E", product_id="DEMO-MISSING"), transaction_row("DEMO-TX-A"),
        ])
        self.write_bytes("transactions/unselected.csv", b"unrelated and invalid\n")
        before = {path: path.read_bytes() for path in self.source.rglob("*.csv")}
        runs = [self.private / "first", self.private / "second"]
        with patch.object(builder, "PRIVATE_ROOT", self.private):
            for run in runs:
                counts = builder.build_private_cohort(self.source, Path("transactions/selected.csv"), run, limit=1)
                self.assertEqual(counts, {"customers": 1, "products": 1, "transactions": 1, "quarantined_rows": 5})

        payload = {path.name: path.read_bytes() for path in runs[0].iterdir()}
        self.assertEqual(payload, {path.name: path.read_bytes() for path in runs[1].iterdir()})
        self.assertEqual(set(payload), {"cohort.json", "quarantine.json", "manifest.json"})
        self.assertNotIn(marker.encode(), b"".join(payload.values()))
        manifest = json.loads(payload["manifest.json"])
        sources = manifest["sources"]
        self.assertEqual([entry["file"] for entry in sources],
                         ["customers.csv", "products.csv", "transactions/selected.csv"])
        self.assertEqual([entry["quarantined_row_count"] for entry in sources], [2, 0, 3])
        self.assertEqual([entry["row_count"] for entry in sources], [4, 3, 6])
        self.assertEqual([entry["retained_row_count"] for entry in sources], [3, 2, 6])
        self.assertEqual(sources[2]["duplicate_rows"], 1)
        self.assertEqual(sum(entry["quarantined_row_count"] for entry in sources), counts["quarantined_rows"])
        cohort = json.loads(payload["cohort.json"])
        self.assertEqual([row["record"]["transaction_id"] for row in cohort["transactions"]], ["DEMO-TX-A"])
        self.assertEqual([ref["row_number"] for ref in cohort["transactions"][0]["sources"]], [2, 6])
        self.assertEqual({path: path.read_bytes() for path in before}, before)


if __name__ == "__main__":
    unittest.main()
