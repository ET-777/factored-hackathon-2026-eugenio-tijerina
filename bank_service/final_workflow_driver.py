"""Serial HTTP journey execution on a fresh, disposable loopback demo server.

This module loads no workloads, sources or models and does not score expected
labels. Callers must retain private observations only in ignored owner-local
outputs. Only declared actions execute; missing affordances never cause fallback.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
import json
from string import Formatter
from threading import Thread
from time import perf_counter
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from bank_service.access import Permission
from bank_service.case_store import StoreError
from bank_service.transactions import SourcedTransaction
from bank_service.web_app import DemoServer, PrivateCohortConfig


MAX_STEPS = 16
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
STEP_KEYS = {
    "message": {"kind", "text"}, "select_target": {"kind"}, "select_foreign": {"kind"},
    "respond_offer": {"kind", "prepare"}, "confirm": {"kind", "confirmed"},
    "confirm_again": {"kind"}, "cancel": {"kind"},
    "advance_clock": {"kind", "seconds"}, "set_fault": {"kind", "name"},
}
SAFE_STATUSES = frozenset({
    "greeting", "language_changed", "answered", "needs_filters", "needs_currency", "no_match",
    "ambiguous", "currency_interpretation", "date_interpreted", "intake_offered", "intake_declined",
    "intake_ineligible", "handoff_offered", "handoff_declined", "handoff_unavailable",
    "needs_handoff_context", "handoff_context_cancelled", "needs_request", "case_unverified",
    "session_case_receipts", "confirmation_required", "action_verified", "cancelled",
    "unsupported", "access_denied",
})
SAFE_HTTP_ERRORS = frozenset({
    "access_denied", "unknown_outcome", "action_not_verified", "already_confirmed", "action_already_verified",
    "stale_draft", "draft_expired", "draft_not_active", "no_pending_action", "stale_offer",
    "selection_changed", "transaction_required", "invalid_date", "ambiguous_date", "invalid_amount",
    "ambiguous_amount", "unsupported_currency", "ambiguous_currency", "stale_handoff_context",
    "unsupported_intake_state", "invalid_choice", "invalid_intent_proposal", "operation_failed",
    "csrf_rejected", "invalid_origin", "invalid_host", "session_required", "rate_limited", "session_capacity",
})


class FinalWorkflowDriverError(ValueError):
    """Only fixed codes; never expose request, record or exception contents."""


def _require(condition, code):
    if not condition:
        raise FinalWorkflowDriverError(code)


def _template(text, entry):
    _require(isinstance(text, str) and bool(text.strip()) and len(text) <= 1000, "invalid_message_template")
    record = entry.record
    values = {"transaction_id": record.transaction_id,
              "date_iso": record.transaction_date.date().isoformat(),
              "date_dmy": record.transaction_date.strftime("%d/%m/%Y"),
              "amount": str(record.amount), "currency": record.currency}
    try:
        for _, name, specification, conversion in Formatter().parse(text):
            _require(name is None or (name in values and not specification and conversion is None),
                     "invalid_message_template")
        result = text.format_map(values)
        _require(bool(result.strip()) and len(result) <= 1000, "invalid_message_template")
        result.encode("utf-8")
        return result
    except (ValueError, KeyError, UnicodeError):
        raise FinalWorkflowDriverError("invalid_message_template") from None


def _validate(case, entry, records, router, foreign_entry, now):
    _require(isinstance(case, Mapping) and case.get("language") in ("es", "pt")
             and isinstance(entry, SourcedTransaction) and isinstance(records, Mapping)
             and records.get(entry.record.transaction_id) == entry
             and isinstance(now, datetime) and now.utcoffset() is not None
             and (router is None or callable(getattr(router, "route_intent", None))), "invalid_driver_input")
    _require(foreign_entry is None or (isinstance(foreign_entry, SourcedTransaction)
             and records.get(foreign_entry.record.transaction_id) == foreign_entry
             and foreign_entry.record.customer_id != entry.record.customer_id), "invalid_driver_input")
    permissions = case.get("permissions")
    _require(isinstance(permissions, list) and len(permissions) == len(set(permissions))
             and all(isinstance(value, str) and value in {permission.value for permission in Permission}
                     for value in permissions), "invalid_driver_permissions")
    steps = case.get("steps")
    _require(isinstance(steps, list) and 0 < len(steps) <= MAX_STEPS, "invalid_driver_steps")
    for step in steps:
        _require(isinstance(step, dict) and isinstance(step.get("kind"), str)
                 and step["kind"] in STEP_KEYS and set(step) == STEP_KEYS[step["kind"]], "invalid_driver_step")
        kind = step["kind"]
        if kind == "message":
            _template(step["text"], entry)
        elif kind in ("respond_offer", "confirm"):
            _require(type(step["prepare" if kind == "respond_offer" else "confirmed"]) is bool, "invalid_driver_step")
        elif kind == "advance_clock":
            _require(type(step["seconds"]) is int and 1 <= step["seconds"] <= 1800, "invalid_driver_step")
        elif kind == "set_fault":
            _require(step["name"] == "write_failure", "invalid_driver_fault")
    return PrivateCohortConfig(records, entry.record.customer_id,
                               frozenset(Permission(value) for value in permissions))


def _private_state(state):
    result = deepcopy(state)
    result.pop("csrf_token", None)
    return result


def _new_messages(previous, current):
    for overlap in range(min(len(previous), len(current)), 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:]
    return current


def _browser(server):
    _require(len(server._sessions) == 1, "unexpected_session_population")
    return next(iter(server._sessions.values()))


def _store_snapshot(server):
    """Read only this fresh server's disposable store, independent of receipts."""
    browser = _browser(server)
    with browser.lock, browser.store._lock:
        browser.store._require_open()
        rows = [dict(row) for row in browser.store._connection.execute(
            "SELECT * FROM cases ORDER BY case_id").fetchall()]
    return rows


