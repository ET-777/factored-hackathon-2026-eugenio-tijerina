"""Post-final engineering regressions, not another final evaluation.

All records, owners, source references and utterances below are invented toy
fixtures. No cohort, sealed cases, model artifacts or fitted router is loaded.
Declared visible selection reaches the safety branch without depending on chat
ID discovery. A fixed synthetic proposal exercises the same tool boundaries;
it is not a trained-model comparison or a Portuguese language review.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import unittest

from bank_service.access import Permission
from bank_service.final_workflow_driver import run_final_workflow
from bank_service.records import TransactionRecord
from bank_service.routing import IntentProposal
from bank_service.transactions import SourceReference, SourcedTransaction


NOW = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
ALL_PERMISSIONS = [permission.value for permission in Permission]
TARGET_ID = "SYNTH-SAFETY-TARGET"
FOREIGN_ID = "SYNTH-SAFETY-FOREIGN"
REQUESTS = {"es": "Quiero disputar esta compra.",
            "pt": "Quero contestar esta compra."}
ASSENT = {"es": "Sí.", "pt": "Sim."}


class FixedSyntheticDisputeRouter:
    """A literal test proposal only; it cannot grant permissions or consent."""

    def __init__(self):
        self.calls = []

    def route_intent(self, text, language):
        self.calls.append((text, language))
        return IntentProposal("dispute_intake", 1.0, True)


def synthetic_record(identifier, owner, merchant):
    return SourcedTransaction(TransactionRecord(
        identifier, owner, "SYNTH-PRODUCT", datetime(2025, 1, 2, 9, 17),
        date(2025, 1, 3), "Purchase", Decimal("21.35"), "MXN", "Approved", merchant),
        (SourceReference("transactions/invented_safety_fixture.csv", 7, "a" * 64),))


def intake_steps(language):
    return [{"kind": "select_target"},
            {"kind": "message", "text": REQUESTS[language]},
            {"kind": "respond_offer", "prepare": True}]


class PostFinalSafetyPathsTests(unittest.TestCase):
    def variants(self):
        for language in ("es", "pt"):
            for mode in ("keyword", "synthetic_proposal"):
                yield language, mode

    def run_path(self, steps, language, mode, *, permissions=None, routed=False):
        target = synthetic_record(TARGET_ID, "SYNTH-OWNER", "SYNTH-TARGET-MERCHANT")
        foreign = synthetic_record(FOREIGN_ID, "SYNTH-FOREIGN-OWNER", "SYNTH-FOREIGN-SECRET")
        router = None if mode == "keyword" else FixedSyntheticDisputeRouter()
        # Deliberately incompatible gold fields cannot drive the declared path.
        case = {"id": "synthetic-safety-case", "family_id": "synthetic-safety",
                "language": language, "stratum": "synthetic_engineering",
                "intent": "unsupported", "component_text": "Unused test metadata",
                "record_role": "synthetic", "scenario": "synthetic",
                "permissions": ALL_PERMISSIONS if permissions is None else permissions,
                "steps": steps, "expected": {"terminal": "intake", "writes": 99}}
        result = run_final_workflow(case, target,
                                   {TARGET_ID: target, FOREIGN_ID: foreign}, router,
                                   foreign_entry=foreign, now=NOW)
        self.assertEqual(result["status"], "executed")
        self.assertIsNone(result["driver_error"])
        self.assertIsNone(result["cleanup_error"])
        self.assertEqual(result["handler_errors"], 0)
        self.assertEqual(result["steps_completed"], len(steps))
        observed = result["private_observations"]
        self.assertTrue(all(state["selected_transaction"] is None
                            for state in observed["setup_states"]))
        self.assertTrue(all(state["pending_draft"] is None
                            for state in observed["setup_states"]))
        if routed and router is not None:
            self.assertIn((REQUESTS[language], language), router.calls)
        return result, observed["steps"], observed["final_state"]

    def assert_selected(self, row):
        self.assertEqual(row["action_payload"], {"action": "inquire", "transaction_id": TARGET_ID})
        self.assertEqual(row["http_status"], 200)
        self.assertEqual(row["state"]["selected_transaction"]["transaction_id"], TARGET_ID)
        self.assertIsNone(row["state"]["pending_draft"])

    def assert_offered(self, row):
        self.assertEqual(row["http_status"], 200)
        self.assertEqual(row["action_payload"]["action"], "message")
        self.assertEqual(row["state"]["intake_offer"]["transaction_id"], TARGET_ID)
        self.assertIsNone(row["draft_packet"])
        self.assertIsNone(row["state"]["pending_draft"])
        self.assertIn("intake_offered", [message.get("status") for message in row["new_messages"]])

    def assert_prepared(self, row, offer_row, language):
        self.assertEqual(row["http_status"], 200)
        self.assertEqual(row["action_payload"], {"action": "intake_decision",
                         "offer_id": offer_row["state"]["intake_offer"]["offer_id"], "prepare": True})
        draft = row["state"]["pending_draft"]
        self.assertEqual(draft["kind"], "intake")
        self.assertEqual(draft["draft_id"], row["draft_id"])
        self.assertEqual(row["draft_packet"]["transaction_id"], TARGET_ID)
        self.assertEqual(row["draft_packet"]["language"], language)
        self.assertEqual(row["draft_packet"]["request"], REQUESTS[language])
        self.assertIs(row["draft_packet"]["consent"], False)
        self.assertIs(row["draft_packet"]["simulated"], True)
        self.assertFalse(draft["outcome_unverified"])

    def assert_no_writes(self, result, rows):
        self.assertEqual(result["cases_created"], 0)
        self.assertNotIn("action_verified", result["status_trace"])
        for row in rows:
            self.assertEqual(row["stored_cases"], [])
            self.assertEqual(row["verified_readbacks"], [])
            self.assertEqual(row["state"]["receipts"], [])

    def test_foreign_selection_reaches_actual_owner_denial_without_disclosure(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path(
                    [{"kind": "select_foreign"}, {"kind": "select_target"}], language, mode)
                denied = rows[0]
                self.assertEqual(denied["action_payload"], {"action": "inquire", "transaction_id": FOREIGN_ID})
                self.assertEqual((denied["http_status"], denied["http_error_code"]), (403, "access_denied"))
                self.assertEqual(result["http_errors"], [{"status": 403, "code": "access_denied"}])
                self.assertIsNone(denied["state"]["selected_transaction"])
                rendered = json.dumps(denied["state"])
                for marker in (FOREIGN_ID, "SYNTH-FOREIGN-OWNER", "SYNTH-FOREIGN-SECRET"):
                    self.assertNotIn(marker, rendered)
                self.assert_selected(rows[1])
                self.assertEqual(state["selected_transaction"]["transaction_id"], TARGET_ID)
                self.assert_no_writes(result, rows)

    def test_read_only_session_reaches_actual_intake_permission_denial(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path(intake_steps(language)[:2], language, mode,
                    permissions=[Permission.READ_TRANSACTION.value], routed=True)
                self.assert_selected(rows[0])
                self.assertEqual(rows[1]["action_payload"], {"action": "message", "text": REQUESTS[language]})
                self.assertEqual((rows[1]["http_status"], rows[1]["http_error_code"]), (403, "access_denied"))
                self.assertEqual(result["http_errors"], [{"status": 403, "code": "access_denied"}])
                self.assertIsNone(state["intake_offer"])
                self.assertIsNone(state["pending_draft"])
                self.assert_no_writes(result, rows)

    def test_expired_session_reaches_actual_message_denial_after_owned_selection(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path([
                    {"kind": "select_target"}, {"kind": "advance_clock", "seconds": 1201},
                    {"kind": "message", "text": REQUESTS[language]}], language, mode)
                self.assert_selected(rows[0])
                self.assertFalse(rows[1]["state"]["session"]["active"])
                self.assertEqual(rows[2]["action_payload"], {"action": "message", "text": REQUESTS[language]})
                self.assertEqual((rows[2]["http_status"], rows[2]["http_error_code"]), (403, "access_denied"))
                self.assertEqual(result["http_errors"], [{"status": 403, "code": "access_denied"}])
                self.assertFalse(state["session"]["active"])
                self.assertEqual(state["transactions"], [])
                self.assertIsNone(state["selected_transaction"])
                self.assertIsNone(state["pending_draft"])
                self.assert_no_writes(result, rows)

    def test_declining_an_observed_offer_reaches_actual_decline_and_no_draft(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path(intake_steps(language)[:2] + [
                    {"kind": "respond_offer", "prepare": False}], language, mode, routed=True)
                self.assert_selected(rows[0])
                self.assert_offered(rows[1])
                self.assertEqual(rows[2]["action_payload"], {"action": "intake_decision",
                    "offer_id": rows[1]["state"]["intake_offer"]["offer_id"], "prepare": False})
                self.assertEqual(rows[2]["http_status"], 200)
                self.assertIn("intake_declined", result["status_trace"])
                self.assertIsNone(state["intake_offer"])
                self.assertIsNone(state["pending_draft"])
                self.assert_no_writes(result, rows)

    def test_chat_assent_reaches_confirmation_reminder_and_keeps_unwritten_draft(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path(intake_steps(language) + [
                    {"kind": "message", "text": ASSENT[language]}], language, mode, routed=True)
                self.assert_selected(rows[0])
                self.assert_offered(rows[1])
                self.assert_prepared(rows[2], rows[1], language)
                self.assertEqual(rows[3]["action_payload"], {"action": "message", "text": ASSENT[language]})
                self.assertEqual(rows[3]["http_status"], 200)
                self.assertEqual(rows[3]["state"]["messages"][-1]["status"], "confirmation_required")
                self.assertEqual(state["pending_draft"]["draft_id"], rows[2]["draft_id"])
                self.assertIs(rows[3]["draft_packet"]["consent"], False)
                self.assert_no_writes(result, rows)

    def test_cancelling_an_observed_draft_reaches_actual_cancellation(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path(intake_steps(language) + [
                    {"kind": "cancel"}], language, mode, routed=True)
                self.assert_selected(rows[0])
                self.assert_offered(rows[1])
                self.assert_prepared(rows[2], rows[1], language)
                self.assertEqual(rows[3]["action_payload"], {"action": "cancel", "draft_id": rows[2]["draft_id"]})
                self.assertEqual(rows[3]["http_status"], 200)
                self.assertIn("cancelled", result["status_trace"])
                self.assertIsNone(state["pending_draft"])
                self.assert_no_writes(result, rows)

    def test_duplicate_actual_confirmation_returns_one_identical_verified_case(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path(intake_steps(language) + [
                    {"kind": "confirm", "confirmed": True}, {"kind": "confirm_again"}],
                    language, mode, routed=True)
                self.assert_selected(rows[0])
                self.assert_offered(rows[1])
                self.assert_prepared(rows[2], rows[1], language)
                self.assertTrue(all(row["stored_cases"] == [] for row in rows[:3]))
                expected_submit = {"action": "confirm", "draft_id": rows[2]["draft_id"], "confirmed": True}
                self.assertEqual(rows[3]["action_payload"], expected_submit)
                self.assertEqual(rows[4]["action_payload"], expected_submit)
                self.assertEqual([row["http_status"] for row in rows[3:]], [200, 200])
                self.assertEqual(result["cases_created"], 1)
                self.assertEqual(len(rows[3]["stored_cases"]), 1)
                self.assertEqual(rows[3]["stored_cases"], rows[4]["stored_cases"])
                self.assertEqual(rows[3]["verified_readbacks"], rows[4]["verified_readbacks"])
                self.assertEqual(len(rows[4]["verified_readbacks"]), 1)
                stored = rows[4]["stored_cases"][0]
                receipt = rows[4]["verified_readbacks"][0]
                self.assertEqual(receipt["case_id"], stored["case_id"])
                self.assertEqual(receipt["payload_json"], stored["payload_json"])
                packet = json.loads(stored["payload_json"])
                self.assertIs(packet["consent"], True)
                self.assertIs(packet["simulated"], True)
                self.assertEqual(packet["transaction_id"], TARGET_ID)
                self.assertEqual(packet["request"], REQUESTS[language])
                self.assertEqual(len(state["receipts"]), 1)
                self.assertEqual(state["receipts"][0]["case_id"], stored["case_id"])
                self.assertIsNone(state["pending_draft"])
                self.assertIn("action_verified", result["status_trace"])
                self.assertEqual(result["http_errors"], [])

    def test_actual_failed_write_reaches_http_unknown_outcome_without_verified_success(self):
        for language, mode in self.variants():
            with self.subTest(language=language, mode=mode):
                result, rows, state = self.run_path(intake_steps(language) + [
                    {"kind": "set_fault", "name": "write_failure"},
                    {"kind": "confirm", "confirmed": True}], language, mode, routed=True)
                self.assert_selected(rows[0])
                self.assert_offered(rows[1])
                self.assert_prepared(rows[2], rows[1], language)
                self.assertEqual(rows[3]["user_step"], {"kind": "set_fault", "name": "write_failure"})
                self.assertEqual(rows[3]["http_status"], 200)
                self.assertEqual(rows[3]["draft_id"], rows[2]["draft_id"])
                self.assertEqual(rows[4]["action_payload"], {
                    "action": "confirm", "draft_id": rows[2]["draft_id"], "confirmed": True})
                self.assertEqual((rows[4]["http_status"], rows[4]["http_error_code"]), (409, "unknown_outcome"))
                self.assertEqual(result["http_errors"], [{"status": 409, "code": "unknown_outcome"}])
                self.assertIs(state["error"]["outcome_unverified"], True)
                self.assertIs(state["pending_draft"]["outcome_unverified"], True)
                self.assertEqual(state["pending_draft"]["draft_id"], rows[2]["draft_id"])
                self.assert_no_writes(result, rows)


if __name__ == "__main__":
    unittest.main()
