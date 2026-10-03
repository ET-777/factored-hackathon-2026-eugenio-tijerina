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

## Plain inquiry correction, October 3

An owner screenshot showed the learned preview refusing the short request
«ver un pago». A bounded TRAIN-only diagnostic reproduced that raw prediction;
«quiero ver un pago» was instead classified as dispute intake, and analogous
Portuguese requests could be classified as human requests. The normalized model
score was high for some wrong answers, so it cannot establish correct intent.

The shared conversation now recognizes complete plain read/search requests such
as «ver un pago», «quiero consultar una transacción» and «ver um pagamento» before
either router. It requires a read verb and a transaction noun, accepts bounded
polite wording, and excludes negation, consent, support-case requests and unknown
or mixed tails. Missing details are still requested; no fixture amount, currency
or record is supplied automatically. A new read request replaces an unfinished
dispute instead of inheriting its intake intent. Explicit selected-record
references still require the real server-owned selection.

This is another shared conversation rule, not model retraining or evidence of
improved classifier accuracy. The classifier implementation, training data,
development workload and first scores remain unchanged. Unfamiliar or mixed
wording continues through the experimental router; general language coverage is
still limited. New isolated HTTP regressions use the unchanged local TRAIN model
with fictional records and verify the screenshot sequence, bilingual detail
collection and withdrawal of unaccepted dispute proposals without writes.

After narrowing the guard to exclude ambiguous «revisar» requests, the full suite
passed **469 tests**. The scoped privacy check passed 107 eligible files with zero
violations and eight of eight exclusion probes. All seven protected artifact
hashes still match the pre-fix checkpoint; original final contents remain unread.

## Human-request boundary correction, October 3

The owner then reported unrelated messages («quiero comer» and «hello») preparing
human-handoff drafts. A TRAIN-only diagnostic reproduced both raw predictions as
`human_request`. The classifier has no reliable general out-of-domain detector:
familiar character fragments can receive a winning intent even when the message
does not express a banking request. A model score cannot establish a customer's
request to prepare a ticket.

The shared workflow now requires a complete positive human-request clause before
preparing a handoff from chat. It supports bounded Spanish/Portuguese request
wording and human-contact shortcuts. Negated or narrative mentions do not qualify;
an explicit refusal to prepare a ticket also vetoes preparation. When only the
classifier predicts a human request, unclear wording receives a scope clarification
without creating a new draft or handoff offer. An explicit human request can override a wrong valid model label,
but permissions, source checks and the separate final confirmation still apply.
Prior search, selection, banking issue and unaccepted consent offers are preserved
when the classifier alone predicts a human request. Existing consent-bound
escalation for ineligible intake and previous-case continuation is unchanged.

Standalone «hello», «hi» and «hey» are greeting aliases, answered in the selected
Spanish or Portuguese language. Mixed greeting/business messages still go through
request handling; this does not add English business-language support.

These are conversation-policy repairs, not retraining or general language
understanding. The raw model, TRAIN/DEV labels, first measured scores and protected
evaluation artifacts remain unchanged. The new regression includes the screenshot
sequence through isolated HTTP with the existing TRAIN model and fictional
records, plus forced wrong predictions, negation/narrative wording, preserved
context and separate confirmation of explicitly requested human drafts.
Other model-predicted intents retain their existing handling; this boundary does
not establish reliable detection of every unrelated message. Synthetic diagnostic
assertions that previously expected model-only handoff drafts now expect no case
and incomplete workflow results. The frozen driver, scoring rules and first-run
artifacts were not changed or rerun.

The complete suite passed **485 tests** after this correction. The scoped privacy
check passed 108 eligible files with zero violations and eight of eight exclusion
probes. All seven protected artifact hashes matched their original checkpoint.
Original final contents, dictionary credentials and private source rows were not
read in this increment; no provider calls, public release or deployment occurred.
