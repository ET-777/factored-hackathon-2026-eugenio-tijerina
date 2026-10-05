# Bounded naive Bayes smoothing comparison, October 4

The owner authorized one smoothing-only comparison, capped at 15 minutes from
2026-10-05 00:32:53 UTC through 00:47:53 UTC. Compare **alpha 0.1, 1 and 10**
once, then stop. No wording, feature, prior, threshold or further model search
is authorized. Preserve the earlier evidence and existing UI selectors. No
external inference, paid calls, deployment or public publication occurs here.

## Fixed inputs and models

Use only the fixed authored TRAIN144 file
`evaluation/routing_train_short_v2.json`; validate unchanged inclusion of the
original TRAIN96 file `evaluation/routing_train.json`. Reuse the frozen
`evaluation/linear_routing_groups_v1.json`: 24 families grouped into 15 semantic
clusters. The existing three folds each hold out 48 rows, 24 per language.
Keep whole clusters and both languages together; class/subtype counts differ
across folds. Fit each model's vocabulary and counts on the other 96 rows only.
Do not read old development/short-message test batches, source records/cohorts,
PDFs or any final cases. Spanish wording/labels have owner approval; Portuguese
fluent-human review remains pending.

The reference is the unchanged v2 multinomial naive Bayes implementation,
alpha 1, character 3–5 counts, normalized and space-padded text, and empirical
class priors. The separate experimental adapter reuses its complete validation
and counts, with instance-owned alpha 0.1 or 10 in both feature numerators and
class denominators. Preserve exact reference behavior at alpha 1 on toy cases.
Never mutate the incumbent's module globals. No dependencies beyond Python's
standard library are needed. Assent, entirely unknown features and tied top
scores retain the existing abstention rules; confidence remains uncalibrated.
Models cannot grant permissions, consent or action success.

## Execution and metrics

Create one exclusive run under ignored `.local/smoothing_routing_runs/`, requiring
the frozen protocol SHA256. Save input, group, protocol, implementation/runtime
fingerprints and exact folds before any fit. Nine comparison component fit
calls yield 432 planned out-of-fold attempts, 144 per setting. The adapter's
validation invokes the incumbent count fit internally; the nine figure counts
comparison component calls. Retain partial/failed runs and never retry fits or
predictions. Record IDs, family/cluster, fold, language, gold/predicted labels,
matched flag, confidence, fixed error codes and timing; do not log wording or
raw exceptions.

Use unchanged `score_routes`: all attempted rows remain in denominators; unmatched
abstentions are incorrect even for unsupported gold labels; failures/malformed
outputs count as errors and abstentions. Report pooled accuracy, macro-F1,
coverage, errors, unsupported recall, per-language/class/fold results, confusion,
family/cluster exact completion and paired changes. Timing covers the local
component only, excluding UI, network, human work and deployment.

## Decision declared before predictions

Rank the two alternative alpha settings by pooled macro-F1, then correct count,
then smaller alpha. The selected alternative earns provisional engineering
consideration only with zero errors for both alternative and reference, F1 gain
at least 0.05, at least four more correct routes and no accuracy or macro-F1
regression in either language. These are project decisions, not organizer
thresholds or statistical significance tests. Report unsupported recall even if
overall improvement passes. Preserve both alternatives, including failures.

If criteria fail, retain v2. If they pass, freeze the selected alpha as a separate
candidate; promotion is not automatic. Keep application defaults and v1/v2
selectors unchanged in this trial. Authorization, record identity, preparation
consent, explicit final confirmation, idempotency and verified receipts remain
prerequisites before separately scoped UI integration.

The same folds were already exposed in logistic and XGBoost model selection.
This repeated search increases selection optimism; the small authored corpus
and manual grouping cannot establish production generalization. This is TRAIN
selection evidence, not an independent test or complete workflow evaluation.
The corpus also reflects earlier development feedback. Independent reviewed
workflow evaluation after implementation freeze remains necessary.

## Preservation and export

Save a sanitized aggregate and concise results document with denominators,
decision, all settings and limitations. Verify hashes of frozen prior code,
TRAIN, grouping, protocols/evidence and the owner's readiness draft before and
after the run. Keep prior artifacts unchanged; append documentation links only
outside frozen implementation files. No source credentials, private records,
model binaries or runtime output enter Git. Existing authorized private repository
synchronization does not change visibility or authorize deployment.
