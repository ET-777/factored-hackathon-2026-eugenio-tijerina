"""Small server-owned conversation state for the simulated banking workflow.

The UI supplies structured filters, choices and explicit confirmation; this module
does not infer consent from text or model output. Create one instance per trusted
session and serialize its turns. State is local to the process, not browser input.
All replies are plain text. Portuguese wording awaits independent human review.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from bank_service.access import AccessDenied, Permission, TrustedSession, require_access
from bank_service.actions import ActionDraft, ActionError, ActionService, VerifiedReceipt
from bank_service.case_store import StoreError
from bank_service.responses import answer_transaction
from bank_service.selection import TransactionFilters, select_transaction
from bank_service.transactions import SourceReference, SourcedTransaction


TEXT = {
    "es": {
        "language_changed": "Idioma cambiado a español.",
        "cancelled": "Solicitud cancelada sin crear un caso nuevo.",
    },
    "pt": {
        "language_changed": "Idioma alterado para português.",
        "cancelled": "Solicitação cancelada sem criar um novo caso.",
    },
}
MAX_ATTEMPTED_STEPS = 12


class ConversationError(ValueError):
    """Fixed error codes only, without customer data or user-supplied text."""


@dataclass(frozen=True)
class ConversationReply:
    status: str
    language: str
    text: str
    candidate_ids: tuple[str, ...] = ()
    selected_id: str | None = None
    draft: ActionDraft | None = None
    receipt: VerifiedReceipt | None = None
    sources: tuple[SourceReference, ...] = ()


class Conversation:
    """Bind all transient state to one server-issued TrustedSession instance.

    Session equality is insufficient: a reconstructed or renewed session needs
    a new conversation. Facts and receipts are read again on every use rather
    than cached in conversation state. Candidate IDs confer no authority.
    """

    def __init__(
        self,
        records: Mapping[str, SourcedTransaction],
        actions: ActionService,
        session: TrustedSession,
        *,
        language: str = "es",
    ) -> None:
        if not isinstance(session, TrustedSession):
            raise AccessDenied("Access denied")
        self._validate_language(language)
        self._records = records
        self._actions = actions
        self._session = session
        self._language = language
        self._candidate_ids: tuple[str, ...] = ()
        self._selected_id: str | None = None
        self._pending_draft_id: str | None = None
        self._confirmed_draft_id: str | None = None
        self._attempted_steps: tuple[str, ...] = ()
        self._verified_case_ids: tuple[str, ...] = ()

    @staticmethod
    def _validate_language(language: str) -> None:
        if not isinstance(language, str) or language not in TEXT:
            raise ConversationError("unsupported_language")

    def _authorize(self, session: TrustedSession, now: datetime) -> None:
        if session is not self._session:
            raise AccessDenied("Access denied")
        require_access(session, session.customer_id, Permission.READ_TRANSACTION, now=now)

    def _step(self, code: str) -> None:
        # This is a bounded summary of distinct observed step types, not an
        # execution log. Repeated searches must not crowd out earlier outcomes.
        # Codes originate in this controller, never in a user/model transcript.
        if code not in self._attempted_steps:
            self._attempted_steps = (*self._attempted_steps, code)[-MAX_ATTEMPTED_STEPS:]

    def _invalidate_action(self, session: TrustedSession, now: datetime) -> None:
        pending_id = self._pending_draft_id
        if pending_id is not None:
            # Preserve this recovery token if cancellation cannot establish that
            # no case exists. A previous confirmation may already have committed.
            # The new turn aborts; a repeated explicit confirmation can reconcile.
            self._actions.cancel(session, pending_id, now=now)
        self._pending_draft_id = None
        self._confirmed_draft_id = None

    def _clear_selection(self, session: TrustedSession, now: datetime) -> None:
        # Clear selection first even when cancellation/search/formatting fails.
        self._candidate_ids = ()
        self._selected_id = None
        self._invalidate_action(session, now)

    def _answer(self, session: TrustedSession, transaction_id: str, now: datetime) -> ConversationReply:
        answer = answer_transaction(
            session, transaction_id, records=self._records, language=self._language, now=now,
        )
        self._selected_id = transaction_id
        self._candidate_ids = ()
        self._step("transaction_answered")
        return ConversationReply(
            "answered", self._language, answer.text,
            selected_id=transaction_id, sources=answer.sources,
        )

    def clear_selection(self, session: TrustedSession, *, now: datetime) -> None:
        """Start a new subject without discarding observed steps or verified cases.

        If cancellation cannot establish the previous action's outcome, this
        raises and preserves its recovery token while clearing record selection.
        """
        self._authorize(session, now)
        self._clear_selection(session, now)

    def search(
        self, session: TrustedSession, filters: TransactionFilters, *, now: datetime,
    ) -> ConversationReply:
        self._authorize(session, now)
        self._clear_selection(session, now)
        self._step("search_attempted")
        result = select_transaction(
            session, filters, records=self._records, language=self._language, now=now,
        )
        if result.status == "selected":
            return self._answer(session, result.candidate_ids[0], now)
        self._candidate_ids = result.candidate_ids
        self._step("search_" + result.status)
        return ConversationReply(
            result.status, self._language, result.clarification or "",
            candidate_ids=result.candidate_ids,
        )

    def choose(
        self, session: TrustedSession, transaction_id: str, *, now: datetime,
    ) -> ConversationReply:
        self._authorize(session, now)
        if not isinstance(transaction_id, str) or transaction_id not in self._candidate_ids:
            self._step("choice_rejected")
            # A rejected choice starts no valid selection. Do not silently carry
            # a previously answered transaction into a later action or handoff.
            self._clear_selection(session, now)
            raise ConversationError("invalid_choice")
        self._clear_selection(session, now)
        return self._answer(session, transaction_id, now)

    def inquire(
        self, session: TrustedSession, transaction_id: str | None = None, *, now: datetime,
    ) -> ConversationReply:
        self._authorize(session, now)
        selected_id = self._selected_id if transaction_id is None else transaction_id
        if selected_id is None:
            raise ConversationError("transaction_required")
        self._clear_selection(session, now)
        return self._answer(session, selected_id, now)

    def set_language(
        self, session: TrustedSession, language: str, *, now: datetime,
    ) -> ConversationReply:
        self._authorize(session, now)
        self._validate_language(language)
        self._invalidate_action(session, now)
        self._language = language
        return ConversationReply("language_changed", language, TEXT[language]["language_changed"])

    def prepare_intake(
        self, session: TrustedSession, reason: str, *, now: datetime,
    ) -> ConversationReply:
        self._authorize(session, now)
        if self._selected_id is None:
            raise ConversationError("transaction_required")
        self._invalidate_action(session, now)
        draft = self._actions.prepare_intake(
            session, self._selected_id, reason, language=self._language, now=now,
        )
        self._pending_draft_id = draft.draft_id
        self._step("intake_prepared")
        return ConversationReply(
            "confirmation_required", self._language, draft.summary,
            selected_id=draft.transaction_id, draft=draft,
        )

    def prepare_handoff(
        self, session: TrustedSession, request: str, *,
        escalation_reason: str = "human_requested", unresolved_questions: tuple[str, ...] = (),
        now: datetime,
    ) -> ConversationReply:
        self._authorize(session, now)
        self._invalidate_action(session, now)
        draft = self._actions.prepare_handoff(
            session, transaction_id=self._selected_id, request=request,
            escalation_reason=escalation_reason, attempted_steps=self._attempted_steps,
            unresolved_questions=unresolved_questions, language=self._language, now=now,
            verified_case_ids=self._verified_case_ids,
        )
        self._pending_draft_id = draft.draft_id
        self._step("handoff_prepared")
        return ConversationReply(
            "confirmation_required", self._language, draft.summary,
            selected_id=draft.transaction_id, draft=draft,
        )

    def confirm(
        self, session: TrustedSession, draft_id: str, *, confirmed: bool, now: datetime,
    ) -> ConversationReply:
        """Reconcile repeat confirmation within the current action context only."""
        self._authorize(session, now)
        if type(confirmed) is not bool:
            raise ConversationError("invalid_confirmation")
        if (
            not isinstance(draft_id, str)
            or draft_id not in (self._pending_draft_id, self._confirmed_draft_id)
        ):
            raise ConversationError("no_pending_action")
        if not confirmed and draft_id == self._confirmed_draft_id:
            raise ConversationError("action_already_verified")
        try:
            receipt = self._actions.confirm(session, draft_id, confirmed=confirmed, now=now)
        except (ActionError, StoreError):
            # A fixed code conveys the failed attempt without claiming whether a
            # write occurred. The action service must reconcile before retrying.
            self._step("confirmation_failed")
            raise
        if confirmed and receipt is None:
            self._step("confirmation_failed")
            raise ConversationError("action_not_verified")
        self._pending_draft_id = None
        if receipt is None:
            self._confirmed_draft_id = None
            self._step("action_cancelled")
            return ConversationReply("cancelled", self._language, TEXT[self._language]["cancelled"])
        self._confirmed_draft_id = draft_id
        if receipt.case_id not in self._verified_case_ids:
            self._verified_case_ids = (*self._verified_case_ids, receipt.case_id)[-MAX_ATTEMPTED_STEPS:]
        self._step("action_verified")
        return ConversationReply(
            "action_verified", self._language, receipt.text,
            selected_id=receipt.transaction_id, receipt=receipt,
        )
