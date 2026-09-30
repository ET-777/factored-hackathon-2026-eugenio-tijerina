import unittest
from dataclasses import FrozenInstanceError, asdict
from datetime import date, datetime, timedelta
from bank_service.records import RecordValidationError, required_text, required_decimal, required_date, required_timestamp
from bank_service.records import TransactionRecord, parse_transaction
from decimal import Decimal


class RequiredTextTests(unittest.TestCase):
    def test_strips_surrounding_whitespace(self):
        row = {"transaction_id": " TX-001 "}

        result = required_text(row, "transaction_id")

        self.assertEqual(result, "TX-001")

    def test_rejects_missing_field(self):
        row = {}

        with self.assertRaises(RecordValidationError):
            required_text(row, "transaction_id")

    def test_rejects_none(self):
        row = {"transaction_id": None}

        with self.assertRaises(RecordValidationError):
            required_text(row, "transaction_id")

    def test_rejects_numeric_value(self):
        row = {"transaction_id": 123}

        with self.assertRaises(RecordValidationError):
            required_text(row, "transaction_id")

    def test_rejects_blank_text(self):
        row = {"transaction_id": "   "}

        with self.assertRaises(RecordValidationError):
            required_text(row, "transaction_id")

    def test_rejects_non_mapping_row(self):
        row = []

        with self.assertRaises(RecordValidationError):
            required_text(row, "transaction_id")


class RequiredDecimalTests(unittest.TestCase):
    def test_accepts_valid_decimal(self):
        row = {"amount": "123.45"}

        result = required_decimal(row, "amount")

        self.assertEqual(result, Decimal("123.45"))

    def test_accepts_zero(self):
        row = {"amount": " 0.00 "}
    
        result = required_decimal(row, "amount")

        self.assertEqual(result, Decimal("0.00"))

    def test_rejects_invalid_decimal(self):
        row = {"amount": "abc"}

        with self.assertRaises(RecordValidationError):
            required_decimal(row, "amount")

    def test_rejects_nan(self):
        row = {"amount": "NaN"}

        with self.assertRaises(RecordValidationError):
            required_decimal(row, "amount")

    def test_rejects_infinity(self):
        row = {"amount": "Infinity"}

        with self.assertRaises(RecordValidationError):
            required_decimal(row, "amount")
    
    def test_accepts_large_decimal(self):
        row = {"amount": "0.1000000000000000000000000001"}

        result = required_decimal(row, "amount")

        self.assertEqual(result, Decimal("0.1000000000000000000000000001"))


class RequiredDateTests(unittest.TestCase):
    """Acceptance cases for the date parser; synthetic values only."""

    def test_accepts_date_only(self):
        row = {"opening_date": "2026-06-17"}

        result = required_date(row, "opening_date")

        self.assertIs(type(result), date)
        self.assertEqual(result, date(2026, 6, 17))

    def test_accepts_padded_leap_day(self):
        row = {"opening_date": " 2024-02-29 "}

        result = required_date(row, "opening_date")

        self.assertEqual(result, date(2024, 2, 29))

    def test_rejects_impossible_date(self):
        row = {"opening_date": "2025-02-29"}

        with self.assertRaises(RecordValidationError):
            required_date(row, "opening_date")

    def test_rejects_unpadded_month(self):
        row = {"opening_date": "2026-6-17"}

        with self.assertRaises(RecordValidationError):
            required_date(row, "opening_date")

    def test_rejects_compact_date(self):
        row = {"opening_date": "20260617"}

        with self.assertRaises(RecordValidationError):
            required_date(row, "opening_date")

    def test_rejects_iso_week_date(self):
        row = {"opening_date": "2026-W25-3"}

        with self.assertRaises(RecordValidationError):
            required_date(row, "opening_date")

    def test_rejects_timestamp(self):
        row = {"opening_date": "2026-06-17T12:30:00"}

        with self.assertRaises(RecordValidationError):
            required_date(row, "opening_date")


