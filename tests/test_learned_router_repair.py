"""Invented preview-policy regressions; no private/final cases or scoring."""

from dataclasses import FrozenInstanceError
import unittest

from bank_service.learned_routing import GuardedPreviewRouter, train_router
from bank_service.routing import IntentProposal, RoutingError, route_intent
from tests.test_learned_routing import toy_rows


class FixedModel:
    """A misleading score cannot substitute for customer intent evidence."""

    training_hash = "a" * 64
    training_row_count = 8
    vocabulary_size = 100
    class_counts = {"inquiry": 2, "dispute_intake": 2, "human_request": 2, "unsupported": 2}
    language_counts = {"es": 4, "pt": 4}

    def __init__(self, intent):
        self.proposal = IntentProposal(intent, 0.999, True)
        self.calls = []

    def route_intent(self, text, language):
        self.calls.append((text, language))
        return self.proposal


class LearnedRouterRepairTests(unittest.TestCase):
    def test_plain_reads_and_read_requests_with_filters_override_wrong_model_label(self):
        cases = (
            ("es", "quiero ver un pago"),
            ("es", "Consulta este cargo del 18 de junio de 2026"),
            ("pt", "Quero ver um pagamento"),
            ("pt", "Confira esta compra de 18/06/2026"),
        )
        for model_label in ("dispute_intake", "human_request", "unsupported"):
            model = FixedModel(model_label)
            router = GuardedPreviewRouter(model)
            for language, text in cases:
                with self.subTest(language=language, label=model_label, text=text):
                    self.assertEqual(router.route_intent(text, language),
                                     IntentProposal("inquiry", 1.0, True))
            self.assertEqual(model.calls, [])

    def test_supported_short_disputes_require_actual_complaint_wording(self):
        cases = (
            ("es", "No reconozco este cargo"),
            ("es", "yo no hize esto"),
            ("es", "Este pago no es mío"),
            ("es", "Me cobraron dos veces esta compra"),
            ("es", "Quiero impugnar este cargo"),
            ("pt", "Não reconheço esta cobrança"),
            ("pt", "não fui eu"),
            ("pt", "Esta compra não é minha"),
            ("pt", "Fui cobrado duas vezes nesta compra"),
            ("pt", "Quero contestar esta cobrança"),
        )
        model = FixedModel("inquiry")
        router = GuardedPreviewRouter(model)
        for language, text in cases:
            with self.subTest(language=language, text=text):
                self.assertEqual(router.route_intent(text, language),
                                 IntentProposal("dispute_intake", 1.0, True))
        self.assertEqual(model.calls, [])

    def test_unsupported_actions_keep_precedence_over_financial_or_complaint_terms(self):
        cases = (
            ("es", "Quiero hacer una transacción"),
            ("es", "No reconozco el cargo; devuelve mi dinero"),
            ("es", "Quiero ver este pago y transferir dinero"),
            ("pt", "Quero fazer um pagamento"),
            ("pt", "Não reconheço a compra; reembolse agora"),
            ("pt", "Quero consultar este pagamento e transferir dinheiro"),
        )
        model = FixedModel("dispute_intake")
        router = GuardedPreviewRouter(model)
        for language, text in cases:
            with self.subTest(language=language, text=text):
                self.assertEqual(router.route_intent(text, language),
                                 IntentProposal("unsupported", 1.0, True))
        self.assertEqual(model.calls, [])

    def test_human_request_requires_positive_user_wording(self):
        router = GuardedPreviewRouter(FixedModel("inquiry"))
        for language, text in (("es", "Quiero hablar con una persona"),
                               ("pt", "Quero falar com uma pessoa")):
            with self.subTest(language=language):
                self.assertEqual(router.route_intent(text, language),
                                 IntentProposal("human_request", 1.0, True))
        for model_label in ("human_request", "dispute_intake"):
            guarded = GuardedPreviewRouter(FixedModel(model_label))
            for language, text in (("es", "El agente explicó el cargo ayer"),
                                   ("pt", "O atendente explicou a compra ontem")):
                with self.subTest(language=language, model_label=model_label):
                    self.assertEqual(guarded.route_intent(text, language),
                                     IntentProposal("unsupported", 0.0, False))

    def test_greetings_assent_and_unrelated_messages_do_not_enter_consequential_routes(self):
        cases = (
            ("es", "Hola"), ("es", "hello"), ("es", "sí"), ("es", "quiero comer"),
            ("es", "me gusta el fútbol"), ("es", "¿qué tiempo hace?"),
            ("pt", "Olá"), ("pt", "hello"), ("pt", "sim"), ("pt", "quero comer"),
            ("pt", "gosto de futebol"), ("pt", "como está o tempo?"),
        )
        for model_label in ("human_request", "dispute_intake", "inquiry", "unsupported"):
            model = FixedModel(model_label)
            router = GuardedPreviewRouter(model)
            for language, text in cases:
                with self.subTest(language=language, label=model_label, text=text):
                    self.assertEqual(router.route_intent(text, language),
                                     IntentProposal("unsupported", 0.0, False))
            self.assertEqual(model.calls, [])

    def test_details_cannot_create_complaint_intent(self):
        cases = (("es", "18/06/2026"), ("es", "25 MXN"), ("es", "COP"),
                 ("pt", "18 de junho de 2026"), ("pt", "25 USD"), ("pt", "ARS"))
        model = FixedModel("dispute_intake")
        router = GuardedPreviewRouter(model)
        for language, text in cases:
            with self.subTest(language=language, text=text):
                self.assertEqual(router.route_intent(text, language),
                                 IntentProposal("inquiry", 1.0, True))
        self.assertEqual(model.calls, [])

    def test_negated_requests_and_ambiguous_narrative_abstain_even_at_high_score(self):
        cases = (
            ("es", "No quiero disputar este pago"),
            ("es", "No quiero ver este cargo"),
            ("es", "Este cargo no está duplicado"),
            ("es", "Desconozco por qué aparece el nombre de este comercio"),
            ("pt", "Não quero contestar esta cobrança"),
            ("pt", "Não quero ver esta compra"),
            ("pt", "Esta compra não está duplicada"),
            ("pt", "Desconheço por que aparece o nome deste estabelecimento"),
        )
        router = GuardedPreviewRouter(FixedModel("dispute_intake"))
        for language, text in cases:
            with self.subTest(language=language, text=text):
                self.assertEqual(router.route_intent(text, language),
                                 IntentProposal("unsupported", 0.0, False))

    def test_indirect_in_scope_messages_still_use_the_learned_model(self):
        for language, text in (("es", "¿A qué vendedor corresponde?"),
                               ("pt", "Qual estabelecimento consta ali?")):
            self.assertFalse(route_intent(text, language).matched)
            for label in ("inquiry", "unsupported"):
                model = FixedModel(label)
                with self.subTest(language=language, label=label):
                    self.assertEqual(GuardedPreviewRouter(model).route_intent(text, language),
                                     model.proposal)
                    self.assertEqual(model.calls, [(text, language)])

    def test_raw_model_and_metadata_remain_unchanged(self):
        model = train_router(toy_rows())
        router = GuardedPreviewRouter(model)
        self.assertEqual(model.route_intent("lumora", "es").intent, "inquiry")
        self.assertEqual(router.route_intent("lumora comercio", "es").intent, "inquiry")
        for field in ("training_hash", "training_row_count", "vocabulary_size",
                      "class_counts", "language_counts"):
            self.assertEqual(getattr(router, field), getattr(model, field))
        with self.assertRaises(FrozenInstanceError):
            router.model = model

    def test_validation_precedes_all_guard_and_model_operations(self):
        model = FixedModel("dispute_intake")
        router = GuardedPreviewRouter(model)
        for text, language, code in (("\ud800", "es", "invalid_request"),
                                     (None, "pt", "invalid_request"),
                                     ("x" * 1001, "es", "request_too_long"),
                                     ("hola", "en", "unsupported_language")):
            with self.subTest(code=code):
                with self.assertRaisesRegex(RoutingError, "^" + code + "$"):
                    router.route_intent(text, language)
        self.assertEqual(model.calls, [])


if __name__ == "__main__":
    unittest.main()
