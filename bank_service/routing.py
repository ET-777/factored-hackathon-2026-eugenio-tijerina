"""Bounded bilingual rules baseline and conservative request slots.

This module proposes an intent; it never authorizes access, confirms a draft, or
writes a case. ``confidence`` is a binary rule-match indicator, not a calibrated
probability. No learned model is implemented here. Unknown wording requires the
UI to clarify or offer a human path. Dates accept ISO, day-first numeric dates,
and bounded Spanish/Portuguese month names. An omitted year uses a trusted
reference date and is marked for display. The word dollar/dólar/dólares means USD,
with that interpretation marked for display. The symbol $ and the word pesos remain ambiguous.
Bare amounts are held separately until a currency is supplied. No conversion or
inference from the customer's location is performed. The prototype record
contract allows USD, COP, ARS and MXN only. "Pesos" requires an explicit code
because it can refer to MXN, COP or ARS.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Literal
import unicodedata

from bank_service.records import SUPPORTED_CURRENCIES
from bank_service.request_dates import DateParsingError, extract_request_date, is_date_reply, mask_request_dates
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
    assumed_date_year: bool = False


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
    # Requests to execute new transactions/payments differ from reading an
    # existing record. Past forms such as hice/realicé/fiz/realizei/pagué/paguei
    # are deliberately absent, so questions about completed payments still work.
    r"\b(?:hacer|haz|haga|hagas|realizar|realiza|ejecutar|ejecuta|efectuar|efectua|procesar|procesa|fazer|faca|realize|executar|execute|efetuar|efetue|processar|processe)\s+(?:(?:un|una|el|la|mi|otro|otra|nuevo|nueva|um|uma|o|a|meu|minha|este|esta|novo|nova)\s+){0,2}(?:transaccion|transacao|pago|pagamento)\b",
    r"\b(?:quiero|necesito|deseo|puedes|podrias|quero|preciso|desejo|pode|poderia|voy a|vou)\s+(?:que\s+(?:voce\s+)?)?(?:pagar|pagues|pague)\b",
    r"^(?:pagar|paga)\b",
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
    r"\b(?:USD|COP|ARS|MXN)\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b[A-Za-z0-9]+-TX-[A-Za-z0-9_-]+\b",
)
_NEGATED_ACTION = re.compile(
    r"\b(?:no|nao)\s+(?:(?:quiero|quero|deseo|desejo|necesito|preciso|voy a|vou)\s+)?"
    r"(?:disputar|contestar|reclamar|abrir|crear|criar|transferir|bloquear|reembolsar|hablar|falar|hacer|hagas|realizar|realices|ejecutar|ejecutes|efectuar|procesar|pagar|pagues|fazer|faca|realize|executar|execute|efetuar|processar|pague)\b[^,;.!?]*"
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


def extract_slots(text: str, language: str, *, reference_date: date | None = None) -> RequestSlots:
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

    try:
        interpreted = extract_request_date(
            checked, language, reference_date=date.today() if reference_date is None else reference_date)
    except DateParsingError as error:
        raise RoutingError(str(error)) from None
    transaction_date = interpreted.value

    used_dollar_alias = bool(_DOLLAR_ALIAS.search(ascii_text))
    # A date's day/year cannot become a monetary amount merely because the
    # customer adds a currency code after it. Mask only recognized date spans.
    money_text = _DOLLAR_ALIAS.sub("USD", mask_request_dates(ascii_text, language))
    has_peso_alias = bool(_PESO_ALIAS.search(ascii_text))
    currencies = {match.group(0).upper() for match in _CURRENCY_PATTERN.finditer(money_text)}
    if currencies - SUPPORTED_CURRENCIES:
        raise RoutingError("unsupported_currency")
    currency = _one_value(currencies, "ambiguous_currency")
    if has_peso_alias and currency is not None and currency not in ("MXN", "COP", "ARS"):
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
        interpreted.assumed_year,
    )


def refers_to_selected_transaction(text: str, language: str) -> bool:
    """Recognize an explicit singular reference; the caller owns actual state.

    This flag neither chooses a record nor overrides an explicit identifier or
    new search filters. It is only useful while a server-owned selection exists.
    """
    normalized = _without_accents(_checked_text(text, language)).casefold()
    noun = (
        r"(?:compra|cargo|cobro|transaccion|transacao|pago|pagamento|debito|"
        r"operacion|operacao|movimiento|movimento|movimentacao|lancamento)"
    )
    # A request for another/new record is not a reference to the selection, even
    # when the customer mentions the selected record as a comparison.
    new_noun = (
        r"(?:compras?|cargos?|cobros?|transaccion(?:es)?|transacao|transacoes|pagos?|"
        r"pagamentos?|debitos?|operacion(?:es)?|operacao|operacoes|movimientos?|"
        r"movimentos?|movimentacao|movimentacoes|lancamentos?)"
    )
    if re.search(r"\b(?:otr[oa]s?|outr[oa]s?|nuev[oa]s?|nov[oa]s?)\s+" + new_noun + r"\b", normalized):
        return False
    return bool(re.search(
        r"\b(?:esta|este|esa|ese|aquella|aquel|essa|esse|aquela|aquele|"
        r"desta|deste|dessa|desse|daquela|daquele|nesta|neste|nessa|nesse|naquela|naquele)\s+"
        + noun + r"\b|"
        r"\b(?:el|la|del|o|a|do|da|no|na)\s+" + noun
        + r"\s+(?:seleccionad[oa]|selecionad[oa]|elegid[oa]|escolhid[oa])\b",
        normalized,
    ))


def is_greeting(text: str, language: str) -> bool:
    """Recognize a complete greeting, retaining the selected ES/PT response.

    Common standalone English greetings are courtesy aliases only, not English
    business-language support. A greeting mixed with a request is excluded.
    """
    normalized = _without_accents(_checked_text(text, language)).casefold().strip(" \t\r\n.!¡?¿")
    pattern = (r"(?:hola|buenas|buen dia|buenos dias|buenas tardes|buenas noches)"
               if language == "es" else r"(?:ola|oi|bom dia|boa tarde|boa noite)")
    return re.fullmatch(r"(?:" + pattern + r"|hello|hi|hey)", normalized) is not None


def declines_handoff_preparation(text: str, language: str) -> bool:
    """Recognize an explicit refusal to prepare/save a support request."""
    normalized = _without_accents(_checked_text(text, language)).casefold()
    # A request for a person is not permission to prepare a ticket when another
    # clause explicitly refuses preparation. A failed past attempt ("no pude
    # crear...") does not match this bounded refusal grammar.
    declined_preparation = (
        r"\b(?:no|nao|nunca|sin|sem)\s+"
        r"(?:(?:quiero|quero|necesito|preciso|deseo|desejo|permito|autorizo|solicito)\s+)?"
        r"(?:(?:que|me|voce|se|realmente|mesmo|un|una|um|uma|ningun|ninguna|nenhum|nenhuma)\s+){0,4}"
        r"(?:preparar|prepara|prepare|prepares|crear|crea|cree|crees|criar|crie|abrir|abra|abras|"
        r"guardar|guarda|guarde|guardes|salvar|salve|enviar|envia|envie|envies|"
        r"ticket|caso|solicitud|solicitacao|pedido|resumen|resumo|borrador|rascunho)\b"
    )
    return re.search(declined_preparation, normalized) is not None


def is_explicit_human_request(text: str, language: str) -> bool:
    """Require positive human-request wording, never just a model label.

    This bounded check establishes only the request to prepare a human summary;
    it never grants access, confirms storage or verifies bank case history.
    Complete positive request clauses are required; narrative mentions and
    unclear negation need clarification. Existing unsupported-action priority
    still applies across the whole message.
    """
    normalized = _without_accents(_checked_text(text, language)).casefold()
    if declines_handoff_preparation(text, language):
        return False
    proposal = route_intent(normalized, language)
    if proposal.intent == "unsupported" and proposal.matched:
        return False
    target = (
        r"(?:(?:un|una|um|uma|el|la|o|a)\s+)?"
        r"(?:persona|pessoa|agente|atendente|humano|humana|asesor|assessor)"
        r"(?:\s+(?:real|humano|humana))?"
    )
    prefix = (
        r"(?:quiero|quisiera|necesito|deseo|me gustaria|puedo|puedes|podrias|"
        r"quero|queria|preciso|desejo|gostaria de|posso|pode|poderia)"
    )
    contact = (
        r"(?:hablar|hablarme|conversar|falar|contactar|conectar|comunicarme|"
        r"conectame|comunicame|pasame)\s+(?:con|com|a)\s+" + target
    )
    request = (
        r"(?:por\s+favor\s+)?(?:"
        + r"(?:" + prefix + r"\s+)?(?:por\s+favor\s+)?" + contact
        + r"|(?:" + prefix + r")\s+(?:de\s+)?" + target
        + r"|atencion\s+humana|atendimento\s+human[oa])"
        + r"(?:\s+(?:sobre|por|acerca de|a respeito de)\s+[^,;.!?]+)?"
        + r"(?:\s+por\s+favor)?"
    )
    for clause in re.split(r"[,;.!?\n]+", normalized):
        clause = clause.strip(" \t\r\n¡¿")
        # A negative customer problem after "because" is distinct from a
        # negated request for a person. The whole-message refusal and action
        # checks above still apply before this positive request clause.
        human_clause = re.split(
            r"\s+(?:porque|sobre|acerca de|a respeito de|para)\s+", clause, maxsplit=1)[0]
        if re.search(r"\b(?:no|nao|nunca|jamas|jamais|ni|nem|sin|sem)\b", human_clause):
            continue
        if re.fullmatch(request, human_clause):
            return True
    return False


def human_request_purpose(text: str, language: str) -> str | None:
    """Return an inline, literal customer purpose; never a model summary.

    This helper is used only after positive human-request wording is verified.
    A reason introduced after that request is retained without interpreting it
    as an instruction to execute a banking action. Mixed complaint clauses may
    retain the full informative request rather than invent a rewritten issue.
    """
    checked = _checked_text(text, language).strip()
    if not is_explicit_human_request(checked, language):
        return None
    for connector in re.finditer(
        r"\s+(?:porque|sobre|acerca de|a respeito de|por|para)\s+", checked, re.IGNORECASE):
        prefix = checked[:connector.start()].strip()
        if is_explicit_human_request(prefix, language):
            purpose = checked[connector.end():].strip()
            normalized = _without_accents(purpose).casefold().strip(" .!?¡¿")
            if normalized not in ("", "favor", "si", "sim", "ayuda", "ajuda", "algo",
                                  "gracias", "muchas gracias", "obrigado", "obrigada", "thanks"):
                return purpose
    clauses = [part.strip() for part in re.split(r"[,;\n]+", checked) if part.strip()]
    if any(not is_explicit_human_request(part, language)
           and not is_greeting(part, language)
           and _without_accents(part).casefold().strip(" .!?¡¿") not in (
               "por favor", "si", "sim", "gracias", "muchas gracias", "obrigado", "obrigada", "thanks")
           for part in clauses):
        return checked
    return None


def is_explicit_inquiry(text: str, language: str) -> bool:
    """Recognize a complete, plain read/search request before model routing.

    A read verb and transaction noun are both required. The whole-message
    grammar deliberately excludes unknown tails, negation, support cases,
    consent and mixed action requests. Existing higher-priority baseline intents
    must agree that this is an inquiry. This flag never selects a record or
    supplies missing search details, permission or action consent.
    """
    normalized = _without_accents(_checked_text(text, language)).casefold().strip()
    if route_intent(text, language).intent != "inquiry":
        return False
    if language == "es":
        greeting = r"(?:hola|buenas|buen dia|buenos dias|buenas tardes|buenas noches)"
        prefix = (
            r"(?:quiero|quisiera|necesito|deseo|me gustaria|puedo|puedes|podrias|"
            r"ayudame a|me ayudas a|puedes ayudarme a|podrias ayudarme a)"
        )
        verb = r"(?:ver|consultar|buscar|busca|busco|encontrar|localizar|mostrar|mostrarme|muestra|muestrame|ensena|ensename)"
        article = r"(?:un|una|el|la|los|las|mi|mis|este|esta|estos|estas|ese|esa|esos|esas)"
        noun = r"(?:pagos?|cargos?|cobros?|compras?|transaccion(?:es)?|movimientos?|operacion(?:es)?|debitos?)"
        detail = r"(?:los\s+)?(?:datos|detalles)\s+(?:de|del)\s+"
    else:
        greeting = r"(?:ola|oi|bom dia|boa tarde|boa noite)"
        prefix = (
            r"(?:quero|queria|preciso|desejo|gostaria de|posso|pode|poderia|"
            r"me ajude a|pode me ajudar a|poderia me ajudar a)"
        )
        verb = r"(?:ver|consultar|consulte|buscar|busque|encontrar|localizar|conferir|confira|verificar|mostrar|mostre)"
        article = r"(?:um|uma|o|a|os|as|meu|meus|minha|minhas|este|esta|estes|estas|esse|essa|esses|essas|deste|desta|desse|dessa)"
        noun = r"(?:pagamentos?|compras?|cobrancas?|transacao|transacoes|debitos?|movimentos?|movimentacao|movimentacoes|operacao|operacoes|lancamentos?)"
        detail = r"(?:os\s+)?(?:dados|detalhes)\s+(?:(?:de|do|da)\s+)?"
    pattern = (
        r"[\s¡!¿?]*" + r"(?:" + greeting + r"\s*[,!:]?\s+)?"
        + r"(?:por\s+favor\s*[,!:]?\s+)?"
        + r"(?:" + prefix + r"\s+)?"
        + r"(?:por\s+favor\s+)?" + verb + r"\s+"
        + r"(?:" + detail + r")?"
        + r"(?:" + article + r"\s+)?" + noun
        + r"(?:\s*[,!:]?\s+por\s+favor)?[\s.!?¡¿]*"
    )
    return re.fullmatch(pattern, normalized) is not None


def is_case_continuation(text: str, language: str) -> bool:
    """Recognize a request about a customer-claimed existing support case.

    This predicate never verifies that a case exists or retrieves its status.
    It requires a support-case reference and a continuation/status request;
    explicit requests to open a new case and negated follow-up requests are
    excluded. The caller must explain the unavailable history and obtain any
    separate consent needed to prepare a human-review packet.
    """
    normalized = _without_accents(_checked_text(text, language)).casefold()
    noun = (
        r"(?:caso|reclamo|reclamacion|queja|ticket|solicitud\s+de\s+revision)"
        if language == "es" else
        r"(?:caso|reclamacao|queixa|chamado|protocolo|pedido\s+de\s+revisao)"
    )
    case = r"\b" + noun + r"\b"
    if not re.search(case, normalized):
        return False
    no_existing_case = (
        r"\b(?:no|nao)\s+(?:tengo|tenho|hay|ha|existe|abri|"
        r"he\s+abierto|registrei|presente|envie|mandei)\b"
    )
    if re.search(
        no_existing_case + r"[^.;!?]{0,55}" + case + r"|"
        + case + r"[^.;!?]{0,55}" + no_existing_case,
        normalized,
    ):
        return False
    # Infinitives distinguish a requested new case from a past action such as
    # "presenté"/"registré", whose accents disappear during normalization.
    if re.search(
        r"\b(?:abrir|crear|criar|registrar|iniciar|presentar)\b"
        r"[^.;!?]{0,55}" + case,
        _NEGATED_ACTION.sub(" ", normalized),
    ):
        return False
    resume = (
        r"(?:retomar|retoma|retome|retomemos|continuar|continua|continue|"
        r"continuemos|reanudar|reanuda|proseguir|prosseguir|"
        r"dar\s+seguimiento|hacer\s+seguimiento|seguir\s+con|"
        r"acompanhar|acompanhe|dar\s+continuidade)"
    )
    followup = (
        r"(?:" + resume + r"|consultar|verificar|revisar|saber|conocer|"
        r"acompanhar|checar|conferir)"
    )
    if re.search(
        r"\b(?:no|nao)\s+(?:(?:quiero|quero|necesito|preciso|deseo|desejo)\s+)?"
        + followup + r"\b[^.;!?]{0,55}" + case,
        normalized,
    ):
        return False
    # Resuming/following up an explicitly named case already implies a prior
    # customer interaction. A generic question merely mentioning a case does not.
    if re.search(r"\b" + resume + r"\b[^.;!?]{0,90}" + case, normalized):
        return True
    owned_case = bool(re.search(
        r"\b(?:mi|mis|nuestro|nuestra|meu|minha|nosso|nossa)\s+"
        r"(?:(?:primer|primera|ultimo|ultima|anterior|primeiro|primeira)\s+)?"
        + case,
        normalized,
    ))
    prior = (
        r"\b(?:abri|abrimos|envie|enviamos|presente|presentamos|mande|mandei|"
        r"registrei|registramos|iniciei|iniciamos|abiert[oa]|abert[oa]|"
        r"registrad[oa]|presentad[oa]|enviad[oa]|anterior|previ[oa]|"
        r"existente|pendiente|pendente)\b|\b(?:ya|ja)\s+(?:tengo|tenho)\b"
    )
    existing_case = owned_case or bool(re.search(
        case + r"[^.;!?]{0,90}" + prior + r"|"
        + prior + r"[^.;!?]{0,90}" + case,
        normalized,
    ))
    status_request = bool(re.search(
        r"\b(?:seguimiento|seguimento|andamento|avance|novedades|atualizacoes|"
        r"atualizacao|actualizaciones|actualizacion|status|estado|situacion|retorno)\b|"
        r"\bcomo\s+(?:va|sigue|vai|esta|anda)\b|"
        r"\b(?:consultar|verificar|revisar|saber|conocer|checar|conferir)\b",
        normalized,
    ))
    return existing_case and status_request


def is_search_followup(text: str, language: str) -> bool:
    """Recognize one slot-only reply for an unfinished server-owned search.

    This predicate does not validate the value, preserve an intent, or read any
    conversation state. The caller can start an inquiry or continue a prior search,
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
    if is_date_reply(text, language):
        return True
    masked = mask_request_dates(normalized, language)
    if masked != normalized:
        # Combined details remain details: a date plus currency/amount cannot
        # start a dispute or discard an active request because of a model label.
        # Only closed connector/label words are removed; any business prose
        # remains and fails the whole money-fragment grammar below.
        normalized = re.sub(
            r"\b(?:el|la|o|a|del|de|en|em|fue|foi|por|y|e|fecha|data)\b", " ", masked)
        normalized = re.sub(r"(?<!\d)[,;:](?!\d)", " ", normalized).strip(" \t\r\n.!?¿¡")
        if not normalized:
            return True
        normalized = re.sub(r"\s+", " ", normalized)
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
        r"(?:\$\s*" + number + r"(?:\s+" + unit + r")?|"
        + number + r"(?:\s+" + unit + r")?|"
        + number + r"\s+pesos?\s+" + _CURRENCY + r"|"
        + unit + r"\s+" + number + r"|"
        + _CURRENCY + r"\s+" + number + r"\s+pesos?)",
        normalized, re.IGNORECASE,
    ))
