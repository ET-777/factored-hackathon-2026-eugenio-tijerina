"""The preview loader accepts only a bounded TRAIN artifact, never a dev file."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bank_service.route_loader import load_preview_router


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


if __name__ == "__main__":
    unittest.main()
