# Local bilingual interface checkpoint

The local UI connects the existing guarded workflow to Spanish/Portuguese chat,
transaction selection, exact proposal review, explicit confirmation, verified
receipts and readable human-handoff packets. It uses independently authored
fictional demo records, never the private source cohort or either evaluation split.

## Run and review

From the repository root, with Python 3.11+:

```powershell
python -B -m bank_service web --port 8765
```

Open **http://127.0.0.1:8765**. The server binds only to `127.0.0.1`; stop it with
Ctrl+C. No extra UI dependency, provider account or model call is required.

1. Ask `Quiero consultar una compra de 25,50 USD del 2026-06-16`. Both owned demo
   transactions match; choose a candidate. The amount, currency, status, dates and
   merchant come from that record. Source proof is available in a disclosure panel.
2. Use `No reconozco un cargo`. Review the proposed ticket's exact request and
   transaction facts. Confirm or cancel using the proposal's buttons. Typing
   agreement does not authorize a write. A successful receipt verifies a local
   simulated ticket; it does not resolve the dispute or promise a refund.
3. Switch to Portuguese after completing/cancelling the proposal. Ask
   `Quero falar com uma pessoa sobre esta compra`. Review the exact handoff request,
   facts, attempted steps, prior verified ticket reference and unresolved questions
   before confirming. The receipt confirms a simulated queue entry; no human or
   bank is contacted. Earlier messages and stored receipts keep their original text.
4. Start a new session and try `Quiero un préstamo` or a transaction outside this
   demo session. Unsupported services offer a human path; unauthorized references
   return the same generic denial as missing references.

The owner can now review the experience and handoff presentation on the working UI.
Portuguese wording still needs independent fluent review; functional tests are not
a linguistic quality assessment.

## Current input component

`routing.py` implements the keyword baseline's four intent proposals: `inquiry`,
`dispute_intake`, `human_request`, and `unsupported`. It extracts explicit transaction
IDs, ISO dates and finite decimal amounts paired with explicit USD/COP/ARS currencies.
Comma decimals are supported. Ambiguous dates, IDs, currencies and grouped money
strings fail safely rather than selecting a convenient interpretation. The transaction
list and suggested prompts provide an alternative when the rules do not understand.

The rule's 0/1 confidence value is a match indicator, not a calibrated probability.
This is not the planned learned component or an unrestricted conversational model.
The later character n-gram classifier will propose the same intents while permission,
selection, confirmation and receipt checks stay outside it.

## Session and storage behavior

- The server mints an opaque cookie and keeps the exact trusted identity, permissions,
  expiry, controller and action drafts outside browser input. Each browser session
  has a separate temporary SQLite case store, even when its fictional customer label
  matches another browser. Session lifetime is 20 minutes; proposals last five minutes.
- Reset starts a fresh Spanish demo and retires the old session. It clears access
  to prior tickets and drafts. No production login or durable draft recovery is claimed.
  Database files are temporary and removed when the server closes normally.
- Confirmation retries reconcile the same draft, never an automatic new write. A
  committed write with failed verification shows an unverified outcome, retains the
  reference and allows reconciliation after proposal expiry while the session is
  active. Expiry still prevents new writes. No uncertain result is labelled success.
- Host, Origin, CSRF, strict bounded JSON and exact action-field checks guard requests.
  Turns are serialized per session. Limits are 16 KiB/request, 1,000 characters/text,
  60 actions/minute/session, 40 retained chat messages, 20 active sessions and 100
  sessions minted per server run. These are prototype bounds, not capacity qualification.
- Static assets are local with a restrictive content policy. Record names, user text
  and packets are inserted as text. No prompts, cookies or request bodies are logged.

## Verification and remaining work

Verification on 2026-09-29: **225 tests passed** with
`python -B -m unittest discover -s tests -q`; `node --check bank_service/web/app.js`
passed. These include 15 routing and 19 loopback HTTP checks added to the prior
191-test library/CLI suite. Tests cover bilingual journeys, exact pre-consent packets,
typed-assent rejection, idempotent confirmation, uncertain committed writes, recovery
with unavailable page state, owner/session isolation, expiry, reset races, Host/Origin/
CSRF, malformed input and injected authority fields. Browser review completed Spanish
search/choice/intake, Portuguese inquiry/intake/handoff, unsupported-request context,
cancellation, generic denied lookup, reset and the desktop layout without console
warnings/errors. Transport/receipt failure behavior is tested at the HTTP layer;
browser fault injection and mobile qualification are not claimed.

The working-tree privacy check passed 63 eligible files and 8/8 exclusion probes;
no dictionary access or exact-credential comparison was performed, and Git history
was not scanned. Nine of ten protected before-edit hashes matched; `actions.py` is
the sole intentional change, adding the authorized read-only draft presentation port.
The protected source adapter, repository, selection, responses, conversation, case
store and public evaluation files remained unchanged. Final case contents were not
read. Backups are under ignored `.local/review_backups/ui-20260929T210331/`; the local
fictional-data screenshot is `.local/ui-review/verified-handoff.jpg`, also ignored.

HTTP tests use disposable fictional records and temporary stores; they do not count
as the public 19-case development or sealed 32-case final benchmark.

The source adapter's native contract is preserved. The only core action extension
is a read-only, freshly authorized port for displaying the proposed packet. Evaluation
scenarios have an independent schema; [evaluation_adapter.md](evaluation_adapter.md)
records the required integration without mapping currencies/statuses or inventing facts.

Next implement that scenario adapter, train the local classifier on independent
bilingual training phrases, and compare it to these keyword rules on development
cases. Keep final contents sealed until freeze. Source-update replay, operational
tracing, language review, deployment, repository publication, slides and video remain.
