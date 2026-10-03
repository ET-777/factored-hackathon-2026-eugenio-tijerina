# Authored routing workload: training and development drafts

Status: **draft_pending_owner_and_portuguese_review**. These files are Codex-authored
requests for the selected four-intent routing task. They are engineered examples,
not observed customer demand, representative production language, or a
human-validated benchmark. No fitting, threshold selection, performance scoring,
new final-case authoring, or final freeze was performed while creating them.

## Why authored messages are justified

The selected workflow answers questions about supplied transaction records,
prepares confirmed simulated dispute intake, and supports useful human handoff.
The source-intent inventory could not supply the required intent/language coverage.
The October 2 organizer reply, documented with its screenshot limitations in
[source_intent_inventory.md](source_intent_inventory.md), permits the scoped plan
for justified authored ES/PT evaluation inputs using supplied transaction records
and separately labeled simulated safety/tool failures. This is not blanket
permission for fictional bank rows, unsupported production claims, external model
providers, or redistribution of source data.

The public messages below contain no source rows, customer/product/transaction
identifiers, merchant names, amounts, balances, currencies taken from a record,
dates, or other copied record values. Ordinary banking vocabulary describes a
request; it is not asserted as a fact about a supplied row. Customer statements
about authorization, cancellation, non-delivery, or a failed withdrawal are
authored allegations to be recorded as such, never verified bank outcomes.

## Artifacts and annotation rule

- [routing_train.json](../evaluation/routing_train.json): 96 messages in 12 families.
- [routing_development.json](../evaluation/routing_development.json): 32 messages
  in 8 different families.

Both files use `schema_version: 1`, `provenance: codex_authored`, and the pending
review status above. Each example has an ASCII `id` and `family_id`, a language
(`es` or `pt`), text, and one intent. The author read the selected scope, the
source-intent annotation rubric, and evaluation readiness gates. The author did
not inspect baseline patterns, candidate predictions, trained weights, source
utterances, the old diagnostic development cases, or final-case contents for this
increment. Wording was not selected to favor a particular classifier.

| Intent | Positive evidence in the authored request |
|---|---|
| `inquiry` | Find or explain recorded details/status of an existing transaction. Missing record facts remain an answer/clarification concern, not a different intent. |
| `dispute_intake` | Describe an existing charge as unrecognized/incorrect or explicitly request its review/contest. The label permits no mutation and says nothing about eligibility or a refund. |
| `human_request` | Explicitly ask for a person, agent, or human review. Routing does not imply consent to share a packet or that a handoff has occurred. |
| `unsupported` | Clearly request another service/action, such as balance lookup, a new transfer, card suspension, credit-limit change, or password reset. |

All four labels describe the user's requested service, not action authorization.
Identity, ownership, consent, confirmation, idempotency, and receipt verification
remain external to both routers. A bare affirmative, greeting, vague request,
negated service request, or unresolved mixture of intents is not forced into one
of these gold-label candidates. Those inputs belong in separately labeled
clarification/state/safety diagnostics. Broader out-of-domain requests and prompt
injection diagnostics likewise need their own declared handling expectations;
this small clean-intent workload does not measure them.

## Counts and family grouping

| Split | Families per intent | ES per intent | PT per intent | Total |
|---|---:|---:|---:|---:|
| Training | 3 | 12 | 12 | 96 |
| Development | 2 | 4 | 4 | 32 |

Each training family contains four Spanish variants and four Portuguese variants.
Each development family contains two Spanish variants and two Portuguese variants.
Translations and close paraphrases share the same family ID within the same split.
Family IDs and normalized message text are disjoint between the two files. Do not
shuffle individual messages across splits or count translated variants as
independent scenario families.

| Intent | Training family topics | Development family topics |
|---|---|---|
| Inquiry | Original amount/currency; stored status; merchant identity | Recorded time/channel; overall record summary |
| Dispute intake | Unrecognized purchase; duplicate charge; cancelled subscription still charged | Cash not dispensed; goods not received |
| Human request | Preference for a person; repeated self-service attempts; guided conversation | Written packet for human review; continuity of an existing case |
| Unsupported | Account balance; executing a new transfer; suspending a card | Credit-limit increase; resetting login credentials |

