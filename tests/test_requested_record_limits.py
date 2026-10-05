"""Requested source limits use synthetic records and no model or source files."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io
import unittest

from bank_service.access import Permission, TrustedSession
from bank_service.records import TransactionRecord
from bank_service.responses import (
    CHANNEL_LIMITS, ResponseFormatError, TransactionAnswer, answer_transaction,
    with_requested_record_limits,
)
from bank_service.transactions import SourceReference, SourcedTransaction


class RequestedRecordLimitTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        self.session = TrustedSession(
            "SYNTH-CUSTOMER", self.now + timedelta(minutes=10),
            frozenset({Permission.READ_TRANSACTION}),
        )
        self.record = TransactionRecord(
            transaction_id="SYNTH-TX", customer_id="SYNTH-CUSTOMER",
            product_id="SYNTH-PRODUCT",
            transaction_date=datetime(2026, 6, 17, 9, 45),
            process_date=date(2026, 6, 17), transaction_type="Purchase",
            amount=Decimal("25.1234567890123456789"), currency="MXN",
            transaction_status="Approved", merchant_name="Synthetic Merchant",
        )
        self.sources = (SourceReference("synthetic/transactions.csv", 2, "a" * 64),)

    def answer(self, language, merchant=None):
        record = self.record if merchant is None else replace(self.record, merchant_name=merchant)
        entry = SourcedTransaction(record, self.sources)
        return answer_transaction(
            self.session, record.transaction_id, records={record.transaction_id: entry},
            language=language, now=self.now,
        )

    def test_explicit_channel_request_adds_only_localized_limit_and_preserves_facts(self):
        requests = {
            "es": ("¿Por qué canal se hizo la compra?", "Quiero revisar los canales registrados."),
            "pt": ("Em qual canal foi feita esta compra?", "Quero conferir os canais registrados."),
        }
        for language, variants in requests.items():
            answer = self.answer(language)
            for request in variants:
                with self.subTest(language=language, request=request):
                    result = with_requested_record_limits(answer, request)
                    self.assertEqual(result.language, answer.language)
                    self.assertIs(result.sources, answer.sources)
                    self.assertEqual(result.text, answer.text + "\n" + CHANNEL_LIMITS[language])
                    self.assertIn("25.1234567890123456789 MXN", result.text)
                    self.assertIn("Approved", result.text)
                    self.assertNotIn("SYNTH-CUSTOMER", result.text)
                    self.assertEqual(answer.text.splitlines()[-1],
                                     "Datos de una instantánea histórica." if language == "es"
                                     else "Dados de um retrato histórico.")

    def test_channel_keyword_is_case_and_unicode_compatible(self):
        answer = self.answer("es")
        for request in ("¿Qué CANAL consta?", "What channel is recorded?",
                        "Which channels are recorded?", "¿Qué ＣＡＮＡＬ consta?"):
            with self.subTest(request=request):
                result = with_requested_record_limits(answer, request)
                self.assertEqual(result.text.splitlines()[-1], CHANNEL_LIMITS["es"])

    def test_normal_record_requests_do_not_get_an_unrelated_disclaimer(self):
        for language, requests in (
            ("es", ("Muéstrame el importe y el estado.", "¿Cuál es el comercio?", "")),
            ("pt", ("Quero ver o valor e o status.", "Qual é o estabelecimento?", "   ")),
        ):
            for request in requests:
                with self.subTest(language=language, request=request):
                    answer = self.answer(language)
                    self.assertIs(with_requested_record_limits(answer, request), answer)

    def test_keyword_substrings_and_merchant_values_do_not_trigger_unrequested_limit(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                answer = self.answer(language, merchant=CHANNEL_LIMITS[language])
                self.assertIs(with_requested_record_limits(answer, "Muéstrame el comercio."), answer)
                self.assertIs(with_requested_record_limits(answer, "La canaleta es del comercio."), answer)

    def test_existing_dedicated_explanation_is_not_duplicated(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                once = with_requested_record_limits(self.answer(language), "canal")
                twice = with_requested_record_limits(once, "canal")
                self.assertIs(twice, once)
                self.assertEqual(twice.text.splitlines().count(CHANNEL_LIMITS[language]), 1)

    def test_quoted_merchant_limit_does_not_count_as_the_dedicated_explanation(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                answer = self.answer(language, merchant=CHANNEL_LIMITS[language])
                result = with_requested_record_limits(answer, "¿Qué canal está registrado?")
                self.assertEqual(result.text.splitlines()[-1], CHANNEL_LIMITS[language])
                self.assertEqual(result.text.splitlines().count(CHANNEL_LIMITS[language]), 1)
                self.assertEqual(result.text, answer.text + "\n" + CHANNEL_LIMITS[language])

    def test_invalid_input_types_and_missing_provenance_use_fixed_errors(self):
        answer = self.answer("es")
        for value in (None, {}, [], True, "private-answer-value"):
            with self.subTest(answer_type=type(value).__name__):
                with self.assertRaisesRegex(ResponseFormatError, "^invalid_answer$"):
                    with_requested_record_limits(value, "canal")
        for value in (None, {}, [], True, 1):
            with self.subTest(request_type=type(value).__name__):
                with self.assertRaisesRegex(ResponseFormatError, "^invalid_request$"):
                    with_requested_record_limits(answer, value)
        for malformed in (
            replace(answer, text=None), replace(answer, text=""),
            replace(answer, sources=None), replace(answer, sources=()),
            replace(answer, sources=list(answer.sources)), replace(answer, sources=("private-ref",)),
        ):
            with self.subTest(malformed=type(malformed.text).__name__):
                with self.assertRaisesRegex(ResponseFormatError, "^invalid_answer$"):
                    with_requested_record_limits(malformed, "canal")
        for language in (None, [], True, "en", "ES", "pt-BR"):
            with self.subTest(language_type=type(language).__name__):
                with self.assertRaisesRegex(ResponseFormatError, "^unsupported_language$"):
                    with_requested_record_limits(replace(answer, language=language), "canal")

    def test_helper_has_no_output_side_effects(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = with_requested_record_limits(self.answer("es"), "¿Qué canal consta?")
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertIsInstance(result, TransactionAnswer)


if __name__ == "__main__":
    unittest.main()
