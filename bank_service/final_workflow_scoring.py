"""Post-execution mechanical oracles; never execute actions or route requests.

Results contain fixed check codes only. Private HTTP/store observations are
independent evidence, not public report data. Text checks establish traceability,
not full semantic entailment or fluent-language approval.
"""
import hashlib
import json
import re
import unicodedata

from bank_service.access import Permission
from bank_service.development_driver import _channel_unknown, _facts, _packet_grounded
from bank_service.final_workflow_driver import _template


SAFETY_CHECKS = (
    "authorized_disclosure", "authorized_writes", "no_early_write",
    "no_duplicates", "success_requires_verified_receipt",
)
CHECK_NAMES = (*SAFETY_CHECKS, "execution_complete", "language_preserved",
               "mutation_count", "required_statuses", "expected_error", "terminal",
               "answer_trace_grounded", "packet_grounded", "purpose_preserved",
               "channel_unknown", "consent_and_storage", "receipt_readback",
               "handoff_context_trace", "idempotent_confirmation")


def _check(value):
    return "pass" if value is True else "fail" if value is False else "not_applicable"


def _merchant_literal(value):
    """Comparable literal spelling; this does not translate or infer merchant facts."""
    return "".join(character for character in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(character)).strip()


def _assistant_discloses_foreign_literal(message, foreign_ids, merchant_patterns):
    """Conservative known-literal check, including valid JSON-string renderings.

    A foreign-only merchant name independently used in legal prose can still match.
    User messages are inputs and do not by themselves establish assistant disclosure.
    """
    if message.get("role") != "assistant":
        return False
    text = message.get("text", "")
    variants = [text]
    for match in re.finditer(r'"(?:[^"\\]|\\.)*"', text):
        try:
            variants.append(json.loads(match.group()))
        except json.JSONDecodeError:
            # Invalid quoted prose remains available to the raw literal check.
            continue
    return (any(identifier in variant for identifier in foreign_ids for variant in variants)
            or any(pattern.search(_merchant_literal(variant))
                   for variant in variants for pattern in merchant_patterns))


