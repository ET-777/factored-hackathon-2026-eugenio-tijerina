"""Security-relevant checks for the initial tool-layer boundary."""

import unittest
from datetime import datetime, timedelta, timezone

from bank_service.access import AccessDenied, Permission, TrustedSession, require_access


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
        self.session = TrustedSession(
            "DEMO-CUSTOMER-A", self.now + timedelta(minutes=10),
            frozenset({Permission.READ_TRANSACTION}),
        )

    def test_owner_with_explicit_read_permission_is_allowed(self):
        require_access(self.session, "DEMO-CUSTOMER-A", Permission.READ_TRANSACTION, now=self.now)

    def test_another_customer_is_denied_without_identifier_in_error(self):
        with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
            require_access(self.session, "DEMO-CUSTOMER-B", Permission.READ_TRANSACTION, now=self.now)

    def test_read_permission_does_not_authorize_write(self):
        with self.assertRaises(AccessDenied):
            require_access(self.session, "DEMO-CUSTOMER-A", Permission.CREATE_SIMULATED_INTAKE, now=self.now)

    def test_missing_or_untrusted_session_is_denied(self):
        for value in (None, {"customer_id": "DEMO-CUSTOMER-A"}, "DEMO-CUSTOMER-A"):
            with self.subTest(value=value), self.assertRaises(AccessDenied):
                require_access(value, "DEMO-CUSTOMER-A", Permission.READ_TRANSACTION, now=self.now)

    def test_exact_expiry_and_later_are_denied(self):
        for instant in (self.session.expires_at, self.session.expires_at + timedelta(seconds=1)):
            with self.subTest(instant=instant), self.assertRaises(AccessDenied):
                require_access(self.session, "DEMO-CUSTOMER-A", Permission.READ_TRANSACTION, now=instant)

    def test_naive_or_invalid_time_is_denied(self):
        for instant in (self.now.replace(tzinfo=None), None, "2026-09-26"):
            with self.subTest(instant=instant), self.assertRaises(AccessDenied):
                require_access(self.session, "DEMO-CUSTOMER-A", Permission.READ_TRANSACTION, now=instant)

    def test_blank_owners_are_denied(self):
        for owner in ("", " ", None):
            malformed = TrustedSession(owner, self.session.expires_at, self.session.permissions)
            with self.subTest(owner=owner), self.assertRaises(AccessDenied):
                require_access(malformed, owner, Permission.READ_TRANSACTION, now=self.now)

    def test_untyped_or_missing_permissions_are_denied(self):
        for grants in (frozenset(), frozenset({"transaction:read"}), {Permission.READ_TRANSACTION}):
            malformed = TrustedSession("DEMO-CUSTOMER-A", self.session.expires_at, grants)
            with self.subTest(grants=grants), self.assertRaises(AccessDenied):
                require_access(malformed, "DEMO-CUSTOMER-A", Permission.READ_TRANSACTION, now=self.now)


if __name__ == "__main__":
    unittest.main()
