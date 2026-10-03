# Bounded source-intent feasibility review

This review asks whether supplied customer wording can support a source-grounded
comparison of the four-intent router. It is label/coverage feasibility work, not model
performance, threshold selection or final scoring. Raw utterances and annotations
remain in ignored `data/intent_review/`; only aggregates belong in Git.

## Scope and annotation rubric

Use seven fixed daily transcript partitions, June 17-23, 2023, with hard file, byte,
row, text and runtime bounds. Normalize customer wording with NFKC, casefold and
whitespace collapse, matching the earlier contact audit. Never use source topic/intent
fields, agent responses, resolution outcomes or current router predictions to assign
semantic labels. Retain input-file hashes, row positions and text identities privately.
Subset multiplicity is not full-corpus prevalence or independent example support.

| Draft label | Customer wording needed |
| --- | --- |
| `inquiry` | Find, list or explain facts/status of an existing transaction. Account/card mentions are allowed when the object is an existing transaction. |
| `dispute_intake` | Explicitly describe an existing charge as unrecognized, unauthorized, duplicated or incorrect, or request a review/contest of that charge. This label does not grant action permission. |
| `human_request` | Explicitly request a person, agent or human contact. |
| `unsupported` | Clearly request a different service or action: account balance, product support, a new payment/transfer, card blocking, refund execution or general technical/service assistance. |
| `uncertain` | Wording does not distinguish the four intents, or mixes requests without one clear primary intent. Preserve candidate labels and a reason rather than forcing a label. |
| `unusable` | Blank/corrupt wording or no recoverable customer request without missing context. |

Negated requests are not positive intents. Group clear paraphrases and template
variants into the same family before assessing split feasibility; do not collapse
all requests sharing an intent into one family. Uncertain/unusable groups remain in
the inventory denominator and are not classifier training labels.

Codex annotations are drafts for owner/human review. A second Codex semantic pass is
cross-checking, not independent human validation. Source language tags do not establish
native linguistic quality. Do not promise four-class or Portuguese coverage.

## Verified extraction and draft semantic findings, October 1

The canonical run `june17-23-intents-v1` read seven complete daily CSV files: **1,098
rows and 883,373 bytes**, with no missing customer text, truncation or unknown language
tags. Every stored language tag was `es`; zero were `pt`. All seven file hashes match
the earlier ignored contact-audit manifest. This checks those seven inputs, not remote
download completeness, later file stability or native linguistic validation.

The subset contains **42 normalized full customer-text groups**, matching the earlier
full-audit count. A semantic review found only **two opening business-request families**:

| Reviewed opening family | Full-text variants | Subset rows | Draft scope label |
| --- | ---: | ---: | --- |
| Savings-account balance | 21 | 558 | `unsupported` |
| Credit-card balance | 21 | 540 | `unsupported` |
| Total | 42 | 1,098 | 42 unsupported; zero inquiry, dispute intake or human request |

There were no uncertain/unusable openings or disagreements in the second Codex pass.
Both Codex reviews remain drafts for human validation. Neither pass used source topics,
agent responses, outcomes or router predictions. The source rows have no supplied
transaction-inquiry, dispute or human-request openings in this fixed subset under the
project's four-intent rubric; this is not a reannotation of all 171,321 corpus rows.

The full text varies through appended acknowledgment/follow-up wording: **459/1,098
rows** have text after the reviewed opening span. Each opening family has the same 21
suffix variants, including an empty suffix. These tails create text diversity without
independent initial requests. Savings wording begins with a greeting sentence before
the business request; extracting only its first sentence would lose the request.
Opening spans are reviewed interpretations of the wording, not verified native turn
boundaries. Do not use later customer replies as first-turn classifier features.

**High-confidence extraction finding; high-impact modeling limitation:** the proposed
four-class classifier cannot be trained or meaningfully compared on this subset: three
classes have no support, the only supported class has two request families, and there
is no Portuguese coverage. A majority/unsupported classifier could score perfectly on
these openings without demonstrating useful transaction routing. Do not create a row
split, report such a score as benefit, fit a model or select thresholds from these
repeated templates.

