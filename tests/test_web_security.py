"""HTTP boundary regressions against disposable fictional-data servers."""

from datetime import timedelta
from http.client import HTTPConnection
import json
from threading import Event, Lock, Thread
import unittest
from unittest.mock import patch

from bank_service.web_app import COOKIE_NAME, DemoServer, MAX_BODY_BYTES


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(0)
        self.worker = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.worker.start()
        self.port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.worker.join(timeout=3)
        self.server.server_close()

    def request(self, method, path, *, data=None, raw=None, cookie=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        request_headers = dict(headers or {})
        if cookie is not None:
            request_headers["Cookie"] = cookie
        body = raw
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if method == "POST":
            request_headers.setdefault("Origin", self.origin)
            request_headers.setdefault("Content-Type", "application/json")
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            response_body = response.read()
            content_type = response.getheader("Content-Type", "")
            parsed = json.loads(response_body) if "application/json" in content_type else response_body
            return response.status, parsed, dict(response.getheaders())
        finally:
            connection.close()

    def browser(self):
        status, state, headers = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0], state["csrf_token"], state

    def act(self, cookie, csrf, action, **fields):
        return self.request("POST", "/api/action", cookie=cookie,
                            data={"action": action, "csrf_token": csrf, **fields})

    def test_cross_site_reads_cannot_mint_sessions_or_exhaust_capacity(self):
        for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://untrusted.example"}):
            with self.subTest(headers=headers):
                status, body, _ = self.request("GET", "/api/state", headers=headers)
                self.assertEqual(status, 403)
                self.assertEqual(len(self.server._sessions), 0)
                self.assertNotIn("transactions", body)
        status, state, _ = self.request("GET", "/api/state", headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(status, 200)
        self.assertTrue(state["session"]["active"])

    def test_host_origin_cookie_and_csrf_are_independent_gates(self):
        cookie, csrf, _ = self.browser()
        checks = (
            ({"Host": "untrusted.example"}, cookie, csrf, 403),
            ({"Origin": "https://untrusted.example"}, cookie, csrf, 403),
            ({"Origin": ""}, cookie, csrf, 403),
            ({}, f"{COOKIE_NAME}=forged", csrf, 401),
            ({}, cookie, "wrong-token", 403),
            ({}, cookie, "non-ascii-\u00f1", 403),
        )
        for headers, supplied_cookie, supplied_csrf, expected in checks:
            with self.subTest(headers=headers, token=supplied_csrf):
                status, _, _ = self.request("POST", "/api/action", cookie=supplied_cookie,
                                            headers=headers, data={"action": "inquire",
                                                                  "transaction_id": "DEMO-TX-001",
                                                                  "csrf_token": supplied_csrf})
                self.assertEqual(status, expected)
        status, state, _ = self.request("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIsNone(state["selected_transaction"])
        self.assertEqual(state["receipts"], [])

    def test_browser_cannot_supply_identity_grants_or_server_state(self):
        cookie, csrf, _ = self.browser()
        for injected in ({"customer_id": "DEMO-CUSTOMER-B"},
                         {"permissions": ["transaction:read"]},
                         {"session": {"customer_id": "DEMO-CUSTOMER-B"}},
                         {"selected_id": "DEMO-TX-003"}):
            with self.subTest(injected=injected):
                status, state, _ = self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-003", **injected)
                self.assertEqual(status, 400)
                self.assertEqual(state["error"]["code"], "unexpected_fields")
        status, state, _ = self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-003")
        self.assertEqual(status, 403)
        serialized = json.dumps(state)
        self.assertNotIn("Demo Foreign Merchant", serialized)
        self.assertNotIn("DEMO-CUSTOMER-B", serialized)

    def test_other_browser_cannot_confirm_or_read_a_case_even_for_same_demo_owner(self):
        first_cookie, first_csrf, _ = self.browser()
        second_cookie, second_csrf, _ = self.browser()
        self.assertEqual(self.act(first_cookie, first_csrf, "inquire", transaction_id="DEMO-TX-001")[0], 200)
        status, state, _ = self.act(first_cookie, first_csrf, "prepare_intake", reason="No reconozco esta compra.")
        self.assertEqual(status, 200)
        draft_id = state["pending_draft"]["draft_id"]
        status, state, _ = self.act(second_cookie, second_csrf, "confirm", draft_id=draft_id, confirmed=True)
        self.assertNotEqual(status, 200)
        self.assertEqual(state["receipts"], [])
        status, state, _ = self.act(first_cookie, first_csrf, "confirm", draft_id=draft_id, confirmed=True)
        self.assertEqual(status, 200)
        case_id = state["receipts"][0]["case_id"]
        status, state, _ = self.act(second_cookie, second_csrf, "view_case", case_id=case_id)
        self.assertEqual(status, 403)
        self.assertEqual(state["receipts"], [])

    def test_expired_browser_session_hides_cached_records_drafts_and_receipts(self):
        cookie, csrf, _ = self.browser()
        self.assertEqual(self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-001")[0], 200)
        status, state, _ = self.act(cookie, csrf, "prepare_intake", reason="No reconozco esta compra.")
        self.assertEqual(status, 200)
        self.assertEqual(self.act(cookie, csrf, "confirm", draft_id=state["pending_draft"]["draft_id"], confirmed=True)[0], 200)
        token = cookie.split("=", 1)[1]
        expiry = self.server.get_session(token).session.expires_at
        with patch("bank_service.web_app._now", return_value=expiry + timedelta(seconds=1)):
            status, state, _ = self.request("GET", "/api/state", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertFalse(state["session"]["active"])
            for field in ("transactions", "receipts", "candidate_ids"):
                self.assertEqual(state[field], [])
            for field in ("pending_draft", "selected_transaction", "handoff"):
                self.assertIsNone(state[field])
            self.assertNotIn("Demo Mercado Sol", json.dumps(state))
            self.assertEqual(self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-001")[0], 403)

    def test_malformed_json_cannot_change_workflow(self):
        cookie, csrf, _ = self.browser()
        examples = (
            (b'{"action":"reset","action":"inquire"}', 400),
            (b'{"action":"message","text":NaN}', 400),
            (b'[]', 400),
        )
        for raw, expected in examples:
            with self.subTest(raw_length=len(raw)):
                status, _, _ = self.request("POST", "/api/action", raw=raw, cookie=cookie)
                self.assertEqual(status, expected)
        status, state, _ = self.request("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIsNone(state["selected_transaction"])
        self.assertEqual(state["receipts"], [])

    def test_oversized_content_length_rejected_without_changing_workflow(self):
        cookie, csrf, _ = self.browser()
        self.assertEqual(self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-001")[0], 200)
        status, before, _ = self.act(cookie, csrf, "prepare_intake", reason="No reconozco esta compra.")
        self.assertEqual(status, 200)
        self.assertIsNotNone(before["pending_draft"])
        browser = self.server.get_session(cookie.split("=", 1)[1])
        case_count = browser.store.count()

        # The size gate must reject the announced upload before reading its body.
        # Sending headers alone avoids racing an upload against connection close.
        status, body, _ = self.request(
            "POST", "/api/action", cookie=cookie,
            headers={"Content-Length": str(MAX_BODY_BYTES + 1)},
        )
        self.assertEqual(status, 413)
        self.assertEqual(body["error"]["code"], "body_too_large")

        status, after, _ = self.request("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, 200)
        for field in ("selected_transaction", "pending_draft", "receipts", "candidate_ids", "messages"):
            with self.subTest(field=field):
                self.assertEqual(after[field], before[field])
        self.assertEqual(after["csrf_token"], csrf)
        self.assertEqual(browser.store.count(), case_count)
        self.assertEqual(len(self.server._sessions), 1)

    def test_reset_revokes_an_already_looked_up_session_before_later_turn(self):
        cookie, csrf, _ = self.browser()
        token = cookie.split("=", 1)[1]
        original_lookup = self.server.get_session
        looked_up, release = Event(), Event()
        once_lock = Lock()
        intercepted = False
        result = []

        def delayed_lookup(candidate):
            nonlocal intercepted
            session = original_lookup(candidate)
            with once_lock:
                should_wait = candidate == token and not intercepted
                if should_wait:
                    intercepted = True
            if should_wait:
                looked_up.set()
                if not release.wait(4):
                    raise RuntimeError("test_release_timeout")
            return session

        def old_request():
            result.append(self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-001"))

        with patch.object(self.server, "get_session", side_effect=delayed_lookup):
            pending = Thread(target=old_request, daemon=True)
            pending.start()
            try:
                self.assertTrue(looked_up.wait(2))
                self.assertEqual(self.act(cookie, csrf, "reset")[0], 200)
            finally:
                release.set()
                pending.join(timeout=4)
        self.assertFalse(pending.is_alive())
        self.assertEqual(len(result), 1)
        self.assertIn(result[0][0], (401, 403))
        self.assertNotIn("Demo Mercado Sol", json.dumps(result[0][1]))


if __name__ == "__main__":
    unittest.main()
