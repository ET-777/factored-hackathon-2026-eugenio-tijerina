"""Loopback-only demo UI with server-owned sessions and guarded workflow calls.

All records are independently authored demo fixtures. No source cohort, evaluator,
model, credential or network provider is loaded. This local HTTP server is a review
tool; production hosting/authentication are a separate deployment task.
"""

from collections import deque
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from threading import RLock
import time
from urllib.parse import urlsplit

from bank_service.access import AccessDenied, Permission, require_access
from bank_service.actions import ActionDraft, ActionError, ActionService
from bank_service.case_store import CaseStore, StoreError
from bank_service.conversation import Conversation, ConversationError, ConversationReply
from bank_service.demo_fixtures import demo_records, demo_session
from bank_service.responses import ResponseFormatError
from bank_service.routing import RoutingError, extract_slots, route_intent
from bank_service.selection import SelectionError, TransactionFilters
from bank_service.transactions import get_transaction


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
    "prepare_handoff": {"request", "unresolved_questions"},
    "confirm": {"draft_id", "confirmed"}, "cancel": {"draft_id"},
    "language": {"language"}, "reset": set(), "view_case": {"case_id"},
}
TEXT = {
    "es": {
        "greeting": "Hola. Puedo ayudarte a encontrar una transacción ficticia, revisar sus datos o abrir una solicitud de revisión. ¿Qué necesitas?",
        "denied": "No puedo acceder a esa información con esta sesión. Puedes iniciar una nueva sesión de demostración.",
        "invalid": "No pude interpretar esos datos. Revisa la fecha, el importe y la moneda, o selecciona una transacción de la lista.",
        "unsupported": "Esta demostración permite consultar transacciones y abrir solicitudes de revisión. Para esta petición, puedo preparar una derivación a revisión humana si lo deseas.",
        "confirm_button": "Para aprobar una solicitud, revisa el borrador y usa su botón de confirmación.",
        "draft": "Revisa los detalles de la solicitud antes de confirmar. Aún no se ha guardado.",
        "intake": "Abrir un ticket de revisión de esta transacción (demostración).",
        "handoff": "Guardar una solicitud para revisión humana (cola simulada).",
        "unknown": "No pude verificar el resultado de la solicitud. Conservé la misma referencia: vuelve a comprobarla para evitar crear un duplicado.",
        "stale": "Los datos cambiaron o el borrador venció. Revisa de nuevo la transacción y prepara otra solicitud.",
        "request": "Selecciona primero la transacción que quieres revisar.",
        "busy": "Hay demasiadas solicitudes. Espera un momento y vuelve a intentarlo.",
        "security": "La sesión de la página no coincide. Recarga la página antes de continuar.",
        "already_saved": "Esta solicitud ya está guardada. Comprueba la misma referencia para recuperar su recibo.",
    },
    "pt": {
        "greeting": "Olá. Posso ajudar a encontrar uma transação fictícia, consultar seus dados ou abrir uma solicitação de revisão. Do que você precisa?",
        "denied": "Não posso acessar essas informações com esta sessão. Você pode iniciar uma nova sessão de demonstração.",
        "invalid": "Não consegui interpretar esses dados. Confira a data, o valor e a moeda, ou selecione uma transação da lista.",
        "unsupported": "Esta demonstração permite consultar transações e abrir solicitações de revisão. Para este pedido, posso preparar um encaminhamento para revisão humana se você desejar.",
        "confirm_button": "Para aprovar uma solicitação, revise o rascunho e use o botão de confirmação.",
        "draft": "Revise os detalhes da solicitação antes de confirmar. Ela ainda não foi salva.",
        "intake": "Abrir um ticket de revisão desta transação (demonstração).",
        "handoff": "Salvar uma solicitação para revisão humana (fila simulada).",
        "unknown": "Não consegui verificar o resultado da solicitação. Mantive a mesma referência: verifique-a novamente para evitar criar uma duplicata.",
        "stale": "Os dados mudaram ou o rascunho expirou. Consulte novamente a transação e prepare outra solicitação.",
        "request": "Selecione primeiro a transação que deseja revisar.",
        "busy": "Há muitas solicitações. Aguarde um momento e tente novamente.",
        "security": "A sessão da página não corresponde. Recarregue a página antes de continuar.",
        "already_saved": "Esta solicitação já está salva. Verifique a mesma referência para recuperar o recibo.",
    },
}


class UiError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