The development situations were authored separately from the training families,
rather than splitting translations or assigning new IDs to the same request
template. Shared intent concepts and normal banking words are unavoidable. A
family ID or a no-duplicate check does not prove semantic independence. Review
should reject or regroup a family if it is merely a renamed paraphrase of another.
In particular, the record-summary family is deliberately broad and may encompass
facts also mentioned in training; report that overlap in task semantics rather
than claiming an entirely unseen service.

The balanced class counts are an experimental design choice, not a prevalence
estimate. Only two development families per intent remain after grouping; 32
messages must not be described as 32 independent situations. Portuguese wording is
authored in a broadly Brazilian register and has not been validated by a fluent
human reviewer. Regional coverage, spelling noise, code-switching, speech
recognition errors, and real customer diversity are unmeasured.

An independent Codex reviewer checked all 128 messages against the rubric without
viewing classifier rules or predictions and found no forced-label ambiguity or
wording correction. That review confirmed the shared semantics of the broad
development summary family and the training inquiry families, and the distinction
between withdrawal-dispute intent and the demo's purchase-only intake eligibility.
It does not establish human/native language validation; the pending JSON review
status is unchanged. The owner's Spanish-only checklist is
[routing_review_es.md](routing_review_es.md), containing all 64 ES messages with
their proposed labels and family grouping. Portuguese human review remains pending.

## Pure routing versus private service checks

Pure intent classification consumes only `text` and the selected language. Its
labels can be reviewed without seeing any bank record. It does not demonstrate
grounding, task completion, safe actions, source coverage, or useful handoff.
Deictic wording such as “this transaction” assumes the UI's selected transaction;
it neither supplies an ID nor authenticates the speaker.

For separate service checks, bind an approved authored request privately to a
compatible record in the existing validated **50-record source cohort**. Record
binding belongs in ignored local metadata, with the supplied row/source hash,
trusted test session, selected record reference, and the message's provenance kept
separate. Preserve the source amount, native currency, recorded status, merchant
availability, dates, ownership, and snapshot limitations exactly. Do not create
fictional bank rows or alter source facts to make an authored message work.

An allegation about a withdrawal needs a compatible existing withdrawal for an
end-to-end service case; an allegation about a purchase needs a compatible purchase.
If the cohort lacks a compatible record, mark that proposed service binding
unavailable before protocol freeze. Do not invent a match, silently drop a failure
after execution, or imply the source validates the allegation. Existing-case
continuity may use a separately labeled app-created simulated case with verified
receipt provenance; it is not a reconstructed historical bank complaint.

The current demo intake is restricted to eligible purchases. The withdrawal
development family correctly expresses `dispute_intake`, but a service check must
expect the external eligibility guard to decline intake and offer an appropriate
human path. A correct routing label is not a promise that a simulated ticket can
be created for every transaction type. Preserve this distinction in any later
workflow oracle instead of changing the intent label to fit tool eligibility.

Any read/write failure, timeout, duplicate confirmation, expiry, or receipt mismatch
is a separately tagged diagnostic configuration. A simulated failure must not be
reported as a historical source event. Public classification texts remain generic;
private service traces must not expose raw source records or identifiers.

### Private binding builder

[bind_routing_workload.py](../scripts/bind_routing_workload.py) creates proposed
context anchors from these two fixed authored files and one explicitly supplied,
already validated bounded cohort run. It does not route requests, fit a model,
produce predictions, score development, open final cases, or execute a workflow.
The fixed artifacts are capped at 256 KiB and 256 examples each, with strict keys,
labels, language/text validation, label-consistent families, and no cross-split
ID/family/normalized-text overlap. `load_private_cohort` applies its existing
200-record table cap, record/link validation and provenance-structure checks.

The builder deterministically matches one compatible source customer/transaction
to each family, with translations sharing that anchor. Withdrawal families are
allocated first, eligible-purchase dispute families next, and context-only families
last. Customer-level matching can reassign earlier compatible choices to avoid
unnecessary allocation failures. Bound customers and transactions are disjoint
across both splits and all families. An unsupported-service context anchor does
not make the requested service, balance, or other unavailable fact accessible.

