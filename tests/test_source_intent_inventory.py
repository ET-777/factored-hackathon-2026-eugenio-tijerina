"""Isolated synthetic inventory tests; no organizer or evaluation data is read."""
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import inventory_source_intents as inventory


class SourceIntentInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.source = self.root / "source"
        self.project.mkdir()
        self.source.mkdir()
        self.paths = inventory.selected_partitions()
        for relative, _ in self.paths:
            self.write_rows(relative, [])

    def write_rows(self, relative, rows, *, fields=None):
        fields = list(inventory.COLUMNS) if fields is None else fields
        day = next(day for name, day in self.paths if name == relative)
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({"process_date": day, **row})
        return path

    def run_inventory(self, run="synthetic-v1"):
        return inventory.inventory(self.source, run, project_root=self.project)

    def read_inventory(self, run="synthetic-v1"):
        return json.loads((self.project / "data" / "intent_review" / run / "inventory.json").read_text(encoding="utf-8"))

    def expect_refusal(self, code, run="synthetic-v1"):
        with self.assertRaises(inventory.InventoryError) as caught:
            self.run_inventory(run)
        self.assertEqual(str(caught.exception), code)
        self.assertFalse((self.project / "data" / "intent_review" / run).exists())

    def test_normalized_groups_and_provenance_do_not_copy_semantic_labels_or_ids(self):
        fields = [*inventory.COLUMNS, "customer_id", "main_topics", "detected_intents", "agent_text", "outcome"]
        first = self.write_rows(self.paths[0][0], [
            {"customer_text": " ＨＯＬＡ\t Mundo ", "detected_language": "es", "customer_id": "SECRET-CUSTOMER-1", "main_topics": "SOURCE-LABEL-A", "agent_text": "SECRET-AGENT-ADVICE"},
            {"customer_text": "hola mundo", "detected_language": "pt", "main_topics": "SOURCE-LABEL-B"},
        ], fields=fields)
        self.write_rows(self.paths[1][0], [
            {"customer_text": "HOLA\nMUNDO", "detected_language": "es", "detected_intents": "SOURCE-INTENT-C"},
        ], fields=fields)
        summary = self.run_inventory()
        payload = self.read_inventory()
        group, = payload["groups"]
        digest = hashlib.sha256("hola mundo".encode()).hexdigest()
        self.assertEqual(group["group_id"], "SRC-" + digest)
        self.assertEqual(group["text_sha256"], digest)
        self.assertEqual(group["normalized_customer_text"], "hola mundo")
        self.assertEqual(group["representative_customer_text"], " ＨＯＬＡ\t Mundo ")
        self.assertEqual(group["subset_row_count"], 3)
        self.assertEqual(group["source_languages"], ["es", "pt"])
        self.assertEqual([ref["row_number"] for ref in group["first_occurrence_refs"]], [2, 2])
        self.assertEqual(payload["input_files"][0]["sha256"], hashlib.sha256(first.read_bytes()).hexdigest())
        self.assertEqual(payload["input_files"][0]["bytes"], first.stat().st_size)
        self.assertIsNone(group["provisional_label"])
        self.assertFalse(payload["source_labels_used"])
        self.assertFalse(payload["keyword_router_used"])
        self.assertEqual(payload["source_columns_used"], list(inventory.COLUMNS))
        serialized = json.dumps(payload)
        for forbidden in ("SECRET-CUSTOMER-1", "SOURCE-LABEL-A", "SOURCE-LABEL-B", "SOURCE-INTENT-C", "SECRET-AGENT-ADVICE"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(summary["rows_read"], 3)
        self.assertEqual(summary["distinct_text_groups"], 1)
        self.assertEqual(summary["bytes_read"], sum(item["bytes"] for item in payload["input_files"]))
        self.assertTrue(all(item["complete_file_rows_scanned"] for item in payload["input_files"]))

    def test_subset_counts_distinguish_missing_text_and_unknown_language(self):
        self.write_rows(self.paths[0][0], [
            {"customer_text": "", "detected_language": "es"},
            {"customer_text": " null ", "detected_language": ""},
            {"customer_text": "None", "detected_language": "es"},
            {"customer_text": "NaN", "detected_language": "en"},
            {"customer_text": "Pergunta", "detected_language": "UNTRUSTED-LANGUAGE-TAG"},
        ])
        summary = self.run_inventory()
        self.assertEqual(summary["rows_read"], 5)
        self.assertEqual(summary["missing_customer_text_rows"], 4)
        self.assertEqual(summary["nonblank_customer_text_rows"], 1)
        self.assertEqual(summary["other_language_rows"], 1)
        self.assertEqual(summary["missing_language_rows"], 1)
        self.assertNotIn("UNTRUSTED-LANGUAGE-TAG", json.dumps(summary))
        self.assertEqual(self.read_inventory()["groups"][0]["source_languages"], ["UNTRUSTED-LANGUAGE-TAG"])

    def test_only_generated_paths_are_read_and_input_files_stay_unchanged(self):
        unrelated = self.source / "credentials.csv"
        unrelated.write_text("FORBIDDEN-CREDENTIAL-CONTENT", encoding="utf-8")
        before = {relative: (self.source / relative).read_bytes() for relative, _ in self.paths}
        with patch.object(Path, "rglob", side_effect=AssertionError("recursive scan forbidden")):
            summary = self.run_inventory()
        self.assertEqual(summary["files_read"], 7)
        self.assertEqual([item["relative_path"] for item in self.read_inventory()["input_files"]], [name for name, _ in self.paths])
        self.assertEqual(before, {relative: (self.source / relative).read_bytes() for relative, _ in self.paths})
        self.assertNotIn("FORBIDDEN-CREDENTIAL-CONTENT", json.dumps(self.read_inventory()))

    def test_existing_run_is_refused_without_overwriting_any_artifact(self):
        self.run_inventory()
        artifact = self.project / "data" / "intent_review" / "synthetic-v1" / "inventory.json"
        before = artifact.read_bytes()
        with self.assertRaisesRegex(inventory.InventoryError, "^run_directory_exists$"):
            self.run_inventory()
        self.assertEqual(artifact.read_bytes(), before)

    def test_source_must_be_outside_project_and_run_names_are_bounded(self):
        inside = self.project / "raw"
        inside.mkdir()
        with self.assertRaisesRegex(inventory.InventoryError, "^source_must_be_outside_project$"):
            inventory.inventory(inside, "new", project_root=self.project)
        for name in ("../escape", "a/b", "", "CON", "x" * 65):
            with self.subTest(name=name):
                with self.assertRaisesRegex(inventory.InventoryError, "^invalid_run_name$"):
                    self.run_inventory(name)

    def test_malformed_csv_and_selected_values_use_safe_codes(self):
        first = self.source / self.paths[0][0]
        bad_inputs = (
            ("customer_text,customer_text,process_date\na,b,c\n", "invalid_csv_header"),
            ("customer_text,detected_language,process_date\nPRIVATE-TEXT,es\n", "malformed_csv_row"),
            ("customer_text,detected_language,process_date\n\"UNFINISHED-PRIVATE-TEXT,es,2023-06-17\n", "invalid_csv"),
            ("customer_text,detected_language,process_date\nPRIVATE-TEXT,es,not-a-date\n", "invalid_process_date"),
            ("customer_text,detected_language,process_date\nPRIVATE-TEXT,es,2023-06-18\n", "process_date_partition_mismatch"),
            ("customer_text,detected_language,process_date\nPRIVATE\x00TEXT,es,2023-06-17\n", "invalid_csv"),
        )
        for text, code in bad_inputs:
            with self.subTest(code=code):
                first.write_text(text, encoding="utf-8")
                self.expect_refusal(code)

    def test_oversized_text_metadata_and_csv_fields_are_refused(self):
        for row, code in (
            ({"customer_text": "x" * (inventory.MAX_TEXT_CHARACTERS + 1)}, "selected_field_too_large"),
            ({"customer_text": "question", "detected_language": "x" * 33}, "selected_field_too_large"),
            ({"customer_text": "x" * (inventory.MAX_CSV_FIELD_CHARACTERS + 1)}, "invalid_csv"),
        ):
            with self.subTest(code=code):
                self.write_rows(self.paths[0][0], [row])
                self.expect_refusal(code)

    def test_byte_cap_is_checked_before_reading_an_oversized_file(self):
        first = self.source / self.paths[0][0]
        first.write_bytes(b"x" * (inventory.MAX_BYTES + 1))
        with patch.object(Path, "open", side_effect=AssertionError("must not read oversized file")):
            self.expect_refusal("byte_limit_exceeded")

    def test_row_cap_is_an_explicit_partial_subset_and_reads_no_next_row(self):
        self.write_rows(self.paths[0][0], [
            {"customer_text": "Same question", "detected_language": "es"}
            for _ in range(inventory.MAX_ROWS)
        ] + [{"customer_text": "LAST-ROW-MUST-NOT-BE-PARSED", "process_date": "malformed"}])
        summary = self.run_inventory()
        payload = self.read_inventory()
        self.assertEqual(summary["rows_read"], inventory.MAX_ROWS)
        self.assertEqual(summary["files_read"], 1)
        self.assertTrue(summary["row_cap_reached"])
        self.assertFalse(payload["input_files"][0]["complete_file_rows_scanned"])
        self.assertEqual(payload["groups"][0]["subset_row_count"], inventory.MAX_ROWS)
        self.assertNotIn("LAST-ROW-MUST-NOT-BE-PARSED", json.dumps(payload))
        self.assertEqual(len(payload["requested_daily_partitions"]), 7)

    def test_distinct_group_cap_refuses_instead_of_silently_dropping_groups(self):
        self.write_rows(self.paths[0][0], [
            {"customer_text": f"Distinct synthetic question {number}"}
            for number in range(inventory.MAX_GROUPS + 1)
        ])
        self.expect_refusal("group_limit_exceeded")

    def test_runtime_cap_and_field_limit_restoration(self):
        original_limit = csv.field_size_limit()
        with patch.object(inventory.time, "monotonic", side_effect=[0, inventory.MAX_SECONDS + 1]):
            self.expect_refusal("runtime_limit_exceeded")
        self.assertEqual(csv.field_size_limit(), original_limit)

    def test_source_change_after_read_is_refused_before_publishing(self):
        real_read = inventory._read_source
        changed = False
        def changing_read(path, remaining, started):
            nonlocal changed
            result = real_read(path, remaining, started)
            if not changed:
                changed = True
                path.write_bytes(path.read_bytes() + b"\n")
            return result
        with patch.object(inventory, "_read_source", side_effect=changing_read):
            self.expect_refusal("source_file_changed")

    def test_source_symlink_escape_is_rejected(self):
        first = self.source / self.paths[0][0]
        outside = self.root / "outside.csv"
        outside.write_text("PRIVATE-OUTSIDE-CONTENT", encoding="utf-8")
        first.unlink()
        try:
            first.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not permit creating a synthetic symlink")
        self.expect_refusal("source_path_escape")

    def test_cli_errors_emit_only_fixed_safe_json(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = inventory.main(["--run-name", "new", "--unexpected", "SECRET-ARGUMENT"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(stdout.getvalue()), {"status": "refused", "error": "invalid_cli_arguments"})
        self.assertNotIn("SECRET-ARGUMENT", stdout.getvalue())
        first = self.source / self.paths[0][0]
        first.write_text("PRIVATE-HEADER\nPRIVATE-CUSTOMER-TEXT", encoding="utf-8")
        stdout = io.StringIO()
        with patch.object(inventory, "ROOT", self.project), redirect_stdout(stdout):
            result = inventory.main(["--source", str(self.source), "--run-name", "new"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(stdout.getvalue()), {"status": "refused", "error": "invalid_csv_header"})
        self.assertNotIn("PRIVATE", stdout.getvalue())
        self.assertNotIn(str(self.source), stdout.getvalue())

    def test_cli_success_emits_counts_without_source_text_or_paths(self):
        self.write_rows(self.paths[0][0], [{"customer_text": "PRIVATE-CUSTOMER-PHRASE", "detected_language": "PRIVATE-LANGUAGE"}])
        stdout = io.StringIO()
        with patch.object(inventory, "ROOT", self.project), redirect_stdout(stdout):
            result = inventory.main(["--source", str(self.source), "--run-name", "cli-v1"])
        self.assertEqual(result, 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["status"], "completed")
        self.assertEqual(output["rows_read"], 1)
        self.assertEqual(output["other_language_rows"], 1)
        self.assertNotIn("PRIVATE", stdout.getvalue())
        self.assertNotIn(str(self.source), stdout.getvalue())
        self.assertEqual(self.read_inventory("cli-v1")["groups"][0]["representative_customer_text"], "PRIVATE-CUSTOMER-PHRASE")


if __name__ == "__main__":
    unittest.main()
