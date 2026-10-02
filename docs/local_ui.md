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

1. Press `Buscar una compra`: it sends a broad inquiry and asks for search details.
   Then enter `25,50 USD del 2026-06-16`. Both owned demo
   transactions match; choose a candidate. The amount, currency, status, dates and
   merchant come from that record. Source proof is available in a disclosure panel.
2. Use `No reconozco esta compra`. First accept or decline the offer to prepare a
   request, using its buttons or a short `sí`/`no` reply. Acceptance only prepares
   a draft. The chat directs you to the side panel to review its exact request and
   transaction facts. Confirm or cancel using the draft's buttons. Typing agreement
   while that draft is pending does not authorize a write. A successful receipt verifies a local
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
IDs, ISO dates and finite decimal amounts paired with explicit MXN/COP/ARS/USD currencies.
An unfinished inquiry or dispute retains its original request while collecting an
amount and currency across turns. Common plural requests such as `Enséñame mis pagos`
are supported. Comma decimals are supported. Ambiguous dates, IDs, currencies and grouped money
strings fail safely rather than selecting a convenient interpretation. The transaction
list and suggested prompts provide an alternative when the rules do not understand.

For example, `No reconozco un cargo` → `dólares` → `25,5` → choose a candidate
offers to prepare a ticket. Accepting preserves the original dispute reason and
that candidate's exact facts in an unconfirmed draft.
`25 dólares` has no match in these fixtures; it is not rounded to `25.50 USD`.
As a prototype interpretation chosen by the team, the word `dólares` means USD and
the chat displays that interpretation. `$` and `pesos` require an explicit code.
No currency is inferred from location and no amounts are converted. The owner
requested MXN/COP/ARS/USD support even where current records lack a currency.
The fictional UI records are all USD, so MXN, COP and ARS searches currently return
no match. BRL remains unsupported and its rejection permits a correction or date-only search.

Context is bounded to one unfinished search. Slot-only replies and short prefixes
such as `son`/`são` continue it. A new broad request starts a new subject; an explicit
singular reference such as `esta compra` may reuse the selected record. Relative
dates and unrestricted conversation are not implemented. Language changes and reset
clear unfinished slot collection. Failed parsing or choices clear record selection
in both the UI and authorized controller, preventing a later draft from attaching
an earlier transaction.

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

At that checkpoint the source adapter's native contract was preserved, and the only
core action extension was a freshly authorized port for displaying the proposal. Evaluation
scenarios have an independent schema; [evaluation_adapter.md](evaluation_adapter.md)
records the required integration without mapping currencies/statuses or inventing facts.

### Owner-feedback checkpoint, 2026-09-30

The owner's screenshots became synthetic regression checks, separate from training
and benchmark cases. In addition to the input/context changes above, handoff steps
now show each observed step type once in first-observed order. They summarize work
attempted, rather than an event log. Verified receipts remain distinct evidence.
The request for a person appears in the request/escalation fields. An actual unresolved
business request is carried separately; if none is known, the questions list stays
empty and the UI says none were specified. Preparing or saving an intake does not
resolve the underlying disputed charge. Long business requests use a literal excerpt
of at most 300 characters, ending in an ellipsis, in the questions field. The handoff's
own request remains in its separate pre-consent field.

Verification: **257 tests passed**, including 29 routing and 32 loopback HTTP tests.
The regression journeys cover ES/PT amount/currency collection, original dispute
reason, exact amounts, pesos/$ ambiguity, unsupported currency correction, interruption
by a new inquiry/unsupported service/human request, failed selections, typed consent,
handoff deduplication, reset, language changes and browser isolation. The source record,
access, selection, transaction, response and store modules and both public evaluation
files matched all eight protected before-edit hashes. Final contents were not read.
The working-tree privacy check passed 63 eligible files and 8/8 exclusion probes,
without reading the dictionary or scanning Git history. Baseline backups are ignored
under `.local/review_backups/chat-feedback-20260930/`.
Live Edge review verified Spanish dispute → MXN/pesos clarification → USD/amount →
selection → confirmed simulated intake → meaningful handoff, and Portuguese plural
inquiry → exact amount correction → selection → handoff with honest empty questions.
No browser warnings/errors were captured. Fictional-only screenshot proofs are
ignored under `.local/ui-review/chat-feedback-handoff-es.png` and
`.local/ui-review/chat-feedback-handoff-pt.png`. This browser check does not replace
independent Portuguese language review or the benchmark evaluation.

