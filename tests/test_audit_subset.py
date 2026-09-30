"""Small checks for bounded ingestion and public aggregate privacy."""
import unittest
from unittest.mock import patch

from scripts.audit_subset import AuditError, MAX_BYTES, MAX_REQUESTS, Reader, parse_prefix, profile


class BoundedAuditTests(unittest.TestCase):
    def test_truncated_quoted_record_is_not_accepted(self):
        columns, rows, malformed = parse_prefix(b'id,text\n1,"complete\ntext"\n2,"cut\n')
        self.assertEqual(columns, ["id", "text"])
        self.assertEqual(rows, [{"id": "1", "text": "complete\ntext"}])
        self.assertEqual(malformed, 1)

    def test_row_cap_and_incomplete_transport_tail(self):
        _, rows, _ = parse_prefix(b"id,value\n1,first\n2,second\n3,incomplete", limit=1)
        self.assertEqual(rows, [{"id": "1", "value": "first"}])

    def test_arbitrary_category_text_is_withheld(self):
        result = profile("transactions", ["transaction_id", "currency"], [{"transaction_id": "toy", "currency": "PRIVATE ARBITRARY VALUE"}], 0)
        self.assertEqual(result["categories"]["currency"], {"[unrecognized value withheld]": 1})
        self.assertNotIn("PRIVATE ARBITRARY VALUE", str(result))

    def test_exhausted_request_budget_prevents_source_call(self):
        reader = Reader({"bucket": "unit-test", "region": "us-east-1", "access": "test-only", "secret": "test-only"}, {"request_count": MAX_REQUESTS, "response_bytes": 0})
        with patch.object(reader._opener, "open") as source:
            with self.assertRaisesRegex(AuditError, "request_budget_exhausted"):
                reader.get()
            source.assert_not_called()

    def test_exhausted_byte_budget_prevents_source_call(self):
        reader = Reader({"bucket": "unit-test", "region": "us-east-1", "access": "test-only", "secret": "test-only"}, {"request_count": 0, "response_bytes": MAX_BYTES})
        with patch.object(reader._opener, "open") as source:
            with self.assertRaisesRegex(AuditError, "byte_budget_exhausted"):
                reader.get(ranged=True)
            source.assert_not_called()


if __name__ == "__main__":
    unittest.main()
