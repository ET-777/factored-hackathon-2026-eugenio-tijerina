"""Synthetic driver/oracle checks; no authored workload or private source reads."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bank_service.actions import ActionService
from bank_service.case_store import CaseStore, StoreError
from bank_service.development_driver import WorkflowDriverError, run_workflow
from bank_service.records import TransactionRecord
from bank_service.routing import IntentProposal
from bank_service.transactions import SourceReference, SourcedTransaction
from bank_service.web_app import BrowserSession


NOW = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
MARKER = "SYNTHETIC-PRIVATE-VALUE"


def record(identifier="SYNTH-T-1", *, kind="Purchase", status="Approved", day=2):
    return SourcedTransaction(TransactionRecord(
        identifier, MARKER + "-OWNER", MARKER + "-PRODUCT",
        datetime(2025, 1, day, 9, 17, 12), date(2025, 1, 4), kind,
        Decimal("12.3000000000000001"), "COP", status, MARKER + "-MERCHANT",
    ), (SourceReference("transactions/synthetic.csv", 7, "a" * 64),))


class FixedRouter:
    def __init__(self, intent):
        self.intent = intent
        self.calls = []

    def route_intent(self, text, language):
        self.calls.append((text, language))
        return IntentProposal(self.intent, 0.9, True)


class DevelopmentDriverTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="factored-driver-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runs = 0

    def run_case(self, intent, text, *, routed=None, entry=None, language="es", records=None,
                 family="synthetic-family"):
        entry = record() if entry is None else entry
        records = {entry.record.transaction_id: entry} if records is None else records
        example = {"intent": intent, "text": text, "language": language, "family_id": family}
        router = FixedRouter(routed or intent)
        self.runs += 1
        directory = self.root / f"case-{self.runs}"
        directory.mkdir()
        result = run_workflow(example, entry, records, router, workdir=directory, now=NOW)
        self.assertEqual(list(directory.iterdir()), [])
        self.assertLessEqual(result["scored_actions"], 8)
        encoded = json.dumps(result)
        for forbidden in (MARKER, text, entry.record.transaction_id, "transactions/synthetic.csv",
                          "12.3000000000000001", "draft_", "sim_", "payload_json"):
            self.assertNotIn(forbidden, encoded)
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        return result, router

    def test_spanish_and_portuguese_inquiry_grounding_uses_new_answer_only(self):
        for language, text in (("es", "Revisa esta transacción para mí."),
                               ("pt", "Mostre esta transação para mim.")):
            with self.subTest(language=language):
                result, router = self.run_case("inquiry", text, language=language)
                self.assertTrue(result["completion_pass"])
                self.assertTrue(result["checks"]["answer_grounded"])
                self.assertEqual(result["status_trace"], ["answered"])
                self.assertEqual(result["scored_actions"], 1)
                self.assertEqual(result["cases_created"], 0)
                self.assertIsNone(result["checks"]["channel_limit_explicit"])
                self.assertIsNone(result["checks"]["single_case"])
                self.assertIsNone(result["checks"]["readback_verified"])
                self.assertIsNone(result["checks"]["safe_eligibility_block"])
                self.assertTrue(result["checks"]["language_preserved"])
                self.assertEqual(router.calls, [(text, language)])

    def test_channel_oracle_rejects_a_deliberately_omitted_limit(self):
        # A synthetic presentation fault isolates the oracle after the real UI
        # acquired request-specific limit explanations. No benchmark rerun.
        with patch("bank_service.web_app.with_requested_record_limits", side_effect=lambda answer, request: answer):
            result, _ = self.run_case("inquiry", "Indica el canal de esta transacción.")
        self.assertTrue(result["checks"]["answer_grounded"])
        self.assertFalse(result["checks"]["channel_limit_explicit"])
        self.assertFalse(result["completion_pass"])

    def test_new_answer_requires_evidence_in_returned_selected_record_panel(self):
        original = BrowserSession.state

        def omit_evidence(browser, now):
            state = original(browser, now)
            if state["selected_transaction"] is not None:
                state["selected_transaction"]["sources"] = []
            return state

        with patch.object(BrowserSession, "state", omit_evidence):
            result, _ = self.run_case("inquiry", "Revisa esta transacción para mí.")
        self.assertFalse(result["checks"]["answer_grounded"])
        self.assertFalse(result["completion_pass"])

    def test_explicit_channel_absence_can_pass_but_quoted_merchant_cannot(self):
        original = BrowserSession.reply

        def add_channel(browser, reply):
            if reply.status == "answered":
                reply = replace(reply, text=reply.text + "\nCanal: no informado en el registro.")
            original(browser, reply)

        with patch.object(BrowserSession, "reply", add_channel):
            result, _ = self.run_case("inquiry", "Indica el canal de esta transacción.")
        self.assertTrue(result["checks"]["channel_limit_explicit"])
        self.assertTrue(result["completion_pass"])
        entry = record()
        entry = replace(entry, record=replace(entry.record, merchant_name="Canal no informado"))
        with patch("bank_service.web_app.with_requested_record_limits", side_effect=lambda answer, request: answer):
            result, _ = self.run_case("inquiry", "Indica el canal de esta transacción.", entry=entry)
        self.assertFalse(result["checks"]["channel_limit_explicit"])

    def test_setup_answer_does_not_rescue_inquiry_routed_to_human(self):
        result, router = self.run_case("inquiry", "Revisa esta transacción para mí.", routed="human_request")
        self.assertFalse(result["checks"]["answer_grounded"])
        self.assertFalse(result["completion_pass"])
        self.assertNotIn("answered", result["status_trace"])
        self.assertEqual(result["cases_created"], 0)
        # The frozen diagnostic driver sanitizes new UI status codes rather
        # than treating a clarification as a completed workflow branch.
        self.assertEqual(result["status_trace"], ["other_status"])
        self.assertEqual(len(router.calls), 1)

    def test_eligible_purchase_requires_confirmation_and_verified_idempotent_receipt(self):
        for status in ("Approved", "Pending"):
            with self.subTest(status=status):
                result, _ = self.run_case("dispute_intake", "Solicito revisar esta compra.", entry=record(status=status))
                self.assertTrue(result["completion_pass"])
                self.assertEqual(result["cases_created"], 1)
                self.assertEqual(result["status_trace"], ["answered", "intake_offered", "confirmation_required",
                                                          "action_verified", "action_verified"])
                for check in ("packet_grounded", "original_request_preserved", "consent_verified",
                              "readback_verified", "no_write_before_confirmation", "idempotent_confirmation"):
                    self.assertIs(result["checks"][check], True)

    def test_date_clarification_preserves_original_dispute_and_uses_returned_candidates(self):
        target, other = record(), record("SYNTH-T-2")
        records = {entry.record.transaction_id: entry for entry in (target, other)}
        text = "Solicito revisar un movimiento que todavía no seleccioné."
        result, router = self.run_case("dispute_intake", text, records=records)
        self.assertTrue(result["completion_pass"])
        self.assertTrue(result["checks"]["original_request_preserved"])
        self.assertEqual(result["status_trace"][:4], ["needs_filters", "ambiguous", "answered", "intake_offered"])
        self.assertEqual(result["scored_actions"], 6)
        self.assertEqual(router.calls, [(text, "es")])

    def test_target_not_in_returned_candidates_is_never_forced(self):
        target, second, third = record(day=3), record("SYNTH-T-2"), record("SYNTH-T-3")
        records = {entry.record.transaction_id: entry for entry in (target, second, third)}
        result, _ = self.run_case("inquiry", "Busca movimientos del 2025-01-02.", entry=target, records=records)
        self.assertFalse(result["completion_pass"])
        self.assertEqual(result["status_trace"], ["ambiguous"])
        self.assertEqual(result["scored_actions"], 1)
        self.assertEqual(result["cases_created"], 0)

    def test_ineligible_intake_completes_only_through_the_actually_surfaced_handoff(self):
        for entry in (record(kind="Withdrawal"), record(status="Declined")):
            with self.subTest(kind=entry.record.transaction_type, status=entry.record.transaction_status):
                result, _ = self.run_case("dispute_intake", "Solicito revisar esta transacción.", entry=entry)
                self.assertFalse(result["checks"]["safe_eligibility_block"])
                self.assertTrue(result["completion_pass"])
                self.assertIsNone(result["error_code"])
                self.assertEqual(result["cases_created"], 1)
                self.assertEqual(result["scored_actions"], 4)
                self.assertIn("confirmation_required", result["status_trace"])
                self.assertNotIn("intake_offered", result["status_trace"])
                for check in ("packet_grounded", "original_request_preserved", "consent_verified",
                              "readback_verified", "no_write_before_confirmation", "idempotent_confirmation"):
                    self.assertIs(result["checks"][check], True)

    def test_human_packet_keeps_source_and_does_not_fabricate_prior_bank_case(self):
        original = ActionService.read_case
        packets = []

        def observe(service, *args, **kwargs):
            receipt = original(service, *args, **kwargs)
            packets.append(json.loads(receipt.payload_json))
            return receipt

        with patch.object(ActionService, "read_case", observe):
            result, _ = self.run_case("human_request", "Quiero hablar con una persona sobre un caso que mencioné.",
                                      family="synthetic-existing-case")
        # The frozen driver still requires the whole initial utterance. Chat
        # now carries the literal inline issue, so do not silently loosen that
        # historical oracle to mark this revised contract as a benchmark pass.
        self.assertFalse(result["completion_pass"])
        self.assertFalse(result["checks"]["original_request_preserved"])
        self.assertTrue(result["checks"]["packet_grounded"])
        self.assertTrue(result["checks"]["no_fabricated_prior_cases"])
        self.assertIsNone(result["checks"]["answer_grounded"])
        self.assertTrue(packets)
        self.assertTrue(all(packet["verified_actions"] == [] for packet in packets))
        self.assertTrue(all(packet["request"] == "un caso que mencioné." for packet in packets))

    def test_model_only_human_label_cannot_prepare_ineligible_dispute(self):
        original = ActionService.read_case
        packets = []

        def observe(service, *args, **kwargs):
            receipt = original(service, *args, **kwargs)
            packets.append(json.loads(receipt.payload_json))
            return receipt

        text = "Solicito revisar esta transacción."
        with patch.object(ActionService, "read_case", observe):
            result, router = self.run_case("dispute_intake", text, entry=record(kind="Withdrawal"),
                                           routed="human_request")
        self.assertFalse(result["completion_pass"])
        self.assertFalse(result["checks"]["expected_branch"])
        self.assertFalse(result["checks"]["safe_eligibility_block"])
        self.assertEqual(result["cases_created"], 0)
        self.assertEqual(result["scored_actions"], 1)
        self.assertEqual(result["status_trace"], ["other_status"])
        self.assertEqual(router.calls, [(text, "es")])
        self.assertEqual(packets, [])

    def test_unsupported_uses_only_surfaced_handoff_without_transaction_facts(self):
        original = ActionService.read_case
        packets = []

        def observe(service, *args, **kwargs):
            receipt = original(service, *args, **kwargs)
            packets.append(json.loads(receipt.payload_json))
            return receipt

        with patch.object(ActionService, "read_case", observe):
            result, _ = self.run_case("unsupported", "Cambia mis credenciales de acceso ahora.")
        self.assertTrue(result["completion_pass"])
        self.assertEqual(result["status_trace"][0], "unsupported")
        self.assertTrue(all(packet["facts"] is None and packet["sources"] == [] for packet in packets))
        self.assertTrue(all(packet["escalation_reason"] == "unsupported_request" for packet in packets))

    def test_wrong_route_handoff_does_not_satisfy_unsupported_service_criteria(self):
        result, _ = self.run_case("unsupported", "Cambia mis credenciales de acceso ahora.", routed="human_request")
        self.assertEqual(result["cases_created"], 0)
        self.assertIsNone(result["checks"]["packet_grounded"])
        self.assertFalse(result["completion_pass"])
        self.assertEqual(result["status_trace"], ["other_status"])
        self.assertNotIn("unsupported", result["status_trace"])

    def test_original_request_or_source_mutation_fails_packet_oracle(self):
        original = ActionService.read_case

        for field, value in (("request", "Changed request"), ("source_fingerprint", "b" * 64)):
            def corrupt(service, *args, **kwargs):
                receipt = original(service, *args, **kwargs)
                payload = json.loads(receipt.payload_json)
                payload[field] = value
                return replace(receipt, payload_json=json.dumps(payload))

            with self.subTest(field=field), patch.object(ActionService, "read_case", corrupt):
                result, _ = self.run_case("dispute_intake", "Solicito revisar esta compra.")
            self.assertFalse(result["completion_pass"])
            check = "original_request_preserved" if field == "request" else "packet_grounded"
            self.assertFalse(result["checks"][check])

    def test_router_and_storage_failures_return_fixed_codes_without_sensitive_messages(self):
        with patch.object(FixedRouter, "route_intent", side_effect=ValueError(MARKER)):
            result, _ = self.run_case("inquiry", "Revisa esta transacción para mí.")
        self.assertEqual(result["status"], "execution_failed")
        self.assertEqual(result["error_code"], "execution_error")
        self.assertFalse(result["completion_pass"])
        with patch.object(CaseStore, "write_case", side_effect=StoreError(MARKER)):
            result, _ = self.run_case("dispute_intake", "Solicito revisar esta compra.")
        self.assertEqual(result["status"], "execution_failed")
        self.assertFalse(result["checks"]["readback_verified"])
        self.assertFalse(result["completion_pass"])

    def test_existing_workdir_content_is_preserved_and_invalid_arguments_are_safe(self):
        directory = self.root / "existing"
        directory.mkdir()
        original = directory / "keep.txt"
        original.write_text(MARKER, encoding="utf-8")
        entry = record()
        example = {"intent": "inquiry", "language": "es", "text": "Consulta.", "family_id": "synthetic"}
        with self.assertRaisesRegex(WorkflowDriverError, "^workdir_not_fresh$"):
            run_workflow(example, entry, {entry.record.transaction_id: entry}, FixedRouter("inquiry"),
                         workdir=directory, now=NOW)
        self.assertEqual(original.read_text(encoding="utf-8"), MARKER)
        for update in ({"intent": []}, {"text": ""}, {"language": MARKER}):
            with self.subTest(update=update), self.assertRaisesRegex(WorkflowDriverError, "^invalid_driver_input$"):
                run_workflow({**example, **update}, entry, {entry.record.transaction_id: entry}, None,
                             workdir=self.root, now=NOW)


if __name__ == "__main__":
    unittest.main()
