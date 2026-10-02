# Selected scope and next implementation step

**Selected under the user's delegated decision:** a Spanish/Portuguese transaction
inquiry assistant that can clarify a transaction, explain its recorded facts, and
prepare a **confirmed simulated dispute intake** or a useful human handoff.
Intake completion means a verified case receipt, not dispute resolution or a refund.

## Why this workflow

The [local-data review](local_data_review.md) supersedes first-day scope estimates with
all relevant files in the user-provided download. Among 686,296 interactions,
240,056 (34.98%) are Transactional, the largest category in every year. Product is
150,863 (21.98%) and Complaint 117,021 (17.05%). These broad categories describe the
supplied synthetic corpus; they do not establish real-bank demand or the exact share
requesting dispute intake. The initial [audit](audit.md) remains historical evidence.

| Candidate | Demand / record support | Effort and evaluation feasibility | Decision |
|---|---|---|---|
| Transaction inquiry, with simulated intake/handoff | Largest contact category; 4,425,008 transaction rows with consistent customer/product owner and currency joins. 12,297 complaints have an unrecognized-charge subcategory. | Exact record facts, authorization, ambiguity, confirmation and receipts have deterministic oracles. Chronology conflicts require quarantine first. | **Selected.** Complete this one workflow within the reserved time. |
| Complaint-status assistant | 117,021 Complaint contacts and 67,095 complaint records. | All complaint origin-interaction keys are blank and no transaction key exists. A status lookup alone offers less complete demonstrated service. | Defer as a separate workflow. |
| Product/credit eligibility support | 150,863 Product contacts; customer/product dimensions now inspected; no verified eligibility policy. | Needs additional policy provenance and credit-specific evaluation/safeguards. | Defer. |
| Fraud scoring or prediction | Full local scan finds 4,316 positive labels among 4,425,008 transactions (0.0975%), correcting the small sample's absence. | Severe imbalance, chronology issues and unknown point-in-time label/feature availability require a separate evaluation design. | Defer. Presence of labels does not establish a credible classifier or service workflow. |

Transaction/customer/product ownership and currency consistency now pass across all
4,425,008 inspected transactions and both full dimension snapshots. However,
**1,450,689 transactions (32.78%) predate the supplied customer registration or product
opening date**. Quarantine these conflicts without rewriting dates or owners. A small
private source cohort must pass the complete serving contract; the public demo continues
to use clearly labeled, independently authored fixtures. Current snapshots do not prove
historical ownership intervals, and a chat-supplied ID is never authentication.

## Service boundary

1. Start from a server-owned trusted test session and a selected language (`es`/`pt`).
2. Interpret one of four intents: inquiry, dispute intake, human request, unsupported.
3. Resolve only an authorized transaction. Ask a follow-up when zero/multiple plausible
   matches or missing facts prevent an answer. Preserve context across turns.
4. Return only permitted record facts, their source reference and snapshot time.
   Unknown policy, merchant details, refund rules or settlement times stay unknown.
5. For an unrecognized charge, prepare a draft with transaction and user-stated reason.
   Require explicit confirmation tied to that draft; create one local simulated case.
6. Read back and verify the persisted result before claiming creation. On an ambiguous
   write outcome, reconcile or hand off without a false success message.
7. Produce a human packet with request, verified facts, source references, actions and
   receipts, escalation reason, and unresolved questions. A simulated queue is labeled.

No live money movement, reimbursement, chargeback adjudication, card blocking, lending,
new workflow, full-dataset ingestion, or production bank integration is in this scope.
No authentic bank policy was supplied: any demo intake rules must be labeled synthetic.
The dictionary's complaint schema lacks a transaction ID (pp. 12-13, 15-16); new intake
links are app-created simulation records, never reconstructed historical facts.

## Learning that is small enough to evaluate honestly

Use a local character n-gram intent classifier trained on separately authored,
reviewed Spanish/Portuguese training phrases, versus deterministic bilingual keyword
rules. Both use identical tools, state, permissions, grounding templates and confirmation
rules. The only experimental change is the intent component. A classifier suggests
intent; it cannot grant permissions or execute an action.

