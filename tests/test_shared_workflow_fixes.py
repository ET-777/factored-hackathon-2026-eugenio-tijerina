"""Post-development regressions using synthetic records and isolated case stores."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bank_service.access import AccessDenied, Permission
from bank_service.demo_fixtures import DEMO_CUSTOMER, demo_records
from bank_service.responses import CHANNEL_LIMITS
from bank_service.routing import IntentProposal, RoutingError
from bank_service.web_app import BrowserSession, PrivateCohortConfig, UiError, _now


class FixedRouter:
    def __init__(self, intent, matched=True):
        self.proposal = IntentProposal(intent, 1.0 if matched else 0.0, matched)
        self.calls = 0

    def route_intent(self, text, language):
        self.calls += 1
        return self.proposal


class SharedWorkflowFixTests(unittest.TestCase):
    def browser(self, *, language="es", router=None, kind="Purchase", status="Approved", permissions=None):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config = None
        if permissions is not None:
            records = demo_records()
            entry = records["DEMO-TX-001"]
            records["DEMO-TX-001"] = replace(entry, record=replace(
                entry.record, transaction_type=kind, transaction_status=status))
            config = PrivateCohortConfig(records, DEMO_CUSTOMER, permissions)
        browser = BrowserSession(Path(temporary.name) / "cases.sqlite3", config=config, router=router)
        self.addCleanup(browser.close)
        if config is None:
            entry = browser.records["DEMO-TX-001"]
            browser.records["DEMO-TX-001"] = replace(entry, record=replace(
                entry.record, transaction_type=kind, transaction_status=status))
        now = _now()
        browser.act({"action": "language", "language": language}, now)
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
        return browser, now

    def save_handoff(self, browser, now, request, reason):
        state = browser.state(now)
        self.assertIsNone(state["intake_offer"])
        self.assertIsNone(state["pending_draft"])
        self.assertEqual(browser.store.count(), 0)
        offer_id = state["handoff_offer"]["offer_id"]
        browser.act({"action": "handoff_decision", "offer_id": offer_id, "prepare": True}, now)
        draft = browser.state(now)["pending_draft"]
        self.assertEqual(draft["kind"], "handoff")
        self.assertEqual(draft["packet"]["request"], request)
        self.assertEqual(draft["packet"]["escalation_reason"], reason)
        self.assertEqual(draft["packet"]["facts"]["transaction_id"], "DEMO-TX-001")
        self.assertEqual(draft["packet"]["sources"], state["selected_transaction"]["sources"])
        self.assertEqual(draft["packet"]["verified_actions"], [])
        self.assertEqual(browser.store.count(), 0)
        browser.act({"action": "message", "text": "confirmo"}, now)
        self.assertEqual(browser.store.count(), 0)
        for _ in range(2):
            browser.act({"action": "confirm", "draft_id": draft["draft_id"], "confirmed": True}, now)
        self.assertEqual(browser.store.count(), 1)
        self.assertEqual(len(browser.case_ids), 1)
        receipt = browser.actions.read_case(browser.session, browser.case_ids[0], now=now)
        packet = json.loads(receipt.payload_json)
        self.assertEqual(receipt.kind, "handoff")
        self.assertIs(packet["consent"], True)
        self.assertIs(packet["simulated"], True)
        self.assertEqual(packet["request"], request)
        return packet

    def test_ineligible_movement_offers_grounded_handoff_for_both_routes_and_languages(self):
        for language, request in (("es", "Quiero reclamar esta transacción."),
                                  ("pt", "Quero contestar esta transação.")):
            for learned in (False, True):
                for kind, status in (("Withdrawal", "Approved"), ("Purchase", "Declined"),
                                     ("Purchase", "Reversed")):
                    with self.subTest(language=language, learned=learned, kind=kind, status=status):
                        browser, now = self.browser(language=language, kind=kind, status=status,
                                                    router=FixedRouter("dispute_intake") if learned else None)
                        browser.act({"action": "message", "text": request}, now)
                        packet = self.save_handoff(browser, now, request, "ineligible_intake")
                        self.assertEqual(packet["facts"]["transaction_type"], kind)
                        self.assertEqual(packet["facts"]["transaction_status"], status)

    def test_read_plus_handoff_does_not_need_intake_grant_for_ineligible_movement(self):
        permissions = frozenset({Permission.READ_TRANSACTION, Permission.CREATE_SIMULATED_HANDOFF})
        browser, now = self.browser(kind="Withdrawal", permissions=permissions)
        request = "Quiero reclamar esta transacción."
        browser.act({"action": "message", "text": request}, now)
        self.save_handoff(browser, now, request, "ineligible_intake")
        self.assertEqual(browser.session.permissions, permissions)

    def test_no_handoff_grant_means_explanation_without_action_affordance(self):
        for permissions in (frozenset({Permission.READ_TRANSACTION}),
                            frozenset({Permission.READ_TRANSACTION, Permission.CREATE_SIMULATED_INTAKE})):
            with self.subTest(permissions=permissions):
                browser, now = self.browser(kind="Withdrawal", permissions=permissions)
                browser.act({"action": "message", "text": "Quiero reclamar esta transacción."}, now)
                state = browser.state(now)
                self.assertEqual(state["messages"][-1]["status"], "handoff_unavailable")
                self.assertFalse(state["offers_handoff"])
                self.assertIsNone(state["handoff_offer"])
                self.assertIsNone(state["intake_offer"])
                self.assertIsNone(state["pending_draft"])
                self.assertEqual(browser.store.count(), 0)

    def test_handoff_no_by_text_or_button_preserves_record_and_creates_nothing(self):
        for language, reply in (("es", "No gracias"), ("pt", "Não obrigado")):
            for by_text in (True, False):
                with self.subTest(language=language, by_text=by_text):
                    browser, now = self.browser(language=language, kind="Withdrawal", router=FixedRouter("dispute_intake"))
                    browser.act({"action": "message", "text": "Revisar esta transacción"}, now)
                    identifier = browser.handoff_offer.offer_id
                    payload = ({"action": "message", "text": reply} if by_text else
                               {"action": "handoff_decision", "offer_id": identifier, "prepare": False})
                    browser.act(payload, now)
                    self.assertIsNone(browser.handoff_offer)
                    self.assertIsNone(browser.pending_draft)
                    self.assertEqual(browser.selected_id, "DEMO-TX-001")
                    self.assertEqual(browser.store.count(), 0)

    def test_handoff_offer_is_bound_to_selection_snapshot_expiry_permissions_and_boolean_choice(self):
        for mutation in ("selection", "snapshot", "expiry", "permissions", "choice", "wrong_token"):
            with self.subTest(mutation=mutation):
                browser, now = self.browser(kind="Withdrawal", router=FixedRouter("dispute_intake"))
                browser.act({"action": "message", "text": "Revisar esta transacción"}, now)
                offer = browser.handoff_offer
                payload = {"action": "handoff_decision", "offer_id": offer.offer_id, "prepare": True}
                if mutation == "selection":
                    browser.act({"action": "inquire", "transaction_id": "DEMO-TX-002"}, now)
                elif mutation == "snapshot":
                    entry = browser.records["DEMO-TX-001"]
                    browser.records["DEMO-TX-001"] = replace(entry, record=replace(entry.record, merchant_name="Changed synthetic merchant"))
                elif mutation == "expiry":
                    now = offer.expires_at
                elif mutation == "permissions":
                    browser.session = replace(browser.session, permissions=frozenset({Permission.READ_TRANSACTION}))
                elif mutation == "choice":
                    payload["prepare"] = "yes"
                else:
                    payload["offer_id"] = "different-synthetic-token"
                with self.assertRaises((UiError, AccessDenied)):
                    browser.act(payload, now)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.store.count(), 0)

    def test_ambiguous_assent_keeps_offer_but_does_not_prepare_or_confirm(self):
        browser, now = self.browser(kind="Withdrawal", router=FixedRouter("dispute_intake"))
        browser.act({"action": "message", "text": "Revisar esta transacción"}, now)
        offer = browser.handoff_offer
        browser.router = FixedRouter("unsupported", False)
        browser.act({"action": "message", "text": "confirmo"}, now)
        self.assertIs(browser.handoff_offer, offer)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)
        browser.act({"action": "message", "text": "sí"}, now)
        self.assertEqual(browser.pending_draft.kind, "handoff")
        self.assertEqual(browser.store.count(), 0)

    def test_explicit_previous_case_request_bypasses_dispute_classifier_and_preserves_unverified_issue(self):
        for language, request in (("es", "Quiero retomar una reclamación que ya había abierto para esta operación."),
                                  ("pt", "Quero retomar uma reclamação que já abri para esta operação.")):
            for learned in (False, True):
                with self.subTest(language=language, learned=learned):
                    router = FixedRouter("dispute_intake") if learned else None
                    browser, now = self.browser(language=language, router=router)
                    browser.act({"action": "message", "text": request}, now)
                    self.assertIn("case_unverified", [message["status"] for message in browser.messages])
                    if router is not None:
                        self.assertEqual(router.calls, 0)
                    self.save_handoff(browser, now, request, "existing_case_unverified")

    def test_previous_case_request_replaces_unaccepted_intake_and_malformed_reference_clears_old_offer(self):
        browser, now = self.browser(router=FixedRouter("dispute_intake"))
        browser.act({"action": "message", "text": "Quiero reclamar esta compra"}, now)
        self.assertIsNotNone(browser.intake_offer)
        browser.act({"action": "message", "text": "Quiero retomar mi reclamación anterior"}, now)
        self.assertIsNone(browser.intake_offer)
        self.assertIsNotNone(browser.handoff_offer)
        with self.assertRaises(RoutingError):
            browser.act({"action": "message", "text": "Quiero retomar mi reclamación del 2026-99-99"}, now)
        self.assertIsNone(browser.handoff_offer)
        self.assertIsNone(browser.selected_id)
        self.assertEqual(browser.store.count(), 0)

    def test_previous_case_foreign_transaction_reference_is_still_denied(self):
        browser, now = self.browser(router=FixedRouter("dispute_intake"))
        with self.assertRaises(AccessDenied):
            browser.act({"action": "message", "text": "Quiero retomar mi caso sobre DEMO-TX-003"}, now)
        self.assertIsNone(browser.handoff_offer)
        self.assertIsNone(browser.pending_draft)
        self.assertIsNone(browser.selected_id)
        self.assertEqual(browser.store.count(), 0)

    def test_channel_request_survives_date_and_candidate_choice_and_does_not_leak_into_later_inquiry(self):
        for language, request in (("es", "¿Cuál es el canal de mis pagos?"),
                                  ("pt", "Qual é o canal dos meus pagamentos?")):
            for learned in (False, True):
                with self.subTest(language=language, learned=learned):
                    browser, now = self.browser(language=language, router=FixedRouter("inquiry") if learned else None)
                    browser.act({"action": "message", "text": request}, now)
                    browser.act({"action": "message", "text": "2026-06-16"}, now)
                    self.assertIn("DEMO-TX-001", browser.candidate_ids)
                    browser.act({"action": "choose", "transaction_id": "DEMO-TX-001"}, now)
                    self.assertIn(CHANNEL_LIMITS[language], browser.messages[-1]["text"])
                    self.assertEqual(browser.store.count(), 0)
                    browser.act({"action": "inquire", "transaction_id": "DEMO-TX-002"}, now)
                    self.assertNotIn(CHANNEL_LIMITS[language], browser.messages[-1]["text"])

    def test_direct_inquiry_does_not_reuse_unfinished_channel_request(self):
        browser, now = self.browser(router=FixedRouter("inquiry"))
        browser.act({"action": "message", "text": "Indica el canal de mis pagos"}, now)
        self.assertIsNotNone(browser.pending_search)
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-002"}, now)
        self.assertNotIn(CHANNEL_LIMITS["es"], browser.messages[-1]["text"])


if __name__ == "__main__":
    unittest.main()
