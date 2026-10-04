"""TRAIN-only integration regressions on owner-reported short requests.

Uses existing independently authored fictional records. No development/final
workload, source row or private cohort is loaded. These are software checks,
not an accuracy estimate.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bank_service.route_loader import load_short_preview_router
from bank_service.routing import IntentProposal
from bank_service.web_app import BrowserSession, _denies_selected_transaction, _now


class ShortPreviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = load_short_preview_router()

    def browser(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        browser = BrowserSession(Path(directory.name) / "cases.sqlite3", router=self.router)
        self.addCleanup(browser.close)
        return browser

    def test_short_payment_inquiry_collects_details_without_proposing_a_case(self):
        browser, now = self.browser(), _now()
        browser.message("quiero ver un pago", now)
        self.assertEqual(browser.pending_search.kind, "inquiry")
        self.assertEqual(browser.messages[-1]["status"], "needs_filters")
        browser.message("25.50 USD", now)
        self.assertIn("DEMO-TX-001", browser.candidate_ids)
        browser.act({"action": "choose", "transaction_id": "DEMO-TX-001"}, now)
        self.assertEqual(browser.selected_id, "DEMO-TX-001")
        self.assertEqual(browser.messages[-1]["status"], "answered")
        self.assertIsNone(browser.intake_offer)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)

    def test_misspelled_denial_preserves_allegation_and_requires_both_consent_steps(self):
        browser, now = self.browser(), _now()
        allegation = "yo no hize esto"
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
        browser.message(allegation, now)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)
        offer = browser.intake_offer
        self.assertIsNotNone(offer)
        self.assertEqual(offer.transaction_id, "DEMO-TX-001")
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)
        browser.act({"action": "intake_decision", "offer_id": offer.offer_id,
                     "prepare": True}, now)
        draft = browser.pending_draft
        self.assertIsNotNone(draft)
        self.assertEqual(browser.store.count(), 0)
        browser.message("si", now)
        self.assertEqual(browser.store.count(), 0)
        self.assertEqual(browser.pending_draft.draft_id, draft.draft_id)
        for _ in range(2):
            browser.act({"action": "confirm", "draft_id": draft.draft_id,
                         "confirmed": True}, now)
        self.assertEqual(browser.store.count(), 1)
        self.assertEqual(len(browser.case_ids), 1)
        receipt = browser.actions.read_case(browser.session, browser.case_ids[0], now=now)
        packet = json.loads(receipt.payload_json)
        self.assertEqual(packet["reason"], allegation)
        self.assertEqual(packet["facts"]["transaction_id"], "DEMO-TX-001")
        self.assertIs(packet["consent"], True)
        self.assertIs(packet["simulated"], True)

    def test_new_payment_request_never_turns_into_an_existing_charge_dispute(self):
        browser, now = self.browser(), _now()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
        browser.message("quiero hacer un pago", now)
        self.assertEqual(browser.messages[-1]["status"], "unsupported")
        self.assertIsNone(browser.pending_search)
        self.assertIsNone(browser.intake_offer)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)

    def test_denial_uses_the_latest_selection_in_both_languages_despite_a_wrong_model(self):
        class WrongRouter:
            def route_intent(self, text, language):
                raise AssertionError("Selected denial must bypass model classification")

        for language, text in (("es", "yo no hize esto"), ("pt", "eu nao fis isso")):
            for use_model in (False, True):
                with self.subTest(language=language, use_model=use_model):
                    browser, now = self.browser(), _now()
                    browser.router = WrongRouter() if use_model else None
                    browser.act({"action": "language", "language": language}, now)
                    for identifier in ("DEMO-TX-001", "DEMO-TX-002"):
                        browser.act({"action": "inquire", "transaction_id": identifier}, now)
                    browser.message(text, now)
                    self.assertEqual(browser.intake_offer.transaction_id, "DEMO-TX-002")
                    self.assertIsNone(browser.pending_draft)
                    self.assertEqual(browser.store.count(), 0)

    def test_without_selected_record_denial_does_not_guess_a_transaction_or_create_a_draft(self):
        class AbstainingRouter:
            def route_intent(self, text, language):
                return IntentProposal("unsupported", 0.0, False)

        browser, now = self.browser(), _now()
        browser.router = AbstainingRouter()
        browser.message("yo no hize esto", now)
        self.assertIsNone(browser.selected_id)
        self.assertIsNone(browser.intake_offer)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)


class SelectedDenialGrammarTests(unittest.TestCase):
    def test_past_action_denials_accept_bounded_spanish_and_portuguese_typos(self):
        for language, text in (("es", "yo no hize esto"), ("es", "No autoricé ese pago."),
                               ("pt", "eu nao fis isso"), ("pt", "Não comprei essa compra.")):
            with self.subTest(language=language, text=text):
                self.assertTrue(_denies_selected_transaction(text, language))

    def test_negated_intentions_narratives_and_mixed_commands_are_not_denials(self):
        for language, text in (("es", "no quiero hacer un pago"), ("es", "yo hice esto"),
                               ("es", "yo no hize esto y devuélveme el dinero"),
                               ("es", "¿yo no hice esto?"),
                               ("es", "yo no hize esto？"),
                               ("es", "no hice esto, abre un ticket"),
                               ("pt", "não quero fazer um pagamento"),
                               ("pt", "eu fiz isso"), ("pt", "eu nao fis isso?"),
                               ("pt", "eu nao fis isso？"),
                               ("pt", "eu nao fis isso e reembolsa")):
            with self.subTest(language=language, text=text):
                self.assertFalse(_denies_selected_transaction(text, language))


if __name__ == "__main__":
    unittest.main()