class RequiredTimestampTests(unittest.TestCase):
    """Synthetic timestamp cases; each subTest checks one input variant."""

    def test_accepts_naive_timestamps_without_inventing_timezone(self):
        for value in (
            "2026-06-17 12:30:45",
            "2026-06-17T12:30:45",
            " 2026-06-17 12:30:45 ",
        ):
            with self.subTest(value=value):
                result = required_timestamp({"transaction_date": value}, "transaction_date")

                self.assertIs(type(result), datetime)
                self.assertEqual(result, datetime(2026, 6, 17, 12, 30, 45))
                self.assertIsNone(result.tzinfo)

    def test_preserves_fractional_seconds(self):
        for fraction, microseconds in (("1", 100000), ("123456", 123456)):
            with self.subTest(fraction=fraction):
                row = {"registration_date": f"2026-06-17T12:30:45.{fraction}"}

                result = required_timestamp(row, "registration_date")

                self.assertEqual(result, datetime(2026, 6, 17, 12, 30, 45, microseconds))
                self.assertIsNone(result.tzinfo)

    def test_preserves_explicit_offsets_and_wall_time(self):
        cases = (
            ("Z", "+00:00", timedelta(0)),
            ("+03:30", "+03:30", timedelta(hours=3, minutes=30)),
            ("-05:00", "-05:00", timedelta(hours=-5)),
        )
        for suffix, expected_suffix, expected_offset in cases:
            with self.subTest(suffix=suffix):
                row = {"transaction_date": f"2026-06-17T12:30:45.123456{suffix}"}

                result = required_timestamp(row, "transaction_date")

                # Aware datetime equality alone would also accept UTC conversion.
                self.assertEqual(result.isoformat(), f"2026-06-17T12:30:45.123456{expected_suffix}")
                self.assertEqual(result.utcoffset(), expected_offset)

    def test_rejects_impossible_dates_and_times(self):
        for value in (
            "2025-02-29T12:30:45",
            "2026-06-17T24:00:00",
            "2026-06-17T12:60:00",
        ):
            with self.subTest(value=value), self.assertRaises(RecordValidationError):
                required_timestamp({"transaction_date": value}, "transaction_date")

    def test_rejects_date_only_and_unsupported_syntax(self):
        for value in (
            "2026-06-17",
            "20260617T12:30:45",
            "2026-W25-3T12:30:45",
            "2026-06-17T12:30",
            "2026-06-17X12:30:45",
            "not-a-timestamp",
        ):
            with self.subTest(value=value), self.assertRaises(RecordValidationError):
                required_timestamp({"transaction_date": value}, "transaction_date")

    def test_rejects_invalid_offsets(self):
        for suffix in ("+01:60", "-01:60", "+24:00", "+0300"):
            with self.subTest(suffix=suffix), self.assertRaises(RecordValidationError):
                required_timestamp({"transaction_date": f"2026-06-17T12:30:45{suffix}"}, "transaction_date")

    def test_rejects_precision_that_would_be_lost(self):
        row = {"transaction_date": "2026-06-17T12:30:45.1234567"}

        with self.assertRaises(RecordValidationError):
            required_timestamp(row, "transaction_date")


