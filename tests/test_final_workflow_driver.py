"""Real loopback HTTP journeys on disposable synthetic records only."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
import json
import unittest
from unittest.mock import patch

from bank_service.access import Permission
from bank_service.final_workflow_driver import run_final_workflow
from bank_service.records import TransactionRecord
from bank_service.transactions import SourceReference, SourcedTransaction
from bank_service.web_app import DemoServer


NOW = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
ALL_PERMISSIONS = [permission.value for permission in Permission]


def record(identifier="SYNTH-TARGET", owner="SYNTH-OWNER", merchant="SYNTH-PRIVATE-MERCHANT"):
    return SourcedTransaction(TransactionRecord(
        identifier, owner, "SYNTH-PRODUCT", datetime(2025, 1, 2, 9, 17), date(2025, 1, 3),
        "Purchase", Decimal("21.35"), "COP", "Approved", merchant),
        (SourceReference("transactions/synthetic.csv", 7, "a" * 64),))


def case(steps, *, permissions=None, language="es", expected=None):
    return {"id": "toy-case", "family_id": "toy-family", "language": language,
            "stratum": "toy", "intent": "unsupported", "component_text": "unused",
            "record_role": "toy", "scenario": "toy", "permissions": ALL_PERMISSIONS if permissions is None else permissions,
            "steps": steps, "expected": {"deliberately_wrong": True} if expected is None else expected}


def selected_intake_steps():
    return [{"kind": "select_target"}, {"kind": "message", "text": "No hice esta compra."},
            {"kind": "respond_offer", "prepare": True}]


class FinalWorkflowDriverTests(unittest.TestCase):
    def run_case(self, steps, **options):
        target, foreign = record(), record("SYNTH-FOREIGN", "SYNTH-FOREIGN-OWNER", "SYNTH-FOREIGN-SECRET")
        configuration = case(steps, **options)
        result = run_final_workflow(configuration, target,
                                    {entry.record.transaction_id: entry for entry in (target, foreign)},
                                    foreign_entry=foreign, now=NOW)
        self.assertIsNone(result["cleanup_error"])
        private = result["private_observations"]
        self.assertNotIn('"csrf_token"', json.dumps(private))
        self.assertLessEqual(result["steps_completed"], 16)
        public = {key: value for key, value in result.items() if key != "private_observations"}
        serialized = json.dumps(public)
        for marker in ("SYNTH-TARGET", "SYNTH-OWNER", "SYNTH-PRIVATE-MERCHANT", "SYNTH-FOREIGN-SECRET", "21.35"):
            self.assertNotIn(marker, serialized)
        return result

    def test_fresh_http_lookup_without_preselection_and_gold_unused(self):
        result = self.run_case([{"kind": "message", "text": "Quiero ver el pago del {date_iso} por {amount} {currency}."}])
        self.assertEqual((result["status"], result["cases_created"], result["http_errors"]), ("executed", 0, []))
        private = result["private_observations"]
        self.assertIsNone(private["setup_states"][0]["selected_transaction"])
        self.assertIsNone(private["setup_states"][1]["selected_transaction"])
        self.assertEqual(private["final_state"]["selected_transaction"]["transaction_id"], "SYNTH-TARGET")
        self.assertIn("answered", result["status_trace"])
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertEqual(result["http_requests"], 3)

    def test_preparation_chat_assent_explicit_confirmation_and_duplicate_readback(self):
        steps = selected_intake_steps() + [{"kind": "message", "text": "Sí."},
                                          {"kind": "confirm", "confirmed": True}, {"kind": "confirm_again"}]
        result = self.run_case(steps)
        self.assertEqual((result["status"], result["cases_created"], result["http_errors"]), ("executed", 1, []))
        observations = result["private_observations"]["steps"]
        self.assertTrue(all(len(row["stored_cases"]) == 0 for row in observations[:4]))
        self.assertEqual(observations[3]["state"]["messages"][-1]["status"], "confirmation_required")
        self.assertIs(observations[2]["draft_packet"]["consent"], False)
        self.assertEqual(observations[4]["stored_cases"], observations[5]["stored_cases"])
        self.assertEqual(observations[4]["verified_readbacks"], observations[5]["verified_readbacks"])
        packet = json.loads(observations[4]["stored_cases"][0]["payload_json"])
        self.assertIs(packet["consent"], True)
        self.assertIs(packet["simulated"], True)

    def test_bare_human_request_asks_purpose_then_preserves_literal_issue(self):
        purpose = "Necesito revisar un cargo que no reconozco."
        result = self.run_case([{"kind": "message", "text": "Quiero hablar con una persona."},
                                {"kind": "message", "text": purpose}, {"kind": "confirm", "confirmed": True}])
        self.assertEqual((result["status"], result["cases_created"]), ("executed", 1))
        observations = result["private_observations"]["steps"]
        self.assertTrue(observations[0]["state"]["awaiting_handoff_context"])
        self.assertIsNone(observations[0]["draft_packet"])
        self.assertEqual(observations[1]["draft_packet"]["request"], purpose)
        self.assertIsNone(observations[1]["draft_packet"]["facts"])
        self.assertEqual(observations[2]["stored_cases"][0]["kind"], "handoff")
        self.assertIn("needs_handoff_context", result["status_trace"])

    def test_portuguese_http_intake_keeps_language_and_requires_final_confirmation(self):
        result = self.run_case([{"kind": "select_target"},
                                {"kind": "message", "text": "Eu não fiz esta compra."},
                                {"kind": "respond_offer", "prepare": True},
                                {"kind": "message", "text": "Sim."},
                                {"kind": "confirm", "confirmed": True}], language="pt")
        self.assertEqual((result["status"], result["cases_created"], result["http_errors"]), ("executed", 1, []))
        observations = result["private_observations"]["steps"]
        self.assertEqual(observations[2]["draft_packet"]["language"], "pt")
        self.assertEqual(observations[3]["stored_cases"], [])
        packet = json.loads(observations[-1]["stored_cases"][0]["payload_json"])
        self.assertEqual(packet["language"], "pt")
        self.assertEqual(packet["request"], "Eu não fiz esta compra.")

    def test_declined_preparation_and_cancelled_draft_create_no_cases(self):
        result = self.run_case(selected_intake_steps()[:2] + [{"kind": "respond_offer", "prepare": False}])
        self.assertEqual((result["status"], result["cases_created"]), ("executed", 0))
        self.assertIn("intake_declined", result["status_trace"])
        result = self.run_case(selected_intake_steps() + [{"kind": "cancel"}])
        self.assertEqual((result["status"], result["cases_created"]), ("executed", 0))
        self.assertIn("cancelled", result["status_trace"])

    def test_foreign_forged_id_and_missing_intake_permission_are_denied_over_http(self):
        result = self.run_case([{"kind": "select_foreign"}, {"kind": "select_target"},
                                {"kind": "message", "text": "No hice esta compra."}],
                               permissions=[Permission.READ_TRANSACTION.value])
        self.assertEqual((result["status"], result["cases_created"]), ("executed", 0))
        self.assertEqual(result["http_errors"], [{"status": 403, "code": "access_denied"}] * 2)
        first_state = result["private_observations"]["steps"][0]["state"]
        self.assertNotIn("SYNTH-FOREIGN-SECRET", json.dumps(first_state))
        self.assertIsNone(first_state["selected_transaction"])

    def test_actual_store_write_failure_produces_http_unknown_outcome(self):
        result = self.run_case(selected_intake_steps() + [{"kind": "set_fault", "name": "write_failure"},
                                                         {"kind": "confirm", "confirmed": True}])
        self.assertEqual((result["status"], result["cases_created"]), ("executed", 0))
        self.assertEqual(result["http_errors"], [{"status": 409, "code": "unknown_outcome"}])
        state = result["private_observations"]["final_state"]
        self.assertIs(state["error"]["outcome_unverified"], True)
        self.assertIs(state["pending_draft"]["outcome_unverified"], True)
        self.assertEqual(state["receipts"], [])
        self.assertNotIn("action_verified", result["status_trace"])

    def test_expired_session_and_unavailable_affordance_are_retained(self):
        result = self.run_case([{"kind": "advance_clock", "seconds": 1201},
                                {"kind": "message", "text": "Quiero ver el pago."}])
        self.assertEqual((result["status"], result["cases_created"]), ("executed", 0))
        self.assertFalse(result["private_observations"]["final_state"]["session"]["active"])
        self.assertEqual(result["http_errors"], [{"status": 403, "code": "access_denied"}])
        result = self.run_case([{"kind": "respond_offer", "prepare": True}])
        self.assertEqual((result["status"], result["driver_error"], result["steps_completed"]),
                         ("execution_failed", "unavailable_affordance", 0))
        self.assertEqual(result["cases_created"], 0)

    def test_invalid_templates_and_steps_do_not_start_server(self):
        target = record()
        for steps in ([{"kind": "message", "text": "{merchant}"}],
                      [{"kind": "message", "text": "{transaction_id.__class__}"}],
                      [{"kind": "advance_clock", "seconds": 0}],
                      [{"kind": "advance_clock", "seconds": 1801}],
                      [{"kind": "confirm", "confirmed": "true"}],
                      [{"kind": "cancel"}] * 17):
            with self.subTest(steps=steps), patch("bank_service.final_workflow_driver.DemoServer") as server:
                result = run_final_workflow(case(steps), target, {target.record.transaction_id: target}, now=NOW)
            self.assertEqual(result["status"], "execution_failed")
            server.assert_not_called()

    def test_foreign_fixture_with_same_owner_is_rejected_before_http_setup(self):
        target, mislabeled_foreign = record(), record("SYNTH-SECOND-OWNED")
        with patch("bank_service.final_workflow_driver.DemoServer") as server:
            result = run_final_workflow(case([{"kind": "select_foreign"}]), target,
                                        {entry.record.transaction_id: entry for entry in (target, mislabeled_foreign)},
                                        foreign_entry=mislabeled_foreign, now=NOW)
        self.assertEqual((result["status"], result["driver_error"], result["http_requests"]),
                         ("execution_failed", "invalid_driver_input", 0))
        self.assertIsNone(result["cases_created"])
        server.assert_not_called()

    def test_cleanup_failure_is_reported_after_owned_server_is_closed(self):
        target = record()
        original = DemoServer.server_close
        def close_then_fail(server):
            original(server)
            raise RuntimeError("SYNTH-PRIVATE-CLEANUP")
        with patch.object(DemoServer, "server_close", close_then_fail):
            result = run_final_workflow(case([{"kind": "select_target"}]), target,
                                        {target.record.transaction_id: target}, now=NOW)
        self.assertEqual((result["status"], result["cleanup_error"]), ("execution_failed", "server_cleanup_failed"))
        self.assertNotIn("SYNTH-PRIVATE-CLEANUP", json.dumps(result))

    def test_unexpected_handler_fault_is_retained_without_raw_stderr(self):
        class BrokenRouter:
            def route_intent(self, text, language):
                raise RuntimeError("SYNTH-PRIVATE-HANDLER-ERROR")
        target = record()
        errors = StringIO()
        with patch("sys.stderr", errors):
            result = run_final_workflow(case([{"kind": "message", "text": "Un mensaje de prueba ajeno."}]),
                                        target, {target.record.transaction_id: target}, BrokenRouter(), now=NOW)
        self.assertEqual((result["status"], result["handler_errors"], result["steps_completed"]),
                         ("execution_failed", 1, 0))
        self.assertEqual(result["cases_created"], 0)
        self.assertIsNotNone(result["driver_error"])
        self.assertEqual(errors.getvalue(), "")
        self.assertNotIn("SYNTH-PRIVATE-HANDLER-ERROR", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
