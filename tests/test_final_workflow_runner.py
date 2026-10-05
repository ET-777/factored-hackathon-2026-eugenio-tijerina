"""Synthetic review-gate, exclusivity and denominator checks; no final reads."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_final_workflow as runner
from bank_service.final_workflow_scoring import CHECK_NAMES, SAFETY_CHECKS
from bank_service.routing import IntentProposal
from tests.test_final_workflow_driver import record
from tests.test_final_workflow_inputs import toy_cases


def toy_rows():
    rows = []
    for index in range(24):
        for lang in ("es", "pt"):
            for system in runner.SYSTEMS:
                service = index < 16
                label = ("inquiry", "dispute_intake", "human_request", "unsupported")[index % 4] if service else None
                passed = system == runner.SYSTEMS[1]
                rows.append({"id": f"toy-{index:02d}-{lang}", "family_id": f"toy-{index:02d}", "language": lang,
                             "stratum": "service" if service else "simulated_safety", "gold_intent": label,
                             "system": system, "expected_terminal": "answered" if service else "access_denied",
                             "proposal": {"intent": label, "confidence": .9, "matched": passed} if service else None,
                             "component_error": False, "component_seconds": .001 if service else None,
                             "workflow": {"status": "executed", "completion_pass": passed,
                                          "checks": dict.fromkeys(CHECK_NAMES, "pass"), "elapsed_seconds": .01,
                                          "persisted_handoffs": 0}})
    return rows


class FinalWorkflowRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="factored-final-runner-toy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def review_files(self):
        directory = self.root / runner.PRIVATE
        directory.mkdir(parents=True)
        names = ("cases.json", "manifest.json", "owner_review_es.md", "development_output_review_es.md", "author_notes.json")
        hashes = {}
        for name in names:
            body = b"TOY-ONLY-CONTENT"
            (directory / name).write_bytes(body)
            hashes[name] = hashlib.sha256(body).hexdigest()
        review = {"schema_version": 1, "spanish_cases_wording_labels_approved": True,
                  "spanish_development_outputs_handoff_approved": True,
                  "cases_sha256": hashes["cases.json"], "spanish_review_sha256": hashes["owner_review_es.md"],
                  "development_output_review_sha256": hashes["development_output_review_es.md"],
                  "portuguese_status": "provisional_fluent_review_pending", "owner_approval_evidence": "TOY OWNER APPROVAL"}
        (directory / "owner_review.json").write_text(json.dumps(review), encoding="utf-8")
        return directory, review

    def test_review_exact_hashes_and_true_booleans_required(self):
        directory, review = self.review_files()
        hashes = runner.review_commitments(self.root)
        self.assertIn("owner_review.json", hashes)
        for flag in (False, 1, "true"):
            altered = {**review, "spanish_cases_wording_labels_approved": flag}
            (directory / "owner_review.json").write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(runner.FinalRunError, "owner_review_pending"):
                runner.review_commitments(self.root)
        (directory / "owner_review.json").write_text(json.dumps(review), encoding="utf-8")
        (directory / "cases.json").write_text("TOY-CHANGED", encoding="utf-8")
        with self.assertRaisesRegex(runner.FinalRunError, "owner_review_commitment_changed"):
            runner.review_commitments(self.root)

    def test_missing_review_refuses_before_loading_cases_or_fitting(self):
        with patch.object(runner, "load_final_inputs") as loader, patch.object(runner, "train_router") as fit:
            with self.assertRaises(Exception):
                runner.freeze(self.root)
            loader.assert_not_called()
            fit.assert_not_called()

    def test_output_is_exclusive_and_path_names_are_bounded(self):
        folder = runner.create_directory(self.root, "toy-run")
        with self.assertRaisesRegex(runner.FinalRunError, "run_already_exists"):
            runner.create_directory(self.root, "toy-run")
        runner.write_new(folder / "claim.json", {"toy": True})
        with self.assertRaises(FileExistsError):
            runner.write_new(folder / "claim.json", {"toy": False})
        for name in ("NUL", "..", "a/b", "COM1", "", "a" * 65):
            with self.assertRaisesRegex(runner.FinalRunError, "invalid_run_name"):
                runner.create_directory(self.root, name)

    def test_all_planned_service_and_fault_attempts_remain_separate(self):
        summary = runner.summarize(toy_rows())
        candidate = summary["systems"][runner.SYSTEMS[1]]
        self.assertEqual(candidate["component"]["overall"]["attempts"], 32)
        self.assertEqual(candidate["workflow"]["overall"]["attempts"], 48)
        self.assertEqual(candidate["workflow"]["by_language"]["es"]["service"]["attempts"], 16)
        self.assertEqual(candidate["workflow"]["by_language"]["pt"]["simulated_safety"]["attempts"], 8)
        self.assertEqual(summary["paired_by_language"]["es"]["candidate_only_correct"], 16)
        self.assertFalse(summary["final_output_human_review_complete"])
        self.assertFalse(summary["default_router_changed"])

    def test_unknown_safety_and_failed_fit_cannot_pass_engineering_targets(self):
        rows = toy_rows()
        for row in rows:
            if row["system"] == runner.SYSTEMS[1]:
                row["proposal"], row["component_error"], row["component_seconds"] = None, True, None
                row["workflow"].update(completion_pass=False, status="execution_failed", elapsed_seconds=None,
                                       checks=dict.fromkeys(CHECK_NAMES, "unassessed"))
        summary = runner.summarize(rows)
        candidate = summary["systems"][runner.SYSTEMS[1]]
        self.assertEqual(candidate["component"]["overall"]["errors"], 32)
        self.assertEqual(candidate["workflow"]["overall"]["incomplete"], 48)
        self.assertEqual(candidate["workflow"]["overall"]["latency"]["missing"], 48)
        self.assertTrue(all(candidate["workflow"]["overall"]["checks"][name]["unassessed"] == 48 for name in SAFETY_CHECKS))
        self.assertFalse(summary["engineering_targets_met"])

    def test_duplicate_or_missing_pair_refused(self):
        rows = toy_rows()
        for bad in (rows[:-1], rows + [rows[0]], rows[:-1] + [deepcopy(rows[0])]):
            with self.assertRaises(runner.FinalRunError):
                runner.summarize(bad)

    def test_cli_errors_never_print_exception_content(self):
        from contextlib import redirect_stdout
        from io import StringIO
        captured = StringIO()
        with patch.object(runner, "freeze", side_effect=RuntimeError("PRIVATE-MARKER")), redirect_stdout(captured):
            self.assertEqual(runner.main(["--freeze"]), 1)
        self.assertNotIn("PRIVATE-MARKER", captured.getvalue())
        self.assertIn("final_workflow_failed", captured.getvalue())


class FinalWorkflowExecutionIntegrationTests(unittest.TestCase):
    """Exercise the runner's execution boundary with only patched toy inputs."""

    def setUp(self):
        temporary = TemporaryDirectory(prefix="factored-final-execute-toy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / runner.PRIVATE).mkdir(parents=True)
        self.cases = toy_cases()["cases"]
        records, bindings = {}, {}
        for number in range(24):
            entry = record(f"TOY-TRANSACTION-{number}", f"TOY-OWNER-{number}", "TOY-PRIVATE-MERCHANT")
            records[entry.record.transaction_id] = entry
            bindings[f"TOY-FAMILY-{number}"] = {"target_transaction_id": entry.record.transaction_id}
        self.inputs = SimpleNamespace(cases=self.cases, records=records, family_bindings=bindings)
        self.training = [{"toy_training_sentinel": True}]
        self.frozen = {"schema_version": 1, "status": "toy_frozen_for_integration_only"}

    def fake_driver(self, case, entry, records, router, **kwargs):
        self.assertIsNone(router)  # A failed candidate may never enter baseline execution.
        return {"status": "executed", "driver_error": None, "cleanup_error": None,
                "status_trace": [], "http_errors": [], "http_requests": 0,
                "steps_completed": len(case["steps"]), "cases_created": 0,
                "elapsed_seconds": .01, "private_observations": {"stored_cases": []}}

    @staticmethod
    def fake_score(case, entry, records, observation):
        good = observation["status"] == "executed"
        return {"completion_pass": good,
                "checks": dict.fromkeys(CHECK_NAMES, "pass" if good else "unassessed"),
                "scoring_error": None if good else "missing_observations"}

    @staticmethod
    def fake_component(function, text, language):
        return function(text, language), False, .001

    def patches(self):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        checked = stack.enter_context(patch.object(runner, "checked_freeze", return_value=(self.frozen, self.training, self.inputs)))
        fit = stack.enter_context(patch.object(runner, "train_router", side_effect=RuntimeError("TOY-PRIVATE-FIT-ERROR")))
        driver = stack.enter_context(patch.object(runner, "run_final_workflow", side_effect=self.fake_driver))
        scorer = stack.enter_context(patch.object(runner, "score_final_workflow", side_effect=self.fake_score))
        component = stack.enter_context(patch.object(runner, "component_attempt", side_effect=self.fake_component))
        keyword = stack.enter_context(patch.object(runner, "route_intent", return_value=IntentProposal("inquiry", 1.0, True)))
        return checked, fit, driver, scorer, component, keyword

    def test_failed_candidate_fit_preserves_all_planned_attempts_without_fallback(self):
        checked, fit, driver, scorer, component, keyword = self.patches()
        summary = runner.execute(self.root, "toy-fit-failed", "0" * 64)
        directory = self.root / ".local/final_workflow_runs/toy-fit-failed"
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        model = json.loads((directory / "model_manifest.json").read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in (directory / "outcomes.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((manifest["planned_workflow_attempts"], manifest["planned_component_attempts"]), (96, 64))
        self.assertTrue(manifest["manifest_saved_before_fit_and_prediction"])
        self.assertEqual(model, {"status": "failed", "error": "candidate_fit_failed"})
        self.assertEqual(len(rows), 96)
        self.assertEqual(len({(row["id"], row["system"]) for row in rows}), 96)
        self.assertEqual(len(list(directory.glob("private-*.json"))), 96)
        candidate = [row for row in rows if row["system"] == runner.SYSTEMS[1]]
        self.assertEqual(len(candidate), 48)
        self.assertEqual(sum(row["stratum"] == "service" for row in candidate), 32)
        self.assertTrue(all(row["workflow"]["driver_error"] == "candidate_fit_failed"
                            and not row["workflow"]["completion_pass"] for row in candidate))
        self.assertTrue(all(row["proposal"] is None and row["component_error"] is True
                            and row["component_seconds"] is None
                            for row in candidate if row["stratum"] == "service"))
        totals = summary["systems"][runner.SYSTEMS[1]]
        self.assertEqual(totals["component"]["overall"]["attempts"], 32)
        self.assertEqual(totals["component"]["overall"]["errors"], 32)
        self.assertEqual(totals["component_latency"]["missing"], 32)
        self.assertEqual(totals["workflow"]["overall"]["attempts"], 48)
        self.assertEqual(totals["workflow"]["overall"]["execution_errors"], 48)
        self.assertEqual(totals["workflow"]["overall"]["latency"]["missing"], 48)
        self.assertTrue(all(totals["workflow"]["overall"]["checks"][name]["unassessed"] == 48
                            for name in SAFETY_CHECKS))
        fit.assert_called_once_with(self.training)
        self.assertEqual(driver.call_count, 48)
        self.assertTrue(all(call.args[3] is None for call in driver.call_args_list))
        self.assertEqual(len({call.args[0]["id"] for call in driver.call_args_list}), 48)
        self.assertEqual(component.call_count, 32)
        self.assertEqual(keyword.call_count, 32)
        self.assertEqual(scorer.call_count, 96)
        self.assertEqual(checked.call_count, 2)
        for filename in ("model_manifest.json", "outcomes.jsonl", "summary.json"):
            self.assertNotIn("TOY-PRIVATE-FIT-ERROR", (directory / filename).read_text(encoding="utf-8"))

    def test_execution_claim_refuses_a_second_named_run_before_more_fit_or_execution(self):
        checked, fit, driver, scorer, component, keyword = self.patches()
        runner.execute(self.root, "toy-first", "0" * 64)
        claim = self.root / runner.PRIVATE / "execution_claim.json"
        outcomes = self.root / ".local/final_workflow_runs/toy-first/outcomes.jsonl"
        before = (claim.read_bytes(), outcomes.read_bytes())
        with self.assertRaisesRegex(runner.FinalRunError, "^benchmark_already_claimed$"):
            runner.execute(self.root, "toy-second", "0" * 64)
        self.assertEqual((claim.read_bytes(), outcomes.read_bytes()), before)
        self.assertFalse((self.root / ".local/final_workflow_runs/toy-second/outcomes.jsonl").exists())
        self.assertEqual(fit.call_count, 1)
        self.assertEqual(driver.call_count, 48)
        self.assertEqual(component.call_count, 32)
        self.assertEqual(keyword.call_count, 32)
        self.assertEqual(scorer.call_count, 96)

    def test_one_scorer_exception_retains_all_attempts_and_unassessed_failure(self):
        checked, fit, driver, scorer, component, keyword = self.patches()
        calls = [0]
        def score_once_failure(case, entry, records, observation):
            calls[0] += 1
            if calls[0] == 1:
                raise RuntimeError("TOY-PRIVATE-SCORER-ERROR")
            return self.fake_score(case, entry, records, observation)
        scorer.side_effect = score_once_failure
        summary = runner.execute(self.root, "toy-scorer-fault", "0" * 64)
        directory = self.root / ".local/final_workflow_runs/toy-scorer-fault"
        rows = [json.loads(line) for line in (directory / "outcomes.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 96)
        failed = [row for row in rows if row["workflow"]["scoring_error"] == "unexpected_scoring_failure"]
        self.assertEqual(len(failed), 1)
        self.assertFalse(failed[0]["workflow"]["completion_pass"])
        self.assertEqual(set(failed[0]["workflow"]["checks"].values()), {"unassessed"})
        self.assertEqual(summary["systems"][runner.SYSTEMS[0]]["workflow"]["overall"]["attempts"], 48)
        self.assertEqual(summary["systems"][runner.SYSTEMS[1]]["workflow"]["overall"]["attempts"], 48)
        self.assertEqual(scorer.call_count, 96)
        self.assertEqual(driver.call_count, 48)
        self.assertNotIn("TOY-PRIVATE-SCORER-ERROR", (directory / "outcomes.jsonl").read_text(encoding="utf-8"))

    def test_component_template_exception_keeps_its_error_in_planned_population(self):
        checked, fit, driver, scorer, component, keyword = self.patches()
        original_template = runner._template
        calls = [0]
        def template_once_failure(text, entry):
            calls[0] += 1
            if calls[0] == 1:
                raise RuntimeError("TOY-PRIVATE-TEMPLATE-ERROR")
            return original_template(text, entry)
        with patch.object(runner, "_template", side_effect=template_once_failure):
            summary = runner.execute(self.root, "toy-template-fault", "0" * 64)
        directory = self.root / ".local/final_workflow_runs/toy-template-fault"
        rows = [json.loads(line) for line in (directory / "outcomes.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 96)
        baseline_errors = [row for row in rows if row["system"] == runner.SYSTEMS[0] and row["component_error"]]
        self.assertEqual(len(baseline_errors), 1)
        self.assertIsNone(baseline_errors[0]["proposal"])
        self.assertIsNone(baseline_errors[0]["component_seconds"])
        self.assertEqual(summary["systems"][runner.SYSTEMS[0]]["component"]["overall"]["attempts"], 32)
        self.assertEqual(summary["systems"][runner.SYSTEMS[0]]["component"]["overall"]["errors"], 1)
        self.assertEqual(summary["systems"][runner.SYSTEMS[0]]["component_latency"]["missing"], 1)
        self.assertEqual(driver.call_count, 48)
        self.assertEqual(component.call_count, 31)
        self.assertNotIn("TOY-PRIVATE-TEMPLATE-ERROR", (directory / "outcomes.jsonl").read_text(encoding="utf-8"))

    def test_postflight_failure_preserves_claim_rows_and_sanitized_failure_marker(self):
        checked, fit, driver, scorer, component, keyword = self.patches()
        checked.side_effect = [(self.frozen, self.training, self.inputs), RuntimeError("TOY-PRIVATE-POSTFLIGHT-ERROR")]
        with self.assertRaises(RuntimeError):
            runner.execute(self.root, "toy-postflight-fault", "0" * 64)
        directory = self.root / ".local/final_workflow_runs/toy-postflight-fault"
        failure = json.loads((directory / "failure.json").read_text(encoding="utf-8"))
        self.assertEqual(failure, {
            "schema_version": 1, "status": "failed_or_interrupted_no_retry",
            "planned_workflow_attempts": 96, "observed_workflow_rows": 96,
            "error": "final_run_did_not_complete", "partial_evidence_preserved": True,
        })
        rows = (directory / "outcomes.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 96)
        self.assertTrue((self.root / runner.PRIVATE / "execution_claim.json").is_file())
        self.assertFalse((directory / "summary.json").exists())
        self.assertNotIn("TOY-PRIVATE-POSTFLIGHT-ERROR", json.dumps(failure))
        self.assertEqual(fit.call_count, 1)
        self.assertEqual(driver.call_count, 48)
        self.assertEqual(component.call_count, 32)

    def test_freeze_or_review_gate_failure_prevents_fit_driver_and_execution_claim(self):
        for code in ("freeze_hash_mismatch", "review_changed_since_freeze"):
            with self.subTest(code=code):
                with patch.object(runner, "checked_freeze", side_effect=runner.FinalRunError(code)), \
                     patch.object(runner, "train_router") as fit, \
                     patch.object(runner, "run_final_workflow") as driver, \
                     patch.object(runner, "component_attempt") as component:
                    with self.assertRaisesRegex(runner.FinalRunError, "^" + code + "$"):
                        runner.execute(self.root, "toy-gated", "0" * 64)
                    fit.assert_not_called()
                    driver.assert_not_called()
                    component.assert_not_called()
                self.assertFalse((self.root / runner.PRIVATE / "execution_claim.json").exists())
                self.assertFalse((self.root / ".local/final_workflow_runs").exists())
        with patch.object(runner, "review_commitments", side_effect=runner.FinalRunError("owner_review_pending")), \
             patch.object(runner, "load_final_inputs") as inputs, \
             patch.object(runner, "train_router") as fit, \
             patch.object(runner, "run_final_workflow") as driver:
            with self.assertRaisesRegex(runner.FinalRunError, "^owner_review_pending$"):
                runner.freeze(self.root)
            inputs.assert_not_called()
            fit.assert_not_called()
            driver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