def _action_readbacks(server, state, now):
    browser = _browser(server)
    draft_packet, draft_id, readbacks = None, None, []
    with browser.lock:
        pending = state.get("pending_draft")
        if isinstance(pending, dict):
            draft_id = pending.get("draft_id")
            draft_packet = json.loads(browser.actions.review_draft(browser.session, draft_id, now=now))
        for receipt in state.get("receipts", []):
            readbacks.append(asdict(browser.actions.read_case(browser.session, receipt["case_id"], now=now)))
    return draft_id, draft_packet, readbacks


def run_final_workflow(case, entry, records, router=None, *, foreign_entry=None, now):
    """Execute declared steps through the actual HTTP API; do not inspect gold.

    The clock patch is process-global: callers must execute cases serially.
    ``expected``, intent, stratum and component_text are never execution inputs.
    HTTP errors are observed outcomes; the separate scorer decides whether they
    are expected safe denials/fault handling or failed service. Driver errors
    and cleanup failures are retained explicitly.
    """
    result = {"status": "execution_failed", "driver_error": None, "cleanup_error": None,
              "status_trace": [], "http_errors": [], "http_requests": 0, "steps_completed": 0,
              "handler_errors": 0,
              "declared_steps": len(case.get("steps", [])) if isinstance(case, Mapping) and isinstance(case.get("steps"), list) else None,
              "cases_created": None, "elapsed_seconds": None, "setup_seconds": None,
              "private_observations": {"setup_states": [], "steps": [], "final_state": None, "stored_cases": [],
                                       "states": [], "messages": [], "draft_snapshots": [], "verified_readbacks": []}}
    server = thread = None
    clock = [now]
    stack = ExitStack()
    started = scored_start = None
    try:
        config = _validate(case, entry, records, router, foreign_entry, now)
        stack.enter_context(patch("bank_service.web_app._now", side_effect=lambda: clock[0]))
        started = perf_counter()
        server = DemoServer(0, config=config, router=router)
        # BaseServer's default prints raw exception text. Suppress that logging
        # only on this disposable server; retain the unexpected handler fault.
        def handle_error(_request, _client_address):
            result["handler_errors"] += 1
        server.handle_error = handle_error
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        state = {}
        previous_messages = []
        literal_messages, last_draft_id = [], None

        def request(payload=None):
            nonlocal state, previous_messages
            url = origin + ("/api/state" if payload is None else "/api/action")
            headers = {"Origin": origin, "Sec-Fetch-Site": "same-origin"}
            body = None
            if payload is not None:
                payload = {**payload, "csrf_token": state.get("csrf_token")}
                body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                headers["Content-Type"] = "application/json"
            result["http_requests"] += 1
            try:
                response = opener.open(Request(url, data=body, headers=headers), timeout=5)
            except HTTPError as response_error:
                response = response_error
            with response:
                status = response.code
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            _require(len(raw) <= MAX_RESPONSE_BYTES, "http_response_too_large")
            try:
                observed = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError):
                raise FinalWorkflowDriverError("invalid_http_response") from None
            _require(isinstance(observed, dict), "invalid_http_response")
            # Keep the last CSRF token on error responses that contain no state.
            if "csrf_token" not in observed and "csrf_token" in state:
                observed["csrf_token"] = state["csrf_token"]
            state = observed
            messages = state.get("messages", [])
            _require(isinstance(messages, list), "invalid_http_response")
            added = _new_messages(previous_messages, messages)
            previous_messages = deepcopy(messages)
            code = None
            if status >= 400:
                raw_code = state.get("error", {}).get("code") if isinstance(state.get("error"), dict) else None
                code = raw_code if isinstance(raw_code, str) and raw_code in SAFE_HTTP_ERRORS else "http_action_error"
                result["http_errors"].append({"status": status, "code": code})
            return status, added, code

        for setup_payload in (None, {"action": "language", "language": case["language"]}):
            status, _, _ = request(setup_payload)
            _require(status == 200, "http_setup_failed")
            result["private_observations"]["setup_states"].append(_private_state(state))
        result["setup_seconds"] = perf_counter() - started
        result["private_observations"]["messages"] = deepcopy(state.get("messages", []))
        scored_start = perf_counter()
        for index, step in enumerate(case["steps"]):
            kind, payload = step["kind"], None
            if kind == "message":
                text = _template(step["text"], entry)
                literal_messages.append(text.strip())
                payload = {"action": "message", "text": text}
            elif kind == "select_target":
                identifier = entry.record.transaction_id
                candidates = state.get("candidate_ids", [])
                if candidates:
                    _require(identifier in candidates, "unavailable_affordance")
                    payload = {"action": "choose", "transaction_id": identifier}
                else:
                    _require(any(isinstance(record, dict) and record.get("transaction_id") == identifier
                                 for record in state.get("transactions", [])), "unavailable_affordance")
                    payload = {"action": "inquire", "transaction_id": identifier}
            elif kind == "select_foreign":
                _require(foreign_entry is not None, "foreign_record_unavailable")
                payload = {"action": "inquire", "transaction_id": foreign_entry.record.transaction_id}
            elif kind == "respond_offer":
                prepare = step["prepare"]
                if isinstance(state.get("intake_offer"), dict):
                    payload = {"action": "intake_decision", "offer_id": state["intake_offer"]["offer_id"], "prepare": prepare}
                elif isinstance(state.get("handoff_offer"), dict):
                    payload = {"action": "handoff_decision", "offer_id": state["handoff_offer"]["offer_id"], "prepare": prepare}
                elif state.get("offers_handoff") is True and prepare is True:
                    request_text = state.get("handoff_request")
                    _require(isinstance(request_text, str) and request_text.strip() in literal_messages, "unavailable_affordance")
                    payload = {"action": "prepare_handoff", "request": request_text}
                else:
                    raise FinalWorkflowDriverError("unavailable_affordance")
            elif kind in ("confirm", "cancel"):
                draft = state.get("pending_draft")
                _require(isinstance(draft, dict) and isinstance(draft.get("draft_id"), str), "unavailable_affordance")
                last_draft_id = draft["draft_id"]
                payload = {"action": "cancel", "draft_id": last_draft_id} if kind == "cancel" else {
                    "action": "confirm", "draft_id": last_draft_id, "confirmed": step["confirmed"]}
            elif kind == "confirm_again":
                _require(last_draft_id is not None, "unavailable_affordance")
                payload = {"action": "confirm", "draft_id": last_draft_id, "confirmed": True}
            elif kind == "advance_clock":
                clock[0] += timedelta(seconds=step["seconds"])
            elif kind == "set_fault":
                stack.enter_context(patch.object(_browser(server).store, "write_case",
                                                 side_effect=StoreError("simulated_write_failure")))
            status, added, code = request(payload)
            for message in added:
                if isinstance(message, dict) and message.get("role") == "assistant":
                    status_code = message.get("status")
                    result["status_trace"].append(status_code if status_code in SAFE_STATUSES else "other_status")
            stored = _store_snapshot(server)
            draft_id, draft_packet, readbacks = _action_readbacks(server, state, clock[0])
            result["cases_created"] = len(stored)
            result["private_observations"]["steps"].append({
                "index": index, "user_step": deepcopy(step), "action_payload": deepcopy(payload),
                "http_status": status, "http_error_code": code, "new_messages": deepcopy(added),
                "state": _private_state(state), "stored_cases": stored,
                "draft_id": draft_id, "draft_packet": draft_packet, "verified_readbacks": readbacks,
                "clock": clock[0].isoformat()})
            result["private_observations"]["states"].append(_private_state(state))
            result["private_observations"]["messages"].extend(deepcopy(added))
            if draft_packet is not None:
                result["private_observations"]["draft_snapshots"].append({
                    "index": index, "draft_id": draft_id, "packet": draft_packet})
            result["private_observations"]["verified_readbacks"].extend(readbacks)
            result["steps_completed"] += 1
        result["status"] = "executed"
    except FinalWorkflowDriverError as error:
        result["driver_error"] = str(error)
    except Exception:
        result["driver_error"] = "workflow_execution_failed"
    finally:
        if scored_start is not None:
            result["elapsed_seconds"] = perf_counter() - scored_start
        if result["handler_errors"]:
            result["driver_error"] = result["driver_error"] or "http_handler_execution_failed"
            result["status"] = "execution_failed"
        if server is not None:
            try:
                if server._sessions:
                    result["private_observations"]["stored_cases"] = _store_snapshot(server)
                    result["cases_created"] = len(result["private_observations"]["stored_cases"])
                if "state" in locals():
                    result["private_observations"]["final_state"] = _private_state(state)
            except Exception:
                result["driver_error"] = result["driver_error"] or "observation_readback_failed"
                result["status"] = "execution_failed"
            try:
                if thread is not None and thread.is_alive():
                    server.shutdown()
                    thread.join(timeout=5)
                    _require(not thread.is_alive(), "server_cleanup_failed")
                server.server_close()
            except Exception:
                result["cleanup_error"] = "server_cleanup_failed"
                result["status"] = "execution_failed"
        try:
            stack.close()
        except Exception:
            result["cleanup_error"] = "patch_cleanup_failed"
            result["status"] = "execution_failed"
    return result
