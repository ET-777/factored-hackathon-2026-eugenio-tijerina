"""Real loopback HTTP checks with isolated authored fixtures and temporary cases."""

from dataclasses import replace
from datetime import timedelta
import http.client
import json
from threading import Thread
import unittest
from unittest.mock import patch

from bank_service.access import AccessDenied
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
        return state["pending_draft"]["draft_id"]

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
                self.assertTrue(draft["packet"]["unresolved_questions"])
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
        self.assertEqual(self.browser().store.count(), 0)


if __name__ == "__main__":
    unittest.main()
