# Bounded XGBoost comparison, October 4

This owner-authorized follow-up compares two shallow XGBoost configurations with
the unchanged naive Bayes v2 algorithm. It preserves the completed logistic
experiment and stops after this comparison. The work budget is 30 minutes from
2026-10-05 00:03:09 UTC, ending by 00:33:09 UTC. No external inference, paid calls,
deployment, public publication or access to final cases is authorized here.

## Fixed inputs and settings

Use only the fixed TRAIN artifacts `evaluation/routing_train.json` (96 rows,
preservation validation only) and `evaluation/routing_train_short_v2.json`
(144 rows, all fits). They contain authored messages, not supplied transcripts
or representative production traffic. Spanish wording and labels have owner
approval; Portuguese fluent-human review remains pending. Do not change wording,
labels, groups, folds, features or settings after viewing predictions.

Reuse the unchanged `evaluation/linear_routing_groups_v1.json`: 24 authored
families in 15 manually reviewed semantic clusters. All rows of each cluster,
including both languages, stay in one fold. Each of three folds holds out 48
rows, 24 per language; class counts differ. Train each component on the other
96 rows. Fit vocabulary and IDF only inside that partition.

The reference is character 3–5 counts, multinomial naive Bayes, alpha 1 and
empirical priors. XGBoost uses the logistic experiment's exact normalized,
space-padded character 3–5 counts with smoothed TF-IDF and L2 row normalization.
Only `max_depth` varies, fixed at **1 and 2**. Every other setting is fixed:

- 100 boosting rounds, learning rate 0.1, minimum child weight 2;
- L2 regularization 10, L1 regularization 0;
- full row and feature sampling;
- four-class `multi:softprob`, explicit sorted intent encoding 0–3;
- CPU histogram trees, random seed 0, one thread, no early stopping;
- no class weights, confidence threshold, calibration, feature search or retries.

Use XGBoost 3.1.3 in an ignored isolated environment, with the versions pinned in
`requirements-xgboost-experiment.txt`. The sparse TF-IDF matrix stays sparse;
XGBoost treats absent sparse entries as missing and learns their default branch.
This is a fixed modeling choice, not a searched feature transformation.
Confidence is an uncalibrated model score. Preserve input/language validation
and abstention on assent, no known features or tied top scores. Models propose
intents only; permissions, consent, record identity and action verification stay
outside them. Neither challenger is connected to the application.

## Execution and scoring

Create one exclusive run under ignored `.local/xgboost_routing_runs/`. Require
the declared protocol SHA256 and save input, group, protocol, implementation,
package and fold fingerprints before any fit. Nine component fit calls produce
432 planned out-of-fold attempts: 144 per system. Preserve partial/failed runs.
Validation inside the challenger also invokes the incumbent's bounded training
contract; the nine count describes comparison component calls, not every
internal validation operation.

Use the unchanged `score_routes` arithmetic. All attempted rows remain in the
denominator. Unmatched abstentions are incorrect even for unsupported gold
labels. Failed fits/inferences and malformed outputs count as errors and
abstentions; do not retry or remove them. Record IDs, family/cluster, fold,
language, gold/predicted label, matched flag, confidence, fixed error code and
timing. Do not log customer wording or raw exception messages.

Report pooled accuracy, macro-F1, coverage, errors, unsupported recall,
per-language/class/fold results, confusion matrices, family and cluster exact
completion, paired changes and fit/inference timing. Timing covers this local
component only, excluding UI, network and human work. Do not read old development,
coverage/follow-up messages, source records/cohorts, PDFs or any final workload.

## Decision before scores

Rank depth settings by pooled macro-F1, then correct count, then smaller depth.
The selected challenger earns provisional engineering consideration only with
zero errors for both challenger and reference, macro-F1 gain at least 0.05,
at least four more correct routes, and no pooled accuracy or macro-F1 regression
in either language. These are project decisions, not organizer thresholds or
statistical significance tests. Record both configurations even if neither
passes. Do not start another search after the result.

If these criteria pass, retain the frozen configuration as a separate candidate;
promotion is not automatic. Shared authorization, selected-record identity,
preparation consent, final confirmation, idempotency and verified receipt checks
remain prerequisites before any separately scoped opt-in UI integration. Keep
the keyword default and existing v1/v2 selectors unchanged during this trial.

These folds have already been exposed in the logistic experiment. Reusing them
for model selection increases selection optimism: this is TRAIN cross-validation,
not a fresh independent test or workflow evaluation. The small authored corpus,
manual grouping and pending Portuguese review limit generalization claims. The
expanded corpus already reflects earlier development feedback. Untouched final
evaluation remains necessary after implementation freeze.

## Preservation and export

Export sanitized aggregates and a concise results document with the manifest,
denominators, decision and limitations. Verify old TRAIN, grouping, evidence,
protocol/code and the owner-created readiness draft have unchanged bytes.
Leave `pyproject.toml` unchanged because its hash belongs to frozen prior
evidence. Source credentials, private records, binaries and runtime outputs stay
out of Git. Existing private repository synchronization does not authorize a
visibility change or deployment.
