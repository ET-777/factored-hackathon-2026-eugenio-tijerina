from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re


# Limit fractional seconds to Python datetime.
_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?"
)

SUPPORTED_CURRENCIES = frozenset({"USD", "COP", "ARS", "MXN"})
SUPPORTED_TRANSACTION_TYPES = frozenset(
    {"Deposit", "Withdrawal", "Transfer", "Purchase", "Payment", "Adjustment"}
)
SUPPORTED_TRANSACTION_STATUSES = frozenset({"Approved", "Declined", "Pending", "Reversed"})


class RecordValidationError(ValueError):
    """A record fails the data contract."""


def required_text(row: object, field: str) -> str:
    """Return a required, nonblank string with surrounding whitespace removed."""

    if not isinstance(row, Mapping):
        raise RecordValidationError(f"row must be a mapping, not {type(row).__name__}")

    value = row.get(field)

    if value is None or not isinstance(value, str):
        raise RecordValidationError(f"Field '{field}' is required and must be a string")

    value = value.strip()

    if not value:
        raise RecordValidationError(f"Field '{field}' is required and must be a nonblank string")
    else:
        return value


def required_decimal(row: object, field: str) -> Decimal:
    """Return a required decimal value."""

    value = required_text(row, field)

    try:
        value = Decimal(value)
    except InvalidOperation:
        raise RecordValidationError(f"Field '{field}' must be a valid decimal number")

    if value.is_nan() or value.is_infinite():
        raise RecordValidationError(f"Field '{field}' must be a valid decimal number")
    
    return value


def required_date(row: object, field: str) -> date:
    """Return a required calendar date"""

    value = required_text(row, field)

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise RecordValidationError(f"Field '{field}' must be a valid date in YYYY-MM-DD format")

    if parsed.isoformat() != value:
        raise RecordValidationError(f"Field '{field}' must be a valid date in YYYY-MM-DD format")

    return parsed


def required_timestamp(row: object, field: str) -> datetime:
    """Return a required timestamp"""

    value = required_text(row, field)

    if not _TIMESTAMP_PATTERN.fullmatch(value):
        raise RecordValidationError(f"Field '{field}' must be a valid timestamp in YYYY-MM-DDTHH:MM:SS[.ffffff][Z|±HH:MM] format")

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise RecordValidationError(f"Field '{field}' must be a valid timestamp in YYYY-MM-DDTHH:MM:SS[.ffffff][Z|±HH:MM] format")

    return parsed


@dataclass(frozen=True)
class TransactionRecord:
    """Represent a parsed transaction."""

    transaction_id: str
    customer_id: str
    product_id: str
    transaction_date: datetime
    process_date: date
    transaction_type: str
    amount: Decimal
    currency: str
    transaction_status: str
    merchant_name: str | None


def parse_transaction(row: object) -> TransactionRecord:
    """Parse source row and invalid fields check."""

    transaction_id = required_text(row, "transaction_id")
    customer_id = required_text(row, "customer_id")
    product_id = required_text(row, "product_id")
    transaction_date = required_timestamp(row, "transaction_date")
    process_date = required_date(row, "process_date")
    amount = required_decimal(row, "amount")
    transaction_type = required_text(row, "transaction_type")
    currency = required_text(row, "currency")
    transaction_status = required_text(row, "transaction_status")

    if transaction_type not in SUPPORTED_TRANSACTION_TYPES:
        raise RecordValidationError("Unsupported transaction_type")
    
    if currency not in SUPPORTED_CURRENCIES:
        raise RecordValidationError("Unsupported currency")

    if transaction_status not in SUPPORTED_TRANSACTION_STATUSES:
        raise RecordValidationError("Unsupported transaction_status")


    merchant_name = row.get("merchant_name")

    if isinstance(merchant_name, str):
        merchant_name = merchant_name.strip()
        if not merchant_name:
            merchant_name = None
    elif merchant_name is not None:
        raise RecordValidationError("Merchant name must be a string or absent")


    return TransactionRecord(
        transaction_id=transaction_id,
        customer_id=customer_id,
        product_id=product_id,
        transaction_date=transaction_date,
        process_date=process_date,
        transaction_type=transaction_type,
        amount=amount,
        currency=currency,
        transaction_status=transaction_status,
        merchant_name=merchant_name
    )


@dataclass(frozen=True)
class CustomerRecord:
    """Customer facts needed for record consistency checks."""

    customer_id: str
    registration_date: datetime


@dataclass(frozen=True)
class ProductRecord:
    """Product facts needed for record consistency checks."""

    product_id: str
    customer_id: str
    currency: str
    opening_date: date


def parse_customer(row: object) -> CustomerRecord:
    """Parse customer_id and registration_date"""

    customer_id = required_text(row, "customer_id")
    registration_date = required_timestamp(row, "registration_date")

    return CustomerRecord(customer_id=customer_id, registration_date=registration_date)


def parse_product(row: object) -> ProductRecord:
    """Parse product_id, customer_id, currency, and opening_date"""

    product_id = required_text(row, "product_id")
    customer_id = required_text(row, "customer_id")
    currency = required_text(row, "currency")
    opening_date = required_date(row, "opening_date")

    if currency not in SUPPORTED_CURRENCIES:
        raise RecordValidationError("Unsupported currency")

    return ProductRecord(
        product_id=product_id,
        customer_id=customer_id,
        currency=currency,
        opening_date=opening_date
    )


def validate_transaction_links(transaction: TransactionRecord, customer: CustomerRecord | None,product: ProductRecord | None,) -> None:
    """Check record links and calendar-date order; return None if successful."""

    if not isinstance(transaction, TransactionRecord):
        raise RecordValidationError("transaction must be a TransactionRecord")
    if not isinstance(customer, CustomerRecord):
        raise RecordValidationError("customer must be a CustomerRecord")
    if not isinstance(product, ProductRecord):
        raise RecordValidationError("product must be a ProductRecord")
    
    if transaction.customer_id != customer.customer_id:
        raise RecordValidationError("transaction.customer_id does not match customer.customer_id")
    if transaction.product_id != product.product_id:
        raise RecordValidationError("transaction.product_id does not match product.product_id")
    if product.customer_id != customer.customer_id:
        raise RecordValidationError("product.customer_id does not match customer.customer_id")
    if transaction.currency != product.currency:
        raise RecordValidationError("transaction.currency does not match product.currency")

    event_date = transaction.transaction_date.date()
    if event_date < product.opening_date:
        raise RecordValidationError("transaction date is before product opening date")
    if event_date < customer.registration_date.date():
        raise RecordValidationError("transaction date is before customer registration date")

    return None
