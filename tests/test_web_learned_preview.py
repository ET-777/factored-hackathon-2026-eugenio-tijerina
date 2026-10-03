"""Routing proposals never replace shared slots, consent or access controls."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bank_service.access import AccessDenied, Permission
from bank_service.demo_fixtures import DEMO_CUSTOMER, demo_records
from bank_service.routing import IntentProposal, RoutingError
from bank_service.web_app import BrowserSession, DemoServer, PrivateCohortConfig, _now


class CountingRouter:
    def __init__(self, proposal):
        self.proposal, self.calls = proposal, 0

    def route_intent(self, text, language):
        self.calls += 1
        return self.proposal


class LearnedPreviewWorkflowTests(unittest.TestCase):
    def browser(self, proposal):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        router = CountingRouter(proposal)
        browser = BrowserSession(Path(directory.name) / "cases.sqlite3", router=router)
        self.addCleanup(browser.close)
        return browser, router

    def test_learned_proposal_collects_slots_without_reclassifying_them(self):
        browser, router = self.browser(IntentProposal("dispute_intake", 0.8, True))
        now = _now()
        original = "Este cobro tiene un problema que necesito revisar"
        browser.message(original, now)
        browser.message("USD", now)
        browser.message("25,5", now)
        self.assertEqual(router.calls, 1)
        self.assertEqual(browser.pending_search.request, original)
        self.assertEqual(browser.pending_search.kind, "intake")
        self.assertEqual(len(browser.candidate_ids), 2)
        self.assertEqual(browser.store.count(), 0)
        self.assertEqual(browser.state(now)["route_mode"], "learned_preview")

    def test_preparation_assent_and_pending_draft_bypass_model(self):
        browser, router = self.browser(IntentProposal("dispute_intake", 0.8, True))
        now = _now()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
        browser.message("No reconozco esta compra", now)
        self.assertIsNotNone(browser.intake_offer)
        browser.message("si", now)
        draft = browser.pending_draft
        self.assertIsNotNone(draft)
        self.assertEqual(router.calls, 1)
        self.assertEqual(browser.store.count(), 0)
        browser.message("si", now)
        self.assertEqual(router.calls, 1)
        self.assertEqual(browser.store.count(), 0)
        browser.act({"action": "confirm", "draft_id": draft.draft_id, "confirmed": True}, now)
        self.assertEqual(browser.store.count(), 1)

    def test_model_never_grants_foreign_record_access(self):
        browser, router = self.browser(IntentProposal("inquiry", 1.0, True))
        with self.assertRaises(AccessDenied):
            browser.act({"action": "message", "text": "Quiero ver DEMO-TX-003"}, _now())
        self.assertEqual(router.calls, 1)
        self.assertIsNone(browser.selected_id)
        self.assertEqual(browser.store.count(), 0)

    def test_explicit_operation_context_is_shared_and_new_filters_take_precedence(self):
        for learned in (False, True):
            for language, text in (("es", "Quiero consultar esta operación"),
                                   ("pt", "Quero consultar os dados desta operação")):
                with self.subTest(learned=learned, language=language):
                    browser, router = self.browser(IntentProposal("inquiry", 0.9, True))
                    if not learned:
                        browser.router = None
                    now = _now()
                    browser.act({"action": "language", "language": language}, now)
                    browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, now)
                    browser.message(text, now)
                    self.assertEqual(browser.selected_id, "DEMO-TX-001")
                    self.assertIsNone(browser.pending_search)
                    self.assertEqual(browser.store.count(), 0)
                    self.assertEqual(router.calls, 1 if learned else 0)
                    browser.message(text + " 9999 USD", now)
                    self.assertIsNone(browser.selected_id)
                    self.assertEqual(browser.store.count(), 0)

    def test_invalid_proposals_are_refused_without_actions(self):
        for proposal in (None, {"intent": "inquiry"},
                         IntentProposal("pay", 1.0, True),
                         IntentProposal("inquiry", float("nan"), True),
                         IntentProposal("inquiry", 2.0, True),
                         IntentProposal("inquiry", True, True),
                         IntentProposal("inquiry", 0.8, "yes"),
                         IntentProposal("human_request", 0.0, False)):
            with self.subTest(proposal=proposal):
                browser, _ = self.browser(proposal)
                with self.assertRaisesRegex(RoutingError, "^invalid_intent_proposal$"):
                    browser.message("Solicitud de prueba", _now())
                self.assertEqual(browser.store.count(), 0)

    def test_new_and_replacement_sessions_preserve_router_and_private_scopes(self):
        router = CountingRouter(IntentProposal("inquiry", 0.9, True))
        scopes = frozenset({Permission.READ_TRANSACTION})
        config = PrivateCohortConfig(demo_records(), DEMO_CUSTOMER, scopes)
        server = DemoServer(0, config=config, router=router)
        self.addCleanup(server.server_close)
        old_token, first = server.mint_session()
        _, second = server.mint_session()
        server.retire_session(old_token)
        _, replacement = server.mint_session()
        for browser in (second, replacement):
            self.assertIs(browser.router, router)
            self.assertEqual(browser.session.customer_id, DEMO_CUSTOMER)
            self.assertEqual(browser.session.permissions, scopes)
            self.assertEqual(browser.state(_now())["route_mode"], "learned_preview")
        self.assertTrue(first.retired)

    def test_default_remains_keyword_baseline(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        browser = BrowserSession(Path(directory.name) / "cases.sqlite3")
        self.addCleanup(browser.close)
        self.assertEqual(browser.state(_now())["route_mode"], "keyword_baseline")


if __name__ == "__main__":
    unittest.main()