### Owner-approved currency support, 2026-09-30

The owner requested support for **MXN, COP, ARS and USD**, even when a currency has
no available transaction examples. The shared record/product validator, exact search,
chat parser, grounded responses and saved action packets now accept that set.
This supersedes the earlier MXN rejection shown in the feedback checkpoint; the
audit's zero-MXN transaction/product finding is unchanged. No source records were
invented or converted, and the two public demo records remain USD-only.

`No reconozco un cargo` → `MXN` → `25,50` now completes a valid search and returns
no match in the demo. The original dispute request remains available for correction
or human handoff. Bare `pesos` and `$` still require a code because the denomination
is ambiguous. `25,50 pesos MXN` is an explicit MXN amount. BRL/EUR remain outside
the four-currency application decision.

Verification: **262 tests passed**. Synthetic ES/PT checks exercise all four
currencies through exact selection, answers, confirmed simulated intake, handoff,
duplicate confirmation and receipt readback through a fresh service/store. A currency
change invalidates an earlier draft. Loopback HTTP checks prove valid MXN searches
return no match against the unchanged USD fixtures, without a currency conversion,
old selection, draft or write. One initial full-suite run hit a Windows connection
abort (WinError 10053) in an existing Origin-rejection check; the seven security tests
and the complete suite passed on rerun without changes to those tests or guards.
All 13 protected before-edit hashes matched, including core permission/action
modules, fictional demo fixtures, audit documents and public evaluation files.
Final contents were not read. The privacy check again passed 63 eligible files and
8/8 exclusion probes, without dictionary access or a Git history scan. Baseline
backups are ignored under `.local/review_backups/mxn-support-20260930/`.

Next implement that scenario adapter, train the local classifier on independent
bilingual training phrases, and compare it to these keyword rules on development
cases. Keep final contents sealed until freeze. Source-update replay, operational
tracing, language review, deployment, slides and video remain.

### Owner-requested interaction revisions, 2026-10-01

The search shortcut now asks broadly for a purchase, without prescribing an amount
or currency. Available fictional record options remain. Approved answers show the
native facts and historical-snapshot note without the unrelated blanket disclaimer;
other statuses receive a brief relevant source-limit note. No settlement or refund
claim is inferred from approval. Explicit requests to make or execute a new payment
or transaction are unsupported; inquiries about past payments remain supported.

After identifying a disputed movement, the assistant asks whether to prepare a
request. An opaque server-owned offer binds the original request, selected record,
source snapshot and at most five minutes of validity to that browser session.
Acceptance creates no stored case and no final consent. The chat explains where to
review and submit the draft in the side panel. Declining creates nothing. New
requests, navigation, language changes and reset invalidate the offer; acceptance
rechecks authorization and record freshness. Only the separate final confirmation
can save a simulated ticket. The explicit `prepare_intake` API remains a deliberate
preparation command for structured callers, never a save command.

After Enter sends a message, focus returns to the composer when the response leaves
it available. A pending draft still requires side-panel confirmation or cancellation.

Verification: **274 tests passed**, including seven new HTTP consent/navigation/
freshness checks and five routing/response checks. JavaScript syntax and the privacy
checker passed; all 12 protected before-edit hashes matched. Source adapters,
permissions, action/store/controller modules, demo records, audit findings and both
public evaluation artifacts remained unchanged. Final case contents were not read.
Browser review in Spanish and Portuguese verified broad search, approved-record
wording, offer acceptance/decline, side-panel instructions, unsupported transaction
creation and Enter focus. Spanish final submission returned a verified simulated
receipt; no browser warnings/errors were captured. These checks do not establish
benchmark performance or independent Portuguese wording review. Ignored backups
and fictional screenshots are under `.local/review_backups/ux-feedback-20261001/`
and `.local/ui-review/ux-feedback-20261001-{es,pt}.png`.

The user subsequently authorized GitHub publication. On 2026-09-29, the 63 reviewed
code/documentation, synthetic fixture and aggregate-evidence files were uploaded to
[ET-777/factored-hackathon-2026-claro](https://github.com/ET-777/factored-hackathon-2026-claro).
The pre-publication checker compared both dictionary credential values in memory,
found zero violations and passed 8/8 exclusion probes without displaying the values.
Source PDFs, private data, runtime databases, screenshots and final case contents
remain excluded. Repository publication does not deploy the local application.
The owner subsequently required private visibility during development, and the
repository was changed to private. Keep it private until new explicit owner
authorization permits public release.
