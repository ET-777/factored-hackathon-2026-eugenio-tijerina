"""Private UI contracts using only authored in-memory records and temp stores."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
import http.client
import json
from threading import Thread
import unittest
from unittest.mock import patch

from bank_service.access import AccessDenied, Permission
from bank_service.records import TransactionRecord
from bank_service.transactions import SourceReference, SourcedTransaction
from bank_service.web_app import BrowserSession, DemoServer, PrivateCohortConfig, _now


OWNER = "SYNTH-PRIVATE-OWNER"
OTHER_OWNER = "SYNTH-PRIVATE-OTHER"
READ_ONLY = frozenset({Permission.READ_TRANSACTION})
ALL_PERMISSIONS = frozenset({Permission.READ_TRANSACTION, Permission.CREATE_SIMULATED_INTAKE,
                             Permission.CREATE_SIMULATED_HANDOFF})


def synthetic_records():
    records = {}
    for identifier, owner, amount, currency, merchant in (
        ("SYNTH-PRIVATE-001", OWNER, "13000.12500", "COP", "Authored source shop"),
        ("SYNTH-PRIVATE-002", OWNER, "44.40", "USD", "Authored second shop"),
        ("SYNTH-FOREIGN-003", OTHER_OWNER, "12.00", "ARS", "FOREIGN-PRIVATE-MERCHANT"),
    ):
        record = TransactionRecord(
            identifier, owner, "SYNTH-PRIVATE-PRODUCT", datetime(2026, 6, 16, 12, 30),
            date(2026, 6, 17), "Purchase", Decimal(amount), currency, "Approved", merchant,
        )
        records[identifier] = SourcedTransaction(record, (
            SourceReference("transactions/year=2026/month=06/day=17/transactions_20260617.csv", 7, "a" * 64),
        ))
    return records


class PrivateCohortConfigurationTests(unittest.TestCase):
    def test_configuration_snapshots_mapping_and_browser_copies_preserve_fixed_grants(self):
        records = synthetic_records()
        config = PrivateCohortConfig(records, OWNER, READ_ONLY)
        first = BrowserSession(":memory:", config=config)
        second = BrowserSession(":memory:", config=config)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        records.clear()
        self.assertEqual(len(config.records), 3)
        self.assertIsNot(first.records, second.records)
        self.assertIsNot(first.records, config.records)
        self.assertIsNot(first.session, second.session)
        self.assertNotEqual(first.csrf_token, second.csrf_token)
        self.assertEqual(first.session.customer_id, OWNER)
        self.assertEqual(first.session.permissions, READ_ONLY)
        for mapping in (config.records, first.records, second.records):
            with self.assertRaises(TypeError):
                mapping["unexpected"] = synthetic_records()["SYNTH-PRIVATE-001"]
        self.assertEqual(len(first.state(_now())["transactions"]), 2)

    def test_configuration_requires_existing_customer_and_explicit_valid_read_grant(self):
        for customer in (None, "", " ", "ABSENT-PRIVATE-CUSTOMER", f" {OWNER} "):
            with self.subTest(customer=customer), self.assertRaisesRegex(ValueError, "^invalid_private_cohort_config$"):
                PrivateCohortConfig(synthetic_records(), customer, READ_ONLY)
        for permissions in (None, set(READ_ONLY), frozenset(),
                            frozenset({Permission.CREATE_SIMULATED_INTAKE}),
                            frozenset({Permission.READ_TRANSACTION.value}),
                            frozenset({Permission.READ_TRANSACTION, "unrecognized:permission"})):
            with self.subTest(permissions=permissions), self.assertRaisesRegex(ValueError, "^invalid_private_cohort_config$"):
                PrivateCohortConfig(synthetic_records(), OWNER, permissions)

    def test_configuration_rejects_missing_oversized_or_malformed_record_repository(self):
        entry = synthetic_records()["SYNTH-PRIVATE-001"]
        excessive = {f"SYNTH-{index}": replace(entry, record=replace(entry.record, transaction_id=f"SYNTH-{index}"))
                     for index in range(201)}
        invalid = (None, [], {}, excessive, {"wrong-key": entry}, {"SYNTH-PRIVATE-001": None},
                   {"SYNTH-PRIVATE-001": replace(entry, record=None)},
                   {"SYNTH-PRIVATE-001": replace(entry, sources=())})
        for records in invalid:
            with self.subTest(type=type(records).__name__), self.assertRaisesRegex(ValueError, "^invalid_private_cohort_config$"):
                PrivateCohortConfig(records, OWNER, READ_ONLY)

    def test_source_references_must_be_relative_bounded_safe_values(self):
        entry = synthetic_records()["SYNTH-PRIVATE-001"]
        reference = entry.sources[0]
        invalid = [replace(reference, file=value) for value in (
            "C:/PRIVATE-RUN/transactions.csv", "C:\\PRIVATE-RUN\\transactions.csv", "/PRIVATE-RUN/source.csv",
            "../PRIVATE-RUN/source.csv", "rows/../source.csv", "rows//source.csv", "rows/./source.csv",
            "rows/source.csv\nPRIVATE-RUN", "https://example.invalid/source.csv", "",
        )]
        invalid += [replace(reference, row_number=True), replace(reference, row_number=0),
                    replace(reference, row_sha256="PRIVATE-HASH"), None]
        for reference in invalid:
            records = {entry.record.transaction_id: replace(entry, sources=(reference,))}
            with self.subTest(reference_type=type(reference).__name__):
                with self.assertRaisesRegex(ValueError, "^invalid_private_cohort_config$") as caught:
                    PrivateCohortConfig(records, OWNER, READ_ONLY)
                self.assertNotIn("PRIVATE-RUN", str(caught.exception))

    def test_invalid_config_refuses_startup_without_demo_fallback(self):
        with patch("bank_service.web_app.demo_records", side_effect=AssertionError("No demo fallback")):
            for constructor in (lambda: BrowserSession(":memory:", config={}),
                                lambda: DemoServer(0, config={})):
                with self.assertRaisesRegex(ValueError, "^invalid_private_cohort_config$"):
                    constructor()
            config = PrivateCohortConfig(synthetic_records(), OWNER, READ_ONLY)
            browser = BrowserSession(":memory:", config=config)
            self.addCleanup(browser.close)
            self.assertEqual(browser.state(_now())["data_mode"], "private_cohort")

    def test_private_read_only_session_cannot_prepare_actions_or_intake_offer(self):
        browser = BrowserSession(":memory:", config=PrivateCohortConfig(synthetic_records(), OWNER, READ_ONLY))
        self.addCleanup(browser.close)
        now = _now()
        browser.act({"action": "inquire", "transaction_id": "SYNTH-PRIVATE-001"}, now)
        for payload in (
            {"action": "dispute_selected", "transaction_id": "SYNTH-PRIVATE-001"},
            {"action": "prepare_intake", "reason": "Synthetic reason"},
            {"action": "prepare_handoff", "request": "Synthetic request"},
        ):
            with self.subTest(action=payload["action"]), self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                browser.act(payload, now)
        self.assertIsNone(browser.intake_offer)
        self.assertIsNone(browser.pending_draft)
        self.assertEqual(browser.store.count(), 0)

    def test_default_browser_keeps_demo_records_and_twenty_minute_session(self):
        now = _now()
        with patch("bank_service.web_app._now", return_value=now):
            browser = BrowserSession(":memory:")
        self.addCleanup(browser.close)
        state = browser.state(now)
        self.assertEqual(state["data_mode"], "demo")
        self.assertEqual(browser.session.expires_at, now + timedelta(minutes=20))
        self.assertEqual([record["transaction_id"] for record in state["transactions"]],
                         ["DEMO-TX-001", "DEMO-TX-002"])
        self.assertIn("ficticia", state["messages"][0]["text"])


class PrivateCohortHttpTests(unittest.TestCase):
    def setUp(self):
        self.config = PrivateCohortConfig(synthetic_records(), OWNER, ALL_PERMISSIONS)
        self.server = DemoServer(0, config=self.config)
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.cookie = ""
        self.state = {}
        self.addCleanup(self.stop)
        self.request("GET", "/api/state")

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method, path, payload=None):
        headers = {"Cookie": self.cookie} if self.cookie else {}
        body = None
        if method == "POST":
            headers.update({"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/json"})
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = json.loads(response.read())
            cookie = response.getheader("Set-Cookie")
            if cookie:
                self.cookie = cookie.split(";", 1)[0]
            if "messages" in data:
                self.state = data
            return response.status, data
        finally:
            connection.close()

    def post(self, action, **fields):
        return self.request("POST", "/api/action", {
            "action": action, "csrf_token": self.state["csrf_token"], **fields,
        })

    def browser(self):
        return self.server.get_session(self.cookie.split("=", 1)[1])

    def assert_private_projection(self, state):
        encoded = json.dumps(state, ensure_ascii=False)
        for forbidden in (OWNER, OTHER_OWNER, "SYNTH-PRIVATE-PRODUCT", "FOREIGN-PRIVATE-MERCHANT",
                          "customer_id", "product_id", "manifest", self.server._temporary.name):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(state["data_mode"], "private_cohort")

    def test_private_state_projects_only_owned_records_and_relative_grounding_refs(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assert_private_projection(self.state)
        self.assertEqual([record["transaction_id"] for record in self.state["transactions"]],
                         ["SYNTH-PRIVATE-001", "SYNTH-PRIVATE-002"])
        record = self.state["transactions"][0]
        self.assertEqual((record["amount"], record["currency"]), ("13000.12500", "COP"))
        self.assertEqual(record["sources"], [{
            "file": "transactions/year=2026/month=06/day=17/transactions_20260617.csv",
            "row_number": 7, "row_sha256": "a" * 64,
        }])
        self.assertIn("privada", self.state["messages"][0]["text"])
        self.assertNotIn("ficticia", self.state["messages"][0]["text"])

    def test_missing_and_other_owner_requests_are_denied_without_leaking_foreign_facts(self):
        errors = []
        for identifier in ("SYNTH-FOREIGN-003", "SYNTH-NOT-FOUND"):
            status, state = self.post("inquire", transaction_id=identifier)
            self.assertEqual(status, 403)
            errors.append(state["error"])
            self.assert_private_projection(state)
            self.assertIsNone(state["selected_transaction"])
        self.assertEqual(errors[0], errors[1])

    def test_browser_cannot_override_source_identity_or_permissions(self):
        for field, value in (("customer_id", OTHER_OWNER), ("permissions", ["intake:create_simulated"]),
                             ("cohort_run", "PRIVATE-RUN-PATH"), ("data_mode", "demo")):
            with self.subTest(field=field):
                status, state = self.post("inquire", transaction_id="SYNTH-PRIVATE-001", **{field: value})
                self.assertEqual(status, 400)
                self.assertEqual(state["error"]["code"], "unexpected_fields")
                self.assertNotIn("PRIVATE-RUN-PATH", json.dumps(state))
                self.assertEqual(self.browser().session.customer_id, OWNER)
                self.assertEqual(self.browser().session.permissions, ALL_PERMISSIONS)

    def test_private_currency_wording_is_accurate_in_spanish_and_portuguese(self):
        for language, phrase in (("es", "Busca la compra de 13000 pesos"),
                                 ("pt", "Busque a compra de 13000 pesos")):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                status, state = self.post("message", text=phrase)
                self.assertEqual(status, 200)
                self.assertEqual(state["messages"][-1]["status"], "needs_currency")
                text = state["messages"][-1]["text"]
                self.assertIn("privada", text)
                self.assertNotIn("fictici", text)
                self.assertNotIn("en USD", text)
                self.assertNotIn("em USD", text)
                self.assertIn("privad", self.browser().text("greeting"))
                self.assert_private_projection(state)

    def test_reset_mints_new_authority_but_preserves_startup_mode_customer_and_grants(self):
        old_cookie, old_browser = self.cookie, self.browser()
        old_session, old_csrf = old_browser.session, self.state["csrf_token"]
        self.post("inquire", transaction_id="SYNTH-PRIVATE-001")
        # An expired browser still needs an explicit reset; it cannot read facts.
        expired = old_browser.state(old_session.expires_at)
        self.assertFalse(expired["session"]["active"])
        self.assertEqual(expired["transactions"], [])
        before = _now()
        status, state = self.post("reset")
        after = _now()
        self.assertEqual(status, 200)
        fresh = self.browser()
        self.assertNotEqual(self.cookie, old_cookie)
        self.assertNotEqual(state["csrf_token"], old_csrf)
        self.assertIsNot(fresh.session, old_session)
        self.assertTrue(old_browser.retired)
        self.assertIsNone(self.server.get_session(old_cookie.split("=", 1)[1]))
        self.assertEqual(fresh.session.customer_id, OWNER)
        self.assertEqual(fresh.session.permissions, ALL_PERMISSIONS)
        self.assertLessEqual(before + timedelta(minutes=20), fresh.session.expires_at)
        self.assertLessEqual(fresh.session.expires_at, after + timedelta(minutes=20))
        self.assertEqual(state["receipts"], [])
        self.assertIsNone(state["selected_transaction"])
        self.assert_private_projection(state)
        with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
            old_browser.authorize(after)

    def test_bilingual_source_backed_intake_and_handoff_remain_explicit_simulations(self):
        for language in ("es", "pt"):
            with self.subTest(language=language):
                self.post("reset")
                self.post("language", language=language)
                status, state = self.post("search", amount="13000.12500", currency="COP")
                self.assertEqual(status, 200)
                self.assertEqual(state["selected_transaction"]["transaction_id"], "SYNTH-PRIVATE-001")
                status, state = self.post("dispute_selected", transaction_id="SYNTH-PRIVATE-001")
                self.assertEqual(status, 200)
                self.assertIsNone(state["pending_draft"])
                self.assertEqual(self.browser().store.count(), 0)
                offer = state["intake_offer"]
                status, state = self.post("intake_decision", offer_id=offer["offer_id"], prepare=True)
                self.assertEqual(status, 200)
                draft = state["pending_draft"]
                self.assertEqual(draft["packet"]["facts"]["amount"], "13000.12500")
                self.assertEqual(draft["packet"]["facts"]["currency"], "COP")
                self.assertTrue(draft["packet"]["sources"])
                self.assertTrue(draft["packet"]["simulated"])
                self.assertEqual(self.browser().store.count(), 0)
                self.assert_private_projection(state)
                status, state = self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertEqual(status, 200)
                receipt_id = state["receipts"][0]["case_id"]
                self.post("confirm", draft_id=draft["draft_id"], confirmed=True)
                self.assertEqual(self.browser().store.count(), 1)
                phrase = "Quiero hablar con una persona" if language == "es" else "Quero falar com uma pessoa"
                status, state = self.post("message", text=phrase)
                handoff = state["pending_draft"]
                self.assertEqual(handoff["packet"]["verified_actions"][0]["case_id"], receipt_id)
                self.assertEqual(self.browser().store.count(), 1)
                self.assert_private_projection(state)
                status, state = self.post("confirm", draft_id=handoff["draft_id"], confirmed=True)
                self.assertEqual(status, 200)
                self.assertEqual(self.browser().store.count(), 2)
                self.assertIs(state["handoff"]["simulated"], True)
                self.assertEqual(state["handoff"]["facts"]["currency"], "COP")
                self.assertTrue(state["handoff"]["sources"])
                self.assert_private_projection(state)


if __name__ == "__main__":
    unittest.main()
