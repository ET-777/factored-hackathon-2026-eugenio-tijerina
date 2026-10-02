"""Synthetic CLI checks: private startup is explicit and fails without fallback."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from bank_service.__main__ import main
from bank_service.access import Permission
from bank_service.cohort_repository import CohortLoadError
from bank_service.demo_fixtures import DEMO_CUSTOMER, demo_records


class PrivateWebCliTests(unittest.TestCase):
    def invoke(self, args, *, failure=None):
        output, errors = StringIO(), StringIO()
        with (
            patch("sys.argv", ["bank_service", "web", *args]),
            patch("bank_service.web_app.serve") as serve,
            patch("bank_service.cohort_repository.load_private_cohort",
                  return_value=demo_records(), side_effect=failure) as load,
            redirect_stdout(output), redirect_stderr(errors),
        ):
            code = 0
            try:
                main()
            except SystemExit as exc:
                code = exc.code
        return serve, load, code, output.getvalue(), errors.getvalue()

    def cohort_args(self):
        # This path is never opened: the synthetic loader is patched above.
        return ["--cohort-run", "private-example", "--customer-id", DEMO_CUSTOMER]

    def test_default_demo_never_loads_a_cohort(self):
        serve, load, code, _, errors = self.invoke([])
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        serve.assert_called_once_with(8765)
        load.assert_not_called()

    def test_private_mode_loads_once_and_defaults_to_read_only(self):
        serve, load, code, _, errors = self.invoke(self.cohort_args() + ["--port", "8766"])
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        load.assert_called_once_with(Path("private-example"))
        self.assertEqual(serve.call_args.args, (8766,))
        config = serve.call_args.kwargs["config"]
        self.assertEqual(config.customer_id, DEMO_CUSTOMER)
        self.assertEqual(config.permissions, frozenset({Permission.READ_TRANSACTION}))

    def test_simulated_action_grants_must_be_explicit(self):
        arguments = self.cohort_args()
        for permission in Permission:
            arguments += ["--permission", permission.value]
        serve, _, code, _, _ = self.invoke(arguments)
        self.assertEqual(code, 0)
        self.assertEqual(serve.call_args.kwargs["config"].permissions, frozenset(Permission))

    def test_private_options_without_cohort_do_not_start_demo(self):
        for arguments in (["--customer-id", DEMO_CUSTOMER],
                          ["--permission", Permission.READ_TRANSACTION.value]):
            with self.subTest(arguments=arguments):
                serve, load, code, _, _ = self.invoke(arguments)
                self.assertEqual(code, 2)
                serve.assert_not_called()
                load.assert_not_called()

    def test_missing_or_blank_identity_refused_before_loading(self):
        for arguments in (["--cohort-run", "private-example"],
                          ["--cohort-run", "private-example", "--customer-id", "  "]):
            with self.subTest(arguments=arguments):
                serve, load, code, _, _ = self.invoke(arguments)
                self.assertEqual(code, 2)
                serve.assert_not_called()
                load.assert_not_called()

    def test_load_failure_is_sanitized_without_demo_fallback(self):
        serve, load, code, output, errors = self.invoke(
            self.cohort_args(), failure=CohortLoadError("sensitive-private-example"))
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertEqual(errors, "Private cohort startup refused.\n")
        load.assert_called_once()
        serve.assert_not_called()

    def test_unknown_customer_refused_without_echoing_identity(self):
        serve, _, code, output, errors = self.invoke(
            ["--cohort-run", "private-example", "--customer-id", "PRIVATE-UNKNOWN-CUSTOMER"])
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertEqual(errors, "Private cohort startup refused.\n")
        serve.assert_not_called()

    def test_permission_set_without_read_is_refused(self):
        serve, _, code, _, errors = self.invoke(
            self.cohort_args() + ["--permission", Permission.CREATE_SIMULATED_INTAKE.value])
        self.assertEqual(code, 1)
        self.assertEqual(errors, "Private cohort startup refused.\n")
        serve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
