"""Synthetic explicit-read guard cases; no model, workload or source reads."""

import unittest

from bank_service.routing import RoutingError, is_explicit_inquiry


class ExplicitInquiryTests(unittest.TestCase):
    def test_short_spanish_read_requests(self):
        for text in (
            "ver un pago",
            "quiero ver un pago",
            "consultar una transacción",
            "buscar una compra",
            "Muéstrame mis movimientos",
            "Enséñame mis pagos",
            "Quiero consultar esta operación",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_explicit_inquiry(text, "es"))

    def test_short_portuguese_read_requests(self):
        for text in (
            "ver um pagamento",
            "quero consultar um pagamento",
            "buscar uma compra",
            "conferir esta transação",
            "Mostre meus pagamentos",
            "Quero ver as transações",
            "Quero consultar esta operação",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_explicit_inquiry(text, "pt"))

    def test_polite_wrappers_and_normalization(self):
        for text, language in (
            ("Por favor, muéstrame mis pagos.", "es"),
            ("¿Puedo consultar mis transacciones?", "es"),
            ("Hola, quiero ver un pago", "es"),
            ("Quiero consultar una compra, por favor", "es"),
            ("ＶＥＲ un PAGO", "es"),
            ("Por favor, mostre meus pagamentos.", "pt"),
            ("Posso consultar minhas transações?", "pt"),
            ("Olá, quero ver um pagamento", "pt"),
            ("Quero consultar uma compra, por favor", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertTrue(is_explicit_inquiry(text, language))

    def test_ambiguous_review_requests_remain_for_business_routing(self):
        # "Review" can mean inspecting a record or requesting investigation.
        # This guard must not force those messages into the read-only route.
        for text, language in (
            ("revisar este cargo", "es"),
            ("Revisar esta transacción", "es"),
            ("Quiero revisar un pago", "es"),
            ("Revisar esta transação", "pt"),
            ("Quero revisar um pagamento", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertFalse(is_explicit_inquiry(text, language))

    def test_execute_refund_and_mixed_requests_are_not_read_guards(self):
        for text, language in (
            ("Quiero hacer una transacción", "es"),
            ("Quiero pagar una compra", "es"),
            ("Quiero ver un pago y pagar otro", "es"),
            ("Ver un pago y transferir dinero", "es"),
            ("Ver un pago y devolver su importe", "es"),
            ("Quiero ver el reembolso de una compra", "es"),
            ("Quero fazer uma transação", "pt"),
            ("Quero pagar uma compra", "pt"),
            ("Quero ver um pagamento e pagar outro", "pt"),
            ("Ver um pagamento e transferir dinheiro", "pt"),
            ("Ver um pagamento e devolver o valor", "pt"),
            ("Quero ver o reembolso de uma compra", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertFalse(is_explicit_inquiry(text, language))

    def test_dispute_human_and_case_history_keep_their_other_routes(self):
        for text, language in (
            ("Quiero revisar un cargo que no reconozco", "es"),
            ("Quiero ver un pago y disputarlo", "es"),
            ("Quiero consultar esta compra y abrir un reclamo", "es"),
            ("Quiero ver un pago con una persona", "es"),
            ("Ver un pago y hablar con un agente", "es"),
            ("Quiero ver el estado de mi reclamo", "es"),
            ("Quero revisar uma cobrança que não reconheço", "pt"),
            ("Quero ver um pagamento e contestá-lo", "pt"),
            ("Quero consultar esta compra e abrir uma reclamação", "pt"),
            ("Quero ver um pagamento com um atendente", "pt"),
            ("Ver um pagamento e falar com uma pessoa", "pt"),
            ("Quero ver o andamento da minha reclamação", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertFalse(is_explicit_inquiry(text, language))

    def test_negated_read_requests_do_not_become_inquiries(self):
        for text, language in (
            ("No quiero ver un pago", "es"),
            ("No necesito consultar mis transacciones", "es"),
            ("No me muestres mis pagos", "es"),
            ("Não quero ver um pagamento", "pt"),
            ("Não preciso consultar minhas transações", "pt"),
            ("Não mostre meus pagamentos", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertFalse(is_explicit_inquiry(text, language))

    def test_nouns_slots_consent_and_unrecognized_tails_are_outside_guard(self):
        for text, language in (
            ("un pago", "es"),
            ("mis transacciones", "es"),
            ("2026-06-17", "es"),
            ("25 USD", "es"),
            ("sí", "es"),
            ("confirmo consultar la transacción", "es"),
            ("ver un pago y algo más", "es"),
            ("um pagamento", "pt"),
            ("minhas transações", "pt"),
            ("2026-06-17", "pt"),
            ("25 COP", "pt"),
            ("sim", "pt"),
            ("confirmo consultar a transação", "pt"),
            ("ver um pagamento e outra coisa", "pt"),
        ):
            with self.subTest(text=text, language=language):
                self.assertFalse(is_explicit_inquiry(text, language))

    def test_invalid_contract_raises_fixed_errors_without_echoing_input(self):
        for text, language, code in (
            (None, "es", "invalid_request"),
            (17, "pt", "invalid_request"),
            ("   ", "es", "invalid_request"),
            ("x" * 1001, "pt", "request_too_long"),
            ("ver un pago", "en", "unsupported_language"),
            ("ver um pagamento", None, "unsupported_language"),
        ):
            with self.subTest(language=language, code=code):
                with self.assertRaisesRegex(RoutingError, "^" + code + "$"):
                    is_explicit_inquiry(text, language)


if __name__ == "__main__":
    unittest.main()
