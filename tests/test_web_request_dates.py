"""Loopback journeys for date replies and the shared consent boundary.

The independently authored June 16 fixtures are the only records used here.
Clocks, sessions and case stores are isolated; no private or sealed cases are read.
"""

from datetime import datetime, timezone
from decimal import Decimal
import http.client
import json
from threading import Thread
import unicodedata
import unittest
from unittest.mock import patch

from bank_service.routing import IntentProposal
from bank_service.web_app import DemoServer


class ConfidentDisputeRouter:
    """A bad model suggestion must not turn date details into a dispute."""

    def __init__(self):
        self.calls = 0

    def route_intent(self, text, language):
        self.calls += 1
        return IntentProposal("dispute_intake", 1.0, True)


class WebRequestDateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 20, 12, tzinfo=timezone.utc)
        self.clock = patch("bank_service.web_app._now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.server = DemoServer(0)
        self.thread = Thread(target=self.server.serve_forever,
                             kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.port = self.server.server_address[1]
        self.cookie = ""
        self.state = {}
        status, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 200)

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

    def action(self, action, **values):
        return self.request("POST", "/api/action", {
            "action": action, "csrf_token": self.state["csrf_token"], **values,
        })

    def post(self, action, **values):
        status, state = self.action(action, **values)
        self.assertEqual(status, 200, state.get("error"))
        return state

    def browser(self):
        return self.server.get_session(self.cookie.split("=", 1)[1])

    def inquiry(self, language="es"):
        self.post("reset")
        self.post("language", language=language)
        request = "ver un pago" if language == "es" else "ver um pagamento"
        state = self.post("message", text=request)
        self.assertEqual(state["messages"][-1]["status"], "needs_filters")
        self.assertEqual(self.browser().pending_search.kind, "inquiry")
        return state

    def assert_unprepared(self, state):
        self.assertIsNone(state["pending_draft"])
        self.assertIsNone(state["handoff_offer"])
        self.assertEqual(state["receipts"], [])
        self.assertEqual(self.browser().store.count(), 0)

    def assert_read_only(self, state):
        self.assert_unprepared(state)
        self.assertIsNone(state["intake_offer"])
        self.assertFalse(state["offers_handoff"])

    def assert_clean_presentation(self, text):
        normalized = "".join(character for character in unicodedata.normalize("NFKD", text.lower())
                             if not unicodedata.combining(character))
        for repeated_disclaimer in ("simulad", "demostr", "demonstra", "fictici"):
            self.assertNotIn(repeated_disclaimer, normalized)

    def test_natural_month_name_variants_preserve_bilingual_inquiry(self):
        for language, dates in (
            ("es", ("16 de Junio 2026", "16 de junio, 2026", "Junio 16, 2026",
                    "16 de junio del 2026")),
            ("pt", ("16 de Junho 2026", "16 de junho, 2026", "Junho 16, 2026",
                    "16 de junho de 2026")),
        ):
            for text in dates:
                with self.subTest(language=language, text=text):
                    self.inquiry(language)
                    state = self.post("message", text=text)
                    self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                    self.assertEqual(self.browser().pending_search.kind, "inquiry")
                    self.assertEqual(self.browser().pending_search.transaction_date.isoformat(),
                                     "2026-06-16")
                    self.assert_read_only(state)
                    state = self.post("choose", transaction_id="DEMO-TX-002")
                    self.assertEqual(state["messages"][-1]["status"], "answered")
                    self.assertEqual(state["selected_transaction"]["transaction_id"], "DEMO-TX-002")
                    self.assert_read_only(state)

    def test_card_numeric_date_and_iso_find_the_same_records(self):
        for language in ("es", "pt"):
            for text in ("16/06/2026", "16-06-2026", "2026-06-16"):
                with self.subTest(language=language, text=text):
                    self.inquiry(language)
                    state = self.post("message", text=text)
                    self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                    self.assert_read_only(state)

    def test_standalone_dates_do_not_use_a_dispute_model_or_prepare_a_request(self):
        for language, text in (("es", "16 de junio 2026"),
                               ("pt", "16 de junho 2026")):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                router = ConfidentDisputeRouter()
                self.browser().router = router
                state = self.post("message", text=text)
                self.assertEqual(router.calls, 0)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.assertEqual(self.browser().pending_search.kind, "inquiry")
                self.assert_read_only(state)

    def test_omitted_year_is_visible_and_uses_server_monterrey_calendar(self):
        for current, expected_year, expected_matches in (
            (datetime(2027, 1, 1, 0, 30, tzinfo=timezone.utc), 2026,
             ["DEMO-TX-001", "DEMO-TX-002"]),
            (datetime(2027, 1, 1, 6, 30, tzinfo=timezone.utc), 2027, []),
        ):
            for language, text in (("es", "16 de junio"), ("pt", "16 de junho")):
                with self.subTest(current=current.isoformat(), language=language):
                    with patch("bank_service.web_app._now", return_value=current):
                        self.inquiry(language)
                        state = self.post("message", text=text)
                        notices = [message for message in state["messages"]
                                   if message["role"] == "assistant"
                                   and message["status"] == "date_interpreted"]
                        self.assertEqual(len(notices), 1)
                        self.assertIn(f"16/06/{expected_year}", notices[0]["text"])
                        self.assertIn(str(expected_year), notices[0]["text"])
                        self.assertEqual(state["candidate_ids"], expected_matches)
                        self.assert_read_only(state)

    def test_invalid_current_year_leap_day_cannot_fall_back_to_another_date(self):
        for language, invalid, correction in (
            ("es", "29 de febrero", "16 de junio 2026"),
            ("pt", "29 de fevereiro", "16 de junho 2026"),
        ):
            with self.subTest(language=language):
                self.inquiry(language)
                status, state = self.action("message", text=invalid)
                self.assertEqual(status, 400)
                self.assertEqual(state["error"]["code"], "invalid_date")
                self.assertEqual(state["candidate_ids"], [])
                self.assertIsNone(state["selected_transaction"])
                self.assertIsNone(self.browser().pending_search.transaction_date)
                self.assert_read_only(state)
                state = self.post("message", text=correction)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.assert_read_only(state)

    def test_current_year_phrase_corrects_no_match_without_changing_the_request(self):
        for language, month, suffix, dispute in (
            ("es", "Junio", "de este a\u00f1o", "No reconozco un cargo"),
            ("pt", "Junho", "deste ano", "N\u00e3o reconhe\u00e7o uma compra"),
        ):
            for context in ("standalone", "inquiry", "intake"):
                for learned in (False, True):
                    with self.subTest(language=language, context=context, learned=learned):
                        router = ConfidentDisputeRouter() if learned else None
                        self.server._router = router
                        self.post("reset")
                        self.post("language", language=language)
                        if context == "inquiry":
                            self.post("message", text="ver un pago" if language == "es"
                                      else "ver um pagamento")
                        elif context == "intake":
                            self.post("message", text=dispute)
                        calls_before_date = router.calls if router is not None else 0
                        state = self.post("message", text=f"17 de {month} {suffix}")
                        self.assertEqual(state["messages"][-1]["status"], "no_match")
                        self.assertEqual(state["candidate_ids"], [])
                        self.assert_read_only(state)
                        state = self.post("message", text=f"16 de {month} {suffix}")
                        if router is not None:
                            self.assertEqual(router.calls, calls_before_date)
                        pending = self.browser().pending_search
                        self.assertEqual(pending.kind, "intake" if context == "intake"
                                         else "inquiry")
                        self.assertEqual(pending.transaction_date.isoformat(), "2026-06-16")
                        if context == "intake":
                            self.assertEqual(pending.request, dispute)
                        notices = [item for item in state["messages"]
                                   if item["status"] == "date_interpreted"]
                        self.assertEqual(len(notices), 2)
                        self.assertIn("16/06/2026", notices[-1]["text"])
                        self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                        self.assert_read_only(state)

    def test_invalid_current_year_phrase_preserves_filters_until_corrected(self):
        for language, invalid_dates, correction in (
            ("es", ("16 de junio de este a\u00f1o 2025",
                    "16 de junio de este a\u00f1ofoo", "29 de febrero de este a\u00f1o"),
             "16 de junio de este a\u00f1o"),
            ("pt", ("16 de junho de este ano 2025",
                    "16 de junho de este anofoo", "29 de fevereiro de este ano"),
             "16 de junho de este ano"),
        ):
            for text in invalid_dates:
                with self.subTest(language=language, text=text):
                    router = ConfidentDisputeRouter()
                    self.server._router = router
                    self.inquiry(language)
                    self.post("message", text="25.50 USD")
                    status, state = self.action("message", text=text)
                    self.assertEqual(status, 400)
                    self.assertEqual(state["error"]["code"], "invalid_date")
                    pending = self.browser().pending_search
                    self.assertEqual(pending.kind, "inquiry")
                    self.assertEqual(pending.amount, Decimal("25.50"))
                    self.assertEqual(pending.currency, "USD")
                    self.assertIsNone(pending.transaction_date)
                    self.assertNotIn("date_interpreted", [item["status"]
                                                         for item in state["messages"]])
                    self.assert_read_only(state)
                    state = self.post("message", text=correction)
                    self.assertEqual(router.calls, 0)
                    self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                    self.assertEqual(pending.transaction_date.isoformat(), "2026-06-16")
                    self.assert_read_only(state)

    def test_natural_date_year_is_not_an_amount_even_with_currency(self):
        for language, text in (("es", "16 de junio 2026 USD"),
                               ("pt", "16 de junho de 2026 USD")):
            with self.subTest(language=language):
                self.inquiry(language)
                state = self.post("message", text=text)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                context = self.browser().pending_search
                self.assertIsNone(context.amount)
                self.assertEqual(context.currency, "USD")
                self.assertEqual(context.transaction_date.isoformat(), "2026-06-16")
                self.assert_read_only(state)

    def test_malformed_explicit_year_requires_correction_without_changing_inquiry(self):
        for language, texts in (
            ("es", ("16 de junio del 2026foo", "16 de junio del", "16 de junio de 2026.00 USD")),
            ("pt", ("16 de junho de 2026foo", "16 de junho de", "16 de junho de 2026USD")),
        ):
            for text in texts:
                with self.subTest(language=language, text=text):
                    router = ConfidentDisputeRouter()
                    self.server._router = router
                    self.inquiry(language)
                    status, state = self.action("message", text=text)
                    self.assertEqual(status, 400)
                    self.assertEqual(state["error"]["code"], "invalid_date")
                    self.assertEqual(router.calls, 0)
                    self.assertEqual(self.browser().pending_search.kind, "inquiry")
                    self.assertIsNone(self.browser().pending_search.transaction_date)
                    self.assertNotIn("date_interpreted", [item["status"] for item in state["messages"]])
                    self.assert_read_only(state)

    def test_combined_date_and_money_followups_bypass_an_incorrect_dispute_model(self):
        for language, texts in (
            ("es", ("16 de junio 2026 USD", "25.50 USD el 16 de junio 2026")),
            ("pt", ("16 de junho de 2026 USD", "25.50 USD em 16 de junho de 2026")),
        ):
            for text in texts:
                with self.subTest(language=language, text=text):
                    router = ConfidentDisputeRouter()
                    self.server._router = router
                    self.inquiry(language)
                    self.assertEqual(router.calls, 0)
                    state = self.post("message", text=text)
                    self.assertEqual(router.calls, 0)
                    self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                    context = self.browser().pending_search
                    self.assertEqual(context.kind, "inquiry")
                    self.assertEqual(context.currency, "USD")
                    self.assertEqual(context.transaction_date.isoformat(), "2026-06-16")
                    self.assertEqual(context.amount,
                                     Decimal("25.50") if text.startswith("25.50") else None)
                    self.assert_read_only(state)

    def test_combined_date_and_money_continue_prior_dispute_in_both_routing_modes(self):
        for language, request, texts in (
            ("es", "No reconozco un cargo",
             ("16 de junio 2026 USD", "25.50 USD el 16 de junio 2026")),
            ("pt", "N\u00e3o reconhe\u00e7o uma compra",
             ("16 de junho de 2026 USD", "25.50 USD em 16 de junho de 2026")),
        ):
            for learned in (False, True):
                for text in texts:
                    with self.subTest(language=language, learned=learned, text=text):
                        router = ConfidentDisputeRouter() if learned else None
                        self.server._router = router
                        self.post("reset")
                        self.post("language", language=language)
                        self.post("message", text=request)
                        self.assertEqual(self.browser().pending_search.kind, "intake")
                        if router is not None:
                            self.assertEqual(router.calls, 1)
                        state = self.post("message", text=text)
                        if router is not None:
                            self.assertEqual(router.calls, 1)
                        context = self.browser().pending_search
                        self.assertEqual(context.kind, "intake")
                        self.assertEqual(context.request, request)
                        self.assertEqual(context.currency, "USD")
                        self.assertEqual(context.transaction_date.isoformat(), "2026-06-16")
                        self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                        self.assert_read_only(state)

    def test_dispute_date_followup_requires_selection_preparation_and_final_confirmation(self):
        for language, request, text in (
            ("es", "No reconozco un cargo", "16 de junio del 2026"),
            ("pt", "N\u00e3o reconhe\u00e7o uma compra", "16 de junho de 2026"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                self.post("message", text=request)
                self.assertEqual(self.browser().pending_search.kind, "intake")
                state = self.post("message", text=text)
                self.assertEqual(self.browser().pending_search.kind, "intake")
                self.assertEqual(self.browser().pending_search.request, request)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                self.assert_read_only(state)
                state = self.post("choose", transaction_id="DEMO-TX-002")
                offer = state["intake_offer"]
                self.assertIsNotNone(offer)
                self.assertEqual(offer["transaction_id"], "DEMO-TX-002")
                self.assert_unprepared(state)
                state = self.post("intake_decision", offer_id=offer["offer_id"], prepare=True)
                draft = state["pending_draft"]
                self.assertEqual(draft["kind"], "intake")
                self.assert_clean_presentation(draft["summary"])
                for message in state["messages"]:
                    if message["role"] == "assistant":
                        self.assert_clean_presentation(message["text"])
                self.assertEqual(draft["packet"]["facts"]["transaction_id"], "DEMO-TX-002")
                self.assertIs(draft["packet"]["simulated"], True)
                self.assertEqual(self.browser().store.count(), 0)
                self.assertEqual(state["receipts"], [])
                state = self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertIsNone(state["pending_draft"])
                self.assertEqual(self.browser().store.count(), 1)
                self.assertEqual(len(state["receipts"]), 1)
                receipt = state["receipts"][0]
                self.assertEqual(receipt["kind"], "intake")
                self.assert_clean_presentation(receipt["text"])
                saved = self.browser().actions.read_case(self.browser().session, receipt["case_id"],
                                                         now=self.now)
                packet = json.loads(saved.payload_json)
                self.assertIs(packet["consent"], True)
                self.assertIs(packet["simulated"], True)
                self.assertEqual(packet["facts"]["transaction_id"], "DEMO-TX-002")


if __name__ == "__main__":
    unittest.main()
