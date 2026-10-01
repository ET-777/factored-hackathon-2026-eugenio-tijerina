import unittest
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import date, datetime
from decimal import Decimal

from bank_service.records import (
    CustomerRecord,
    ProductRecord,
    RecordValidationError,
    TransactionRecord,
    parse_customer,
    parse_product,
    validate_transaction_links,
)


class ParseCustomerTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "customer_id": " DEMO-CUSTOMER-A ",
            "registration_date": "2026-06-01 09:00:00",
            "first_name": "Synthetic Name",
            "email": "demo@example.invalid",
        }

    def test_parses_only_customer_fields_without_mutating_input(self):
        original = self.row.copy()

        record = parse_customer(self.row)

        self.assertIsInstance(record, CustomerRecord)
        self.assertEqual(record.customer_id, "DEMO-CUSTOMER-A")
        self.assertEqual(record.registration_date, datetime(2026, 6, 1, 9))
        self.assertIs(type(record.registration_date), datetime)
        self.assertIsNone(record.registration_date.tzinfo)
        self.assertEqual(set(vars(record)), {"customer_id", "registration_date"})
        self.assertEqual(self.row, original)

    def test_preserves_registration_timestamp_offset(self):
        value = "2026-06-01T09:00:00.123456-05:00"

        record = parse_customer({**self.row, "registration_date": value})

        self.assertEqual(record.registration_date.isoformat(), value)

    def test_rejects_missing_or_invalid_required_fields(self):
        cases = [None, [], {}]
        for field in ("customer_id", "registration_date"):
            row = self.row.copy()
            del row[field]
            cases.append(row)
        for field, value in (
            ("customer_id", " "), ("customer_id", 123),
            ("registration_date", None), ("registration_date", "2026-06-01"),
        ):
            cases.append({**self.row, field: value})

        for index, row in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(RecordValidationError):
                parse_customer(row)

    def test_customer_record_is_immutable(self):
        record = parse_customer(self.row)

        with self.assertRaises(FrozenInstanceError):
            record.customer_id = "DEMO-CUSTOMER-B"


class ParseProductTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "product_id": " DEMO-PRODUCT-A ",
            "customer_id": " DEMO-CUSTOMER-A ",
            "currency": "USD",
            "opening_date": "2026-06-05",
            "product_number": "SYNTHETIC-UNNEEDED-NUMBER",
            "current_balance": "999.99",
        }

    def test_parses_only_product_fields_without_mutating_input(self):
        original = self.row.copy()

        record = parse_product(self.row)

        self.assertEqual(record, ProductRecord(
            product_id="DEMO-PRODUCT-A",
            customer_id="DEMO-CUSTOMER-A",
            currency="USD",
            opening_date=date(2026, 6, 5),
        ))
        self.assertIs(type(record.opening_date), date)
        self.assertEqual(set(vars(record)), {"product_id", "customer_id", "currency", "opening_date"})
        self.assertEqual(self.row, original)

    def test_accepts_supported_currency_with_outer_whitespace(self):
        for currency in ("USD", "COP", "ARS", "MXN"):
            with self.subTest(currency=currency):
                record = parse_product({**self.row, "currency": f" {currency} "})

                self.assertEqual(record.currency, currency)

    def test_rejects_missing_or_invalid_required_fields(self):
        cases = [None, [], {}]
        for field in ("product_id", "customer_id", "currency", "opening_date"):
            row = self.row.copy()
            del row[field]
            cases.append(row)
        for field, value in (
            ("product_id", " "), ("customer_id", None),
            ("currency", "BRL"), ("currency", "EUR"), ("currency", "usd"), ("currency", 123),
            ("opening_date", "2026-02-30"), ("opening_date", "2026-06-05T12:30:00"),
        ):
            cases.append({**self.row, field: value})

        for index, row in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(RecordValidationError):
                parse_product(row)

    def test_unsupported_currency_error_does_not_echo_value(self):
        marker = "SYNTHETIC_PRIVATE_MARKER"

        with self.assertRaises(RecordValidationError) as raised:
            parse_product({**self.row, "currency": marker})

        self.assertNotIn(marker, str(raised.exception))

    def test_product_record_is_immutable(self):
        record = parse_product(self.row)

        with self.assertRaises(FrozenInstanceError):
            record.customer_id = "DEMO-CUSTOMER-B"


