"""Human-request context journeys over loopback with disposable fictional data.

These are engineering regressions, not final evaluation cases. No organizer
records, private cohort, transcript corpus, or evaluation workloads are loaded.
"""

from dataclasses import replace
from decimal import Decimal
import http.client
import json
from threading import Thread
import unittest
from unittest.mock import patch

from bank_service.access import Permission
from bank_service.demo_fixtures import demo_session
from bank_service.routing import IntentProposal
from bank_service.web_app import DemoServer, _now


class CountingRouter:
    """Expose accidental classification of a reply to the context question."""

    def __init__(self, intent="human_request"):
        self.intent = intent
        self.calls = 0

    def route_intent(self, text, language):
        self.calls += 1
        return IntentProposal(self.intent, 1.0, True)


class WebHandoffContextTests(unittest.TestCase):
    REQUEST = {
        "es": "Quiero hablar con una persona",
        "pt": "Quero falar com uma pessoa",
    }
    ISSUE = {
        "es": "Necesito actualizar mi dirección y saber qué documentos debo llevar.",
        "pt": "Preciso atualizar meu endereço e saber quais documentos devo levar.",
    }

    def setUp(self):
        self.server = DemoServer(0)
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

    def fresh(self, language, *, learned=False, handoff_permission=True):
        if handoff_permission:
            self.post("reset")
        else:
            with patch("bank_service.web_app.demo_session", side_effect=lambda now: replace(
                    demo_session(now), permissions=frozenset({Permission.READ_TRANSACTION}))):
                self.post("reset")
        self.post("language", language=language)
        router = CountingRouter() if learned else None
        self.browser().router = router
        return router

    def assert_unsaved(self, state, *, draft=False):
        if not draft:
            self.assertIsNone(state["pending_draft"])
        self.assertEqual(state["receipts"], [])
        self.assertEqual(self.browser().store.count(), 0)

    def ask_for_context(self, language):
        state = self.post("message", text=self.REQUEST[language])
        self.assertEqual(state["messages"][-1]["status"], "needs_handoff_context")
        self.assert_unsaved(state)
        self.assertIsNone(state["handoff_offer"])
        self.assertIsNone(state["intake_offer"])
        self.assertFalse(state["offers_handoff"])
        return state

    def test_bilingual_baseline_and_learned_context_requires_separate_verified_confirmation(self):
        for language in ("es", "pt"):
            for learned in (False, True):
                with self.subTest(language=language, learned=learned):
                    router = self.fresh(language, learned=learned)
                    self.ask_for_context(language)
                    calls = None if router is None else router.calls
                    issue = self.ISSUE[language]
                    state = self.post("message", text=issue)
                    self.assertEqual(state["messages"][-1]["status"], "confirmation_required")
                    self.assert_unsaved(state, draft=True)
                    draft = state["pending_draft"]
                    packet = draft["packet"]
                    self.assertEqual(draft["kind"], "handoff")
                    self.assertEqual(packet["request"], issue)
                    self.assertEqual(packet["language"], language)
                    self.assertEqual(packet["unresolved_questions"], [])
                    self.assertEqual(packet["escalation_reason"], "human_requested")
                    self.assertEqual(packet["verified_actions"], [])
                    self.assertIs(packet["simulated"], True)
                    self.assertNotIn(self.REQUEST[language], packet["unresolved_questions"])
                    if router is not None:
                        self.assertEqual(router.calls, calls)
                    # Chat agreement still cannot perform the final write.
                    state = self.post("message", text="confirmo")
                    self.assertEqual(state["messages"][-1]["status"], "confirmation_required")
                    self.assert_unsaved(state, draft=True)
                    state = self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                    self.assertIsNone(state["pending_draft"])
                    self.assertEqual(len(state["receipts"]), 1)
                    self.assertEqual(self.browser().store.count(), 1)
                    receipt = state["receipts"][0]
                    saved = self.browser().actions.read_case(
                        self.browser().session, receipt["case_id"], now=_now())
                    payload = json.loads(saved.payload_json)
                    self.assertIs(payload["consent"], True)
                    self.assertIs(payload["simulated"], True)
                    self.assertEqual(payload["request"], issue)
                    self.assertEqual(payload["unresolved_questions"], [])

    def test_context_preserves_selected_record_and_its_exact_source_references(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                self.fresh(language, learned=True)
                selected = self.post("inquire", transaction_id="DEMO-TX-001")["selected_transaction"]
                self.ask_for_context(language)
                state = self.post("message", text=self.ISSUE[language])
                packet = state["pending_draft"]["packet"]
                self.assertEqual(state["selected_transaction"], selected)
                self.assertEqual(packet["facts"]["transaction_id"], "DEMO-TX-001")
                self.assertEqual(packet["facts"]["amount"], selected["amount"])
                self.assertEqual(packet["sources"], selected["sources"])
                self.assert_unsaved(state, draft=True)

    def test_inline_issue_skips_redundant_context_question_in_both_languages(self):
        for language, request, issue in (
            ("es", "Quiero hablar con una persona porque necesito corregir mi dirección.",
             "necesito corregir mi dirección"),
            ("pt", "Quero falar com uma pessoa porque preciso corrigir meu endereço.",
             "preciso corrigir meu endereço"),
        ):
            with self.subTest(language=language):
                self.fresh(language, learned=True)
                state = self.post("message", text=request)
                self.assertEqual(state["messages"][-1]["status"], "confirmation_required")
                packet = state["pending_draft"]["packet"]
                self.assertIn(issue, packet["request"])
                self.assertEqual(packet["unresolved_questions"], [])
                self.assert_unsaved(state, draft=True)

    def test_known_dispute_context_skips_question_and_preserves_issue(self):
        for language, issue in (("es", "No reconozco esta compra"),
                                ("pt", "Não reconheço esta compra")):
            with self.subTest(language=language):
                self.fresh(language)
                self.post("inquire", transaction_id="DEMO-TX-001")
                state = self.post("message", text=issue)
                self.assertEqual(state["messages"][-1]["status"], "intake_offered")
                self.assert_unsaved(state)
                self.browser().router = CountingRouter("unsupported")
                state = self.post("message", text=self.REQUEST[language])
                self.assertEqual(state["messages"][-1]["status"], "confirmation_required")
                packet = state["pending_draft"]["packet"]
                self.assertEqual(packet["request"], issue)
                self.assertEqual(packet["unresolved_questions"], [])
                self.assertEqual(packet["facts"]["transaction_id"], "DEMO-TX-001")
                self.assert_unsaved(state, draft=True)

    def test_dispute_intake_does_not_collect_a_second_generic_reason(self):
        for language, issue in (("es", "No reconozco esta compra"),
                                ("pt", "Não reconheço esta compra")):
            with self.subTest(language=language):
                self.fresh(language)
                self.post("inquire", transaction_id="DEMO-TX-001")
                state = self.post("message", text=issue)
                offer = state["intake_offer"]
                self.assertIsNotNone(offer)
                state = self.post("intake_decision", offer_id=offer["offer_id"], prepare=True)
                self.assertEqual(state["messages"][-1]["status"], "confirmation_required")
                draft = state["pending_draft"]
                self.assertEqual(draft["kind"], "intake")
                self.assertEqual(draft["packet"]["request"], issue)
                self.assert_unsaved(state, draft=True)

    def test_yes_greeting_and_repeated_human_request_do_not_substitute_for_purpose(self):
        for language, replies in (
            ("es", ("sí", "Hola", "Quiero hablar con una persona")),
            ("pt", ("sim", "Olá", "Quero falar com uma pessoa")),
        ):
            with self.subTest(language=language):
                router = self.fresh(language, learned=True)
                self.ask_for_context(language)
                calls = router.calls
                for reply in replies:
                    state = self.post("message", text=reply)
                    self.assertEqual(state["messages"][-1]["status"], "needs_handoff_context")
                    self.assert_unsaved(state)
                self.assertEqual(router.calls, calls)

    def test_chat_cancellation_discards_context_without_any_case(self):
        for language, cancellation in (("es", "cancelar"), ("es", "no gracias"),
                                       ("pt", "cancelar"), ("pt", "não obrigado")):
            with self.subTest(language=language, cancellation=cancellation):
                self.fresh(language)
                self.ask_for_context(language)
                state = self.post("message", text=cancellation)
                self.assertEqual(state["messages"][-1]["status"], "handoff_context_cancelled")
                self.assert_unsaved(state)
                state = self.post("message", text=self.ISSUE[language])
                self.assert_unsaved(state)
                self.assertNotEqual(state["messages"][-1]["status"], "confirmation_required")

    def test_new_inquiry_and_navigation_discard_pending_context(self):
        for navigation in ("plain_inquiry", "search", "inquire", "language", "reset"):
            with self.subTest(navigation=navigation):
                self.fresh("es", learned=True)
                self.ask_for_context("es")
                if navigation == "plain_inquiry":
                    state = self.post("message", text="Buscar una compra")
                    self.assertEqual(state["messages"][-1]["status"], "needs_filters")
                elif navigation == "search":
                    state = self.post("search", transaction_date="2026-06-16")
                    self.assertEqual(state["messages"][-1]["status"], "ambiguous")
                elif navigation == "inquire":
                    state = self.post("inquire", transaction_id="DEMO-TX-002")
                    self.assertEqual(state["selected_transaction"]["transaction_id"], "DEMO-TX-002")
                elif navigation == "language":
                    state = self.post("language", language="pt")
                else:
                    state = self.post("reset")
                self.assert_unsaved(state)
                # Outside the waiting step, a classifier's human label alone
                # cannot convert an unrelated message into a prepared handoff.
                self.browser().router = CountingRouter()
                state = self.post("message", text="Necesito actualizar mi dirección postal.")
                self.assertNotEqual(state["messages"][-1]["status"], "confirmation_required")
                self.assert_unsaved(state)

    def test_missing_or_revoked_handoff_permission_never_prompts_or_prepares(self):
        for language in ("es", "pt"):
            with self.subTest(language=language, scenario="missing"):
                self.fresh(language, handoff_permission=False)
                code, state = self.request("POST", "/api/action", {
                    "action": "message", "csrf_token": self.state["csrf_token"],
                    "text": self.REQUEST[language],
                })
                self.assertEqual(code, 403)
                self.assertEqual(state["error"]["code"], "access_denied")
                self.assertNotEqual(state["messages"][-1]["status"], "needs_handoff_context")
                self.assert_unsaved(state)
            with self.subTest(language=language, scenario="revoked_after_prompt"):
                self.fresh(language)
                self.ask_for_context(language)
                browser = self.browser()
                browser.session = replace(browser.session, permissions=frozenset({Permission.READ_TRANSACTION}))
                code, state = self.request("POST", "/api/action", {
                    "action": "message", "csrf_token": self.state["csrf_token"],
                    "text": self.ISSUE[language],
                })
                self.assertEqual(code, 403)
                self.assertEqual(state["error"]["code"], "access_denied")
                self.assert_unsaved(state)

    def test_changed_record_or_expired_context_cannot_prepare_from_a_stale_prompt(self):
        for mutation in ("changed_record", "expired_context"):
            with self.subTest(mutation=mutation):
                self.fresh("es")
                self.post("inquire", transaction_id="DEMO-TX-001")
                self.ask_for_context("es")
                browser = self.browser()
                if mutation == "changed_record":
                    entry = browser.records["DEMO-TX-001"]
                    browser.records["DEMO-TX-001"] = replace(
                        entry, record=replace(entry.record, amount=Decimal("30.00")))
                    code, state = self.request("POST", "/api/action", {
                        "action": "message", "csrf_token": self.state["csrf_token"],
                        "text": self.ISSUE["es"],
                    })
                else:
                    with patch("bank_service.web_app._now", return_value=browser.pending_handoff_context.expires_at):
                        code, state = self.request("POST", "/api/action", {
                            "action": "message", "csrf_token": self.state["csrf_token"],
                            "text": self.ISSUE["es"],
                        })
                self.assertEqual(code, 409)
                self.assert_unsaved(state)


if __name__ == "__main__":
    unittest.main()
