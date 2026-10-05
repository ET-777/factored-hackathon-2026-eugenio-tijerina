"""Membership privacy through real chat paths, using invented records only."""
import json
import unittest

from bank_service.routing import IntentProposal
from bank_service.final_workflow_driver import run_final_workflow
from tests.test_final_workflow_driver import NOW, case, record


OWNED = "REF-OWNEDKEY"
FOREIGN = "REF-FOREIGNKEY"
SECRET = "INVENTED-FOREIGN-MERCHANT-CANARY"


class FixedProposal:
    def route_intent(self, text, language):
        return IntentProposal("unsupported", 0.95, True)


class ReferencePrivacyTests(unittest.TestCase):
    def journey(self, request, *, foreign=None, setup=(), language="es", learned=False):
        target = record(OWNED)
        rows = {OWNED: target}
        if foreign is not None:
            rows[foreign.record.transaction_id] = foreign
        result = run_final_workflow(
            case([*setup, {"kind": "message", "text": request}], language=language),
            target, rows, FixedProposal() if learned else None, now=NOW,
        )
        self.assertEqual(result["status"], "executed", result["driver_error"])
        self.assertIsNone(result["cleanup_error"])
        state = result["private_observations"]["final_state"]
        self.assertNotIn(SECRET, json.dumps(state))
        self.assertEqual(result["cases_created"], 0)
        return result, state

    def signature(self, result, state):
        selected = state["selected_transaction"]
        draft = state["pending_draft"]
        return {
            "trace": result["status_trace"], "errors": result["http_errors"],
            "selected": None if selected is None else selected["transaction_id"],
            "candidates": state["candidate_ids"],
            "draft_kind": None if draft is None else draft["kind"],
            "draft_packet": None if draft is None else draft["packet"],
            "intake_offer": state["intake_offer"] is not None,
            "handoff_offer": state["handoff_offer"] is not None,
            "replies": [(m["status"], m["text"]) for m in state["messages"]
                        if m["role"] == "assistant"],
        }

    def test_same_generic_request_cannot_distinguish_foreign_membership(self):
        foreign = record(FOREIGN, "INVENTED-OTHER-OWNER", SECRET)
        for language in ("es", "pt"):
            for learned in (False, True):
                for request in (FOREIGN, f'"{FOREIGN}"', f"'{FOREIGN}'", f"id: {FOREIGN}"):
                    with self.subTest(language=language, learned=learned, request=request):
                        absent = self.journey(request, language=language, learned=learned)
                        present = self.journey(request, foreign=foreign, language=language,
                                               learned=learned)
                        self.assertEqual(self.signature(*absent), self.signature(*present))
                        self.assertIsNone(present[1]["selected_transaction"])

    def test_same_request_preserves_privacy_in_search_dispute_and_handoff_context(self):
        foreign = record(FOREIGN, "INVENTED-OTHER-OWNER", SECRET)
        for language, search, dispute, human in (
            ("es", "Quiero buscar una compra", "No reconozco un cargo",
             "Quiero hablar con una persona"),
            ("pt", "Quero buscar uma compra", "Não reconheço uma compra",
             "Quero falar com uma pessoa"),
        ):
            for setup in (({"kind": "select_target"},),
                          ({"kind": "message", "text": search},),
                          ({"kind": "message", "text": dispute},),
                          ({"kind": "message", "text": human},)):
                with self.subTest(language=language, setup=setup):
                    absent = self.journey(FOREIGN, setup=setup, language=language)
                    present = self.journey(FOREIGN, foreign=foreign, setup=setup,
                                           language=language)
                    self.assertEqual(self.signature(*absent), self.signature(*present))

    def test_foreign_alias_never_changes_owned_resolution(self):
        for language in ("es", "pt"):
            for stored in (f'"{OWNED}"', f"'{OWNED}'"):
                with self.subTest(language=language, stored=stored):
                    foreign = record(stored, "INVENTED-OTHER-OWNER", SECRET)
                    absent = self.journey(OWNED, language=language, learned=True)
                    present = self.journey(OWNED, foreign=foreign, language=language,
                                           learned=True)
                    self.assertEqual(self.signature(*absent), self.signature(*present))
                    self.assertEqual(present[1]["selected_transaction"]["transaction_id"], OWNED)
                    self.assertEqual(present[0]["status_trace"], ["answered"])

    def test_foreign_only_alias_cannot_make_absent_generic_id_recognizable(self):
        for stored in (f'"{FOREIGN}"', f"'{FOREIGN}'"):
            foreign = record(stored, "INVENTED-OTHER-OWNER", SECRET)
            absent = self.journey(FOREIGN)
            present = self.journey(FOREIGN, foreign=foreign)
            self.assertEqual(self.signature(*absent), self.signature(*present))

    def test_authorized_quoted_key_stays_exact_and_masks_embedded_slots(self):
        key = '"REF-USD-2026-06-17"'
        target = record(key)
        for language in ("es", "pt"):
            result = run_final_workflow(
                case([{"kind": "message", "text": key[1:-1]}], language=language),
                target, {key: target}, FixedProposal(), now=NOW,
            )
            self.assertEqual(result["status"], "executed")
            state = result["private_observations"]["final_state"]
            self.assertEqual(state["selected_transaction"]["transaction_id"], key)
            self.assertEqual(result["status_trace"], ["answered"])
            self.assertEqual(result["cases_created"], 0)
            self.assertIsNone(state["pending_draft"])


if __name__ == "__main__":
    unittest.main()