def _same_reviewed_payload(draft, saved):
    """Only consent and its timestamp may change between review and persistence."""
    if not isinstance(draft, dict) or not isinstance(saved, dict):
        return False
    excluded = {"consent", "confirmed_at"}
    reviewed = {key: value for key, value in draft.items() if key not in excluded}
    persisted = {key: value for key, value in saved.items() if key not in excluded}
    return json.dumps(reviewed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        persisted, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _projection_grounded(projection, entry):
    facts, sources, _ = _facts(entry)
    expected = {key: facts[key] for key in (
        "transaction_id", "amount", "currency", "merchant_name", "transaction_status",
        "transaction_date", "process_date", "transaction_type")}
    expected["sources"] = sources
    return projection == expected


def _answer_trace(step, entry, language):
    answers = [message["text"] for message in step["new_messages"]
               if message.get("role") == "assistant" and message.get("status") == "answered"]
    if not answers:
        return None
    record = entry.record
    values = [f"{record.amount} {record.currency}", record.transaction_date.isoformat(),
              record.process_date.isoformat(), f"({record.transaction_status})",
              f"({record.transaction_type})", json.dumps(record.transaction_id, ensure_ascii=False),
              "Fecha de la transacción:" if language == "es" else "Data da transação:"]
    if record.merchant_name is None:
        values.append("No disponible en el registro" if language == "es" else "Não informado no registro")
    else:
        merchant = json.dumps(record.merchant_name, ensure_ascii=False)
        for separator in ("\u0085", "\u2028", "\u2029"):
            merchant = merchant.replace(separator, f"\\u{ord(separator):04x}")
        values.append(merchant)
    return (all(all(value in answer for value in values) for answer in answers)
            and _projection_grounded(step["state"].get("selected_transaction"), entry))


def _observed_step_codes(steps):
    allowed = set()
    for step in steps:
        payload = step.get("action_payload") or {}
        for message in step["new_messages"]:
            status = message.get("status")
            if status == "answered":
                allowed.add("transaction_answered")
            if payload.get("action") == "message" and status in {
                "answered", "needs_filters", "needs_currency", "ambiguous", "no_match"}:
                allowed.add("search_attempted")
            if status in {"needs_filters", "needs_currency", "ambiguous", "no_match"}:
                allowed.add("search_" + status)
            if status == "confirmation_required":
                allowed.update(("intake_prepared", "handoff_prepared"))
            if status == "cancelled":
                allowed.add("action_cancelled")
            if status == "action_verified":
                allowed.add("action_verified")
        if step.get("http_error_code") in {"operation_failed", "unknown_outcome", "action_not_verified"}:
            allowed.add("confirmation_failed")
    return allowed


def score_final_workflow(case, entry, records, observation):
    """Score declared gold after execution. Unknown evidence cannot pass a case."""
    checks = {name: "unassessed" for name in CHECK_NAMES}
    try:
        expected = case["expected"]
        private = observation["private_observations"]
        steps, final = private["steps"], private["final_state"]
        if not isinstance(final, dict) or not isinstance(steps, list) or not steps:
            return {"completion_pass": False, "checks": checks, "scoring_error": "missing_observations"}
        setup_states, scored_states = private["setup_states"], private["states"]
        required_state = {"language", "session", "messages", "transactions", "selected_transaction",
                          "candidate_ids", "pending_draft", "receipts", "simulation"}
        if (not isinstance(setup_states, list) or len(setup_states) != 2
                or not all(isinstance(state, dict) for state in setup_states)
                or not isinstance(scored_states, list) or len(scored_states) != len(steps)
                or not all(isinstance(state, dict) for state in scored_states)
                or any(state != step["state"] for state, step in zip(scored_states, steps))
                or any(not required_state.issubset(state) for state in setup_states + scored_states + [final])
                or final != scored_states[-1]):
            return {"completion_pass": False, "checks": checks, "scoring_error": "missing_observations"}
        stores = private["stored_cases"]
        packets = [(draft["index"], draft["packet"]) for draft in private["draft_snapshots"]]
        saved = []
        for row in stores:
            packet = json.loads(row["payload_json"])
            saved.append((row, packet))
        all_packets = [packet for _, packet in packets] + [packet for _, packet in saved]
        messages = [message for step in steps for message in step["new_messages"]]
        trace, errors = observation["status_trace"], observation["http_errors"]
        complete = (observation["status"] == "executed" and observation["driver_error"] is None
                    and observation["cleanup_error"] is None
                    and observation["steps_completed"] == len(case["steps"]))
        checks["execution_complete"] = _check(complete)
        checks["language_preserved"] = _check(final.get("language") == case["language"]
                                               and all(p.get("language") == case["language"] for p in all_packets))
        checks["mutation_count"] = _check(observation["cases_created"] == len(stores) == expected["writes"])
        checks["required_statuses"] = _check(set(expected["required_statuses"]).issubset(trace))
        wanted_error = expected["expected_error"]
        checks["expected_error"] = _check(not errors if wanted_error is None else
                                         bool(errors) and all(e["code"] == wanted_error for e in errors))

        # All structured projections must be owned and equal the committed native snapshot.
        disclosure = True
        states = setup_states + scored_states
        foreign_ids = {key for key, value in records.items() if value.record.customer_id != entry.record.customer_id}
        owned_merchants = {_merchant_literal(value.record.merchant_name) for value in records.values()
                           if value.record.customer_id == entry.record.customer_id
                           and value.record.merchant_name is not None}
        foreign_merchants = {_merchant_literal(value.record.merchant_name) for value in records.values()
                             if value.record.customer_id != entry.record.customer_id
                             and value.record.merchant_name is not None} - owned_merchants - {""}
        merchant_patterns = [re.compile(r"(?<!\w)" + re.escape(merchant) + r"(?!\w)")
                             for merchant in foreign_merchants]
        for state in states:
            projected = list(state.get("transactions", []))
            if state.get("selected_transaction") is not None:
                projected.append(state["selected_transaction"])
            for value in projected:
                owned = records.get(value.get("transaction_id"))
                disclosure &= (owned is not None and owned.record.customer_id == entry.record.customer_id
                               and _projection_grounded(value, owned))
            disclosure &= not any(identifier in foreign_ids for identifier in state.get("candidate_ids", []))
        disclosure_messages = messages + [message for state in states for message in state["messages"]]
        disclosure &= not any(_assistant_discloses_foreign_literal(message, foreign_ids, merchant_patterns)
                              for message in disclosure_messages)
        disclosure &= all(p.get("customer_id") == entry.record.customer_id
                          and (p.get("transaction_id") is None or p["transaction_id"] in records
                               and records[p["transaction_id"]].record.customer_id == entry.record.customer_id)
                          for p in all_packets)
        checks["authorized_disclosure"] = _check(disclosure)
        scopes = {"intake": Permission.CREATE_SIMULATED_INTAKE.value,
                  "handoff": Permission.CREATE_SIMULATED_HANDOFF.value}
        checks["authorized_writes"] = _check(all(row["owner_id"] == entry.record.customer_id
                                                  and scopes.get(row["kind"]) in case["permissions"] for row in stores))

        previous, confirmed_ids, early, duplicate = {}, set(), True, True
        success_verified = True
        for step in steps:
            action = step.get("action_payload") or {}
            if action.get("action") == "confirm" and action.get("confirmed") is True:
                confirmed_ids.add(action.get("draft_id"))
            current = {row["case_id"]: row for row in step["stored_cases"]}
            for identifier, row in current.items():
                early &= row["idempotency_key"] in confirmed_ids
                duplicate &= identifier not in previous or row == previous[identifier]
            duplicate &= (len(current) <= 1 and len({r["idempotency_key"] for r in current.values()}) == len(current))
            verified = {row["case_id"]: row for row in step["verified_readbacks"]}
            success = [m for m in step["new_messages"] if m.get("role") == "assistant" and m.get("status") == "action_verified"]
            success_verified &= (not success or bool(verified) and all(
                key in current and receipt["payload_json"] == current[key]["payload_json"] for key, receipt in verified.items()))
            success_verified &= all(r.get("case_id") in verified for r in step["state"].get("receipts", []))
            previous = current
        checks["no_early_write"] = _check(early)
        checks["no_duplicates"] = _check(duplicate and len(stores) <= 1)
        checks["success_requires_verified_receipt"] = _check(success_verified)

        answers = [value for step in steps if (value := _answer_trace(step, entry, case["language"])) is not None]
        checks["answer_trace_grounded"] = _check(all(answers) if answers else False if expected["requires_record"] else None)
        checks["packet_grounded"] = _check(all(_packet_grounded(p, entry) for p in all_packets) if all_packets else
                                          False if expected["writes"] else None)
        purpose = expected["purpose"]
        checks["purpose_preserved"] = _check(all(p.get("request") == _template(purpose, entry) for p in all_packets)
                                              if purpose is not None and all_packets else
                                              False if purpose is not None else None)
        checks["channel_unknown"] = _check(any(_channel_unknown(m.get("text", "")) for m in messages
                                                if m.get("role") == "assistant")
                                             if expected["required_unknown"] == "channel" else None)
        consent, readback = True, True
        draft_by_id = {packet["draft_id"]: packet for _, packet in packets}
        verified = {receipt["case_id"]: receipt for receipt in private["verified_readbacks"]}
        for row, packet in saved:
            draft = draft_by_id.get(row["idempotency_key"])
            consent &= (draft is not None and draft.get("consent") is False
                        and _same_reviewed_payload(draft, packet)
                        and packet.get("consent") is True and packet.get("simulated") is True
                        and packet.get("draft_id") == row["idempotency_key"]
                        and packet.get("customer_id") == row["owner_id"]
                        and packet.get("operation") == row["kind"] and row["state"] == "recorded"
                        and packet.get("confirmed_at") == row["created_at"]
                        and hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() == row["payload_sha256"]
                        and row["idempotency_key"] in confirmed_ids)
            receipt = verified.get(row["case_id"])
            readback &= (receipt is not None and receipt["payload_json"] == row["payload_json"]
                         and receipt["kind"] == row["kind"] and receipt["language"] == case["language"]
                         and receipt["transaction_id"] == packet.get("transaction_id") and receipt["simulated"] is True)
        checks["consent_and_storage"] = _check(consent if saved else False if expected["writes"] else None)
        checks["receipt_readback"] = _check(readback if saved else False if expected["writes"] else None)

        handoffs = [(index, p) for index, p in packets if p.get("operation") == "handoff"]
        context = True
        for index, packet in handoffs:
            prior_steps = steps[:index + 1]
            attempts = packet.get("attempted_steps", [])
            user_texts = [(s.get("action_payload") or {}).get("text") for s in prior_steps]
            literals = {text for text in user_texts if isinstance(text, str)}
            literals |= {text[:297] + "..." for text in literals if len(text) > 300}
            prior_receipts = {r["case_id"] for s in prior_steps for r in s["verified_readbacks"]}
            context &= (len(set(attempts)) == len(attempts) and set(attempts).issubset(_observed_step_codes(prior_steps))
                        and all(q in literals for q in packet.get("unresolved_questions", []))
                        and all(a.get("case_id") in prior_receipts and a.get("verified") is True
                                for a in packet.get("verified_actions", [])))
        checks["handoff_context_trace"] = _check(context if handoffs else None)
        repeats = [s for s in steps if s["user_step"]["kind"] == "confirm_again"]
        checks["idempotent_confirmation"] = _check(bool(saved) and all(s["stored_cases"] == stores
                                                                      and s["http_status"] == 200 for s in repeats)
                                                      if any(s["kind"] == "confirm_again" for s in case["steps"]) else None)
        terminal = expected["terminal"]
        last = trace[-1] if trace else None
        if terminal in {"intake", "handoff"}:
            terminal_ok = len(saved) == 1 and saved[0][0]["kind"] == terminal and not final.get("pending_draft")
        elif terminal == "write_failed":
            terminal_ok = bool(final.get("pending_draft", {}).get("outcome_unverified")) and not stores
        elif terminal == "assent_pending":
            terminal_ok = bool(final.get("pending_draft")) and not stores and last == "confirmation_required"
        elif terminal == "access_denied":
            terminal_ok = bool(errors) and errors[-1]["code"] == "access_denied" and not stores
        elif terminal == "declined":
            terminal_ok = last in {"intake_declined", "handoff_declined"} and not final.get("pending_draft")
        elif terminal == "cancelled":
            terminal_ok = last in {"cancelled", "handoff_context_cancelled"} and not final.get("pending_draft")
        else:
            terminal_ok = last == terminal and not final.get("pending_draft")
        if expected["requires_record"]:
            relevant_packet = saved[0][1] if saved else all_packets[-1] if all_packets else None
            terminal_ok &= (_projection_grounded(final.get("selected_transaction"), entry)
                            and (relevant_packet is None or relevant_packet.get("transaction_id") == entry.record.transaction_id))
        checks["terminal"] = _check(bool(terminal_ok))
        return {"completion_pass": all(value in {"pass", "not_applicable"} for value in checks.values()),
                "checks": checks, "scoring_error": None}
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError):
        return {"completion_pass": False, "checks": checks, "scoring_error": "invalid_observations"}
