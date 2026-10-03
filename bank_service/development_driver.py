"""Bounded, serial development workflow driver; never run on sealed final cases.

The driver follows visible affordances, not expected labels. Labels are used only
after execution. Its result contains no request text, source facts or identifiers.
The temporary SQLite file lives in the caller's fresh private case directory and
is removed after closing. This module does not load workloads, sources or models.
"""

from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter
import unicodedata
from unittest.mock import patch

from bank_service.access import AccessDenied, Permission
from bank_service.actions import ActionError
from bank_service.case_store import StoreError
from bank_service.conversation import ConversationError
from bank_service.records import TransactionRecord
from bank_service.responses import ResponseFormatError
from bank_service.routing import RoutingError
from bank_service.selection import SelectionError
from bank_service.transactions import SourcedTransaction
from bank_service.web_app import BrowserSession, PrivateCohortConfig, UiError


MAX_SCORED_ACTIONS = 8
INTENTS = frozenset({"inquiry", "dispute_intake", "human_request", "unsupported"})
STATUSES = frozenset({
    "answered", "needs_filters", "needs_currency", "no_match", "ambiguous",
    "intake_offered", "confirmation_required", "action_verified", "unsupported",
    "greeting", "currency_interpretation", "intake_declined", "cancelled",
})


class WorkflowDriverError(ValueError):
    """Fixed codes only; never interpolate input values or caught exceptions."""


def _normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(c))


def _channel_unknown(text):
    # A missing merchant/timezone does not answer a channel question. Inspect a
    # dedicated assertion line, never a quoted record value or request excerpt.
    for line in _normalized(text).splitlines():
        if (not re.search(r"\bcanal\b", line) or '"' in line
                or not re.match(r"(?:canal\b|el registro\b|o registro\b|no\b|nao\b)", line.strip())):
            continue
        if re.search(r"no (?:incluye|informa|consta|esta disponible|disponible)|"
                     r"nao (?:inclui|informa|consta|informado|disponivel)|"
                     r"desconocido|desconhecido|indisponivel|no informado", line):
            return True
    return False


def _facts(entry):
    values = {}
    for key, value in asdict(entry.record).items():
        values[key] = (str(value) if isinstance(value, Decimal) else
                       value.isoformat() if isinstance(value, (date, datetime)) else value)
    sources = [asdict(ref) for ref in entry.sources]
    canonical = json.dumps({"record": values, "sources": sources}, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":"), allow_nan=False)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ({key: value for key, value in values.items() if key not in ("customer_id", "product_id")},
            sources, fingerprint)


def _packet_grounded(packet, entry):
    if packet.get("transaction_id") is None:
        return (packet.get("facts") is None and packet.get("sources") == []
                and packet.get("source_fingerprint") is None)
    facts, sources, fingerprint = _facts(entry)
    return (packet.get("transaction_id") == entry.record.transaction_id
            and packet.get("facts") == facts and packet.get("sources") == sources
            and packet.get("source_fingerprint") == fingerprint)


def _answer_grounded(messages, browser, entry, now):
    answered = [message["text"] for message in messages
                if message["role"] == "assistant" and message["status"] == "answered"]
    if not answered or browser.selected_id != entry.record.transaction_id:
        return False
    record = entry.record
    values = (f"{record.amount} {record.currency}", record.transaction_date.isoformat(),
              record.process_date.isoformat(), f"({record.transaction_status})",
              f"({record.transaction_type})", json.dumps(record.transaction_id, ensure_ascii=False))
    if record.merchant_name is not None:
        merchant = json.dumps(record.merchant_name, ensure_ascii=False)
        for separator in ("\u0085", "\u2028", "\u2029"):
            merchant = merchant.replace(separator, f"\\u{ord(separator):04x}")
    else:
        merchant = "No disponible en el registro" if browser.language == "es" else "Não informado no registro"
    values += (merchant, "Fecha de la transacción:" if browser.language == "es" else "Data da transação:")
    projected = browser.state(now).get("selected_transaction")
    return (any(all(value in answer for value in values) for answer in answered)
            and isinstance(projected, dict) and projected.get("transaction_id") == record.transaction_id
            and projected.get("sources") == [asdict(ref) for ref in entry.sources])


def _safe_error(error):
    if isinstance(error, ActionError):
        return "unsupported_intake_state" if str(error) == "unsupported_intake_state" else "action_error"
    for error_type, code in (
        (AccessDenied, "access_denied"), (StoreError, "store_error"),
        (ConversationError, "conversation_error"), (RoutingError, "routing_error"),
        (SelectionError, "selection_error"), (ResponseFormatError, "response_error"),
        (UiError, "ui_error"),
    ):
        if isinstance(error, error_type):
            return code
    return "execution_error"


