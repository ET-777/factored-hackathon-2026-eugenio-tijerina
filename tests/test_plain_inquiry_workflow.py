"""Plain read requests must not inherit a classifier's proposed write intent."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bank_service.routing import IntentProposal
from bank_service.web_app import BrowserSession, _now


class CountingRouter:
    def __init__(self, intent):
        self.proposal = IntentProposal(intent, 1.0, True)
        self.calls = 0

    def route_intent(self, text, language):
        self.calls += 1
        return self.proposal


class PlainInquiryWorkflowTests(unittest.TestCase):
    def browser(self, intent=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        router = None if intent is None else CountingRouter(intent)
        browser = BrowserSession(Path(directory.name) / "cases.sqlite3", router=router)
        self.addCleanup(browser.close)
        return browser, router

    def assert_read_only(self, browser):
        self.assertIsNone(browser.intake_offer)
        self.assertIsNone(browser.handoff_offer)
        self.assertFalse(browser.offers_handoff)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)

    def test_plain_request_collects_details_despite_wrong_business_proposals(self):
        for intent in (None, "unsupported", "dispute_intake", "human_request"):
            for language, request in (("es", "ver un pago"), ("pt", "ver um pagamento")):
                with self.subTest(intent=intent, language=language):
                    browser, router = self.browser(intent)
                    now = _now()
                    browser.act({"action": "language", "language": language}, now)
                    browser.message(request, now)
                    self.assertEqual(browser.pending_search.kind, "inquiry")
                    self.assertEqual(browser.pending_search.request, request)
                    self.assertEqual(browser.messages[-1]["status"], "needs_filters")
                    self.assertEqual(browser.candidate_ids, ())
                    self.assertIsNone(browser.selected_id)
                    self.assert_read_only(browser)
                    if router is not None:
                        self.assertEqual(router.calls, 0)
                    browser.message("USD", now)
                    browser.message("25.50", now)
                    self.assertEqual(len(browser.candidate_ids), 2)
                    browser.act({"action": "choose", "transaction_id": "DEMO-TX-001"}, now)
                    self.assertEqual(browser.messages[-1]["status"], "answered")
                    self.assertEqual(browser.selected_id, "DEMO-TX-001")
                    self.assertIsNone(browser.pending_search)
                    self.assert_read_only(browser)
                    if router is not None:
                        self.assertEqual(router.calls, 0)

    def test_new_read_request_replaces_an_unfinished_dispute(self):
        browser, router = self.browser("dispute_intake")
        now = _now()
        browser.message("No reconozco un cargo", now)
        self.assertEqual(browser.pending_search.kind, "intake")
        browser.message("quiero ver un pago", now)
        self.assertEqual(browser.pending_search.kind, "inquiry")
        self.assertEqual(browser.pending_search.request, "quiero ver un pago")
        self.assertIsNone(browser.pending_route)
        self.assertIsNone(browser.business_issue)
        self.assertEqual(router.calls, 1)
        browser.message("2026-06-16", now)
        self.assertEqual(len(browser.candidate_ids), 2)
        browser.act({"action": "choose", "transaction_id": "DEMO-TX-001"}, now)
        self.assertEqual(browser.selected_id, "DEMO-TX-001")
        self.assertEqual(browser.messages[-1]["status"], "answered")
        self.assert_read_only(browser)

    def test_new_read_request_clears_old_intake_offer_without_accepting_it(self):
        browser, router = self.browser("dispute_intake")
        now = _now()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
        browser.message("No reconozco esta compra", now)
        self.assertIsNotNone(browser.intake_offer)
        browser.message("Buscar una compra", now)
        self.assertEqual(browser.messages[-1]["status"], "needs_filters")
        self.assertIsNone(browser.selected_id)
        self.assertIsNone(browser.business_issue)
        self.assertEqual(browser.pending_search.kind, "inquiry")
        self.assertEqual(router.calls, 1)
        self.assert_read_only(browser)

    def test_only_explicit_selected_reference_can_reuse_current_record(self):
        for text, expected_id in (("ver un pago", None),
                                  ("Quiero consultar esta transacción", "DEMO-TX-001")):
            with self.subTest(text=text):
                browser, router = self.browser("human_request")
                now = _now()
                browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
                browser.message(text, now)
                self.assertEqual(browser.selected_id, expected_id)
                self.assertEqual(router.calls, 0)
                self.assert_read_only(browser)

    def test_read_request_does_not_submit_or_replace_a_pending_draft(self):
        browser, router = self.browser("dispute_intake")
        now = _now()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
        browser.message("No reconozco esta compra", now)
        browser.message("sí", now)
        draft = browser.pending_draft
        self.assertIsNotNone(draft)
        browser.message("ver un pago", now)
        self.assertIs(browser.pending_draft, draft)
        self.assertEqual(browser.messages[-1]["status"], "confirmation_required")
        self.assertEqual(browser.store.count(), 0)
        self.assertEqual(router.calls, 1)


if __name__ == "__main__":
    unittest.main()
