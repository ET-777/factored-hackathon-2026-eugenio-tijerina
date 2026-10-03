# Shared workflow fixes after the first development run

October 3, 2026. These changes address failures observed in the first frozen
development comparison. They are post-development fixes, not another benchmark.
The [first results](development_results.md), frozen protocol, TRAIN/DEV messages,
labels, classifier configuration and final-set commitment remain unchanged.
The final case contents were not opened.

An inquiry still answers from the validated transaction record. If a customer
explicitly asks for the channel, the response now says that the available record
does not report it. That question is retained through date/amount clarification
and candidate selection. Ordinary approved-payment answers receive no extra
channel disclaimer. This describes the validated record exposed by this adapter;
it is not a claim that every raw source table lacks a channel field.

A request to dispute a transaction outside the simulated intake's purchase/status
eligibility now explains that limit and offers a grounded human summary. The
customer can accept or decline that offer. Accepting prepares a draft in the side
panel; only a separate confirmation saves a simulated handoff and returns a
verified receipt. The original customer issue and available record evidence are
preserved. No refund or bank dispute is filed.

Explicit requests to follow up on a previous support case are intercepted before
either router can treat them as a new dispute. The assistant states that it cannot
verify prior bank-case history. A handoff labels the prior-case reference as
unverified; a transaction shown in this session is supporting context, not proof
that it belongs to the claimed old case. Receipts from this browser session are
distinguished from inaccessible prior bank history. This is a bounded wording
guard, not general recognition of every possible follow-up expression.

The shared service still enforces permissions, record ownership, current
selection, source snapshot, offer expiry, preparation consent and final action
confirmation outside the model. A stale offer cannot silently switch to a newly
selected transaction. Missing human-handoff permission produces an explanation
without a draft or write. Short affirmative replies accept preparation only.

## Verification and interpretation

The full standard-library suite passed: **452 tests**, including five isolated
HTTP tests for the new handoff flow. The UI JavaScript passed Node's syntax check.
The eligible-file privacy check found zero violations across 104 files and all
eight exclusion probes passed. That check did not read dictionary credentials or
scan Git history. All seven protected protocol, workload, review and first-result
artifact hashes matched their pre-fix values.

The regression tests use separately authored fictional records, including
ineligible transactions and permission/stale-offer scenarios. They are engineering
diagnostics, not source-backed customer demand evidence or submission performance
scores. HTTP checks exercise the real local endpoints and confirmation path.
Portuguese tests check the technical contract and fixed wording; fluent human
review remains pending.

No new development-score run, source-data access, external model call, deployment
or final evaluation was performed. The first measured scores continue to describe
the earlier frozen code, not these fixes. A new comparison requires a separately
documented protocol and code freeze.

## Local review

Restart an already-running server to load the updated Python code, then reset the
browser session. The owner's ignored learned-preview launcher remains:

```powershell
python -B .local\learned-preview\start_review.py
```

Review these interactions in Spanish (and Portuguese when a fluent reviewer is
available):

1. Ask about a transaction's channel, provide search details and choose a result.
   The answer should preserve the facts and explicitly report the channel limit.
2. Ask to review a selected ineligible transaction. Decline the human offer once;
   then accept it, review the side-panel draft and confirm separately.
3. Ask to follow up on a previous support case. The assistant should acknowledge
   the unknown history and offer human review, without creating a new dispute.

The private-cohort launcher may select an eligible purchase by default. The
ineligible branch is covered by the isolated regression fixtures; do not alter
source records merely to make that branch appear in the live preview.