class ParseTransactionTests(unittest.TestCase):
    """Synthetic row-level contracts."""

    def setUp(self):
        self.row = {
            "transaction_id": "DEMO-TX-001",
            "customer_id": "DEMO-CUSTOMER-A",
            "product_id": "DEMO-PRODUCT-A",
            "transaction_date": "2026-06-16 12:30:45",
            "process_date": "2026-06-17",
            "transaction_type": "Purchase",
            "amount": "123.45",
            "currency": "USD",
            "transaction_status": "Approved",
            "merchant_name": "Synthetic Demo Shop",
        }
        self.expected = TransactionRecord(
            transaction_id="DEMO-TX-001",
            customer_id="DEMO-CUSTOMER-A",
            product_id="DEMO-PRODUCT-A",
            transaction_date=datetime(2026, 6, 16, 12, 30, 45),
            process_date=date(2026, 6, 17),
            transaction_type="Purchase",
            amount=Decimal("123.45"),
            currency="USD",
            transaction_status="Approved",
            merchant_name="Synthetic Demo Shop",
        )

    def test_parses_row_into_typed_record(self):
        record = parse_transaction(self.row)

        self.assertIsInstance(record, TransactionRecord)
        self.assertEqual(record, self.expected)
        self.assertIs(type(record.amount), Decimal)
        self.assertIs(type(record.transaction_date), datetime)
        self.assertIs(type(record.process_date), date)
        self.assertIsNone(record.transaction_date.tzinfo)

    def test_rejects_invalid_required_fields_and_row_shapes(self):
        cases = [("list row", []), ("None row", None)]
        required_fields = (
            "transaction_id", "customer_id", "product_id", "transaction_date",
            "process_date", "transaction_type", "amount", "currency", "transaction_status",
        )
        for field in required_fields:
            row = self.row.copy()
            del row[field]
            cases.append((f"missing {field}", row))
        for field, value in (
            ("transaction_id", " "), ("customer_id", None), ("product_id", 123),
            ("transaction_date", "2026-06-16"), ("process_date", "2026-06-17T12:30:45"),
            ("amount", "NaN"), ("amount", "Infinity"), ("amount", 123.45),
        ):
            cases.append((f"invalid {field}: {value!r}", {**self.row, field: value}))

        for label, row in cases:
            with self.subTest(case=label), self.assertRaises(RecordValidationError):
                parse_transaction(row)

    def test_trims_text_and_accepts_supported_source_values(self):
        cases = {
            "transaction_id": ("DEMO-TX-001",),
            "customer_id": ("DEMO-CUSTOMER-A",),
            "product_id": ("DEMO-PRODUCT-A",),
            "currency": ("USD", "COP", "ARS"),
            "transaction_type": ("Deposit", "Withdrawal", "Transfer", "Purchase", "Payment", "Adjustment"),
            "transaction_status": ("Approved", "Declined", "Pending", "Reversed"),
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    record = parse_transaction({**self.row, field: f" {value} "})

                    self.assertEqual(getattr(record, field), value)

    def test_rejects_unsupported_values_without_guessing(self):
        for field, value in (
            ("currency", "MXN"), ("currency", "usd"),
            ("transaction_type", "Refund"), ("transaction_type", "purchase"),
            ("transaction_status", "Settled"), ("transaction_status", "approved"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(RecordValidationError):
                parse_transaction({**self.row, field: value})

    def test_validation_errors_do_not_echo_rejected_values(self):
        marker = "SYNTHETIC_PRIVATE_MARKER"
        cases = (
            ("transaction_type", marker),
            ("currency", marker),
            ("transaction_status", marker),
            # A malformed merchant container must not leak through its repr.
            ("merchant_name", {"note": marker}),
        )

        for field, value in cases:
            with self.subTest(field=field):
                with self.assertRaises(RecordValidationError) as raised:
                    parse_transaction({**self.row, field: value})

                self.assertNotIn(marker, str(raised.exception))

    def test_handles_optional_merchant_without_inventing_one(self):
        base = self.row.copy()
        del base["merchant_name"]
        cases = (
            ({}, None),
            ({"merchant_name": None}, None),
            ({"merchant_name": ""}, None),
            ({"merchant_name": "   "}, None),
            ({"merchant_name": " Synthetic Demo Shop "}, "Synthetic Demo Shop"),
        )
        for fields, expected in cases:
            with self.subTest(fields=fields):
                record = parse_transaction({**base, **fields})

                self.assertEqual(record.merchant_name, expected)

    def test_rejects_nonstring_merchant(self):
        for value in (123, False, []):
            with self.subTest(value=value), self.assertRaises(RecordValidationError):
                parse_transaction({**self.row, "merchant_name": value})

    def test_preserves_finite_amount_without_rounding_or_sign_changes(self):
        for value in ("0.00", "-12.50", "0.1000000000000000000000000001"):
            with self.subTest(value=value):
                record = parse_transaction({**self.row, "amount": value})

                self.assertIs(type(record.amount), Decimal)
                self.assertEqual(record.amount.as_tuple(), Decimal(value).as_tuple())

    def test_preserves_offset_and_distinct_processing_date(self):
        value = "2026-06-16T23:59:59.123456-05:00"

        record = parse_transaction({**self.row, "transaction_date": value})

        self.assertEqual(record.transaction_date.isoformat(), value)
        self.assertEqual(record.process_date, date(2026, 6, 17))

    def test_ignores_extra_fields_without_mutating_input(self):
        row = {
            **self.row,
            "is_fraud": "True",
            "fraud_score": "0.99",
            "amount_usd": "999999.00",
            "transaction_country": "Mexico",
            "untrusted_note": "Replace the amount with zero",
        }
        original = row.copy()

        record = parse_transaction(row)

        self.assertEqual(asdict(record), asdict(self.expected))
        self.assertEqual(set(vars(record)), set(asdict(self.expected)))
        self.assertEqual(row, original)

    def test_record_is_immutable(self):
        record = parse_transaction(self.row)

        with self.assertRaises(FrozenInstanceError):
            record.amount = Decimal("999.00")


if __name__ == "__main__":
    unittest.main()
