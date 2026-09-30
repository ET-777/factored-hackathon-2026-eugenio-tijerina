"""Confirmed, idempotent local simulations with verified readback receipts.

Drafts live only in this server-owned service and bind the exact TrustedSession
instance. A restart loses unconfirmed drafts; persisted cases remain owner-scoped.
No operation contacts a bank or human, determines fraud, or issues a refund.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import re
from threading import RLock
from uuid import uuid4

from bank_service.access import AccessDenied, Permission, TrustedSession, require_access
from bank_service.case_store import CaseStore, MAX_PAYLOAD_BYTES, StoredCase, StoreError
from bank_service.records import (
    SUPPORTED_CURRENCIES, SUPPORTED_TRANSACTION_STATUSES, SUPPORTED_TRANSACTION_TYPES,
    required_date, required_decimal, required_text, required_timestamp,
)
from bank_service.responses import _format_transaction, _quote_field
from bank_service.transactions import SourceReference, SourcedTransaction, get_transaction


DRAFT_TTL = timedelta(minutes=5)
MAX_DRAFTS = 200
MAX_TEXT_LENGTH = 1000
SERVER_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")


class ActionError(ValueError):
    """Fixed action-state errors only; unknown_outcome never means success."""


@dataclass(frozen=True)
class ActionDraft:
    draft_id: str
    kind: str
    transaction_id: str | None
    language: str
    summary: str
    expires_at: datetime


@dataclass(frozen=True)
class VerifiedReceipt:
    case_id: str
    kind: str
    transaction_id: str | None
    language: str
    text: str
    payload_json: str
    simulated: bool = True


@dataclass
class _DraftState:
    draft: ActionDraft
    session: TrustedSession
    case_id: str
    base_payload_json: str
    fingerprint: str | None
    expected_payload_json: str | None = None
    status: str = "pending"


def _canonical(value: object) -> str:
    try:
        result = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(result.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ActionError("action_payload_too_large")
        return result
    except (TypeError, ValueError, UnicodeError):
        raise ActionError("invalid_action_payload") from None


def _text(value: object, *, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ActionError("invalid_action_text")
    return value.strip()


def _language(value: object) -> str:
    if not isinstance(value, str) or value not in ("es", "pt"):
        raise ActionError("unsupported_language")
    return value


def _code(value: object) -> str:
    if not isinstance(value, str) or SERVER_CODE.fullmatch(value) is None:
        raise ActionError("invalid_server_code")
    return value


def _permission(kind: str) -> Permission:
    if kind == "intake":
        return Permission.CREATE_SIMULATED_INTAKE
    if kind == "handoff":
        return Permission.CREATE_SIMULATED_HANDOFF
    raise ActionError("unknown_outcome")


def _authorize(session: TrustedSession | None, kind: str, now: datetime, owner: str | None = None) -> None:
    if not isinstance(session, TrustedSession):
        raise AccessDenied("Access denied")
    owner = session.customer_id if owner is None else owner
    require_access(session, owner, Permission.READ_TRANSACTION, now=now)
    require_access(session, owner, _permission(kind), now=now)


def _snapshot(entry: SourcedTransaction) -> tuple[str, dict, list[dict]]:
    """Fingerprint every saved fact and reference; expose only permitted facts."""
    if (not isinstance(entry.sources, tuple) or not entry.sources
            or not all(isinstance(ref, SourceReference) for ref in entry.sources)):
        raise ActionError("invalid_record_evidence")
    values = {}
    for key, value in asdict(entry.record).items():
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ActionError("invalid_record_evidence")
            values[key] = str(value)
        elif isinstance(value, (date, datetime)):
            values[key] = value.isoformat()
        elif value is None or isinstance(value, str):
            values[key] = value
        else:
            raise ActionError("invalid_record_evidence")
    sources = [asdict(ref) for ref in entry.sources]
    fingerprint = hashlib.sha256(_canonical({"record": values, "sources": sources}).encode("utf-8")).hexdigest()
    facts = {key: value for key, value in values.items() if key not in ("customer_id", "product_id")}
    return fingerprint, facts, sources


def _validate_saved_packet(payload: dict) -> None:
    """Reject malformed stored packets even when no in-memory draft survives."""
    expected_fields = {
        "schema_version", "simulated", "operation", "draft_id", "customer_id",
        "transaction_id", "language", "request", "reason", "facts", "sources",
        "source_fingerprint", "escalation_reason", "attempted_steps", "unresolved_questions",
        "prepared_at", "confirmed_at", "verified_actions", "consent",
    }
    if set(payload) != expected_fields:
        raise ActionError("unknown_outcome")
    for field in ("draft_id", "customer_id"):
        required_text(payload, field)
    _language(payload["language"])
    request = _text(payload["request"])
    prepared = required_timestamp(payload, "prepared_at")
    confirmed = required_timestamp(payload, "confirmed_at")
    if prepared.utcoffset() is None or confirmed.utcoffset() is None or confirmed < prepared:
        raise ActionError("unknown_outcome")
    transaction_id = payload["transaction_id"]
    if transaction_id is None:
        if payload["facts"] is not None or payload["sources"] != [] or payload["source_fingerprint"] is not None:
            raise ActionError("unknown_outcome")
    else:
        required_text(payload, "transaction_id")
        facts, sources = payload["facts"], payload["sources"]
        if not isinstance(facts, dict) or set(facts) != {
            "transaction_id", "transaction_date", "process_date", "transaction_type",
            "amount", "currency", "transaction_status", "merchant_name",
        }:
            raise ActionError("unknown_outcome")
        if facts["transaction_id"] != transaction_id:
            raise ActionError("unknown_outcome")
        required_decimal(facts, "amount")
        required_timestamp(facts, "transaction_date")
        required_date(facts, "process_date")
        for field, allowed in (("currency", SUPPORTED_CURRENCIES),
                               ("transaction_type", SUPPORTED_TRANSACTION_TYPES),
                               ("transaction_status", SUPPORTED_TRANSACTION_STATUSES)):
            if required_text(facts, field) not in allowed:
                raise ActionError("unknown_outcome")
        if facts["merchant_name"] is not None and not isinstance(facts["merchant_name"], str):
            raise ActionError("unknown_outcome")
        if (not isinstance(payload["source_fingerprint"], str)
                or SHA256.fullmatch(payload["source_fingerprint"]) is None
                or not isinstance(sources, list) or not sources):
            raise ActionError("unknown_outcome")
        seen = set()
        for source in sources:
            if (not isinstance(source, dict) or set(source) != {"file", "row_number", "row_sha256"}
                    or not isinstance(source["file"], str) or not source["file"].strip()
                    or type(source["row_number"]) is not int or source["row_number"] < 1
                    or not isinstance(source["row_sha256"], str) or SHA256.fullmatch(source["row_sha256"]) is None):
                raise ActionError("unknown_outcome")
            identity = (source["file"], source["row_number"])
            if identity in seen:
                raise ActionError("unknown_outcome")
            seen.add(identity)
    steps, questions, actions = payload["attempted_steps"], payload["unresolved_questions"], payload["verified_actions"]
    if not isinstance(steps, list) or len(steps) > 12 or not isinstance(questions, list) or len(questions) > 10:
        raise ActionError("unknown_outcome")
    for step in steps:
        _code(step)
    for question in questions:
        _text(question, limit=MAX_TEXT_LENGTH)
    if not isinstance(actions, list) or len(actions) > 12:
        raise ActionError("unknown_outcome")
    action_ids = set()
    for action in actions:
        if (not isinstance(action, dict) or set(action) != {"case_id", "kind", "transaction_id", "verified", "simulated"}
                or not isinstance(action["case_id"], str) or not action["case_id"]
                or action["kind"] not in ("intake", "handoff")
                or action["verified"] is not True or action["simulated"] is not True
                or action["case_id"] in action_ids
                or (action["transaction_id"] is not None and not isinstance(action["transaction_id"], str))
                or (action["kind"] == "intake" and not action["transaction_id"])):
            raise ActionError("unknown_outcome")
        action_ids.add(action["case_id"])
    if payload["operation"] == "intake":
        if (transaction_id is None or payload["reason"] != request or payload["escalation_reason"] is not None
                or steps or questions or actions or payload["facts"]["transaction_type"] != "Purchase"
                or payload["facts"]["transaction_status"] not in ("Approved", "Pending")):
            raise ActionError("unknown_outcome")
    else:
        _code(payload["escalation_reason"])
        if payload["reason"] is not None:
            raise ActionError("unknown_outcome")


def _validate_stored_shape(stored: object) -> None:
    if not isinstance(stored, StoredCase) or any(
        not isinstance(getattr(stored, field), str) or not getattr(stored, field)
        for field in ("case_id", "idempotency_key", "owner_id", "kind", "payload_json",
                      "payload_sha256", "state", "created_at")
    ):
        raise ActionError("unknown_outcome")


class ActionService:
    """Server-owned action state; callers cannot submit or alter draft payloads."""

    def __init__(self, records: Mapping[str, SourcedTransaction], store: CaseStore):
        if not isinstance(records, Mapping):
            raise ActionError("invalid_repository")
        self.records = records
        self.store = store
        self._drafts: dict[str, _DraftState] = {}
        self._lock = RLock()

    def _new_draft(
        self, session: TrustedSession, kind: str, entry: SourcedTransaction | None,
        request: str, language: str, now: datetime, *, escalation_reason: str | None,
        attempted_steps: tuple[str, ...], unresolved_questions: tuple[str, ...],
        verified_actions: tuple[dict, ...] = (),
    ) -> ActionDraft:
        if len(self._drafts) >= MAX_DRAFTS:
            raise ActionError("draft_capacity_exceeded")
        draft_id = "draft_" + uuid4().hex
        fingerprint, facts, sources = (None, None, []) if entry is None else _snapshot(entry)
        transaction_id = None if entry is None else entry.record.transaction_id
        base = {
            "schema_version": 1, "simulated": True, "operation": kind,
            "draft_id": draft_id, "customer_id": session.customer_id,
            "transaction_id": transaction_id, "language": language, "request": request,
            "reason": request if kind == "intake" else None,
            "facts": facts, "sources": sources, "source_fingerprint": fingerprint,
            "escalation_reason": escalation_reason, "attempted_steps": list(attempted_steps),
            "unresolved_questions": list(unresolved_questions), "prepared_at": now.isoformat(),
            "verified_actions": list(verified_actions), "consent": False,
        }
        is_es = language == "es"
        heading = ("Borrador de solicitud de revisión simulada" if is_es else "Rascunho de solicitação de revisão simulada") if kind == "intake" else (
            "Borrador para una cola humana simulada" if is_es else "Rascunho para uma fila humana simulada")
        lines = [heading]
        if kind == "intake":
            lines.append("Regla sintética de demostración: compras aprobadas (Approved) o pendientes (Pending)." if is_es else
                         "Regra sintética de demonstração: compras aprovadas (Approved) ou pendentes (Pending).")
        if entry is not None:
            lines.append(_format_transaction(entry, language).text)
        else:
            lines.append("Sin transacción seleccionada." if is_es else "Nenhuma transação selecionada.")
        lines.append(("Solicitud: " if is_es else "Solicitação: ") + _quote_field(request))
        if kind == "handoff":
            lines.append(("Motivo de derivación: " if is_es else "Motivo do encaminhamento: ") + escalation_reason)
            lines.append(("Pasos intentados: " if is_es else "Etapas tentadas: ") + _canonical(list(attempted_steps)))
            lines.append(("Preguntas pendientes: " if is_es else "Perguntas pendentes: ") +
                         "; ".join(_quote_field(question) for question in unresolved_questions))
            lines.append(("Acciones simuladas verificadas: " if is_es else "Ações simuladas verificadas: ") +
                         "; ".join(_quote_field(action["case_id"]) for action in verified_actions))
        lines.append("Confirma estos detalles para guardar la simulación. Este borrador aún no se ha guardado." if is_es else
                     "Confirme estes detalhes para salvar a simulação. Este rascunho ainda não foi salvo.")
        draft = ActionDraft(draft_id, kind, transaction_id, language, "\n".join(lines),
                            min(now + DRAFT_TTL, session.expires_at))
        self._drafts[draft_id] = _DraftState(draft, session, "sim_" + uuid4().hex, _canonical(base), fingerprint)
        return draft

    def prepare_intake(
        self, session: TrustedSession | None, transaction_id: str, reason: str, *, language: str, now: datetime,
    ) -> ActionDraft:
        with self._lock:
            _authorize(session, "intake", now)
            language, reason = _language(language), _text(reason)
            entry = get_transaction(session, transaction_id, records=self.records, now=now)
            if entry.record.transaction_type != "Purchase" or entry.record.transaction_status not in ("Approved", "Pending"):
                raise ActionError("unsupported_intake_state")
            return self._new_draft(session, "intake", entry, reason, language, now,
                                   escalation_reason=None, attempted_steps=(), unresolved_questions=())

    def prepare_handoff(
        self, session: TrustedSession | None, *, transaction_id: str | None, request: str,
        escalation_reason: str, attempted_steps: tuple[str, ...], unresolved_questions: tuple[str, ...],
        language: str, now: datetime, verified_case_ids: tuple[str, ...] = (),
    ) -> ActionDraft:
        with self._lock:
            _authorize(session, "handoff", now)
            language, request = _language(language), _text(request)
            escalation_reason = _code(escalation_reason)
            if not isinstance(attempted_steps, tuple) or len(attempted_steps) > 12:
                raise ActionError("invalid_attempted_steps")
            if not isinstance(unresolved_questions, tuple) or len(unresolved_questions) > 10:
                raise ActionError("invalid_unresolved_questions")
            attempted_steps = tuple(_code(step) for step in attempted_steps)
            unresolved_questions = tuple(_text(question, limit=300) for question in unresolved_questions)
            if not unresolved_questions:
                unresolved_questions = (request,)
            if (not isinstance(verified_case_ids, tuple) or len(verified_case_ids) > 12
                    or any(not isinstance(case_id, str) or not case_id for case_id in verified_case_ids)
                    or len(set(verified_case_ids)) != len(verified_case_ids)):
                raise ActionError("invalid_verified_case_ids")
            verified_actions = []
            for case_id in verified_case_ids:
                receipt = self.read_case(session, case_id, now=now)
                verified_actions.append({"case_id": receipt.case_id, "kind": receipt.kind,
                                         "transaction_id": receipt.transaction_id,
                                         "verified": True, "simulated": True})
            entry = None if transaction_id is None else get_transaction(session, transaction_id, records=self.records, now=now)
            return self._new_draft(session, "handoff", entry, request, language, now,
                                   escalation_reason=escalation_reason, attempted_steps=attempted_steps,
                                   unresolved_questions=unresolved_questions,
                                   verified_actions=tuple(verified_actions))

    def _bound_draft(self, session: TrustedSession | None, draft_id: str, now: datetime) -> _DraftState:
        if not isinstance(session, TrustedSession) or not isinstance(draft_id, str):
            raise AccessDenied("Access denied")
        state = self._drafts.get(draft_id)
        if state is None or state.session is not session:
            raise AccessDenied("Access denied")
        _authorize(session, state.draft.kind, now)
        return state

    def _read_key(self, draft_id: str) -> StoredCase | None:
        try:
            return self.store.read_by_key(draft_id)
        except StoreError:
            raise ActionError("unknown_outcome") from None

    def _receipt(self, stored: StoredCase, state: _DraftState | None = None) -> VerifiedReceipt:
        """Validate stored identity, operation, state and complete expected payload."""
        _validate_stored_shape(stored)
        try:
            payload = json.loads(stored.payload_json)
            if (not isinstance(payload, dict) or _canonical(payload) != stored.payload_json
                    or hashlib.sha256(stored.payload_json.encode("utf-8")).hexdigest() != stored.payload_sha256
                    or stored.state != "recorded" or stored.kind not in ("intake", "handoff")
                    or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1
                    or payload.get("simulated") is not True or payload.get("consent") is not True
                    or payload.get("customer_id") != stored.owner_id
                    or payload.get("draft_id") != stored.idempotency_key
                    or payload.get("operation") != stored.kind
                    or payload.get("confirmed_at") != stored.created_at
                    or payload.get("language") not in ("es", "pt")
                    or not isinstance(stored.case_id, str) or not stored.case_id):
                raise ActionError("unknown_outcome")
            if state is not None and (
                state.expected_payload_json is None or stored.payload_json != state.expected_payload_json
                or stored.case_id != state.case_id or stored.idempotency_key != state.draft.draft_id
                or stored.owner_id != state.session.customer_id or stored.kind != state.draft.kind
            ):
                raise ActionError("unknown_outcome")
            transaction_id = payload.get("transaction_id")
            if (transaction_id is not None and (not isinstance(transaction_id, str) or not transaction_id)):
                raise ActionError("unknown_outcome")
            if stored.kind == "intake" and transaction_id is None:
                raise ActionError("unknown_outcome")
            _validate_saved_packet(payload)
        except (TypeError, ValueError, KeyError, AttributeError, UnicodeError, RecursionError):
            raise ActionError("unknown_outcome") from None
        is_es = payload["language"] == "es"
        if stored.kind == "intake":
            text = ("Solicitud simulada guardada y verificada. No resuelve una disputa ni emite un reembolso. Referencia: " if is_es else
                    "Solicitação simulada salva e verificada. Não resolve uma contestação nem emite um reembolso. Referência: ")
        else:
            text = ("Entrada guardada y verificada en una cola simulada. No se ha contactado a una persona. Referencia: " if is_es else
                    "Entrada salva e verificada em uma fila simulada. Nenhuma pessoa foi contatada. Referência: ")
        return VerifiedReceipt(stored.case_id, stored.kind, transaction_id, payload["language"],
                               text + _quote_field(stored.case_id), stored.payload_json)

    def confirm(
        self, session: TrustedSession | None, draft_id: str, *, confirmed: bool, now: datetime,
    ) -> VerifiedReceipt | None:
        with self._lock:
            state = self._bound_draft(session, draft_id, now)
            if type(confirmed) is not bool:
                raise ActionError("explicit_confirmation_required")
            if state.status == "cancelled":
                if not confirmed:
                    return None
                raise ActionError("draft_not_active")
            if state.status in ("stale", "expired") and confirmed:
                raise ActionError("draft_not_active")

            # Read first on EVERY attempt; an earlier write may have committed.
            existing = self._read_key(draft_id)
            if existing is not None:
                receipt = self._receipt(existing, state)
                state.status = "confirmed"
                if not confirmed:
                    raise ActionError("already_confirmed")
                return receipt
            if state.status == "confirmed":
                raise ActionError("unknown_outcome")
            if not confirmed:
                state.status = "cancelled"
                return None
            if now >= state.draft.expires_at:
                state.status = "expired"
                raise ActionError("draft_expired")

            if state.draft.transaction_id is not None:
                try:
                    current = get_transaction(session, state.draft.transaction_id, records=self.records, now=now)
                except AccessDenied:
                    state.status = "stale"
                    raise
                if _snapshot(current)[0] != state.fingerprint:
                    state.status = "stale"
                    raise ActionError("stale_draft")
            if state.expected_payload_json is None:
                payload = json.loads(state.base_payload_json)
                payload.update(consent=True, confirmed_at=now.isoformat())
                state.expected_payload_json = _canonical(payload)
            payload = json.loads(state.expected_payload_json)
            state.status = "unknown"
            try:
                self.store.write_case(
                    case_id=state.case_id, idempotency_key=draft_id, owner_id=session.customer_id,
                    kind=state.draft.kind, payload_json=state.expected_payload_json,
                    created_at=payload["confirmed_at"],
                )
            except StoreError:
                raise ActionError("unknown_outcome") from None
            stored = self._read_key(draft_id)
            if stored is None:
                raise ActionError("unknown_outcome")
            receipt = self._receipt(stored, state)
            state.status = "confirmed"
            return receipt

    def cancel(self, session: TrustedSession | None, draft_id: str, *, now: datetime) -> None:
        self.confirm(session, draft_id, confirmed=False, now=now)

    def review_draft(self, session: TrustedSession | None, draft_id: str, *, now: datetime) -> str:
        """Return the exact proposed payload for authorized pre-consent review.

        This is a read-only presentation port. The caller cannot replace this
        payload when confirming; confirmation still uses server-owned state.
        """
        with self._lock:
            state = self._bound_draft(session, draft_id, now)
            if state.draft.transaction_id is not None:
                get_transaction(session, state.draft.transaction_id, records=self.records, now=now)
            return state.base_payload_json

    def read_case(self, session: TrustedSession | None, case_id: str, *, now: datetime) -> VerifiedReceipt:
        with self._lock:
            if not isinstance(session, TrustedSession) or not isinstance(case_id, str) or not case_id:
                raise AccessDenied("Access denied")
            require_access(session, session.customer_id, Permission.READ_TRANSACTION, now=now)
            try:
                stored = self.store.read_case(case_id)
            except StoreError:
                raise ActionError("unknown_outcome") from None
            if stored is None:
                raise AccessDenied("Access denied")
            _validate_stored_shape(stored)
            _authorize(session, stored.kind, now, stored.owner_id)
            if stored.case_id != case_id:
                raise ActionError("unknown_outcome")
            return self._receipt(stored, self._drafts.get(stored.idempotency_key))
