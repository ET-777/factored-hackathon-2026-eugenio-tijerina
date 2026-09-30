"""Bounded bilingual rules baseline and conservative request slots.

This module proposes an intent; it never authorizes access, confirms a draft, or
writes a case. ``confidence`` is a binary rule-match indicator, not a calibrated
probability. No learned model is implemented here. Unknown wording requires the
UI to clarify or offer a human path. Slots require an explicit ISO date or native
currency code; no currency conversion or implied currency is performed.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Literal
import unicodedata

from bank_service.records import SUPPORTED_CURRENCIES
from bank_service.selection import TransactionFilters


MAX_REQUEST_CHARACTERS = 1000
Intent = Literal["inquiry", "dispute_intake", "human_request", "unsupported"]


class RoutingError(ValueError):
    """Fixed codes only; never include request text or extracted values."""


@dataclass(frozen=True)
class IntentProposal:
    intent: Intent
    confidence: float
    matched: bool


@dataclass(frozen=True)
class RequestSlots:
    transaction_id: str | None
    filters: TransactionFilters


def _checked_text(text: str, language: str) -> str:
    if not isinstance(language, str) or language not in ("es", "pt"):
        raise RoutingError("unsupported_language")
    if not isinstance(text, str) or not text.strip():
        raise RoutingError("invalid_request")
    if len(text) > MAX_REQUEST_CHARACTERS:
        raise RoutingError("request_too_long")
    return unicodedata.normalize("NFKC", text)


def _without_accents(text: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(character)
    )


_UNSUPPORTED_ACTIONS = (
    r"\b(?:transferir|transfiere|transfiera|transfere|transfira)\b",
    r"\b(?:enviar|envia|enviar|mande|mandar)\s+(?:el\s+|o\s+)?dinero\b",
    r"\b(?:enviar|envie|mandar|mande)\s+(?:o\s+)?dinheiro\b",
    r"\b(?:hacer|haz|realizar|realiza|fazer|faca)\s+(?:una?\s+|uma\s+)?transferencia\b",
    r"\b(?:bloquear|bloquea|bloquee|bloqueie|desbloquear|desbloquea|desbloqueie)\b",
    r"\b(?:reembolsar|reembolsa|reembolse|devuelve|devolver|devolva)\b",
    r"\b(?:quiero|quero|solicito|emitir|emite|procesar|procesa|processar)\s+(?:un\s+|um\s+|el\s+|o\s+)?reembolso\b",
    r"\b(?:solicitar|solicito|solicite|pedir|pido|quero|quiero|aprobar|aprova|aprobar|aprovar)\s+(?:un\s+|um\s+|el\s+|o\s+)?(?:prestamo|emprestimo)\b",
)
_HUMAN_REQUESTS = (
    r"\b(?:hablar|hablarme|conversar|falar|contactar|conectar|comunicarme)\b.{0,45}\b(?:persona|agente|humano|humana|pessoa|atendente|asesor|assessor)\b",
    r"\b(?:quiero|necesito|quero|preciso)\s+(?:una?\s+|um[ao]?\s+)?(?:persona|agente|humano|humana|pessoa|atendente|asesor|assessor)\b",
    r"\b(?:atencion|atendimento)\s+(?:humana?|personal)\b",
)
_DISPUTE_REQUESTS = (
    r"\b(?:no|nao)\s+(?:reconozco|reconheco)\b",
    r"\b(?:cargo|cobro|cobranca|debito|compra)\s+(?:no\s+reconocid[oa]|nao\s+reconhecid[oa]|indebid[oa]|duplicad[oa])\b",
    r"\b(?:disputar|disputa|contestar|contestacao|reclamar|reclamacion|reclamacao)\b",
    r"\b(?:abrir|crear|criar)\s+(?:un\s+|um\s+|una\s+|uma\s+)?(?:caso|reclamo|reclamacion|reclamacao)\b",
)
_INQUIRY_REQUESTS = (
    r"\b(?:transaccion|transacao|transaction|cargo|cobro|cobranca|compra|compras|pago|pagamento|movimiento|movimentacao|debito)\b",
    r"\b(?:estado|status|importe|monto|valor|fecha|data)\b.{0,40}\b(?:tarjeta|cartao|registro|operacion|operacao)\b",
    r"\b(?:buscar|busca|encontrar|localizar|consultar|ver)\b.{0,30}\b(?:importe|monto|valor|registro|operacion|operacao)\b",
    r"\b(?:USD|COP|ARS)\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b[A-Za-z0-9]+-TX-[A-Za-z0-9_-]+\b",
)
_NEGATED_ACTION = re.compile(
    r"\b(?:no|nao)\s+(?:(?:quiero|quero|deseo|desejo|necesito|preciso|voy a|vou)\s+)?"
    r"(?:disputar|contestar|reclamar|abrir|crear|criar|transferir|bloquear|reembolsar|hablar|falar)\b[^,;.!?]*"
)
_CONFIRMATION = re.compile(
    r"^(?:si|sim|yes|ok|okay|de acuerdo)[\s.!?]*$"
    r"|^(?:confirmo|confirmar|confirmado|acepto|aceitar)\b"
)


def route_intent(text: str, language: str) -> IntentProposal:
    """Propose one intent using fixed rules; explicit action consent is separate."""
    normalized = _without_accents(_checked_text(text, language)).casefold().strip()
    if _CONFIRMATION.search(normalized):
        return IntentProposal("unsupported", 0.0, False)
    normalized = _NEGATED_ACTION.sub(" ", normalized)
    for intent, patterns in (
        ("unsupported", _UNSUPPORTED_ACTIONS),
        ("human_request", _HUMAN_REQUESTS),
        ("dispute_intake", _DISPUTE_REQUESTS),
        ("inquiry", _INQUIRY_REQUESTS),
    ):
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns):
            return IntentProposal(intent, 1.0, True)
    return IntentProposal("unsupported", 0.0, False)


# Known explicit currencies beyond the source contract produce an error. This
# allowlist avoids treating every three-letter word in prose as a currency.
_CURRENCY_CODES = (
    "USD", "COP", "ARS", "MXN", "BRL", "EUR", "GBP", "PEN", "CLP", "UYU",
    "BOB", "PYG", "VES", "CRC", "GTQ", "HNL", "NIO", "DOP", "CAD", "JPY", "CHF",
)
_CURRENCY = "(?:" + "|".join(_CURRENCY_CODES) + ")"
_CURRENCY_PATTERN = re.compile(r"\b" + _CURRENCY + r"\b", re.IGNORECASE)
_VALUE = r"[+-]?(?:\d(?:[\d.,]*\d)?(?:\s+\d(?:[\d.,]*\d)?)*(?:[eE][+-]?\d+)?|s?NaN|Infinity|Inf)"
_AMOUNT_AFTER = re.compile(
    r"\b(?P<currency>" + _CURRENCY + r")\b\s+(?P<value>" + _VALUE + r")(?![\w-]|[.,](?=\d))",
    re.IGNORECASE,
)
_AMOUNT_BEFORE = re.compile(
    r"(?<![\w.,-])(?P<value>" + _VALUE + r")\s+(?P<currency>" + _CURRENCY + r")\b",
    re.IGNORECASE,
)
_DIRECT_ID = re.compile(
    r"(?<![A-Za-z0-9_-])(?:[A-Za-z0-9]+-TX-[A-Za-z0-9_-]+|TX[-_][A-Za-z0-9_-]+)(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
_EXPLICIT_ID = re.compile(
    r"\b(?:transaccion|transacao|transaction|tx|id)\s+(?:id\s*[:#]?\s*|[:#]\s*)?"
    r"([A-Za-z0-9][A-Za-z0-9_-]{2,63})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)


def _one_value(values: set, code: str):
    if len(values) > 1:
        raise RoutingError(code)
    return next(iter(values)) if values else None


def _parse_amount(value: str) -> Decimal:
    # Grouping is deliberately unsupported: 1,000 and 1.000 are ambiguous.
    if not re.fullmatch(r"[+-]?\d+(?:[.,]\d{1,2})?", value):
        raise RoutingError("invalid_amount")
    try:
        amount = Decimal(value.replace(",", "."))
    except InvalidOperation:
        raise RoutingError("invalid_amount") from None
    if not amount.is_finite():
        raise RoutingError("invalid_amount")
    return amount


def extract_slots(text: str, language: str) -> RequestSlots:
    """Extract exact optional slots, raising rather than guessing ambiguity."""
    checked = _checked_text(text, language)
    ascii_text = _without_accents(checked)
    identifiers = set()
    for match in _DIRECT_ID.finditer(ascii_text):
        token = match.group(0)
        if len(token) > 64:
            raise RoutingError("invalid_transaction_id")
        identifiers.add(token.upper() if token.upper().startswith("DEMO-TX-") else token)
    for match in _EXPLICIT_ID.finditer(ascii_text):
        token = match.group(1)
        # Labels, ordinary words, currency codes, dates and customer/product IDs
        # are not transaction identifiers. Authorization still checks stored IDs.
        if (
            not any(character.isdigit() for character in token)
            or not any(character.isalpha() for character in token)
            or token.upper().startswith(("CUSTOMER", "CUST-", "CLIENTE", "PRODUCT", "PROD-"))
        ):
            continue
        identifiers.add(token.upper() if token.upper().startswith("DEMO-TX-") else token)
    transaction_id = _one_value(identifiers, "ambiguous_transaction_id")

    dates = set()
    for match in re.finditer(r"(?<![\w-])\d{4}-\d{1,2}-\d{1,2}(?![\w-])", checked):
        raw = match.group(0)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise RoutingError("invalid_date")
        try:
            dates.add(date.fromisoformat(raw))
        except ValueError:
            raise RoutingError("invalid_date") from None
    transaction_date = _one_value(dates, "ambiguous_date")

    currencies = {match.group(0).upper() for match in _CURRENCY_PATTERN.finditer(checked)}
    if currencies - SUPPORTED_CURRENCIES:
        raise RoutingError("unsupported_currency")
    currency = _one_value(currencies, "ambiguous_currency")
    amounts = set()
    for pattern in (_AMOUNT_BEFORE, _AMOUNT_AFTER):
        for match in pattern.finditer(checked):
            amounts.add(_parse_amount(match.group("value")))
    amount = _one_value(amounts, "ambiguous_amount")
    return RequestSlots(transaction_id, TransactionFilters(transaction_date, amount, currency))
