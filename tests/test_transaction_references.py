"""Post-final engineering checks with invented records; no evaluation cases."""
from datetime import date
from decimal import Decimal
import json
import unittest

from bank_service.routing import IntentProposal, RoutingError
from bank_service.access import AccessDenied
from bank_service.selection import TransactionFilters
from bank_service.transaction_references import extract_record_slots, parse_transaction_reference
from bank_service.final_workflow_driver import run_final_workflow
from tests.test_final_workflow_driver import NOW, case, record


TARGET = "TRX-000TOYABC1"
FOREIGN = "TRX-000OTHER2"


class MisleadingRouter:
    def __init__(self, intent):
        self.intent, self.calls = intent, []

    def route_intent(self, text, language):
        self.calls.append((text, language))
        return IntentProposal(self.intent, .99, True)


class TransactionReferenceUnitTests(unittest.TestCase):
    def test_bare_labeled_and_balanced_quoted_source_references(self):
        for language in ("es", "pt"):
            for text in (TARGET, f'"{TARGET}"', f"'{TARGET}'", f"id: {TARGET}",
                         f'transacción "{TARGET}"', f"transação '{TARGET}'", f"referencia: {TARGET}."):
                with self.subTest(language=language, text=text):
                    parsed = parse_transaction_reference(text, language, {TARGET: None})
                    self.assertEqual(parsed.transaction_id, TARGET)
                    self.assertTrue(parsed.slot_only)
                    slots = extract_record_slots(text, language, {TARGET: None}, reference_date=NOW.date())
                    self.assertEqual(slots.transaction_id, TARGET)
                    self.assertEqual(slots.filters, TransactionFilters())

    def test_literal_source_quote_wrappers_preserve_exact_stored_key(self):
        for stored in (f'"{TARGET}"', f"'{TARGET}'"):
            for text in (TARGET, f'"{TARGET}"', f"'{TARGET}'"):
                parsed = parse_transaction_reference(text, "es", {stored: None})
                self.assertEqual(parsed.transaction_id, stored)
                self.assertTrue(parsed.slot_only)

    def test_native_case_exact_legacy_demo_uppercase_compatibility(self):
        parsed = parse_transaction_reference(TARGET.lower(), "es", {TARGET: None})
        self.assertEqual(parsed.transaction_id, TARGET.lower())
        self.assertTrue(parsed.slot_only)
        self.assertEqual(parse_transaction_reference("demo-tx-001", "es", {"DEMO-TX-001": None}).transaction_id,
                         "DEMO-TX-001")

    def test_multiple_distinct_and_quote_alias_collisions_rejected(self):
        for text, identifiers in ((f"{TARGET} {FOREIGN}", {TARGET: None, FOREIGN: None}),
                                  (f"{TARGET} TX-OTHER-3", {TARGET: None})):
            with self.subTest(text=text), self.assertRaisesRegex(RoutingError, "^ambiguous_transaction_id$"):
                parse_transaction_reference(text, "es", identifiers)
        with self.assertRaises(AccessDenied):
            parse_transaction_reference(TARGET, "es", {TARGET: None, f'"{TARGET}"': None})
        parsed = parse_transaction_reference(f'{TARGET} "{TARGET}"', "es", {TARGET: None})
        self.assertEqual(parsed.transaction_id, TARGET)
        self.assertTrue(parsed.slot_only)

    def test_identifier_currency_amount_and_date_substrings_are_masked(self):
        for identifier in ("TRX-USD-25", "TX-USD-25", "TRX-2026-06-17", "TRX-MXN-2026-05-03"):
            with self.subTest(identifier=identifier):
                slots = extract_record_slots(identifier, "es", {identifier: None}, reference_date=NOW.date())
                self.assertEqual(slots.transaction_id, identifier)
                self.assertEqual(slots.filters, TransactionFilters())
                self.assertFalse(slots.needs_currency)
                self.assertIsNone(slots.amount_without_currency)
        slots = extract_record_slots('Consultar "TRX-USD-25" el 17/06/2026 por 21,35 COP', "es",
                                     {"TRX-USD-25": None}, reference_date=NOW.date())
        self.assertEqual(slots.filters, TransactionFilters(date(2026, 6, 17), Decimal("21.35"), "COP"))

    def test_explicit_dispute_and_unsupported_business_prose_are_not_slot_only(self):
        for text in (f"No reconozco el cargo {TARGET}", f"Transfiere dinero a {TARGET}",
                     f"Quiero hablar con una persona sobre {TARGET}"):
            with self.subTest(text=text):
                parsed = parse_transaction_reference(text, "es", {TARGET: None})
                self.assertEqual(parsed.transaction_id, TARGET)
                self.assertFalse(parsed.slot_only)

    def test_partial_and_unbalanced_quotes_are_never_repaired(self):
        for text in (f'"{TARGET}', f"{TARGET}'", f'"{TARGET}\''):
            with self.subTest(text=text), self.assertRaisesRegex(RoutingError, "^invalid_transaction_id$"):
                parse_transaction_reference(text, "es", {TARGET: None})
        longer = TARGET + "SUFFIX"
        self.assertNotEqual(parse_transaction_reference(longer, "es", {TARGET: None}).transaction_id, TARGET)
        self.assertIsNone(parse_transaction_reference("prefix_" + TARGET + "_suffix", "es", {TARGET: None}).transaction_id)
        with self.assertRaisesRegex(RoutingError, "^invalid_transaction_id$"):
            parse_transaction_reference("TRX-" + "A" * 65, "es", {})

    def test_unknown_and_generic_known_native_id_keep_identity_only(self):
        parsed = parse_transaction_reference("TRX-UNKNOWN9", "pt", {TARGET: None})
        self.assertEqual(parsed.transaction_id, "TRX-UNKNOWN9")
        self.assertTrue(parsed.slot_only)
        parsed = parse_transaction_reference("SYNTH-TARGET", "pt", {"SYNTH-TARGET": None})
        self.assertEqual(parsed.transaction_id, "SYNTH-TARGET")
        self.assertTrue(parsed.slot_only)

    def test_unicode_neighbours_and_normalization_cannot_select_partial_id(self):
        for text in ("transaccion TRX-TOY1é", "transacción TRX-TOY1é", "éDEMO-TX-001",
                     "TRX-TOY1\u0301", "\u0301TRX-TOY1", "ＴＲＸ-TOY1"):
            with self.subTest(text=text):
                slots = extract_record_slots(text, "es", {"TRX-TOY1": None, "TRX-TOY1e": None,
                                                           "DEMO-TX-001": None}, reference_date=NOW.date())
                self.assertIsNone(slots.transaction_id)
        for text in ("transacción ABC9", "transação ABC9", "id: ABC9"):
            self.assertEqual(extract_record_slots(text, "es", {}, reference_date=NOW.date()).transaction_id,
                             "ABC9")


