"""Release-boundary checks with independently authored disposable files only."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_demo.py"
_SPEC = importlib.util.spec_from_file_location("package_demo", _SCRIPT)
package_demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(package_demo)


class DemoPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        self.output = Path(self.temporary.name) / "public-package"
        for index, name in enumerate(package_demo.PACKAGE_FILES):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f"Authored safe file {index}\r\n".encode())
        self.commit = "1" * 40
        self.commit_patch = patch.object(package_demo, "_source_commit", return_value=self.commit)
        self.commit_patch.start()
        self.addCleanup(self.commit_patch.stop)

    def export(self):
        return package_demo.export_package(self.output, source_root=self.root)

    def test_literal_allowlist_byte_parity_and_manifest(self):
        manifest = self.export()
        actual = {path.relative_to(self.output).as_posix()
                  for path in self.output.rglob("*") if path.is_file()}
        self.assertEqual(actual, {*package_demo.PACKAGE_FILES, package_demo.MANIFEST_NAME})
        self.assertEqual(manifest["source_commit"], self.commit)
        for row in manifest["files"]:
            expected = (self.root / row["path"]).read_bytes()
            self.assertEqual((self.output / row["path"]).read_bytes(), expected)
            self.assertEqual(row["bytes"], len(expected))
            self.assertEqual(row["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(json.loads((self.output / package_demo.MANIFEST_NAME).read_text()), manifest)

    def test_private_source_evaluation_and_credentials_never_opened_or_exported(self):
        private_names = (
            ".env", ".git/config", "data/raw/organizer.csv", "data/final/cases.json",
            "evidence/private_result.json", "credentials.json", "materials/source.pdf",
            "bank_service/resources/final_cases.json", "bank_service/evaluation_metrics.py",
            "bank_service/final_workflow_driver.py", "bank_service/unused_runtime.py",
            "bank_service/__pycache__/web_app.pyc", "tests/private_test.py",
        )
        for name in private_names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"DO-NOT-READ-OR-PUBLISH")
        original = package_demo._source_bytes
        opened = []

        def tracked(path):
            opened.append(path.relative_to(self.root).as_posix())
            return original(path)

        with patch.object(package_demo, "_source_bytes", side_effect=tracked):
            self.export()
        self.assertEqual(opened, list(package_demo.PACKAGE_FILES))
        for name in private_names:
            self.assertFalse((self.output / name).exists(), name)

    def test_refuses_nonempty_destination_without_mutating_it(self):
        self.output.mkdir()
        existing = self.output / "owner-file.txt"
        existing.write_bytes(b"keep-owner-bytes")
        with patch.object(package_demo, "_source_bytes") as read:
            with self.assertRaisesRegex(package_demo.PackageError, "destination_not_empty"):
                self.export()
            read.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"keep-owner-bytes")
        self.assertEqual(list(self.output.iterdir()), [existing])

    def test_accepts_existing_empty_destination(self):
        self.output.mkdir()
        self.export()
        self.assertTrue((self.output / package_demo.MANIFEST_NAME).is_file())

    def test_missing_allowlisted_source_refuses_before_destination_creation(self):
        (self.root / "bank_service/hosting.py").unlink()
        with self.assertRaisesRegex(package_demo.PackageError, "source_file_unavailable"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_identical_snapshots_have_identical_manifest_bytes(self):
        self.export()
        second = self.output.with_name("second-package")
        package_demo.export_package(second, source_root=self.root)
        self.assertEqual((self.output / package_demo.MANIFEST_NAME).read_bytes(),
                         (second / package_demo.MANIFEST_NAME).read_bytes())

    def make_link(self, link, target, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("This host does not permit test symlink creation")

    def test_source_file_symlink_refused(self):
        target = self.root / "pyproject.toml"
        target.unlink()
        outside = self.root.parent / "private-file"
        outside.write_bytes(b"private-not-exported")
        self.make_link(target, outside)
        with self.assertRaisesRegex(package_demo.PackageError, "path_redirect_refused"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_source_parent_symlink_refused(self):
        real = self.root / "resources-original"
        real.mkdir()
        resources = self.root / "bank_service/resources"
        for name in ("routing_train.json", "routing_train_short_v2.json"):
            (resources / name).unlink()
            (real / name).write_bytes(b"safe-authored-fixture")
        resources.rmdir()
        self.make_link(self.root / "bank_service/resources", real, directory=True)
        with self.assertRaisesRegex(package_demo.PackageError, "path_redirect_refused"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_windows_reparse_attribute_refused_before_open(self):
        original = Path.lstat
        redirected = self.root / "bank_service/resources"

        def inspected(path):
            info = original(path)
            if path == redirected:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info

        with patch.object(Path, "lstat", autospec=True, side_effect=inspected):
            with self.assertRaisesRegex(package_demo.PackageError, "path_redirect_refused"):
                self.export()
        self.assertFalse(self.output.exists())

    def test_docker_context_exceptions_match_literal_runtime_allowlist(self):
        content = (_SCRIPT.parent.parent / ".dockerignore").read_text(encoding="utf-8")
        rules = [line.strip() for line in content.splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        expected = set(package_demo.PACKAGE_FILES) - {
            "Dockerfile", ".dockerignore", "docs/deployment.md",
        }
        self.assertEqual(rules[0], "**")
        self.assertEqual({rule for rule in rules[1:] if not rule.startswith("!")},
                         {"bank_service/**", "bank_service/web/**", "bank_service/resources/**"})
        self.assertEqual({rule[1:] for rule in rules[1:]
                          if rule.startswith("!") and not rule.endswith("/")}, expected)
        self.assertEqual({rule for rule in rules[1:]
                          if rule.startswith("!") and rule.endswith("/")},
                         {"!bank_service/", "!bank_service/web/", "!bank_service/resources/"})

    def test_docker_directory_exceptions_do_not_admit_unlisted_descendants(self):
        content = (_SCRIPT.parent.parent / ".dockerignore").read_text(encoding="utf-8")
        rules = [line.strip() for line in content.splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]

        def admitted(path):
            # These rules use only literals and recursive **. Docker applies a
            # matched parent directory rule to its descendants too: a directory
            # exception alone therefore reopens its entire subtree. This models
            # that closure instead of merely comparing exception text.
            components = [path]
            while "/" in components[-1]:
                components.append(components[-1].rsplit("/", 1)[0])
            excluded = False
            for rule in rules:
                exception = rule.startswith("!")
                pattern = (rule[1:] if exception else rule).rstrip("/")
                matches = (pattern == "**" or pattern in components
                           or (pattern.endswith("/**")
                               and any(component.startswith(pattern[:-2])
                                       for component in components)))
                if matches:
                    excluded = not exception
            return not excluded

        allowed = set(package_demo.PACKAGE_FILES) - {
            "Dockerfile", ".dockerignore", "docs/deployment.md",
        }
        for name in allowed:
            with self.subTest(allowed=name):
                self.assertTrue(admitted(name))
        denied = (
            ".env", ".git/config", "data/raw/organizer.csv", "source.pdf",
            "tests/test_private.py", "evidence/private_result.json",
            "bank_service/evaluation_metrics.py", "bank_service/final_workflow_driver.py",
            "bank_service/__pycache__/web_app.pyc", "bank_service/credentials.json",
            "bank_service/resources/final_cases.json",
            "bank_service/resources/nested/private.json",
            "bank_service/web/private-secret.txt", "bank_service/web/nested/private.json",
        )
        for name in denied:
            with self.subTest(denied=name):
                self.assertFalse(admitted(name))

    def test_destination_symlink_refused(self):
        real = self.output.with_name("owner-directory")
        real.mkdir()
        self.make_link(self.output, real, directory=True)
        with self.assertRaisesRegex(package_demo.PackageError, "path_redirect_refused"):
            self.export()
        self.assertEqual(list(real.iterdir()), [])

    def test_source_hardlink_refused(self):
        target = self.root / "pyproject.toml"
        outside = self.root.parent / "private-hardlink"
        try:
            os.link(target, outside)
        except (OSError, NotImplementedError):
            self.skipTest("This filesystem does not permit test hardlink creation")
        with self.assertRaisesRegex(package_demo.PackageError, "source_file_refused"):
            self.export()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
