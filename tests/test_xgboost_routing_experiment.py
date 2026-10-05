"""Disposable toy artifacts and stub fits only; never read project workloads."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bank_service.routing import IntentProposal
from scripts import run_xgboost_routing_experiment as experiment


def toy_artifacts():
    original, additions, clusters = [], [], []
    # Each authored family has eight original or four short rows. These synthetic
    # clusters reproduce the declared metadata shape without project wording.
    specifications = {
        "dispute_intake": [(0, ["o0", "s0"]), (1, ["o1", "s1"]), (2, ["o2"]), (2, ["s2"])],
        "human_request": [(0, ["o0", "s0", "s1", "s2"]), (1, ["o1"]), (2, ["o2"])],
        "inquiry": [(0, ["o0"]), (1, ["o1", "s0", "s1", "s2"]), (2, ["o2"])],
        "unsupported": [(0, ["o0"]), (1, ["o1"]), (2, ["o2", "s0"]), (2, ["s1"]), (2, ["s2"])],
    }
    for label, groups in specifications.items():
        for group_index, (fold, members) in enumerate(groups):
            cluster_id = f"toy-cluster-{label}-{group_index}"
            cluster_families, count = [], 0
            for member in members:
                family = f"toy-family-{label}-{member}"
                cluster_families.append(family)
                size = 8 if member.startswith("o") else 4
                count += size
                for language in ("es", "pt"):
                    for index in range(size // 2):
                        row = {"id": f"toy-{label}-{member}-{language}-{index}", "family_id": family,
                               "language": language, "intent": label,
                               "text": f"SYNTHETIC-SECRET {label} {language} {member} {index}"}
                        (original if member.startswith("o") else additions).append(row)
            clusters.append({"id": cluster_id, "intent": label, "fold": fold,
                             "rows": count, "families": cluster_families})
    def document(rows):
        return {"schema_version": 1, "split": "train", "provenance": "codex_authored",
                "review_status": "draft_pending_owner_and_portuguese_review", "examples": rows}
    grouping = {"schema_version": 1, "purpose": "train_only_grouped_cross_validation",
                "source": experiment.CANDIDATE, "reviewer": "Synthetic reviewer",
                "grouping_notes": ["Synthetic metadata-only test."], "clusters": clusters}
    return document(original), document(original + additions), grouping


def save_json(root, relative, document):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def make_files(root):
    original, candidate, grouping = toy_artifacts()
    save_json(root, experiment.TRAIN, original)
    save_json(root, experiment.CANDIDATE, candidate)
    save_json(root, experiment.GROUPING, grouping)
    protocol = root / experiment.PROTOCOL
    protocol.parent.mkdir(parents=True, exist_ok=True)
    protocol.write_bytes(b"Frozen synthetic protocol.\n")
    for relative in experiment.CODE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# synthetic fingerprint input\n")
    return hashlib.sha256(protocol.read_bytes()).hexdigest()


def stub_model(rows, predictor=None):
    return SimpleNamespace(
        route_intent=predictor or (lambda text, language: IntentProposal(text.split()[1], 0.8, True)),
        training_row_count=len(rows), training_hash="a" * 64, vocabulary_size=7)


class XgboostRoutingExperimentTests(unittest.TestCase):
    def test_input_preservation_and_fixed_population_guards_without_fitting(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            make_files(root)
            with patch.object(experiment, "train_router") as nb, patch.object(experiment, "train_xgboost_router") as linear:
                rows, hashes = experiment.load_inputs(root)
            self.assertEqual((len(rows), set(hashes)), (144, {experiment.TRAIN, experiment.CANDIDATE}))
            nb.assert_not_called()
            linear.assert_not_called()
            _, candidate, _ = toy_artifacts()
            candidate["examples"][0]["text"] = "changed synthetic original"
            save_json(root, experiment.CANDIDATE, candidate)
            with self.assertRaisesRegex(experiment.ExperimentError, "^candidate_changed_original_training$"):
                experiment.load_inputs(root)

    def test_strict_training_metadata_and_grouping_errors_are_refused(self):
        _, candidate, grouping = toy_artifacts()
        rows = candidate["examples"]
        family_map, mapping, audit = experiment.assign_folds(rows, grouping)
        self.assertEqual((len(family_map), len(mapping)), (24, 15))
        self.assertEqual([fold["held_out_rows"] for fold in audit], [48, 48, 48])
        self.assertTrue(all(fold["held_out_language_counts"] == {"es": 24, "pt": 24} for fold in audit))
        self.assertEqual(experiment.assign_folds(list(reversed(rows)), grouping), (family_map, mapping, audit))
        mutations = [lambda d: d.update(schema_version=True),
                     lambda d: d.update(source="evaluation/final_private/hidden.json"),
                     lambda d: d["clusters"][0].update(rows=11),
                     lambda d: d["clusters"][0].update(fold=True),
                     lambda d: d["clusters"][0].update(id="../bad"),
                     lambda d: d["clusters"][0].update(intent="unsupported"),
                     lambda d: d["clusters"][0]["families"].append(d["clusters"][1]["families"][0]),
                     lambda d: d["clusters"][0]["families"].append("not-in-train"),
                     lambda d: d["clusters"].pop(),
                     lambda d: d["clusters"][0].update(fold=2)]
        for mutate in mutations:
            malformed = deepcopy(grouping)
            mutate(malformed)
            with self.subTest(mutation=mutate), self.assertRaises(experiment.ExperimentError):
                experiment.assign_folds(rows, malformed)

    def test_run_names_and_output_are_exclusive(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            directory = experiment.create_run_directory(root, "toy-1")
            self.assertEqual(directory, root / ".local/xgboost_routing_runs/toy-1")
            with self.assertRaisesRegex(experiment.ExperimentError, "^output_exists_or_redirected$"):
                experiment.create_run_directory(root, "toy-1")
            for name in ("", "..", "../outside", "a/b", "NUL", "COM1", "ñ", "a" * 65):
                with self.subTest(name=name), self.assertRaises(experiment.ExperimentError):
                    experiment.create_run_directory(root, name)

    def test_manifest_before_each_fit_features_use_only_partition_and_single_predictions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            protocol_hash = make_files(root)
            run_directory = root / ".local/xgboost_routing_runs/toy"
            fits, predictions = [], []
            def predict(text, language):
                self.assertTrue((run_directory / "manifest.json").exists())
                predictions.append((text, language))
                return IntentProposal(text.split()[1], 0.8, True)
            def fit(rows, max_depth=None):
                manifest = json.loads((run_directory / "manifest.json").read_text())
                seen_folds = {manifest["row_fold_mapping"][row["id"]] for row in rows}
                self.assertEqual((len(rows), len(seen_folds)), (96, 2))
                absent = ({0, 1, 2} - seen_folds).pop()
                all_families = manifest["family_cluster_mapping"]
                self.assertTrue(all(manifest["cluster_fold_mapping"][all_families[row["family_id"]]] != absent
                                    for row in rows))
                fits.append((absent, max_depth))
                return stub_model(rows, predict)
            with patch.object(experiment, "train_router", side_effect=fit), \
                    patch.object(experiment, "train_xgboost_router", side_effect=fit), \
                    patch.object(experiment, "package_versions", return_value={name: "toy" for name in experiment.PACKAGE_NAMES}):
                result = experiment.execute_run(root, run_name="toy", protocol_sha256=protocol_hash)
            self.assertEqual((result["attempts"], result["fits"], result["errors"], len(predictions)), (432, 9, 0, 432))
            self.assertEqual(fits, [(fold, c) for fold in range(3) for c in (None, 1, 2)])
            manifest = json.loads((run_directory / "manifest.json").read_text())
            self.assertTrue(manifest["manifest_saved_before_fit_and_prediction"])
            self.assertEqual(set(manifest["code_sha256"]), set(experiment.CODE_FILES))
            self.assertEqual(len(manifest["grouping_sha256"]), 64)
            summary = json.loads((run_directory / "summary.json").read_text())
            self.assertEqual(summary["selection"]["max_depth"], 1)
            self.assertFalse(summary["selection"]["consideration_passed"])
            for system in experiment.SYSTEMS:
                metrics = summary["systems"][system]
                self.assertEqual(metrics["pooled_out_of_fold"]["overall"]["attempts"], 144)
                self.assertEqual(metrics["pooled_out_of_fold"]["by_language"]["pt"]["attempts"], 72)
                self.assertEqual(metrics["semantic_group_scores"]["overall"]["family_exact_all_correct"]["families"], 15)
                self.assertEqual(metrics["fit_latency"]["attempts"], 3)
                self.assertEqual(metrics["prediction_latency"]["attempts"], 144)
                self.assertEqual(metrics["unsupported_recall"], {"overall": 1.0, "by_language": {"es": 1.0, "pt": 1.0}})
            outcomes = [json.loads(line) for line in (run_directory / "outcomes.jsonl").read_text().splitlines()]
            self.assertEqual(len({(row["system"], row["id"]) for row in outcomes}), 432)
            for path in run_directory.iterdir():
                self.assertNotIn("SYNTHETIC-SECRET", path.read_text())
                self.assertNotIn('"text"', path.read_text())

    def test_all_fit_failures_and_malformed_predictions_remain_attempts(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            protocol_hash = make_files(root)
            def fit(rows, max_depth):
                if max_depth == 2:
                    raise RuntimeError("SYNTHETIC-SECRET-ERROR")
                return stub_model(rows)
            with patch.object(experiment, "train_router", side_effect=lambda rows: stub_model(
                    rows, lambda *_: IntentProposal("inquiry", True, True))), \
                    patch.object(experiment, "train_xgboost_router", side_effect=fit), \
                    patch.object(experiment, "package_versions", return_value={name: "toy" for name in experiment.PACKAGE_NAMES}):
                result = experiment.execute_run(root, run_name="failures", protocol_sha256=protocol_hash)
            self.assertEqual((result["attempts"], result["errors"], result["status"]), (432, 288, "completed_with_errors"))
            run_directory = root / ".local/xgboost_routing_runs/failures"
            summary = json.loads((run_directory / "summary.json").read_text())
            self.assertFalse(summary["selection"]["consideration_criteria"]["reference_zero_errors"])
            self.assertFalse(summary["selection"]["consideration_passed"])
            for system in ("learned_short_v2", "xgboost_depth_2"):
                metric = summary["systems"][system]["pooled_out_of_fold"]["overall"]
                self.assertEqual((metric["attempts"], metric["errors"], metric["abstentions"]), (144, 144, 144))
            self.assertEqual(summary["systems"]["xgboost_depth_2"]["prediction_latency"]["missing"], 144)
            for path in run_directory.iterdir():
                self.assertNotIn("SYNTHETIC-SECRET", path.read_text())

    def test_protocol_or_dependency_failure_preserved_without_any_fit(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            protocol_hash = make_files(root)
            with patch.object(experiment, "train_router") as nb, patch.object(experiment, "train_xgboost_router") as linear:
                with self.assertRaisesRegex(experiment.ExperimentError, "^protocol_hash_mismatch$"):
                    experiment.execute_run(root, run_name="bad-hash", protocol_sha256="0" * 64)
                with patch.object(experiment, "package_versions", return_value={name: None for name in experiment.PACKAGE_NAMES}):
                    with self.assertRaisesRegex(experiment.ExperimentError, "^model_packages_missing$"):
                        experiment.execute_run(root, run_name="missing-dependency", protocol_sha256=protocol_hash)
            nb.assert_not_called()
            linear.assert_not_called()
            bad = root / ".local/xgboost_routing_runs/bad-hash"
            self.assertTrue((bad / "failure.json").exists())
            self.assertFalse((bad / "manifest.json").exists())
            missing = root / ".local/xgboost_routing_runs/missing-dependency"
            self.assertTrue((missing / "manifest.json").exists())
            self.assertTrue((missing / "failure.json").exists())
            self.assertFalse((missing / "outcomes.jsonl").exists())

    def test_single_inference_no_retries_sanitized_and_unmatched_not_correct(self):
        calls = []
        def broken(*args):
            calls.append(args)
            raise RuntimeError("SYNTHETIC-SECRET")
        proposal, code, seconds = experiment.component_attempt(broken, "synthetic", "es")
        self.assertEqual((proposal, code, len(calls)), (None, "component_execution_failed", 1))
        self.assertGreaterEqual(seconds, 0)
        proposal, code, _ = experiment.component_attempt(lambda *_: IntentProposal("unsupported", 0.0, False), "toy", "pt")
        outcome = {"prediction": proposal.intent, "confidence": proposal.confidence, "matched": proposal.matched,
                   "gold_intent": "unsupported", "language": "pt", "family_id": "toy", "cluster_id": "toy",
                   "error_code": code}
        self.assertFalse(experiment._correct(outcome))


if __name__ == "__main__":
    unittest.main()
