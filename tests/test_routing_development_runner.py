"""Synthetic harness/aggregation tests; no authored workload or source inputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bank_service.routing import IntentProposal
from scripts.run_routing_development import (
    DevelopmentRunError, SYSTEMS, component_attempt, create_run_directory, summarize_results,
    workflow_attempt,
)
from bank_service.development_driver import WorkflowDriverError


def outcome(identity, language, system, proposal, *, complete=True, available=True):
    return {"example_id": identity, "family_id": "family-" + language,
            "language": language, "gold_intent": "inquiry", "system": system,
            "binding_available": available, "proposal": proposal, "component_error": False,
            "component_seconds": 0.002,
            "workflow": {"completion_pass": complete,
                         "checks": {"no_write_before_confirmation": True,
                                    "channel_limit_explicit": None},
                         "status": "completed" if available else "unavailable_binding",
                         "elapsed_ms": 5 if available else None}}


class DevelopmentRunnerTests(unittest.TestCase):
    def rows(self):
        rows = []
        for language in ("es", "pt"):
            for system in SYSTEMS:
                proposal = {"intent": "inquiry", "confidence": 1.0,
                            "matched": system == SYSTEMS[1]}
                rows.append(outcome(language + "-1", language, system, proposal,
                                    complete=system == SYSTEMS[1],
                                    available=system == SYSTEMS[1]))
        return rows

    def test_paired_abstentions_and_unavailable_attempts_retained(self):
        result = summarize_results(self.rows())
        baseline = result["systems"][SYSTEMS[0]]
        self.assertEqual(baseline["component"]["overall"]["attempts"], 2)
        self.assertEqual(baseline["component"]["overall"]["abstentions"], 2)
        self.assertEqual(baseline["workflow"]["overall"]["incomplete"], 2)
        self.assertEqual(baseline["workflow"]["overall"]["unavailable_bindings"], 2)
        self.assertEqual(baseline["workflow"]["overall"]["latency"]["missing"], 2)
        self.assertEqual(result["paired_by_language"]["es"]["learned_only_correct"], 1)
        self.assertEqual(result["paired_by_language"]["es"]["macro_f1_delta"], 0.25)
        checks = baseline["workflow"]["overall"]["checks"]
        self.assertEqual(checks["channel_limit_explicit"]["applicable"], 0)
        self.assertIsNone(checks["channel_limit_explicit"]["rate"])

    def test_duplicate_or_missing_pair_refused(self):
        with self.assertRaisesRegex(DevelopmentRunError, "^duplicate_result_attempt$"):
            summarize_results(self.rows() + [self.rows()[0]])
        with self.assertRaisesRegex(DevelopmentRunError, "^unpaired_result_population$"):
            summarize_results(self.rows()[:-1])

    def test_component_exception_and_malformed_proposal_count_as_error(self):
        def fail(text, language):
            raise ValueError("PRIVATE-MUST-NOT-LEAVE-CALL")
        proposal, error, seconds = component_attempt(fail, "synthetic", "es")
        self.assertIsNone(proposal)
        self.assertTrue(error)
        self.assertGreaterEqual(seconds, 0)
        for malformed in (None, IntentProposal("inquiry", float("nan"), True),
                          IntentProposal("inquiry", True, True), IntentProposal("fake", 1, True)):
            proposal, error, seconds = component_attempt(lambda *_: malformed, "synthetic", "pt")
            self.assertIsNone(proposal)
            self.assertTrue(error)

    def test_exclusive_run_directory_and_invalid_names(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = create_run_directory(root, "synthetic-1")
            self.assertEqual(path, root / ".local/evaluation_runs/synthetic-1")
            with self.assertRaisesRegex(DevelopmentRunError, "^output_exists_or_redirected$"):
                create_run_directory(root, "synthetic-1")
            for name in ("..", "../private", "a/b", "NUL", "COM1", "", "a" * 65):
                with self.subTest(name=name):
                    with self.assertRaises(DevelopmentRunError):
                        create_run_directory(root, name)

    def test_setup_cleanup_faults_remain_failed_attempts_without_private_exception(self):
        for error in (WorkflowDriverError("driver_setup_failed"), WorkflowDriverError("driver_cleanup_failed"),
                      RuntimeError("SYNTHETIC-PRIVATE-EXCEPTION")):
            with self.subTest(error_type=type(error).__name__):
                with patch("scripts.run_routing_development.run_workflow", side_effect=error):
                    result = workflow_attempt({}, None, {}, None, workdir=Path("synthetic"), now=None)
                self.assertEqual(result["status"], "execution_failed")
                self.assertFalse(result["completion_pass"])
                self.assertIsNone(result["elapsed_ms"])
                self.assertIsNone(result["cases_created"])
                self.assertNotIn("PRIVATE", str(result))
                rows = self.rows()
                rows[1]["workflow"] = result
                summary = summarize_results(rows)
                self.assertEqual(summary["systems"][SYSTEMS[1]]["workflow"]["overall"]["attempts"], 2)
                self.assertEqual(summary["systems"][SYSTEMS[1]]["workflow"]["overall"]["execution_errors"], 1)
                checks = summary["systems"][SYSTEMS[1]]["workflow"]["overall"]["checks"]
                self.assertEqual(checks["no_write_before_confirmation"]["unassessed"], 1)
                self.assertEqual(checks["channel_limit_explicit"]["not_applicable"], 1)
                self.assertEqual(checks["channel_limit_explicit"]["unassessed"], 1)


if __name__ == "__main__":
    unittest.main()
