"""Human preparation needs explicit wording, never a classifier label alone.

All records and case stores are synthetic/disposable. The isolated HTTP journey
uses the fixed TRAIN-only preview loader; it does not read DEVELOPMENT, final
evaluation or private bank source records.
"""

import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from bank_service.route_loader import load_preview_router
from bank_service.routing import (
    IntentProposal, RoutingError, human_request_purpose, is_explicit_human_request, is_greeting,
)
from bank_service.web_app import BrowserSession, DemoServer, _now


class HumanRouter:
    """A maximally confident model proposal still carries no human consent."""

    def __init__(self, intent="human_request"):
        self.proposal = IntentProposal(intent, 1.0, True)
        self.calls = 0

    def route_intent(self, text, language):
        self.calls += 1
        return self.proposal


class ExplicitHumanRequestTests(unittest.TestCase):
    def test_direct_human_wording_is_recognized_bilingually(self):
        for language, requests in (
            ("es", ("Quiero hablar con una persona", "Necesito un asesor",
                    "Quiero conversar con un agente", "Atenci\u00f3n humana")),
            ("pt", ("Quero falar com uma pessoa", "Preciso de um atendente",
                    "Quero conversar com um agente", "Atendimento humano")),
        ):
            for text in requests:
                with self.subTest(language=language, text=text):
                    self.assertTrue(is_explicit_human_request(text, language))

    def test_negated_or_unrelated_wording_is_not_a_human_request(self):
        for language, requests in (
            ("es", ("quiero comer", "necesito ayuda con mi tarjeta",
                    "No quiero hablar con una persona", "No necesito una persona",
                    "No deseo conversar con un agente", "hello", "xyz", "123abc")),
            ("pt", ("quero comer", "preciso de ajuda com meu cart\u00e3o",
                    "N\u00e3o quero falar com uma pessoa", "N\u00e3o preciso de um atendente",
                    "N\u00e3o desejo conversar com um agente", "hello", "xyz")),
        ):
            for text in requests:
                with self.subTest(language=language, text=text):
                    self.assertFalse(is_explicit_human_request(text, language))

    def test_fixed_validation_codes_do_not_echo_request_values(self):
        for text, language, error in (
            (None, "es", "invalid_request"), (" ", "pt", "invalid_request"),
            ("x" * 1001, "es", "request_too_long"),
            ("Quiero hablar con una persona", "en", "unsupported_language"),
        ):
            with self.subTest(language=language, error=error):
                with self.assertRaisesRegex(RoutingError, "^" + error + "$"):
                    is_explicit_human_request(text, language)

    def test_english_greeting_alias_is_exact_and_preserves_mixed_request(self):
        for language in ("es", "pt"):
            for text in ("hello", "Hi!", " HELLO. "):
                with self.subTest(language=language, text=text):
                    self.assertTrue(is_greeting(text, language))
            for text in ("hello, necesito hablar con una persona", "hi, quero falar com uma pessoa",
                         "hello necesito ayuda con mi tarjeta", "highlight"):
                with self.subTest(language=language, text=text):
                    self.assertFalse(is_greeting(text, language))


