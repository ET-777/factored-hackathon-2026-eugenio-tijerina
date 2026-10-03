# Local workflow review checkpoint

Implemented with Codex assistance on 2026-09-28 after the owner authorized complete
implementation increments. The owner's record adapter, private cohort loader,
transaction lookup, selection and bilingual response code are retained. This milestone
adds the conversation controller, simulated action service, SQLite store and a runnable
synthetic demonstration. It does not establish classifier performance or final-set success.

## Run it

From the project directory, with Python 3.11+ and no extra packages:

```powershell
python -B -m bank_service demo --language es
python -B -m bank_service demo --language pt
python -B -m unittest discover -s tests -q
```

The scripted demonstration uses three independently authored transactions. Two are
owned by the trusted demo customer and match the same amount/currency. It asks for a
choice, explains the chosen record, prepares an intake, explicitly confirms it,
repeats that same confirmation, then prepares and confirms a simulated human handoff.
It also attempts a foreign record and an expired-session read. Scripted consent is
clearly labeled: it is never inferred from a customer phrase or a model response.

Expected complete-demo summary: **two new cases**, **one reused intake receipt**,
and **two access denials**. Case IDs are newly generated each run. The handoff packet
contains permitted facts, evidence, attempted steps, prior verified receipts and open
questions. A queue receipt means local simulated storage; nobody is contacted.

The default temporary database is removed when the demo ends. To keep only these
fictional demo cases for inspection, use:

```powershell
python -B -m bank_service demo --language es --db .local/demo/cases.sqlite3
```

The database is ignored by Git. A new invocation makes new request IDs, so it creates
new cases; duplicate protection applies to repeated delivery of the same request.
`--scenario inquiry`, `intake`, `handoff` or `safety` runs a smaller demonstration.
Every scenario begins with inquiry and clarification. No source data, private cohort,
development/final evaluation content, credential, network service or model is read.

## How the pieces connect

| Module | Responsibility |
|---|---|
| `records.py`, `cohort_repository.py` | Validate source records and bounded private cohort provenance. |
| `access.py`, `transactions.py` | Authorize the trusted session against the actual record owner. Separate read, intake and handoff grants. |
| `selection.py`, `responses.py` | Exact bounded search and grounded ES/PT plain-text answers. |
| `conversation.py` | Keep candidate IDs, selected ID, language, pending action and bounded attempt codes across turns. |
| `actions.py` | Prepare exact drafts, check explicit consent, reauthorize, check freshness, reconcile and verify persisted outcomes. |
| `case_store.py` | Parameterized local SQLite storage with a unique request key and atomic case creation. |
| `demo_fixtures.py`, `demo.py` | Independent fictional records and a reproducible demonstration of these real code paths. |

## Confirmation and verification

Drafts belong to the exact server-owned session instance. A customer ID, equal-looking
session object, candidate ID or draft ID alone grants no access. The draft records the
operation, transaction facts/provenance, reason, language and expiry. Intake eligibility
is a **synthetic demo rule** for an Approved/Pending Purchase, not organizer banking policy.

Preparing a draft writes no case. Confirmation must be an actual Boolean bound to
the pending draft ID. The controller clears old pending actions on a new search,
selection or language change. The service checks permission, expiry and record changes
before creating a new case. A fresh draft is needed after relevant source changes.

A stable draft/request ID is the idempotency key. A successful database call alone is
insufficient: readback must match the full expected payload, owner, operation and state
before the service returns a success receipt. A failed/uncertain write or readback is
an unknown outcome. The same request can reconcile by reading the stored result;
blind repeated writes are not the recovery mechanism. Cancellation never undoes an
already-created case and must not falsely report that no case exists.

All outputs are plain text; a later UI must escape/display them as text. Merchant
names and user reasons remain quoted data. The handoff has an explicit consent step
and a separate permission; reading records cannot authorize creating a case.

## What to review as owner

1. Run both languages. Explain why the first search asks for a choice and the answer
   comes only from the chosen record.
2. Identify the draft/confirmation boundary and the verified receipt. A receipt is
   simulated intake completion, never a refund, adjudication or a live bank action.
3. Check that duplicate confirmation returns the same receipt and creates one intake.
4. Read the handoff packet: does it give a human enough context without a raw transcript?
5. Inspect the safe denial paths and acknowledge any Portuguese wording needing review.

## Historical CLI verification and limits at that checkpoint

Verification on 2026-09-28: **191 tests passed** with
`python -B -m unittest discover -s tests -q` (155 existing tests plus 36 new
action/store, conversation and demo checks). The tests cover both languages, consent,
cancellation, stale records, permissions, receipt corruption, uncertain-write recovery,
duplicate delivery and reopening persisted storage. The CLI also emits valid UTF-8
when redirected on Windows. Both full-language demonstrations completed with the
expected two cases, duplicate receipt reuse and two safe denials.

Independent synthetic review reproduced and resolved lost recovery tokens after
failed readback, mismatched requested-case IDs, and incomplete stored receipts after
restart. This was a second implementation review, not an independent final benchmark.
Eight protected source/fixture files matched their before-edit SHA256 values.
The scoped artifact checker passed 53 eligible files and 8/8 exclusion probes, with
no dictionary access or exact-credential comparison; it does not scan Git history.
Backups of edited existing files are under the ignored
`.local/review_backups/workflow-20260928T232229/` directory.

- The controller accepts structured commands. The later loopback UI adds keyword
  routing, bounded slot extraction and an experimental learned router. Their
  comparative evaluation remains pending.
- This is a local library plus scripted CLI, not a deployed web application. Trusted
  sessions are server-created demo objects, not an authentication provider. Serialize
  turns for each conversation; concurrent web serving has not been qualified.
- Draft/conversation state is in memory. SQLite cases survive restart, but pending
  conversations and confirmations do not. Durable draft recovery is not claimed.
- The public development fixtures use an independent scenario schema (including
  `MXN`/`BRL` and statuses such as `posted`). The owner subsequently requested
  transaction support for MXN, COP, ARS and USD; BRL and the remaining scenario
  schema differences still require explicit handling. A later fixture/domain adapter
  must preserve those native facts. Do not silently map `posted` to `Approved`, change
  final cases, or weaken source validation to make the evaluation pass.
- Unit/integration tests and demo runs do not count as the 19-case development or
  sealed 32-case final evaluation. Neither split is run by this demonstration.
- Portuguese templates remain drafts until reviewed fluently. Source freshness/version
  replay, complete operational tracing and production retention/capacity controls remain
  separate work; draft fingerprint checks alone do not prove a complete update pipeline.

The subsequent [local UI checkpoint](local_ui.md) adds the loopback interface and
keyword baseline; the above 191-test result remains historical CLI evidence. The current
increment connects the existing validated private cohort to a separate [loopback UI](private_cohort_ui.md)
mode, with identity and permissions from trusted startup configuration, exact native
record facts, simulated actions and private evidence. The fictional demonstration
remains unchanged; the full dataset is not loaded behind the app.

The scoped generated ES/PT evaluation plan now has organizer permission with
justification; see [evaluation.md](evaluation.md). Reviewed labels, independent families,
Portuguese review and the comparison protocol remain pending. The [scenario
adapter](evaluation_adapter.md) is deferred diagnostic work. The later [learned
preview](learned_routing.md) fits the authored TRAIN draft locally without scoring
development. Next complete human review and declare the shared source-grounded
comparison protocol. No comparative performance, public release or deployment is
claimed. Keep the existing
final set sealed; any new source-grounded final workload requires a separate authorized
freeze rather than changing old cases to fit the implementation.
