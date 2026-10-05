"""Fictional hosted-demo checks against a loopback fake TLS boundary.

These HTTP clients manually send Secure cookies. They exercise trusted startup
authority and application guards, not real cloud HTTPS or browser TLS behavior.
No source dataset, customer cohort or training artifact is opened here.
"""

from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from io import StringIO
import json
import os
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch

from bank_service.__main__ import main
from bank_service.access import Permission
from bank_service.demo_fixtures import DEMO_CUSTOMER, demo_records
from bank_service.hosting import HostingConfig
from bank_service.web_app import COOKIE_NAME, DemoServer, PrivateCohortConfig


ORIGIN = "https://demo.example.test"
AUTHORITY = "demo.example.test"


class HostingConfigTests(unittest.TestCase):
    def test_only_canonical_https_dns_origins_are_accepted(self):
        invalid = (
            None, {}, "", " https://demo.example.test", "https://demo.example.test ",
            "http://demo.example.test", "HTTPS://demo.example.test", "https://Demo.example.test",
            "https://demo.example.test/", "https://demo.example.test/path",
            "https://demo.example.test?key=value", "https://demo.example.test?",
            "https://demo.example.test#fragment", "https://demo.example.test#",
            "https://user@demo.example.test", "https://user:password@demo.example.test",
            "https://demo.example.test:0", "https://demo.example.test:65536",
            "https://demo.example.test:443", "https://demo.example.test:08443",
            "https://demo.example.test:", "https://demo.example.test:abc",
            "https://localhost", "https://demo.localhost", "https://demo.local", "https://demo.internal",
            "https://127.0.0.1", "https://192.168.1.2", "https://[::1]",
            "https://demo.example.test.", "https://-demo.example.test", "https://demo-.example.test",
            "https://demo..example.test", "https://demo_example.test", "https://demo.123",
            "https://demo.example.test\\@other.example", "https://demo.example.test\n",
            "https://démó.example.test", "https://" + "a" * 64 + ".example.test",
            "https://" + ".".join(["a" * 63] * 5),
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__, origin=value):
                with self.assertRaisesRegex(ValueError, "^invalid_hosting_config$"):
                    HostingConfig(value)
        for origin in (ORIGIN, ORIGIN + ":8443", "https://demo.example.test:65535"):
            self.assertEqual(HostingConfig(origin).public_origin, origin)

    def test_bind_selection_is_explicit_and_private_config_fails_before_socket_or_store(self):
        for host in ("localhost", "::", "public.example.test", None):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "^invalid_hosting_config$"):
                HostingConfig(ORIGIN, host)
        private = PrivateCohortConfig(demo_records(), DEMO_CUSTOMER, frozenset({Permission.READ_TRANSACTION}))
        with patch("bank_service.web_app.TemporaryDirectory") as temporary:
            with self.assertRaisesRegex(ValueError, "^hosted_private_config_forbidden$"):
                DemoServer(0, hosting=HostingConfig(ORIGIN), config=private)
            temporary.assert_not_called()

    def test_invalid_server_port_or_hosting_type_does_not_open_a_socket(self):
        for port in (-1, 65536, "8080", True):
            with self.subTest(port=port), self.assertRaisesRegex(ValueError, "^invalid_port$"):
                DemoServer(port, hosting=HostingConfig(ORIGIN))
        with self.assertRaisesRegex(ValueError, "^invalid_hosting_config$"):
            DemoServer(0, hosting={})


