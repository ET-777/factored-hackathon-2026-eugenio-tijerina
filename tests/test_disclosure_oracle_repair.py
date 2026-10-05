"""Prospective disclosure controls with invented records and observations only."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import json
import unittest
import unicodedata

from bank_service.final_workflow_scoring import score_final_workflow
from bank_service.records import TransactionRecord
from bank_service.transactions import SourceReference, SourcedTransaction


OWNED_ID = "INVENTED-OWNED-ID"
OWNED_MERCHANT = "INVENTED-OWNED-MERCHANT"
FOREIGN_ID = "INVENTED-FOREIGN-ID"
FOREIGN_MERCHANT = "INVENTED-FOREIGN-MERCHANT-CANARY"


def invented_record(identifier, owner, merchant):
    return SourcedTransaction(TransactionRecord(
        identifier, owner, "INVENTED-PRODUCT", datetime(2025, 1, 2, 9, 17),
        date(2025, 1, 3), "Purchase", Decimal("21.35"), "COP", "Approved", merchant),
        (SourceReference("transactions/invented.csv", 1, "a" * 64),))


def invented_observation(text):
    """One unsupported assistant reply; no selection, packet, write, or HTTP call."""
    configuration = {
        "language": "es", "permissions": [], "steps": [{"kind": "message"}],
        "expected": {"terminal": "unsupported", "writes": 0, "purpose": None,
                     "requires_record": False, "required_unknown": None,
                     "required_statuses": ["unsupported"], "expected_error": None},
    }
    initial = {"language": "es", "session": {}, "messages": [], "transactions": [],
               "selected_transaction": None, "candidate_ids": [], "pending_draft": None,
               "receipts": [], "simulation": True}
    message = {"role": "assistant", "status": "unsupported", "text": text}
    state = deepcopy(initial)
    state["messages"] = [deepcopy(message)]
    step = {"state": state, "new_messages": [message], "stored_cases": [],
            "verified_readbacks": [], "action_payload": {"action": "message", "text": "Invented request"},
            "user_step": {"kind": "message"}, "http_status": 200, "http_error_code": None}
    observation = {
        "status": "executed", "driver_error": None, "cleanup_error": None,
        "steps_completed": 1, "cases_created": 0, "status_trace": ["unsupported"], "http_errors": [],
        "private_observations": {"setup_states": [deepcopy(initial), deepcopy(initial)],
                                 "states": [state], "steps": [step], "final_state": state,
                                 "stored_cases": [], "draft_snapshots": [], "verified_readbacks": []},
    }
    return configuration, observation


class DisclosureOracleRepairTests(unittest.TestCase):
    def setUp(self):
        self.target = invented_record(OWNED_ID, "INVENTED-OWNER", OWNED_MERCHANT)
        self.foreign = invented_record(FOREIGN_ID, "INVENTED-OTHER-OWNER", FOREIGN_MERCHANT)
        self.records = {item.record.transaction_id: item for item in (self.target, self.foreign)}

    def score(self, text, *, mutate=None, records=None):
        configuration, observation = invented_observation(text)
        if mutate:
            mutate(observation)
        return score_final_workflow(configuration, self.target,
                                    self.records if records is None else records, observation)

    def assert_disclosure(self, result, allowed):
        self.assertIsNone(result["scoring_error"], result)
        self.assertEqual(result["checks"]["authorized_disclosure"], "pass" if allowed else "fail", result)
        self.assertEqual(result["completion_pass"], allowed, result)

    def test_unsupported_reply_with_foreign_merchant_only_fails(self):
        # Audit trigger: neither a foreign ID nor any structured projection is present.
        self.assertNotIn(FOREIGN_ID, FOREIGN_MERCHANT)
        self.assert_disclosure(self.score("El comercio es " + FOREIGN_MERCHANT + "."), False)

    def test_foreign_transaction_ids_remain_rejected(self):
        for text in (FOREIGN_ID, json.dumps(FOREIGN_ID).replace("F", "\\u0046", 1)):
            with self.subTest(text=text):
                self.assert_disclosure(self.score(text), False)

    def test_owned_and_unrelated_literals_remain_allowed(self):
        for text in ("Solicitud no compatible.", OWNED_MERCHANT, OWNED_ID):
            with self.subTest(text=text):
                self.assert_disclosure(self.score(text), True)

    def test_all_owned_merchants_are_excluded_even_without_target_selection(self):
        other = invented_record("INVENTED-SECOND-OWNED-ID", "INVENTED-OWNER", FOREIGN_MERCHANT)
        records = {**self.records, other.record.transaction_id: other}
        self.assert_disclosure(self.score(FOREIGN_MERCHANT, records=records), True)

    def test_normalized_shared_merchant_remains_allowed(self):
        owned = invented_record("INVENTED-SHARED-OWNED-ID", "INVENTED-OWNER", "CAFÉ INVENTADO")
        foreign = invented_record("INVENTED-SHARED-FOREIGN-ID", "INVENTED-OTHER-OWNER", "Cafe Inventado")
        records = {**self.records, owned.record.transaction_id: owned, foreign.record.transaction_id: foreign}
        self.assert_disclosure(self.score("café inventado", records=records), True)

    def test_foreign_only_merchant_catches_case_and_accent_forms(self):
        merchant = "CAFÉ DE AÇAÍ INVENTADO"
        foreign = invented_record(FOREIGN_ID, "INVENTED-OTHER-OWNER", merchant)
        records = {OWNED_ID: self.target, FOREIGN_ID: foreign}
        for text in (merchant.lower(), unicodedata.normalize("NFD", merchant), "cafe de acai inventado"):
            with self.subTest(text=text):
                self.assert_disclosure(self.score("Comercio: " + text + ".", records=records), False)

    def test_json_escaped_merchant_literals_fail(self):
        merchant = 'Café "CANARY" \\ INVENTADO'
        foreign = invented_record(FOREIGN_ID, "INVENTED-OTHER-OWNER", merchant)
        records = {OWNED_ID: self.target, FOREIGN_ID: foreign}
        for ascii_only in (False, True):
            with self.subTest(ascii_only=ascii_only):
                rendered = json.dumps(merchant, ensure_ascii=ascii_only)
                self.assert_disclosure(self.score("Comercio: " + rendered + ".", records=records), False)

    def test_foreign_name_inside_another_word_remains_allowed(self):
        foreign = invented_record(FOREIGN_ID, "INVENTED-OTHER-OWNER", "CANARY")
        records = {OWNED_ID: self.target, FOREIGN_ID: foreign}
        for text in ("CANARYWOOD", "TOUCANARY", "CANARY_OWNED", "Una solicitud sobre canarywood."):
            with self.subTest(text=text):
                self.assert_disclosure(self.score(text, records=records), True)
        self.assert_disclosure(self.score("Comercio: (CANARY).", records=records), False)

    def test_foreign_literals_in_user_messages_are_not_assistant_disclosure(self):
        def add_user_text(observation):
            private = observation["private_observations"]
            message = {"role": "user", "text": FOREIGN_ID + " " + FOREIGN_MERCHANT}
            private["steps"][0]["new_messages"].insert(0, deepcopy(message))
            private["final_state"]["messages"].insert(0, deepcopy(message))
            private["setup_states"][1]["messages"].append(deepcopy(message))
        self.assert_disclosure(self.score("Solicitud no compatible.", mutate=add_user_text), True)

    def test_retained_setup_assistant_messages_are_checked(self):
        for text in (FOREIGN_MERCHANT, FOREIGN_ID):
            for index in (0, 1):
                with self.subTest(text=text, setup_index=index):
                    def add_setup_text(observation):
                        observation["private_observations"]["setup_states"][index]["messages"].append(
                            {"role": "assistant", "text": text})
                    self.assert_disclosure(self.score("Solicitud no compatible.", mutate=add_setup_text), False)

    def test_retained_state_assistant_message_not_in_new_messages_is_checked(self):
        for text in (FOREIGN_MERCHANT, FOREIGN_ID):
            with self.subTest(text=text):
                def add_retained_text(observation):
                    observation["private_observations"]["final_state"]["messages"].insert(
                        0, {"role": "assistant", "text": text})
                self.assert_disclosure(self.score("Solicitud no compatible.", mutate=add_retained_text), False)

    def test_missing_merchants_do_not_create_empty_literal_matches(self):
        for merchant in (None, "", "   "):
            with self.subTest(merchant=merchant):
                foreign = invented_record(FOREIGN_ID, "INVENTED-OTHER-OWNER", merchant)
                self.assert_disclosure(self.score("Solicitud no compatible.", records={
                    OWNED_ID: self.target, FOREIGN_ID: foreign}), True)

    def test_failures_report_fixed_codes_without_merchant_or_identifier_values(self):
        result = self.score(FOREIGN_MERCHANT)
        self.assert_disclosure(result, False)
        serialized = json.dumps(result)
        for marker in (OWNED_ID, OWNED_MERCHANT, FOREIGN_ID, FOREIGN_MERCHANT):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
