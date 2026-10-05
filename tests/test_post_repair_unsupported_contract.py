"""Unsupported service and handoff permissions on invented demo records only."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bank_service.access import AccessDenied, Permission
from bank_service.demo_fixtures import DEMO_CUSTOMER, demo_records
from bank_service.routing import IntentProposal
from bank_service.web_app import BrowserSession, PrivateCohortConfig, _now


class InquiryProposal:
    def __init__(self):
        self.calls = 0

    def route_intent(self, text, language):
        self.calls += 1
        return IntentProposal("inquiry", 1.0, True)


class PostRepairUnsupportedContractTests(unittest.TestCase):
    def browser(self, language, *, learned=False, permissions=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        router = InquiryProposal() if learned else None
        config = None if permissions is None else PrivateCohortConfig(
            demo_records(), DEMO_CUSTOMER, frozenset(permissions))
        browser = BrowserSession(Path(directory.name) / "cases.sqlite3", router=router, config=config)
        self.addCleanup(browser.close)
        now = _now()
        browser.act({"action": "language", "language": language}, now)
        return browser, now, router

    def test_positive_credential_change_is_refused_outside_both_routers(self):
        examples = {
            "es": ("¿Puedes cambiar el PIN de mi tarjeta?", "Cambia mi PIN, por favor.",
                   "Quiero restablecer mi contraseña.", "Ayúdame a cambiar la clave de acceso.",
                   "¿Cómo puedo cambiar el PIN de mi tarjeta?",
                   "No quiero que lo hagas; solo pregunto cómo restablecer la contraseña."),
            "pt": ("Pode trocar o PIN do meu cartão?", "Troque meu PIN, por favor.",
                   "Quero redefinir minha senha.", "Ajude-me a alterar a senha.",
                   "Como posso trocar o PIN do cartão?",
                   "Não quero que faça isso; só pergunto como redefinir a senha."),
        }
        for language, requests in examples.items():
            for learned in (False, True):
                for request in requests:
                    with self.subTest(language=language, learned=learned, request=request):
                        browser, now, router = self.browser(language, learned=learned)
                        browser.act({"action": "message", "text": request}, now)
                        state = browser.state(now)
                        self.assertEqual(state["messages"][-1]["status"], "unsupported")
                        self.assertIn("PIN", state["messages"][-1]["text"])
                        self.assertTrue(state["offers_handoff"])
                        self.assertEqual(state["handoff_request"], request)
                        self.assertIsNone(state["pending_draft"])
                        self.assertIsNone(state["intake_offer"])
                        self.assertEqual(browser.store.count(), 0)
                        if router is not None:
                            self.assertEqual(router.calls, 0)

    def test_negated_or_historical_changes_do_not_become_unsupported_actions(self):
        examples = {
            "es": ("No quiero cambiar mi PIN.", "Ya cambié el PIN de mi tarjeta.",
                   "Quiero ver un pago después de cambiar mi PIN.",
                   "No pregunté cómo cambiar el PIN."),
            "pt": ("Não quero trocar meu PIN.", "Já troquei o PIN do cartão.",
                   "Quero ver um pagamento depois de trocar meu PIN.",
                   "Não perguntei como trocar o PIN."),
        }
        for language, requests in examples.items():
            for learned in (False, True):
                for request in requests:
                    with self.subTest(language=language, learned=learned, request=request):
                        browser, now, _ = self.browser(language, learned=learned)
                        browser.act({"action": "message", "text": request}, now)
                        state = browser.state(now)
                        self.assertNotEqual(state["messages"][-1]["status"], "unsupported")
                        self.assertFalse(state["offers_handoff"])
                        self.assertIsNone(state["pending_draft"])
                        self.assertEqual(browser.store.count(), 0)

    def test_unrelated_request_stays_scope_clarification_without_handoff(self):
        for language, request in (("es", "Quiero una receta de sopa."),
                                  ("pt", "Quero uma receita de sopa.")):
            browser, now, _ = self.browser(language)
            browser.act({"action": "message", "text": request}, now)
            state = browser.state(now)
            self.assertEqual(state["messages"][-1]["status"], "needs_request")
            self.assertFalse(state["offers_handoff"])
            self.assertIsNone(state["pending_draft"])
            self.assertEqual(browser.store.count(), 0)

    def test_positive_scheduling_request_is_refused_outside_both_routers(self):
        examples = {
            "es": ("Programa una transferencia para mañana.", "Quiero programar un pago.",
                   "Déjame programado un depósito para el lunes.",
                   "Déjame programado un giro para el próximo mes."),
            "pt": ("Agende um pagamento para amanhã.", "Quero agendar uma transferência.",
                   "Deixe uma transferência programada para segunda-feira."),
        }
        for language, requests in examples.items():
            for learned in (False, True):
                for request in requests:
                    with self.subTest(language=language, learned=learned, request=request):
                        browser, now, router = self.browser(language, learned=learned)
                        browser.act({"action": "message", "text": request}, now)
                        state = browser.state(now)
                        self.assertEqual(state["messages"][-1]["status"], "unsupported")
                        self.assertTrue(state["offers_handoff"])
                        self.assertEqual(state["handoff_request"], request)
                        self.assertIsNone(state["pending_draft"])
                        self.assertIsNone(state["intake_offer"])
                        self.assertEqual(browser.store.count(), 0)
                        if router is not None:
                            self.assertEqual(router.calls, 0)

    def test_negated_or_historical_scheduling_stays_outside_operation_boundary(self):
        examples = {
            "es": ("No quiero programar un pago.", "Quiero ver una transferencia programada.",
                   "Programé un pago ayer; quiero consultarlo."),
            "pt": ("Não quero agendar um pagamento.", "Quero ver uma transferência agendada.",
                   "Agendei um pagamento ontem; quero consultá-lo."),
        }
        for language, requests in examples.items():
            for learned in (False, True):
                for request in requests:
                    with self.subTest(language=language, learned=learned, request=request):
                        browser, now, _ = self.browser(language, learned=learned)
                        browser.act({"action": "message", "text": request}, now)
                        state = browser.state(now)
                        self.assertNotEqual(state["messages"][-1]["status"], "unsupported")
                        self.assertFalse(state["offers_handoff"])
                        self.assertIsNone(state["pending_draft"])
                        self.assertEqual(browser.store.count(), 0)

    def test_missing_handoff_permission_exposes_no_handoff_affordance(self):
        for permissions in ((Permission.READ_TRANSACTION,),
                            (Permission.READ_TRANSACTION, Permission.CREATE_SIMULATED_INTAKE)):
            for language, requests in (
                ("es", ("Quiero cambiar mi PIN.", "Quiero un préstamo para estudiar.")),
                ("pt", ("Quero trocar meu PIN.", "Quero um empréstimo para estudar."))):
                for request in requests:
                    with self.subTest(language=language, permissions=permissions, request=request):
                        browser, now, _ = self.browser(language, permissions=permissions)
                        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
                        browser.act({"action": "message", "text": request}, now)
                        state = browser.state(now)
                        self.assertEqual(state["messages"][-1]["status"], "unsupported")
                        self.assertFalse(state["offers_handoff"])
                        self.assertIsNone(state["handoff_request"])
                        self.assertIsNone(state["handoff_offer"])
                        self.assertIsNone(state["pending_draft"])
                        self.assertIsNone(state["selected_transaction"])
                        self.assertEqual(browser.store.count(), 0)
                        with self.assertRaises(AccessDenied):
                            browser.act({"action": "prepare_handoff", "request": request}, now)
                        self.assertEqual(browser.store.count(), 0)

    def test_optional_handoff_preserves_literal_issue_and_needs_final_confirmation(self):
        for language, request in (("es", "Quiero cambiar el PIN de mi tarjeta."),
                                  ("pt", "Quero trocar o PIN do meu cartão.")):
            browser, now, _ = self.browser(language)
            browser.act({"action": "message", "text": request}, now)
            browser.act({"action": "prepare_handoff", "request": request}, now)
            state = browser.state(now)
            draft = state["pending_draft"]
            self.assertEqual(draft["kind"], "handoff")
            self.assertEqual(draft["packet"]["request"], request)
            self.assertEqual(draft["packet"]["escalation_reason"], "unsupported_request")
            self.assertIsNone(draft["packet"]["facts"])
            self.assertEqual(browser.store.count(), 0)
            browser.act({"action": "message", "text": "sí" if language == "es" else "sim"}, now)
            self.assertEqual(browser.store.count(), 0)
            browser.act({"action": "confirm", "draft_id": draft["draft_id"], "confirmed": True}, now)
            self.assertEqual(browser.store.count(), 1)
            self.assertEqual(browser.state(now)["messages"][-1]["status"], "action_verified")


if __name__ == "__main__":
    unittest.main()
