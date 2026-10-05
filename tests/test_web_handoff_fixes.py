"""Real loopback regressions for handoff controls, using isolated demo records."""

from dataclasses import replace
from html.parser import HTMLParser
import http.client
import json
from threading import Thread
import unittest
from unittest.mock import patch

from bank_service.access import Permission
from bank_service.demo_fixtures import demo_session
from bank_service.web_app import DemoServer, _now


class ButtonInventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = {}

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            values = dict(attrs)
            self.buttons[values.get("id")] = values


class WebHandoffFixTests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(0)
        self.addCleanup(self.stop)
        self.thread = Thread(target=self.server.serve_forever,
                             kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.cookie = ""
        self.state = {}
        self.request("GET", "/api/state")

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method, path, payload=None):
        headers = {"Cookie": self.cookie} if self.cookie else {}
        body = None
        if method == "POST":
            headers.update({"Origin": f"http://127.0.0.1:{self.port}",
                            "Content-Type": "application/json"})
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            data = (json.loads(raw) if "application/json" in response.getheader("Content-Type", "")
                    else raw.decode("utf-8"))
            cookie = response.getheader("Set-Cookie")
            if cookie:
                self.cookie = cookie.split(";", 1)[0]
            if isinstance(data, dict) and "messages" in data:
                self.state = data
            return response.status, data
        finally:
            connection.close()

    def post(self, action, **values):
        return self.request("POST", "/api/action", {
            "action": action, "csrf_token": self.state["csrf_token"], **values,
        })

    def browser(self):
        return self.server.get_session(self.cookie.split("=", 1)[1])

    def offer(self, language="es", *, handoff_permission=True):
        if handoff_permission:
            code, _ = self.post("reset")
        else:
            # Mint a genuinely read-only server-owned session, rather than
            # replace the exact identity already bound to its conversation.
            with patch("bank_service.web_app.demo_session", side_effect=lambda now: replace(
                    demo_session(now), permissions=frozenset({Permission.READ_TRANSACTION}))):
                code, _ = self.post("reset")
        self.assertEqual(code, 200)
        self.assertEqual(self.post("language", language=language)[0], 200)
        browser = self.browser()
        entry = browser.records["DEMO-TX-001"]
        browser.records["DEMO-TX-001"] = replace(
            entry, record=replace(entry.record, transaction_type="Withdrawal"))
        self.assertEqual(self.post("inquire", transaction_id="DEMO-TX-001")[0], 200)
        request = "Quiero reclamar esta transacción." if language == "es" else "Quero contestar esta transação."
        code, state = self.post("message", text=request)
        self.assertEqual(code, 200)
        self.assertIsNone(state["intake_offer"])
        self.assertIsNone(state["pending_draft"])
        self.assertEqual(browser.store.count(), 0)
        return request, state

    def test_bilingual_withdrawal_http_journey_requires_preparation_and_verified_confirmation(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                request, state = self.offer(language)
                offer = state["handoff_offer"]
                self.assertIsNotNone(offer)
                self.assertEqual(offer["transaction_id"], "DEMO-TX-001")
                self.assertEqual(state["messages"][-1]["status"], "handoff_offered")
                browser = self.browser()
                code, state = self.post("handoff_decision", offer_id=offer["offer_id"], prepare=True)
                self.assertEqual(code, 200)
                self.assertIsNone(state["handoff_offer"])
                self.assertFalse(state["offers_handoff"])
                draft = state["pending_draft"]
                self.assertEqual(draft["kind"], "handoff")
                packet = draft["packet"]
                self.assertEqual(packet["request"], request)
                self.assertEqual(packet["language"], language)
                self.assertEqual(packet["escalation_reason"], "ineligible_intake")
                self.assertEqual(packet["facts"]["transaction_type"], "Withdrawal")
                self.assertEqual(packet["facts"]["transaction_id"], "DEMO-TX-001")
                self.assertEqual(packet["sources"], state["selected_transaction"]["sources"])
                self.assertEqual(packet["verified_actions"], [])
                self.assertEqual(browser.store.count(), 0)
                self.assertEqual(state["receipts"], [])
                for _ in range(2):
                    code, state = self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                    self.assertEqual(code, 200)
                    self.assertIsNone(state["pending_draft"])
                    self.assertEqual(browser.store.count(), 1)
                    self.assertEqual(len(state["receipts"]), 1)
                receipt = state["receipts"][0]
                self.assertEqual(receipt["kind"], "handoff")
                saved = browser.actions.read_case(browser.session, receipt["case_id"], now=_now())
                saved_packet = json.loads(saved.payload_json)
                self.assertIs(saved_packet["consent"], True)
                self.assertIs(saved_packet["simulated"], True)
                self.assertEqual(saved_packet["request"], request)
                self.assertEqual(state["handoff"]["facts"]["transaction_type"], "Withdrawal")

    def test_http_handoff_preparation_rejects_invalid_choice_token_selection_and_revoked_grant(self):
        for mutation, expected_status, expected_error in (
            ("string_choice", 400, "invalid_confirmation"),
            ("wrong_token", 409, "stale_offer"),
            ("new_selection", 409, "stale_offer"),
            ("revoked_grant", 403, "access_denied"),
        ):
            with self.subTest(mutation=mutation):
                _, offered = self.offer()
                identifier = offered["handoff_offer"]["offer_id"]
                choice = True
                browser = self.browser()
                if mutation == "string_choice":
                    choice = "true"
                elif mutation == "wrong_token":
                    identifier = "different-synthetic-offer"
                elif mutation == "new_selection":
                    self.assertEqual(self.post("inquire", transaction_id="DEMO-TX-002")[0], 200)
                else:
                    browser.session = replace(browser.session, permissions=frozenset({Permission.READ_TRANSACTION}))
                code, state = self.post("handoff_decision", offer_id=identifier, prepare=choice)
                self.assertEqual(code, expected_status)
                self.assertEqual(state["error"]["code"], expected_error)
                self.assertIsNone(state["pending_draft"])
                self.assertEqual(state["receipts"], [])
                self.assertEqual(browser.store.count(), 0)
                if mutation == "new_selection":
                    self.assertEqual(state["selected_transaction"]["transaction_id"], "DEMO-TX-002")

    def test_absent_handoff_grant_returns_explanation_without_an_action_offer(self):
        _, state = self.offer(handoff_permission=False)
        self.assertEqual(state["messages"][-1]["status"], "handoff_unavailable")
        self.assertFalse(state["offers_handoff"])
        self.assertIsNone(state["handoff_offer"])
        self.assertIsNone(state["intake_offer"])
        self.assertIsNone(state["pending_draft"])
        self.assertEqual(self.browser().store.count(), 0)

    def test_http_decline_consumes_offer_without_changing_selection_or_creating_a_case(self):
        _, state = self.offer()
        identifier = state["handoff_offer"]["offer_id"]
        code, state = self.post("handoff_decision", offer_id=identifier, prepare=False)
        self.assertEqual(code, 200)
        self.assertEqual(state["messages"][-1]["status"], "handoff_declined")
        self.assertIsNone(state["handoff_offer"])
        self.assertIsNone(state["pending_draft"])
        self.assertEqual(state["selected_transaction"]["transaction_id"], "DEMO-TX-001")
        self.assertEqual(self.browser().store.count(), 0)
        code, state = self.post("handoff_decision", offer_id=identifier, prepare=True)
        self.assertEqual(code, 409)
        self.assertEqual(state["error"]["code"], "stale_offer")
        self.assertEqual(self.browser().store.count(), 0)

    def test_served_assets_expose_a_decline_control_and_use_the_token_bound_action(self):
        code, document = self.request("GET", "/")
        self.assertEqual(code, 200)
        parser = ButtonInventory()
        parser.feed(document)
        decline = parser.buttons.get("decline-handoff")
        self.assertIsNotNone(decline)
        self.assertEqual(decline["type"], "button")
        self.assertIn("hidden", decline)
        self.assertIn("offer-handoff", parser.buttons)
        code, script = self.request("GET", "/app.js")
        self.assertEqual(code, 200)
        self.assertIn('"decline-handoff"', script)
        self.assertRegex(script, r'action\(["\']handoff_decision["\']')
        self.assertRegex(script, r"offer_id\s*:")


if __name__ == "__main__":
    unittest.main()
