# Short-message development results, October 4

The owner authorized a bounded check and conditional expansion after observing
that real requests may be brief or misspelled. These are project development
diagnostics on authored messages, not a final benchmark or representative traffic.
The [protocol](short_message_protocol.md) was declared before the first score.
The [aggregate evidence](../evidence/routing_short_diagnostic_v1.json) retains
all runs, input/code hashes, confusion matrices, per-language/class metrics,
failures and decision checks.

## Training and freeze

Only four of the original 96 TRAIN messages had five words or fewer. A separate
author created a 48-message short-request coverage batch; a blinded Codex review
checked its labels before scoring. V1 made 17 errors, including the owner's two
examples; 15 errors were on authored cases, meeting the declared expansion trigger.

The new candidate retains every original TRAIN row and adds exactly 48 messages:
24 ES and 24 PT, six per intent/language, in 12 paired families. All additions
contain three to five words. Its 144 rows produce 6,906 character features.
Algorithm, normalization, alpha 1, empirical priors and abstention rules are
unchanged. No confidence threshold was selected. The candidate was frozen before
its first score and was not revised after predictions.

Another author created the 32-case follow-up without seeing TRAIN, coverage
messages, routing rules or predictions. Its contents stayed unread by the
implementer until candidate freeze and the first candidate coverage score.
Original TRAIN bytes, the old development result and its language-review record
remain unchanged. Old DEVELOPMENT was not rescored; final cases remain sealed.

## Raw component results

Correct labels include all attempts. Unmatched proposals count as abstentions,
including for gold unsupported; malformed outputs/errors remain in denominators.
No execution errors occurred. Shared conversation guards were not applied in
these component scores.

| Coverage batch | ES correct / 24 | PT correct / 24 |
|---|---:|---:|
| Keyword baseline | 12 | 15 |
| Learned v1, 96 TRAIN | 16 | 15 |
| Learned v2, 144 TRAIN | 19 | 19 |

Spanish coverage macro-F1 improved from 0.6266 to 0.7869; Portuguese from 0.5327
to 0.7650. Combined correct labels improved from 31/48 to 38/48. This batch guided
the expansion, so its before/after figures are adaptation feedback.

| Separately authored follow-up | ES correct / 16 | PT correct / 16 |
|---|---:|---:|
| Keyword baseline | 8 | 7 |
| Learned v1 | 15 | 14 |
| Frozen learned v2 | 15 | 16 |

Spanish performance tied v1, while Portuguese gained two correct routes.
No per-language follow-up accuracy regression occurred. These small counts do
not establish significance or reliable generalization.

The owner approved the new Spanish wording/labels on October 4, after scoring;
Portuguese fluent-human review remains pending. The
[Spanish checklist](routing_short_review_es.md) has 64 new intent items and four
unscored state cases, without predictions. The [separate review record](../evidence/routing_short_language_review.json)
binds the new approval to exact rows and artifact hashes. The checklist omitted
model predictions; this was retrospective owner language review, not an
independent or pre-score human-label review. Frozen input/run metadata retain
their original pending-review status as historical evidence.

## Remaining mistakes and shared workflow repair

The raw v2 model still misclassifies both owner examples. It proposes unsupported
for "quiero ver un pago" and inquiry for "yo no hize esto". The existing complete
read-request guard already protects the first phrase in the application.
The ten remaining coverage mistakes are retained in the diagnostic evidence;
no training example or parameter was adjusted after those predictions.

A separate post-score conversation repair now recognizes a complete past-action
denial about an already selected authorized transaction, including bounded ES
hice/hize and PT fiz/fis spellings. This rule is shared by keyword and learned
modes; it is not a learned improvement and does not change the raw scores.
It rechecks the selected record through the existing inquiry tool and offers
preparation consent for that record. It never prepares or saves a case directly.
Without a selected record it does not infer a transaction identity.
Questions, negated intentions and mixed commands are excluded from the guard.

TRAIN-only fictional-record integration checks cover both languages, the latest
of two selected transactions, a forced wrong classifier, no guessed record,
preparation consent, chat assent refusing to submit, explicit final confirmation
and idempotent verified readback with the original misspelled allegation retained.
The full suite passed 556 tests. Seven focused checks passed after an independent
review caught and corrected a fullwidth-question-mark edge. These are software
regressions, not source-grounded performance or language-validation evidence.
The eight separately authored state cases were not scored as intents.

## Preview and limits

The candidate meets the provisional engineering consideration checks and is
available only through a separate selector. Keyword remains the default and
the original learned preview remains v1. Stop an existing server with Ctrl+C,
then start the fictional-record preview on one PowerShell line:

    python -B -m bank_service web --port 8767 --router learned-preview-v2

For an existing private-cohort launcher, change only its router selector; retain
its trusted startup identity and explicit permissions. Keep that preview local.
UI startup reads only the fixed TRAIN artifacts, never development/final cases.

The coverage batch has 24 paired families and the follow-up eight families.
Translations and close paraphrases remain grouped within their authored sets.
TRAIN and these sets share intent concepts; different family IDs do not prove
semantic independence. Near-paraphrases occur, including a punctuation-only
TRAIN/coverage difference. Exact normalized duplicate checks retain punctuation
and do not establish independence. The follow-up is generally more explicit
than the terse coverage batch, so its higher accuracy is not a traffic estimate.

This component-only comparison does not assess multi-turn completion, record
grounding, human-handoff usefulness, access/consent safety or deployed latency.
Those require their own workflow and final protocol. No source rows were model
features; no final contents, original CSV/PDF, paid inference, deployment or
public release was used. External provider calls/charges are zero; local
hardware/electricity cost is unmeasured.
