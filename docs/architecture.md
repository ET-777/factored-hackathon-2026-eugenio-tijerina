# Minimal implementation contract and local implementation status

The user requested a narrow bilingual service workflow with grounded answers,
permissions outside the model, verified actions, and useful escalation. The organizer
allows mock tools and trusted test sessions (Brief p. 5; filenames in requirements.md).
The validated record/cohort path, guarded inquiry, multi-turn structured controller,
confirmed simulated intake/handoff and SQLite readback now have a local implementation.
See [local_workflow.md](local_workflow.md) and [local_ui.md](local_ui.md) for the runnable
synthetic demonstrations and limits. A loopback interface now mints opaque browser
sessions and routes Spanish/Portuguese requests through keyword rules into this
controller. Production identity, the learned router, scenario evaluation adapter,
update replay, deployment and final evaluation are pending.

## One small application

Use a single Python app and a local SQLite case store. Separate the web interface,
intent component, state machine, and tools into simple modules in the same app. A thin
Spanish/Portuguese interface and templates are sufficient; extra agents, streaming,
vector infrastructure and live-bank integrations add no necessary value here.

`trusted session -> intent proposal -> deterministic workflow -> guarded tools -> evidence-backed response`

The learned component proposes `inquiry`, `dispute_intake`, `human_request`, or `unsupported`.
It does not choose identity, authorize access, assert that an action succeeded, determine
fraud, or invent banking policy. Uncertain intent triggers clarification or human review.
Preserve the selected transaction and pending action across turns; recheck authorization
and expiry for every tool call. Keep a user's language separate from record language.

The current keyword proposal is a baseline, not learned inference. Typed assent is
never action consent; only the exact draft's explicit confirmation is accepted.
Before consent, `ActionService.review_draft` rechecks the bound session/permissions
and exposes the exact proposed packet through the UI's allowlist. Per-session locks
serialize turns; reset retires the old session even for an already looked-up request.
Uncertain confirmation keeps its recovery reference and cannot display success until
the persisted case is verified. Browser/session storage is ephemeral and bounded.

## Tool contracts

| Tool | Minimum contract |
|---|---|
| `list_transactions(session, filters)` | Server-owned session selects customer; parameterized queries; return allowlisted facts only; no caller-supplied customer override. |
| `get_transaction(session, transaction_id)` | Load actual owner from repository, enforce access, then return record facts and immutable source/version reference. Treat missing and unauthorized references without revealing existence. |
| `prepare_intake(session, transaction_id, reason)` | Validate ownership, required evidence, action permission and supported state; produce a specific draft for explicit confirmation. No write yet. |
| `confirm_intake(session, draft_id, confirmation, idempotency_key)` | Confirmation binds to the exact transaction/reason and draft version; recheck permission and freshness; make one atomic local simulated write. A classifier output is never confirmation. |
| `read_intake(session, case_id)` | Read back persisted case and compare identity, transaction, payload and state before emitting a success receipt. Missing/uncertain readback means unverified, never success. |
| `build_handoff(...)` | Return request, permitted verified facts, source refs, actions/results, failure or escalation reason and unresolved questions. Store/display a simulated human queue receipt; do not claim a human was contacted. |

Mutation retries reuse the same idempotency key and reconcile by reading first.
Use a maximum of one automatic retry for transient reads; do not blindly retry a write
after a timeout. Record `unknown_outcome` and reconcile or hand off if necessary.
No raw transcript needs to be persisted to explain the outcome.

## Grounding and data contracts

- Use decimal money and explicit currencies, never floats or unstated conversion.
- Keep original transaction status/date/amount/merchant. Missing merchant or uncertain
  status is unknown; a policy reason, refund promise or dispute deadline cannot be inferred.
- Source evidence includes table, record/version ID, snapshot/as-of time and available fields.
  User text and free-text records are untrusted data, never new tool instructions.
- Transactions need stable transaction/customer/product IDs, parseable timestamps,
  supported status and currency, and finite decimal amounts. Validate actual values
  before picking an allowed enum; the dictionary may differ from sampled data.
- Intake links are newly created by this simulated app. The source complaints schema
  has customer/product/interaction keys but no transaction ID (Dictionary pp. 12-13, 15-16).
  Never fabricate that historical link or train on resolution/compensation fields as inputs.
- Label source fixtures separately from team-authored test/demo fixtures. Snapshot the
  source subset, deduplicate exact copies, quarantine conflicting IDs, and preserve lineage.
  Enforce customer-product-transaction ownership consistency before serving source rows.
  The full local audit verifies owner/currency joins but finds 1,450,689 transactions
  predating current product opening or customer registration. Quarantine chronology
  conflicts; never silently rewrite source dates or infer historical versions. Select
  a small private cohort that passes this contract, as detailed in local_data_review.md.
- Define the displayed data's `as_of`; do not call 2023-2026 snapshots live bank information.
  Replay a separate, labeled update fixture with duplicate delivery, stale versions and
  conflicting records. An update must invalidate pending drafts when relevant facts change.

## Deployment preparation for a later session

Deploy only allowlisted, independently authored demo fixtures unless redistribution
permission is confirmed. Use server-minted demo sessions, disable open registration,
keep source access credentials out of the deployed app, cap request size/rate and work,
and restrict the simulated case viewer to its owner. Plan ephemeral or short-retention
demo records, documented reset behavior, safe errors and trace IDs. Decide exact hosting
and storage limits when deploying; none are selected or paid for this session.

Traces contain safe outcome/status codes, component and policy versions, tool timings,
attempt counts, source references, and verified execution receipts. Do not record secrets,
full source records, private prompts, or hidden chain-of-thought. The final report must
distinguish a small evaluated prototype from production authentication, security or capacity.
