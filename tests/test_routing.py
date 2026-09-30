"""Synthetic baseline and conservative slot tests; no dataset or final split."""

from datetime import date
from decimal import Decimal
import unittest

from bank_service.routing import IntentProposal, RoutingError, extract_slots, route_intent
from bank_service.selection import TransactionFilters


class IntentRoutingTests(unittest.TestCase):
    def test_bilingual_inquiry_and_normalization(self):
        cases = (
            ("¿Cuál es el estado de esta transacción?", "es"),
            ("Quero consultar a compra no cartão", "pt"),
            ("Buscar movimiento por 25,50 USD", "es"),
            ("ＣＯＮＳＵＬＴＡＲ transação", "pt"),
            ("2026-06-17", "es"),
        )
        for text, language in cases:
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language), IntentProposal("inquiry", 1.0, True))

    def test_bilingual_disputed_charge(self):
        for text, language in (
            ("No reconozco este cargo", "es"),
            ("Quiero contestar un cobro indebido", "es"),
            ("Não reconheço esta compra", "pt"),
            ("Quero abrir uma reclamação por cobrança duplicada", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language).intent, "dispute_intake")

    def test_explicit_human_request_and_priority_over_dispute(self):
        for text, language in (
            ("Quiero hablar con una persona", "es"),
            ("Preciso falar com um atendente sobre esta cobrança", "pt"),
            ("No reconozco este cargo; necesito hablar con un agente", "es"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language).intent, "human_request")

    def test_unsupported_actions_win_over_other_keywords(self):
        for text, language in (
            ("Transfiere dinero desde mi tarjeta y dime el estado", "es"),
            ("Quero fazer uma transferência e falar com uma pessoa", "pt"),
            ("Bloquea mi tarjeta por esta compra", "es"),
            ("Devolva o dinheiro desta compra", "pt"),
            ("Quiero reembolso del cargo", "es"),
            ("Quero um empréstimo y ver la transacción", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language), IntentProposal("unsupported", 1.0, True))

    def test_negative_action_is_not_a_dispute_or_human_request(self):
        for text, language, expected in (
            ("No quiero disputar esta compra, solo ver la transacción", "es", "inquiry"),
            ("Não quero contestar a cobrança, quero consultar a transação", "pt", "inquiry"),
            ("No quiero hablar con una persona", "es", "unsupported"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language).intent, expected)

    def test_unknown_and_confirmation_do_not_infer_consent(self):
        for text in ("Hola", "Sí", "sim!", "yes", "confirmo", "confirmo la disputa", "acepto crear el caso"):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, "es"), IntentProposal("unsupported", 0.0, False))

    def test_request_contract_and_fixed_errors(self):
        for function in (route_intent, extract_slots):
            for text, language, code in (
                (None, "es", "invalid_request"),
                (123, "pt", "invalid_request"),
                (" ", "es", "invalid_request"),
                ("consulta", "en", "unsupported_language"),
                ("consulta", [], "unsupported_language"),
                ("x" * 1001, "es", "request_too_long"),
            ):
                with self.subTest(function=function.__name__, code=code):
                    with self.assertRaises(RoutingError) as caught:
                        function(text, language)
                    self.assertEqual(str(caught.exception), code)


class SlotExtractionTests(unittest.TestCase):
    def test_exact_demo_id_date_and_decimal_native_currency(self):
        result = extract_slots("Consulta demo-tx-001 por 25,50 USD el 2026-06-17", "es")
        self.assertEqual(result.transaction_id, "DEMO-TX-001")
        self.assertEqual(result.filters, TransactionFilters(date(2026, 6, 17), Decimal("25.50"), "USD"))
        self.assertIsInstance(result.filters.amount, Decimal)

    def test_amount_prefix_currency_zero_negative_and_case(self):
        for text, expected_amount, expected_currency in (
            ("USD 0", Decimal("0"), "USD"),
            ("valor -25.50 cop", Decimal("-25.50"), "COP"),
            ("ARS +12,5", Decimal("12.5"), "ARS"),
        ):
            with self.subTest(text=text):
                filters = extract_slots(text, "pt").filters
                self.assertEqual((filters.amount, filters.currency), (expected_amount, expected_currency))

    def test_absent_slots_and_currency_alone_do_not_guess(self):
        for text, filters in (
            ("Quero ver a compra", TransactionFilters()),
            ("importe $25.50", TransactionFilters()),
            ("consulta USD", TransactionFilters(currency="USD")),
            ("25,50", TransactionFilters()),
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_slots(text, "pt").filters, filters)

    def test_explicit_identifier_and_no_customer_derivation(self):
        self.assertEqual(extract_slots("transação TXN_000102", "pt").transaction_id, "TXN_000102")
        for text in ("cliente CUSTOMER-A", "transacción CUSTOMER-001", "transacción 2026-06-17", "transacción pendiente"):
            with self.subTest(text=text):
                self.assertIsNone(extract_slots(text, "es").transaction_id)

    def test_date_is_calendar_exact_and_ambiguity_is_rejected(self):
        for text, code in (
            ("consulta 2026-02-30", "invalid_date"),
            ("consulta 2026-6-17", "invalid_date"),
            ("consulta 2026-06-17 y 2026-06-18", "ambiguous_date"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(RoutingError) as caught:
                    extract_slots(text, "es")
                self.assertEqual(str(caught.exception), code)

    def test_ambiguous_or_nonfinite_amounts_are_rejected(self):
        for value in ("1,000", "1.000", "1,000.50", "1.000,50", "1 000", "1e3", "NaN", "Infinity", "25.123"):
            with self.subTest(value=value):
                with self.assertRaises(RoutingError) as caught:
                    extract_slots(value + " USD", "es")
                self.assertEqual(str(caught.exception), "invalid_amount")
        with self.assertRaisesRegex(RoutingError, "^ambiguous_amount$"):
            extract_slots("25.50 USD y 30.00 USD", "pt")

    def test_currency_and_identifier_ambiguity_are_rejected(self):
        for text, code in (
            ("25.50 BRL", "unsupported_currency"),
            ("MXN", "unsupported_currency"),
            ("USD o COP", "ambiguous_currency"),
            ("DEMO-TX-001 o DEMO-TX-002", "ambiguous_transaction_id"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(RoutingError) as caught:
                    extract_slots(text, "es")
                self.assertEqual(str(caught.exception), code)

    def test_repeated_identical_slots_are_consistent(self):
        result = extract_slots("DEMO-TX-001, transacción DEMO-TX-001, 25.50 USD y USD 25,50, 2026-06-17 2026-06-17", "es")
        self.assertEqual(result.transaction_id, "DEMO-TX-001")
        self.assertEqual(result.filters.amount, Decimal("25.50"))
        self.assertEqual(result.filters.transaction_date, date(2026, 6, 17))


if __name__ == "__main__":
    unittest.main()
