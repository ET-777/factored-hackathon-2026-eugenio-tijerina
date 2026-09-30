"""Synthetic regressions for private-cohort output boundaries and completion."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_private_cohort as builder


class PrivateCohortOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="factored-cohort-output-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "private"

    def write_run(self, run, **changes):
        payloads = {
            "cohort": {"transactions": []},
            "quarantine": [],
            "manifest": {"schema_version": 1},
            "private_root": self.private,
        }
        payloads.update(changes)
        builder.write_private_cohort(run, **payloads)

    def test_rejects_sibling_that_shares_private_root_name_prefix(self):
        sibling = self.root / "private-other" / "run"

        with self.assertRaises(builder.CohortBuildError):
            self.write_run(sibling)

        self.assertFalse(sibling.parent.exists())

    def test_rejects_private_root_itself_even_when_it_does_not_exist(self):
        with self.assertRaises(builder.CohortBuildError):
            self.write_run(self.private)

        self.assertFalse(self.private.exists())

    def test_refuses_existing_run_without_changing_its_files(self):
        run = self.private / "complete"
        self.write_run(run)
        before = {path.name: path.read_bytes() for path in run.iterdir()}

        with self.assertRaises(builder.CohortBuildError):
            self.write_run(run, cohort={"replacement": True})

        self.assertEqual({path.name: path.read_bytes() for path in run.iterdir()}, before)

    def test_manifest_serialization_failure_leaves_no_completion_marker(self):
        run = self.private / "bad-manifest"

        with self.assertRaises(builder.CohortBuildError) as caught:
            self.write_run(run, manifest={"bad": object()})

        self.assertEqual(str(caught.exception), "output_write_failed")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertFalse((run / "manifest.json").exists())
        self.assertEqual(json.loads((run / "cohort.json").read_text(encoding="utf-8")),
                         {"transactions": []})
        self.assertTrue((run / "quarantine.json").is_file())

    def test_manifest_write_failure_leaves_no_completion_marker(self):
        run = self.private / "write-failed"
        original_open = Path.open

        def fail_manifest(path, *args, **kwargs):
            if path.name == "manifest.json.tmp":
                raise OSError("SYNTHETIC_PRIVATE_FAILURE_MARKER")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_manifest):
            with self.assertRaises(builder.CohortBuildError) as caught:
                self.write_run(run)

        self.assertEqual(str(caught.exception), "output_write_failed")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertFalse((run / "manifest.json").exists())
        self.assertTrue((run / "cohort.json").is_file())
        self.assertTrue((run / "quarantine.json").is_file())

    def test_publish_failure_retains_partial_run_without_completion_marker(self):
        run = self.private / "publish-failed"

        with patch.object(Path, "rename", side_effect=OSError("SYNTHETIC_PRIVATE_FAILURE_MARKER")):
            with self.assertRaises(builder.CohortBuildError) as caught:
                self.write_run(run)

        self.assertEqual(str(caught.exception), "output_write_failed")
        self.assertFalse((run / "manifest.json").exists())
        self.assertTrue((run / "manifest.json.tmp").is_file())

    def test_success_is_deterministic_and_has_only_three_json_files(self):
        first = self.private / "first"
        second = self.private / "second"
        self.write_run(first)
        self.write_run(second)

        first_bytes = {path.name: path.read_bytes() for path in first.iterdir()}
        self.assertEqual(set(first_bytes), {"cohort.json", "quarantine.json", "manifest.json"})
        self.assertEqual(first_bytes, {path.name: path.read_bytes() for path in second.iterdir()})


if __name__ == "__main__":
    unittest.main()
