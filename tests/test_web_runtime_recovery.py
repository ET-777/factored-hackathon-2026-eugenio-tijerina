"""Invented inputs and clocks reproduce encoding and session lifecycle faults."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

from bank_service.access import AccessDenied
from bank_service.actions import ActionError
from bank_service.case_store import StoreError
from bank_service.web_app import (
    DemoServer, MAX_SESSIONS, MAX_SESSION_MINTS_PER_MINUTE, UiError, _text,
)


START = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)


class RuntimeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch("bank_service.web_app._now", return_value=START)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.ticks = patch("bank_service.web_app.time.monotonic", return_value=1000.0)
        self.monotonic = self.ticks.start()
        self.addCleanup(self.ticks.stop)
        self.server = DemoServer(0)
        self.addCleanup(self.server.server_close)

    def database(self, token):
        return Path(self.server._temporary.name) / f"{token}.sqlite3"

    def test_strict_text_rejects_surrogates_and_preserves_bilingual_unicode(self):
        self.assertEqual(_text("  Olá, revisão; transacción 😀  "), "Olá, revisão; transacción 😀")
        for malformed in ("\ud800", "hello\udfff", "\ud83d\ude00"):
            with self.subTest(input_kind=repr(malformed)):
                with self.assertRaisesRegex(UiError, "^invalid_input$"):
                    _text(malformed)

    def test_direct_message_rejects_before_append_and_state_remains_utf8(self):
        _, browser = self.server.mint_session()
        before = browser.state(START)
        with self.assertRaisesRegex(UiError, "^invalid_input$"):
            browser.message("\ud800", START)
        self.assertEqual(browser.state(START), before)
        json.dumps(browser.state(START), ensure_ascii=False).encode("utf-8")
        browser.message("Hola", START)
        self.assertEqual(browser.messages[-1]["status"], "greeting")

    def test_action_rejects_all_string_fields_before_context_or_rate_mutation(self):
        _, browser = self.server.mint_session()
        browser.message("Quiero hablar con una persona", START)
        self.assertIsNotNone(browser.pending_handoff_context)
        context = browser.pending_handoff_context
        before = browser.state(START)
        for payload in (
            {"action": "prepare_intake", "reason": "\ud800"},
            {"action": "prepare_handoff", "request": "Ayuda", "unresolved_questions": ["\udfff"]},
            {"action": "inquire", "transaction_id": "\ud800"},
        ):
            with self.subTest(action=payload["action"]):
                with self.assertRaisesRegex(UiError, "^invalid_input$"):
                    browser.act(payload, START)
                self.assertIs(browser.pending_handoff_context, context)
                self.assertEqual(browser.state(START), before)
                self.assertEqual(len(browser.request_times), 0)
                self.assertEqual(browser.store.count(), 0)

    def test_direct_prepare_rejects_unicode_before_selected_offer_or_draft_mutation(self):
        _, browser = self.server.mint_session()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, START)
        browser.message("No reconozco esta compra", START)
        offer = browser.intake_offer
        self.assertIsNotNone(offer)
        before = browser.state(START)
        for kind, request, questions in (
            ("intake", "\ud800", None),
            ("handoff", "Necesito ayuda", ("\udfff",)),
        ):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(UiError, "^invalid_input$"):
                    browser.prepare(kind, request, START, questions=questions)
                self.assertIs(browser.intake_offer, offer)
                self.assertIsNone(browser.pending_draft)
                self.assertEqual(browser.state(START), before)
                self.assertEqual(browser.store.count(), 0)

    def test_expired_abandoned_sessions_reclaimed_before_new_admission(self):
        originals = [self.server.mint_session() for _ in range(MAX_SESSIONS)]
        self.now.return_value = START + timedelta(minutes=21)
        self.monotonic.return_value = 1000.0 + 21 * 60
        fresh_token, fresh = self.server.mint_session()
        self.assertEqual(len(self.server._sessions), 1)
        self.assertEqual(list(Path(self.server._temporary.name).glob("*.sqlite3")),
                         [self.database(fresh_token)])
        self.assertTrue(fresh.state(self.now.return_value)["session"]["active"])
        for old_token, old in originals:
            self.assertIsNone(self.server.get_session(old_token))
            self.assertTrue(old.retired)
            with self.assertRaises(AccessDenied):
                old.act({"action": "message", "text": "Hola"}, self.now.return_value)
            with self.assertRaisesRegex(StoreError, "^store_closed$"):
                old.store.count()

    def test_live_cap_remains_enforced_and_does_not_discard_active_state(self):
        originals = [self.server.mint_session() for _ in range(MAX_SESSIONS)]
        with self.assertRaises(UiError) as raised:
            self.server.mint_session()
        self.assertEqual((raised.exception.code, raised.exception.status), ("session_capacity", 503))
        self.assertEqual(len(self.server._sessions), MAX_SESSIONS)
        for token, browser in originals:
            self.assertIs(self.server.get_session(token), browser)
            self.assertFalse(browser.retired)
            self.assertEqual(browser.store.count(), 0)

    def test_more_than_lifetime_limit_of_legitimate_resets_remain_bounded(self):
        token, _ = self.server.mint_session()
        for index in range(1, MAX_SESSION_MINTS_PER_MINUTE + 31):
            self.monotonic.return_value = 1000.0 + 2 * index
            self.now.return_value = START + timedelta(seconds=2 * index)
            previous = token
            token, browser = self.server.replace_session(token)
            self.assertIsNone(self.server.get_session(previous))
            self.assertFalse(self.database(previous).exists())
            self.assertEqual(len(self.server._sessions), 1)
            self.assertTrue(browser.state(self.now.return_value)["session"]["active"])
        self.assertLessEqual(len(self.server._mint_times), 31)
        self.assertEqual(len(list(Path(self.server._temporary.name).glob("*.sqlite3"))), 1)

    def test_burst_mint_limit_recovers_and_rate_failure_preserves_reset_state(self):
        token, browser = self.server.mint_session()
        for _ in range(MAX_SESSION_MINTS_PER_MINUTE - 1):
            token, browser = self.server.replace_session(token)
        browser.message("Hola", START)
        before = browser.state(START)
        with self.assertRaises(UiError) as raised:
            self.server.replace_session(token)
        self.assertEqual((raised.exception.code, raised.exception.status), ("rate_limited", 429))
        self.assertIs(self.server.get_session(token), browser)
        self.assertEqual(browser.state(START), before)
        self.assertFalse(browser.retired)
        self.assertEqual(len(self.server._mint_times), MAX_SESSION_MINTS_PER_MINUTE)
        self.monotonic.return_value += 61
        fresh_token, fresh = self.server.replace_session(token)
        self.assertNotEqual(fresh_token, token)
        self.assertEqual(len(self.server._mint_times), 1)
        self.assertTrue(fresh.state(START)["session"]["active"])

    def test_reset_constructor_failure_preserves_existing_draft_cookie_and_store(self):
        token, browser = self.server.mint_session()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, START)
        browser.message("No reconozco esta compra", START)
        browser.act({"action": "intake_decision", "offer_id": browser.intake_offer.offer_id,
                     "prepare": True}, START)
        before = browser.state(START)
        mint_times = tuple(self.server._mint_times)
        with patch("bank_service.web_app.BrowserSession", side_effect=StoreError("synthetic_startup_failure")):
            with self.assertRaisesRegex(StoreError, "^synthetic_startup_failure$"):
                self.server.replace_session(token)
        self.assertIs(self.server.get_session(token), browser)
        self.assertFalse(browser.retired)
        self.assertEqual(browser.state(START), before)
        self.assertEqual(tuple(self.server._mint_times), mint_times)
        self.assertTrue(self.database(token).exists())
        self.assertEqual(browser.store.count(), 0)
        self.assertIsNone(self.server._pending_cleanup)
        self.assertEqual(len(list(Path(self.server._temporary.name).glob("*.sqlite3"))), 1)

    def test_failed_replacement_cleanup_is_bounded_and_retried_before_more_admission(self):
        token, browser = self.server.mint_session()
        with patch.object(self.server, "_remove_session_files", side_effect=UiError("session_cleanup_failed", 503)), \
                patch.object(self.server, "_construct_session", wraps=self.server._construct_session) as construct:
            with self.assertRaisesRegex(UiError, "^session_cleanup_failed$"):
                self.server.replace_session(token)
            self.assertTrue(browser.retired)
            self.assertEqual(len(self.server._sessions), 1)
            self.assertIsNotNone(self.server._pending_cleanup)
            self.assertTrue(self.server._pending_cleanup[1].retired)
            for _ in range(3):
                with self.assertRaisesRegex(UiError, "^session_cleanup_failed$"):
                    self.server.mint_session()
            self.assertEqual(construct.call_count, 1)
            self.assertEqual(len(list(Path(self.server._temporary.name).glob("*.sqlite3"))), 2)
        self.server.mint_session()
        self.assertIsNone(self.server._pending_cleanup)
        self.assertEqual(len(self.server._sessions), 1)
        self.assertEqual(len(list(Path(self.server._temporary.name).glob("*.sqlite3"))), 1)

    def test_retirement_deletes_only_own_store(self):
        first_token, first = self.server.mint_session()
        second_token, second = self.server.mint_session()
        unrelated = Path(self.server._temporary.name) / "unrelated.sqlite3"
        unrelated.write_bytes(b"invented unrelated file")
        second.store.write_case(case_id="INVENTED-CASE", idempotency_key="INVENTED-KEY",
                                owner_id="INVENTED-OWNER", kind="handoff", payload_json="{}",
                                created_at=START.isoformat())
        self.server.retire_session(first_token)
        self.assertTrue(first.retired)
        self.assertFalse(self.database(first_token).exists())
        self.assertTrue(self.database(second_token).exists())
        self.assertEqual(second.store.count(), 1)
        self.assertEqual(unrelated.read_bytes(), b"invented unrelated file")

    def test_admission_preserves_active_unknown_write_for_same_key_reconciliation(self):
        token, browser = self.server.mint_session()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, START)
        browser.act({"action": "message", "text": "No reconozco esta compra"}, START)
        browser.act({"action": "intake_decision", "offer_id": browser.intake_offer.offer_id,
                     "prepare": True}, START)
        draft = browser.pending_draft
        read_key = browser.store.read_by_key

        def unavailable_readback(key):
            if browser.store.count():
                raise StoreError("synthetic_failure")
            return read_key(key)

        with patch.object(browser.store, "read_by_key", side_effect=unavailable_readback):
            with self.assertRaisesRegex(ActionError, "^unknown_outcome$"):
                browser.act({"action": "confirm", "draft_id": draft.draft_id,
                             "confirmed": True}, START)
        # The HTTP error handler marks this exact outcome for presentation.
        browser.outcome_unverified = True
        before = browser.state(START)
        self.server.mint_session()
        self.assertIs(self.server.get_session(token), browser)
        self.assertEqual(browser.state(START), before)
        self.assertEqual(browser.store.count(), 1)
        browser.act({"action": "confirm", "draft_id": draft.draft_id, "confirmed": True}, START)
        self.assertEqual(browser.store.count(), 1)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(len(browser.case_ids), 1)
        self.assertFalse(browser.outcome_unverified)

    def test_active_unverified_reset_preserves_state_until_reconciliation(self):
        token, browser = self.server.mint_session()
        browser.act({"action": "inquire", "transaction_id": "DEMO-TX-001"}, START)
        browser.act({"action": "message", "text": "No reconozco esta compra"}, START)
        browser.act({"action": "intake_decision", "offer_id": browser.intake_offer.offer_id,
                     "prepare": True}, START)
        draft = browser.pending_draft
        read_key = browser.store.read_by_key

        def unavailable_readback(key):
            if browser.store.count():
                raise StoreError("synthetic_failure")
            return read_key(key)

        with patch.object(browser.store, "read_by_key", side_effect=unavailable_readback):
            with self.assertRaisesRegex(ActionError, "^unknown_outcome$"):
                browser.act({"action": "confirm", "draft_id": draft.draft_id,
                             "confirmed": True}, START)
        browser.outcome_unverified = True  # The same marker set by the HTTP error handler.
        before = browser.state(START)
        mint_times = tuple(self.server._mint_times)
        with self.assertRaises(UiError) as raised:
            self.server.replace_session(token)
        self.assertEqual((raised.exception.code, raised.exception.status), ("action_not_verified", 409))
        self.assertIs(self.server.get_session(token), browser)
        self.assertIs(browser.pending_draft, draft)
        self.assertFalse(browser.retired)
        self.assertTrue(self.database(token).exists())
        self.assertEqual(browser.state(START), before)
        self.assertEqual(tuple(self.server._mint_times), mint_times)
        self.assertEqual(browser.store.count(), 1)
        browser.act({"action": "confirm", "draft_id": draft.draft_id, "confirmed": True}, START)
        self.assertEqual(browser.store.count(), 1)
        self.assertFalse(browser.outcome_unverified)
        fresh_token, fresh = self.server.replace_session(token)
        self.assertNotEqual(fresh_token, token)
        self.assertTrue(fresh.state(START)["session"]["active"])

    def test_unverified_marker_does_not_extend_expired_session_authority(self):
        token, browser = self.server.mint_session()
        browser.outcome_unverified = True
        self.now.return_value = START + timedelta(minutes=21)
        self.monotonic.return_value += 21 * 60
        fresh_token, fresh = self.server.replace_session(token)
        self.assertNotEqual(fresh_token, token)
        self.assertIsNone(self.server.get_session(token))
        self.assertTrue(browser.retired)
        self.assertFalse(self.database(token).exists())
        self.assertTrue(fresh.state(self.now.return_value)["session"]["active"])

    def test_busy_expired_session_is_not_closed_or_waited_on_under_registry_lock(self):
        originals = [self.server.mint_session() for _ in range(MAX_SESSIONS)]
        token, busy = originals[0]
        busy.session = replace(busy.session, expires_at=START - timedelta(seconds=1))
        held, release = Event(), Event()

        def in_flight_action():
            with busy.lock:
                held.set()
                release.wait(timeout=2)

        worker = Thread(target=in_flight_action, daemon=True)
        worker.start()
        self.assertTrue(held.wait(timeout=2))
        started = time.perf_counter()
        try:
            with self.assertRaisesRegex(UiError, "^session_capacity$"):
                self.server.mint_session()
            self.assertLess(time.perf_counter() - started, 0.5)
            self.assertIs(self.server.get_session(token), busy)
            self.assertFalse(busy.retired)
            self.assertEqual(busy.store.count(), 0)
        finally:
            release.set()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.server.mint_session()
        self.assertIsNone(self.server.get_session(token))
        self.assertTrue(busy.retired)
        self.assertEqual(len(self.server._sessions), MAX_SESSIONS)


class UnicodeHttpRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(0)
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method, payload=None, cookie=""):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        headers = {"Cookie": cookie} if cookie else {}
        body = None
        if payload is not None:
            headers.update({"Content-Type": "application/json",
                            "Origin": f"http://127.0.0.1:{self.server.server_address[1]}"})
            body = json.dumps(payload, ensure_ascii=True).encode("ascii")
        try:
            connection.request(method, "/api/state" if method == "GET" else "/api/action",
                               body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), response.getheader("Set-Cookie")
        finally:
            connection.close()

    def test_escaped_surrogate_is_rejected_without_poisoning_session(self):
        status, initial, cookie = self.request("GET")
        self.assertEqual(status, 200)
        cookie = cookie.split(";", 1)[0]
        for invalid in ("\ud800", "\udfff"):
            status, state, _ = self.request("POST", {"action": "message", "text": invalid,
                                                    "csrf_token": initial["csrf_token"]}, cookie)
            self.assertEqual(status, 400)
            self.assertEqual(state["error"]["code"], "invalid_input")
            self.assertEqual(state["messages"], initial["messages"])
            self.assertEqual(self.request("GET", cookie=cookie)[0], 200)
        status, state, _ = self.request("POST", {"action": "message", "text": "Olá, transacción 😀",
                                                "csrf_token": initial["csrf_token"]}, cookie)
        self.assertEqual(status, 200)
        self.assertEqual(state["messages"][-2]["text"], "Olá, transacción 😀")

    def test_reset_http_409_retains_cookie_and_unverified_case_until_same_key_readback(self):
        _, initial, cookie = self.request("GET")
        cookie = cookie.split(";", 1)[0]
        browser = self.server.get_session(cookie.split("=", 1)[1])

        def post(action, **values):
            return self.request("POST", {"action": action, "csrf_token": initial["csrf_token"], **values}, cookie)

        post("inquire", transaction_id="DEMO-TX-001")
        post("message", text="No reconozco esta compra")
        _, draft_state, _ = post("intake_decision", offer_id=browser.intake_offer.offer_id, prepare=True)
        draft_id = draft_state["pending_draft"]["draft_id"]
        read_key = browser.store.read_by_key

        def unavailable_readback(key):
            if browser.store.count():
                raise StoreError("synthetic_failure")
            return read_key(key)

        with patch.object(browser.store, "read_by_key", side_effect=unavailable_readback):
            status, state, _ = post("confirm", draft_id=draft_id, confirmed=True)
        self.assertEqual(status, 409)
        self.assertTrue(state["pending_draft"]["outcome_unverified"])
        mints_before = tuple(self.server._mint_times)
        status, reset_state, replacement_cookie = post("reset")
        self.assertEqual(status, 409)
        self.assertEqual(reset_state["error"]["code"], "action_not_verified")
        self.assertIsNone(replacement_cookie)
        self.assertEqual(reset_state["csrf_token"], initial["csrf_token"])
        self.assertEqual(reset_state["pending_draft"], state["pending_draft"])
        self.assertEqual(tuple(self.server._mint_times), mints_before)
        self.assertFalse(browser.retired)
        self.assertEqual(browser.store.count(), 1)
        status, receipt_state, _ = post("confirm", draft_id=draft_id, confirmed=True)
        self.assertEqual(status, 200)
        self.assertIsNone(receipt_state["pending_draft"])
        self.assertEqual(len(receipt_state["receipts"]), 1)
        self.assertEqual(browser.store.count(), 1)
        status, fresh, replacement_cookie = post("reset")
        self.assertEqual(status, 200)
        self.assertIsNotNone(replacement_cookie)
        self.assertNotEqual(fresh["csrf_token"], initial["csrf_token"])


if __name__ == "__main__":
    unittest.main()
