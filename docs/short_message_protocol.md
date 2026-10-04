# Short-message development diagnostic, October 4

This protocol is a project decision, declared before scoring the new coverage
batch. The owner authorized a bounded check and, if repeated gaps appear, a
small training expansion. This is local development work, not final evaluation.

## Scope and labels

Use the fixed `evaluation/routing_short_messages_v1.json` artifact: 48 authored
short requests, 24 Spanish and 24 Portuguese, balanced across inquiry,
dispute intake, explicit human request and unsupported service. The owner's two
example phrases are observed development seeds, not unseen evaluation evidence.
Other phrases are authored language, not collected customer transcripts.
Deictic dispute wording assumes an existing selected transaction. The component
does not see that transaction and cannot establish facts or action consent.

Use the annotation definitions in `routing_workload.md`. Greetings, vague or
negated requests do not receive forced four-class gold labels. Any separately
listed state cases are excluded from component accuracy and retained as future
conversation regression inputs. No source records, raw data, dictionary,
private cohort, old DEVELOPMENT message contents or sealed final contents are
needed. Do not run the original final verifier or replace its workload.

All newly authored wording and labels have pending Spanish owner and Portuguese
fluent-human review. Report both languages as provisional. Existing Spanish
approval applies only to the original hash-bound TRAIN/DEVELOPMENT artifacts.
Technical review by another Codex agent does not replace language review.

## Systems and single-pass comparison

Compare unchanged keyword routing and unchanged v1 character 3-5 gram
multinomial naive Bayes, alpha 1, empirical class priors, 96 original TRAIN
messages. Fit only TRAIN. Evaluate one raw component call per clean-intent
case/system, sorted by case ID. No retry, threshold search, parameter tuning or
shared-rule repair belongs to this diagnostic. Keep unmatched proposals,
malformed outputs and errors in the denominator using `score_routes`' existing
ABSTAIN/error rules. Save per-case predictions, per-language counts, confusion,
macro-F1 and family exact counts. Confidence remains uncalibrated.

Freeze input, implementation and protocol hashes before fitting/inference in a
new exclusive `.local/short_message_runs/<run-name>/` directory. Never overwrite
a prior run. Report a harness defect and preserve the failed run before any
corrected execution. No raw exception text or private bank facts enter logs.

## Conditional expansion and candidate freeze

Two or more v1 errors on authored, unambiguous short requests constitute a
repeated component coverage gap; observed owner seeds alone do not satisfy this
trigger. This is a development decision threshold, not a quality target.
If triggered, author exactly 48 additional TRAIN messages (six per intent per
language) in `evaluation/routing_train_short_v2.json` together with the original
96 rows. Preserve v1 byte-for-byte, including its existing review record and
historical development result. The new 144-row candidate keeps the same
algorithm, parameters and shared workflow. No diagnostic text or label row is
copied into TRAIN; reject normalized exact duplicates. Preserve related
translations/paraphrases together within their authored group and disclose
semantic overlap with the diagnostic and original TRAIN concepts.

Freeze this one candidate before its first score. Do not revise its training
messages, labels or parameters after seeing candidate predictions. A second
development comparison on the same coverage batch is adaptation feedback, not
an independent improvement estimate. Old DEVELOPMENT is not rescored here.

An independently authored 32-message follow-up check, with balanced intents and
languages, may be created without access to TRAIN/diagnostic messages or model
predictions. Its text remains unread by the implementing agent until candidate
freeze. Compare v1 and the frozen candidate once, retain every result, and
disclose shared task semantics, authored-data bias and pending language review.
This is still a development check, never a replacement final evaluation.

Candidate consideration requires improved Spanish coverage-batch macro-F1,
no per-language overall accuracy regression on the fresh follow-up check, and
passing relevant permission/consent/receipt regression tests. These are
provisional engineering criteria. Do not change the default keyword route or
silently replace the original `learned-preview` model. Any new preview gets an
explicit separate version selector. Human wording review and untouched final
evaluation remain separate requirements before submission claims.

## Limits

The character classifier learns message intent; additional banking rows do not
train it. Raw routing counts do not measure record grounding, transaction
selection, multi-turn completion, useful handoff, deployed latency, or safety.
Synthetic integration regressions stay separately labelled. No external model
calls, paid services, deployment, public release or real banking actions occur.
