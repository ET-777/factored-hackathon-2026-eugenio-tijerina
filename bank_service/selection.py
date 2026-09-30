from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from bank_service.access import AccessDenied, Permission, TrustedSession, require_access
from bank_service.records import SUPPORTED_CURRENCIES, TransactionRecord
from bank_service.transactions import SourcedTransaction, get_transaction


# Search the small validated repository, never the original CSV dataset.
MAX_SEARCH_RECORDS = 200

# Draft wording; independent Portuguese language review remains pending.
CLARIFICATIONS = {
    "es": {
        "needs_filters": "Indica la fecha de la transacción o el importe y su moneda para buscar en los datos disponibles.",
        "no_match": "No encontré coincidencias en tus datos disponibles. Revisa la fecha, el importe y la moneda.",
        "ambiguous": "Hay varias coincidencias en tus datos disponibles. Elige una transacción o precisa la fecha, el importe y la moneda.",
    },
    "pt": {
        "needs_filters": "Informe a data da transação ou o valor e a moeda para pesquisar nos dados disponíveis.",
        "no_match": "Não encontrei correspondências nos seus dados disponíveis. Confira a data, o valor e a moeda.",
        "ambiguous": "Há várias correspondências nos seus dados disponíveis. Escolha uma transação ou informe mais detalhes sobre a data, o valor e a moeda.",
    },
}


class SelectionError(ValueError):
    """Fixed error codes only; never include customer IDs, filters, or record data."""


@dataclass(frozen=True)
class TransactionFilters:
    """Optional exact filters; amount requires currency, currency alone is allowed."""

    transaction_date: date | None = None
    amount: Decimal | None = None
    currency: str | None = None


@dataclass(frozen=True)
class SelectionResult:
    """Only IDs from authorized matches; clarification text contains no record data."""

    language: str
    status: Literal["needs_filters", "no_match", "selected", "ambiguous"]
    candidate_ids: tuple[str, ...]
    clarification: str | None


def _validate_filters(filters: TransactionFilters) -> None:
    """Reject malformed values; an entirely empty filter object is valid."""

    if not isinstance(filters, TransactionFilters):
        raise SelectionError("invalid_filters")
    # datetime inherits from date; this filter deliberately accepts date only.
    if filters.transaction_date is not None and type(filters.transaction_date) is not date:
        raise SelectionError("invalid_filters")

    # Check absence explicitly so zero-valued amounts still undergo validation.
    if filters.amount is not None:
        if not isinstance(filters.amount, Decimal) or not filters.amount.is_finite():
            raise SelectionError("invalid_filters")
        if filters.currency is None:
            raise SelectionError("invalid_filters")

    if filters.currency is not None and (
        not isinstance(filters.currency, str) or filters.currency not in SUPPORTED_CURRENCIES
    ):
        raise SelectionError("invalid_filters")

    return None


def find_transactions(
    session: TrustedSession | None,
    filters: TransactionFilters,
    *,
    records: Mapping[str, SourcedTransaction],
    now: datetime,
) -> tuple[SourcedTransaction, ...]:
    """Find all authorized exact matches, sorted by transaction ID."""

    if not isinstance(session, TrustedSession):
        raise AccessDenied("Access denied")

    # This checks session validity and the read grant, even when no search occurs.
    # get_transaction still checks each candidate's actual stored owner below.
    require_access(session, session.customer_id, Permission.READ_TRANSACTION, now=now)

    _validate_filters(filters)
    if filters.amount is None and filters.currency is None and filters.transaction_date is None:
        return ()
    
    if not isinstance(records, Mapping):
        raise SelectionError("invalid_repository")
    if len(records) > MAX_SEARCH_RECORDS:
        raise SelectionError("repository_limit_exceeded")

    matches = []
    for mapping_key, entry in records.items():
        if not isinstance(entry, SourcedTransaction) or not isinstance(entry.record, TransactionRecord):
            raise SelectionError("invalid_repository")
        if entry.record.customer_id != session.customer_id:
            continue

        # Keep owner filtering, authorization, and matching in the same loop.
        authorized = get_transaction(session, mapping_key, records=records, now=now)
        record = authorized.record
        if filters.transaction_date is not None and record.transaction_date.date() != filters.transaction_date:
            continue
        if filters.amount is not None and record.amount != filters.amount:
            continue
        if filters.currency is not None and record.currency != filters.currency:
            continue
        matches.append(authorized)

    # A later matching row changes a unique selection into an ambiguous result.
    return tuple(sorted(matches, key=lambda entry: entry.record.transaction_id))

def select_transaction(
    session: TrustedSession | None,
    filters: TransactionFilters,
    *,
    records: Mapping[str, SourcedTransaction],
    language: str,
    now: datetime,
) -> SelectionResult:
    """Return one of four selection states without choosing arbitrarily."""

    matches = find_transactions(session, filters, records=records, now=now)

    if not isinstance(language, str) or language not in ("es", "pt"):
        raise SelectionError("unsupported_language")

    candidate_ids = tuple(match.record.transaction_id for match in matches)
    if filters.transaction_date is None and filters.amount is None and filters.currency is None:
        status = "needs_filters"
    elif len(matches) == 0:
        status = "no_match"
    elif len(matches) == 1:
        status = "selected"
    else:
        status = "ambiguous"

    clarification = None if status == "selected" else CLARIFICATIONS[language][status]
    return SelectionResult(
        language=language, status=status, candidate_ids=candidate_ids, clarification=clarification,
    )
