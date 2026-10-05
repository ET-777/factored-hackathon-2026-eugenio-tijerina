"""Invented bilingual request forms for post-exposure serving-policy repairs.

No private record, exposed evaluation utterance or unopened final case is loaded.
These regressions establish specific intent/consent behavior, not held-out gains.
"""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bank_service.learned_routing import GuardedPreviewRouter
from bank_service.route_loader import load_short_preview_router
from bank_service.routing import IntentProposal
from bank_service.web_app import BrowserSession, _now


class MisleadingModel:
    def __init__(self, intent):
        self.intent = intent

    def route_intent(self, text, language):
        return IntentProposal(self.intent, 0.999, True)


class PostRepairDisputeIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = load_short_preview_router()

    def browser(self, language):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        browser = BrowserSession(Path(temporary.name) / "cases.sqlite3", router=self.router)
        self.addCleanup(browser.close)
        now = _now()
        browser.act({"action": "language", "language": language}, now)
        return browser, now

    def test_explicit_financial_review_requests_override_an_incorrect_read_label(self):
        router = GuardedPreviewRouter(MisleadingModel("inquiry"))
        requests = (
            ("es", "Detecté una diferencia en la compra. Me gustaría registrar un reclamo."),
            ("es", "Este débito parece incorrecto; necesito abrir una solicitud de análisis."),
            ("es", "Hay un problema con el pago. Quisiera presentar una solicitud de revisión."),
            ("pt", "Percebi uma diferença na compra. Gostaria de registrar uma reclamação."),
            ("pt", "Este débito parece incorreto; preciso abrir uma solicitação de análise."),
            ("pt", "Há um problema com o pagamento. Eu quero apresentar um pedido de revisão."),
        )
        for language, text in requests:
            with self.subTest(language=language, text=text):
                self.assertEqual(router.route_intent(text, language),
                                 IntentProposal("dispute_intake", 1.0, True))

    def test_reported_problem_requires_a_positive_request_and_financial_antecedent(self):
        router = GuardedPreviewRouter(MisleadingModel("inquiry"))
        for language, text in (
            ("es", "Esta compra parece extraña. Quisiera reportarla."),
            ("es", "El pago presenta un error; necesito comunicar el problema."),
            ("pt", "Esta compra parece estranha. Quero relatar o problema."),
            ("pt", "O pagamento apresenta um erro; preciso comunicar o problema."),
        ):
            with self.subTest(language=language, text=text):
                self.assertEqual(router.route_intent(text, language).intent, "dispute_intake")

    def test_negation_history_third_party_and_unrelated_requests_create_no_review(self):
        cases = (
            ("es", "No quiero registrar una reclamación por esta compra."),
            ("es", "No quiero reportar el problema de esta compra."),
            ("es", "Quiero registrar que no deseo una reclamación sobre este cargo."),
            ("es", "La agente dijo quiero registrar un reclamo de este pago."),
            ("es", "Ayer registré una solicitud de revisión de mi compra."),
            ("es", "Quiero registrar una reclamación por el partido de fútbol."),
            ("es", "Quiero comunicar que no existe ningún problema con este pago."),
            ("pt", "Não quero registrar uma reclamação por esta compra."),
            ("pt", "Não quero comunicar o problema deste pagamento."),
            ("pt", "Quero registrar que não quero uma reclamação sobre este débito."),
            ("pt", "A atendente disse quero registrar uma reclamação deste pagamento."),
            ("pt", "Ontem registrei um pedido de revisão da compra."),
            ("pt", "Quero registrar uma reclamação sobre o jogo de futebol."),
            ("pt", "Quero comunicar que não existe nenhum problema com este pagamento."),
        )
        for language, text in cases:
            with self.subTest(language=language, text=text):
                proposal = GuardedPreviewRouter(MisleadingModel("dispute_intake")).route_intent(text, language)
                self.assertNotIn(proposal.intent, ("dispute_intake", "human_request"))
                browser, now = self.browser(language)
                browser.message(text, now)
                self.assertIsNone(browser.intake_offer)
                self.assertIsNone(browser.handoff_offer)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.store.count(), 0)

    def test_new_banking_actions_retain_unsupported_precedence(self):
        for language, text in (
            ("es", "Quiero registrar un reclamo por este cargo y transferir dinero."),
            ("es", "Quiero comunicar el problema con mi compra; devuelve mi dinero."),
            ("pt", "Quero registrar uma reclamação desta compra e transferir dinheiro."),
            ("pt", "Quero comunicar o problema com o pagamento; reembolse agora."),
        ):
            with self.subTest(language=language, text=text):
                self.assertEqual(self.router.route_intent(text, language).intent, "unsupported")
                browser, now = self.browser(language)
                browser.message(text, now)
                self.assertIsNone(browser.intake_offer)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.store.count(), 0)

    def test_comparison_reads_start_inquiry_without_review_offer(self):
        for language, text in (("es", "Quisiera cotejar una compra."),
                               ("pt", "Quero comparar um lançamento.")):
            with self.subTest(language=language, text=text):
                browser, now = self.browser(language)
                browser.message(text, now)
                self.assertEqual(browser.pending_search.kind, "inquiry")
                self.assertEqual(browser.messages[-1]["status"], "needs_filters")
                self.assertIsNone(browser.intake_offer)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.store.count(), 0)

    def test_negated_comparison_requests_abstain_even_with_a_read_model_label(self):
        router = GuardedPreviewRouter(MisleadingModel("inquiry"))
        for language, text in (("es", "No quiero cotejar esta compra."),
                               ("pt", "Não quero comparar este lançamento.")):
            with self.subTest(language=language):
                self.assertEqual(router.route_intent(text, language),
                                 IntentProposal("unsupported", 0.0, False))

    def test_review_purpose_survives_selection_and_separate_consent_steps(self):
        for language, text, assent in (
            ("es", "Hay una diferencia en esta compra; necesito registrar un reclamo.", "Sí"),
            ("pt", "Há uma diferença nesta compra; preciso registrar uma reclamação.", "Sim"),
        ):
            with self.subTest(language=language):
                browser, now = self.browser(language)
                browser.message(text, now)
                self.assertEqual(browser.pending_search.kind, "intake")
                self.assertEqual(browser.pending_search.request, text)
                browser.message("25.50 USD", now)
                self.assertEqual(len(browser.candidate_ids), 2)
                browser.act({"action": "choose", "transaction_id": "DEMO-TX-001"}, now)
                offer = browser.intake_offer
                self.assertIsNotNone(offer)
                self.assertEqual(offer.request, text)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.store.count(), 0)
                browser.act({"action": "intake_decision", "offer_id": offer.offer_id,
                             "prepare": True}, now)
                draft = browser.pending_draft
                self.assertEqual(browser.store.count(), 0)
                browser.message(assent, now)
                self.assertIs(browser.pending_draft, draft)
                self.assertEqual(browser.store.count(), 0)
                for _ in range(2):
                    browser.act({"action": "confirm", "draft_id": draft.draft_id,
                                 "confirmed": True}, now)
                self.assertEqual(browser.store.count(), 1)
                receipt = browser.actions.read_case(browser.session, browser.case_ids[0], now=now)
                packet = json.loads(receipt.payload_json)
                self.assertEqual(packet["reason"], text)
                self.assertEqual(packet["facts"]["transaction_id"], "DEMO-TX-001")
                self.assertIs(packet["consent"], True)

    def test_withdrawal_review_uses_contextual_handoff_with_explicit_consent(self):
        for language, text in (
            ("es", "Hay una diferencia en este retiro; necesito registrar un reclamo."),
            ("pt", "Há uma diferença neste saque; preciso registrar uma reclamação."),
        ):
            with self.subTest(language=language):
                browser, now = self.browser(language)
                entry = browser.records["DEMO-TX-001"]
                browser.records["DEMO-TX-001"] = replace(entry, record=replace(
                    entry.record, transaction_type="Withdrawal"))
                browser.message(text, now)
                self.assertEqual(browser.pending_search.kind, "intake")
                browser.message("DEMO-TX-001", now)
                offer = browser.handoff_offer
                self.assertIsNotNone(offer)
                self.assertEqual(offer.request, text)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.store.count(), 0)
                browser.act({"action": "handoff_decision", "offer_id": offer.offer_id,
                             "prepare": True}, now)
                draft = browser.pending_draft
                browser.act({"action": "confirm", "draft_id": draft.draft_id,
                             "confirmed": True}, now)
                receipt = browser.actions.read_case(browser.session, browser.case_ids[0], now=now)
                packet = json.loads(receipt.payload_json)
                self.assertEqual(receipt.kind, "handoff")
                self.assertEqual(packet["escalation_reason"], "ineligible_intake")
                self.assertEqual(packet["request"], text)
                self.assertEqual(packet["facts"]["transaction_type"], "Withdrawal")
                self.assertIs(packet["consent"], True)


if __name__ == "__main__":
    unittest.main()