When no disjoint compatible anchor exists, every affected example remains present
with `binding_unavailable`, null context/hash/eligibility, and a fixed reason code.
It is not relabeled, removed from the denominator, or supplied a fabricated row.
Eligibility is explicitly the synthetic Purchase + Approved/Pending rule;
Withdrawal remains ineligible. It does not bypass permissions or confirmation.

The output is exclusively created at ignored
`data/routing_workloads/<run-name>/bindings.json`; an existing run is never
overwritten. It records exact authored-artifact and bounded cohort input hashes,
the original CSV hashes already recorded in the cohort manifest, per-anchor source
row references/hashes, and a canonical snapshot hash matching the runtime action
snapshot. Original CSVs are not reopened or rehashed. Scorer intent and eligibility
live under `scorer_metadata`; the future system input may use only the independently
loaded message and `system_context`, never that label metadata. The customer ID is
a proposed trusted test-session configuration, not proof of a logged-in user.

CLI output consists only of aggregate counts or fixed failure codes. Fixed authored
input paths, the ignored private output root, and the run directory must resolve
exactly to their intended lexical locations under the resolved project root.
Symlink or junction redirection is rejected even when its target remains elsewhere
inside the project, preventing alternate input selection or private output outside
the intended ignored directory.

The builder has 21 focused tests using authored in-memory records, temporary cohort files, and
loader patches, including runtime snapshot parity, disjointness, unavailable
bindings, incompatible statuses, changing inputs, exclusive output, in-project path
redirection with mocked resolution for Windows portability, and error
privacy. These checks prove the binding contract only. They are neither routing
performance nor end-to-end workflow evidence. The binding implementer did not
execute it against source data. The parent agent then ran it once on the existing
validated 50-record `june17-v1` cohort: all 96 TRAIN messages (12 families) and all
32 DEVELOPMENT messages (8 families) received disjoint compatible anchors, with
zero unavailable examples. No bound workflow case was executed or scored. See the
[aggregate availability evidence](../evidence/routing_bindings_summary.json).
Actual contexts, identities, source references and hashes remain ignored under
`data/routing_workloads/authored-routing-v1/`.

To create a fresh private binding run locally, use one physical PowerShell line:

```powershell
python -B -m scripts.bind_routing_workload --cohort-run data/private_cohort/june17-v1 --run-name authored-routing-v1
```

An existing run name is refused; use a new name for any deliberate later revision
and retain the prior record. This command prepares contexts without evaluating them.

## Review and comparison readiness

1. An independent Codex reviewer checks label clarity, family grouping, translations,
   and Portuguese phrasing without viewing classifier rules, predictions, or scores.
   Record concerns and corrections; this is a second model review, not independent
   human validation.
2. Keep both artifacts marked as pending owner and Portuguese review. A reviewer
   should accept, correct, or quarantine unclear examples under the fixed rubric;
   do not resolve ambiguity by observing which router predicts a desired answer.
3. The current increment permits a fixed training-only fitting preview after the
   independent semantic draft review, under the root agent's shared protocol.
   Keep this draft provenance visible. Development remains unscored; no threshold
   selection or final scoring is part of that preview. It cannot be represented
   as final performance or native-language validation. Do not rewrite development
   messages, labels, or the baseline after seeing results to manufacture a gain.
4. Before a submission-grade comparison, finalize reviews, group assignments,
   compatible service bindings, and a declared protocol. Both routers must share
   records, state, permissions, tools, failure accounting, and scoring. Report
   per-language/per-intent support, errors, and abstentions; preserve unsuccessful
   attempts. A routing gain is not a verified service-completion gain.

No classifier score appears in these files. No observed result justifies changing
their labels or coverage because no system was run during authorship.

## Abstract proposal for a future final workload

A possible future source-grounded final workload is **32 messages: four intents ×
two newly reviewed scenario families × two languages × two variants**. That would
provide 16 ES and 16 PT messages, 8 per intent, but only eight family groups, so
uncertainty would remain substantial. This is a count proposal only. No final
wording, IDs, labels, source bindings, case file, commitment, or freeze was created
for it in this increment.

A separately authorized final protocol would require fresh family review,
independent authorship/scoring where practical, compatible supplied-record
bindings for service checks, and a commitment before system access. It must disclose
remaining author/reviewer overlap and constructed-data limits. The existing sealed
final workload is preserved: this proposal neither opens nor replaces it and does
not authorize a final run.
