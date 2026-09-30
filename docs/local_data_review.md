# Local dataset review and revised decisions

Reviewed September 26, 2026 (America/Monterrey). The user supplied a downloaded
`../Data/` directory and delegated the workflow decision. Source files were read only;
the original first-day audit and the sealed final evaluation cases were preserved.

## Decision

**Select transaction inquiry -> confirmed simulated dispute intake -> verified receipt
or useful human handoff**, in Spanish and Portuguese. Keep the learned component small:
a local character n-gram intent classifier trained on independently authored, reviewed
bilingual examples, compared fairly with deterministic keyword rules. The classifier
routes requests; the service controls identity, permissions, grounding and actions.

The stronger submission story is supported demand, explicit handling of unreliable
data, and demonstrated completion of one service journey. The fuller download justifies
better data contracts and stronger evidence; it does not justify more workflows. No
winning outcome or model improvement is guaranteed or currently measured.

## What was checked

| Coverage | Verified locally |
|---|---|
| Every CSV's metadata and header | 13 tables, 7,671 files, 5,349,322,481 bytes (5.35 GB / 4.98 GiB); one header layout per table. No missing filename dates within each observed table range. |
| Full customer and product files | 150,000 customers and 400,000 products. |
| Every transaction CSV | 4,425,008 transactions in 1,097 daily files. |
| Every contact-service CSV | 686,296 interactions, 171,321 transcripts and 67,095 complaints in 3,291 daily files. |
| Total row-level scope | **5,899,720 records across six tables**, 4,390 source files and 1,218,405,862 bytes of content. The other seven tables received metadata/header inspection only. |

The core process-date range is June 17, 2023 through June 17, 2026; campaign filenames
start July 1, 2023. There was no remote listing/checksum comparison. These counts describe
the files present, not certification that every organizer object was downloaded. The
transaction/contact/transcript/complaint counts are below the dictionary's approximate
5M/800k/200k/80k targets; do not label that difference missing data without source proof.
The snapshot is historical, not current bank information.
The four first-day local CSVs also match the original audit's source-response SHA256
values, confirming continuity with those earlier source objects.

## Findings that revise the first-session plan

| Finding | Verified evidence | Required revision |
|---|---|---|
| Transactional demand remains strongest | 240,056/686,296 contacts (34.98%); largest category in every year, with monthly share 34.15%-35.65%. | Replace the first-day estimate in the submission narrative with the full local contact counts. These are synthetic-corpus contact shares, not real-bank impact estimates. |
| Ownership is usable; chronology is not uniformly coherent | All 4,425,008 transaction/customer/product references exist and owner/currency comparisons agree. But 827,610 transactions precede their current product opening date; 829,540 precede current customer registration. The union is **1,450,689 (32.78%)**. | Add chronology checks to the source adapter. Quarantine conflicting rows without correcting their dates or owners. Current snapshots cannot establish historical ownership/version intervals. |
| A sufficiently large candidate cohort remains | 2,974,319 transactions have none of the audited issues; transaction/customer/product keys are unique in these files. | Build a small deterministic, private source cohort from validated rows. This count is not production qualification and does not settle policy eligibility or unchecked fields. Keep public demo fixtures independently authored. |
| Transcript supervision is worse than the small sample suggested | 171,321 transcripts collapse to 42 normalized customer texts; all 42 groups have conflicting topic labels. The per-text majority agreement is 59,786/171,321 (34.897%), equal to always choosing the majority topic. | Do not train or score our router against source `main_topics` or `detected_intents`. Use separately reviewed intent examples and family-level splits. Do not claim a random-row split measures language generalization. |
| Portuguese is still absent from source language tags | 171,321/171,321 transcripts have stored language `es`; no native Portuguese corpus was verified. | Use clearly labeled, team-authored Portuguese requests and controlled responses; review facts, negation, consent and handoff wording. Record fluent-review status honestly. |
| Historical dispute linkage is unavailable across the full complaint corpus | All 67,095 origin-interaction fields are blank; 22,525 affected-product fields are blank; no complaint file has `transaction_id`. There are 12,297 unrecognized-charge subcategories. | Create new simulated intake receipts linked by our app. Do not learn historical transaction-dispute outcomes or claim refunds/chargebacks are resolved. |
| Currency and missingness need explicit handling | No MXN products or transactions among the audited 400,000/4,425,008 rows. All USD transactions have blank `amount_usd`; native amounts are valid. 54,172/1,083,406 purchases lack merchant name (5.0%). | Preserve native currency/amount; do not infer MXN from a Mexican country field or invent a merchant/FX rate. A team-authored MXN demo remains labeled synthetic. |
| Fraud positives do exist | 4,316/4,425,008 transactions (0.0975%) carry a positive stored fraud label. | Supersede the first-sample absence as a scope rationale. Still defer fraud prediction: severe imbalance, chronology issues and unverified label availability demand a separate evaluation design. |