class HostedCliTests(unittest.TestCase):
    def invoke(self, arguments, *, environment=None):
        output, errors = StringIO(), StringIO()
        router = object()
        with (
            patch("sys.argv", ["bank_service", "web", *arguments]),
            patch.dict(os.environ, environment or {}, clear=True),
            patch("bank_service.web_app.serve") as serve,
            patch("bank_service.cohort_repository.load_private_cohort") as cohort,
            patch("bank_service.route_loader.load_preview_router", return_value=router) as preview,
            patch("bank_service.route_loader.load_short_preview_router", return_value=router) as short_preview,
            redirect_stdout(output), redirect_stderr(errors),
        ):
            code = 0
            try:
                main()
            except SystemExit as error:
                code = error.code
        return code, serve, cohort, preview, short_preview, output.getvalue(), errors.getvalue()

    def test_hosted_environment_contract_and_keyword_default(self):
        code, serve, cohort, preview, short, _, errors = self.invoke(
            ["--hosted"], environment={"PUBLIC_ORIGIN": ORIGIN, "PORT": "8088"})
        self.assertEqual((code, errors), (0, ""))
        serve.assert_called_once_with(8088, hosting=HostingConfig(ORIGIN))
        for loader in (cohort, preview, short):
            loader.assert_not_called()

    def test_hosted_explicit_arguments_override_environment(self):
        code, serve, _, _, _, _, _ = self.invoke(
            ["--hosted", "--public-origin", ORIGIN, "--host", "127.0.0.1", "--port", "8089"],
            environment={"PUBLIC_ORIGIN": "invalid", "PORT": "invalid"})
        self.assertEqual(code, 0)
        serve.assert_called_once_with(8089, hosting=HostingConfig(ORIGIN, "127.0.0.1"))

    def test_missing_port_defaults_to_8080_and_preview_is_opt_in(self):
        code, serve, cohort, preview, short, output, _ = self.invoke(
            ["--hosted", "--public-origin", ORIGIN, "--router", "learned-preview-v2"])
        self.assertEqual(code, 0)
        self.assertEqual(serve.call_args.args, (8080,))
        self.assertEqual(serve.call_args.kwargs["hosting"], HostingConfig(ORIGIN))
        self.assertIs(serve.call_args.kwargs["router"], short.return_value)
        short.assert_called_once_with()
        cohort.assert_not_called()
        preview.assert_not_called()
        self.assertIn("hosted DEMO", output)
        self.assertIn("guarded serving policy", output)

    def test_hosted_private_overrides_fail_before_any_loader(self):
        for override in (["--cohort-run", "NEVER-OPEN"], ["--customer-id", "NEVER-USE"],
                         ["--permission", "transaction:read"]):
            with self.subTest(option=override[0]):
                code, serve, cohort, preview, short, _, errors = self.invoke(
                    ["--hosted", "--public-origin", ORIGIN, "--router", "learned-preview", *override])
                self.assertEqual(code, 2)
                self.assertIn("hosted mode forbids", errors)
                for action in (serve, cohort, preview, short):
                    action.assert_not_called()

    def test_hosted_invalid_authority_or_port_refused_before_loaders(self):
        invalid_environments = ({}, {"PUBLIC_ORIGIN": "http://demo.example.test"},
                                {"PUBLIC_ORIGIN": ORIGIN, "PORT": "0"},
                                {"PUBLIC_ORIGIN": ORIGIN, "PORT": "65536"},
                                {"PUBLIC_ORIGIN": ORIGIN, "PORT": " 8080"},
                                {"PUBLIC_ORIGIN": ORIGIN, "PORT": "eight"})
        for environment in invalid_environments:
            with self.subTest(environment=environment):
                code, serve, cohort, preview, short, _, errors = self.invoke(
                    ["--hosted", "--router", "learned-preview"], environment=environment)
                self.assertEqual(code, 2)
                self.assertIn("canonical HTTPS", errors)
                for action in (serve, cohort, preview, short):
                    action.assert_not_called()

    def test_local_default_ignores_hosted_environment_and_public_bind_requires_opt_in(self):
        code, serve, cohort, preview, short, _, _ = self.invoke(
            [], environment={"PUBLIC_ORIGIN": ORIGIN, "PORT": "8088"})
        self.assertEqual(code, 0)
        serve.assert_called_once_with(8765)
        for loader in (cohort, preview, short):
            loader.assert_not_called()
        for arguments in (["--host", "0.0.0.0"], ["--public-origin", ORIGIN]):
            with self.subTest(arguments=arguments):
                code, serve, _, _, _, _, errors = self.invoke(arguments)
                self.assertEqual(code, 2)
                self.assertIn("require --hosted", errors)
                serve.assert_not_called()


