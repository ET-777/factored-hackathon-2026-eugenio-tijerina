"""Synthetic baseline and conservative slot tests; no dataset or final split."""

from datetime import date
from decimal import Decimal
import unittest

from bank_service.routing import (
    IntentProposal, RoutingError, extract_slots, is_greeting, is_search_followup,
    refers_to_selected_transaction, route_intent,
)
from bank_service.records import SUPPORTED_CURRENCIES
from bank_service.selection import TransactionFilters


class IntentRoutingTests(unittest.TestCase):
    def test_pure_greetings_do_not_include_business_requests_or_consent(self):
        for text, language in (("¡Hola!", "es"), ("Buenos días", "es"),
                               ("Olá!", "pt"), ("Oi", "pt"), ("Boa tarde", "pt")):
            with self.subTest(text=text):
                self.assertTrue(is_greeting(text, language))
        for text, language in (("Hola, no reconozco esta compra", "es"),
                               ("Oi, quero falar com uma pessoa", "pt"),
                               ("sí", "es"), ("sim", "pt"), ("25 USD", "es")):
            with self.subTest(text=text):
                self.assertFalse(is_greeting(text, language))

    def test_malformed_date_fragments_remain_slots_and_require_strict_iso(self):
        for language in ("es", "pt"):
            for text in ("20226-17-05", "2026-17-05", "2026-6-16", "16-06-2026", "2026-02-30"):
                with self.subTest(text=text, language=language):
                    self.assertTrue(is_search_followup(text, language))
                    with self.assertRaisesRegex(RoutingError, "^invalid_date$"):
                        extract_slots(text, language)

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

    def test_common_plural_inquiries_from_owner_development_review(self):
        for text, language in (
            ("Enséñame mis pagos", "es"),
            ("Muéstrame mis cargos y movimientos", "es"),
            ("Busco las transacciones", "es"),
            ("Mostre meus pagamentos", "pt"),
            ("Quero ver as transações e movimentações", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language), IntentProposal("inquiry", 1.0, True))

    def test_money_replies_route_to_inquiry_for_context_or_clarification(self):
        for text in ("25 dolares", "25,5 dólares", "25", "25 pesos", "pesos", "MXN", "BRL", "$25.50"):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, "es"), IntentProposal("inquiry", 1.0, True))
        # Explicit unsupported requests retain priority over the fragment rule.
        self.assertEqual(route_intent("Transfiere 25 dolares", "es").intent, "unsupported")

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

    def test_new_payment_or_transaction_execution_is_unsupported(self):
        for text, language in (
            ("Quiero hacer una transacción de 25 USD", "es"),
            ("Quiero hacer una nueva transacción", "es"),
            ("Necesito que hagas un pago", "es"),
            ("Haz un pago con mi tarjeta", "es"),
            ("Realiza mi pago ahora", "es"),
            ("Ejecuta una transacción y dime el estado", "es"),
            ("Necesito pagar 25 MXN", "es"),
            ("¿Puedes pagar mi factura?", "es"),
            ("Paga el importe de 25 USD", "es"),
            ("Quero fazer uma transação de 25 USD", "pt"),
            ("Preciso fazer uma nova transação", "pt"),
            ("Faça um pagamento", "pt"),
            ("Execute uma transação", "pt"),
            ("Quero efetuar o pagamento", "pt"),
            ("Preciso que você pague a conta", "pt"),
            ("Quero pagar e falar com um atendente", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language), IntentProposal("unsupported", 1.0, True))

    def test_existing_payment_history_queries_still_route_to_inquiry(self):
        for text, language in (
            ("¿Cuál es el estado del pago que hice ayer?", "es"),
            ("Ya realicé una transacción; quiero ver su importe", "es"),
            ("Muéstrame el pago que ya ejecuté", "es"),
            ("¿Qué pasó con la transacción que pagué?", "es"),
            ("Quero consultar o pagamento que fiz", "pt"),
            ("Qual é o status da transação que realizei?", "pt"),
            ("Mostre o pagamento que já paguei", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language), IntentProposal("inquiry", 1.0, True))

    def test_negated_new_actions_do_not_override_existing_record_queries(self):
        for text, language in (
            ("No quiero hacer un pago, quiero consultar la transacción", "es"),
            ("No hagas un pago, muéstrame mis pagos", "es"),
            ("No necesito pagar, solo ver el cargo", "es"),
            ("Não quero fazer uma transação, quero ver meus pagamentos", "pt"),
            ("Não faça um pagamento, consulte esta transação", "pt"),
            ("Não vou pagar, quero consultar o pagamento anterior", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(route_intent(text, language), IntentProposal("inquiry", 1.0, True))

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

    def test_explicit_demo_dollar_word_interpretation_is_flagged(self):
        for text, language, amount in (
            ("25 dolares", "es", Decimal("25")),
            ("25,5 dólares", "es", Decimal("25.5")),
            ("25,50 dólares", "pt", Decimal("25.50")),
            ("dólares 0", "pt", Decimal("0")),
        ):
            with self.subTest(text=text):
                slots = extract_slots(text, language)
                self.assertEqual(slots.filters, TransactionFilters(amount=amount, currency="USD"))
                self.assertTrue(slots.used_dollar_alias)
                self.assertFalse(slots.needs_currency)
                self.assertIsNone(slots.amount_without_currency)

    def test_bare_amount_and_ambiguous_units_stay_out_of_search_filters(self):
        for text, amount in (
            ("25", Decimal("25")),
            ("25,5", Decimal("25.5")),
            ("0 pesos", Decimal("0")),
            ("pesos -25.50", Decimal("-25.50")),
            ("$25.50", Decimal("25.50")),
            ("importe 25.50", Decimal("25.50")),
        ):
            with self.subTest(text=text):
                slots = extract_slots(text, "es")
                self.assertEqual(slots.filters, TransactionFilters())
                self.assertEqual(slots.amount_without_currency, amount)
                self.assertTrue(slots.needs_currency)
                self.assertFalse(slots.used_dollar_alias)
        slots = extract_slots("pesos", "es")
        self.assertTrue(slots.needs_currency)
        self.assertIsNone(slots.amount_without_currency)

    def test_explicit_native_code_disambiguates_pesos_and_symbols(self):
        for text, amount, code in (
            ("25 pesos COP", Decimal("25"), "COP"),
            ("$25,50 ARS", Decimal("25.50"), "ARS"),
            ("25 pesos MXN", Decimal("25"), "MXN"),
            ("importe 25.50 USD", Decimal("25.50"), "USD"),
        ):
            with self.subTest(text=text):
                slots = extract_slots(text, "es")
                self.assertEqual(slots.filters, TransactionFilters(amount=amount, currency=code))
                self.assertFalse(slots.needs_currency)
        self.assertEqual(SUPPORTED_CURRENCIES, frozenset({"USD", "COP", "ARS", "MXN"}))

    def test_explicit_mxn_code_and_amounts_in_both_languages(self):
        for text, language, amount in (
            ("25.50 MXN", "es", Decimal("25.50")),
            ("25,50 MXN", "pt", Decimal("25.50")),
            ("MXN 0", "es", Decimal("0")),
            ("25,5 pesos MXN", "pt", Decimal("25.5")),
            ("$25.50 MXN", "es", Decimal("25.50")),
            ("mxn -25,50", "pt", Decimal("-25.50")),
            ("MXN", "es", None),
        ):
            with self.subTest(text=text):
                slots = extract_slots(text, language)
                self.assertEqual(slots.filters, TransactionFilters(amount=amount, currency="MXN"))
                self.assertFalse(slots.needs_currency)
                self.assertFalse(slots.currency_ambiguous)
                self.assertFalse(slots.used_dollar_alias)
                self.assertIsNone(slots.amount_without_currency)
                self.assertEqual(route_intent(text, language).intent, "inquiry")
                self.assertTrue(is_search_followup(text, language))

    def test_ambiguous_denomination_is_distinct_from_bare_amount(self):
        for text, expected in (
            ("25", False), ("25,5", False), ("importe 25", False),
            ("25 pesos", True), ("pesos", True), ("$25.50", True),
            ("25 dolares", False), ("$25.50 USD", False), ("25 pesos COP", False),
            ("25 pesos MXN", False),
        ):
            with self.subTest(text=text):
                self.assertIs(extract_slots(text, "es").currency_ambiguous, expected)

    def test_alias_conflicts_and_unsupported_codes_are_not_converted(self):
        for text, error in (
            ("25 dolares COP", "ambiguous_currency"),
            ("25 pesos USD", "ambiguous_currency"),
            ("25 dólares CAD", "unsupported_currency"),
            ("25 pesos EUR", "unsupported_currency"),
            ("25 reais BRL", "unsupported_currency"),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(RoutingError, "^" + error + "$"):
                    extract_slots(text, "es")

    def test_missing_currency_amount_validation_and_conflict(self):
        for text, error in (
            ("1,000", "invalid_amount"),
            ("$NaN", "invalid_amount"),
            ("25,123 pesos", "invalid_amount"),
            ("25 pesos y 30 pesos", "ambiguous_amount"),
            ("25 USD y importe 30", "ambiguous_amount"),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(RoutingError, "^" + error + "$"):
                    extract_slots(text, "es")

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
            ("EUR", "unsupported_currency"),
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

    def test_explicit_reference_helper_does_not_treat_broad_queries_as_selection(self):
        for text, language in (
            ("No reconozco esta compra", "es"),
            ("Quiero revisar ese cargo", "es"),
            ("Não reconheço esse débito", "pt"),
            ("Quero falar desta transação: esta transação", "pt"),
        ):
            with self.subTest(text=text):
                self.assertTrue(refers_to_selected_transaction(text, language))
        for text in ("Enséñame mis pagos", "Buscar otra compra", "Quiero consultar todas las transacciones", "Sí"):
            with self.subTest(text=text):
                self.assertFalse(refers_to_selected_transaction(text, "es"))

    def test_operation_movement_and_contracted_references_are_clearly_singular(self):
        for text, language in (
            ("¿Cuál es el importe de esta operación?", "es"),
            ("Dime la fecha de ese movimiento", "es"),
            ("Quiero revisar la operación seleccionada", "es"),
            ("¿Qué pasó con el movimiento seleccionado?", "es"),
            ("Dime el estado del pago elegido", "es"),
            ("Qual é o valor desta operação?", "pt"),
            ("Quando ocorreu esse movimento?", "pt"),
            ("Quero saber o valor desse débito", "pt"),
            ("Consulte essa movimentação", "pt"),
            ("Quero detalhes daquele lançamento", "pt"),
            ("Qual é o status da operação selecionada?", "pt"),
            ("Mostre o pagamento escolhido", "pt"),
        ):
            with self.subTest(text=text):
                self.assertTrue(refers_to_selected_transaction(text, language))

    def test_plural_broad_and_new_record_queries_are_not_selected_references(self):
        for text, language in (
            ("Enséñame mis movimientos", "es"),
            ("Muéstrame estas operaciones", "es"),
            ("Quiero ver los movimientos seleccionados", "es"),
            ("Busca otra operación", "es"),
            ("Busca una nueva operación como esta compra", "es"),
            ("Busca otras operaciones como este movimiento", "es"),
            ("¿Cuál es el importe de una operación?", "es"),
            ("Mostre meus movimentos", "pt"),
            ("Quero ver essas operações", "pt"),
            ("Consulte os movimentos selecionados", "pt"),
            ("Quero outra operação como essa compra", "pt"),
            ("Quero outras operações como esse movimento", "pt"),
            ("Qual é o valor de uma operação?", "pt"),
            ("Qual é o status da transação?", "pt"),
        ):
            with self.subTest(text=text):
                self.assertFalse(refers_to_selected_transaction(text, language))

    def test_reference_flag_does_not_replace_explicit_id_or_filter_slots(self):
        text = "Revise esta operação DEMO-TX-002 de 25,50 MXN em 2026-06-17"
        self.assertTrue(refers_to_selected_transaction(text, "pt"))
        slots = extract_slots(text, "pt")
        self.assertEqual(slots.transaction_id, "DEMO-TX-002")
        self.assertEqual(slots.filters, TransactionFilters(date(2026, 6, 17), Decimal("25.50"), "MXN"))

    def test_search_followup_accepts_only_bounded_slot_replies(self):
        for text, language in (
            ("USD", "es"), ("MXN", "es"), ("BRL", "pt"),
            ("dólares", "pt"), ("pesos", "es"), ("$", "es"),
            ("25", "es"), ("25.", "es"), ("25,5", "pt"), ("25 dolares", "es"),
            ("de 25,50 dólares", "es"), ("del 25 USD", "es"),
            ("em COP", "pt"), ("en 2026-06-17", "es"),
            ("$25.50", "es"), ("USD 25.50", "pt"),
            ("DEMO-TX-001", "es"), ("TX_102", "pt"),
        ):
            with self.subTest(text=text):
                self.assertTrue(is_search_followup(text, language))

    def test_search_followup_does_not_inherit_intent_into_new_requests(self):
        for text in (
            "Enséñame mis pagos", "Busca otra compra de 25 USD", "Quero ver meus pagamentos",
            "No reconozco esta compra", "Hablar con una persona", "Falar com um atendente",
            "Transfiere 25 USD", "Bloquea mi tarjeta", "Sí", "sim!", "confirmo", "acepto",
            "USD y COP", "25 USD y busca otra compra", "cliente CUSTOMER-001", "hola",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_search_followup(text, "es"))

    def test_search_followup_still_requires_slot_validation_and_input_bounds(self):
        self.assertTrue(is_search_followup("1,000 USD", "es"))
        with self.assertRaisesRegex(RoutingError, "^invalid_amount$"):
            extract_slots("1,000 USD", "es")
        self.assertTrue(is_search_followup("2026-02-30", "es"))
        with self.assertRaisesRegex(RoutingError, "^invalid_date$"):
            extract_slots("2026-02-30", "es")
        for text, language, error in (
            (None, "es", "invalid_request"), ("USD", "en", "unsupported_language"),
            ("x" * 1001, "pt", "request_too_long"),
        ):
            with self.subTest(error=error):
                with self.assertRaisesRegex(RoutingError, "^" + error + "$"):
                    is_search_followup(text, language)

    def test_short_bilingual_slot_prefixes_preserve_search_shape(self):
        for text, language, amount, currency in (
            ("Son 25.5 dólares", "es", Decimal("25.5"), "USD"),
            ("São 25,50 dólares", "pt", Decimal("25.50"), "USD"),
            ("es 25", "es", Decimal("25"), None),
            ("é 25,50", "pt", Decimal("25.50"), None),
            ("fue 25 USD", "es", Decimal("25"), "USD"),
            ("foi 25 COP", "pt", Decimal("25"), "COP"),
            ("por 25 pesos", "es", Decimal("25"), None),
        ):
            with self.subTest(text=text):
                self.assertTrue(is_search_followup(text, language))
                self.assertEqual(route_intent(text, language).intent, "inquiry")
                slots = extract_slots(text, language)
                self.assertEqual(slots.filters.currency, currency)
                if currency is None:
                    self.assertEqual(slots.amount_without_currency, amount)
                    self.assertTrue(slots.needs_currency)
                else:
                    self.assertEqual(slots.filters.amount, amount)
        for text in ("Son mis pagos", "São meus pagamentos", "Es otra compra de 25 USD", "Fue un reembolso"):
            with self.subTest(new_request=text):
                self.assertFalse(is_search_followup(text, "es"))

    def test_malformed_amount_replies_remain_followups_but_never_valid_slots(self):
        for text, language in (
            ("NaN", "es"), ("Infinity", "pt"), ("son NaN", "es"),
            ("São Infinity", "pt"), ("foi 1e3", "pt"), ("por 25,123 pesos", "es"),
            ("Son 1,000 dólares", "es"),
        ):
            with self.subTest(text=text):
                self.assertTrue(is_search_followup(text, language))
                self.assertEqual(route_intent(text, language).intent, "inquiry")
                with self.assertRaisesRegex(RoutingError, "^invalid_amount$"):
                    extract_slots(text, language)


if __name__ == "__main__":
    unittest.main()
