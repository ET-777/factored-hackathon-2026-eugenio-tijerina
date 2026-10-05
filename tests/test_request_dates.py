"""Authored date-parser regressions; no source data or evaluation workloads."""

from datetime import date, datetime
import unittest

from bank_service.request_dates import (
    DateInterpretation, DateParsingError, extract_request_date, is_date_reply,
    mask_request_dates,
)


class RequestDateTests(unittest.TestCase):
    REFERENCE = date(2032, 10, 4)

    def parse(self, text, language="es", reference=None):
        return extract_request_date(
            text, language, reference_date=reference or self.REFERENCE,
        )

    def test_owner_examples_and_accent_case_normalization(self):
        for text in (
            "3 de Mayo 2026", "3 de Mayo, 2026", "Mayo 3, 2026",
            "3 de Mayo del 2026", "３ de ＭＡＹＯ ２０２６",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), DateInterpretation(date(2026, 5, 3)))
                self.assertTrue(is_date_reply(text, "es"))

    def test_portuguese_orders_and_connectors(self):
        for text, expected in (
            ("3 de maio de 2026", date(2026, 5, 3)),
            ("maio 3, 2026", date(2026, 5, 3)),
            ("3 de maio do 2026", date(2026, 5, 3)),
            ("3 de março, 2026", date(2026, 3, 3)),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text, "pt").value, expected)
                self.assertTrue(is_date_reply(text, "pt"))

    def test_all_months_both_languages(self):
        month_sets = {
            "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
            "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split(),
        }
        for language, months in month_sets.items():
            for number, name in enumerate(months, start=1):
                for text in (f"17 de {name} 2026", f"{name} 17, 2026"):
                    with self.subTest(language=language, text=text):
                        self.assertEqual(self.parse(text, language).value, date(2026, number, 17))
        self.assertEqual(self.parse("8 de setiembre 2026").value, date(2026, 9, 8))

    def test_omitted_year_uses_only_injected_reference_year(self):
        for text, language, expected in (
            ("8 de Septiembre", "es", date(2032, 9, 8)),
            ("3 de mayo", "es", date(2032, 5, 3)),
            ("maio 3", "pt", date(2032, 5, 3)),
            ("03/05", "es", date(2032, 5, 3)),
            ("03-05", "pt", date(2032, 5, 3)),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text, language), DateInterpretation(expected, True))

    def test_numeric_dates_are_day_first_and_iso_remains_exact(self):
        for text in ("03/05/2026", "03-05-2026", "2026-05-03"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text).value, date(2026, 5, 3))
                self.assertTrue(is_date_reply(text, "es"))
        self.assertEqual(self.parse("05/03/2026").value, date(2026, 3, 5))
        self.assertEqual(self.parse("17/06/2026").value, date(2026, 6, 17))

    def test_explicit_this_year_phrases_use_injected_reference_and_mask_the_entire_suffix(self):
        for text, language in (
            ("17 de Junio de este año", "es"), ("junio 17 del este año", "es"),
            ("17 de junio este año", "es"), ("17 de junho deste ano", "pt"),
            ("junho 17 de este ano", "pt"), ("17 de junho do este ano", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text, language), DateInterpretation(date(2032, 6, 17), True))
                self.assertTrue(is_date_reply(text, language))
                self.assertEqual(mask_request_dates(text, language).strip(), "")
                self.assertEqual(self.parse(text + " por 25.50 USD", language).value, date(2032, 6, 17))
                self.assertEqual(mask_request_dates(text + " por 25.50 USD", language).strip(), "por 25.50 usd")
        self.assertEqual(self.parse("29 de febrero de este año").value, date(2032, 2, 29))
        with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
            self.parse("29 de fevereiro deste ano", "pt", reference=date(2031, 1, 1))

    def test_current_year_phrase_does_not_override_malformed_or_conflicting_explicit_years(self):
        for text, language in (
            ("17 de junio de este año 2025", "es"), ("17 de junio de este añofoo", "es"),
            ("17 de junho deste ano 2025", "pt"), ("17 de junho de este anofoo", "pt"),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
                    self.parse(text, language)
                self.assertTrue(is_date_reply(text, language))
        self.assertEqual(self.parse("3 de mayo de este año, 25 USD"), DateInterpretation(date(2032, 5, 3), True))
        self.assertEqual(mask_request_dates("3 de mayo de este año, 25 USD", "es").strip(), "25 usd")

    def test_invalid_numeric_widths_calendar_and_separators_are_not_guessed(self):
        for text in (
            "20226-17-05", "2026-17-05", "2026-6-16", "2026-02-30",
            "3/05/2026", "03/5/2026", "03/05/26", "03/05-2026",
            "2026/05/03", "05/17/2026", "00/05/2026", "03/00/2026",
            "03/05/0000", "03/05/10000", "2026-05", "2026-05-03-04",
            "+2026-05-03", "-2026-05-03",
            "10000000000-05-03",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_date_reply(text, "es"))
                with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
                    self.parse(text)

    def test_invalid_named_days_and_years_are_not_current_year_fallbacks(self):
        for text in (
            "31 de abril 2026", "0 de mayo 2026", "003 de mayo 2026",
            "3 de mayo 26", "3 de mayo del 20226", "3 de mayo de 0000",
            "3 de mayo del -2026", "3 de mayo 10000",
            "3 de mayo del 10000000000",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
                    self.parse(text)

    def test_malformed_explicit_year_suffix_never_silently_defaults(self):
        cases = (
            ("3 de mayo +2026", "es"),
            ("3 de mayo 2026foo", "es"),
            ("3 de mayo del 2026foo", "es"),
            ("3 de mayo del", "es"),
            ("3 de mayo del mañana", "es"),
            ("3 de mayo de 2026USD", "es"),
            ("3 de mayo del,2026", "es"),
            ("3 de mayo del2026", "es"),
            ("3 de mayo de 2026.00 USD", "es"),
            ("3 de mayo de mi tarjeta", "es"),
            ("3 de maio +2026", "pt"),
            ("3 de maio 2026foo", "pt"),
            ("3 de maio de 2026foo", "pt"),
            ("3 de maio do", "pt"),
            ("3 de maio do amanhã", "pt"),
            ("3 de maio de 2026USD", "pt"),
            ("3 de maio de 2026.00 USD", "pt"),
        )
        for text, language in cases:
            with self.subTest(text=text, language=language):
                with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
                    self.parse(text, language)
                with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
                    self.parse("Busco el pago del " + text, language)
        for text, language in cases:
            if text.endswith(" USD") or text.endswith("tarjeta"):
                continue
            with self.subTest(reply=text):
                self.assertTrue(is_date_reply(text, language))
        for text, language in (
            ("3 de mayo, 25 USD", "es"),
            ("3 de mayo, 25.50 USD", "es"),
            ("3 de maio, 25,50 USD", "pt"),
        ):
            with self.subTest(amount=text):
                self.assertEqual(self.parse(text, language), DateInterpretation(date(2032, 5, 3), True))

    def test_leap_days_validate_the_supplied_or_assumed_year(self):
        self.assertEqual(self.parse("29 de febrero").value, date(2032, 2, 29))
        self.assertEqual(self.parse("29 de fevereiro 2024", "pt").value, date(2024, 2, 29))
        with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
            self.parse("29 de febrero", reference=date(2031, 1, 1))
        with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
            self.parse("29/02/2026")

    def test_dates_embedded_in_business_requests_are_extracted_without_claiming_reply(self):
        for text, language in (
            ("Busco el pago del 3 de mayo, 2026 por 25.50 USD", "es"),
            ("Quero consultar o pagamento de maio 3, 2026 de 25,50 USD", "pt"),
            ("No reconozco el cargo del 03/05/2026", "es"),
            ("Quero falar com uma pessoa sobre 2026-05-03", "pt"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text, language).value, date(2026, 5, 3))
                self.assertFalse(is_date_reply(text, language))

    def test_date_reply_prefixes_and_punctuation(self):
        for text, language in (
            ("el 3 de mayo 2026.", "es"), ("del 03/05/2026", "es"),
            ("2026-05-03.", "es"), ("03/05/2026.", "es"),
            ("fecha: 3 de mayo", "es"), ("la fecha es 03-05-2026", "es"),
            ("foi 3 de maio de 2026", "pt"), ("em 03/05/2026!", "pt"),
            ("a data é 3 de maio", "pt"),
        ):
            with self.subTest(text=text):
                self.assertTrue(is_date_reply(text, language))

    def test_multiple_distinct_dates_ambiguous_but_same_day_duplicates_allowed(self):
        for text in ("3 de mayo 2026 o 4 de mayo 2026", "03/05/2026 2026-05-04"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(DateParsingError, "^ambiguous_date$"):
                    self.parse(text)
        self.assertEqual(self.parse("3 de mayo 2026, 2026-05-03").value, date(2026, 5, 3))
        self.assertEqual(self.parse("3 de mayo y 2026-05-03", reference=date(2026, 1, 1)),
                         DateInterpretation(date(2026, 5, 3), True))
        with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
            self.parse("3 de mayo 2026 y 31 de abril 2026")

    def test_non_date_prose_relative_dates_and_identifiers_are_not_dates(self):
        for text in (
            "Hola", "Quiero comer", "hello", "mayo", "2026", "ayer", "hoje",
            "3 dias", "3 de mayonesa", "TRX-2026-05-03", "ID_03/05/2026",
            "2026-05-03-ref", "2026-05-03foo", "3 de mayofoo 2026",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_date_reply(text, "es"))
                self.assertEqual(self.parse(text), DateInterpretation(None))

    def test_mask_prevents_year_or_day_becoming_currency_amount(self):
        for text, expected_remaining in (
            ("03/05/2026 USD", "USD"),
            ("3 de mayo 2026 USD", "USD"),
            ("mayo 3 USD", "USD"),
            ("3 de mayo, 25.50 USD", ", 25.50 USD"),
            ("3 de mayo, 25,50 USD", ", 25,50 USD"),
            ("3 de mayo, 25 USD", ", 25 USD"),
            ("03/05/2026 por 25.50 USD", "por 25.50 USD"),
        ):
            with self.subTest(text=text):
                self.assertEqual(mask_request_dates(text, "es").strip(), expected_remaining.casefold())
                self.assertEqual(self.parse(text).value.month, 5)

    def test_malformed_types_are_fixed_errors_and_datetime_not_reference_date(self):
        for reference in (None, "2026-05-03", datetime(2026, 5, 3)):
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
                    extract_request_date("3 de mayo", "es", reference_date=reference)
        for text, language in ((None, "es"), ("3 de mayo", "en"), ("3 de mayo", [])):
            with self.subTest(text=text, language=language):
                with self.assertRaisesRegex(DateParsingError, "^invalid_date$"):
                    self.parse(text, language)


if __name__ == "__main__":
    unittest.main()
