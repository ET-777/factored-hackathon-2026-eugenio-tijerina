# Bounded local router comparison, October 4

This is a new project development experiment authorized by the owner after the
short-message diagnostic. It does not amend that diagnostic's frozen protocol,
replace its evidence, or authorize access to a final workload. Limit the work to
60 minutes from the start of this increment; stop the search after the declared
comparison, even if no challenger earns consideration.

## Inputs and systems

Read only the two fixed authored TRAIN artifacts: `routing_train.json` (96 rows)
and `routing_train_short_v2.json` (144 rows). Preserve their exact bytes and verify
that the second contains all original rows unchanged plus the 48 balanced short
additions. The first file is for validation; fit every comparison using subsets
of the same 144-row file. These are authored customer messages, not supplied
transcripts, banking records or representative production traffic. Spanish
wording/labels have owner approval; Portuguese fluent-human review is pending.

Compare the unchanged v2 algorithm (character 3–5 counts, multinomial naive
Bayes, alpha 1, empirical priors) against one alternative: the same normalized,
space-padded character 3–5 fragments, TF-IDF with default smoothed IDF and L2 row
normalization, and L2 logistic regression. Its only searched parameter is
regularization C, fixed in advance at **0.1, 1.0, 10.0**. Use deterministic lbfgs
with maximum 1,000 iterations. A convergence warning makes that fit a failed
attempt, rather than a silently accepted result. Record actual package versions.

Reuse input bounds, language checks, assent handling, and abstention on no known
features or tied top scores. All confidence outputs remain uncalibrated. Do not
search thresholds, fragment lengths, class weights, solver choices, training
wording, or additional model families. No external inference or paid calls.

## Grouping and scoring

Use three deterministic folds inside TRAIN. Before any prediction, independently
review the 24 authored families for close paraphrases across family IDs and merge
related families into fixed semantic clusters. Keep both languages and every
row of each cluster in one validation fold. Record the exact reviewed mapping
and fold assignment in the run manifest before fitting. The accompanying
grouping artifact is a planning decision made without predictions; refuse an
unexpected family, missing row, split cluster, or a fold without all four intents
and both languages. Fold populations may differ to preserve clusters.

The fixed mapping is `evaluation/linear_routing_groups_v1.json`: 15 clusters
retain all 24 source families and all 144 rows. The independently reviewed
mapping places 48 rows (24 ES, 24 PT) in each fold; class/subtype counts differ.
All short human-preference variants are held out with the original preference
family; generic short inquiries are held out with the original status family;
unrecognized/duplicate disputes and new-transfer variants are grouped likewise.
The mapping and its SHA256 must be frozen in the manifest before fitting.

Fit vocabulary, TF-IDF weights, and classifier separately on each fold's training
partition. Each row receives exactly one out-of-fold prediction per system. Sort
rows and groups deterministically. Do not reshuffle, repeat, retry failed fits,
or revise groups after inspecting scores. No existing DEVELOPMENT, short-message
coverage/follow-up, source cohort, original source files, or final inputs are read
or scored by this experiment.

Use the existing `score_routes` arithmetic: all attempted rows remain in the
denominator; unmatched predictions count as incorrect abstentions even when the
gold intent is unsupported; malformed outputs and fit/inference errors are errors
and abstentions. Preserve per-row predictions with IDs, cluster/family, fold,
language, labels, matched flag, uncalibrated confidence and fixed error codes.
Do not log customer wording or raw exception text.

Report pooled out-of-fold accuracy, macro-F1, coverage, abstentions, errors,
per-language/class counts, confusion matrices, cluster/family exact completion,
paired correct/incorrect changes and per-fold variation. Do not average unequal
fold percentages as if they were pooled accuracy. Fit time and component inference
median/p95 exclude UI, networking, human time and deployment; label them accordingly.

## Decision fixed before scores

Rank the three C settings by pooled overall macro-F1, then overall correct count,
then smaller C for a tie. The selected setting earns provisional engineering
consideration only if it has zero execution/convergence errors, improves pooled
macro-F1 by at least 0.05 and correct routes by at least four over the incumbent,
and has no pooled accuracy or macro-F1 regression in either language. These are
project decisions, not organizer acceptance thresholds or significance tests.
The incumbent must also have zero execution errors: a failed reference cannot
establish improvement. Retain its failed attempts but refuse consideration.
Record all alternatives, including unsuccessful ones. A failed comparison does
not justify additional search or replacing v2.

Cross-validation used to choose a setting is selection evidence, not an untouched
test or independent improvement estimate. The manual semantic grouping cannot
prove independence, and the small number of clusters makes fold estimates noisy.
The training corpus itself was expanded after earlier development feedback.
These limitations must accompany the result.

If consideration criteria pass, freeze the selected configuration and retain it
as a separate experimental candidate. Meaningful toy/regression checks must
preserve authorization, selected-record identity, preparation consent, explicit
final confirmation, idempotency and verified receipts before any opt-in UI
integration. Such checks are engineering evidence, not a workflow benchmark.
Keep the default router and v1/v2 selectors unchanged. An independent reviewed
workflow comparison after implementation freeze remains necessary for submission
claims; this experiment does not open, replace or score the sealed final set.

## Reproducibility and preservation

Create a new exclusive run under ignored `.local/linear_routing_runs/`. Write
input, grouping, protocol, implementation and dependency fingerprints, runtime,
folds, systems and selection criteria before the first fit. Retain partial and
failed runs. Export a sanitized aggregate artifact and concise result document
with the run manifest, denominators, decision and limitations. Verify the old
TRAIN/evidence files and owner-created readiness draft have unchanged hashes.
Keep raw/source credentials, private records, model binaries and runtime outputs
out of Git. No deployment, visibility change or public publication occurs here.
