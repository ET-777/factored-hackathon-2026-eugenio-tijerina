# Transaction Support Assistant — five-slide submission copy

English draft, October 4, 2026. Use the current project name above. This file is
copy for a five-slide deck; it is not a completed submission or a deployed-tool
claim. Retain the limitations and source footnotes when converting it to slides.

## Slide 1 — A charge question needs a traceable next step

**Transaction Support Assistant**

Spanish and Portuguese transaction inquiry → confirmed simulated dispute intake
or human review.

- **240,056 / 686,296 contacts (34.98%)** are Transactional, the largest category
  in the supplied synthetic corpus. This is a scope rationale, not real-bank demand.
- **4,425,008 transaction rows** have consistent current owner/currency joins.
  **1,450,689 / 4,425,008 (32.78%)** have chronology conflicts and require quarantine.
- Serve an existing validated **50-record cohort**, not the full dataset. The public
  demo uses separate, independently authored fictional records.

**Intended outcome:** explain recorded facts, preserve the customer's issue, and
return a verified intake reference or a useful handoff. No measured business gain
is claimed.

Footnote: [scope](scope.md), [local data review](local_data_review.md),
[contact aggregates](../evidence/local_contacts_summary.json),
[transaction aggregates](../evidence/local_transactions_summary.json).

Visual direction: one large contact-share figure and a short workflow line. Keep
the two data counts labeled as local audit observations of synthetic source data.

## Slide 2 — Transaction inquiry and confirmed review

1. **Find:** ask for amount/currency/date; two fictional purchases require a choice.
2. **Explain:** show the selected record's native facts and evidence reference.
3. **Prepare:** a complaint offers a review request; accepting creates a draft only.
4. **Confirm:** review the exact draft, then explicitly confirm; report success only
   after SQLite persistence and readback agree.
5. **Hand off:** preserve the issue, verified facts, evidence, attempted steps,
   existing receipts and unresolved questions in a consented human-review packet.

**Visible demonstration:** ES `No reconozco esta compra` → verified local ticket;
PT `Quero falar com uma pessoa sobre a compra que não reconheço` → verified
simulated queue entry.
An unauthorized reference is denied; an unsupported loan request offers human review.

**Boundary:** a ticket is intake completion. No refund, adjudication, bank action
or human contact occurs.

Footnote: [local UI](local_ui.md), [local workflow](local_workflow.md),
[fictional fixtures](../bank_service/demo_fixtures.py).

Visual direction: five compact steps with the two confirmation boundaries clearly
marked. Use a readable current fictional UI screenshot if one is available.

## Slide 3 — Intent routing and service authority

**Local experiment:** character 3–5 n-gram Naive Bayes v2, alpha 1; **144 authored
TRAIN messages**; four intents. Compare with bilingual keyword rules using shared
records, workflow, permissions, templates and scorer.

**Why authored messages:** all **171,321 / 171,321** transcript language tags are
Spanish; **42 / 42** normalized text groups have conflicting topic labels. A bounded
inventory of **1,098 rows / 42 variants** found two balance-request opening families,
outside this workflow. It cannot supply the four-intent benchmark.

**Authority path:** browser → intent proposal → server-owned test session and owner
checks → authorized record facts → exact consent → persistence and verified receipt.
The classifier grants no access and performs no banking action.

**Provenance:** scoped organizer permission supports justified authored ES/PT
messages grounded in supplied transactions and labeled simulated faults. Historical
records and authored requests are separate. Spanish is owner-approved; Portuguese
is owner-accepted by assumption without fluent-human validation.

Footnote: [source-intent inventory](source_intent_inventory.md),
[requirements](requirements.md), [frozen protocol](final_workflow_protocol.md),
[current repairs/review](post_audit_repairs.md).

Visual direction: a single architecture line; show the permission/consent gate as
part of the service. Keep language/provenance limits legible.

## Slide 4 — Better intent scores did not qualify the workflow

**Original frozen comparison — keyword baseline → raw Naive Bayes v2**

| Measure | Spanish | Portuguese, provisional |
|---|---:|---:|
| Component correct | **8/16 → 11/16** | **6/16 → 12/16** |
| Strict service completion | **10/16 → 8/16** | **7/16 → 9/16** |

**Qualification failed. Keyword routing stays the default.**

- Each system attempted **32 component probes and 48 fresh HTTP journeys**:
  16 service + 8 safety journeys per language. Safety completion was **1/8 per
  language for each system**; six intended fault conditions were never reached.
- The same 50-record cohort and authored messages constrain generalization.
  Small balanced samples are not production rates; original failures remain frozen.

**Current engineering evidence, kept separate:** **752 synthetic tests passed**;
four installed-package fictional journeys (**v1/v2 × ES/PT**) completed the guarded
workflow, and two hosted keyword journeys completed through a loopback fake TLS
boundary. Container execution and real cloud HTTPS remain unverified.
Native-reference repair reached all eight intended safety conditions in
**32 invented journeys**. These are regressions, not a new held-out comparison.

**Current guarded learned serving is unscored.**

Footnote: [frozen results](final_workflow_results.md),
[frozen aggregate evidence](../evidence/final_workflow_results_v1.json),
[lookup repair](post_final_lookup_repair.md),
[current audit repairs](post_audit_repairs.md), [delivery checks](deployment_readiness.md).

Visual direction: a two-column results table above a clearly separate engineering
strip. Avoid a combined "accuracy" number, victory claim or green safety badge.

## Slide 5 — Run locally, inspect evidence, finish judge access

```text
python -B -m bank_service web --port 8765
python -B -m unittest discover -s tests -q
```

**Inspect:** source audit → frozen protocol/results → current repair evidence.

**Current status:** local ES/PT demo; private development repository; deployment
and submission delivery pending.

**Remaining limits:** trusted test identity rather than production login; historical
snapshot uncertainty; temporary session receipts; Portuguese review gap; no untouched
post-repair evaluation or production latency/cost/scale validation. Remaining
automation and missed-escalation metric definitions are documented as unfinished.

**Submission links — visibly pending**

- `PUBLIC REPOSITORY URL — PENDING OWNER PUBLICATION`
- `DEPLOYED TOOL URL — PENDING DEPLOYMENT AND JUDGE-ACCESS CHECK`
- `VIDEO URL — PENDING RECORDING AND VIEWER-ACCESS CHECK`

The known development repository is
[ET-777/factored-hackathon-2026-claro](https://github.com/ET-777/factored-hackathon-2026-claro).
It is private and does not fulfill public judge access. Do not render invented URLs
or an inaccessible development link as completed submission access.

Footnote: [README](../README.md), [requirements](requirements.md),
[current repairs](post_audit_repairs.md), [video script](submission_video_script.md).

Visual direction: commands and an evidence index on one side; a conspicuous pending
access panel on the other. Replace placeholders only after actual access verification.

## Deck production checks

Editable draft: [five-slide PowerPoint](../submission/transaction-support-draft-v4.pptx).
All five slides were rendered and visually checked with the bundled presentation
runtime; tables and text remain editable. Native PowerPoint execution is unverified.

- Preserve exactly five slides and English explanatory copy. Customer UI prompts
  remain Spanish/Portuguese.
- Keep counts, denominators, frozen/current labels and failed qualification visible.
  Prefer short footnotes using the repository paths above.
- Use only fictional `DEMO-TX` screenshots. Exclude raw source records, final cases,
  credentials, source PDFs, private browser state and private output-review material.
- Verify slide rendering and readable text before export. A video script, slide
  source or local UI is not evidence that the required recording exists.
