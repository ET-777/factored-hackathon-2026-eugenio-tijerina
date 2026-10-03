# First routing development comparison

Protocol version: **development-v1**, declared October 3, 2026 before development
prediction or scoring. This is a development diagnostic, not final evaluation.
The runner requires this file's SHA-256 and saves it with implementation/input
hashes before fitting or inference. Later changes require another protocol/run;
initial results and failures must be retained.

## Evidence and population

Organizer permission covers authored ES/PT customer requests evaluated against
supplied transaction records, with separately labeled simulated fault scenarios;
see [source_intent_inventory.md](source_intent_inventory.md). The following
protocol, targets and automation choices are project decisions.

Use the unchanged 96-message TRAIN artifact and all 32 DEVELOPMENT messages:
16 Spanish and 16 Portuguese, four intents, eight development families. Source
transcripts do not cover these four classes or Portuguese. Requests are authored,
balanced and unlike representative production traffic; source facts are supplied
by the bounded, validated 50-record private cohort and existing private bindings.
Translations/paraphrases share a family and record; customer and record anchors
are disjoint across TRAIN/DEVELOPMENT families. Distinct family IDs do not prove
semantic independence. The author and technical reviewers have seen wording;
this is not a blinded benchmark.

Spanish wording/labels have owner approval, bound to exact artifact hashes.
**Spanish (16 messages, eight families) is the primary development diagnostic.**
Portuguese (16) is exploratory: fluent-human wording/label/output review remains
pending. Combined 32-message figures are descriptive and mix review quality.
Output semantics and human-handoff usefulness still need human review in both
languages. Mechanical checks alone cannot close those gates.

Do not read original `evaluation/final_private/`, run the old fictional-record
workload, or create a replacement final set. No external inference, API charges,
publishing or deployment belongs to this run. Original source CSV/PDF files are
not read; manifest source hashes are inherited, not independently rehashed.

## Frozen systems and execution

- Baseline: unchanged bilingual `routing.route_intent` keyword rules.
- Candidate: unchanged character 3-5 gram multinomial naive Bayes, alpha=1,
  empirical priors, trained once on 96 TRAIN text/label rows only. Shared text
  normalization and existing abstention rules; no threshold or parameter search.
- Same records, trusted identity, three explicit permissions, deterministic UTC
  clock, response templates, conversation controller, tools and oracles. The
  classifier sees only request text and selected language, never source facts,
  eligibility, gold label or scorer metadata. Scores are not calibrated.
- Exactly one component attempt and one workflow attempt per example/system:
  64 of each. Sort example IDs; alternate which system runs first within pairs.
  No retries, best-of selection, route repair or tuning after outcomes.
- Every workflow starts with a fresh browser session and SQLite store. Set
  language and directly select the bound authorized transaction as context before
  the scored authored turn. This setup is excluded from completion and timing:
  it evaluates routing/service with established context, not record discovery or
  end-user authentication. Its answer cannot earn a scored inquiry pass.
- Follow actual surfaced controls only. At most one date clarification, using
  the bound source transaction date; choose that record only if returned among
  candidates. Accept an actual intake-preparation offer or prepare an actual
  offered human handoff, then explicitly confirm a displayed draft and repeat
  that confirmation once to verify idempotency. Maximum eight scored actions.
  Gold labels choose the final oracle, never the system path or a corrective
  action. An unsurfaced fallback is not available to the driver.
- Unavailable bindings, malformed proposals, errors and incomplete journeys stay
  in the declared denominator. Report missing timing observations. No failure
  outcome is silently replaced with a successful fallback or another record.

## Component scoring

Four fixed labels: inquiry, dispute_intake, human_request, unsupported. A valid
unmatched proposal is **ABSTAIN**, incorrect even for gold unsupported. An error
or malformed proposal is an error plus ABSTAIN. Report all four classes' support,
precision, recall and F1, 4x5 confusion matrix, accuracy, coverage, abstentions,
errors and fixed-four-class macro-F1. Report an entire family correct only when
all its messages in that population are correct. No confidence threshold is
selected; no independence-based confidence intervals or superiority claims.