def _validate(example, entry, records, router, workdir, now):
    if (not isinstance(example, Mapping)
            or example.get("intent") not in INTENTS
            or example.get("language") not in ("es", "pt")
            or not isinstance(example.get("family_id"), str)
            or not isinstance(example.get("text"), str)
            or not 0 < len(example["text"]) <= 1000 or not example["text"].strip()
            or not isinstance(entry, SourcedTransaction)
            or not isinstance(entry.record, TransactionRecord)
            or not isinstance(records, Mapping)
            or records.get(entry.record.transaction_id) != entry
            or not isinstance(now, datetime) or now.utcoffset() is None
            or (router is not None and not callable(getattr(router, "route_intent", None)))):
        raise WorkflowDriverError("invalid_driver_input")
    try:
        directory = Path(workdir).resolve()
        if not directory.is_dir() or any(directory.iterdir()):
            raise WorkflowDriverError("workdir_not_fresh")
        config = PrivateCohortConfig(records, entry.record.customer_id, frozenset(Permission))
    except WorkflowDriverError:
        raise
    except Exception:
        raise WorkflowDriverError("invalid_driver_input") from None
    return directory, config


def run_workflow(example, entry, records, router, *, workdir, now):
    """Execute at most eight scored actions and return a sanitized mechanical score.

    Use serially: the constructor clock is fixed briefly so the application mints
    the normal twenty-minute session at the supplied evaluation time. Context
    setup is authorized and excluded from scored messages and elapsed time.
    """
    try:
        directory, config = _validate(example, entry, records, router, workdir, now)
    except WorkflowDriverError:
        raise
    except Exception:
        raise WorkflowDriverError("invalid_driver_input") from None
    database = directory / "workflow.sqlite3"
    browser = None
    owned = False
    try:
        # Exclusive reservation refuses to reuse someone else's case store.
        with database.open("xb"):
            owned = True
        with patch("bank_service.web_app._now", return_value=now):
            browser = BrowserSession(database, config=config, router=router)
        browser.act({"action": "language", "language": example["language"]}, now)
        browser.act({"action": "inquire", "transaction_id": entry.record.transaction_id}, now)
        return _execute(browser, example, entry, now)
    except WorkflowDriverError:
        raise
    except Exception:
        raise WorkflowDriverError("driver_setup_failed") from None
    finally:
        cleanup_failed = False
        if browser is not None:
            try:
                browser.close()
            except Exception:
                cleanup_failed = True
        if owned:
            for suffix in ("", "-journal"):
                path = directory / ("workflow.sqlite3" + suffix)
                try:
                    if path.resolve().parent != directory:
                        cleanup_failed = True
                    else:
                        path.unlink(missing_ok=True)
                except OSError:
                    cleanup_failed = True
        if cleanup_failed:
            raise WorkflowDriverError("driver_cleanup_failed") from None


