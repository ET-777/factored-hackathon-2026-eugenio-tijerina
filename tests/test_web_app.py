"""Real loopback HTTP checks with isolated authored fixtures and temporary cases."""

from dataclasses import replace
from datetime import timedelta
import http.client
import json
from threading import Thread
import unittest
from unittest.mock import patch

from bank_service.access import AccessDenied, Permission
from bank_service.case_store import StoreError
from bank_service.web_app import COOKIE_NAME, DemoServer, _now


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(0)
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.cookie = ""
        self.state = {}
        self.addCleanup(self.stop)
        self.request("GET", "/api/state")

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method, path, *, payload=None, cookie=None, extra_headers=None):
        headers = {}
        browser_cookie = self.cookie if cookie is None else cookie
        if browser_cookie:
            headers["Cookie"] = browser_cookie
        body = None
        if method == "POST":
            headers.update({"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/json"})
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers.update(extra_headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            data = json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw
            new_cookie = response.getheader("Set-Cookie")
            if new_cookie:
                self.cookie = new_cookie.split(";", 1)[0]
            if isinstance(data, dict) and "messages" in data:
                self.state = data
            return response.status, data, dict(response.getheaders())
        finally:
            connection.close()

    def post(self, action, **values):
        return self.request("POST", "/api/action", payload={
            "action": action, "csrf_token": self.state["csrf_token"], **values})

    def browser(self):
        token = self.cookie.split("=", 1)[1]
        return self.server.get_session(token)

    def prepare(self):
        self.post("inquire", transaction_id="DEMO-TX-001")
        code, state, _ = self.post("message", text="No reconozco esta compra")
        self.assertEqual(code, 200)
        self.accept_offer()
        return self.state["pending_draft"]["draft_id"]

    def accept_offer(self):
        self.assertIsNone(self.state["pending_draft"])
        offer = self.state["intake_offer"]
        self.assertIsNotNone(offer)
        before = self.browser().store.count()
        code, state, _ = self.post("intake_decision", offer_id=offer["offer_id"], prepare=True)
        self.assertEqual(code, 200)
        self.assertIsNone(state["intake_offer"])
        self.assertEqual(self.browser().store.count(), before)
        self.assertIsNotNone(state["pending_draft"])
        return state

    def test_session_minted_by_server_and_only_owned_transactions_are_returned(self):
        self.assertTrue(self.state["session"]["active"])
        self.assertEqual([entry["transaction_id"] for entry in self.state["transactions"]],
                         ["DEMO-TX-001", "DEMO-TX-002"])
        self.assertNotIn("Demo Foreign Merchant", json.dumps(self.state))
        _, _, headers = self.request("GET", "/api/state", cookie="")
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_bilingual_search_clarification_ticket_confirmation_and_handoff(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                phrase = "Busca la compra de 25.50 USD" if language == "es" else "Busque a compra de 25,50 USD"
                code, state, _ = self.post("message", text=phrase)
                self.assertEqual(code, 200)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                code, state, _ = self.post("choose", transaction_id="DEMO-TX-001")
                self.assertEqual(state["selected_transaction"]["amount"], "25.50")
                phrase = "No reconozco esta compra" if language == "es" else "Não reconheço esta compra"
                code, state, _ = self.post("message", text=phrase)
                state = self.accept_offer()
                draft = state["pending_draft"]
                self.assertEqual(draft["packet"]["facts"]["amount"], "25.50")
                self.assertEqual(self.browser().store.count(), 0)
                code, state, _ = self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertEqual(code, 200)
                case_id = state["receipts"][0]["case_id"]
                self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertEqual(self.browser().store.count(), 1)
                phrase = "Quiero hablar con una persona" if language == "es" else "Quero falar com uma pessoa"
                code, state, _ = self.post("message", text=phrase)
                draft = state["pending_draft"]
                self.assertEqual(draft["kind"], "handoff")
                self.assertEqual(draft["packet"]["verified_actions"][0]["case_id"], case_id)
                self.assertEqual(draft["packet"]["request"],
                                 "No reconozco esta compra" if language == "es" else "Não reconheço esta compra")
                self.assertEqual(draft["packet"]["unresolved_questions"], [])
                self.assertEqual(self.browser().store.count(), 1)
                code, state, _ = self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertEqual(self.browser().store.count(), 2)
                self.assertIs(state["handoff"]["simulated"], True)
                self.assertEqual(state["handoff"]["language"], language)

    def test_dispute_search_remembers_intent_until_customer_selects_a_match(self):
        code, state, _ = self.post("message", text="No reconozco la compra de 25.50 USD")
        self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
        self.assertIsNone(state["pending_draft"])
        code, state, _ = self.post("choose", transaction_id="DEMO-TX-002")
        self.assertEqual(state["intake_offer"]["transaction_id"], "DEMO-TX-002")
        state = self.accept_offer()
        self.assertEqual(state["pending_draft"]["kind"], "intake")
        self.assertEqual(state["pending_draft"]["packet"]["facts"]["transaction_id"], "DEMO-TX-002")
        self.assertEqual(self.browser().store.count(), 0)

    def test_typed_confirmation_never_mutates_and_cancel_cannot_be_reused(self):
        identifier = self.prepare()
        self.post("message", text="sí, confirmo")
        self.assertEqual(self.browser().store.count(), 0)
        self.post("cancel", draft_id=identifier)
        code, state, _ = self.post("confirm", draft_id=identifier, confirmed=True)
        self.assertEqual(code, 409)
        self.assertEqual(self.browser().store.count(), 0)

    def test_new_browser_cannot_read_another_browsers_ticket_even_with_same_demo_customer(self):
        identifier = self.prepare()
        _, first, _ = self.post("confirm", draft_id=identifier, confirmed=True)
        case_id = first["receipts"][0]["case_id"]
        self.request("GET", "/api/state", cookie="")
        code, state, _ = self.post("view_case", case_id=case_id)
        self.assertEqual(code, 403)
        self.assertEqual(state["receipts"], [])

    def test_foreign_or_missing_transactions_have_same_safe_error(self):
        replies = []
        for identifier in ("DEMO-TX-003", "DEMO-NOT-FOUND"):
            code, state, _ = self.post("inquire", transaction_id=identifier)
            replies.append((code, state["error"]))
            self.assertIsNone(state["selected_transaction"])
            self.assertNotIn("Demo Foreign Merchant", json.dumps(state))
        self.assertEqual(replies[0], replies[1])

    def test_expiry_hides_facts_and_requires_explicit_fresh_demo(self):
        browser = self.browser()
        with patch("bank_service.web_app._now", return_value=browser.session.expires_at):
            code, state, _ = self.request("GET", "/api/state")
            self.assertFalse(state["session"]["active"])
            self.assertEqual(state["transactions"], [])
            self.assertEqual(state["receipts"], [])
            code, _, _ = self.post("inquire", transaction_id="DEMO-TX-001")
            self.assertEqual(code, 403)
            code, state, _ = self.post("reset")
            self.assertEqual(code, 200)
            self.assertTrue(state["session"]["active"])
        self.assertIsNot(self.browser(), browser)

    def test_uncertain_committed_write_retains_same_draft_and_reconciles_one_case(self):
        identifier = self.prepare()
        browser = self.browser()
        original = browser.store.read_by_key

        def fail_readback(key):
            if browser.store.count():
                raise StoreError("synthetic_failure")
            return original(key)

        with patch.object(browser.store, "read_by_key", side_effect=fail_readback):
            code, state, _ = self.post("confirm", draft_id=identifier, confirmed=True)
            self.assertEqual(code, 409)
            self.assertEqual(state["error"]["code"], "unknown_outcome")
            self.assertEqual(state["pending_draft"]["draft_id"], identifier)
            self.assertTrue(state["pending_draft"]["outcome_unverified"])
            self.assertEqual(state["receipts"], [])
        self.assertEqual(browser.store.count(), 1)
        self.assertTrue(self.request("GET", "/api/state")[1]["pending_draft"]["outcome_unverified"])
        code, state, _ = self.post("confirm", draft_id=identifier, confirmed=True)
        self.assertEqual(code, 200)
        self.assertEqual(browser.store.count(), 1)
        self.assertEqual(len(state["receipts"]), 1)

    def test_language_change_cancels_old_draft_and_only_explicit_buttons_confirm(self):
        identifier = self.prepare()
        self.post("language", language="pt")
        self.assertIsNone(self.state["pending_draft"])
        self.assertEqual(self.state["language"], "pt")
        code, _, _ = self.post("confirm", draft_id=identifier, confirmed=True)
        self.assertEqual(code, 409)
        self.assertEqual(self.browser().store.count(), 0)

    def test_unverified_marker_survives_unavailable_state_with_an_earlier_receipt(self):
        first = self.prepare()
        self.post("confirm", draft_id=first, confirmed=True)
        pending = self.prepare()
        browser = self.browser()
        original = browser.store.read_by_key

        def fail_new_readback(key):
            if browser.store.count() == 2:
                raise StoreError("synthetic_failure")
            return original(key)

        with patch.object(browser.store, "read_by_key", side_effect=fail_new_readback), \
                patch.object(browser.store, "read_case", side_effect=StoreError("synthetic_failure")):
            code, state, _ = self.post("confirm", draft_id=pending, confirmed=True)
            self.assertEqual(code, 409)
            self.assertTrue(state["error"]["outcome_unverified"])
            self.assertNotIn("messages", state)
            self.assertTrue(browser.outcome_unverified)
            self.assertEqual(browser.pending_draft.draft_id, pending)
        code, state, _ = self.post("confirm", draft_id=pending, confirmed=True)
        self.assertEqual(code, 200)
        self.assertEqual(browser.store.count(), 2)
        self.assertEqual(len(state["receipts"]), 2)

    def test_authorized_exact_draft_review_is_read_only_and_session_bound(self):
        identifier = self.prepare()
        browser = self.browser()
        packet = json.loads(browser.actions.review_draft(browser.session, identifier, now=_now()))
        self.assertEqual(packet["transaction_id"], "DEMO-TX-001")
        self.assertIs(packet["consent"], False)
        self.assertEqual(browser.store.count(), 0)
        with self.assertRaises(AccessDenied):
            browser.actions.review_draft(replace(browser.session), identifier, now=_now())

    def test_unsupported_handoff_offer_preserves_original_request_without_writing(self):
        request = "Quiero un préstamo para estudiar"
        code, state, _ = self.post("message", text=request)
        self.assertEqual(code, 200)
        self.assertTrue(state["offers_handoff"])
        self.assertEqual(state["handoff_request"], request)
        code, state, _ = self.post("prepare_handoff", request=state["handoff_request"])
        self.assertEqual(code, 200)
        self.assertEqual(state["pending_draft"]["packet"]["request"], request)
        self.assertIn(request, state["pending_draft"]["packet"]["unresolved_questions"])
        self.assertEqual(state["pending_draft"]["packet"]["escalation_reason"], "unsupported_request")
        self.assertEqual(self.browser().store.count(), 0)

    def test_bilingual_dispute_collects_currency_and_amount_without_losing_original_reason(self):
        for language, request, currency, amount in (
            ("es", "No reconozco un cargo", "dólares", "25.5"),
            ("pt", "Não reconheço uma cobrança", "dólares", "25,50"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                self.post("message", text=request)
                code, state, _ = self.post("message", text=currency)
                self.assertEqual(code, 200)
                self.assertFalse(state["offers_handoff"])
                self.assertEqual(state["candidate_ids"], [])
                self.assertIn("USD", state["messages"][-2]["text"])
                self.assertEqual(state["messages"][-2]["status"], "currency_interpretation")
                code, state, _ = self.post("message", text=amount)
                self.assertEqual(code, 200)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.assertIsNone(state["pending_draft"])
                code, state, _ = self.post("choose", transaction_id="DEMO-TX-002")
                state = self.accept_offer()
                packet = state["pending_draft"]["packet"]
                self.assertEqual(packet["request"], request)
                self.assertEqual(packet["facts"]["transaction_id"], "DEMO-TX-002")
                self.assertEqual(packet["facts"]["amount"], "25.50")
                self.assertEqual(self.browser().store.count(), 0)

    def test_natural_plural_inquiry_and_dollar_followups_match_exact_amounts(self):
        for language, inquiry, wrong, corrected in (
            ("es", "Enséñame mis pagos", "25 dolares", "25,5 dolares"),
            ("pt", "Mostre meus pagamentos", "25 dólares", "25,5 dólares"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                code, state, _ = self.post("message", text=inquiry)
                self.assertEqual(state["messages"][-1]["status"], "needs_filters")
                self.assertFalse(state["offers_handoff"])
                code, state, _ = self.post("message", text=wrong)
                self.assertEqual(state["messages"][-1]["status"], "no_match")
                self.assertEqual(state["candidate_ids"], [])
                code, state, _ = self.post("message", text=corrected)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.post("choose", transaction_id="DEMO-TX-001")
                self.assertIsNone(self.state["pending_draft"])
                self.assertEqual(self.browser().store.count(), 0)

    def test_amount_first_and_ambiguous_pesos_or_symbol_require_explicit_currency(self):
        for fragment in ("25.5", "25,50 pesos", "$25.50"):
            with self.subTest(fragment=fragment):
                self.post("reset")
                self.post("message", text="No reconozco un cargo")
                code, state, _ = self.post("message", text=fragment)
                self.assertEqual(state["messages"][-1]["status"], "needs_currency")
                self.assertEqual(state["candidate_ids"], [])
                self.assertIsNone(state["pending_draft"])
                code, state, _ = self.post("message", text="USD")
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.assertIsNone(state["pending_draft"])
        self.post("reset")
        self.post("message", text="No reconozco un cargo")
        self.post("message", text="USD")
        self.post("message", text="$25.50")
        self.assertEqual(self.state["candidate_ids"], [])
        self.assertEqual(self.state["messages"][-1]["status"], "needs_currency")

    def test_unsupported_currency_and_pesos_keep_search_without_generic_handoff(self):
        self.post("message", text="No reconozco un cargo")
        for fragment in ("BRL", "pesos"):
            code, state, _ = self.post("message", text=fragment)
            self.assertEqual(code, 200)
            self.assertEqual(state["messages"][-1]["status"], "needs_currency")
            self.assertFalse(state["offers_handoff"])
            self.assertIsNone(state["selected_transaction"])
        self.post("message", text="USD")
        self.post("message", text="25.50")
        self.post("choose", transaction_id="DEMO-TX-002")
        self.accept_offer()
        self.assertEqual(self.state["pending_draft"]["packet"]["request"], "No reconozco un cargo")

    def test_new_broad_request_clears_old_selection_but_explicit_reference_can_reuse_it(self):
        self.post("inquire", transaction_id="DEMO-TX-001")
        self.post("message", text="No reconozco un cargo")
        self.assertIsNone(self.state["selected_transaction"])
        self.assertIsNone(self.state["pending_draft"])
        self.post("message", text="25.50 USD")
        self.post("choose", transaction_id="DEMO-TX-002")
        self.accept_offer()
        identifier = self.state["pending_draft"]["draft_id"]
        self.assertEqual(self.state["pending_draft"]["packet"]["facts"]["transaction_id"], "DEMO-TX-002")
        self.post("cancel", draft_id=identifier)
        self.post("message", text="No reconozco esta compra")
        self.accept_offer()
        self.assertEqual(self.state["pending_draft"]["packet"]["facts"]["transaction_id"], "DEMO-TX-002")

    def test_explicit_new_inquiry_and_unsupported_action_supersede_pending_dispute(self):
        self.post("message", text="No reconozco un cargo")
        self.post("message", text="Enséñame mis pagos de 25.50 USD")
        self.post("choose", transaction_id="DEMO-TX-001")
        self.assertIsNone(self.state["pending_draft"])
        self.post("message", text="No reconozco un cargo de 25.50 USD")
        self.post("message", text="Quiero transferir 25.50 USD")
        self.assertTrue(self.state["offers_handoff"])
        self.assertEqual(self.state["candidate_ids"], [])
        self.assertIsNone(self.state["selected_transaction"])
        self.assertIsNone(self.state["pending_draft"])
        self.post("message", text="25.50 USD")
        self.post("choose", transaction_id="DEMO-TX-002")
        self.assertIsNone(self.state["pending_draft"])
        self.assertEqual(self.browser().store.count(), 0)

    def test_foreign_or_invalid_followup_cannot_attach_an_old_transaction(self):
        for fragment, expected in (("DEMO-TX-003", 403), ("USD 1,000", 400)):
            with self.subTest(fragment=fragment):
                self.post("reset")
                self.post("inquire", transaction_id="DEMO-TX-001")
                self.post("message", text="No reconozco un cargo")
                code, state, _ = self.post("message", text=fragment)
                self.assertEqual(code, expected)
                self.assertIsNone(state["selected_transaction"])
                self.assertEqual(state["candidate_ids"], [])
                self.assertIsNone(state["pending_draft"])
                code, state, _ = self.post("prepare_intake", reason="No reconozco el cargo")
                self.assertEqual(state["error"]["code"], "transaction_required")
                self.assertEqual(self.browser().store.count(), 0)

    def test_handoff_summary_preserves_issue_and_distinct_steps_without_repeating_human_request(self):
        request = "No reconozco un cargo"
        human = "Quiero hablar con una persona"
        self.post("message", text=request)
        self.post("message", text="USD")
        self.post("message", text="25")
        self.post("message", text="25.50")
        self.post("choose", transaction_id="DEMO-TX-001")
        self.accept_offer()
        self.post("confirm", draft_id=self.state["pending_draft"]["draft_id"], confirmed=True)
        case_id = self.state["receipts"][0]["case_id"]
        self.post("message", text=human)
        packet = self.state["pending_draft"]["packet"]
        self.assertEqual(packet["request"], request)
        self.assertEqual(packet["unresolved_questions"], [])
        self.assertEqual(len(packet["attempted_steps"]), len(set(packet["attempted_steps"])))
        self.assertEqual(packet["verified_actions"][0]["case_id"], case_id)
        self.assertEqual(self.browser().store.count(), 1)
        self.post("confirm", draft_id=self.state["pending_draft"]["draft_id"], confirmed=True)
        self.assertEqual(self.state["handoff"]["request"], request)
        self.assertEqual(self.state["handoff"]["unresolved_questions"], [])
        self.post("reset")
        self.post("message", text=human)
        self.assertIsNone(self.state["pending_draft"])
        self.assertEqual(self.state["messages"][-1]["status"], "needs_handoff_context")
        self.post("message", text="Necesito ayuda para recuperar el acceso a mi cuenta")
        self.assertEqual(self.state["pending_draft"]["packet"]["request"],
                         "Necesito ayuda para recuperar el acceso a mi cuenta")
        self.assertEqual(self.state["pending_draft"]["packet"]["unresolved_questions"], [])
        self.assertIsNone(self.state["pending_draft"]["packet"]["facts"])

    def test_human_request_interrupts_slot_collection_and_typed_assent_never_prepares_or_writes(self):
        self.post("message", text="No reconozco un cargo")
        self.post("message", text="25.50")
        self.post("message", text="sí, confirmo")
        self.assertIsNone(self.state["pending_draft"])
        self.assertEqual(self.browser().store.count(), 0)
        self.post("message", text="Quiero hablar con una persona")
        self.assertEqual(self.state["pending_draft"]["kind"], "handoff")
        self.assertEqual(self.state["pending_draft"]["packet"]["request"], "No reconozco un cargo")
        self.assertEqual(self.state["pending_draft"]["packet"]["unresolved_questions"], [])
        self.assertIsNone(self.state["pending_draft"]["packet"]["facts"])
        self.post("message", text="confirmo")
        self.assertEqual(self.browser().store.count(), 0)

    def test_language_reset_and_second_browser_clear_unfinished_slot_context(self):
        self.post("message", text="No reconozco un cargo")
        self.post("message", text="25.50")
        self.post("language", language="pt")
        self.post("message", text="USD")
        self.assertEqual(self.state["candidate_ids"], [])
        self.assertIsNone(self.state["pending_draft"])
        self.post("message", text="25,50")
        self.post("choose", transaction_id="DEMO-TX-001")
        self.assertIsNone(self.state["pending_draft"])
        self.post("reset")
        self.post("message", text="USD")
        self.assertEqual(self.state["candidate_ids"], [])
        self.post("message", text="25.50")
        self.request("GET", "/api/state", cookie="")
        self.post("message", text="USD")
        self.assertEqual(self.state["candidate_ids"], [])
        self.assertEqual(self.browser().store.count(), 0)

    def test_rejected_choice_cannot_attach_old_transaction_to_handoff(self):
        self.post("inquire", transaction_id="DEMO-TX-001")
        code, state, _ = self.post("choose", transaction_id="DEMO-NOT-FOUND")
        self.assertEqual(code, 400)
        self.assertIsNone(state["selected_transaction"])
        self.post("message", text="Quiero hablar con una persona")
        self.assertIsNone(self.state["pending_draft"])
        self.post("message", text="Necesito ayuda para recuperar el acceso a mi cuenta")
        self.assertIsNone(self.state["pending_draft"]["packet"]["facts"])
        self.assertEqual(self.state["pending_draft"]["packet"]["unresolved_questions"], [])

    def test_rejected_currency_discards_old_amount_and_allows_date_only_correction(self):
        for corrected in ("USD", "2026-06-16"):
            with self.subTest(corrected=corrected):
                self.post("reset")
                self.post("message", text="No reconozco un cargo de 25.50 USD")
                self.post("message", text="30 BRL")
                code, state, _ = self.post("message", text=corrected)
                self.assertEqual(code, 200)
                if corrected == "USD":
                    self.assertEqual(state["candidate_ids"], [])
                    self.assertIsNone(state["pending_draft"])
                else:
                    self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.assertEqual(self.browser().store.count(), 0)

    def test_all_supported_currencies_are_valid_searches_and_absent_matches_do_not_convert(self):
        for language in ("es", "pt"):
            for currency in ("MXN", "COP", "ARS", "USD"):
                with self.subTest(language=language, currency=currency):
                    self.post("reset")
                    self.post("language", language=language)
                    request = "No reconozco un cargo" if language == "es" else "Não reconheço uma cobrança"
                    self.post("message", text=request)
                    code, state, _ = self.post("message", text=currency)
                    self.assertEqual(code, 200)
                    self.assertEqual(state["messages"][-1]["status"], "needs_filters")
                    self.assertFalse(state["offers_handoff"])
                    code, state, _ = self.post("message", text="25,50")
                    self.assertEqual(code, 200)
                    expected = "ambiguous" if currency == "USD" else "no_match"
                    self.assertEqual(state["messages"][-1]["status"], expected)
                    self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"] if currency == "USD" else [])
                    self.assertIsNone(state["selected_transaction"])
                    self.assertIsNone(state["pending_draft"])
                    self.assertEqual(self.browser().store.count(), 0)

    def test_pesos_requires_code_and_explicit_mxn_keeps_dispute_context_without_usd_match(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                request = "No reconozco un cargo" if language == "es" else "Não reconheço uma cobrança"
                self.post("message", text=request)
                self.post("message", text="25,50 pesos")
                self.assertEqual(self.state["messages"][-1]["status"], "needs_currency")
                self.assertIn("MXN", self.state["messages"][-1]["text"])
                self.post("message", text="25,50 pesos MXN")
                self.assertEqual(self.state["messages"][-1]["status"], "no_match")
                self.assertEqual(self.state["candidate_ids"], [])
                self.assertIsNone(self.state["pending_draft"])
                self.assertFalse(self.state["offers_handoff"])
                self.post("message", text="USD")
                self.post("choose", transaction_id="DEMO-TX-002")
                self.accept_offer()
                self.assertEqual(self.state["pending_draft"]["packet"]["request"], request)
                self.assertEqual(self.state["pending_draft"]["packet"]["facts"]["currency"], "USD")
                self.assertEqual(self.browser().store.count(), 0)

    def test_structured_mxn_search_is_valid_and_has_no_usd_fallback(self):
        self.post("inquire", transaction_id="DEMO-TX-001")
        code, state, _ = self.post("search", amount="25.50", currency="MXN")
        self.assertEqual(code, 200)
        self.assertEqual(state["messages"][-1]["status"], "no_match")
        self.assertEqual(state["candidate_ids"], [])
        self.assertIsNone(state["selected_transaction"])
        self.assertIsNone(state["pending_draft"])
        self.assertEqual(self.browser().store.count(), 0)

    def test_short_prefixed_and_invalid_numeric_followups_preserve_dispute_intent(self):
        for language, request, followup in (
            ("es", "No reconozco un cargo", "Son 25.5 dólares"),
            ("pt", "Não reconheço uma cobrança", "São 25,50 dólares"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                self.post("message", text=request)
                code, state, _ = self.post("message", text="NaN")
                self.assertEqual(code, 400)
                self.assertIsNone(state["selected_transaction"])
                self.post("message", text=followup)
                self.post("choose", transaction_id="DEMO-TX-002")
                self.accept_offer()
                self.assertEqual(self.state["pending_draft"]["kind"], "intake")
                self.assertEqual(self.state["pending_draft"]["packet"]["request"], request)
                self.assertEqual(self.browser().store.count(), 0)

    def test_bilingual_preparation_agreement_is_separate_from_final_submission(self):
        for language, request, yes in (
            ("es", "No reconozco DEMO-TX-001", "Sí, por favor"),
            ("pt", "Não reconheço DEMO-TX-001", "Sim, por favor"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                code, state, _ = self.post("message", text=request)
                self.assertEqual(code, 200)
                self.assertEqual(state["messages"][-1]["status"], "intake_offered")
                self.assertEqual(state["intake_offer"]["transaction_id"], "DEMO-TX-001")
                self.assertIsNone(state["pending_draft"])
                self.assertEqual(self.browser().store.count(), 0)
                _, state, _ = self.post("message", text=yes)
                draft = state["pending_draft"]
                self.assertEqual(draft["packet"]["request"], request)
                self.assertIn("panel lateral" if language == "es" else "painel lateral", state["messages"][-1]["text"])
                proposed = json.loads(self.browser().actions.review_draft(
                    self.browser().session, draft["draft_id"], now=_now()))
                self.assertIs(proposed["consent"], False)
                self.post("message", text=yes)
                self.assertEqual(self.state["messages"][-1]["status"], "confirmation_required")
                self.assertEqual(self.browser().store.count(), 0)
                self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertEqual(self.browser().store.count(), 1)

    def test_declining_an_offer_by_text_or_button_creates_nothing(self):
        for language, request, no in (
            ("es", "No reconozco DEMO-TX-001", "No, gracias"),
            ("pt", "Não reconheço DEMO-TX-001", "Não, obrigado"),
        ):
            for button in (False, True):
                with self.subTest(language=language, button=button):
                    self.post("reset")
                    self.post("language", language=language)
                    self.post("message", text=request)
                    identifier = self.state["intake_offer"]["offer_id"]
                    if button:
                        self.post("intake_decision", offer_id=identifier, prepare=False)
                    else:
                        self.post("message", text=no)
                    self.assertEqual(self.state["messages"][-1]["status"], "intake_declined")
                    self.assertIsNone(self.state["pending_draft"])
                    self.assertIsNone(self.state["intake_offer"])
                    self.assertEqual(self.browser().store.count(), 0)
                    code, _, _ = self.post("intake_decision", offer_id=identifier, prepare=True)
                    self.assertEqual(code, 409)

    def test_offer_tokens_and_decision_types_cannot_override_server_authority(self):
        self.post("message", text="No reconozco DEMO-TX-001")
        identifier = self.state["intake_offer"]["offer_id"]
        for invalid in ("true", 1, None, [], {}):
            code, _, _ = self.post("intake_decision", offer_id=identifier, prepare=invalid)
            self.assertEqual(code, 400)
            self.assertIsNone(self.state["pending_draft"])
        code, _, _ = self.post("intake_decision", offer_id="missing", prepare=True)
        self.assertEqual(code, 409)
        code, _, _ = self.post("intake_decision", offer_id=identifier, prepare=True, transaction_id="DEMO-TX-002")
        self.assertEqual(code, 400)
        self.accept_offer()
        draft = self.state["pending_draft"]["draft_id"]
        code, _, _ = self.post("intake_decision", offer_id=identifier, prepare=True)
        self.assertEqual(code, 409)
        self.assertEqual(self.state["pending_draft"]["draft_id"], draft)
        self.assertEqual(self.browser().store.count(), 0)
        self.request("GET", "/api/state", cookie="")
        code, _, _ = self.post("intake_decision", offer_id=identifier, prepare=True)
        self.assertEqual(code, 409)
        self.assertIsNone(self.state["pending_draft"])

    def test_navigation_and_new_requests_invalidate_preparation_offer(self):
        for action, values in (
            ("inquire", {"transaction_id": "DEMO-TX-002"}),
            ("search", {"amount": "25.50", "currency": "USD"}),
            ("choose", {"transaction_id": "DEMO-NOT-FOUND"}),
            ("language", {"language": "pt"}),
            ("message", {"text": "Quiero consultar mis pagos"}),
            ("message", {"text": "Quiero hablar con una persona"}),
            ("message", {"text": "Quiero hacer una transaccion"}),
            ("reset", {}),
        ):
            with self.subTest(action=action, values=values):
                self.post("reset")
                self.post("message", text="No reconozco DEMO-TX-001")
                identifier = self.state["intake_offer"]["offer_id"]
                self.post(action, **values)
                self.assertIsNone(self.state["intake_offer"])
                code, _, _ = self.post("intake_decision", offer_id=identifier, prepare=True)
                self.assertEqual(code, 409)
                self.assertEqual(self.browser().store.count(), 0)

    def test_offer_expiry_snapshot_and_permissions_are_rechecked(self):
        for change in ("expiry", "session_expiry", "snapshot", "owner", "permission"):
            with self.subTest(change=change):
                self.post("reset")
                self.post("message", text="No reconozco DEMO-TX-001")
                identifier = self.state["intake_offer"]["offer_id"]
                browser = self.browser()
                offer = browser.intake_offer
                instant = _now()
                expected = 409
                if change == "expiry":
                    instant = offer.expires_at
                elif change == "session_expiry":
                    instant = browser.session.expires_at
                    expected = 403
                elif change in ("snapshot", "owner"):
                    entry = browser.records["DEMO-TX-001"]
                    record = replace(entry.record, merchant_name="Changed") if change == "snapshot" else replace(entry.record, customer_id="OTHER")
                    browser.records["DEMO-TX-001"] = replace(entry, record=record)
                    if change == "owner": expected = 403
                else:
                    browser.session = replace(browser.session, permissions=frozenset({Permission.READ_TRANSACTION}))
                    expected = 403
                with patch("bank_service.web_app._now", return_value=instant):
                    code, _, _ = self.post("intake_decision", offer_id=identifier, prepare=True)
                self.assertEqual(code, expected)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.store.count(), 0)

    def test_ambiguous_offer_reply_never_accepts_a_new_action_request(self):
        self.post("message", text="No reconozco DEMO-TX-001")
        identifier = self.state["intake_offer"]["offer_id"]
        self.post("message", text="confirmo")
        self.assertEqual(self.state["intake_offer"]["offer_id"], identifier)
        self.assertIsNone(self.state["pending_draft"])
        self.post("message", text="sí, quiero transferir 25 USD")
        self.assertIsNone(self.state["intake_offer"])
        self.assertIsNone(self.state["pending_draft"])
        self.assertTrue(self.state["offers_handoff"])
        self.assertEqual(self.browser().store.count(), 0)

    def test_broad_search_prompt_collects_details_and_making_a_payment_is_unsupported(self):
        for language, search, make in (
            ("es", "Quiero consultar una compra", "Quiero hacer una transaccion"),
            ("pt", "Quero consultar uma compra", "Quero fazer uma transação"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                self.post("message", text=search)
                self.assertEqual(self.state["messages"][-1]["status"], "needs_filters")
                self.assertEqual(self.state["candidate_ids"], [])
                self.assertIsNone(self.state["selected_transaction"])
                self.post("message", text=make)
                self.assertEqual(self.state["messages"][-1]["status"], "unsupported")
                self.assertTrue(self.state["offers_handoff"])
                self.assertEqual(self.state["candidate_ids"], [])
                self.assertIsNone(self.state["pending_draft"])
                self.assertEqual(self.browser().store.count(), 0)

    def test_contextual_dispute_shortcut_requires_a_current_selection(self):
        for identifier in ("DEMO-TX-001", "DEMO-TX-003", "DEMO-NOT-FOUND"):
            code, state, _ = self.post("dispute_selected", transaction_id=identifier)
            self.assertEqual(code, 409)
            self.assertEqual(state["error"]["code"], "selection_changed")
            self.assertIsNone(state["selected_transaction"])
            self.assertIsNone(state["intake_offer"])
            self.assertIsNone(state["pending_draft"])
        self.assertEqual(len(self.state["messages"]), 1)
        self.post("message", text="No reconozco un cargo")
        self.assertEqual(self.state["messages"][-1]["status"], "needs_filters")
        self.assertEqual(self.browser().store.count(), 0)

    def test_bilingual_shortcut_binds_to_latest_selected_record_and_only_offers_preparation(self):
        for language, request in (("es", "No reconozco esta compra"), ("pt", "Não reconheço esta compra")):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                self.post("inquire", transaction_id="DEMO-TX-001")
                self.post("inquire", transaction_id="DEMO-TX-002")
                code, state, _ = self.post("dispute_selected", transaction_id="DEMO-TX-002")
                self.assertEqual(code, 200)
                self.assertEqual(state["selected_transaction"]["transaction_id"], "DEMO-TX-002")
                self.assertEqual(state["intake_offer"]["transaction_id"], "DEMO-TX-002")
                self.assertIsNone(state["pending_draft"])
                self.assertEqual([item["text"] for item in state["messages"] if item["role"] == "user"], [request])
                self.accept_offer()
                self.assertEqual(self.state["pending_draft"]["packet"]["facts"]["transaction_id"], "DEMO-TX-002")
                self.assertEqual(self.state["pending_draft"]["packet"]["request"], request)
                self.assertEqual(self.browser().store.count(), 0)

    def test_stale_shortcut_cannot_replace_current_offer_or_draft(self):
        self.post("inquire", transaction_id="DEMO-TX-001")
        self.post("inquire", transaction_id="DEMO-TX-002")
        before = list(self.state["messages"])
        code, state, _ = self.post("dispute_selected", transaction_id="DEMO-TX-001")
        self.assertEqual(code, 409)
        self.assertEqual(state["messages"], before)
        self.assertEqual(state["selected_transaction"]["transaction_id"], "DEMO-TX-002")
        self.assertIsNone(state["intake_offer"])
        self.post("dispute_selected", transaction_id="DEMO-TX-002")
        offer = self.state["intake_offer"]
        before = list(self.state["messages"])
        code, state, _ = self.post("dispute_selected", transaction_id="DEMO-TX-001")
        self.assertEqual(code, 409)
        self.assertEqual(state["intake_offer"], offer)
        self.assertEqual(state["messages"], before)
        self.accept_offer()
        draft = self.state["pending_draft"]["draft_id"]
        code, state, _ = self.post("dispute_selected", transaction_id="DEMO-TX-001")
        self.assertEqual(code, 409)
        self.assertEqual(state["pending_draft"]["draft_id"], draft)
        self.assertEqual(self.browser().store.count(), 0)

    def test_shortcut_cannot_reuse_selection_after_search_reset_or_in_another_browser(self):
        for action, values in (
            ("message", {"text": "Quiero consultar una compra"}),
            ("search", {"amount": "25.50", "currency": "USD"}),
            ("inquire", {"transaction_id": "DEMO-NOT-FOUND"}),
            ("reset", {}),
        ):
            with self.subTest(action=action):
                self.post("reset")
                self.post("inquire", transaction_id="DEMO-TX-001")
                self.post(action, **values)
                code, state, _ = self.post("dispute_selected", transaction_id="DEMO-TX-001")
                self.assertEqual(code, 409)
                self.assertIsNone(state["intake_offer"])
                self.assertIsNone(state["pending_draft"])
                self.assertEqual(self.browser().store.count(), 0)
        self.post("inquire", transaction_id="DEMO-TX-001")
        self.request("GET", "/api/state", cookie="")
        code, _, _ = self.post("dispute_selected", transaction_id="DEMO-TX-001")
        self.assertEqual(code, 409)
        self.assertEqual(self.browser().store.count(), 0)

    def test_shortcut_checks_fresh_owner_and_does_not_accept_browser_reason(self):
        self.post("inquire", transaction_id="DEMO-TX-001")
        code, state, _ = self.post("dispute_selected", transaction_id="DEMO-TX-001", reason="Injected reason")
        self.assertEqual(code, 400)
        self.assertIsNone(self.state["intake_offer"])
        browser = self.browser()
        entry = browser.records["DEMO-TX-001"]
        browser.records["DEMO-TX-001"] = replace(entry, record=replace(entry.record, customer_id="OTHER"))
        before = list(browser.messages)
        code, state, _ = self.post("dispute_selected", transaction_id="DEMO-TX-001")
        self.assertEqual(code, 403)
        self.assertEqual(state["error"]["code"], "access_denied")
        self.assertEqual(browser.messages, before)
        self.assertIsNone(browser.intake_offer)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)


if __name__ == "__main__":
    unittest.main()