There are zero observed primary-key/exact-row duplicates in the six fully inspected
tables, and the contact tables' transcript joins are consistent. Those structural
checks do not prove semantic correctness: contradictory text labels join consistently.
No observed header drift proves only stable column layouts, not stable meaning/types.

## Concrete implementation changes

1. **Put a data-contract adapter before the tools.** Verify key uniqueness, owner
   consistency, supported enums, finite native money, required evidence, and transaction
   date at/after the supplied product-opening and customer-registration dates. Preserve
   raw provenance and quarantine reasons. Do not overwrite source files or manufacture
   corrected dates. Display the snapshot/as-of boundary and timezone uncertainty.
2. **Use two clearly labeled record sources with the same contract.** A small private
   source-backed cohort demonstrates engineering on supplied records; independently
   authored synthetic fixtures power the public demo and workflow tests. Do not load
   the full 5.35 GB into the interactive app or publish raw source data.
3. **Keep learning and evaluation independent of noisy source labels.** Freeze the four
   intents, author/review 80-120 training phrases, compare rules and the small classifier
   on development cases, and tune only there. Keep source adapter tests distinct from
   the 32-case final comparison. No source records or duplicated source templates enter
   the final set. The existing 19 development and 32 final cases remain unchanged.
4. **Preserve safety and packaging time.** Confirmation, idempotency, readback verification,
   useful handoff and both languages remain essential. No additional workflow, predictive
   fraud model, multi-agent app or large training pipeline is added to the 34-hour budget.

## User clarifications incorporated

- Official cutoff, reported and explicitly clarified by the user: **October 5, 2026,
  23:59 GMT-5**, equivalent to **22:59 America/Monterrey**. Internal target stays
  **October 4, 16:00 America/Monterrey**. This is user-supplied organizer information,
  not independent organizer verification.
- Video maximum: **180 seconds**. The revised storyboard totals **165 seconds**.
  No file formats, templates, additional rules or numerical rubric weights were supplied.
- The meaning of `public*` remains uncertain. Participants-only visibility is the user's
  hypothesis; plan public code and independent synthetic fixtures unless clarified.
- The supplied PDFs remain the only known rule documents. Absence of an additional
  license is not blanket permission to redistribute source records or send them to
  external providers. Credentials remain excluded everywhere.
- Portuguese human review is unresolved. Use a reviewer who is fluent if available;
  otherwise disclose the unvalidated linguistic quality instead of claiming human review.

## Reproduction and next step

These scripts use the standard library and require no credentials, API calls or package
installation. They read the source and write aggregate evidence/private manifests in
this project. The transaction audit creates an ignored SQLite key index for bounded
memory use. A source run takes several minutes; there is no need to repeat it routinely.

```powershell
python -X utf8 scripts/inventory_local_dataset.py --source ../Data
python -X utf8 scripts/audit_local_contacts.py --data-root ../Data --max-seconds 600
python -X utf8 scripts/audit_local_transactions.py --source ../Data
```

Detailed methods and input-content commitments are in
[contact findings](local_contacts_findings.md),
[transaction findings](local_transactions_findings.md), and the associated
[contact](../evidence/local_contacts_summary.json),
[transaction](../evidence/local_transactions_summary.json) and
[inventory](../evidence/local_inventory.json) evidence files. Detailed source-file
manifests and raw identifiers stay under ignored `data/local_review/`.

**Next step:** implement the validated read adapter and a small private source cohort,
then one authenticated lookup with evidence-backed ES/PT responses and cross-customer
denial. This establishes the service foundation before adding confirmed intake and
training the router. This review implements no assistant workflow, runs no model,
and performs no publication or deployment.

June 17, 2026 provides 5,342 transactions with neither chronology flag; use this as
a candidate starting partition, while still applying every row-level contract check.
The previous day's partition has chronology conflicts, so recency alone is not a rule.

Completion checks: source aggregate/provenance reconciliations passed; the existing
13 scaffold/audit unit tests passed; the 19 development/32 final case integrity checks
passed with the original final SHA256 unchanged; exact in-memory credential comparisons
found no matches in the 30 Git-eligible files and all eight exclusion probes passed.
These checks do not measure the future assistant's model or workflow performance.
