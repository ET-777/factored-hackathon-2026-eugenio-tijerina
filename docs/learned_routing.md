# Experimental local learned routing, October 2

The prototype has an optional supervised intent router. UI startup fits **TRAIN
only**. A separately frozen [first development comparison](development_results.md)
is now complete; final evaluation and human output review remain pending. The default remains
the keyword baseline. Both routes use the same records, search/selection code,
permissions, response templates, confirmation flow, simulated tools and receipt checks.

## Model and reproducibility

`bank_service/learned_routing.py` implements multinomial naive Bayes over character
3-, 4- and 5-gram counts using only the authored TRAIN messages and their intent labels.
It normalizes NFKC, case, accents and whitespace, uses Laplace smoothing alpha 1 and
empirical class priors, and sorts labels/features deterministically. It supports the
four existing intents and both selected languages in one model. Language is validated
but is not a separate learned feature. No banking records, transcripts, outcomes,
development text or final cases are model features.

The fixed TRAIN draft has **96 messages in 12 families**, 48 per language and 24 per
intent. Its initial local fit produced 6,304 features on Python 3.11.0. The manifest's
single startup timing is not an inference latency result or service SLA.
See [learned_preview_manifest.json](../evidence/learned_preview_manifest.json) for
exact file/canonical-row hashes, implementation hashes and parameters. The model is
rebuilt from the fixed TRAIN artifact at explicit preview startup; no binary artifact
or remote model is required.

File hashes describe exact local filesystem bytes. Git may normalize line endings
between Windows and other checkouts; use the canonical training-row hash to compare
the authored training identity across that conversion.

Normalized scores are **uncalibrated**. There is no selected confidence threshold.
Standalone assent, entirely unseen features and tied top scores abstain. Shared
conversation rules handle consent responses and amount/currency/date continuations
before either router. Recognized character fragments do not prove a request is in
scope; noisy, vague, negated and mixed requests remain coverage risks for this preview.

`bank_service/route_loader.py` accepts only the fixed, bounded
`evaluation/routing_train.json`, validates its provenance/status, and refuses malformed
data with a sanitized startup error. Redirected input paths are refused before reading.
No browser-supplied file or router path is accepted.
The default startup does not load or fit the model.

The October 4 [short-message increment](short_message_results.md) adds a separate
`--router learned-preview-v2` selector and fixed
`evaluation/routing_train_short_v2.json`. It preserves the original 96 TRAIN rows
and adds 48 concise requests, for 144 total. The v1 selector and keyword default
remain unchanged. The owner separately approved the new Spanish wording/labels
after scoring on October 4; Portuguese fluent-human review remains pending.
The new review is bound separately from approval of the original artifacts.
The original development score remains historical evidence for v1, not a v2
quality claim. New diagnostic results and limits are recorded separately.

## Local preview

For the fictional-record UI, use one physical PowerShell line:

```powershell
python -B -m bank_service web --port 8767 --router learned-preview
```

Open **http://127.0.0.1:8767/**. The chat badge says **IA local · experimental**.
The same `--router learned-preview` flag can be added to the existing
[private-cohort command](private_cohort_ui.md). Its trusted startup identity and
explicit permissions stay unchanged. Keep source-backed previews on loopback;
they are owner-local review tools, not publishable raw-data demonstrations.

The keyword instance can remain on port 8766 for comparison. A model-proposed intent
never establishes identity, ownership, permission or consent. Only the existing
explicit final confirmation can save a simulated ticket, and the service must verify
its receipt before reporting success. Plain chat assent cannot confirm a pending draft.
The classifier does not move money, issue a refund or contact a bank.

## Review before scoring

The [workload rationale](routing_workload.md) documents organizer permission, authored
provenance, grouping, source-binding expectations and limits. A second Codex reviewer
checked all 128 TRAIN/DEVELOPMENT messages without viewing model predictions or rules
and proposed no corrections. Their original JSON draft metadata is retained unchanged.
The [October 3 language-review record](../evidence/routing_language_review.json) binds
the owner's Spanish wording/label approval to all 64 ES messages. Portuguese fluent human review remains pending and
must be resolved or disclosed explicitly. A second model review does not replace it.

