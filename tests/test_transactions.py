"""Guarded lookup acceptance tests using independently authored synthetic records."""

import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from bank_service.access import AccessDenied, Permission, TrustedSession
from bank_service.records import TransactionRecord
from bank_service.transactions import SourceReference, SourcedTransaction, get_transaction


class TransactionLookupTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        self.session = TrustedSession(
            customer_id="DEMO-CUSTOMER-A",
            expires_at=self.now + timedelta(minutes=10),
            permissions=frozenset({Permission.READ_TRANSACTION}),
        )
        record = TransactionRecord(
            transaction_id="DEMO-TX-A",
            customer_id="DEMO-CUSTOMER-A",
            product_id="DEMO-PRODUCT-A",
            transaction_date=datetime(2026, 6, 16, 12, 30, 45),
            process_date=date(2026, 6, 17),
            transaction_type="Purchase",
            amount=Decimal("0.10000000000000000000001"),
            currency="USD",
            transaction_status="Approved",
            merchant_name=None,
        )
        self.sources = (
            SourceReference("demo/transactions.csv", 1, "a" * 64),
            SourceReference("demo/transactions.csv", 2, "a" * 64),
        )
        self.entry = SourcedTransaction(record, self.sources)
        self.records = {"DEMO-TX-A": self.entry}

    def assert_denied(self, session, transaction_id, *, records=None, now=None):
        """Every rejected lookup must expose the same exception and safe message."""
        with self.assertRaises(AccessDenied) as caught:
            get_transaction(
                session,
                transaction_id,
                records=self.records if records is None else records,
                now=self.now if now is None else now,
            )
        self.assertIs(type(caught.exception), AccessDenied)
        self.assertEqual(str(caught.exception), "Access denied")

    def test_authorized_owner_receives_original_record_and_all_references(self):
        result = get_transaction(
            self.session, "DEMO-TX-A", records=self.records, now=self.now,
        )

        self.assertIs(result, self.entry)
        self.assertEqual(result.record.amount, Decimal("0.10000000000000000000001"))
        self.assertEqual(result.record.transaction_date, datetime(2026, 6, 16, 12, 30, 45))
        self.assertEqual(result.record.process_date, date(2026, 6, 17))
        self.assertEqual(result.record.currency, "USD")
        self.assertIsNone(result.record.merchant_name)
        self.assertEqual(result.sources, self.sources)
        self.assertEqual(self.records, {"DEMO-TX-A": self.entry})

    def test_another_owner_and_missing_record_have_identical_denials(self):
        another_customer = replace(self.session, customer_id="DEMO-CUSTOMER-B")

        self.assert_denied(another_customer, "DEMO-TX-A")
        self.assert_denied(self.session, "DEMO-MISSING")

    def test_missing_or_fabricated_session_is_denied(self):
        fabricated = {
            "customer_id": "DEMO-CUSTOMER-A",
            "expires_at": self.session.expires_at,
            "permissions": self.session.permissions,
        }
        for session in (None, fabricated, "DEMO-CUSTOMER-A"):
            with self.subTest(session_type=type(session).__name__):
                self.assert_denied(session, "DEMO-TX-A")

    def test_expiry_is_rechecked_on_every_lookup_including_exact_expiry(self):
        before_expiry = self.session.expires_at - timedelta(microseconds=1)
        result = get_transaction(
            self.session, "DEMO-TX-A", records=self.records, now=before_expiry,
        )
        self.assertIs(result, self.entry)

        # The same session and record must stop working once the session expires.
        for instant in (self.session.expires_at, self.session.expires_at + timedelta(seconds=1)):
            with self.subTest(instant=instant):
                self.assert_denied(self.session, "DEMO-TX-A", now=instant)

    def test_missing_or_intake_only_permission_does_not_allow_reading(self):
        for permissions in (frozenset(), frozenset({Permission.CREATE_SIMULATED_INTAKE})):
            with self.subTest(permissions=permissions):
                self.assert_denied(replace(self.session, permissions=permissions), "DEMO-TX-A")

    def test_repository_key_must_match_the_stored_transaction_id(self):
        self.assert_denied(
            self.session,
            "DEMO-ALIAS",
            records={"DEMO-ALIAS": self.entry},
        )

    def test_malformed_entry_or_inner_record_uses_generic_denial(self):
        # Dataclass annotations do not enforce field types at runtime.
        malformed_entries = (
            None,
            {"record": self.entry.record, "sources": self.sources},
            SourcedTransaction(None, self.sources),
            SourcedTransaction({"transaction_id": "DEMO-TX-A"}, self.sources),
        )
        for index, entry in enumerate(malformed_entries):
            with self.subTest(case=index):
                self.assert_denied(self.session, "DEMO-TX-A", records={"DEMO-TX-A": entry})

    def test_blank_or_nonstring_id_is_denied_before_repository_lookup(self):
        class MustNotRead(dict):
            def get(self, key, default=None):
                raise AssertionError("Invalid transaction ID reached repository lookup")

        for identifier in ("", "   ", "\t\n", None, 123, [], {}):
            with self.subTest(identifier=identifier):
                self.assert_denied(self.session, identifier, records=MustNotRead())


if __name__ == "__main__":
    unittest.main()
