"""Isolated HTTP regressions for plain inquiries with the fixed TRAIN router.

The transactions below are independently authored demo fixtures. These checks
exercise the shared workflow, without requiring a particular raw prediction or
reading development, final evaluation, or private source records.
"""

import http.client
import json
from threading import Thread
import unittest

from bank_service.route_loader import load_preview_router
from bank_service.web_app import DemoServer


class WebPlainInquiryTests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(0, router=load_preview_router())
        self.thread = Thread(target=self.server.serve_forever,
                             kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
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
            data = json.loads(response.read())
            cookie = response.getheader("Set-Cookie")
            if cookie:
                self.cookie = cookie.split(";", 1)[0]
            if isinstance(data, dict) and "messages" in data:
                self.state = data
            return response.status, data
        finally:
            connection.close()

    def post(self, action, **values):
        code, state = self.request("POST", "/api/action", {
            "action": action, "csrf_token": self.state["csrf_token"], **values,
        })
        self.assertEqual(code, 200, state.get("error"))
        return state

    def browser(self):
        return self.server.get_session(self.cookie.split("=", 1)[1])

    def assert_read_only(self, state):
        self.assertIsNone(state["pending_draft"])
        self.assertIsNone(state["intake_offer"])
        self.assertIsNone(state["handoff_offer"])
        self.assertFalse(state["offers_handoff"])
        self.assertEqual(state["receipts"], [])
        self.assertEqual(self.browser().store.count(), 0)

    def test_greeting_then_plain_payment_inquiry_collects_details_and_returns_grounded_record(self):
        for language, greeting, request in (
            ("es", "Hola", "ver un pago"),
            ("pt", "Ol\u00e1", "ver um pagamento"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                state = self.post("message", text=greeting)
                self.assertEqual(state["messages"][-1]["status"], "greeting")
                state = self.post("message", text=request)
                self.assertEqual(state["route_mode"], "learned_preview")
                self.assertEqual(state["messages"][-1]["status"], "needs_filters")
                self.assertEqual(self.browser().pending_search.kind, "inquiry")
                self.assertEqual(self.browser().pending_search.request, request)
                self.assert_read_only(state)
                state = self.post("message", text="USD")
                self.assertEqual(state["candidate_ids"], [])
                self.assert_read_only(state)
                state = self.post("message", text="25.50")
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.assert_read_only(state)
                state = self.post("choose", transaction_id="DEMO-TX-002")
                self.assertEqual(state["messages"][-1]["status"], "answered")
                selected = state["selected_transaction"]
                self.assertEqual(selected["transaction_id"], "DEMO-TX-002")
                self.assertEqual(selected["amount"], "25.50")
                self.assertEqual(selected["currency"], "USD")
                self.assertEqual(selected["merchant_name"], "Demo Cafe Luna")
                self.assertTrue(selected["sources"])
                self.assertTrue(all(source["file"] == "synthetic/demo_fixtures"
                                    for source in selected["sources"]))
                self.assert_read_only(state)

    def test_new_plain_inquiry_replaces_an_unfinished_dispute_search(self):
        for language, dispute, inquiry in (
            ("es", "No reconozco un cargo", "ver un pago"),
            ("pt", "N\u00e3o reconhe\u00e7o uma compra", "ver um pagamento"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                self.post("message", text=dispute)
                self.assertEqual(self.browser().pending_search.kind, "intake")
                state = self.post("message", text=inquiry)
                self.assertEqual(state["messages"][-1]["status"], "needs_filters")
                self.assertEqual(self.browser().pending_search.kind, "inquiry")
                self.assertEqual(self.browser().pending_search.request, inquiry)
                self.assertIsNone(self.browser().business_issue)
                self.assert_read_only(state)

    def test_new_plain_inquiry_replaces_unaccepted_intake_offer_without_consent(self):
        for language, dispute, inquiry in (
            ("es", "No reconozco esta compra", "ver un pago"),
            ("pt", "N\u00e3o reconhe\u00e7o esta compra", "ver um pagamento"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                self.post("inquire", transaction_id="DEMO-TX-001")
                state = self.post("message", text=dispute)
                self.assertIsNotNone(state["intake_offer"])
                self.assertIsNone(state["pending_draft"])
                self.assertEqual(self.browser().store.count(), 0)
                state = self.post("message", text=inquiry)
                self.assertEqual(state["messages"][-1]["status"], "needs_filters")
                self.assertIsNone(state["selected_transaction"])
                self.assertEqual(self.browser().pending_search.kind, "inquiry")
                self.assertIsNone(self.browser().business_issue)
                self.assert_read_only(state)


if __name__ == "__main__":
    unittest.main()