class HostedHttpTests(unittest.TestCase):
    def setUp(self):
        self.server = DemoServer(0, hosting=HostingConfig(ORIGIN, "127.0.0.1"))
        self.worker = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.worker.start()
        self.port = self.server.server_address[1]
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.worker.join(timeout=3)
        self.server.server_close()

    def request(self, method, path, *, cookie=None, payload=None, headers=None):
        request_headers = {"Host": AUTHORITY}
        request_headers.update(headers or {})
        if cookie is not None:
            request_headers["Cookie"] = cookie
        body = None
        if method == "POST":
            request_headers.setdefault("Origin", ORIGIN)
            request_headers.setdefault("Content-Type", "application/json")
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            value = json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw
            return response.status, value, dict(response.getheaders())
        finally:
            connection.close()

    def browser(self):
        status, state, headers = self.request("GET", "/api/state", headers={"Origin": ORIGIN})
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0], state["csrf_token"], state

    def act(self, cookie, csrf, action, **fields):
        return self.request("POST", "/api/action", cookie=cookie,
                            payload={"action": action, "csrf_token": csrf, **fields})

    def test_health_has_no_records_cookie_or_session_capacity_cost(self):
        with patch.object(self.server, "mint_session", wraps=self.server.mint_session) as mint:
            for _ in range(3):
                status, body, headers = self.request("GET", "/healthz")
                self.assertEqual((status, body), (200, {"status": "ok"}))
                self.assertNotIn("Set-Cookie", headers)
                self.assertEqual(headers["Cache-Control"], "no-store")
            mint.assert_not_called()
        self.assertEqual(len(self.server._sessions), 0)
        self.assertEqual(len(self.server._mint_times), 0)
        self.assertEqual(list(Path(self.server._temporary.name).iterdir()), [])
        with patch("bank_service.web_app.MAX_SESSIONS", 1):
            cookie, _, _ = self.browser()
            self.assertEqual(self.request("GET", "/api/state")[0], 503)
            status, body, headers = self.request("GET", "/healthz", cookie=cookie)
            self.assertEqual((status, body), (200, {"status": "ok"}))
            self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(len(self.server._sessions), 1)
        self.assertEqual(self.request("GET", "/healthz?detail=records")[0], 404)
        self.assertEqual(self.request("GET", "/healthz", headers={"Host": "localhost"})[0], 403)

    def test_secure_cookie_fixed_demo_identity_and_reset_cookie(self):
        status, state, headers = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertEqual(state["session"]["customer_label"], DEMO_CUSTOMER)
        self.assertEqual(state["authentication"], "fixed_demo_identity_not_production_login")
        self.assertEqual(state["hosting_mode"], "public_fictional_demo")
        self.assertEqual(state["data_mode"], "demo")
        self.assertEqual(state["route_mode"], "keyword_baseline")
        self.assertTrue(state["simulation"])
        self.assertEqual([row["transaction_id"] for row in state["transactions"]],
                         ["DEMO-TX-001", "DEMO-TX-002"])
        status, fresh, headers = self.act(cookie.split(";", 1)[0], state["csrf_token"], "reset")
        self.assertEqual(status, 200)
        self.assertIn("Secure", headers["Set-Cookie"])
        self.assertNotEqual(fresh["csrf_token"], state["csrf_token"])

    def test_state_origin_and_forwarded_headers_cannot_mint_sessions(self):
        invalid_headers = (
            {"Origin": "http://" + AUTHORITY}, {"Origin": "https://evil.example.test"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Host": f"127.0.0.1:{self.port}", "X-Forwarded-Host": AUTHORITY, "X-Forwarded-Proto": "https"},
            {"Host": "evil.example.test", "Forwarded": f"host={AUTHORITY};proto=https"},
            {"Origin": "http://" + AUTHORITY, "X-Forwarded-Proto": "https"},
        )
        for headers in invalid_headers:
            with self.subTest(headers=headers):
                status, state, response_headers = self.request("GET", "/api/state", headers=headers)
                self.assertEqual(status, 403)
                self.assertNotIn("transactions", state)
                self.assertNotIn("Set-Cookie", response_headers)
        self.assertEqual(len(self.server._sessions), 0)
        # Extra forwarding metadata never changes a valid configured authority.
        self.assertEqual(self.request("GET", "/api/state", headers={
            "Origin": ORIGIN, "X-Forwarded-Host": "evil.example.test", "X-Forwarded-Proto": "http"})[0], 200)

    def test_post_origin_csrf_cookie_and_identity_gates_remain_independent(self):
        cookie, csrf, _ = self.browser()
        checks = (
            ({"Origin": ""}, cookie, csrf, 403),
            ({"Origin": "http://" + AUTHORITY, "X-Forwarded-Proto": "https"}, cookie, csrf, 403),
            ({"Origin": "https://evil.example.test", "Forwarded": f"host={AUTHORITY};proto=https"}, cookie, csrf, 403),
            ({"Host": "evil.example.test", "X-Forwarded-Host": AUTHORITY}, cookie, csrf, 403),
            ({}, cookie, "forged", 403), ({}, COOKIE_NAME + "=forged", csrf, 401),
        )
        for headers, supplied_cookie, supplied_csrf, expected in checks:
            with self.subTest(headers=headers, expected=expected):
                status, _, _ = self.request("POST", "/api/action", cookie=supplied_cookie, headers=headers,
                    payload={"action": "inquire", "csrf_token": supplied_csrf, "transaction_id": "DEMO-TX-001"})
                self.assertEqual(status, expected)
        for fields in ({"customer_id": "DEMO-CUSTOMER-B"}, {"permissions": ["transaction:read"]}):
            with self.subTest(fields=fields):
                self.assertEqual(self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-003", **fields)[0], 400)
        status, state, _ = self.act(cookie, csrf, "inquire", transaction_id="DEMO-TX-003")
        self.assertEqual(status, 403)
        self.assertNotIn("Demo Foreign Merchant", json.dumps(state))
        self.assertIsNone(state["selected_transaction"])
        self.assertEqual(state["receipts"], [])

    def test_duplicate_host_and_origin_are_rejected_before_session_mint(self):
        for duplicate in ("Host", "Origin"):
            with self.subTest(duplicate=duplicate):
                connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
                try:
                    connection.putrequest("GET", "/api/state", skip_host=True)
                    connection.putheader("Host", AUTHORITY)
                    connection.putheader("Origin", ORIGIN)
                    connection.putheader(duplicate, AUTHORITY if duplicate == "Host" else ORIGIN)
                    connection.endheaders()
                    response = connection.getresponse()
                    self.assertEqual(response.status, 403)
                    response.read()
                finally:
                    connection.close()
        self.assertEqual(len(self.server._sessions), 0)

    def test_bilingual_inquiry_intake_handoff_receipts_and_browser_isolation(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                cookie, csrf, _ = self.browser()
                self.assertEqual(self.act(cookie, csrf, "language", language=language)[0], 200)
                inquiry = "Busca la compra de 25.50 USD" if language == "es" else "Busque a compra de 25,50 USD"
                status, state, _ = self.act(cookie, csrf, "message", text=inquiry)
                self.assertEqual(status, 200)
                self.assertEqual(state["candidate_ids"], ["DEMO-TX-001", "DEMO-TX-002"])
                status, state, _ = self.act(cookie, csrf, "choose", transaction_id="DEMO-TX-001")
                self.assertEqual(state["selected_transaction"]["amount"], "25.50")
                self.assertTrue(state["selected_transaction"]["sources"])
                dispute = "No reconozco esta compra" if language == "es" else "Não reconheço esta compra"
                status, state, _ = self.act(cookie, csrf, "message", text=dispute)
                self.assertEqual(status, 200)
                self.assertIsNone(state["pending_draft"])
                offer = state["intake_offer"]["offer_id"]
                status, state, _ = self.act(cookie, csrf, "intake_decision", offer_id=offer, prepare=True)
                self.assertEqual(status, 200)
                draft = state["pending_draft"]["draft_id"]
                store = self.server.get_session(cookie.split("=", 1)[1]).store
                self.assertEqual(store.count(), 0)
                other_cookie, other_csrf, _ = self.browser()
                self.assertNotEqual(self.act(other_cookie, other_csrf, "confirm", draft_id=draft, confirmed=True)[0], 200)
                status, state, _ = self.act(cookie, csrf, "confirm", draft_id=draft, confirmed=True)
                self.assertEqual(status, 200)
                case_id = state["receipts"][0]["case_id"]
                self.assertEqual(store.count(), 1)
                self.act(cookie, csrf, "confirm", draft_id=draft, confirmed=True)
                self.assertEqual(store.count(), 1)
                status, hidden, _ = self.act(other_cookie, other_csrf, "view_case", case_id=case_id)
                self.assertEqual(status, 403)
                self.assertEqual(hidden["receipts"], [])
                phrase = "Quiero hablar con una persona" if language == "es" else "Quero falar com uma pessoa"
                status, state, _ = self.act(cookie, csrf, "message", text=phrase)
                self.assertEqual(status, 200)
                handoff = state["pending_draft"]
                self.assertEqual(handoff["kind"], "handoff")
                self.assertEqual(handoff["packet"]["verified_actions"][0]["case_id"], case_id)
                self.assertEqual(store.count(), 1)
                status, state, _ = self.act(cookie, csrf, "confirm", draft_id=handoff["draft_id"], confirmed=True)
                self.assertEqual(status, 200)
                self.assertEqual(store.count(), 2)
                self.assertTrue(state["handoff"]["simulated"])
                self.assertEqual(state["handoff"]["language"], language)


if __name__ == "__main__":
    unittest.main()
