"""Run the real local workflow with authored fixtures and explicit scripted consent.

This is a deterministic integration demonstration, not an intent model or an
evaluation score. No raw dataset, private cohort, final case, or network is used.
"""

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from bank_service.access import AccessDenied
from bank_service.actions import ActionService
from bank_service.case_store import CaseStore
from bank_service.conversation import Conversation, ConversationReply
from bank_service.demo_fixtures import demo_records, demo_session
from bank_service.selection import TransactionFilters


@dataclass(frozen=True)
class DemoResult:
    language: str
    scenario: str
    new_cases: int
    duplicate_reused: bool
    access_denials: int


def run_demo(
    *, language: str = "es", scenario: str = "all",
    db_path: Path | None = None, emit: Callable[[str], None] = print,
) -> DemoResult:
    """Exercise inquiry, confirmation, duplicate delivery, handoff, and denial.

    With no db_path the database is temporary. With a path, cases survive this
    process. Each invocation is a new conversation with new request identifiers.
    The duplicate-confirmation step within an invocation must reuse its receipt.
    """
    if language not in ("es", "pt") or scenario not in ("all", "inquiry", "intake", "handoff", "safety"):
        raise ValueError("invalid_demo_option")

    def show(reply: ConversationReply) -> None:
        emit(f"\n[{reply.status}]\n{reply.text}")
        if reply.candidate_ids:
            emit("\n".join(reply.candidate_ids))
        for ref in reply.sources:
            emit(f"source: {ref.file}:{ref.row_number} sha256={ref.row_sha256}")

    with ExitStack() as stack:
        if db_path is None:
            directory = stack.enter_context(TemporaryDirectory(prefix="factored-demo-"))
            db_path = Path(directory) / "cases.sqlite3"
        else:
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
        store = CaseStore(db_path)
        stack.callback(store.close)
        before_count = store.count()
        records = demo_records()
        session_time = datetime.now(timezone.utc)
        session = demo_session(session_time)
        actions = ActionService(records, store)
        conversation = Conversation(records, actions, session, language=language)
        emit({
            "es": "DEMOSTRACIÓN LOCAL: datos ficticios, acciones simuladas y confirmaciones programadas explícitas. Sin banco ni contacto humano real.",
            "pt": "DEMONSTRAÇÃO LOCAL: dados fictícios, ações simuladas e confirmações programadas explícitas. Sem banco ou contato humano real.",
        }[language])

        # Use a fresh server clock at each tool boundary.
        clock = lambda: datetime.now(timezone.utc)
        show(conversation.search(session, TransactionFilters(
            amount=Decimal("25.50"), currency="USD"), now=clock()))
        show(conversation.choose(session, "DEMO-TX-001", now=clock()))

        duplicate_reused = False
        if scenario in ("all", "intake"):
            reason = {"es": "No reconozco esta compra ficticia.", "pt": "Não reconheço esta compra fictícia."}[language]
            draft_reply = conversation.prepare_intake(session, reason, now=clock())
            show(draft_reply)
            emit("[scripted explicit confirmation: True]")
            receipt_reply = conversation.confirm(
                session, draft_reply.draft.draft_id, confirmed=True, now=clock())
            show(receipt_reply)
            repeated = conversation.confirm(
                session, draft_reply.draft.draft_id, confirmed=True, now=clock())
            duplicate_reused = repeated.receipt.case_id == receipt_reply.receipt.case_id
            if not duplicate_reused:
                raise RuntimeError("duplicate_receipt_mismatch")
            emit({"es": "Confirmación repetida: mismo recibo; sin caso duplicado.",
                  "pt": "Confirmação repetida: mesmo recibo; sem caso duplicado."}[language])

        if scenario in ("all", "handoff"):
            request = {"es": "Quiero revisión humana de esta compra ficticia.",
                       "pt": "Quero uma revisão humana desta compra fictícia."}[language]
            question = {"es": "¿Qué información adicional necesitaría el equipo humano?",
                        "pt": "Quais informações adicionais a equipe humana precisaria?"}[language]
            draft_reply = conversation.prepare_handoff(
                session, request, unresolved_questions=(question,), now=clock())
            show(draft_reply)
            emit("[scripted explicit consent: True]")
            receipt_reply = conversation.confirm(
                session, draft_reply.draft.draft_id, confirmed=True, now=clock())
            show(receipt_reply)
            # Safe here only because this entry point constructs fictional data.
            emit(receipt_reply.receipt.payload_json)

        denials = 0
        if scenario in ("all", "safety"):
            for identifier, instant in (
                ("DEMO-TX-003", clock()), ("DEMO-TX-001", session.expires_at),
            ):
                try:
                    conversation.inquire(session, identifier, now=instant)
                except AccessDenied:
                    denials += 1
                    emit({"es": "Acceso rechazado de forma segura.", "pt": "Acesso negado com segurança."}[language])
                else:
                    raise RuntimeError("expected_access_denial")
        return DemoResult(language, scenario, store.count() - before_count, duplicate_reused, denials)