class BrowserSession:
    """A browser token resolves to this exact server-owned session and controller."""

    def __init__(self, database: Path):
        self.lock = RLock()
        self.retired = False
        self.csrf_token = secrets.token_urlsafe(32)
        self.session = demo_session(_now())
        self.records = demo_records()
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
        self.case_ids: list[str] = []
        self.handoff_id: str | None = None
        self.offers_handoff = False
        self.handoff_request: str | None = None
        self.request_times: deque[float] = deque()
        self.append("assistant", TEXT[self.language]["greeting"], "greeting")

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
            "language": self.language, "csrf_token": self.csrf_token,
            "session": {"customer_label": "Cliente demo A" if self.language == "es" else "Cliente demo A",
                        "expires_at": self.session.expires_at.isoformat(), "active": active},
            "simulation": True, "route_mode": "keyword_baseline", "messages": [],
            "transactions": [], "selected_transaction": None, "candidate_ids": [],
            "pending_draft": None, "receipts": [], "handoff": None, "offers_handoff": False,
            "handoff_request": None,
        }
        if not active:
            state["messages"] = [{"role": "assistant", "status": "access_denied", "text": TEXT[self.language]["denied"]}]
            return state
        # The fixture set is fixed for this browser session. Every returned entry
        # still goes through its actual owner guard; foreign fixtures are omitted.
        state["transactions"] = [self.transaction(identifier, now) for identifier, entry in self.records.items()
                                 if entry.record.customer_id == self.session.customer_id]
        state["messages"] = list(self.messages)
        state["candidate_ids"] = [identifier for identifier in self.candidate_ids
                                  if get_transaction(self.session, identifier, records=self.records, now=now)]
        if self.selected_id is not None:
            state["selected_transaction"] = self.transaction(self.selected_id, now)
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
            state["receipts"].append({"case_id": receipt.case_id, "kind": receipt.kind, "text": receipt.text})
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
        if reply.draft is not None:
            self.pending_draft = reply.draft
            self.outcome_unverified = False
            text = TEXT[self.language]["draft"]
        if reply.status == "cancelled":
            self.pending_draft, self.pending_request = None, None
            self.outcome_unverified = False
        if reply.receipt is not None:
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

    def prepare(self, kind: str, request: str, now: datetime, questions: tuple[str, ...] = ()) -> None:
        if kind == "intake":
            reply = self.conversation.prepare_intake(self.session, request, now=now)
        else:
            reply = self.conversation.prepare_handoff(
                self.session, request, unresolved_questions=questions, now=now)
        self.pending_request = request
        self.reply(reply)

    def message(self, text: str, now: datetime) -> None:
        self.append("user", text, "request")
        proposal = route_intent(text, self.language)
        if self.pending_draft is not None:
            self.append("assistant", TEXT[self.language]["confirm_button"], "confirmation_required")
            return
        self.offers_handoff = False
        if proposal.intent == "human_request":
            self.prepare("handoff", text, now)
            return
        if proposal.intent == "unsupported":
            self.offers_handoff = True
            self.handoff_request = text
            self.append("assistant", TEXT[self.language]["unsupported"], "unsupported")
            return
        slots = extract_slots(text, self.language)
        self.pending_route = None
        if slots.transaction_id is not None:
            self.selected_id, self.candidate_ids = None, ()
            self.reply(self.conversation.inquire(self.session, slots.transaction_id, now=now))
        elif slots.filters != TransactionFilters() or self.selected_id is None:
            self.selected_id, self.candidate_ids = None, ()
            self.reply(self.conversation.search(self.session, slots.filters, now=now))
        else:
            self.reply(self.conversation.inquire(self.session, now=now))
        if proposal.intent == "dispute_intake":
            if self.selected_id is not None:
                self.prepare("intake", text, now)
            else:
                self.pending_route = ("intake", text)

    def act(self, payload: dict, now: datetime) -> None:
        self.authorize(now)
        self.rate_limit()
        action = payload["action"]
        self.offers_handoff = False
        if action == "message":
            self.message(_text(payload.get("text")), now)
        elif action in ("choose", "inquire"):
            identifier = _text(payload.get("transaction_id"))
            route = self.pending_route if action == "choose" else None
            self.cancel_for_navigation(now)
            self.selected_id, self.candidate_ids = None, ()
            method = self.conversation.choose if action == "choose" else self.conversation.inquire
            self.reply(method(self.session, identifier, now=now))
            self.pending_route = None
            if route is not None:
                self.prepare(route[0], route[1], now)
        elif action == "search":
            filters = _filters(payload)
            self.cancel_for_navigation(now)
            self.pending_route = None
            self.selected_id, self.candidate_ids = None, ()
            self.reply(self.conversation.search(self.session, filters, now=now))
        elif action == "prepare_intake":
            self.prepare("intake", _text(payload.get("reason")), now)
        elif action == "prepare_handoff":
            request = _text(payload.get("request"))
            questions = payload.get("unresolved_questions", [])
            if not isinstance(questions, list) or len(questions) > 10:
                raise UiError("invalid_input")
            self.prepare("handoff", request, now, tuple(_text(question) for question in questions))
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
            self.pending_route = None
            self.reply(reply)
        elif action == "view_case":
            receipt = self.actions.read_case(self.session, _text(payload.get("case_id")), now=now)
            self.append("assistant", receipt.text, "action_verified")


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

    def __init__(self, port: int = 8765):
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
            session = BrowserSession(Path(self._temporary.name) / f"{token}.sqlite3")
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
        elif code == "transaction_required":
            label = "request"
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
        state["error"] = {"code": code, "text": TEXT[language][label],
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
                    # Reset deliberately starts a fresh demonstration; expiration
                    # never silently grants the old conversation another session.
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


def serve(port: int = 8765) -> None:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid_port")
    server = DemoServer(port)
    print(f"Local fictional-data review UI: http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
