# Bounded source audit - September 26, 2026

Historical first-session evidence. The subsequent [local-data review](local_data_review.md)
extends these findings to all relevant files in the user's download. Keep this report
and its sample counts unchanged; current scope and decisions are recorded in that review
and in [scope.md](scope.md).

## Decision supported by this audit

Recommend **grounded transaction inquiry with simulated dispute intake and a useful human handoff**, subject to the owner's scope decision. Transactional contacts are the largest category in the inspected day, the transaction fields support precise read-only answers, and the small complaint sample supports an intake demonstration. This audit does **not** establish production demand, a real dispute-resolution policy, or a predictive fraud use case.

Do not use the provided transcript topic labels as unreviewed intent ground truth: identical customer text occurs with conflicting topics. This changes the learned-component plan toward a small reviewed intent dataset, template-group separation, and an independent final evaluation.

## Sources, selection, and reproducibility

- Reference authority: `LATAM_Bank_Complete_Data_Dictionary.pdf`, physical PDF pages 3, 8-10, 12-13 and 18. Page 2 supplies local access configuration; its contents are never copied here. The PDFs are organizer references, not verified data measurements.
- Source access succeeded using read-only S3 listing and ranged reads. Four tables, the lexicographically first CSV object visible in each bounded listing, first **up to 500 complete rows per object**, source `process_date` **2023-06-17**. No random sampling or representativeness claim.
- **1,010 retained rows**: 500 transactions, 384 call-center interactions, 38 complaints, 88 transcripts. The three smaller first-day objects contain fewer than 500 rows. Four range requests each capped at 1 MiB happened to return each small first-day object in full; only the first 500 transaction rows were retained/profiled.
- **11 request attempts: 10 successful, 1 sandbox network failure; 748,416 response-body bytes (0.714 MiB), including listings.** Hard caps: 12 requests, 20 MiB, 500 retained rows/table; actual four-table maximum 2,000 retained rows. No pagination beyond the first 40 listed entries, no full-dataset download, source writes, paid model calls, or publication.
- Each table listing was truncated. This is a first-partition feasibility sample with strong date/order bias. It cannot verify global row counts, geographic distributions, drift, freshness, late arrivals, duplicate rates, or full referential integrity.
- Ignored `data/audit/manifest.json` records selected source object keys, object sizes/ETags, response SHA-256, retained-sample SHA-256, byte ranges, row caps and audit UTC time. Ignored `data/audit/request_ledger.json` records cumulative resource use. Raw samples remain under ignored `data/audit/`.
- Public machine-readable evidence: [`../evidence/audit_summary.json`](../evidence/audit_summary.json). Source rows, identifiers, transcript text, object keys and credentials are excluded. Public category values use an explicit allowlist; unrecognized source strings are withheld.

Recompute the public aggregates without credentials or network, using a Python interpreter with the standard library:

```powershell
python -X utf8 scripts/audit_subset.py --offline
python -m unittest discover -s tests -v
```

Offline replay verifies retained-sample SHA-256 values before profiling. Initial source access additionally requires `pypdf` and the private dictionary path. The script retains its cumulative budget ledger and refuses further reads after the cap; replay is the normal development path. Never put the dictionary, its access configuration, or raw samples in the public repository.

## Documented claims versus verified observations

| Topic | Organizer documentation | Verified in this bounded sample |
|---|---|---|
| Dataset | ~19 million records, 13 tables, synthetic, June 2023-June 2026 (pp. 1, 3) | Only the four tables and first partition above. Whole-dataset size and coverage unverified. Synthetic provenance is the organizer's claim. |
| Language | Text in Spanish with regional variation (pp. 3, 18) | Transcript `detected_language`: 88/88 `es`; no Portuguese examples. Locale enum fields mix Spanish and English. This is a stored language field, not independent linguistic annotation. |
| Schema | Transactions pp. 8; interactions p. 9; transcripts pp. 9-10; complaints pp. 12-13 | Column names match all four documented schemas: 22, 21, 18 and 27 columns respectively. Type/constraint compliance is only partially checked below. |
| Quality | About 2% duplicates, 5% nullable-field nulls, late arrivals and schema evolution (p. 3) | Zero duplicate primary keys/exact rows within the retained sample. Null rates vary greatly by field; this does not validate or refute the global 2%/5% claims. |
| Relationships | Foreign keys, with a small proportion of orphans for testing (p. 18) | All 88 transcripts match sampled interactions with consistent customer and agent IDs. Customer/product dimension ownership joins were not audited. No global orphan claim. |

## Findings and implications

