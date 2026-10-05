# Frozen workflow comparison, October 4

The local learned router improved standalone intent recognition but **failed the
declared workflow qualification targets**. Keep keyword routing as the default;
the unchanged naive Bayes v2 preview remains optional. No model, app, case or
oracle was changed after the run, and no attempts were repeated.

The [protocol](final_workflow_protocol.md),
[preparation commitment](../evidence/final_workflow_preparation_v1.json) and
[freeze](../evidence/final_workflow_freeze_v1.json) precede predictions.
[Saved aggregate evidence](../evidence/final_workflow_results_v1.json) retains
both systems, all denominators, confusion matrices, paired changes, checks and
timing. The exclusive private run is `.local/final_workflow_runs/final-workflow-v1`.
Its private request text, record facts, source references, drafts and receipts
remain outside Git. The original fictional-record final set stays unopened.

## Observed results

Each system attempted 32 balanced service component probes and 48 fresh HTTP
journeys: 16 service and eight safety journeys per language. Both used the same
validated supplied records, server-owned scopes, guards, templates and fixed
clock. Neither started with a selected transaction. TRAIN144 was fitted once
for naive Bayes v2, using unchanged character 3–5 counts and alpha 1.

| Measure | Keyword baseline | Naive Bayes v2 |
|---|---:|---:|
| Spanish component correct | 8/16 | 11/16 |
| Spanish component macro-F1 | 0.5143 | 0.6875 |
| Spanish strict service completion | 10/16 | 8/16 |
| Portuguese component correct, provisional | 6/16 | 12/16 |
| Portuguese component macro-F1, provisional | 0.4768 | 0.7431 |
| Portuguese strict service completion, provisional | 7/16 | 9/16 |
| Safety journey completion, each language | 1/8 | 1/8 |

Spanish component routing gained five correct probes and lost two, net three.
Portuguese gained six and lost none. Spanish service journeys gained two
completions and lost four, net minus two; Portuguese gained four and lost two,
net plus two. Component probes have no conversational context, including two
families whose guarded journeys first discover a record. Do not treat the two
measurements as interchangeable or statistically independent evidence.

The Spanish minimum 12/16 service completions and both-language workflow
nonregression criteria failed. The declared component improvement criterion
passed; the workflow improvement criterion failed. No router promotion follows
this result. Small authored balanced samples do not establish production rates.

Across all 48 observed journeys per system, the mechanical checks found no
unauthorized disclosure/write, early write, duplicate persisted case or
success-status claim without verified readback. **This is not full safety
qualification:** six of the eight intended fault conditions were never reached.
Their absence of a violation cannot prove the unexercised protection works.

## Diagnosis and coverage limits

A read-only inspection of original saved evidence identified a shared discovery
gap: none of the 24 bound native source identifiers match the text parser's
accepted bare-ID formats. Twenty-two of 48 scripts send a bare identifier;
these 44 paired attempts could not use that message to select their record.
The app routes it as ordinary text. The workload author assumed this discovery
path worked without executing it; both that assumption and the app limitation
are disclosed. Earlier preselected development runs did not test this path.

| Intended fault condition | Reached across both systems and languages |
|---|---:|
| Foreign-record access denied | 4/4, HTTP 403 |
| Expired session denied | 4/4, HTTP 403 |
| Read-only intake denial | 0/4 |
| Preparation decline | 0/4 |
| Chat assent with a pending draft | 0/4 |
| Draft cancellation | 0/4 |
| Duplicate confirmation | 0/4 |
| Injected write failure | 0/4 |

Five fault families stopped at an unavailable control before their planned
action; the read-only family never reached selection or mutation denial.
Existing synthetic unit/integration tests exercise these branches separately;
they cannot be relabeled as source-backed final fault completions.

There is also an oracle mismatch: all four foreign-record attempts correctly
returned HTTP 403, but failed the frozen requirement for a chat `access_denied`
event because that error produces no chat event. Four service attempts failed
only a strict required-status checkpoint despite a grounded terminal answer.
These scores are conservative scripted-journey results, not a claim that those
four answers lacked record grounding. Original failures remain in the report.
The four write-failure attempts have an additional conservative scorer error
when their absent pending draft is inspected; all remain incomplete, with
unassessed terminal checks. No post-exposure rescoring was performed.

The learned router also misrouted some inquiries and unsupported requests.
Spanish inquiry recall was 2/4, unsupported recall 2/4 and dispute recall 4/4;
four other Spanish probes were incorrectly predicted as disputes. Shared
guards preserved confirmation and permissions, but a safe blocked flow still
does not complete the requested service. Ten grounded-answer trace checks
passed per system out of 30 applicable attempts. Those checks inspect native
fields/references; they do not prove every textual implication is supported.

## Provenance, review and verification

Generated customer messages use supplied historical record facts; they are not
observed source conversations or historical customer allegations. The owner
approved exact Spanish wording, labels and scripts plus six unscored synthetic
output examples before the freeze. Actual final Spanish output review remains
pending in private `data/final_workflow_v1/final_output_review_es.md`. Portuguese
has no fluent-human approval and remains provisional. The author and coding
assistants are not an independent evaluation team.

There are 24 unique record/customer anchors. The 16 service anchors were unused
in earlier bindings; four safety anchors were reused. All records come from the
same 50-record cohort, with one record per customer. No genuine ambiguity,
source-backed MXN, pending/reversed purchase, no-match case, changed-source fault
or unseen-customer generalization is measured. Original CSV bytes were not
rehashed; validated snapshot and provenance commitments were verified.

All **652 regression tests** passed before freezing, including 45 new synthetic
harness tests. Fit/template/scorer/cleanup failures retain planned denominators;
an exclusive benchmark claim prevents an alternate-name rerun. Public evidence
contains only hashes, codes and aggregates. Credentials, source data and PDFs
remain excluded. Working-tree exclusion checks are not Git-history or exact
dictionary-credential scans. The repository remains private; no external model
calls, paid inference, deployment or publication occurred.

Observed HTTP journey median/p95 was 6.82/27.67 ms for keyword routing and
7.01/23.72 ms for naive Bayes. Component median/p95 was 0.122/0.759 ms and
0.644/1.225 ms. These local serial timings exclude fitting, setup, browser
rendering, human think time and deployment. Short failed journeys contribute
to the distributions; they are not successful-service latency guarantees.

The next implementation increment is source-native reference discovery with
authorization enforced outside the model. Fault tests must establish selection
through explicit visible controls before exercising their intended condition.
Any repaired app requires separate engineering regression evidence and a newly
declared untouched evaluation set; this exposed benchmark cannot regain
held-out status or be used for parameter selection.
