"""Grounded Spanish/Portuguese transaction answers.

Public entry point: answer_transaction. It must authorize through get_transaction
before rendering facts. The private formatter assumes a validated repository entry.
Return plain text: a future UI must display it as text, not execute HTML/Markdown.
Language labels are draft templates; independent Portuguese review is still pending.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json

from bank_service.access import TrustedSession
from bank_service.records import TransactionRecord
from bank_service.transactions import SourceReference, SourcedTransaction, get_transaction


LABELS = {
    "es": {
        "transaction_id": "Transacción",
        "amount": "Importe",
        "transaction_type": "Tipo registrado",
        "status": "Estado registrado",
        "transaction_date": "Fecha de la transacción",
        "process_date": "Fecha de proceso en la fuente",
        "merchant": "Comercio registrado",
        "unknown_merchant": "No disponible en el registro",
        "unknown_timezone": "zona horaria no indicada",
        "historical": "Datos de una instantánea histórica.",
    },
    "pt": {
        "transaction_id": "Transação",
        "amount": "Valor",
        "transaction_type": "Tipo registrado",
        "status": "Status registrado",
        "transaction_date": "Data da transação",
        "process_date": "Data de processamento na fonte",
        "merchant": "Estabelecimento registrado",
        "unknown_merchant": "Não informado no registro",
        "unknown_timezone": "fuso horário não informado",
        "historical": "Dados de um retrato histórico.",
    },
}

STATUS_LABELS = {
    "Approved": {"es": "Aprobada", "pt": "Aprovada"},
    "Declined": {"es": "Rechazada", "pt": "Recusada"},
    "Pending": {"es": "Pendiente", "pt": "Pendente"},
    "Reversed": {"es": "Revertida", "pt": "Revertida"},
}

# Notes address only the recorded status and information absent from this record.
# Approved records need no unrelated blanket reason/settlement/refund disclaimer.
STATUS_NOTES = {
    "Declined": {
        "es": "El registro no incluye el motivo del rechazo.",
        "pt": "O registro não informa o motivo da recusa.",
    },
    "Pending": {
        "es": "El registro no incluye un plazo de actualización de este estado.",
        "pt": "O registro não informa um prazo para atualização desse status.",
    },
    "Reversed": {
        "es": "El registro no confirma un reembolso.",
        "pt": "O registro não confirma um reembolso.",
    },
}

TYPE_LABELS = {
    "Deposit": {"es": "Depósito", "pt": "Depósito"},
    "Withdrawal": {"es": "Retiro", "pt": "Saque"},
    "Transfer": {"es": "Transferencia", "pt": "Transferência"},
    "Purchase": {"es": "Compra", "pt": "Compra"},
    "Payment": {"es": "Pago", "pt": "Pagamento"},
    "Adjustment": {"es": "Ajuste", "pt": "Ajuste"},
}


class ResponseFormatError(ValueError):
    """Fixed error codes only; never include record contents in error messages."""


@dataclass(frozen=True)
class TransactionAnswer:
    language: str
    text: str
    sources: tuple[SourceReference, ...]


def _quote_field(value: str) -> str:
    """Keep record text visibly quoted on one line, without interpreting it."""
    quoted = json.dumps(value, ensure_ascii=False)
    for separator in ("\u0085", "\u2028", "\u2029"):
        quoted = quoted.replace(separator, f"\\u{ord(separator):04x}")
    return quoted


def _format_transaction(entry: SourcedTransaction, language: str) -> TransactionAnswer:
    """Format an already authorized, validated record; perform no I/O or actions."""

    if not isinstance(language, str) or language not in ("es", "pt"):
        raise ResponseFormatError("unsupported_language")

    if not isinstance(entry, SourcedTransaction) or not isinstance(entry.record, TransactionRecord):
        raise ResponseFormatError("invalid_entry")

    if (not isinstance(entry.sources, tuple) or not entry.sources or not all(isinstance(ref, SourceReference) for ref in entry.sources)):
        raise ResponseFormatError("invalid_entry")

    labels = LABELS[language]
    record = entry.record

    if record.transaction_status not in STATUS_LABELS or record.transaction_type not in TYPE_LABELS:
        raise ResponseFormatError("unsupported_record_value")

    
    fact_values = {
        "amount": f"{record.amount} {record.currency}",
        "transaction_date": record.transaction_date.isoformat() + (f" ({labels['unknown_timezone']})" if record.transaction_date.utcoffset() is None else ""),
        "process_date": record.process_date.isoformat(),
        "merchant": (labels["unknown_merchant"] if record.merchant_name is None else _quote_field(record.merchant_name)),
        "transaction_id": _quote_field(record.transaction_id),
        "status": f"{STATUS_LABELS[record.transaction_status][language]} ({record.transaction_status})",
        "type": f"{TYPE_LABELS[record.transaction_type][language]} ({record.transaction_type})",
    }

    lines = [
        f"{labels['transaction_id']}: {fact_values['transaction_id']}",
        f"{labels['amount']}: {fact_values['amount']}",
        f"{labels['transaction_type']}: {fact_values['type']}",
        f"{labels['status']}: {fact_values['status']}",
        f"{labels['transaction_date']}: {fact_values['transaction_date']}",
        f"{labels['process_date']}: {fact_values['process_date']}",
        f"{labels['merchant']}: {fact_values['merchant']}",
        labels["historical"],
    ]
    status_note = STATUS_NOTES.get(record.transaction_status)
    if status_note is not None:
        lines.append(status_note[language])

    return TransactionAnswer(language=language, text="\n".join(lines), sources=entry.sources)


def answer_transaction(
    session: TrustedSession | None,
    transaction_id: str,
    *,
    records: Mapping[str, SourcedTransaction],
    language: str,
    now: datetime,
) -> TransactionAnswer:
    """Authorize the requested record on every call, then format its facts."""

    entry = get_transaction(session, transaction_id, records=records, now=now)

    return _format_transaction(entry, language)
