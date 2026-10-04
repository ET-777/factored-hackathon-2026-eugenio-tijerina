"""Loopback-only review UI with server-owned sessions and guarded workflow calls.

The default mode uses authored demo fixtures. An explicit trusted startup config
may supply an already validated, bounded private cohort and fixed customer. The
browser cannot choose the data source, identity or permissions. All actions remain
local simulations; production hosting/authentication are a separate task.
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from threading import RLock
import time
from types import MappingProxyType
import unicodedata
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from bank_service.access import AccessDenied, Permission, TrustedSession, require_access
from bank_service.actions import ActionDraft, ActionError, ActionService, VerifiedReceipt
from bank_service.case_store import CaseStore, StoreError
from bank_service.conversation import Conversation, ConversationError, ConversationReply
from bank_service.demo_fixtures import demo_records, demo_session
from bank_service.records import TransactionRecord
from bank_service.responses import ResponseFormatError, TransactionAnswer, with_requested_record_limits
from bank_service.routing import (
    IntentProposal, RoutingError, extract_slots, is_case_continuation, is_explicit_human_request,
    is_explicit_inquiry, is_greeting,
    is_search_followup, refers_to_selected_transaction, route_intent,
)
from bank_service.selection import MAX_SEARCH_RECORDS, SelectionError, TransactionFilters
from bank_service.transactions import SourceReference, SourcedTransaction, get_transaction


MAX_BODY_BYTES = 16 * 1024
MAX_SESSIONS = 20
MAX_MINTED_SESSIONS = 100
MAX_MESSAGES = 40
MAX_REQUESTS_PER_MINUTE = 60
COOKIE_NAME = "factored_demo"
WEB_ROOT = Path(__file__).with_name("web")
ACTION_KEYS = {
    "message": {"text"}, "choose": {"transaction_id"}, "inquire": {"transaction_id"},
    "search": {"transaction_date", "amount", "currency"},
    "prepare_intake": {"reason"},
    "dispute_selected": {"transaction_id"},
    "intake_decision": {"offer_id", "prepare"},
    "handoff_decision": {"offer_id", "prepare"},
    "prepare_handoff": {"request", "unresolved_questions"},
    "confirm": {"draft_id", "confirmed"}, "cancel": {"draft_id"},
    "language": {"language"}, "reset": set(), "view_case": {"case_id"},
}
TEXT = {
    "es": {
        "greeting": "Hola. Puedo ayudarte a consultar tus transacciones o preparar una solicitud de revisión. ¿Qué necesitas?",
        "denied": "No puedo acceder a esa información con esta sesión. Puedes iniciar una nueva sesión.",
        "invalid": "No pude interpretar esos datos. Revisa la fecha, el importe y la moneda, o selecciona una transacción de la lista.",
        "unsupported": "Puedo ayudarte a consultar transacciones y abrir solicitudes de revisión. Para esta petición, puedo preparar una derivación a revisión humana si lo deseas.",
        "request_scope": "Puedo ayudarte a consultar una transacción o solicitar su revisión. ¿Qué necesitas hacer?",
        "confirm_button": "Para aprobar una solicitud, revisa el borrador y usa su botón de confirmación.",
        "draft": "Preparé la solicitud en el panel lateral. Revisa allí sus detalles y usa «Confirmar y guardar» para enviarla a revisión. Aún no se ha guardado.",
        "intake_offer": "¿Quieres que prepare una solicitud de revisión de esta transacción? Esto no implica aprobar un reembolso. Puedes responder sí o no, o usar los botones.",
        "intake_declined": "De acuerdo. No preparé ni guardé una solicitud. Puedes seguir consultando tus movimientos.",
        "stale_offer": "Esta opción ya no está vigente. Consulta de nuevo la transacción para solicitar una revisión.",
        "selected_dispute": "No reconozco esta compra",
        "selection_changed": "El movimiento seleccionado cambió o ya no está disponible. Revisa el movimiento actual antes de solicitar una revisión.",
        "intake": "Abrir una solicitud de revisión de esta transacción.",
        "handoff": "Guardar una solicitud para revisión humana.",
        "receipt_verified": "Solicitud guardada y verificada. Referencia: ",
        "unknown": "No pude verificar el resultado de la solicitud. Conservé la misma referencia: vuelve a comprobarla para evitar crear un duplicado.",
        "stale": "Los datos cambiaron o el borrador venció. Revisa de nuevo la transacción y prepara otra solicitud.",
        "request": "Selecciona primero la transacción que quieres revisar.",
        "busy": "Hay demasiadas solicitudes. Espera un momento y vuelve a intentarlo.",
        "security": "La sesión de la página no coincide. Recarga la página antes de continuar.",
        "already_saved": "Esta solicitud ya está guardada. Comprueba la misma referencia para recuperar su recibo.",
        "currency": "Indica el código de moneda: MXN, COP, ARS o USD. «Pesos» y «$» pueden referirse a varias monedas. No convierto importes.",
        "unsupported_currency": "Puedo buscar movimientos en MXN, COP, ARS y USD. Esa moneda no está admitida. No convierto importes; indica una de esas monedas o una fecha en formato DD/MM/AAAA.",
        "dollars": "Interpreto «dólares» como USD; no hago una conversión de moneda.",
        "amount": "Indica el importe de la transacción o una fecha en formato DD/MM/AAAA, como 03/05/2026, para continuar la búsqueda. También puedes escribir el mes con palabras.",
        "followup": "Para continuar, indica una fecha en formato DD/MM/AAAA o con el mes escrito, el importe y su moneda, o elige una coincidencia de la lista.",
        "date_interpreted": "Como no indicaste año, uso el año actual: {year}. Buscaré la fecha {day}.",
        "invalid_date": "Revisa la fecha: usa DD/MM/AAAA, como 03/05/2026, o escribe el mes, como «3 de mayo de 2026». También acepto AAAA-MM-DD. Sin año, uso el año actual.",
        "ambiguous_date": "Indica una sola fecha para buscar. Las fechas numéricas se leen como día/mes/año (DD/MM/AAAA).",
        "ineligible_intake": "Este movimiento no admite la solicitud de revisión de compras. Puedo preparar un resumen para revisión humana con tu solicitud y los datos del movimiento.",
        "case_continuation": "No puedo verificar a qué caso anterior te refieres con la información disponible. Puedo preparar un resumen para revisión humana indicando que ese caso anterior no está verificado.",
        "session_cases": "Puedes consultar los recibos de esta sesión en «Solicitudes guardadas».",
        "handoff_offer": "¿Quieres que prepare ese resumen para revisión humana? Puedes responder sí o no, o usar los botones. Aún no se ha guardado ninguna solicitud.",
        "handoff_unavailable": "Esta sesión no permite guardar una solicitud para revisión humana. No se ha preparado ni guardado una solicitud.",
        "handoff_declined": "De acuerdo. No preparé ni guardé un resumen para revisión humana. Puedes seguir consultando.",
    },
    "pt": {
        "greeting": "Olá. Posso ajudar a consultar suas transações ou preparar uma solicitação de revisão. Do que você precisa?",
        "denied": "Não posso acessar essas informações com esta sessão. Você pode iniciar uma nova sessão.",
        "invalid": "Não consegui interpretar esses dados. Confira a data, o valor e a moeda, ou selecione uma transação da lista.",
        "unsupported": "Posso ajudar a consultar transações e abrir solicitações de revisão. Para este pedido, posso preparar um encaminhamento para revisão humana se você desejar.",
        "request_scope": "Posso ajudar a consultar uma transação ou solicitar sua revisão. O que você precisa fazer?",
        "confirm_button": "Para aprovar uma solicitação, revise o rascunho e use o botão de confirmação.",
        "draft": "Preparei a solicitação no painel lateral. Revise seus detalhes ali e use «Confirmar e salvar» para enviá-la para revisão. Ela ainda não foi salva.",
        "intake_offer": "Você quer que eu prepare uma solicitação de revisão desta transação? Isso não significa aprovar um reembolso. Pode responder sim ou não, ou usar os botões.",
        "intake_declined": "Tudo bem. Não preparei nem salvei uma solicitação. Você pode continuar consultando suas transações.",
        "stale_offer": "Esta opção não está mais vigente. Consulte novamente a transação para solicitar uma revisão.",
        "selected_dispute": "Não reconheço esta compra",
        "selection_changed": "A transação selecionada mudou ou não está mais disponível. Confira a transação atual antes de solicitar uma revisão.",
        "intake": "Abrir uma solicitação de revisão desta transação.",
        "handoff": "Salvar uma solicitação para revisão humana.",
        "receipt_verified": "Solicitação salva e verificada. Referência: ",
        "unknown": "Não consegui verificar o resultado da solicitação. Mantive a mesma referência: verifique-a novamente para evitar criar uma duplicata.",
        "stale": "Os dados mudaram ou o rascunho expirou. Consulte novamente a transação e prepare outra solicitação.",
        "request": "Selecione primeiro a transação que deseja revisar.",
        "busy": "Há muitas solicitações. Aguarde um momento e tente novamente.",
        "security": "A sessão da página não corresponde. Recarregue a página antes de continuar.",
        "already_saved": "Esta solicitação já está salva. Verifique a mesma referência para recuperar o recibo.",
        "currency": "Informe o código da moeda: MXN, COP, ARS ou USD. «Pesos» e «$» podem se referir a várias moedas. Não converto valores.",
        "unsupported_currency": "Posso pesquisar transações em MXN, COP, ARS e USD. Essa moeda não é aceita. Não converto valores; informe uma dessas moedas ou uma data no formato DD/MM/AAAA.",
        "dollars": "Interpreto «dólares» como USD; não faço conversão de moeda.",
        "amount": "Informe o valor da transação ou uma data no formato DD/MM/AAAA, como 03/05/2026, para continuar a pesquisa. Você também pode escrever o mês por extenso.",
        "followup": "Para continuar, informe uma data no formato DD/MM/AAAA ou com o mês por extenso, o valor e a moeda, ou escolha uma correspondência na lista.",
        "date_interpreted": "Como você não informou o ano, uso o ano atual: {year}. Vou pesquisar a data {day}.",
        "invalid_date": "Confira a data: use DD/MM/AAAA, como 03/05/2026, ou escreva o mês, como «3 de maio de 2026». Também aceito AAAA-MM-DD. Sem ano, uso o ano atual.",
        "ambiguous_date": "Informe uma única data para pesquisar. Datas numéricas são lidas como dia/mês/ano (DD/MM/AAAA).",
        "ineligible_intake": "Esta transação não permite a solicitação de revisão de compras. Posso preparar um resumo para revisão humana com seu pedido e os dados da transação.",
        "case_continuation": "Não consigo verificar a qual caso anterior você se refere com as informações disponíveis. Posso preparar um resumo para revisão humana indicando que esse caso anterior não foi verificado.",
        "session_cases": "Você pode consultar os recibos desta sessão em «Solicitações salvas».",
        "handoff_offer": "Você quer que eu prepare esse resumo para revisão humana? Pode responder sim ou não, ou usar os botões. Nenhuma solicitação foi salva ainda.",
        "handoff_unavailable": "Esta sessão não permite salvar uma solicitação para revisão humana. Nenhuma solicitação foi preparada ou salva.",
        "handoff_declined": "Tudo bem. Não preparei nem salvei um resumo para revisão humana. Você pode continuar consultando.",
    },
}

PRIVATE_TEXT = {
    "es": {
        "greeting": TEXT["es"]["greeting"],
        "denied": TEXT["es"]["denied"],
        "currency": "Indica el código de moneda: MXN, COP, ARS o USD. «Pesos» y «$» pueden referirse a varias monedas. La búsqueda conserva la moneda de los registros de esta instantánea privada.",
        "dollars": "Interpreto «dólares» como USD; no hago una conversión de moneda.",
        "customer_label": "Cliente",
    },
    "pt": {
        "greeting": TEXT["pt"]["greeting"],
        "denied": TEXT["pt"]["denied"],
        "currency": "Informe o código da moeda: MXN, COP, ARS ou USD. «Pesos» e «$» podem se referir a várias moedas. A pesquisa preserva a moeda dos registros desta amostra privada.",
        "dollars": "Interpreto «dólares» como USD; não faço conversão de moeda.",
        "customer_label": "Cliente",
    },
}


@dataclass(frozen=True, repr=False)
class PrivateCohortConfig:
    """Trusted startup selection, never reconstructed from browser arguments.

    The caller loads and validates the cohort before creating this configuration.
    Copying the bounded mapping prevents later caller mutations changing the
    configured snapshot. Frozen records and source references can safely be shared.
    """

    records: Mapping[str, SourcedTransaction]
    customer_id: str
    permissions: frozenset[Permission]

    def __post_init__(self) -> None:
        invalid = ValueError("invalid_private_cohort_config")
        allowed_permissions = frozenset({Permission.READ_TRANSACTION, Permission.CREATE_SIMULATED_INTAKE,
                                         Permission.CREATE_SIMULATED_HANDOFF})
        if (not isinstance(self.records, Mapping) or not 0 < len(self.records) <= MAX_SEARCH_RECORDS
                or not isinstance(self.customer_id, str) or not self.customer_id.strip()
                or self.customer_id != self.customer_id.strip()
                or not isinstance(self.permissions, frozenset)
                or any(not isinstance(permission, Permission) for permission in self.permissions)
                or not self.permissions <= allowed_permissions
                or Permission.READ_TRANSACTION not in self.permissions):
            raise invalid
        snapshot = dict(self.records)
        customer_found = False
        for identifier, entry in snapshot.items():
            if (not isinstance(identifier, str) or not identifier.strip()
                    or not isinstance(entry, SourcedTransaction) or not isinstance(entry.record, TransactionRecord)
                    or identifier != entry.record.transaction_id
                    or not isinstance(entry.sources, tuple) or not entry.sources):
                raise invalid
            customer_found = customer_found or entry.record.customer_id == self.customer_id
            for source in entry.sources:
                if (not isinstance(source, SourceReference) or not isinstance(source.file, str)
                        or not source.file or "\\" in source.file or ":" in source.file
                        or any(part in ("", ".", "..") for part in source.file.split("/"))
                        or any(ord(character) < 32 or ord(character) == 127 for character in source.file)
                        or type(source.row_number) is not int or source.row_number < 1
                        or not isinstance(source.row_sha256, str) or len(source.row_sha256) != 64
                        or any(character not in "0123456789abcdef" for character in source.row_sha256)):
                    raise invalid
        if not customer_found:
            raise invalid
        object.__setattr__(self, "records", MappingProxyType(snapshot))


class UiError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _request_reference_date(now: datetime) -> date:
    """Use the server clock in the customer's declared calendar zone."""
    return now.astimezone(ZoneInfo("America/Monterrey")).date()