The chosen transaction workflow remains supported by available record types and the
challenge examples, but these transcript texts do not demonstrate demand for its
specific requests. Broad contact-category counts describe supplied metadata; they
must not be presented as independently verified customer-intent frequencies.

## Reproducible artifacts and limits

- Extractor: [`inventory_source_intents.py`](../scripts/inventory_source_intents.py).
  It generates seven explicit partition paths; caps are seven files, 2 MiB, 1,500
  parsed rows, 64 groups and 30 seconds. It writes a new private run exclusively and
  prints only aggregate counts or fixed error codes.
- Private inventory, draft labels and review metadata: ignored
  `data/intent_review/june17-23-intents-v1/`. Text, per-group identities, request spans
  and source-row references remain there.
- Public counts: [`source_intent_inventory_summary.json`](../evidence/source_intent_inventory_summary.json),
  generated by [`summarize_intent_review.py`](../scripts/summarize_intent_review.py).
  The review is bound to the exact inventory hash; missing/duplicate annotations,
  contaminated label inputs and inconsistent denominators are refused. Only aggregate
  fields are exported, with human-validation status and no performance scores.
- An exploratory preview read the first partition once before canonical extraction,
  adding 71,071 bytes; total source bytes read during this session were **954,444**.
  No full-corpus rescan, network data access, source write, model fitting or final-set
  access occurred.

```powershell
python -X utf8 -B -m scripts.inventory_source_intents --source ../Data --run-name new-private-review
```

Review each group privately under the rubric above, retaining uncertainty and request
spans. Save `labels.json` with the new inventory hash; do not copy this run's annotations
unbound to a new input. The aggregator requires that private review and refuses to
overwrite an existing public result:

```powershell
python -X utf8 -B -m scripts.summarize_intent_review --run-name new-private-review
```

Fifteen isolated synthetic extractor tests and four aggregate/privacy tests pass.
These verify utility boundaries, not model accuracy or human label correctness.

## Scoped organizer permission and next step, October 2

The October 1 report prepared an organizer question because the reviewed source
utterances could not support the four-intent comparison. On October 2 the owner
provided a screenshot of the question they posted and Diego's reply. Its live Slack
permalink has not yet been retrieved; the screenshot is the reference source, and no
local attachment path or image is published here.

Owner's exact question shown in the screenshot:

> I’m building a transaction inquiry/dispute assistant, but the transcripts I reviewed only cover balance requests in Spanish. Can I generate my own Spanish and Portuguese customer messages for evaluation, using the supplied transaction records, with separately labeled simulated safety/tool failure scenarios?

Diego's exact reply:

> Yes just make sure to justify it

This permits the scoped proposal with justification. The completed inventory supplies
that rationale: three intended classes have zero support, the only represented class
has two opening families, and no source language tag is Portuguese. Label generated
customer messages separately from supplied transaction facts and simulated faults;
fault scenarios do not represent historical bank outcomes. Review semantic labels,
independent request families and Portuguese wording, group related examples before
splitting, and disclose generation/review limitations. Permission does not prove model
quality, native language coverage or representative customer demand.

The reply does not blanket-approve the existing workload's fictional banking records,
grant source redistribution/external-provider permission, or authorize opening,
changing or replacing its final seal. A proposed source-grounded workload requires its
own reviewed protocol before a new, separately authorized final freeze. See the
updated readiness checks in [evaluation.md](evaluation.md).

The [October 2 implementation increment](private_cohort_ui.md) connects a separate
loopback UI mode for the existing validated private cohort, with trusted startup
identity/permissions and unchanged fictional demo behavior. Next establish the reviewed
source-grounded authored ES/PT workload and shared comparison protocol. Keep source
evidence private. The synthetic scenario adapter remains deferred; no training,
tuning, performance scoring, public release, deployment or
additional Slack message is part of this increment.

The subsequent [learned-preview increment](learned_routing.md) supplies authored
TRAIN/DEVELOPMENT drafts, private source-context bindings and training-only local
fitting. The source inventory above remains coverage evidence. Human review and a
comparison protocol are pending; no development or final score is claimed.
