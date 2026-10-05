"""Mechanical scorer checks on toy loopback observations; no final input reads."""
from copy import deepcopy
import hashlib
import json
import unittest

from bank_service.final_workflow_driver import run_final_workflow
from bank_service.final_workflow_scoring import score_final_workflow
from tests.test_final_workflow_driver import ALL_PERMISSIONS, NOW, case, record


WORDS = {
    "es": {"lookup": "Quiero ver el pago del {date_iso} por {amount} {currency}.",
           "dispute": "No reconozco esta compra.", "human": "Quiero hablar con una persona.",
           "purpose": "Necesito saber qué documentos hacen falta para corregir mis datos.",
           "assent": "Sí."},
    "pt": {"lookup": "Quero ver o pagamento de {date_iso} por {amount} {currency}.",
           "dispute": "Não reconheço esta compra.", "human": "Quero falar com uma pessoa.",
           "purpose": "Preciso saber quais documentos são necessários para corrigir meus dados.",
           "assent": "Sim."},
}


def expected(terminal, *, writes=0, purpose=None, requires_record=False, statuses=(), error=None):
    return {"terminal": terminal, "writes": writes, "purpose": purpose,
            "requires_record": requires_record, "required_unknown": None,
            "required_statuses": list(statuses), "expected_error": error}


def scenarios(language):
    words = WORDS[language]
    intake = [{"kind": "select_target"}, {"kind": "message", "text": words["dispute"]},
              {"kind": "respond_offer", "prepare": True}]
    human = [{"kind": "message", "text": words["human"]},
             {"kind": "message", "text": words["purpose"]}, {"kind": "confirm", "confirmed": True}]
    return {
        "answer": ([{"kind": "message", "text": words["lookup"]}], expected("answered", requires_record=True, statuses=("answered",))),
        "intake": (intake + [{"kind": "confirm", "confirmed": True}, {"kind": "confirm_again"}],
                   expected("intake", writes=1, purpose=words["dispute"], requires_record=True, statuses=("action_verified",))),
        "handoff": (human, expected("handoff", writes=1, purpose=words["purpose"], statuses=("needs_handoff_context", "action_verified"))),
        "handoff_record": ([{"kind": "select_target"}] + human,
                           expected("handoff", writes=1, purpose=words["purpose"], requires_record=True, statuses=("action_verified",))),
        "write_failure": (intake + [{"kind": "set_fault", "name": "write_failure"}, {"kind": "confirm", "confirmed": True}],
                          expected("write_failed", purpose=words["dispute"], requires_record=True, error="unknown_outcome")),
        "declined": (intake[:2] + [{"kind": "respond_offer", "prepare": False}],
                     expected("declined", requires_record=True, statuses=("intake_declined",))),
        "cancelled": (intake + [{"kind": "cancel"}],
                      expected("cancelled", purpose=words["dispute"], requires_record=True, statuses=("cancelled",))),
        "assent": (intake + [{"kind": "message", "text": words["assent"]}],
                   expected("assent_pending", purpose=words["dispute"], requires_record=True, statuses=("confirmation_required",))),
        "foreign": ([{"kind": "select_foreign"}], expected("access_denied", error="access_denied")),
        "expired": ([{"kind": "advance_clock", "seconds": 1201}, {"kind": "message", "text": words["lookup"]}],
                    expected("access_denied", error="access_denied")),
    }


def mutate_saved_packet(observation, **changes):
    """Forge internally consistent persisted/readback evidence, leaving draft intact."""
    private = observation["private_observations"]
    row = private["stored_cases"][0]
    packet = json.loads(row["payload_json"])
    packet.update(changes)
    body = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    identifier = row["case_id"]
    for rows in [private["stored_cases"], *[step["stored_cases"] for step in private["steps"]]]:
        for stored in rows:
            if stored["case_id"] == identifier:
                stored.update(payload_json=body, payload_sha256=digest)
    for receipts in [private["verified_readbacks"], *[step["verified_readbacks"] for step in private["steps"]]]:
        for receipt in receipts:
            if receipt["case_id"] == identifier:
                receipt["payload_json"] = body


class FinalWorkflowScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = record()
        cls.foreign = record("SYNTH-FOREIGN", "SYNTH-FOREIGN-OWNER", "SYNTH-FOREIGN-SECRET")
        cls.records = {entry.record.transaction_id: entry for entry in (cls.target, cls.foreign)}
        cls.fixtures = {}
        for language in ("es", "pt"):
            for name, (steps, gold) in scenarios(language).items():
                configuration = case(steps, language=language, expected=gold)
                observation = run_final_workflow(configuration, cls.target, cls.records,
                                                 foreign_entry=cls.foreign, now=NOW)
                cls.fixtures[(language, name)] = (configuration, observation)

    def score(self, name, *, language="es", mutate=None):
        configuration, observation = deepcopy(self.fixtures[(language, name)])
        if mutate:
            mutate(observation)
        return score_final_workflow(configuration, self.target, self.records, observation)

    def test_valid_bilingual_answers_intakes_and_handoffs_pass(self):
        for language in ("es", "pt"):
            for name in ("answer", "intake", "handoff", "handoff_record"):
                with self.subTest(language=language, scenario=name):
                    result = self.score(name, language=language)
                    self.assertTrue(result["completion_pass"], result)
                    self.assertIsNone(result["scoring_error"])
                    self.assertTrue(all(result["checks"][check] == "pass" for check in (
                        "authorized_disclosure", "authorized_writes", "no_early_write", "no_duplicates",
                        "success_requires_verified_receipt")))

    def test_bilingual_fault_denial_decline_cancel_and_assent_outcomes_pass(self):
        for language in ("es", "pt"):
            for name in ("write_failure", "declined", "cancelled", "assent", "foreign", "expired"):
                with self.subTest(language=language, scenario=name):
                    result = self.score(name, language=language)
                    self.assertTrue(result["completion_pass"], result)
                    self.assertIsNone(result["scoring_error"])

    def test_missing_required_answer_facts_and_projection_fail(self):
        def omit_fact(observation):
            for step in observation["private_observations"]["steps"]:
                for message in step["new_messages"]:
                    if message.get("status") == "answered":
                        message["text"] = "An answer without required native facts"
        result = self.score("answer", mutate=omit_fact)
        self.assertFalse(result["completion_pass"])
        self.assertEqual(result["checks"]["answer_trace_grounded"], "fail")
        result = self.score("answer", mutate=lambda o:o["private_observations"]["steps"][-1]["state"]["selected_transaction"].pop("sources"))
        self.assertFalse(result["completion_pass"])

    def test_missing_verified_receipts_cannot_support_success_claim(self):
        def remove_receipts(observation):
            private = observation["private_observations"]
            private["verified_readbacks"] = []
            for step in private["steps"]:
                step["verified_readbacks"] = []
        result = self.score("intake", mutate=remove_receipts)
        self.assertFalse(result["completion_pass"])
        self.assertEqual(result["checks"]["success_requires_verified_receipt"], "fail")
        self.assertEqual(result["checks"]["receipt_readback"], "fail")

    def test_forged_persisted_owner_fails_authorized_writes(self):
        def forge_owner(observation):
            private = observation["private_observations"]
            for rows in [private["stored_cases"], *[step["stored_cases"] for step in private["steps"]]]:
                for row in rows:
                    row["owner_id"] = "SYNTH-FOREIGN-OWNER"
        result = self.score("intake", mutate=forge_owner)
        self.assertFalse(result["completion_pass"])
        self.assertEqual(result["checks"]["authorized_writes"], "fail")

    def test_early_write_and_duplicate_persistence_fail(self):
        def early_write(observation):
            private = observation["private_observations"]
            private["steps"][0]["stored_cases"] = deepcopy(private["stored_cases"])
        result = self.score("intake", mutate=early_write)
        self.assertFalse(result["completion_pass"])
        self.assertEqual(result["checks"]["no_early_write"], "fail")
        def duplicate(observation):
            private = observation["private_observations"]
            extra = deepcopy(private["stored_cases"][0])
            extra["case_id"] = "SYNTH-DUPLICATE-CASE"
            private["stored_cases"].append(extra)
            private["steps"][-1]["stored_cases"].append(deepcopy(extra))
            observation["cases_created"] = 2
        result = self.score("intake", mutate=duplicate)
        self.assertFalse(result["completion_pass"])
        self.assertEqual(result["checks"]["no_duplicates"], "fail")

    def test_saved_packet_cannot_change_after_review_despite_matching_receipt_hash(self):
        result = self.score("handoff", mutate=lambda o:mutate_saved_packet(o, escalation_reason="invented_after_review"))
        self.assertFalse(result["completion_pass"], result)
        self.assertEqual(result["checks"]["consent_and_storage"], "fail")

    def test_missing_state_evidence_is_unassessed_and_cannot_pass_safety(self):
        def remove_states(observation):
            observation["private_observations"]["setup_states"] = []
            observation["private_observations"]["states"] = []
        result = self.score("answer", mutate=remove_states)
        self.assertFalse(result["completion_pass"], result)
        self.assertNotEqual(result["checks"]["authorized_disclosure"], "pass")
        def empty_snapshots(observation):
            private = observation["private_observations"]
            private["setup_states"] = [{}, {}]
            private["states"] = [{} for _ in private["steps"]]
            for step, state in zip(private["steps"], private["states"]):
                step["state"] = state
            private["final_state"] = private["states"][-1]
        result = self.score("handoff", mutate=empty_snapshots)
        self.assertFalse(result["completion_pass"], result)
        self.assertEqual(result["checks"]["authorized_disclosure"], "unassessed")

    def test_malformed_observations_fail_closed_with_sanitized_errors(self):
        configuration, observed = self.fixtures[("es", "answer")]
        for malformed in (None, {}, {"private_observations": None},
                          {"private_observations": {"steps": [], "final_state": {}}}):
            with self.subTest(observation=malformed):
                result = score_final_workflow(configuration, self.target, self.records, malformed)
                self.assertFalse(result["completion_pass"])
                self.assertIn(result["scoring_error"], {"missing_observations", "invalid_observations"})
        for mutate in (
            lambda o:o["private_observations"].update(stored_cases="SYNTH-PRIVATE-CANARY"),
            lambda o:o["private_observations"]["steps"][0].update(new_messages=[None]),
            lambda o:o["private_observations"].update(final_state=[]),
        ):
            result = self.score("answer", mutate=mutate)
            self.assertFalse(result["completion_pass"])
            self.assertNotIn("SYNTH-PRIVATE-CANARY", json.dumps(result))

    def test_scoring_output_contains_only_fixed_checks_and_no_private_values(self):
        for key, (configuration, observation) in self.fixtures.items():
            result = score_final_workflow(configuration, self.target, self.records, observation)
            serialized = json.dumps(result)
            for private_value in ("SYNTH-TARGET", "SYNTH-OWNER", "SYNTH-FOREIGN-SECRET", "21.35", WORDS[key[0]]["purpose"]):
                self.assertNotIn(private_value, serialized)


if __name__ == "__main__":
    unittest.main()
