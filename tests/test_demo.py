"""Exercise the user-facing local demonstration against a real temporary DB."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from bank_service.case_store import CaseStore
from bank_service.demo import run_demo


class DemoTests(unittest.TestCase):
    def test_cli_preserves_portuguese_accents_when_output_is_piped(self):
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "bank_service", "demo", "--language", "pt", "--scenario", "inquiry"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, check=True,
        )
        output = completed.stdout.decode("utf-8")
        self.assertIn("DEMONSTRAÇÃO LOCAL", output)
        self.assertIn('Transação: "DEMO-TX-001"', output)
        self.assertNotIn("\ufffd", output)

    def test_complete_demo_both_languages_and_storage_survives_reopening(self):
        for language in ("es", "pt"):
            with self.subTest(language=language), TemporaryDirectory() as directory:
                output = []
                path = Path(directory) / "cases.sqlite3"
                result = run_demo(language=language, db_path=path, emit=output.append)
                self.assertEqual(result.new_cases, 2)
                self.assertTrue(result.duplicate_reused)
                self.assertEqual(result.access_denials, 2)
                store = CaseStore(path)
                try:
                    self.assertEqual(store.count(), 2)
                finally:
                    store.close()
                joined = "\n".join(output)
                self.assertIn("[ambiguous]", joined)
                self.assertIn("[answered]", joined)
                self.assertIn("[confirmation_required]", joined)
                self.assertIn("[action_verified]", joined)
                self.assertNotIn("Demo Foreign Merchant", joined)
                packets = [json.loads(line) for line in output if line.startswith("{")]
                self.assertEqual(len(packets), 1)

    def test_inquiry_demo_does_not_write_cases(self):
        result = run_demo(scenario="inquiry", emit=lambda text: None)
        self.assertEqual(result.new_cases, 0)
        self.assertFalse(result.duplicate_reused)

    def test_invalid_options_fail_before_creating_storage(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "not_created.sqlite3"
            for options in ({"language": "en"}, {"scenario": "bad"}):
                with self.assertRaisesRegex(ValueError, "^invalid_demo_option$"):
                    run_demo(db_path=path, **options)
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
