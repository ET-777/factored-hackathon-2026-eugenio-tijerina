"""The preview loader accepts only a bounded TRAIN artifact, never a dev file."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bank_service.route_loader import load_preview_router, load_short_preview_router


def authored_payload():
    return {
        "schema_version": 1, "split": "train", "provenance": "codex_authored",
        "review_status": "draft_pending_owner_and_portuguese_review",
        "examples": [
            {"id": "TOY-" + str(index), "family_id": "TOY-FAMILY-" + str(index),
             "language": "es", "text": text, "intent": intent}
            for index, (intent, text) in enumerate((
                ("inquiry", "Detalles del apunte existente"),
                ("dispute_intake", "Este cargo no fue autorizado"),
                ("human_request", "Necesito hablar con una persona"),
                ("unsupported", "Quiero cambiar mi contrasena"),
            ))
        ],
    }


def short_payloads():
    """Synthetic balanced TRAIN schemas; never read repository training inputs."""
    original = authored_payload()
    original["examples"] = [
        {"id": f"TOY-{language}-{intent}-{index}", "family_id": f"TOY-{intent}",
         "language": language, "text": f"Synthetic {language} {intent} sample {index}",
         "intent": intent}
        for language in ("es", "pt")
        for intent in ("inquiry", "dispute_intake", "human_request", "unsupported")
        for index in range(12)
    ]
    candidate = json.loads(json.dumps(original))
    candidate["examples"] += [
        {"id": f"NEW-{language}-{intent}-{index}", "family_id": f"NEW-{intent}",
         "language": language, "text": f"New synthetic {language} {intent} utterance {index}",
         "intent": intent}
        for language in ("es", "pt")
        for intent in ("inquiry", "dispute_intake", "human_request", "unsupported")
        for index in range(6)
    ]
    return original, candidate


class PreviewLoaderTests(unittest.TestCase):
    def load(self, body):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "train.json"
            path.write_bytes(body)
            with patch("bank_service.route_loader.TRAINING_PATH", path):
                return load_preview_router()

    def test_valid_authored_train_artifact_fits_local_model(self):
        router = self.load(json.dumps(authored_payload()).encode())
        self.assertEqual(router.training_row_count, 4)
        self.assertEqual(len(router.training_hash), 64)

    def test_development_or_wrong_provenance_never_fitted(self):
        for key, value in (("split", "development"), ("provenance", "organizer_records"),
                           ("schema_version", True), ("review_status", "invented")):
            payload = authored_payload()
            payload[key] = value
            with self.subTest(key=key), patch("bank_service.route_loader.train_router") as train:
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    self.load(json.dumps(payload).encode())
                train.assert_not_called()

    def test_duplicate_keys_nonfinite_and_oversize_refused(self):
        for body in (b'{"split":"train","split":"development"}',
                     b'{"schema_version":NaN}', b"x" * (256 * 1024 + 1)):
            with self.subTest(length=len(body)):
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    self.load(body)

    def test_missing_file_error_contains_no_path(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sensitive-private-path"
            with patch("bank_service.route_loader.TRAINING_PATH", path):
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    load_preview_router()

    def test_redirected_training_path_refused_before_any_read_or_fit(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "train.json"
            alternate = Path(directory) / "unapproved.json"
            with (
                patch("bank_service.route_loader.TRAINING_PATH", path),
                patch.object(type(path), "resolve", return_value=alternate),
                patch.object(type(path), "open") as read,
                patch("bank_service.route_loader.train_router") as fit,
            ):
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    load_preview_router()
                read.assert_not_called()
                fit.assert_not_called()


class ShortPreviewLoaderTests(unittest.TestCase):
    def load(self, candidate, original=None):
        if original is None:
            original, _ = short_payloads()
        body = candidate if isinstance(candidate, bytes) else json.dumps(candidate).encode()
        with TemporaryDirectory() as directory:
            base = Path(directory) / "train.json"
            short = Path(directory) / "train-v2.json"
            base.write_text(json.dumps(original), encoding="utf-8")
            short.write_bytes(body)
            with (
                patch("bank_service.route_loader.TRAINING_PATH", base),
                patch("bank_service.route_loader.SHORT_TRAINING_PATH", short),
            ):
                return load_short_preview_router()

    def test_balanced_candidate_preserves_originals_and_fits_144_rows(self):
        original, candidate = short_payloads()
        candidate["examples"].reverse()  # Exact identities/values, not ordering, are preserved.
        router = self.load(candidate, original)
        self.assertEqual(router.training_row_count, 144)
        self.assertEqual(dict(router.language_counts), {"es": 72, "pt": 72})
        self.assertEqual(set(router.class_counts.values()), {36})

    def test_original_row_changes_or_missing_id_refused_before_fit(self):
        for key, value in (("id", "NEW-REPLACEMENT"), ("text", "changed original"),
                           ("intent", "unsupported"), ("language", "pt")):
            original, candidate = short_payloads()
            candidate["examples"][0][key] = value
            with self.subTest(key=key), patch("bank_service.route_loader.train_router") as fit:
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    self.load(candidate, original)
                fit.assert_not_called()

    def test_wrong_counts_imbalance_or_duplicate_identity_refused_before_fit(self):
        for mutation in ("original_count", "candidate_count", "balance", "duplicate"):
            original, candidate = short_payloads()
            if mutation == "original_count":
                original["examples"].pop()
            elif mutation == "candidate_count":
                candidate["examples"].pop()
            elif mutation == "balance":
                candidate["examples"][-1]["language"] = "es"
            else:
                candidate["examples"][-1] = dict(candidate["examples"][-2])
            with self.subTest(mutation=mutation), patch("bank_service.route_loader.train_router") as fit:
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    self.load(candidate, original)
                fit.assert_not_called()

    def test_candidate_metadata_duplicate_keys_nonfinite_and_oversize_refused(self):
        _, candidate = short_payloads()
        for key, value in (("split", "development"), ("schema_version", True),
                           ("provenance", "organizer_records"), ("review_status", "approved")):
            invalid = json.loads(json.dumps(candidate))
            invalid[key] = value
            with self.subTest(key=key), patch("bank_service.route_loader.train_router") as fit:
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    self.load(invalid)
                fit.assert_not_called()
        for body in (b'{"split":"train","split":"development"}',
                     b'{"schema_version":Infinity}', b"x" * (256 * 1024 + 1)):
            with self.subTest(length=len(body)), patch("bank_service.route_loader.train_router") as fit:
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    self.load(body)
                fit.assert_not_called()

    def test_malformed_candidate_row_errors_are_sanitized(self):
        for value in (None, [], {"id": []}, {"id": "NEW-INVALID", "language": []}):
            _, candidate = short_payloads()
            candidate["examples"][-1] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    self.load(candidate)
        _, candidate = short_payloads()
        candidate["examples"][-1]["text"] = []
        with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
            self.load(candidate)

    def test_redirected_base_or_candidate_refused_before_unintended_read(self):
        original, _ = short_payloads()
        with TemporaryDirectory() as directory:
            base = Path(directory) / "train.json"
            short = Path(directory) / "train-v2.json"
            alternate = Path(directory) / "unapproved.json"
            for redirected in (base, short):
                with (
                    self.subTest(redirected=redirected.name),
                    patch("bank_service.route_loader.TRAINING_PATH", base),
                    patch("bank_service.route_loader.SHORT_TRAINING_PATH", short),
                    patch.object(type(base), "resolve", autospec=True,
                                 side_effect=lambda path: alternate if path == redirected else path.absolute()),
                    patch.object(type(base), "open") as read,
                    patch("bank_service.route_loader.train_router") as fit,
                ):
                    read.return_value.__enter__.return_value.read.return_value = json.dumps(original).encode()
                    with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                        load_short_preview_router()
                    self.assertEqual(read.call_count, 0 if redirected == base else 1)
                    fit.assert_not_called()

    def test_missing_candidate_error_contains_no_path(self):
        original, _ = short_payloads()
        with TemporaryDirectory() as directory:
            base = Path(directory) / "train.json"
            base.write_text(json.dumps(original), encoding="utf-8")
            with (
                patch("bank_service.route_loader.TRAINING_PATH", base),
                patch("bank_service.route_loader.SHORT_TRAINING_PATH",
                      Path(directory) / "sensitive-private-path"),
            ):
                with self.assertRaisesRegex(ValueError, "^invalid_training_artifact$"):
                    load_short_preview_router()


if __name__ == "__main__":
    unittest.main()