Report paired candidate-minus-baseline differences and counts where only one
system is correct. Candidate consideration requires at least +0.05 Spanish
macro-F1 and one additional correct Spanish component attempt, no ES or PT
mechanical completion regression and no observed confirmation/receipt invariant
failure. These are predeclared development criteria, not final acceptance or
evidence of production benefit. Portuguese human review remains a separate gate;
the default UI is not automatically changed by this script.

## Mechanical workflow oracles

- Inquiry: a **new scored** answer must reproduce required native record facts,
  with matching source references in the selected-record evidence returned to
  the UI, preserve language, and write no case. A request containing `canal`
  must explicitly state that channel is unavailable; a generic record summary
  cannot earn full completion. Time-only requests require the supplied timestamp.
- Eligible purchase dispute: retain the original authored allegation as
  unverified customer input; preparation and final storage require separate
  affirmative steps. Exact source facts/references and verified consented receipt
  must match one persisted simulated intake. Duplicate confirmation returns that
  same case. This is ticket intake, not a refund or resolved dispute.
- Withdrawal dispute: no ineligible intake may be saved. A safe eligibility
  refusal is measured separately from completion. Completion would require an
  actually offered, consented, verified useful handoff; the current controller
  offers intake then blocks it without that fallback. Count this limitation.
- Human request: original request, language and authorized selected record facts
  in one consented simulated handoff, source snapshot match and verified readback.
  Existing-case continuity must not invent earlier case status/history; fresh
  stores have no earlier verified actions. Human usefulness remains unreviewed.
- Unsupported credit-limit/password service: explicit unsupported outcome and
  actual surfaced handoff, affirmatively consented and verified by the driver. No
  account/credential change. An unsupported branch may clear record selection;
  a packet without transaction facts is correct here.

The fixed scripted user accepts every preparation offer and confirms every
resulting draft once, then repeats confirmation once. Unsupported completion
requires both the explicit unsupported response and the verified offered handoff;
an offer alone is recorded separately and does not earn full completion.

Separate completion, grounding, request preservation, simulation/consent,
pre-confirmation write count, verified readback and duplicate persistence. Report
each boolean's applicable denominator, genuinely inapplicable checks and
unassessed checks on unavailable/failed cases. Check-pass rates are conditional
on observed applicable checks; completion always uses all attempts. Language
tags are structural checks, not fluent language validation. These clean paths
do not test cross-customer access, expired sessions, corrupt records or tool
faults; existing synthetic regression tests are separate software evidence.
Do not call this a comprehensive safety or end-to-end service benchmark.

## Timing, outputs and follow-up

Component time covers one route call; workflow time covers scored controller
actions and local SQLite checks, excluding setup, fitting, loading, human think
time and network/UI transport. Report observed median and nearest-rank p95 with
attempt/missing counts, Python/platform/CPU context. This in-process run does not
measure deployed latency. No remote API calls occur; API charge is zero, while
local hardware/electricity costs are not measured.

Write an exclusive ignored `.local/evaluation_runs/<run-name>/` directory. Save
the frozen manifest first, then sanitized per-case proposals/status codes/checks
and aggregates. Temporary private SQLite stores are checked in place, then
closed and removed; source bindings and hashes allow reconstruction. Never serialize source
identities, facts, prompts, receipts or exception strings into result logs.
Publish only aggregates and hashes of the binding/cohort/input/code artifacts,
never their private contents. Keep any interrupted run, with its manifest and
partial evidence, and use a new run name only for a documented harness defect.

After the first measurement, report what improved, what failed and what remains
unreviewed. Prioritize concrete failures, then authorize/freeze a genuinely
separate source-grounded final workload before final scoring. Deployment, slides
and the maximum-three-minute video remain submission deliverables.