The [64-message Spanish checklist](routing_review_es.md) is approved for wording and
intent labels. This does not prove semantic family independence or model quality.
Do not use router responses to decide gold labels. The [paired development
protocol](development_protocol.md) was declared before scoring and explicitly
discloses the Portuguese human-review limitation.

The **32-message development workload was scored once** under that protocol. Its eight families are separate
from TRAIN, but this is a small engineered balanced workload with semantic overlap
and author/reviewer limitations. Private source bindings supply record context for
service checks; the binding checkpoint alone was not performance evidence. The
new [aggregate result](../evidence/routing_development_v1.json) preserves every
attempt and reports component and mechanical completion separately. No model
parameter or threshold changed after this run.
The original sealed final set remains unread and unchanged; any future source-grounded
final workload needs a separately authorized freeze and protocol.

No external model/provider calls, deployment or public release occurred in this
increment. Model fitting is local; hardware cost is unmeasured.

## Verification checkpoint

**370 unit/integration tests passed.** They cover the model's synthetic toy-data
behavior, bounded TRAIN loading, private bindings, malformed proposals, shared
search continuation, foreign-record denial, consent, final confirmation and fresh
sessions. JavaScript syntax and ES/PT mode-copy/native-amount checks passed.

A source-backed HTTP probe using four TRAIN messages passed 14 stages across both
languages, including preparation consent, chat assent refusing to submit a pending
draft, explicit submission and verified simulated receipts. This is an integration
probe on training examples, not accuracy, language review or held-out performance.
It selected its record independently in the review UI and did not load or execute
the newly prepared private binding cases.
It first found a shared selection-context omission for «esta operación»/«desta
operação». The reference helper now recognizes explicit singular operation/movement
and selected-record phrases in both routes, while new/plural searches and explicit
filters retain their normal selection rules. A second probe failure came from a
wrong action name in the local harness, which was corrected to the existing endpoint.
Both failed outputs were preserved in ignored local files before the passing run.

The two running source-backed previews have identical authorized transaction lists
and different router modes. Their source facts, permissions and shared code are the
same. The 50-record binding run prepared all 20 families without unavailable examples;
no bound development workflow or classifier score was produced.

The working-tree artifact check passed 86 eligible files, zero violations and 8/8
exclusion probes. It did not read dictionary credentials or scan Git history. Existing
source/access/action/record/store/response/demo modules and the original public
development/final commitment have no diff. Original final contents were not read.

## Neutral chat input correction, October 3

The owner reported a dispute offer after starting with «Hola» and providing dates.
A TRAIN-only diagnostic reproduced the raw classifier proposing dispute intake for
the greeting. Pure greetings now receive a greeting or the current search/offer
reminder before either router runs. A greeting containing a business request still
goes through normal routing. This is a shared conversation rule, not retraining or
evidence that the classifier learned to interpret greetings correctly.

Standalone dates, amounts, currencies and recognized record references now start an
inquiry without consulting either business classifier. If an unfinished request
already exists, the same details continue its original inquiry/dispute intent.
Date attempts with a mistyped year, swapped components or invalid calendar value
reach strict ISO validation; the app does not guess or rewrite the date. Existing
permission checks, preparation consent and final confirmation are unchanged.

**375 tests passed**, including the neutral greeting/date sequence, an explicit
dispute followed by corrections, and preservation of offers/drafts. A separate
12-stage HTTP regression used synthetic component records and the unchanged local
TRAIN model in both languages; its [evidence](../evidence/neutral_chat_input_check.json)
is diagnostic, not a held-out performance score. No source row or screenshot fact
was copied into fixtures. The approved workload texts, labels and model parameters
were unchanged at that checkpoint; development was then unscored and original
final cases unread. The later development run above retains those inputs/model
parameters and leaves the original final untouched.

Stop and restart existing review servers to load the correction. Use the same
updated shared code for the keyword and learned modes. Saved owner-local launchers
remain available locally; they are ignored conveniences, not repository setup
dependencies. The published startup commands above remain available.