def _browser_receipt_text(receipt: VerifiedReceipt) -> str:
    """Present only a receipt already validated by ActionService readback.

    The global DEMO badge carries the environment disclosure. Stored packets and
    CLI receipts retain their explicit simulation markers without editing facts.
    """
    return TEXT[receipt.language]["receipt_verified"] + json.dumps(receipt.case_id, ensure_ascii=False)


def _text(value: object, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > 1000 or (required and not value.strip()):
        raise UiError("invalid_input")
    return value.strip()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("invalid_json_number")


@dataclass
class PendingSearch:
    """One unfinished request and exact slots, owned by the trusted server session."""

    kind: str
    request: str
    transaction_date: date | None = None
    amount: Decimal | None = None
    currency: str | None = None


@dataclass(frozen=True)
class IntakeOffer:
    """Consent to preparation only, bound to this session's observed record."""

    offer_id: str
    transaction_id: str
    request: str
    snapshot: SourcedTransaction
    expires_at: datetime


@dataclass(frozen=True)
class HandoffOffer:
    """Preparation consent bound to the observed context, never a stored action."""

    offer_id: str
    transaction_id: str | None
    request: str
    snapshot: SourcedTransaction | None
    reason: str
    expires_at: datetime


def _intake_preference(text: str, language: str) -> bool | None:
    # Whole replies only. An action or refund request containing 'yes' is never
    # consent, and this parser is never used to confirm a stored action.
    normalized = "".join(character for character in unicodedata.normalize("NFKD", text.lower())
                         if not unicodedata.combining(character))
    normalized = " ".join(normalized.strip(" \t\r\n.!?¡¿").replace(",", " ").split())
    yes = {"es": {"si", "si por favor", "si prepara la solicitud", "de acuerdo"},
           "pt": {"sim", "sim por favor", "sim prepare a solicitacao", "pode preparar"}}
    no = {"es": {"no", "no gracias", "no por ahora"},
          "pt": {"nao", "nao obrigado", "nao obrigada", "nao por enquanto"}}
    if normalized in yes[language]:
        return True
    if normalized in no[language]:
        return False
    return None


class BrowserSession:
    """A browser token resolves to this exact server-owned session and controller."""

    def __init__(self, database: Path, *, config: PrivateCohortConfig | None = None, router=None):
        if config is not None and not isinstance(config, PrivateCohortConfig):
            raise ValueError("invalid_private_cohort_config")
        if router is not None and not callable(getattr(router, "route_intent", None)):
            raise ValueError("invalid_routing_component")
        self.router = router
        self.lock = RLock()
        self.retired = False
        self.csrf_token = secrets.token_urlsafe(32)
        self.data_mode = "demo" if config is None else "private_cohort"
        if config is None:
            self.session = demo_session(_now())
            self.records = demo_records()
        else:
            self.session = TrustedSession(config.customer_id, _now() + timedelta(minutes=20), config.permissions)
            self.records = MappingProxyType(dict(config.records))
        self.store = CaseStore(database)
        self.actions = ActionService(self.records, self.store)
        self.conversation = Conversation(self.records, self.actions, self.session)
        self.language = "es"
        self.messages: list[dict] = []
        self.selected_id: str | None = None
        self.candidate_ids: tuple[str, ...] = ()
        self.pending_draft: ActionDraft | None = None
        self.outcome_unverified = False
        self.pending_request: str | None = None
        self.pending_route: tuple[str, str] | None = None
        self.pending_search: PendingSearch | None = None
        self.intake_offer: IntakeOffer | None = None
        self.handoff_offer: HandoffOffer | None = None
        self.business_issue: str | None = None
        self.case_ids: list[str] = []
        self.handoff_id: str | None = None
        self.offers_handoff = False
        self.handoff_request: str | None = None
        self.request_times: deque[float] = deque()
        self.append("assistant", self.text("greeting"), "greeting")

    def text(self, key: str) -> str:
        if self.data_mode == "private_cohort" and key in PRIVATE_TEXT[self.language]:
            return PRIVATE_TEXT[self.language][key]
        return TEXT[self.language][key]

    def close(self) -> None:
        with self.lock:
            self.retired = True
            self.store.close()

    def append(self, role: str, text: str, status: str) -> None:
        self.messages.append({"role": role, "text": text, "status": status})
        self.messages = self.messages[-MAX_MESSAGES:]

    def authorize(self, now: datetime) -> None:
        if self.retired:
            raise AccessDenied("Access denied")
        require_access(self.session, self.session.customer_id, Permission.READ_TRANSACTION, now=now)

    def rate_limit(self) -> None:
        current = time.monotonic()
        while self.request_times and self.request_times[0] <= current - 60:
            self.request_times.popleft()
        if len(self.request_times) >= MAX_REQUESTS_PER_MINUTE:
            raise UiError("rate_limited", 429)
        self.request_times.append(current)

    def transaction(self, transaction_id: str, now: datetime) -> dict:
        entry = get_transaction(self.session, transaction_id, records=self.records, now=now)
        record = entry.record
        return {
            "transaction_id": record.transaction_id, "amount": str(record.amount),
            "currency": record.currency, "merchant_name": record.merchant_name,
            "transaction_status": record.transaction_status,
            "transaction_date": record.transaction_date.isoformat(),
            "process_date": record.process_date.isoformat(), "transaction_type": record.transaction_type,
            "sources": [asdict(ref) for ref in entry.sources],
        }

    def state(self, now: datetime) -> dict:
        try:
            self.authorize(now)
            active = True
        except AccessDenied:
            active = False
        state = {
            "language": self.language, "csrf_token": self.csrf_token, "data_mode": self.data_mode,
            "session": {"customer_label": self.text("customer_label") if self.data_mode == "private_cohort" else "Cliente A",
                        "expires_at": self.session.expires_at.isoformat(), "active": active},
            "simulation": True, "route_mode": "keyword_baseline" if self.router is None else "learned_preview", "messages": [],
            "transactions": [], "selected_transaction": None, "candidate_ids": [],
            "pending_draft": None, "receipts": [], "handoff": None, "offers_handoff": False,
            "handoff_request": None,
            "intake_offer": None,
            "handoff_offer": None,
        }
        if not active:
            state["messages"] = [{"role": "assistant", "status": "access_denied", "text": self.text("denied")}]
            return state
        # The snapshot is fixed for this browser session. Every returned entry
        # still goes through its actual owner guard; foreign records are omitted.
        state["transactions"] = [self.transaction(identifier, now) for identifier, entry in self.records.items()
                                 if entry.record.customer_id == self.session.customer_id]
        state["messages"] = list(self.messages)
        state["candidate_ids"] = [identifier for identifier in self.candidate_ids
                                  if get_transaction(self.session, identifier, records=self.records, now=now)]
        if self.selected_id is not None:
            state["selected_transaction"] = self.transaction(self.selected_id, now)
        if self.intake_offer is not None:
            offer = self.intake_offer
            if (now >= offer.expires_at or self.selected_id != offer.transaction_id
                    or get_transaction(self.session, offer.transaction_id, records=self.records, now=now) != offer.snapshot):
                self.intake_offer = None
            else:
                state["intake_offer"] = {"offer_id": offer.offer_id, "transaction_id": offer.transaction_id}
        if self.handoff_offer is not None:
            try:
                offer = self.bound_handoff_offer(self.handoff_offer.offer_id, now)
            except (UiError, AccessDenied):
                self.clear_handoff_offer()
            else:
                state["handoff_offer"] = {"offer_id": offer.offer_id, "transaction_id": offer.transaction_id}
        if self.pending_draft is not None:
            draft = self.pending_draft
            proposed = json.loads(self.actions.review_draft(self.session, draft.draft_id, now=now))
            state["pending_draft"] = {
                "draft_id": draft.draft_id, "kind": draft.kind,
                "summary": TEXT[self.language][draft.kind], "request": self.pending_request,
                "expires_at": draft.expires_at.isoformat(),
                "outcome_unverified": self.outcome_unverified,
                "packet": {key: proposed[key] for key in (
                    "request", "language", "facts", "sources", "attempted_steps",
                    "escalation_reason", "unresolved_questions", "verified_actions", "simulated",
                )},
            }
        for identifier in self.case_ids:
            receipt = self.actions.read_case(self.session, identifier, now=now)
            state["receipts"].append({"case_id": receipt.case_id, "kind": receipt.kind, "text": _browser_receipt_text(receipt)})
            if identifier == self.handoff_id:
                payload = json.loads(receipt.payload_json)
                state["handoff"] = {key: payload[key] for key in (
                    "request", "language", "escalation_reason", "attempted_steps", "unresolved_questions",
                    "facts", "sources", "verified_actions", "simulated",
                )}
        state["offers_handoff"] = self.offers_handoff
        if self.offers_handoff:
            state["handoff_request"] = self.handoff_request
        return state

    def reply(self, reply: ConversationReply) -> None:
        self.candidate_ids = reply.candidate_ids
        if reply.status in ("answered", "needs_filters", "no_match", "ambiguous"):
            self.selected_id = reply.selected_id
        text = reply.text
        if reply.status == "needs_filters":
            text = TEXT[self.language]["followup"]
        if reply.status == "answered" and self.pending_search is not None:
            text = with_requested_record_limits(
                TransactionAnswer(reply.language, reply.text, reply.sources), self.pending_search.request).text
        if reply.draft is not None:
            self.pending_draft = reply.draft
            self.outcome_unverified = False
            text = TEXT[self.language]["draft"]
        if reply.status == "cancelled":
            self.pending_draft, self.pending_request = None, None
            self.outcome_unverified = False
        if reply.receipt is not None:
            text = _browser_receipt_text(reply.receipt)
            self.pending_draft, self.pending_request = None, None
            self.outcome_unverified = False
            if reply.receipt.case_id not in self.case_ids:
                self.case_ids.append(reply.receipt.case_id)
                self.case_ids = self.case_ids[-12:]
            if reply.receipt.kind == "handoff":
                self.handoff_id = reply.receipt.case_id
                self.offers_handoff = False
        self.append("assistant", text, reply.status)

    def cancel_for_navigation(self, now: datetime) -> None:
        if self.pending_draft is not None:
            # Preserve the token if outcome reconciliation/cancellation fails.
            reply = self.conversation.confirm(
                self.session, self.pending_draft.draft_id, confirmed=False, now=now)
            self.reply(reply)

    def clear_record_selection(self, now: datetime) -> None:
        # Clear both UI and controller state before parsing a new query that may
        # fail. A stale selected record must never leak into a later draft.
        self.selected_id, self.candidate_ids = None, ()
        self.intake_offer = None
        self.clear_handoff_offer()
        self.conversation.clear_selection(self.session, now=now)

    def clear_search(self) -> None:
        self.pending_search, self.pending_route = None, None

    def clear_handoff_offer(self) -> None:
        self.handoff_offer = None
        self.offers_handoff = False
        self.handoff_request = None

    def bound_handoff_offer(self, identifier: str, now: datetime) -> HandoffOffer:
        self.authorize(now)
        offer = self.handoff_offer
        if (offer is None or identifier != offer.offer_id or now >= offer.expires_at
                or self.pending_draft is not None or self.selected_id != offer.transaction_id):
            raise UiError("stale_offer", 409)
        current = None if offer.transaction_id is None else get_transaction(
            self.session, offer.transaction_id, records=self.records, now=now)
        if current != offer.snapshot:
            self.clear_handoff_offer()
            raise UiError("stale_offer", 409)
        require_access(self.session, self.session.customer_id, Permission.CREATE_SIMULATED_HANDOFF, now=now)
        return offer

    def offer_human_review(self, request: str, reason: str, now: datetime) -> None:
        self.authorize(now)
        entry = None if self.selected_id is None else get_transaction(
            self.session, self.selected_id, records=self.records, now=now)
        self.clear_handoff_offer()
        self.intake_offer = None
        self.clear_search()
        self.business_issue = request
        try:
            require_access(self.session, self.session.customer_id, Permission.CREATE_SIMULATED_HANDOFF, now=now)
        except AccessDenied:
            self.append("assistant", TEXT[self.language]["handoff_unavailable"], "handoff_unavailable")
            return
        self.handoff_offer = HandoffOffer(
            secrets.token_urlsafe(24), self.selected_id, request, entry, reason,
            min(self.session.expires_at, now + timedelta(minutes=5)))
        self.offers_handoff, self.handoff_request = True, request
        self.append("assistant", TEXT[self.language]["handoff_offer"], "handoff_offered")

    def decide_handoff(self, identifier: str, prepare: bool, now: datetime) -> None:
        if type(prepare) is not bool:
            raise UiError("invalid_confirmation")
        offer = self.bound_handoff_offer(identifier, now)
        if prepare:
            self.prepare("handoff", offer.request, now)
        else:
            self.clear_handoff_offer()
            self.append("assistant", TEXT[self.language]["handoff_declined"], "handoff_declined")

    def unresolved_questions(self) -> tuple[str, ...]:
        issue = self.business_issue
        if issue is None and self.pending_search is not None:
            issue = self.pending_search.request
        if issue is None:
            return ()
        # Questions use a visibly bounded literal excerpt, never an invented
        # diagnosis or bank decision. The handoff has its own request field.
        return (issue if len(issue) <= 300 else issue[:297] + "...",)

    def prepare(self, kind: str, request: str, now: datetime, questions: tuple[str, ...] | None = None) -> None:
        reason = "unsupported_request" if request == self.handoff_request else "human_requested"
        if kind == "handoff" and self.handoff_offer is not None:
            # Also preserve the older explicit preparation port: it must match
            # the current server-owned request and snapshot, never replace them.
            offer = self.bound_handoff_offer(self.handoff_offer.offer_id, now)
            if request != offer.request or questions is not None:
                raise UiError("stale_offer", 409)
            reason = offer.reason
        self.intake_offer = None
        if kind == "intake":
            reply = self.conversation.prepare_intake(self.session, request, now=now)
            self.business_issue = request
        else:
            reply = self.conversation.prepare_handoff(
                self.session, request,
                escalation_reason=reason,
                unresolved_questions=self.unresolved_questions() if questions is None else questions, now=now)
        self.pending_request = request
        self.clear_search()
        self.clear_handoff_offer()
        self.reply(reply)

    def offer_intake(self, request: str, now: datetime) -> None:
        if self.selected_id is None:
            raise UiError("transaction_required")
        entry = get_transaction(self.session, self.selected_id, records=self.records, now=now)
        if (entry.record.transaction_type != "Purchase"
                or entry.record.transaction_status not in ("Approved", "Pending")):
            self.append("assistant", TEXT[self.language]["ineligible_intake"], "intake_ineligible")
            self.offer_human_review(request, "ineligible_intake", now)
            return
        require_access(self.session, entry.record.customer_id, Permission.CREATE_SIMULATED_INTAKE, now=now)
        self.intake_offer = IntakeOffer(secrets.token_urlsafe(24), self.selected_id, request, entry,
                                       min(self.session.expires_at, now + timedelta(minutes=5)))
        self.clear_search()
        self.append("assistant", TEXT[self.language]["intake_offer"], "intake_offered")

    def decide_intake(self, identifier: str, prepare: bool, now: datetime) -> None:
        if type(prepare) is not bool:
            raise UiError("invalid_confirmation")
        offer = self.intake_offer
        if (offer is None or identifier != offer.offer_id or now >= offer.expires_at
                or self.pending_draft is not None or self.selected_id != offer.transaction_id):
            raise UiError("stale_offer", 409)
        entry = get_transaction(self.session, offer.transaction_id, records=self.records, now=now)
        if entry != offer.snapshot:
            self.intake_offer = None
            raise UiError("stale_offer", 409)
        if prepare:
            # ActionService rechecks the separate intake grant, selection and
            # source snapshot. Preparation does not persist any case.
            self.prepare("intake", offer.request, now)
        else:
            self.intake_offer = None
            self.append("assistant", TEXT[self.language]["intake_declined"], "intake_declined")

    def message(self, text: str, now: datetime) -> None:
        self.append("user", text, "request")
        if self.pending_draft is not None:
            self.append("assistant", TEXT[self.language]["confirm_button"], "confirmation_required")
            return
        if self.handoff_offer is not None:
            preference = _intake_preference(text, self.language)
            if preference is not None:
                self.decide_handoff(self.handoff_offer.offer_id, preference, now)
                return
        if self.intake_offer is not None:
            preference = _intake_preference(text, self.language)
            if preference is not None:
                self.decide_intake(self.intake_offer.offer_id, preference, now)
                return
        if is_greeting(text, self.language):
            if self.handoff_offer is not None:
                self.append("assistant", TEXT[self.language]["handoff_offer"], "handoff_offered")
            elif self.intake_offer is not None:
                self.append("assistant", TEXT[self.language]["intake_offer"], "intake_offered")
            elif self.pending_search is not None:
                self.append("assistant", TEXT[self.language]["followup"], "needs_filters")
            else:
                self.append("assistant", self.text("greeting"), "greeting")
            return
        if is_case_continuation(text, self.language):
            self.intake_offer = None
            self.clear_handoff_offer()
            self.clear_search()
            try:
                slots = extract_slots(text, self.language, reference_date=_request_reference_date(now))
            except RoutingError:
                self.clear_record_selection(now)
                raise
            if slots.transaction_id is not None:
                self.clear_record_selection(now)
                self.reply(self.conversation.inquire(self.session, slots.transaction_id, now=now))
            elif slots.filters != TransactionFilters() or slots.needs_currency:
                self.clear_record_selection(now)
            self.append("assistant", TEXT[self.language]["case_continuation"], "case_unverified")
            if self.case_ids:
                self.append("assistant", TEXT[self.language]["session_cases"], "session_case_receipts")
            self.offer_human_review(text, "existing_case_unverified", now)
            return
        # Details alone start an inquiry or continue the server-owned request.
        # Neither classifier may infer a dispute/handoff from a date or amount.
        slot_only = is_search_followup(text, self.language)
        continuing = self.pending_search is not None and slot_only
        # Complete plain read requests have the same shared protection as
        # details alone. A classifier must not invent a dispute or handoff from
        # an explicit request to view/search a payment. Fresh requests replace
        # an unfinished dispute; only slot replies continue its prior intent.
        plain_inquiry = is_explicit_inquiry(text, self.language)
        proposal = (IntentProposal("inquiry", 1.0, True) if slot_only or plain_inquiry else
                    route_intent(text, self.language) if self.router is None else
                    self.router.route_intent(text, self.language))
        if (not isinstance(proposal, IntentProposal)
                or proposal.intent not in ("inquiry", "dispute_intake", "human_request", "unsupported")
                or type(proposal.matched) is not bool
                or type(proposal.confidence) not in (int, float)
                or not math.isfinite(proposal.confidence)
                or not 0 <= proposal.confidence <= 1
                or (not proposal.matched and proposal.intent != "unsupported")):
            raise RoutingError("invalid_intent_proposal")
        explicit_human = is_explicit_human_request(text, self.language)
        if explicit_human:
            # A positive user request, rather than a model score, determines
            # preparation intent. Final storage still requires confirmation.
            proposal = IntentProposal("human_request", 1.0, True)
        elif proposal.intent == "human_request":
            # A closed-set model label cannot supply the customer's request to
            # prepare a handoff. Do not turn unrelated/vague text into either a
            # draft or a new handoff offer, and keep any prior business context.
            self.append("assistant", TEXT[self.language]["request_scope"], "needs_request")
            return
        if self.handoff_offer is not None:
            if proposal.intent == "unsupported" and not proposal.matched and not slot_only:
                self.append("assistant", TEXT[self.language]["handoff_offer"], "handoff_offered")
                return
        self.clear_handoff_offer()
        if self.intake_offer is not None:
            if proposal.intent == "unsupported" and not proposal.matched and not is_search_followup(text, self.language):
                self.append("assistant", TEXT[self.language]["intake_offer"], "intake_offered")
                return
            self.intake_offer = None
        if proposal.intent == "human_request":
            self.prepare("handoff", text, now)
            return
        if proposal.intent == "unsupported":
            if not proposal.matched and self.pending_search is not None:
                self.append("assistant", TEXT[self.language]["followup"], "needs_filters")
                return
            self.clear_search()
            self.clear_record_selection(now)
            self.business_issue = text
            self.offers_handoff = True
            self.handoff_request = text
            self.append("assistant", TEXT[self.language]["unsupported"], "unsupported")
            return
        self.handoff_request = None
        if not continuing:
            kind = "intake" if proposal.intent == "dispute_intake" else "inquiry"
            self.pending_search = PendingSearch(kind, text)
            self.business_issue = text if kind == "intake" else None
        context = self.pending_search
        self.pending_route = ("intake", context.request) if context.kind == "intake" else None
        # Only an explicit reference to the selected transaction can reuse it.
        reuse_selection = (not continuing and self.selected_id is not None
                           and refers_to_selected_transaction(text, self.language))
        selected = self.selected_id
        self.clear_record_selection(now)
        try:
            slots = extract_slots(text, self.language, reference_date=_request_reference_date(now))
        except RoutingError as error:
            code = str(error)
            if code in ("invalid_amount", "ambiguous_amount", "unsupported_currency", "ambiguous_currency"):
                context.amount = None
            if code in ("unsupported_currency", "ambiguous_currency"):
                context.currency = None
            if code in ("invalid_date", "ambiguous_date"):
                context.transaction_date = None
            if code == "unsupported_currency":
                self.append("assistant", TEXT[self.language]["unsupported_currency"], "needs_currency")
                return
            raise
        if slots.used_dollar_alias:
            self.append("assistant", self.text("dollars"), "currency_interpretation")
        if slots.assumed_date_year:
            day = slots.filters.transaction_date
            self.append("assistant", TEXT[self.language]["date_interpreted"].format(
                year=day.year, day=day.strftime("%d/%m/%Y")), "date_interpreted")
        if slots.transaction_id is not None:
            self.reply(self.conversation.inquire(self.session, slots.transaction_id, now=now))
        elif reuse_selection and slots.filters == TransactionFilters() and not slots.needs_currency:
            self.reply(self.conversation.inquire(self.session, selected, now=now))
        else:
            if slots.filters.transaction_date is not None:
                context.transaction_date = slots.filters.transaction_date
            if slots.filters.currency is not None:
                context.currency = slots.filters.currency
            elif slots.currency_ambiguous:
                context.currency = None
            amount = slots.filters.amount if slots.filters.amount is not None else slots.amount_without_currency
            if amount is not None:
                context.amount = amount
            if slots.currency_ambiguous or (context.amount is not None and context.currency is None):
                self.append("assistant", self.text("currency"), "needs_currency")
                return
            if context.currency is not None and context.amount is None and context.transaction_date is None:
                self.append("assistant", TEXT[self.language]["amount"], "needs_filters")
                return
            self.reply(self.conversation.search(
                self.session, TransactionFilters(context.transaction_date, context.amount, context.currency), now=now))
        if context.kind == "intake":
            if self.selected_id is not None:
                self.offer_intake(context.request, now)
        elif self.selected_id is not None:
            self.clear_search()

    def act(self, payload: dict, now: datetime) -> None:
        self.authorize(now)
        self.rate_limit()
        action = payload["action"]
        if action == "dispute_selected":
            # A rendered shortcut identifies the record it referred to. An old
            # click must not silently apply to a newer selection or alter it.
            identifier = _text(payload.get("transaction_id"))
            if self.selected_id is None or identifier != self.selected_id:
                raise UiError("selection_changed", 409)
            get_transaction(self.session, identifier, records=self.records, now=now)
        if action not in ("message", "view_case", "prepare_handoff", "handoff_decision"):
            self.clear_handoff_offer()
        if action not in ("message", "dispute_selected", "intake_decision", "view_case"):
            self.intake_offer = None
        if action == "message":
            self.message(_text(payload.get("text")), now)
        elif action == "dispute_selected":
            self.message(TEXT[self.language]["selected_dispute"], now)
        elif action in ("choose", "inquire"):
            identifier = _text(payload.get("transaction_id"))
            route = self.pending_route if action == "choose" else None
            if action == "inquire":
                self.clear_search()
            self.cancel_for_navigation(now)
            self.selected_id, self.candidate_ids = None, ()
            method = self.conversation.choose if action == "choose" else self.conversation.inquire
            self.reply(method(self.session, identifier, now=now))
            self.clear_search()
            if action == "inquire":
                self.business_issue = None
            if route is not None:
                self.offer_intake(route[1], now)
        elif action == "search":
            self.cancel_for_navigation(now)
            self.clear_search()
            self.business_issue = None
            self.clear_record_selection(now)
            filters = _filters(payload)
            self.reply(self.conversation.search(self.session, filters, now=now))
        elif action == "prepare_intake":
            self.prepare("intake", _text(payload.get("reason")), now)
        elif action == "intake_decision":
            self.decide_intake(_text(payload.get("offer_id")), payload.get("prepare"), now)
        elif action == "handoff_decision":
            self.decide_handoff(_text(payload.get("offer_id")), payload.get("prepare"), now)
        elif action == "prepare_handoff":
            request = _text(payload.get("request"))
            questions = payload.get("unresolved_questions")
            if "unresolved_questions" in payload and (not isinstance(questions, list) or len(questions) > 10):
                raise UiError("invalid_input")
            self.prepare("handoff", request, now,
                         None if questions is None else tuple(_text(question) for question in questions))
        elif action in ("confirm", "cancel"):
            identifier = _text(payload.get("draft_id"))
            confirmed = payload.get("confirmed") if action == "confirm" else False
            if type(confirmed) is not bool:
                raise UiError("invalid_confirmation")
            self.reply(self.conversation.confirm(self.session, identifier, confirmed=confirmed, now=now))
        elif action == "language":
            language = payload.get("language")
            if language not in ("es", "pt"):
                raise UiError("unsupported_language")
            self.cancel_for_navigation(now)
            reply = self.conversation.set_language(self.session, language, now=now)
            self.language = language
            self.clear_search()
            self.reply(reply)
        elif action == "view_case":
            receipt = self.actions.read_case(self.session, _text(payload.get("case_id")), now=now)
            self.append("assistant", _browser_receipt_text(receipt), "action_verified")


def _filters(payload: dict) -> TransactionFilters:
    try:
        day = payload.get("transaction_date")
        amount = payload.get("amount")
        currency = payload.get("currency")
        if day is not None:
            day = _text(day)
            if len(day) != 10:
                raise ValueError("invalid_date")
            day = date.fromisoformat(day)
        if amount is not None:
            amount = Decimal(_text(amount))
        if currency is not None:
            currency = _text(currency)
        return TransactionFilters(day, amount, currency)
    except (ValueError, InvalidOperation):
        raise UiError("invalid_input") from None


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int = 8765, *, config: PrivateCohortConfig | None = None, router=None):
        if config is not None and not isinstance(config, PrivateCohortConfig):
            raise ValueError("invalid_private_cohort_config")
        if router is not None and not callable(getattr(router, "route_intent", None)):
            raise ValueError("invalid_routing_component")
        self._config = config
        self._router = router
        self._sessions: dict[str, BrowserSession] = {}
        self._session_lock = RLock()
        self._minted_sessions = 0
        self._temporary = TemporaryDirectory(prefix="factored-ui-")
        try:
            super().__init__(("127.0.0.1", port), DemoHandler)
        except Exception:
            self._temporary.cleanup()
            raise
        actual_port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}

    def mint_session(self) -> tuple[str, BrowserSession]:
        with self._session_lock:
            if len(self._sessions) >= MAX_SESSIONS or self._minted_sessions >= MAX_MINTED_SESSIONS:
                raise UiError("session_capacity", 503)
            token = secrets.token_urlsafe(32)
            session = BrowserSession(Path(self._temporary.name) / f"{token}.sqlite3", config=self._config,
                                     router=self._router)
            self._sessions[token] = session
            self._minted_sessions += 1
            return token, session

    def get_session(self, token: str | None) -> BrowserSession | None:
        with self._session_lock:
            return self._sessions.get(token) if token is not None else None

    def retire_session(self, token: str) -> None:
        with self._session_lock:
            session = self._sessions.pop(token, None)
        if session is not None:
            session.close()

    def server_close(self) -> None:
        super().server_close()
        with self._session_lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()
        self._temporary.cleanup()


