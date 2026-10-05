"""Portuguese selection continuity with invented transactions, not final cases."""
import unittest
from datetime import datetime, timezone

from bank_service.learned_routing import GuardedPreviewRouter
from bank_service.routing import refers_to_selected_transaction
from bank_service.web_app import DemoServer
from tests.test_learned_router_repair import FixedModel


class SelectedCobrancaTests(unittest.TestCase):
    def test_selected_charge_wording_preserves_two_stage_review(self):
        for learned in (False, True):
            with self.subTest(learned=learned):
                server = DemoServer(0, router=GuardedPreviewRouter(FixedModel("unsupported"))
                                    if learned else None)
                try:
                    _, browser = server.mint_session()
                    now = datetime.now(timezone.utc)
                    browser.act({"action": "language", "language": "pt"}, now)
                    identifier = browser.state(now)["transactions"][0]["transaction_id"]
                    browser.act({"action": "inquire", "transaction_id": identifier}, now)
                    browser.act({"action": "message", "text": "Não reconheço esta cobrança"}, now)
                    state = browser.state(now)
                    self.assertEqual(state["selected_transaction"]["transaction_id"], identifier)
                    self.assertEqual(state["intake_offer"]["transaction_id"], identifier)
                    self.assertIsNone(state["pending_draft"])
                    self.assertEqual(browser.store.count(), 0)
                    browser.act({"action": "intake_decision", "offer_id": state["intake_offer"]["offer_id"],
                                 "prepare": True}, now)
                    state = browser.state(now)
                    self.assertEqual(state["pending_draft"]["kind"], "intake")
                    self.assertEqual(browser.store.count(), 0)
                    browser.act({"action": "confirm", "draft_id": state["pending_draft"]["draft_id"],
                                 "confirmed": True}, now)
                    self.assertEqual(browser.store.count(), 1)
                    self.assertEqual(browser.messages[-1]["status"], "action_verified")
                finally:
                    server.server_close()

    def test_another_charge_or_plural_never_reuses_singular_selection(self):
        for text in ("Não reconheço outra cobrança", "Não reconheço essas cobranças",
                     "Outra cobrança diferente desta cobrança", "Uma nova cobrança"):
            with self.subTest(text=text):
                self.assertFalse(refers_to_selected_transaction(text, "pt"))
        self.assertTrue(refers_to_selected_transaction("Não reconheço esta cobrança", "pt"))


if __name__ == "__main__":
    unittest.main()