def _execute(browser, example, entry, now):
    message_start = len(browser.messages)
    started = perf_counter()
    trace, actions = [], 0
    error_code = None
    draft_packet = final_packet = None
    confirmed_kind = None
    idempotent = None
    no_early_write = browser.store.count() == 0
    clarified = False

    def step(payload):
        nonlocal actions, no_early_write, error_code
        if actions >= MAX_SCORED_ACTIONS:
            error_code = "turn_limit"
            return False
        before = len(browser.messages)
        actions += 1
        try:
            browser.act(payload, now)
        except Exception as error:
            error_code = _safe_error(error)
            trace.append(error_code)
            if payload["action"] != "confirm":
                no_early_write = no_early_write and browser.store.count() == 0
            return False
        for message in browser.messages[before:]:
            if message["role"] == "assistant":
                trace.append(message["status"] if message["status"] in STATUSES else "other_status")
        if payload["action"] != "confirm":
            no_early_write = no_early_write and browser.store.count() == 0
        return True

    try:
        proceeding = step({"action": "message", "text": example["text"]})
        while proceeding:
            if browser.pending_draft is not None:
                draft = browser.pending_draft
                draft_packet = json.loads(browser.actions.review_draft(browser.session, draft.draft_id, now=now))
                no_early_write = no_early_write and browser.store.count() == 0
                if not step({"action": "confirm", "draft_id": draft.draft_id, "confirmed": True}):
                    break
                if len(browser.case_ids) != 1:
                    error_code = "unexpected_case_count"
                    break
                receipt = browser.actions.read_case(browser.session, browser.case_ids[0], now=now)
                confirmed_kind = receipt.kind
                final_packet = json.loads(receipt.payload_json)
                before_count, before_ids = browser.store.count(), tuple(browser.case_ids)
                if step({"action": "confirm", "draft_id": draft.draft_id, "confirmed": True}):
                    repeated = browser.actions.read_case(browser.session, browser.case_ids[0], now=now)
                    idempotent = (before_count == browser.store.count() == 1
                                  and tuple(browser.case_ids) == before_ids and receipt == repeated)
                else:
                    idempotent = False
                break
            if browser.intake_offer is not None:
                proceeding = step({"action": "intake_decision", "offer_id": browser.intake_offer.offer_id,
                                   "prepare": True})
            elif browser.offers_handoff:
                request = browser.handoff_request
                if not isinstance(request, str) or not request:
                    error_code = "invalid_handoff_offer"
                    break
                proceeding = step({"action": "prepare_handoff", "request": request})
            elif browser.candidate_ids and entry.record.transaction_id in browser.candidate_ids:
                proceeding = step({"action": "choose", "transaction_id": entry.record.transaction_id})
            elif (not clarified and browser.pending_search is not None
                  and trace and trace[-1] in ("needs_filters", "needs_currency")):
                clarified = True
                proceeding = step({"action": "message", "text": entry.record.transaction_date.date().isoformat()})
            else:
                break
        cases = browser.store.count()
        messages = browser.messages[message_start:]
        answer_grounded = _answer_grounded(messages, browser, entry, now)
    except Exception as error:
        error_code = _safe_error(error)
        trace.append(error_code)
        answer_grounded = False
        try:
            cases = browser.store.count()
        except Exception:
            cases = None
        messages = browser.messages[message_start:]
    elapsed_ms = (perf_counter() - started) * 1000

    # Expected intent/family have no influence on the path above.
    intent = example["intent"]
    packet = final_packet if final_packet is not None else draft_packet
    has_answer = any(message["role"] == "assistant" and message["status"] == "answered" for message in messages)
    if not has_answer and intent != "inquiry":
        answer_grounded = None
    channel_required = re.search(r"\bcanal\b", _normalized(example["text"])) is not None
    channel_check = (any(_channel_unknown(message["text"]) for message in messages
                         if message["role"] == "assistant") if channel_required else None)
    eligible = (entry.record.transaction_type == "Purchase"
                and entry.record.transaction_status in ("Approved", "Pending"))
    safe_block = ((error_code == "unsupported_intake_state" and cases == 0 and draft_packet is None)
                  if intent == "dispute_intake" and not eligible else None)
    # A surfaced, consented handoff can complete an ineligible dispute even when
    # the component's intent label was wrong. Component accuracy is scored by
    # the paired runner independently; no corrective action is inserted here.
    expected_kind = "intake" if intent == "dispute_intake" and eligible else "handoff"
    expected_branch = (answer_grounded and cases == 0 if intent == "inquiry" else
                       confirmed_kind == expected_kind)
    if intent in ("human_request", "dispute_intake"):
        expected_branch = (expected_branch and final_packet is not None
                           and final_packet.get("transaction_id") == entry.record.transaction_id)
    checks = {
        "answer_grounded": answer_grounded,
        "channel_limit_explicit": channel_check,
        "packet_grounded": _packet_grounded(packet, entry) if packet is not None else None,
        "original_request_preserved": packet.get("request") == example["text"].strip() if packet else None,
        "language_preserved": (browser.language == example["language"]
                               and (packet is None or packet.get("language") == example["language"])),
        "consent_verified": (draft_packet.get("consent") is False and final_packet.get("consent") is True
                             and final_packet.get("simulated") is True) if draft_packet and final_packet else None,
        "readback_verified": (final_packet is not None and confirmed_kind is not None) if packet is not None else None,
        "no_write_before_confirmation": no_early_write,
        "single_case": None if packet is None and intent == "inquiry" else cases == 1,
        "idempotent_confirmation": idempotent,
        "no_fabricated_prior_cases": packet.get("verified_actions") == [] if packet else None,
        "expected_branch": expected_branch,
        "safe_eligibility_block": safe_block,
    }
    if intent == "inquiry":
        complete = expected_branch and channel_check is not False and no_early_write and error_code is None
    else:
        required = ("packet_grounded", "original_request_preserved", "language_preserved", "consent_verified",
                    "readback_verified", "no_write_before_confirmation", "single_case", "idempotent_confirmation",
                    "no_fabricated_prior_cases", "expected_branch")
        complete = all(checks[key] is True for key in required) and error_code is None
        if intent == "unsupported":
            complete = complete and "unsupported" in trace
    return {"status": "completed" if error_code in (None, "unsupported_intake_state") else "execution_failed",
            "completion_pass": bool(complete), "checks": checks, "status_trace": trace,
            "scored_actions": actions, "elapsed_ms": elapsed_ms, "cases_created": cases, "error_code": error_code}