class TransactionReferenceHttpTests(unittest.TestCase):
    def journey(self, steps, *, target=None, router=None, language="es", records=None):
        target = target or record(TARGET)
        foreign = record(FOREIGN, "SYNTH-FOREIGN-OWNER", "SYNTH-FOREIGN-SECRET")
        rows = {e.record.transaction_id: e for e in (target, foreign)} if records is None else records
        result = run_final_workflow(case(steps, language=language), target, rows, router,
                                    foreign_entry=foreign if FOREIGN in rows else None, now=NOW)
        self.assertEqual(result["status"], "executed", result["driver_error"])
        self.assertIsNone(result["cleanup_error"])
        return result

    def test_bare_native_lookup_bypasses_misleading_model_and_preserves_native_evidence(self):
        for language in ("es", "pt"):
            for intent in ("dispute_intake", "human_request"):
                for stored in (TARGET, f'"{TARGET}"'):
                    with self.subTest(language=language, intent=intent, stored=stored):
                        target = record(stored)
                        router = MisleadingRouter(intent)
                        result = self.journey([{"kind": "message", "text": TARGET}], target=target,
                                              router=router, language=language)
                        state = result["private_observations"]["final_state"]
                        selected = state["selected_transaction"]
                        self.assertEqual(selected["transaction_id"], stored)
                        self.assertEqual(selected["sources"][0]["row_sha256"], "a" * 64)
                        self.assertEqual(result["status_trace"], ["answered"])
                        self.assertEqual(router.calls, [])
                        self.assertEqual(result["cases_created"], 0)
                        self.assertIsNone(state["pending_draft"])
                        self.assertIsNone(state["intake_offer"])
                        self.assertIsNone(state["handoff_offer"])

    def test_server_owned_pending_dispute_accepts_native_reference_followup(self):
        for language, request in (("es", "No reconozco un cargo."), ("pt", "Não reconheço uma compra.")):
            result = self.journey([{"kind": "message", "text": request},
                                   {"kind": "message", "text": TARGET}], language=language)
            state = result["private_observations"]["final_state"]
            self.assertEqual(state["selected_transaction"]["transaction_id"], TARGET)
            self.assertIsNotNone(state["intake_offer"])
            self.assertIsNone(state["pending_draft"])
            self.assertEqual(result["cases_created"], 0)

    def test_explicit_dispute_with_native_reference_retains_intent_but_requires_consent(self):
        result = self.journey([{"kind": "message", "text": f"No reconozco el cargo {TARGET}"}])
        state = result["private_observations"]["final_state"]
        self.assertEqual(state["selected_transaction"]["transaction_id"], TARGET)
        self.assertIsNotNone(state["intake_offer"])
        self.assertIsNone(state["pending_draft"])
        self.assertEqual(result["cases_created"], 0)

    def test_foreign_missing_and_case_mismatch_give_same_generic_denial(self):
        codes, texts = [], []
        for identifier in (FOREIGN, "TRX-UNKNOWN9", TARGET.lower()):
            result = self.journey([{"kind": "select_target"}, {"kind": "message", "text": identifier}])
            state = result["private_observations"]["final_state"]
            self.assertIsNone(state["selected_transaction"])
            self.assertIsNone(state["pending_draft"])
            self.assertEqual(state["receipts"], [])
            self.assertNotIn("SYNTH-FOREIGN-SECRET", json.dumps(state))
            self.assertEqual(result["cases_created"], 0)
            codes.append(state["error"]["code"])
            texts.append(state["error"]["text"])
        self.assertEqual(codes, ["access_denied"] * 3)
        self.assertEqual(len(set(texts)), 1)

    def test_foreign_alias_collision_is_same_generic_denial_and_clears_selection(self):
        target = record(TARGET)
        first = record(FOREIGN, "SYNTH-FOREIGN-OWNER", "SYNTH-FOREIGN-SECRET")
        second = record(f'"{FOREIGN}"', "SYNTH-SECOND-OWNER", "SYNTH-SECOND-SECRET")
        rows = {entry.record.transaction_id: entry for entry in (target, first, second)}
        result = self.journey([{"kind": "select_target"}, {"kind": "message", "text": FOREIGN}], records=rows)
        state = result["private_observations"]["final_state"]
        self.assertEqual(result["http_errors"], [{"status": 403, "code": "access_denied"}])
        self.assertIsNone(state["selected_transaction"])
        self.assertIsNone(state["pending_draft"])
        self.assertEqual(result["cases_created"], 0)
        self.assertNotIn("SYNTH-FOREIGN-SECRET", json.dumps(state))
        self.assertNotIn("SYNTH-SECOND-SECRET", json.dumps(state))

    def test_expired_reference_denied_without_record_or_draft(self):
        result = self.journey([{"kind": "advance_clock", "seconds": 1201},
                               {"kind": "message", "text": TARGET}])
        state = result["private_observations"]["final_state"]
        self.assertEqual(result["http_errors"], [{"status": 403, "code": "access_denied"}])
        self.assertEqual(state["transactions"], [])
        self.assertIsNone(state["selected_transaction"])
        self.assertIsNone(state["pending_draft"])

    def test_ambiguous_or_malformed_reference_clears_stale_selection(self):
        for text in (f"{TARGET} {FOREIGN}", f'"{TARGET}'):
            result = self.journey([{"kind": "select_target"}, {"kind": "message", "text": text}])
            state = result["private_observations"]["final_state"]
            self.assertIsNone(state["selected_transaction"])
            self.assertIsNone(state["intake_offer"])
            self.assertIsNone(state["pending_draft"])
            self.assertEqual(result["cases_created"], 0)
            self.assertEqual(len(result["http_errors"]), 1)

    def test_identifier_currency_and_date_do_not_trigger_false_filters(self):
        for identifier in ("TRX-USD-25", "TRX-2026-06-17"):
            result = self.journey([{"kind": "message", "text": identifier}], target=record(identifier))
            self.assertEqual(result["status_trace"], ["answered"])
            self.assertEqual(result["private_observations"]["final_state"]["selected_transaction"]["transaction_id"], identifier)


if __name__ == "__main__":
    unittest.main()