class TransactionLinkTests(unittest.TestCase):
    def setUp(self):
        self.transaction = TransactionRecord(
            transaction_id="DEMO-TX-001",
            customer_id="DEMO-CUSTOMER-A",
            product_id="DEMO-PRODUCT-A",
            transaction_date=datetime(2026, 6, 16, 12, 30, 45),
            process_date=date(2026, 6, 17),
            transaction_type="Purchase",
            amount=Decimal("123.45"),
            currency="USD",
            transaction_status="Approved",
            merchant_name=None,
        )
        self.customer = CustomerRecord("DEMO-CUSTOMER-A", datetime(2026, 6, 1, 9))
        self.product = ProductRecord("DEMO-PRODUCT-A", "DEMO-CUSTOMER-A", "USD", date(2026, 6, 5))

    def test_matching_records_pass_without_mutation(self):
        for currency in ("USD", "COP", "ARS", "MXN"):
            with self.subTest(currency=currency):
                records = (replace(self.transaction, currency=currency), self.customer,
                           replace(self.product, currency=currency))
                before = tuple(asdict(record) for record in records)

                result = validate_transaction_links(*records)

                self.assertIsNone(result)
                self.assertEqual(tuple(asdict(record) for record in records), before)

    def test_rejects_missing_or_wrong_record_objects(self):
        for position in range(3):
            for invalid in (None, {}, "not-a-record"):
                with self.subTest(position=position, invalid_type=type(invalid).__name__):
                    records = [self.transaction, self.customer, self.product]
                    records[position] = invalid

                    with self.assertRaises(RecordValidationError):
                        validate_transaction_links(*records)

    def test_rejects_each_link_mismatch_without_echoing_values(self):
        marker = "SYNTHETIC_PRIVATE_IDENTIFIER"
        cases = (
            ("customer reference", self.transaction, replace(self.customer, customer_id=marker), self.product, marker),
            ("product reference", self.transaction, self.customer, replace(self.product, product_id=marker), marker),
            ("product owner", self.transaction, self.customer, replace(self.product, customer_id=marker), marker),
            ("currency", self.transaction, self.customer, replace(self.product, currency="COP"), "COP"),
        )
        for label, transaction, customer, product, rejected_value in cases:
            with self.subTest(case=label):
                with self.assertRaises(RecordValidationError) as raised:
                    validate_transaction_links(transaction, customer, product)

                self.assertNotIn(rejected_value, str(raised.exception))

    def test_rejects_event_before_product_opening(self):
        transaction = replace(self.transaction, transaction_date=datetime(2026, 6, 4, 23, 59))

        with self.assertRaises(RecordValidationError):
            validate_transaction_links(transaction, self.customer, self.product)

    def test_rejects_event_before_customer_registration(self):
        customer = replace(self.customer, registration_date=datetime(2026, 6, 17))

        with self.assertRaises(RecordValidationError):
            validate_transaction_links(self.transaction, customer, self.product)

    def test_accepts_same_calendar_day_without_claiming_time_order(self):
        transaction = replace(self.transaction, transaction_date=datetime(2026, 6, 16))
        customer = replace(self.customer, registration_date=datetime(2026, 6, 16, 23, 59))
        product = replace(self.product, opening_date=date(2026, 6, 16))

        self.assertIsNone(validate_transaction_links(transaction, customer, product))

    def test_uses_event_date_instead_of_processing_date(self):
        invalid_event = replace(
            self.transaction,
            transaction_date=datetime(2026, 6, 4),
            process_date=date(2026, 6, 20),
        )
        with self.assertRaises(RecordValidationError):
            validate_transaction_links(invalid_event, self.customer, self.product)

        old_process_date = replace(self.transaction, process_date=date(2026, 5, 1))
        self.assertIsNone(validate_transaction_links(old_process_date, self.customer, self.product))

    def test_uses_source_calendar_dates_without_timezone_conversion(self):
        transaction = replace(
            self.transaction,
            transaction_date=datetime.fromisoformat("2026-06-16T00:15:00+14:00"),
        )
        product = replace(self.product, opening_date=date(2026, 6, 16))
        for registration in (
            datetime(2026, 6, 15, 23, 45),
            datetime.fromisoformat("2026-06-15T23:45:00-10:00"),
        ):
            with self.subTest(registration_has_offset=registration.tzinfo is not None):
                customer = replace(self.customer, registration_date=registration)

                self.assertIsNone(validate_transaction_links(transaction, customer, product))

        customer = replace(self.customer, registration_date=datetime.fromisoformat("2026-06-01T09:00:00-05:00"))
        self.assertIsNone(validate_transaction_links(self.transaction, customer, self.product))


if __name__ == "__main__":
    unittest.main()