The full source transcript corpus is unsuitable for blind supervision: 171,321
customer transcripts have only 42 normalized distinct texts, all with contradictory
topic labels. Per-text majority agreement is 59,786/171,321 (34.897%), equal to the
overall majority label. This is a corpus diagnostic, not a measured model result or a
universal accuracy ceiling under corrected labels. `detected_intents` is
`consulta_general` in 162,864 rows and missing in 8,457. Use category metadata for corpus composition and records for schema feasibility, not verified intent demand; keep training label
provenance separate, avoid agent-response/outcome fields, and group template paraphrases
and translations before splitting. Portuguese cases are team-generated, not native
organizer records. Human language/label review remains required.

See [evaluation.md](evaluation.md) for predeclared success criteria, development cases,
the sealed final workload, leakage controls, failure denominators and language breakdowns.
No model improvement or production efficiency gain has been established in this session.

**October 2 scoped organizer permission:** the earlier September 29 mock-data reply
requested context and led to the October 1 eligibility gate. The owner then supplied a
screenshot of their specific question about generated ES/PT evaluation messages using
supplied transaction records and separately labeled simulated safety/tool-failure
scenarios. Diego replied: "Yes just make sure to justify it". The exact question and
screenshot source limits are in [source_intent_inventory.md](source_intent_inventory.md);
the live Slack permalink has not yet been retrieved. Justify the missing intent/PT
coverage, distinguish record/message/fault provenance, and review labels, independent
families and Portuguese wording before freezing a comparison protocol. The reply does
not blanket-approve the existing fictional-bank-record workloads or authorize opening
or replacing their final seal. The selected customer workflow is unchanged.

The [completed source-intent inventory](source_intent_inventory.md) found only two
balance-request opening families across 42 full-text variants; all are outside this
transaction workflow. These transcript texts do not substantiate the workflow's exact
customer-intent demand or supply a four-class benchmark. Keep the metadata/record
feasibility rationale separate from observed utterance coverage.

## Next concrete implementation step

The validated adapter, bounded private source cohort, guarded lookup, grounded bilingual
answers and selection now exist. The [local workflow checkpoint](local_workflow.md) adds
multi-turn structured inquiry, confirmed simulated intake, SQLite idempotency/readback,
and consented handoff. Its demonstration uses independently authored fictional records,
not either evaluation split. These are implementation checks, not final quality scores.

The [local interface](local_ui.md) and keyword baseline now implement the browser
journey for independently authored demo records. The [October 2 increment](private_cohort_ui.md) connects the
existing validated private cohort to a separate loopback UI mode, with identity and
permissions from trusted startup configuration rather than browser input. Preserve
exact record facts, owner checks, snapshot uncertainty, simulated actions and verified
receipts; keep source evidence private and the fictional demo unchanged. Do not load
the full dataset behind the app.

The bounded source-intent inventory is complete and cannot supply the four-class
benchmark. The scoped generated-message plan now has organizer permission with
justification; reviewed labels, independent class/family coverage, Portuguese review
and a comparison protocol remain pending before fitting or threshold selection. Any
new final workload needs a separate authorized freeze. The constructed scenario
adapter remains deferred diagnostic work, with native currencies/status meanings
separate from strict source validation. Do not revise the existing sealed final cases
to fit implementation. Next establish the reviewed source-grounded authored ES/PT
workload and shared comparison protocol before fitting. This increment includes no
training, performance scoring, public release or deployment. Scope is selected; no further scope-approval question or
source download is needed.

Use [architecture.md](architecture.md) as the tool/data contract and
[submission_plan.md](submission_plan.md) for the protected 34-hour budget, prototype,
five-slide deck and three-scene demonstration plan. Keep the internal October 4,
16:00 America/Monterrey target. The user-confirmed official deadline is October 5,
23:59 GMT-5 (22:59 America/Monterrey); video duration is at most three minutes.