class HumanRequestBoundaryTests(unittest.TestCase):
    def browser(self, *, language="es", router=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        browser = BrowserSession(Path(directory.name) / "cases.sqlite3", router=router)
        self.addCleanup(browser.close)
        now = _now()
        browser.act({"action": "language", "language": language}, now)
        return browser, now

    def assert_no_preparation(self, browser):
        self.assertIsNone(browser.pending_draft)
        self.assertIsNone(browser.handoff_offer)
        self.assertFalse(browser.offers_handoff)
        self.assertEqual(browser.store.count(), 0)
        self.assertEqual(browser.case_ids, [])

    def test_narrative_and_unclear_negative_clauses_never_prepare_from_model_label(self):
        for text, language in (
            ("No me interesa hablar con una persona", "es"),
            ("No tengo ganas de hablar con una persona", "es"),
            ("No quiero realmente hablar con un agente", "es"),
            ("Me dijeron que podia hablar con una persona", "es"),
            ("N\u00e3o gostaria de falar com um atendente", "pt"),
            ("N\u00e3o quero mesmo falar com uma pessoa", "pt"),
            ("Disseram que eu podia falar com um atendente", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertFalse(is_explicit_human_request(text, language))
                browser, now = self.browser(language=language, router=HumanRouter())
                browser.message(text, now)
                self.assertEqual(browser.messages[-1]["status"], "needs_request")
                self.assert_no_preparation(browser)

    def test_positive_human_request_does_not_depend_on_model_label(self):
        for language, request, purpose in (
            ("es", "No reconozco un cargo, quiero hablar con una persona", None),
            ("pt", "Preciso de um atendente", "Meu cart\u00e3o est\u00e1 bloqueado"),
        ):
            for prediction in ("unsupported", "inquiry", "dispute_intake"):
                with self.subTest(language=language, prediction=prediction):
                    browser, now = self.browser(language=language, router=HumanRouter(prediction))
                    self.assertTrue(is_explicit_human_request(request, language))
                    browser.message(request, now)
                    if purpose is not None:
                        self.assertEqual(browser.messages[-1]["status"], "needs_handoff_context")
                        self.assert_no_preparation(browser)
                        calls = browser.router.calls
                        browser.message(purpose, now)
                        self.assertEqual(browser.router.calls, calls)
                    self.assertEqual(browser.pending_draft.kind, "handoff")
                    self.assertEqual(browser.pending_request, purpose or request)
                    self.assertEqual(browser.store.count(), 0)

    def test_request_for_person_does_not_override_explicit_refusal_to_prepare(self):
        for text, language in (
            ("Quiero hablar con una persona, pero no quiero que prepares nada", "es"),
            ("Quiero hablar con una persona, no quiero abrir un ticket", "es"),
            ("Quiero hablar con una persona, sin preparar una solicitud", "es"),
            ("Quero falar com uma pessoa, mas n\u00e3o prepare uma solicita\u00e7\u00e3o", "pt"),
            ("Quero falar com uma pessoa, n\u00e3o quero que voc\u00ea crie um caso", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertFalse(is_explicit_human_request(text, language))
                browser, now = self.browser(language=language, router=HumanRouter())
                browser.message(text, now)
                self.assertEqual(browser.messages[-1]["status"], "needs_request")
                self.assert_no_preparation(browser)
        self.assertTrue(is_explicit_human_request(
            "No pude crear un caso, quiero hablar con una persona", "es"))

    def test_human_words_do_not_override_payment_execution_limit(self):
        for text, language in (
            ("Quiero hacer un pago y hablar con una persona", "es"),
            ("Quero fazer uma transa\u00e7\u00e3o e falar com uma pessoa", "pt"),
        ):
            with self.subTest(language=language):
                self.assertFalse(is_explicit_human_request(text, language))
                browser, now = self.browser(language=language, router=HumanRouter())
                browser.message(text, now)
                self.assertEqual(browser.messages[-1]["status"], "needs_request")
                self.assert_no_preparation(browser)

    def test_classifier_only_human_label_clarifies_without_preparation(self):
        for language, messages in (
            ("es", ("quiero comer", "xyz", "123abc", "necesito ayuda con mi tarjeta",
                    "No quiero hablar con una persona", "No necesito una persona",
                    "No deseo conversar con un agente")),
            ("pt", ("quero comer", "xyz", "preciso de ajuda com meu cart\u00e3o",
                    "N\u00e3o preciso de um atendente", "N\u00e3o desejo conversar com um agente")),
        ):
            for text in messages:
                with self.subTest(language=language, text=text):
                    router = HumanRouter()
                    browser, now = self.browser(language=language, router=router)
                    browser.message(text, now)
                    self.assertEqual(router.calls, 1)
                    self.assertEqual(browser.messages[-1]["status"], "needs_request")
                    self.assertIsNone(browser.intake_offer)
                    self.assert_no_preparation(browser)

    def test_direct_human_wording_collects_purpose_but_cannot_write_without_confirmation(self):
        for language, request, purpose in (
            ("es", "Quiero hablar con una persona", "Necesito ayuda para desbloquear mi tarjeta"),
            ("pt", "Quero falar com uma pessoa", "Preciso de ajuda para desbloquear meu cart\u00e3o"),
        ):
            for learned in (False, True):
                with self.subTest(language=language, learned=learned):
                    browser, now = self.browser(language=language, router=HumanRouter() if learned else None)
                    browser.message(request, now)
                    self.assertEqual(browser.messages[-1]["status"], "needs_handoff_context")
                    self.assert_no_preparation(browser)
                    calls = None if browser.router is None else browser.router.calls
                    browser.message(purpose, now)
                    if browser.router is not None:
                        self.assertEqual(browser.router.calls, calls)
                    draft = browser.state(now)["pending_draft"]
                    self.assertIsNotNone(draft)
                    self.assertEqual(draft["kind"], "handoff")
                    self.assertEqual(draft["packet"]["request"], purpose)
                    self.assertEqual(draft["packet"]["escalation_reason"], "human_requested")
                    self.assertEqual(draft["packet"]["unresolved_questions"], [])
                    self.assertEqual(browser.store.count(), 0)
                    browser.message("confirmo", now)
                    self.assertEqual(browser.store.count(), 0)
                    browser.act({"action": "confirm", "draft_id": draft["draft_id"], "confirmed": True}, now)
                    self.assertEqual(browser.store.count(), 1)

    def test_model_only_label_keeps_pending_banking_issue_for_later_explicit_human_request(self):
        browser, now = self.browser(router=HumanRouter("dispute_intake"))
        issue = "No reconozco un cargo"
        browser.message(issue, now)
        search, route = browser.pending_search, browser.pending_route
        self.assertEqual(search.kind, "intake")
        browser.router = HumanRouter()
        browser.message("quiero comer", now)
        self.assertIs(browser.pending_search, search)
        self.assertEqual(browser.pending_route, route)
        self.assertEqual(browser.business_issue, issue)
        self.assert_no_preparation(browser)
        request = "Quiero hablar con una persona"
        browser.message(request, now)
        draft = browser.state(now)["pending_draft"]
        self.assertEqual(draft["packet"]["request"], issue)
        self.assertEqual(draft["packet"]["unresolved_questions"], [])
        self.assertEqual(browser.store.count(), 0)

    def test_model_only_label_keeps_selected_record_issue_and_existing_intake_offer(self):
        browser, now = self.browser(router=HumanRouter("dispute_intake"))
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
        issue = "No reconozco esta compra"
        browser.message(issue, now)
        offer = browser.intake_offer
        self.assertIsNotNone(offer)
        browser.router = HumanRouter()
        browser.message("necesito ayuda con mi tarjeta", now)
        self.assertEqual(browser.selected_id, "DEMO-TX-001")
        self.assertEqual(browser.business_issue, issue)
        self.assertIs(browser.intake_offer, offer)
        self.assert_no_preparation(browser)
        browser.message("Quiero hablar con una persona", now)
        draft = browser.state(now)["pending_draft"]
        self.assertEqual(draft["packet"]["facts"]["transaction_id"], "DEMO-TX-001")
        self.assertEqual(draft["packet"]["request"], issue)
        self.assertEqual(draft["packet"]["unresolved_questions"], [])
        self.assertEqual(browser.store.count(), 0)

    def test_hello_and_hi_are_greetings_in_both_languages_and_modes(self):
        for language in ("es", "pt"):
            for learned in (False, True):
                for text in ("hello", "Hi!"):
                    with self.subTest(language=language, learned=learned, text=text):
                        router = HumanRouter() if learned else None
                        browser, now = self.browser(language=language, router=router)
                        browser.message(text, now)
                        self.assertEqual(browser.messages[-1]["status"], "greeting")
                        self.assertEqual(browser.messages[-1]["text"], browser.text("greeting"))
                        self.assert_no_preparation(browser)
                        if router is not None:
                            self.assertEqual(router.calls, 0)

    def test_mixed_greeting_and_explicit_human_request_is_not_swallowed(self):
        for language, text in (("es", "hello, necesito hablar con una persona"),
                               ("pt", "hello, quero falar com uma pessoa")):
            browser, now = self.browser(language=language, router=HumanRouter())
            browser.message(text, now)
            self.assertEqual(browser.messages[-1]["status"], "needs_handoff_context")
            self.assert_no_preparation(browser)

    def test_negative_contact_aliases_cancel_purpose_collection_without_a_draft(self):
        for language, request, refusals in (
            ("es", "Quiero hablar con una persona", (
                "No necesito un asesor", "Ya no necesito atenci\u00f3n humana",
                "No quiero que prepares nada", "No prepares una solicitud",
            )),
            ("pt", "Quero falar com uma pessoa", (
                "N\u00e3o preciso de um atendente", "N\u00e3o preciso de uma pessoa",
                "N\u00e3o prepare uma solicita\u00e7\u00e3o",
            )),
        ):
            for refusal in refusals:
                with self.subTest(language=language, refusal=refusal):
                    router = HumanRouter()
                    browser, now = self.browser(language=language, router=router)
                    browser.message(request, now)
                    self.assertEqual(browser.messages[-1]["status"], "needs_handoff_context")
                    calls = router.calls
                    browser.message(refusal, now)
                    self.assertEqual(browser.messages[-1]["status"], "handoff_context_cancelled")
                    self.assertFalse(browser.state(now)["awaiting_handoff_context"])
                    self.assertEqual(router.calls, calls)
                    self.assert_no_preparation(browser)

    def test_politeness_only_inline_clauses_still_need_customer_purpose(self):
        for language, requests in (
            ("es", ("Quiero hablar con una persona, gracias",
                    "Quiero hablar con una persona, muchas gracias")),
            ("pt", ("Quero falar com uma pessoa, obrigado",
                    "Quero falar com uma pessoa, obrigada")),
        ):
            for request in requests:
                with self.subTest(language=language, request=request):
                    self.assertTrue(is_explicit_human_request(request, language))
                    self.assertIsNone(human_request_purpose(request, language))
                    browser, now = self.browser(language=language, router=HumanRouter())
                    browser.message(request, now)
                    self.assertEqual(browser.messages[-1]["status"], "needs_handoff_context")
                    self.assert_no_preparation(browser)

    def test_negative_customer_issue_is_literal_purpose_rather_than_cancellation(self):
        for language, request, issue in (
            ("es", "Quiero hablar con una persona", "No puedo entrar"),
            ("pt", "Quero falar com uma pessoa", "N\u00e3o consigo entrar"),
        ):
            with self.subTest(language=language):
                router = HumanRouter()
                browser, now = self.browser(language=language, router=router)
                browser.message(request, now)
                calls = router.calls
                browser.message(issue, now)
                packet = browser.state(now)["pending_draft"]["packet"]
                self.assertEqual(packet["request"], issue)
                self.assertEqual(packet["unresolved_questions"], [])
                self.assertEqual(router.calls, calls)
                self.assertEqual(browser.store.count(), 0)


class WebHumanRequestBoundaryTests(unittest.TestCase):
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

    def assert_no_draft_or_case(self, state):
        self.assertIsNone(state["pending_draft"])
        self.assertIsNone(state["handoff_offer"])
        self.assertIsNone(state["intake_offer"])
        self.assertFalse(state["offers_handoff"])
        self.assertEqual(state["receipts"], [])
        self.assertEqual(self.browser().store.count(), 0)

    def test_screenshot_sequence_with_actual_train_router_never_creates_unsolicited_draft(self):
        state = self.post("message", text="quiero comer")
        self.assertEqual(state["messages"][-1]["status"], "needs_request")
        self.assert_no_draft_or_case(state)
        # The old screenshot could cancel its unsolicited draft. There is now
        # no draft, so a fabricated cancellation is rejected without side effects.
        code, _ = self.request("POST", "/api/action", {
            "action": "cancel", "csrf_token": state["csrf_token"],
            "draft_id": "nonexistent-synthetic-draft",
        })
        self.assertEqual(code, 409)
        _, state = self.request("GET", "/api/state")
        self.assert_no_draft_or_case(state)
        state = self.post("message", text="hello")
        self.assertEqual(state["messages"][-1]["status"], "greeting")
        self.assert_no_draft_or_case(state)

    def test_train_router_direct_human_request_only_saves_after_separate_confirm(self):
        for language, request, purpose in (
            ("es", "Quiero hablar con una persona", "Necesito corregir los datos de mi cuenta"),
            ("pt", "Quero falar com uma pessoa", "Preciso corrigir os dados da minha conta"),
        ):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                state = self.post("message", text=request)
                self.assertEqual(state["messages"][-1]["status"], "needs_handoff_context")
                self.assert_no_draft_or_case(state)
                state = self.post("message", text=purpose)
                draft = state["pending_draft"]
                self.assertEqual(draft["kind"], "handoff")
                self.assertEqual(draft["packet"]["request"], purpose)
                self.assertEqual(draft["packet"]["escalation_reason"], "human_requested")
                self.assertEqual(draft["packet"]["unresolved_questions"], [])
                self.assertEqual(self.browser().store.count(), 0)
                state = self.post("message", text="confirmo")
                self.assertEqual(state["messages"][-1]["status"], "confirmation_required")
                self.assertEqual(self.browser().store.count(), 0)
                state = self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertEqual(self.browser().store.count(), 1)
                self.assertEqual(len(state["receipts"]), 1)


if __name__ == "__main__":
    unittest.main()
