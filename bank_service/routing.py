"""Bounded bilingual rules baseline and conservative request slots.

This module proposes an intent; it never authorizes access, confirms a draft, or
writes a case. ``confidence`` is a binary rule-match indicator, not a calibrated
probability. No learned model is implemented here. Unknown wording requires the
UI to clarify or offer a human path. Dates require an explicit ISO calendar date.
The demo explicitly interprets the word dollar/dólar/dólares as USD and marks that
interpretation for display. The symbol $ and the word pesos remain ambiguous.
Bare amounts are held separately until a currency is supplied. No conversion or
inference from the customer's location is performed. The source record contract
continues to allow USD, COP and ARS only.
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
    amount_without_currency: Decimal | None = None
    needs_currency: bool = False
    used_dollar_alias: bool = False
    currency_ambiguous: bool = False


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
    r"\b(?:transaccion(?:es)?|transacao|transacoes|transactions?|cargos?|cobros?|cobrancas?|compras?|pagos?|pagamentos?|movimientos?|movimentacao|movimentacoes|debitos?|transferencias?|depositos?|retiros?|saques?)\b",
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
    # Slot-bearing fragments are inquiry proposals. The caller decides whether
    # they continue an active search or need initial clarification. Unsupported
    # currencies still reach the slot validator instead of a generic refusal.
    if (
        _CURRENCY_PATTERN.search(normalized)
        or _DOLLAR_ALIAS.search(normalized)
        or _PESO_ALIAS.search(normalized)
        or _BARE_AMOUNT.fullmatch(normalized)
        or _SYMBOL_AMOUNT.search(normalized)
        or is_search_followup(text, language)
    ):
        return IntentProposal("inquiry", 1.0, True)
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
_DOLLAR_ALIAS = re.compile(r"\b(?:dolar(?:es)?|dollars?)\b", re.IGNORECASE)
_PESO_ALIAS = re.compile(r"\bpesos?\b", re.IGNORECASE)
_BARE_AMOUNT = re.compile(r"\s*(?:\$\s*)?(?P<value>" + _VALUE + r")[.!?]?\s*", re.IGNORECASE)
_SYMBOL_AMOUNT = re.compile(r"\$\s*(?P<value>" + _VALUE + r")(?![\w-]|[.,](?=\d))", re.IGNORECASE)
_PESO_AMOUNT_BEFORE = re.compile(
    r"(?<![\w.,-])(?P<value>" + _VALUE + r")\s+pesos?\b", re.IGNORECASE,
)
_PESO_AMOUNT_AFTER = re.compile(
    r"\bpesos?\s+(?P<value>" + _VALUE + r")(?![\w-]|[.,](?=\d))", re.IGNORECASE,
)
_NAMED_AMOUNT = re.compile(
    r"\b(?:importe|monto|valor)\s*[:=]?\s*(?P<value>" + _VALUE + r")(?![\w-]|[.,](?=\d))",
    re.IGNORECASE,
)
_SLOT_REPLY_PREFIX = re.compile(
    r"^(?:de|del|en|em|son|sao|es|e|fue|foi|por)\s+", re.IGNORECASE,
)
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

    used_dollar_alias = bool(_DOLLAR_ALIAS.search(ascii_text))
    money_text = _DOLLAR_ALIAS.sub("USD", ascii_text)
    has_peso_alias = bool(_PESO_ALIAS.search(ascii_text))
    currencies = {match.group(0).upper() for match in _CURRENCY_PATTERN.finditer(money_text)}
    if currencies - SUPPORTED_CURRENCIES:
        raise RoutingError("unsupported_currency")
    currency = _one_value(currencies, "ambiguous_currency")
    if has_peso_alias and currency is not None and currency not in ("COP", "ARS"):
        raise RoutingError("ambiguous_currency")
    amounts = set()
    for pattern in (_AMOUNT_BEFORE, _AMOUNT_AFTER):
        for match in pattern.finditer(money_text):
            amounts.add(_parse_amount(match.group("value")))
    # Keep amounts lacking a denomination out of TransactionFilters. The UI may
    # collect the next currency reply, but it cannot authorize a search yet.
    unpaired_amounts = set()
    # Ordinary short replies such as "son 25"/"são 25" remain an amount
    # fragment. Only a full numeric match qualifies; new sentences do not.
    bare = _BARE_AMOUNT.fullmatch(_SLOT_REPLY_PREFIX.sub("", money_text.strip()))
    if bare:
        unpaired_amounts.add(_parse_amount(bare.group("value")))
    for pattern in (_SYMBOL_AMOUNT, _PESO_AMOUNT_BEFORE, _PESO_AMOUNT_AFTER, _NAMED_AMOUNT):
        for match in pattern.finditer(money_text):
            unpaired_amounts.add(_parse_amount(match.group("value")))
    all_amounts = amounts | unpaired_amounts
    _one_value(all_amounts, "ambiguous_amount")
    amount = _one_value(amounts, "ambiguous_amount")
    amount_without_currency = None
    if currency is None:
        amount_without_currency = _one_value(unpaired_amounts, "ambiguous_amount")
    elif amount is None:
        # An explicit code disambiguates a pesos/$/named-amount phrase without
        # changing denominations. There is exactly one code and one amount.
        amount = _one_value(unpaired_amounts, "ambiguous_amount")
    needs_currency = currency is None and (
        amount_without_currency is not None or has_peso_alias or "$" in money_text
    )
    return RequestSlots(
        transaction_id, TransactionFilters(transaction_date, amount, currency),
        amount_without_currency, needs_currency, used_dollar_alias,
        currency is None and (has_peso_alias or "$" in money_text),
    )


def refers_to_selected_transaction(text: str, language: str) -> bool:
    """Recognize an explicit singular reference; the caller owns actual state.

    This flag neither chooses a record nor overrides an explicit identifier or
    new search filters. It is only useful while a server-owned selection exists.
    """
    normalized = _without_accents(_checked_text(text, language)).casefold()
    return bool(re.search(
        r"\b(?:esta|este|esa|ese|essa|esse|aquela|aquele)\s+"
        r"(?:compra|cargo|cobro|transaccion|transacao|pago|pagamento|debito)\b",
        normalized,
    ))


def is_search_followup(text: str, language: str) -> bool:
    """Recognize one slot-only reply for an unfinished server-owned search.

    This predicate does not validate the value, preserve an intent, or read any
    conversation state. The caller uses it only with an active unfinished search
    and still calls extract_slots(), permission checks and record selection.
    Full matching deliberately excludes new requests and typed consent.
    """
    normalized = _without_accents(_checked_text(text, language)).casefold().strip()
    normalized = _SLOT_REPLY_PREFIX.sub("", normalized)
    if _CONFIRMATION.search(normalized):
        return False
    # Permit ordinary terminal punctuation without treating it as another slot.
    if normalized.endswith((".", "!", "?")):
        normalized = normalized[:-1].rstrip()
    if _DIRECT_ID.fullmatch(normalized):
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return True
    unit = "(?:" + _CURRENCY + r"|dolar(?:es)?|dollars?|pesos?)"
    if re.fullmatch(unit + r"|\$", normalized, re.IGNORECASE):
        return True
    # Malformed grouping can still be recognizably money. Slot validation will
    # reject it instead of silently losing the customer's active search intent.
    # Nonfinite and exponent spellings are recognizable amount attempts, but
    # _parse_amount rejects them. Preserve the unfinished search while asking
    # the customer to correct the amount instead of changing their intent.
    number = _VALUE
    return bool(re.fullmatch(
        r"(?:\$\s*" + number + r"|" + number + r"(?:\s+" + unit + r")?|"
        + unit + r"\s+" + number + r")",
        normalized, re.IGNORECASE,
    ))
