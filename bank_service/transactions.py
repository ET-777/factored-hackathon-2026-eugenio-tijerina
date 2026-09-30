from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from bank_service.access import AccessDenied, Permission, TrustedSession, require_access
from bank_service.records import TransactionRecord


@dataclass(frozen=True)
class SourceReference:
    """Runtime provenance fields populated by a future validated cohort loader."""

    file: str
    row_number: int
    row_sha256: str


@dataclass(frozen=True)
class SourcedTransaction:
    """One validated transaction together with its immutable source references."""

    record: TransactionRecord
    sources: tuple[SourceReference, ...]


def get_transaction(
    session: TrustedSession | None,
    transaction_id: str,
    *,
    records: Mapping[str, SourcedTransaction],
    now: datetime,
) -> SourcedTransaction:
    """Return an authorized entry, or raise AccessDenied("Access denied")."""

    if not isinstance(transaction_id, str) or not transaction_id.strip():
        raise AccessDenied("Access denied")

    entry = records.get(transaction_id)
    if (not isinstance(entry, SourcedTransaction) or not isinstance(entry.record, TransactionRecord)):
        raise AccessDenied("Access denied")

    if entry.record.transaction_id != transaction_id:
        raise AccessDenied("Access denied")

    require_access(
        session=session,
        record_customer_id=entry.record.customer_id,
        permission=Permission.READ_TRANSACTION,
        now=now,
    )

    return entry