class DemoHandler(BaseHTTPRequestHandler):
    server: DemoServer
    server_version = "FactoredLocalDemo"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args: object) -> None:
        # Never log browser prompts, cookies, source facts or request bodies.
        pass

    def _host(self) -> str:
        host = self.headers.get("Host", "")
        if host not in self.server.allowed_hosts:
            raise UiError("invalid_host", 403)
        return host

    def _cookie(self) -> str | None:
        try:
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie.get(COOKIE_NAME)
            return None if token is None else token.value
        except CookieError:
            return None

    def _send(self, status: int, body: bytes, content_type: str, token: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("Connection", "close")
        if token is not None:
            self.send_header("Set-Cookie", f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _json(self, status: int, value: dict, token: str | None = None) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8", token)

    def _error(self, error: Exception, session: BrowserSession | None = None) -> None:
        language = "es" if session is None else session.language
        status = error.status if isinstance(error, UiError) else 400
        code = str(error) if isinstance(error, (UiError, ActionError, ConversationError, RoutingError, SelectionError, ResponseFormatError)) else "operation_failed"
        label = "invalid"
        if isinstance(error, AccessDenied):
            status, code, label = 403, "access_denied", "denied"
        elif code in ("already_confirmed", "action_already_verified"):
            status, label = 409, "already_saved"
        elif isinstance(error, StoreError) or code in ("unknown_outcome", "action_not_verified"):
            status, label = 409, "unknown"
            if session is not None and session.pending_draft is not None:
                session.outcome_unverified = True
        elif code in ("stale_draft", "draft_expired", "draft_not_active", "no_pending_action"):
            status, label = 409, "stale"
        elif code == "stale_offer":
            status, label = 409, "stale_offer"
        elif code == "selection_changed":
            status, label = 409, "selection_changed"
        elif code == "transaction_required":
            label = "request"
        elif code in ("invalid_date", "ambiguous_date"):
            label = code
        elif code in ("csrf_rejected", "invalid_origin", "invalid_host", "session_required"):
            label = "security"
        elif code in ("rate_limited", "session_capacity"):
            label = "busy"
        state = {"language": language}
        if session is not None:
            try:
                state = session.state(_now())
            except (AccessDenied, ActionError, StoreError):
                pass
        state["error"] = {"code": code, "text": TEXT[language][label] if session is None else session.text(label),
                          "outcome_unverified": label == "unknown"}
        self._json(status, state)

    def do_GET(self) -> None:
        session = None
        try:
            host = self._host()
            path = urlsplit(self.path).path
            if path == "/api/state":
                site = self.headers.get("Sec-Fetch-Site")
                origin = self.headers.get("Origin")
                if ((site is not None and site not in ("same-origin", "none"))
                        or (origin is not None and origin != f"http://{host}")):
                    raise UiError("invalid_origin", 403)
                token = self._cookie()
                session = self.server.get_session(token)
                minted = session is None
                if minted:
                    token, session = self.server.mint_session()
                with session.lock:
                    self._json(200, session.state(_now()), token if minted else None)
                return
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                      "/app.js": ("app.js", "application/javascript; charset=utf-8")}
            if path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
                return
            if path not in assets:
                raise UiError("not_found", 404)
            filename, content_type = assets[path]
            self._send(200, (WEB_ROOT / filename).read_bytes(), content_type)
        except (UiError, AccessDenied, ActionError, StoreError) as error:
            self._error(error, session)
        except OSError:
            self._error(UiError("asset_unavailable", 503))

    def do_POST(self) -> None:
        session = None
        try:
            host = self._host()
            if self.headers.get("Origin") != f"http://{host}":
                raise UiError("invalid_origin", 403)
            if urlsplit(self.path).path != "/api/action":
                raise UiError("not_found", 404)
            if self.headers.get_content_type() != "application/json":
                raise UiError("invalid_content_type", 415)
            if self.headers.get("Transfer-Encoding") is not None:
                raise UiError("invalid_body", 400)
            try:
                size = int(self.headers.get("Content-Length", ""))
            except ValueError:
                raise UiError("invalid_body", 400) from None
            if not 0 < size <= MAX_BODY_BYTES:
                raise UiError("body_too_large", 413)
            try:
                payload = json.loads(self.rfile.read(size).decode("utf-8"),
                                     object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            except (ValueError, UnicodeError, RecursionError):
                raise UiError("invalid_json") from None
            if not isinstance(payload, dict):
                raise UiError("invalid_json")
            action = payload.get("action")
            if not isinstance(action, str) or action not in ACTION_KEYS:
                raise UiError("invalid_action")
            if set(payload) - ACTION_KEYS[action] - {"action", "csrf_token"}:
                raise UiError("unexpected_fields")
            token = self._cookie()
            session = self.server.get_session(token)
            if session is None:
                raise UiError("session_required", 401)
            with session.lock:
                if session.retired:
                    raise AccessDenied("Access denied")
                supplied = payload.get("csrf_token")
                if (not isinstance(supplied, str) or not supplied.isascii()
                        or not secrets.compare_digest(supplied, session.csrf_token)):
                    raise UiError("csrf_rejected", 403)
                if action == "reset":
                    # Reset mints fresh state with the same startup mode/customer;
                    # expiry never silently extends the old session's authority.
                    session.rate_limit()
                    self.server.retire_session(token)
                    token, session = self.server.mint_session()
                    self._json(200, session.state(_now()), token)
                    return
                session.act(payload, _now())
                self._json(200, session.state(_now()))
        except (UiError, AccessDenied, ActionError, StoreError, ConversationError,
                RoutingError, SelectionError, ResponseFormatError) as error:
            if session is not None:
                with session.lock:
                    self._error(error, session)
            else:
                self._error(error)


def serve(port: int = 8765, *, config: PrivateCohortConfig | None = None, router=None) -> None:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid_port")
    server = DemoServer(port, config=config, router=router)
    label = "fictional-data" if config is None else "private-cohort"
    print(f"Local {label} review UI: http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