| Finding | Evidence and confidence | Impact / next action |
|---|---|---|
| Transactional demand is promising, only for this day | 134/384 contacts (34.9%) transactional; complaints 80/384 (20.8%); product 79/384 (20.6%); technical 48/384 (12.5%); commercial 32/384 (8.3%); retention 11/384 (2.9%). High confidence in counts, low confidence in population representativeness. | Supports a narrow transaction workflow; do not pitch these percentages as bank-wide demand. `contact_reason` equals `reason_category` in all 384 rows, so it supplies no finer-grained demand label. |
| **High: provided text labels conflict** | 88 transcripts contain 25 unique normalized `customer_text` values. Eleven identical-text groups have multiple `main_topics`, affecting 73/88 rows. The sum of per-group majority counts is only 44/88. Full text: 36 groups, five conflicting groups covering 57 rows; majority count 52/88. `detected_intents` is `consulta_general` on 85/88 rows and null on 3/88. High confidence. | A deterministic classifier using only normalized customer text cannot reproduce more than 50% of these supplied topic labels on this sample. This is a descriptive label-conflict bound, **not a trained-model result**. Use manually reviewed intent labels, independent authored Spanish/Portuguese requests, and keep entire template/paraphrase families in one split. Do not use post-interaction metadata as classifier input. |
| Transactions support exact, qualified answers | All 500 have transaction/customer/product IDs, amount, currency, date and status; no duplicate primary keys. Approved 453, Declined 25, Pending 14, Reversed 8. Amounts parse as finite positive decimals in this sample. High confidence. | Deterministic lookup can ground amount, currency and stored status. Do not invent reasons for decline, settlement timing, policy eligibility or fraud judgments; those are not verified facts in these fields. |
| **High: missing optional facts must remain unknown** | Merchant absent in 396/500 overall, including 5/109 purchases (4.6%); USD amount missing in 294/500 (58.8%). High confidence. | Do not synthesize merchants or exchange rates. Use stored native amount/currency. Currency coverage is USD 284, COP 133, ARS 83; **no MXN transactions in this order-biased sample**. Do not sum amounts across currencies or infer a global currency problem. |
| **High: no direct evidence for historical transaction disputes** | Complaint schema has no `transaction_id`; all 38 `origin_interaction_id` values are blank and 12/38 affected products are blank. Six of 38 complaint subcategories are `Cargo no reconocido`; seven are `Cobro indebido`. High confidence. | Show new **simulated** intake linked explicitly to the selected transaction in local state. Do not claim the source complaints prove historical transaction-level dispute outcomes, or that simulated tickets enter a real bank system. |
| Escalation is observable but not an action policy | 39/384 contacts escalated (10.2%); 147/384 require follow-up (38.3%); 102/384 marked unresolved (26.6%). High confidence in stored labels; overlapping groups. | Useful motivation for handoff. These outcomes are not authority to automate eligibility, priority, refund, or resolution decisions. |
| **Medium: schema constraints and time interpretation need care** | Transcript duration missing on 16/88 although dictionary p. 10 marks it NOT NULL. One of two Closed complaints lacks a closing date; no nonblank checked complaint lifecycle timestamp precedes creation. 138/500 transaction timestamps fall on the calendar day after `process_date`; all 500 transaction timestamps lack an explicit timezone. High confidence. | Keep duration optional for this workflow. Do not treat a process partition as a precise time cutoff; confirm timezone and business-day convention before temporal evaluation. Closing-date absence is an observation, not a violation of a documented NOT NULL constraint. |
| **Medium: enum normalization is required** | Interaction categories are Spanish and include `Retención`; p. 9 describes five categories in English and omits retention. `México` and `Mexico` both appear in transaction-country values. High confidence. | Normalize display/routing categories explicitly while preserving raw values locally. Column-name agreement does not prove enum agreement. |
| Fraud learning is unsupported here | `is_fraud=False` on all 500 transactions. High confidence in this sample only. | Do not train or claim a validated fraud classifier from this audit subset. |

## Boundaries and unresolved questions

1. Neither customers nor products were sampled. No product-owner or transaction-product-owner join has been verified; identity and authorization must still be enforced by trusted application code against a validated local fixture.
2. No source policies, refund/dispute eligibility rules, live banking API, existing ticket creation API or Portuguese evaluation corpus were verified. Those remain unavailable evidence, not permission for the model to invent them.
3. Ask the organizer about timestamp timezone/business-day convention, the conflicting transcript-topic labels, missing required durations, and permission to redistribute even synthetic source records. Until clarified, publish code plus independently authored demo fixtures and aggregate evidence only.
4. This sample is development/audit evidence and is **not eligible for the untouched final evaluation set**. Final cases must use separate scenario/template families and withheld labels; outcome leakage and copied source templates would invalidate a convincing evaluation.
5. Recommended next implementation step: build a deterministic transaction lookup and policy/action adapter against small reviewed local fixtures; then establish keyword/template baseline behavior before training a bilingual intent router on separately reviewed examples.

No baseline, learned model, end-to-end quality score, deployed prototype or business impact has been measured during this audit.
