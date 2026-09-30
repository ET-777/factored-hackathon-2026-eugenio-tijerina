"""Independently authored public demo records; never load organizer data here."""

from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json

from bank_service.access import Permission, TrustedSession
from bank_service.records import TransactionRecord
from bank_service.transactions import SourceReference, SourcedTransaction


DEMO_CUSTOMER = "DEMO-CUSTOMER-A"


def demo_records() -> dict[str, SourcedTransaction]:
    """Two same-owner matches and one foreign record for visible access checks."""
    records = {}
    for index, (customer, merchant) in enumerate((
        (DEMO_CUSTOMER, "Demo Mercado Sol"),
        (DEMO_CUSTOMER, "Demo Cafe Luna"),
        ("DEMO-CUSTOMER-B", "Demo Foreign Merchant"),
    ), start=1):
        record = TransactionRecord(
            transaction_id=f"DEMO-TX-{index:03d}", customer_id=customer,
            product_id=f"DEMO-PRODUCT-{customer[-1]}",
            transaction_date=datetime(2026, 6, 16, 12, index),
            process_date=date(2026, 6, 17), transaction_type="Purchase",
            amount=Decimal("25.50"), currency="USD", transaction_status="Approved",
            merchant_name=merchant,
        )
        # This hash identifies this authored fixture, not a source-dataset row.
        canonical = json.dumps(asdict(record), default=str, sort_keys=True)
        ref = SourceReference(
            "synthetic/demo_fixtures", index,
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
        records[record.transaction_id] = SourcedTransaction(record, (ref,))
    return records


def demo_session(now: datetime) -> TrustedSession:
    """Fixed server-owned demo identity; this is not production authentication."""
    return TrustedSession(
        customer_id=DEMO_CUSTOMER, expires_at=now + timedelta(minutes=20),
        permissions=frozenset({
            Permission.READ_TRANSACTION, Permission.CREATE_SIMULATED_INTAKE,
            Permission.CREATE_SIMULATED_HANDOFF,
        }),
    )
