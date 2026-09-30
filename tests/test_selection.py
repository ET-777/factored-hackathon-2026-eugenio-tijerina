"""Synthetic selection, clarification, and authorization contracts."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from bank_service.access import AccessDenied, Permission, TrustedSession
from bank_service.records import TransactionRecord
from bank_service.responses import answer_transaction
from bank_service.selection import (
    SelectionError,
    TransactionFilters,
    _validate_filters,
    find_transactions,
    select_transaction,
)
from bank_service.transactions import SourceReference, SourcedTransaction


def sourced_transaction(identifier="SYNTH-T-A", **changes):
    record = TransactionRecord(
        transaction_id=identifier,
        customer_id="SYNTH-C-OWNER",
        product_id="SYNTH-P-1",
        transaction_date=datetime(2026, 6, 16, 12, 30),
        process_date=date(2026, 6, 17),
        transaction_type="Purchase",
        amount=Decimal("10.00"),
        currency="USD",
        transaction_status="Approved",
        merchant_name="Synthetic shop",
    )
    return SourcedTransaction(
        replace(record, **changes),
        (SourceReference("synthetic/transactions.csv", 1, "a" * 64),),
    )


class UnreadableMapping(Mapping):
    """Make premature repository access observable without any private records."""

    def __getitem__(self, key):
        raise AssertionError("Repository must not be accessed")

    def __iter__(self):
        raise AssertionError("Repository must not be iterated")

    def __len__(self):
        raise AssertionError("Repository size must not be inspected")


class FilterValidationTests(unittest.TestCase):
    def test_accepts_empty_date_currency_and_exact_finite_amount_filters(self):
        for filters in (
            TransactionFilters(),
            TransactionFilters(transaction_date=date(2026, 6, 16)),
            TransactionFilters(currency="COP"),
            TransactionFilters(amount=Decimal("0.00"), currency="USD"),
            TransactionFilters(amount=Decimal("-12.34"), currency="ARS"),
            TransactionFilters(amount=Decimal("0.1000000000000000000000000001"), currency="USD"),
        ):
            with self.subTest(filters=filters):
                self.assertIsNone(_validate_filters(filters))

    def test_rejects_invalid_types_nonfinite_amounts_and_missing_currency(self):
        cases = [None, {}, "", False]
        cases += [TransactionFilters(transaction_date=value)
                  for value in (datetime(2026, 6, 16), "2026-06-16", "", 0, False)]
        cases += [TransactionFilters(amount=value, currency="USD")
                  for value in (0, 0.0, False, "0", Decimal("NaN"), Decimal("sNaN"),
                                Decimal("Infinity"), Decimal("-Infinity"))]
        cases += [TransactionFilters(amount=value) for value in (Decimal("0"), Decimal("1"))]
        cases += [TransactionFilters(currency=value)
                  for value in (False, "", [], "BRL", "usd", "SYNTHETIC_PRIVATE_FILTER")]
        for index, filters in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(SelectionError) as caught:
                    _validate_filters(filters)
                self.assertNotIn("SYNTHETIC_PRIVATE_FILTER", str(caught.exception))


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        self.session = TrustedSession(
            "SYNTH-C-OWNER", self.now + timedelta(minutes=5),
            frozenset({Permission.READ_TRANSACTION}),
        )

    def find(self, filters, records, *, session=None, now=None):
        return find_transactions(
            self.session if session is None else session,
            filters, records=records, now=self.now if now is None else now,
        )

    def test_authenticates_before_filter_validation_or_repository_access(self):
        cases = [
            (None, self.now),
            ({"customer_id": "SYNTH-C-OWNER"}, self.now),
            (replace(self.session, expires_at=self.now), self.now),
            (replace(self.session, expires_at=self.now - timedelta(seconds=1)), self.now),
            (replace(self.session, permissions=frozenset()), self.now),
            (replace(self.session, permissions=frozenset({Permission.CREATE_SIMULATED_INTAKE})), self.now),
            (self.session, self.now.replace(tzinfo=None)),
        ]
        for index, (session, now) in enumerate(cases):
            for filters in (None, TransactionFilters()):
                with self.subTest(case=index, filters=filters):
                    with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                        find_transactions(session, filters, records=UnreadableMapping(), now=now)

    def test_empty_filters_return_empty_tuple_without_scanning(self):
        result = self.find(TransactionFilters(), UnreadableMapping())
        self.assertEqual(result, ())
        self.assertIsInstance(result, tuple)

    def test_rejects_invalid_repository_shapes_and_enforces_record_cap(self):
        filters = TransactionFilters(currency="USD")
        for records in (None, [], {"SYNTH-T-A": None},
                        {"SYNTH-T-A": SourcedTransaction(None, ())}):
            with self.subTest(records_type=type(records)), self.assertRaises(SelectionError):
                self.find(filters, records)
        records = {f"SYNTH-T-{number:03d}": sourced_transaction(f"SYNTH-T-{number:03d}")
                   for number in range(200)}
        self.assertEqual(len(self.find(filters, records)), 200)
        records["SYNTH-T-200"] = sourced_transaction("SYNTH-T-200")
        with self.assertRaises(SelectionError):
            self.find(filters, records)

    def test_combines_all_supplied_filters_with_and(self):
        entries = (
            sourced_transaction("SYNTH-T-A"),
            sourced_transaction("SYNTH-T-B", transaction_date=datetime(2026, 6, 15, 12, 30)),
            sourced_transaction("SYNTH-T-C", currency="COP"),
            sourced_transaction("SYNTH-T-D", amount=Decimal("11.00")),
        )
        records = {entry.record.transaction_id: entry for entry in entries}
        cases = (
            (TransactionFilters(date(2026, 6, 16), Decimal("10.00"), "USD"), ["SYNTH-T-A"]),
            (TransactionFilters(amount=Decimal("10.00"), currency="USD"), ["SYNTH-T-A", "SYNTH-T-B"]),
            (TransactionFilters(transaction_date=date(2026, 6, 16)), ["SYNTH-T-A", "SYNTH-T-C", "SYNTH-T-D"]),
            (TransactionFilters(currency="USD"), ["SYNTH-T-A", "SYNTH-T-B", "SYNTH-T-D"]),
        )
        for filters, expected in cases:
            with self.subTest(filters=filters):
                result = self.find(filters, records)
                self.assertEqual([entry.record.transaction_id for entry in result], expected)

    def test_zero_negative_and_high_precision_amounts_match_exact_native_currency(self):
        exact = Decimal("0.1000000000000000000000000001")
        entries = (
            sourced_transaction("SYNTH-ZERO", amount=Decimal("0.00")),
            sourced_transaction("SYNTH-NEGATIVE", amount=Decimal("-12.34"), currency="COP"),
            sourced_transaction("SYNTH-EXACT", amount=exact),
            sourced_transaction("SYNTH-ROUNDED", amount=Decimal("0.1")),
            sourced_transaction("SYNTH-OTHER-CURRENCY", amount=exact, currency="ARS"),
        )
        records = {entry.record.transaction_id: entry for entry in entries}
        for amount, currency, identifier in (
            (Decimal("0.00"), "USD", "SYNTH-ZERO"),
            (Decimal("-12.34"), "COP", "SYNTH-NEGATIVE"),
            (exact, "USD", "SYNTH-EXACT"),
        ):
            with self.subTest(identifier=identifier):
                result = self.find(TransactionFilters(amount=amount, currency=currency), records)
                self.assertEqual([entry.record.transaction_id for entry in result], [identifier])
                self.assertIs(result[0], records[identifier])

    def test_date_matching_uses_recorded_calendar_date_without_timezone_conversion(self):
        local = datetime(2026, 6, 16, 0, 30, tzinfo=timezone(timedelta(hours=14)))
        utc = local.astimezone(timezone.utc)
        records = {
            "SYNTH-LOCAL": sourced_transaction("SYNTH-LOCAL", transaction_date=local),
            "SYNTH-UTC": sourced_transaction("SYNTH-UTC", transaction_date=utc),
            "SYNTH-NAIVE": sourced_transaction("SYNTH-NAIVE", transaction_date=local.replace(tzinfo=None)),
        }
        result = self.find(TransactionFilters(transaction_date=date(2026, 6, 16)), records)
        self.assertEqual([entry.record.transaction_id for entry in result], ["SYNTH-LOCAL", "SYNTH-NAIVE"])

    def test_foreign_records_are_skipped_before_business_fields_and_do_not_add_ambiguity(self):
        class UnreadableFact:
            def __eq__(self, other):
                raise AssertionError("Foreign business fact must not be compared")

            def date(self):
                raise AssertionError("Foreign transaction date must not be inspected")

        own = sourced_transaction()
        records = {
            "SYNTH-FOREIGN": sourced_transaction("SYNTH-FOREIGN", customer_id="SYNTH-OTHER"),
            "SYNTH-FOREIGN-UNREADABLE": sourced_transaction(
                "SYNTH-FOREIGN-UNREADABLE", customer_id="SYNTH-OTHER",
                amount=UnreadableFact(), currency=UnreadableFact(), transaction_date=UnreadableFact(),
            ),
            "SYNTH-T-A": own,
        }
        filters = TransactionFilters(date(2026, 6, 16), Decimal("10.00"), "USD")
        self.assertEqual(self.find(filters, records), (own,))
        result = select_transaction(self.session, filters, records=records, language="es", now=self.now)
        self.assertEqual(result.status, "selected")
        self.assertEqual(result.candidate_ids, ("SYNTH-T-A",))

    def test_scans_late_matches_and_returns_sorted_original_entries(self):
        first = sourced_transaction("SYNTH-T-Z")
        last = sourced_transaction("SYNTH-T-A")
        records = {
            "SYNTH-T-Z": first,
            "SYNTH-NONMATCH": sourced_transaction("SYNTH-NONMATCH", currency="COP"),
            "SYNTH-T-A": last,
        }
        filters = TransactionFilters(currency="USD")
        result = self.find(filters, records)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIs(result[0], last)
        self.assertIs(result[1], first)
        selection = select_transaction(self.session, filters, records=records, language="pt", now=self.now)
        self.assertEqual(selection.status, "ambiguous")
        self.assertEqual(selection.candidate_ids, ("SYNTH-T-A", "SYNTH-T-Z"))

    def test_owned_mapping_key_mismatch_denies_instead_of_returning_partial_success(self):
        records = {
            "SYNTH-T-A": sourced_transaction("SYNTH-T-A"),
            "SYNTH-WRONG-KEY": sourced_transaction("SYNTH-T-B"),
        }
        with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
            self.find(TransactionFilters(currency="USD"), records)

    def test_four_selection_states_have_localized_static_clarifications(self):
        records = {
            "SYNTH-T-A": sourced_transaction("SYNTH-T-A"),
            "SYNTH-T-B": sourced_transaction("SYNTH-T-B", amount=Decimal("20")),
            "SYNTH-FOREIGN": sourced_transaction("SYNTH-FOREIGN", customer_id="SYNTH-OTHER"),
        }
        cases = (
            (TransactionFilters(), "needs_filters", (), {"es": "Indica", "pt": "Informe"}),
            (TransactionFilters(amount=Decimal("999.99"), currency="USD"), "no_match", (),
             {"es": "No encontré", "pt": "Não encontrei"}),
            (TransactionFilters(amount=Decimal("10"), currency="USD"), "selected", ("SYNTH-T-A",), None),
            (TransactionFilters(currency="USD"), "ambiguous", ("SYNTH-T-A", "SYNTH-T-B"),
             {"es": "varias", "pt": "várias"}),
        )
        for language in ("es", "pt"):
            for filters, status, ids, phrases in cases:
                with self.subTest(language=language, status=status):
                    result = select_transaction(self.session, filters, records=records, language=language, now=self.now)
                    self.assertEqual((result.language, result.status, result.candidate_ids), (language, status, ids))
                    if phrases is None:
                        self.assertIsNone(result.clarification)
                    else:
                        self.assertIn(phrases[language], result.clarification)
                        for private_value in ("SYNTH", "999.99", "USD", "Synthetic shop"):
                            self.assertNotIn(private_value, result.clarification)

    def test_unsupported_languages_fail_after_authorization(self):
        records = {"SYNTH-T-A": sourced_transaction()}
        for language in (None, "", "en", "ES", [], {}):
            with self.subTest(language=language):
                with self.assertRaises(SelectionError):
                    select_transaction(self.session, TransactionFilters(currency="USD"),
                                       records=records, language=language, now=self.now)
                with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                    select_transaction(None, TransactionFilters(), records=UnreadableMapping(),
                                       language=language, now=self.now)

    def test_selected_id_can_be_answered_and_every_followup_reauthorizes(self):
        entry = sourced_transaction()
        records = {"SYNTH-T-A": entry}
        filters = TransactionFilters(amount=Decimal("10"), currency="USD")
        selection = select_transaction(self.session, filters, records=records, language="pt", now=self.now)
        self.assertEqual(selection.status, "selected")
        identifier = selection.candidate_ids[0]
        answer = answer_transaction(self.session, identifier, records=records, language="pt", now=self.now)
        self.assertIn("10.00 USD", answer.text)
        self.assertIs(answer.sources, entry.sources)
        for instant in (self.session.expires_at, self.session.expires_at + timedelta(seconds=1)):
            with self.subTest(instant=instant):
                with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                    select_transaction(self.session, filters, records=records, language="pt", now=instant)
                with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                    answer_transaction(self.session, identifier, records=records, language="pt", now=instant)


if __name__ == "__main__":
    unittest.main()
