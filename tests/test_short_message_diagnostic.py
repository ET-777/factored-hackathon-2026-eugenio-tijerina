"""Disposable synthetic artifacts only; never read project workloads or final."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bank_service.evaluation_metrics import score_routes
from bank_service.routing import IntentProposal
from scripts.run_short_message_diagnostic import (
    BATCHES, CANDIDATE, CODE_FILES, DiagnosticError, LABELS, PROTOCOL, TRAIN,
    _json_artifact, component_attempt, create_run_directory, execute_run,
    load_inputs, validate_cases, validate_training,
)


def training(count=96):
    rows = [{"id": f"train-{i}", "family_id": f"train-family-{i % 4}",
             "language": "es" if (i // 4) % 2 == 0 else "pt",
             "intent": LABELS[i % 4], "text": f"synthetic training {i} {LABELS[i % 4]}"}
            for i in range(count)]
    return {"schema_version": 1, "split": "train", "provenance": "codex_authored",
            "review_status": "draft_pending_owner_and_portuguese_review", "examples": rows}


def diagnostic(batch="coverage"):
    _, count, purpose = BATCHES[batch]
    cases = [{"case_id": f"case-{language}-{label}-{i}", "language": language,
              "family": f"family-{label}-{i}", "intent": label,
              "text": f"synthetic {label} {language} {i}", "origin": "authored"}
             for language in ("es", "pt") for label in LABELS for i in range(count // 8)]
    return {"schema_version": 1, "purpose": purpose, "provenance": "codex_authored",
            "review_status": "pending_owner_spanish_and_fluent_portuguese_review",
            "notes": ["Synthetic test only."], "cases": cases,
            "state_cases": [{"case_id": "state-1", "language": "es", "family": "state",
                             "text": "synthetic state fragment", "origin": "authored",
                             "expected_behavior": "Separate conversation regression, unscored."}]}


def save_json(root, relative, document):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def make_artifacts(root, *, batch="coverage", candidate=False):
    save_json(root, BATCHES[batch][0], diagnostic(batch))
    save_json(root, TRAIN, training())
    if candidate:
        save_json(root, CANDIDATE, training(144))
    protocol = root / PROTOCOL
    protocol.parent.mkdir(parents=True, exist_ok=True)
    protocol.write_bytes(b"Synthetic frozen protocol.\n")
    for relative in CODE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# synthetic fingerprint input\n")
    return hashlib.sha256(protocol.read_bytes()).hexdigest()


class ShortMessageDiagnosticTests(unittest.TestCase):
    def test_strict_json_duplicates_nonfinite_and_bounded_read(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / TRAIN
            path.parent.mkdir(parents=True)
            for body, code in ((b'{"a":1,"a":2}', "duplicate_json_key"),
                               (b'{"a":NaN}', "nonfinite_json_value"),
                               (b'{' + b' ' * (256 * 1024), "artifact_too_large"),
                               (b'\xff', "invalid_json_artifact")):
                with self.subTest(code=code):
                    path.write_bytes(body)
                    with self.assertRaisesRegex(DiagnosticError, "^" + code + "$"):
                        _json_artifact(root, TRAIN)

    def test_redirect_rejected_before_file_open(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / TRAIN
            original_resolve = Path.resolve
            def resolve(path, *args, **kwargs):
                if path == target:
                    return root / "outside-allowlist.json"
                return original_resolve(path, *args, **kwargs)
            with patch.object(Path, "resolve", resolve), patch.object(Path, "open") as opened:
                with self.assertRaisesRegex(DiagnosticError, "^input_path_redirected$"):
                    _json_artifact(root, TRAIN)
                opened.assert_not_called()

    def test_strict_schema_balance_identity_and_text_guards(self):
        original = diagnostic()
        mutations = [lambda d: d.update(schema_version=True),
                     lambda d: d.update(extra="unaccepted"),
                     lambda d: d["cases"][0].update(text="x" * 1001),
                     lambda d: d["cases"][0].update(case_id="../private"),
                     lambda d: d["cases"][0].update(language="en"),
                     lambda d: d["cases"][0].update(intent="unsupported"),
                     lambda d: d["state_cases"][0].update(case_id=d["cases"][0]["case_id"]),
                     lambda d: d["cases"][1].update(text=d["cases"][0]["text"].upper())]
        for mutate in mutations:
            value = deepcopy(original)
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(DiagnosticError):
                validate_cases(value, count=48, purpose=BATCHES["coverage"][2])
        cases, state_count = validate_cases(original, count=48, purpose=BATCHES["coverage"][2])
        self.assertEqual((len(cases), state_count), (48, 1))

    def test_candidate_original_preservation_and_train_diagnostic_overlap(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            make_artifacts(root, candidate=True)
            cases, rows, hashes, state_count = load_inputs(root, batch="coverage", include_candidate=True)
            self.assertEqual((len(cases), len(rows["learned_v1"]), len(rows["learned_short_v2"])),
                             (48, 96, 144))
            self.assertEqual(len(hashes), 3)
            candidate = training(144)
            candidate["examples"][0]["text"] = "altered original synthetic row"
            save_json(root, CANDIDATE, candidate)
            with self.assertRaisesRegex(DiagnosticError, "^candidate_changed_original_training$"):
                load_inputs(root, batch="coverage", include_candidate=True)
            original = training()
            original["examples"][0]["text"] = diagnostic()["cases"][0]["text"].upper()
            save_json(root, TRAIN, original)
            with self.assertRaisesRegex(DiagnosticError, "^diagnostic_training_overlap$"):
                load_inputs(root, batch="coverage", include_candidate=False)

    def test_training_duplicate_nonfinite_shape_and_class_coverage_rejected(self):
        for mutate in (lambda d: d["examples"][1].update(id=d["examples"][0]["id"]),
                       lambda d: d["examples"][1].update(text=d["examples"][0]["text"]),
                       lambda d: d["examples"][0].update(text="\ud800"),
                       lambda d: d.update(review_status="approved-without-evidence")):
            data = training()
            mutate(data)
            with self.assertRaises(DiagnosticError):
                validate_training(data, expected_count=96)

    def test_single_calls_errors_and_abstentions_stay_in_denominator(self):
        calls = []
        def failure(text, language):
            calls.append((text, language))
            raise RuntimeError("PRIVATE-SYNTHETIC-ERROR")
        proposal, code = component_attempt(failure, "synthetic", "es")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(proposal)
        self.assertEqual(code, "component_execution_failed")
        rows = [{"gold_intent": "inquiry", "language": "es", "family_id": "f",
                 "prediction": proposal, "error": True}]
        for invalid in (None, IntentProposal("inquiry", float("nan"), True),
                        IntentProposal("inquiry", True, True), IntentProposal([], 0.5, True),
                        IntentProposal("inquiry", 0.2, False)):
            prediction, code = component_attempt(lambda *_: invalid, "synthetic", "pt")
            rows.append({"gold_intent": "inquiry", "language": "pt", "family_id": "f",
                         "prediction": prediction, "error": code is not None})
        rows.append({"gold_intent": "unsupported", "language": "es", "family_id": "f2",
                     "prediction": IntentProposal("unsupported", 0.0, False)})
        overall = score_routes(rows)["overall"]
        self.assertEqual((overall["attempts"], overall["correct"], overall["errors"],
                          overall["abstentions"]), (7, 0, 6, 7))

    def test_exclusive_output_and_reserved_names(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = create_run_directory(root, "toy-1")
            self.assertEqual(path, root / ".local/short_message_runs/toy-1")
            with self.assertRaisesRegex(DiagnosticError, "^output_exists_or_redirected$"):
                create_run_directory(root, "toy-1")
            for name in ("", "..", "../secret", "a/b", "NUL", "COM1", "ñ", "a" * 65):
                with self.subTest(name=name), self.assertRaises(DiagnosticError):
                    create_run_directory(root, name)

    def test_frozen_manifest_precedes_fit_and_one_call_per_case_system(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            protocol_hash = make_artifacts(root, candidate=True)
            run_dir = root / ".local/short_message_runs/toy"
            calls, fits = [], []
            def predict(text, language):
                self.assertTrue((run_dir / "manifest.json").exists())
                calls.append((text, language))
                return IntentProposal(text.split()[1], 0.7, True)
            def fit(rows):
                self.assertTrue((run_dir / "manifest.json").exists())
                fits.append(len(rows))
                return SimpleNamespace(route_intent=predict, training_row_count=len(rows),
                                       training_hash="a" * 64, vocabulary_size=5)
            with patch("scripts.run_short_message_diagnostic.train_router", side_effect=fit), \
                    patch("scripts.run_short_message_diagnostic.route_intent", side_effect=predict):
                result = execute_run(root, run_name="toy", protocol_sha256=protocol_hash, include_candidate=True)
            self.assertEqual((fits, len(calls), result["attempts"], result["errors"]), ([96, 144], 144, 144, 0))
            manifest = json.loads((run_dir / "manifest.json").read_text())
            self.assertTrue(manifest["manifest_saved_before_fit_and_prediction"])
            self.assertEqual(manifest["state_cases_not_scored_as_intents"], 1)
            self.assertEqual(set(manifest["code_sha256"]), set(CODE_FILES))
            summary = json.loads((run_dir / "summary.json").read_text())
            self.assertFalse(summary["workflow_performance_assessed"])
            self.assertEqual(summary["systems"]["learned_v1"]["by_language"]["pt"]["attempts"], 24)
            serialized = (run_dir / "outcomes.jsonl").read_text()
            self.assertNotIn("synthetic", serialized)
            self.assertNotIn('"text"', serialized)

    def test_fit_failure_retains_all_learned_attempts_and_sanitizes_error(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            protocol_hash = make_artifacts(root, batch="followup")
            with patch("scripts.run_short_message_diagnostic.train_router", side_effect=ValueError("PRIVATE-ERROR")), \
                    patch("scripts.run_short_message_diagnostic.route_intent", return_value=IntentProposal("inquiry", 1, True)):
                result = execute_run(root, run_name="failed-fit", protocol_sha256=protocol_hash, batch="followup")
            self.assertEqual((result["status"], result["attempts"], result["errors"]),
                             ("completed_with_errors", 64, 32))
            run_dir = root / ".local/short_message_runs/failed-fit"
            summary = json.loads((run_dir / "summary.json").read_text())
            metrics = summary["systems"]["learned_v1"]["overall"]
            self.assertEqual((metrics["attempts"], metrics["errors"], metrics["abstentions"]), (32, 32, 32))
            for name in ("models.json", "outcomes.jsonl", "status.json", "summary.json"):
                self.assertNotIn("PRIVATE-ERROR", (run_dir / name).read_text())

    def test_protocol_failure_saved_without_predictions_or_overwrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            make_artifacts(root)
            with patch("scripts.run_short_message_diagnostic.train_router") as fit:
                with self.assertRaisesRegex(DiagnosticError, "^protocol_hash_mismatch$"):
                    execute_run(root, run_name="protocol-fail", protocol_sha256="0" * 64)
                fit.assert_not_called()
            run_dir = root / ".local/short_message_runs/protocol-fail"
            failure = json.loads((run_dir / "failure.json").read_text())
            self.assertTrue(failure["partial_artifacts_preserved"])
            self.assertFalse((run_dir / "outcomes.jsonl").exists())
            with self.assertRaisesRegex(DiagnosticError, "^output_exists_or_redirected$"):
                execute_run(root, run_name="protocol-fail", protocol_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
