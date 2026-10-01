"""Synthetic multi-turn workflow checks using a disposable local case store."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_service.access import AccessDenied, Permission, TrustedSession
from bank_service.actions import ActionError, ActionService
from bank_service.case_store import CaseStore, StoreError
from bank_service.conversation import Conversation, ConversationError
from bank_service.records import TransactionRecord
from bank_service.selection import SelectionError, TransactionFilters
from bank_service.transactions import SourceReference, SourcedTransaction


def synthetic_entry(identifier="SYNTH-A", **changes):
    record = TransactionRecord(
        transaction_id=identifier, customer_id="SYNTH-OWNER", product_id="SYNTH-PRODUCT",
        transaction_date=datetime(2026, 6, 16, 12, 30), process_date=date(2026, 6, 17),
        transaction_type="Purchase", amount=Decimal("10.00"), currency="USD",
        transaction_status="Approved", merchant_name="Synthetic shop",
    )
    return SourcedTransaction(
        replace(record, **changes),
        (SourceReference("synthetic/transactions.csv", 1, "a" * 64),),
    )


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = CaseStore(Path(self.temp.name) / "synthetic.sqlite3")
        self.addCleanup(self.store.close)
        self.now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        self.session = TrustedSession(
            "SYNTH-OWNER", self.now + timedelta(minutes=15),
            frozenset({Permission.READ_TRANSACTION, Permission.CREATE_SIMULATED_INTAKE,
                       Permission.CREATE_SIMULATED_HANDOFF}),
        )
        self.records = {
            "SYNTH-A": synthetic_entry(),
            "SYNTH-B": synthetic_entry("SYNTH-B", amount=Decimal("20.00")),
            "SYNTH-C": synthetic_entry("SYNTH-C", currency="ARS"),
            "SYNTH-FOREIGN": synthetic_entry("SYNTH-FOREIGN", customer_id="SYNTH-OTHER"),
        }
        self.actions = ActionService(self.records, self.store)
        self.conversation = Conversation(self.records, self.actions, self.session)

    def select_a(self, conversation=None):
        conversation = self.conversation if conversation is None else conversation
        return conversation.search(
            self.session, TransactionFilters(amount=Decimal("10"), currency="USD"), now=self.now,
        )

    def prepare(self, conversation=None):
        conversation = self.conversation if conversation is None else conversation
        self.select_a(conversation)
        return conversation.prepare_intake(self.session, "No reconozco esta compra.", now=self.now).draft

    def test_search_returns_all_four_outcomes_in_both_languages(self):
        cases = (
            (TransactionFilters(), "needs_filters", ()),
            (TransactionFilters(currency="COP"), "no_match", ()),
            (TransactionFilters(currency="USD"), "ambiguous", ("SYNTH-A", "SYNTH-B")),
            (TransactionFilters(amount=Decimal("10"), currency="USD"), "answered", ()),
        )
        for language in ("es", "pt"):
            conversation = Conversation(self.records, self.actions, self.session, language=language)
            for filters, expected, candidates in cases:
                with self.subTest(language=language, status=expected):
                    reply = conversation.search(self.session, filters, now=self.now)
                    self.assertEqual((reply.language, reply.status, reply.candidate_ids),
                                     (language, expected, candidates))
                    self.assertTrue(reply.text)
                    self.assertNotIn("SYNTH-FOREIGN", reply.text)
                    self.assertIsNone(reply.receipt)
                    if expected == "answered":
                        self.assertEqual(reply.selected_id, "SYNTH-A")
                        self.assertIn("10.00 USD", reply.text)
                        self.assertEqual(reply.sources, self.records["SYNTH-A"].sources)
            self.assertEqual(self.store.count(), 0)

    def test_ambiguity_choice_and_followup_read_fresh_authorized_facts(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                conversation = Conversation(self.records, self.actions, self.session, language=language)
                conversation.search(self.session, TransactionFilters(currency="USD"), now=self.now)
                choice = conversation.choose(self.session, "SYNTH-B", now=self.now)
                self.assertEqual(choice.selected_id, "SYNTH-B")
                self.assertIn("20.00 USD", choice.text)
                self.records["SYNTH-B"] = synthetic_entry("SYNTH-B", amount=Decimal("99.23"))
                refreshed = conversation.inquire(self.session, now=self.now)
                self.assertIn("99.23 USD", refreshed.text)
                self.assertNotIn("20.00 USD", refreshed.text)
                self.records["SYNTH-B"] = synthetic_entry("SYNTH-B", amount=Decimal("20.00"))

    def test_all_turns_require_exact_session_instance_and_fresh_read_grant(self):
        draft = self.prepare()
        operations = (
            lambda session, now: self.conversation.clear_selection(session, now=now),
            lambda session, now: self.conversation.search(session, None, now=now),
            lambda session, now: self.conversation.choose(session, "SYNTH-FOREIGN", now=now),
            lambda session, now: self.conversation.inquire(session, now=now),
            lambda session, now: self.conversation.set_language(session, "invalid", now=now),
            lambda session, now: self.conversation.prepare_intake(session, None, now=now),
            lambda session, now: self.conversation.prepare_handoff(session, None, now=now),
            lambda session, now: self.conversation.confirm(session, draft.draft_id, confirmed=True, now=now),
        )
        for session, now in (
            (None, self.now), ({"customer_id": "SYNTH-OWNER"}, self.now),
            (replace(self.session), self.now),
            (replace(self.session, customer_id="SYNTH-OTHER"), self.now),
            (self.session, self.session.expires_at), (self.session, self.now.replace(tzinfo=None)),
        ):
            for index, operation in enumerate(operations):
                with self.subTest(operation=index, context=type(session).__name__, now=now):
                    with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                        operation(session, now)
        self.assertEqual(self.store.count(), 0)
        # Rejected attempts did not overwrite the legitimate user's pending draft.
        self.assertEqual(self.conversation.confirm(
            self.session, draft.draft_id, confirmed=True, now=self.now,
        ).status, "action_verified")

    def test_choice_must_belong_to_pending_candidates_without_echoing_invalid_id(self):
        for identifier in ("SYNTH-C", "SYNTH-FOREIGN", "PRIVATE_UNKNOWN", None, []):
            with self.subTest(identifier=identifier):
                self.conversation.search(self.session, TransactionFilters(currency="USD"), now=self.now)
                with self.assertRaisesRegex(ConversationError, "^invalid_choice$"):
                    self.conversation.choose(self.session, identifier, now=self.now)
                with self.assertRaisesRegex(ConversationError, "^invalid_choice$"):
                    self.conversation.choose(self.session, "SYNTH-A", now=self.now)
        self.conversation.search(self.session, TransactionFilters(currency="USD"), now=self.now)
        self.assertEqual(self.conversation.choose(self.session, "SYNTH-A", now=self.now).selected_id, "SYNTH-A")

    def test_rejected_choice_clears_previous_answer_before_handoff(self):
        self.conversation.inquire(self.session, "SYNTH-A", now=self.now)
        with self.assertRaisesRegex(ConversationError, "^invalid_choice$"):
            self.conversation.choose(self.session, "PRIVATE_UNKNOWN", now=self.now)
        with self.assertRaisesRegex(ConversationError, "^transaction_required$"):
            self.conversation.inquire(self.session, now=self.now)
        prepared = self.conversation.prepare_handoff(self.session, "Necesito ayuda humana.", now=self.now)
        proposed = json.loads(self.actions.review_draft(self.session, prepared.draft.draft_id, now=self.now))
        self.assertIsNone(proposed["transaction_id"])
        self.assertIsNone(proposed["facts"])
        self.assertEqual(proposed["sources"], [])
        self.assertIn("choice_rejected", proposed["attempted_steps"])

    def test_failed_search_invalidates_selection_draft_and_prior_candidates(self):
        draft = self.prepare()
        with self.assertRaises(SelectionError):
            self.conversation.search(self.session, None, now=self.now)
        with self.assertRaisesRegex(ConversationError, "^transaction_required$"):
            self.conversation.inquire(self.session, now=self.now)
        with self.assertRaisesRegex(ConversationError, "^no_pending_action$"):
            self.conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        with self.assertRaises(ActionError):
            self.actions.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        self.conversation.search(self.session, TransactionFilters(currency="USD"), now=self.now)
        with self.assertRaises(SelectionError):
            self.conversation.search(self.session, None, now=self.now)
        with self.assertRaisesRegex(ConversationError, "^invalid_choice$"):
            self.conversation.choose(self.session, "SYNTH-A", now=self.now)
        self.assertEqual(self.store.count(), 0)

    def test_clear_selection_invalidates_candidates_and_consent_but_keeps_verified_history(self):
        pending = self.prepare()
        self.assertIsNone(self.conversation.clear_selection(self.session, now=self.now))
        with self.assertRaisesRegex(ConversationError, "^transaction_required$"):
            self.conversation.inquire(self.session, now=self.now)
        with self.assertRaisesRegex(ConversationError, "^no_pending_action$"):
            self.conversation.confirm(self.session, pending.draft_id, confirmed=True, now=self.now)
        self.assertEqual(self.store.count(), 0)
        verified_draft = self.prepare()
        verified = self.conversation.confirm(self.session, verified_draft.draft_id, confirmed=True, now=self.now)
        self.conversation.search(self.session, TransactionFilters(currency="USD"), now=self.now)
        self.conversation.clear_selection(self.session, now=self.now)
        with self.assertRaisesRegex(ConversationError, "^invalid_choice$"):
            self.conversation.choose(self.session, "SYNTH-A", now=self.now)
        with self.assertRaisesRegex(ConversationError, "^no_pending_action$"):
            self.conversation.confirm(self.session, verified_draft.draft_id, confirmed=True, now=self.now)
        handoff = self.conversation.prepare_handoff(self.session, "Necesito ayuda humana.", now=self.now)
        proposed = json.loads(self.actions.review_draft(self.session, handoff.draft.draft_id, now=self.now))
        self.assertIsNone(proposed["transaction_id"])
        self.assertIn("action_verified", proposed["attempted_steps"])
        self.assertEqual(proposed["verified_actions"][0]["case_id"], verified.receipt.case_id)

    def test_changed_record_ownership_is_rechecked_for_choice_and_followup(self):
        self.conversation.search(self.session, TransactionFilters(currency="USD"), now=self.now)
        self.records["SYNTH-A"] = synthetic_entry(customer_id="SYNTH-OTHER")
        with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
            self.conversation.choose(self.session, "SYNTH-A", now=self.now)
        self.records["SYNTH-A"] = synthetic_entry()
        self.select_a()
        self.records["SYNTH-A"] = synthetic_entry(customer_id="SYNTH-OTHER")
        with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
            self.conversation.inquire(self.session, now=self.now)
        with self.assertRaisesRegex(ConversationError, "^transaction_required$"):
            self.conversation.prepare_intake(self.session, "Synthetic reason", now=self.now)

    def test_language_switch_cancels_old_consent_and_preserves_selected_record(self):
        draft = self.prepare()
        reply = self.conversation.set_language(self.session, "pt", now=self.now)
        self.assertEqual((reply.status, reply.language, reply.candidate_ids, reply.selected_id),
                         ("language_changed", "pt", (), None))
        with self.assertRaisesRegex(ConversationError, "^no_pending_action$"):
            self.conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        reply = self.conversation.inquire(self.session, now=self.now)
        self.assertIn('Transação: "SYNTH-A"', reply.text)
        self.assertEqual(self.store.count(), 0)

    def test_intake_requires_selection_and_explicit_consent_then_reconciles_duplicate(self):
        with self.assertRaisesRegex(ConversationError, "^transaction_required$"):
            self.conversation.prepare_intake(self.session, "Synthetic reason", now=self.now)
        draft = self.prepare()
        self.assertEqual(self.store.count(), 0)
        first = self.conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        again = self.conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        self.assertEqual((first.status, again.status), ("action_verified", "action_verified"))
        self.assertEqual(first.receipt, again.receipt)
        self.assertTrue(first.receipt.simulated)
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.actions.read_case(self.session, first.receipt.case_id, now=self.now), first.receipt)
        with self.assertRaisesRegex(ConversationError, "^action_already_verified$"):
            self.conversation.confirm(self.session, draft.draft_id, confirmed=False, now=self.now)

    def test_cancelled_action_cannot_be_resurrected(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                conversation = Conversation(self.records, self.actions, self.session, language=language)
                draft = self.prepare(conversation)
                reply = conversation.confirm(self.session, draft.draft_id, confirmed=False, now=self.now)
                self.assertEqual((reply.status, reply.language, reply.receipt), ("cancelled", language, None))
                self.assertEqual(reply.text, {
                    "es": "Solicitud cancelada sin crear un caso nuevo.",
                    "pt": "Solicitação cancelada sem criar um novo caso.",
                }[language])
                with self.assertRaisesRegex(ConversationError, "^no_pending_action$"):
                    conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
                with self.assertRaises(ActionError):
                    self.actions.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        self.assertEqual(self.store.count(), 0)

    def test_new_action_replaces_pending_confirmation(self):
        old = self.prepare()
        new = self.conversation.prepare_intake(self.session, "Otro motivo sintético.", now=self.now).draft
        self.assertNotEqual(old.draft_id, new.draft_id)
        with self.assertRaisesRegex(ConversationError, "^no_pending_action$"):
            self.conversation.confirm(self.session, old.draft_id, confirmed=True, now=self.now)
        self.conversation.confirm(self.session, new.draft_id, confirmed=True, now=self.now)
        self.assertEqual(self.store.count(), 1)

    def test_handoff_without_selection_requires_consent_and_preserves_useful_context(self):
        conversation = Conversation(self.records, self.actions, self.session, language="pt")
        conversation.search(self.session, TransactionFilters(currency="COP"), now=self.now)
        prepared = conversation.prepare_handoff(
            self.session, "Quero ajuda para localizar a transação.", escalation_reason="record_not_found",
            unresolved_questions=("Qual transação corresponde à solicitação?",), now=self.now,
        )
        self.assertEqual((prepared.status, prepared.selected_id), ("confirmation_required", None))
        self.assertEqual(self.store.count(), 0)
        result = conversation.confirm(self.session, prepared.draft.draft_id, confirmed=True, now=self.now)
        self.assertEqual(result.receipt.language, "pt")
        packet = json.loads(result.receipt.payload_json)
        # Assert contents without coupling these checks to the packet's nesting.
        encoded = json.dumps(packet, ensure_ascii=False)
        for value in ("record_not_found", "search_no_match", "Quero ajuda para localizar a transação.",
                      "Qual transação corresponde à solicitação?"):
            self.assertIn(value, encoded)
        for value in ("SYNTH-FOREIGN", "SYNTH-OTHER", "Synthetic shop"):
            self.assertNotIn(value, encoded)
        self.assertEqual(self.store.count(), 1)

    def test_action_permissions_are_required_in_addition_to_read_access(self):
        session = replace(self.session, permissions=frozenset({Permission.READ_TRANSACTION}))
        conversation = Conversation(self.records, self.actions, session)
        self.assertEqual(conversation.inquire(session, "SYNTH-A", now=self.now).status, "answered")
        for operation in (
            lambda: conversation.prepare_intake(session, "Synthetic reason", now=self.now),
            lambda: conversation.prepare_handoff(session, "Synthetic request", now=self.now),
        ):
            with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                operation()
        self.assertEqual(self.store.count(), 0)

    def test_handoff_resolves_prior_verified_case_and_records_failed_confirmation(self):
        draft = self.prepare()
        with patch.object(self.actions, "confirm", side_effect=ActionError("write_not_verified")):
            with self.assertRaises(ActionError):
                self.conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        verified = self.conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        prepared = self.conversation.prepare_handoff(
            self.session, "Necesito ayuda con el caso simulado.", now=self.now,
        )
        result = self.conversation.confirm(self.session, prepared.draft.draft_id, confirmed=True, now=self.now)
        packet = json.dumps(json.loads(result.receipt.payload_json), ensure_ascii=False)
        self.assertIn(verified.receipt.case_id, packet)
        self.assertIn("confirmation_failed", packet)
        self.assertIn("action_verified", packet)
        self.assertEqual(self.store.count(), 2)

    def test_repeated_searches_do_not_hide_prior_handoff_outcomes(self):
        for language, request, question in (
            ("es", "Quiero hablar con una persona", "No reconozco la compra seleccionada."),
            ("pt", "Quero falar com uma pessoa", "Não reconheço a compra selecionada."),
        ):
            with self.subTest(language=language):
                conversation = Conversation(self.records, self.actions, self.session, language=language)
                cancelled = self.prepare(conversation)
                conversation.confirm(self.session, cancelled.draft_id, confirmed=False, now=self.now)
                draft = self.prepare(conversation)
                with patch.object(self.actions, "confirm", side_effect=ActionError("write_not_verified")):
                    with self.assertRaises(ActionError):
                        conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
                verified = conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
                for _ in range(16):
                    self.select_a(conversation)
                prepared = conversation.prepare_handoff(
                    self.session, request, unresolved_questions=(question,), now=self.now,
                )
                proposed = json.loads(self.actions.review_draft(
                    self.session, prepared.draft.draft_id, now=self.now,
                ))
                steps = proposed["attempted_steps"]
                self.assertEqual(len(steps), len(set(steps)))
                self.assertLessEqual(len(steps), 12)
                for observed in ("search_attempted", "transaction_answered", "intake_prepared",
                                 "action_cancelled", "confirmation_failed", "action_verified"):
                    self.assertIn(observed, steps)
                self.assertEqual(proposed["request"], request)
                self.assertEqual(proposed["unresolved_questions"], [question])
                self.assertEqual(proposed["verified_actions"][0]["case_id"], verified.receipt.case_id)
                result = conversation.confirm(self.session, prepared.draft.draft_id, confirmed=True, now=self.now)
                stored = json.loads(result.receipt.payload_json)
                self.assertEqual(stored["attempted_steps"], steps)
                self.assertEqual(stored["unresolved_questions"], [question])

    def test_confirmation_rejects_truthy_values_and_unrelated_ids_without_writing(self):
        draft = self.prepare()
        for value in (1, "yes", "false", None, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ConversationError, "^invalid_confirmation$"):
                self.conversation.confirm(self.session, draft.draft_id, confirmed=value, now=self.now)
        for identifier in ("PRIVATE_UNKNOWN", None, []):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(ConversationError, "^no_pending_action$"):
                self.conversation.confirm(self.session, identifier, confirmed=True, now=self.now)
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(self.conversation.confirm(
            self.session, draft.draft_id, confirmed=True, now=self.now,
        ).status, "action_verified")

    def test_unverified_action_result_never_becomes_success_or_false_cancellation(self):
        draft = self.prepare()
        with patch.object(self.actions, "confirm", return_value=None):
            with self.assertRaisesRegex(ConversationError, "^action_not_verified$"):
                self.conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(self.conversation.confirm(
            self.session, draft.draft_id, confirmed=True, now=self.now,
        ).status, "action_verified")

    def test_failed_cancellation_preserves_recovery_of_a_committed_unverified_case(self):
        for operation in ("search", "clear_selection", "invalid_choice"):
            with self.subTest(operation=operation):
                conversation = Conversation(self.records, self.actions, self.session)
                draft = self.prepare(conversation)
                before = self.store.count()
                original_read = self.store.read_by_key

                def fail_after_write(key):
                    if self.store.count() > before:
                        raise StoreError("store_read_failed")
                    return original_read(key)

                with patch.object(self.store, "read_by_key", side_effect=fail_after_write):
                    with self.assertRaisesRegex(ActionError, "^unknown_outcome$"):
                        conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
                self.assertEqual(self.store.count(), before + 1)
                with self.assertRaisesRegex(ActionError, "^already_confirmed$"):
                    if operation == "search":
                        conversation.search(self.session, TransactionFilters(currency="USD"), now=self.now)
                    elif operation == "clear_selection":
                        conversation.clear_selection(self.session, now=self.now)
                    else:
                        conversation.choose(self.session, "PRIVATE_UNKNOWN", now=self.now)
                with self.assertRaisesRegex(ConversationError, "^transaction_required$"):
                    conversation.inquire(self.session, now=self.now)
                recovered = conversation.confirm(self.session, draft.draft_id, confirmed=True, now=self.now)
                self.assertEqual(recovered.status, "action_verified")
                self.assertEqual(self.store.count(), before + 1)


if __name__ == "__main__":
    unittest.main()
