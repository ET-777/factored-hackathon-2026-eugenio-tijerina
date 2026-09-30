# Full local customer, product and transaction review

The full local evidence supports keeping **transaction inquiry with simulated dispute intake and human handoff**. Ownership joins are consistent across every inspected transaction. The material change is a mandatory eligibility filter: nearly one third of transactions conflict with dates in the current customer/product snapshots. A recent, explicitly validated serving cohort is appropriate; blindly loading all transactions into the prototype is not.

This review preserves the earlier bounded audit and describes the user's downloaded local files. It does not change source records, train a model, inspect the private final evaluation, or validate real banking actions.

## Coverage and reproducibility

| Input | Files | Parsed rows | Bytes |
|---|---:|---:|---:|
| Customers | 1 | 150,000 | 46,897,358 |
| Products | 1 | 400,000 | 68,213,646 |
| Transactions | 1,097 | 4,425,008 | 808,333,639 |
| Total reviewed | 1,099 | 4,975,008 | 923,444,643 |

Transaction `process_date` covers all **1,097 dates from 2023-06-17 through 2026-06-17**, with a single 22-column header schema across all daily files. Customer and product headers contain 27 and 17 columns. No malformed parsed rows were found. This is a complete scan of the discovered local transaction files, not a statistical sample.

The dictionary advertises 5,000,000 transactions; the local files contain **4,425,008**. The date coverage and full local scan are verified. Whether the count discrepancy reflects generation choices, a different dataset release, or unavailable exports remains unconfirmed; do not label the local export organizer-complete solely from its date coverage.

The main pass took **345.61 seconds**, followed by a brief independent check that all dimension dates used for temporal comparisons parse. All 1,099 input files have private SHA-256/size/mtime provenance. The source-set fingerprint and aggregates are in [`../evidence/local_transactions_summary.json`](../evidence/local_transactions_summary.json); detailed paths and the disk-based transaction-key index remain under ignored `data/local_review/transactions_*/`.

Reproduce with standard-library Python:

```powershell
python -X utf8 scripts/audit_local_transactions.py --source "../Data"
```

Each run creates a new ignored provenance/index directory and replaces only the new public aggregate summary. It never reads credentials, PDFs, `evaluation/final_private`, or the network. The original bounded-audit evidence is preserved. Counts are aggregate-only; the public output contains no source row identifiers, names, account numbers, transaction descriptions or raw text.

## Findings that affect the scope

| Finding | Verified evidence | Consequence |
|---|---|---|
| **Ownership joins pass** | Every product owner exists among the 150,000 customers. All 4,425,008 transactions have existing customer and product references; transaction customer equals product owner in every row. Zero product-currency versus transaction-currency mismatches. | Source-backed transaction lookup is feasible. Application code must still enforce the authenticated principal's permissions; source consistency is not user authentication. |
| Primary IDs and required-field presence pass | All 150,000 customer, 400,000 product and 4,425,008 transaction primary IDs are unique. Zero exact duplicate excess rows, conflicting primary IDs, or missing values in the explicitly checked required columns. | No deduplication or ownership repair is needed for these files. Other uniqueness rules, such as document/account numbers, and all business/type constraints were not exhaustively audited. |
| **High: chronology conflicts with current snapshots** | **827,610 transactions (18.7030%)** precede the current product opening date; **829,540 (18.7466%)** precede the current customer registration date. Their union is **1,450,689 (32.7839%)**. The counts overlap and must not be added. All compared dimension dates and transaction dates parse. | Exclude these rows from the first serving cohort and surface a data-quality reason when encountered. Do not rewrite dates, reassign owners or infer historical validity. Current snapshots do not contain historical ownership/validity intervals, so this is a cross-file temporal inconsistency, not proof of fraud or unauthorized activity. |
| A usable checked subset remains | **2,974,319 transactions (67.2161%)** have none of the explicitly checked row issues. On **2026-06-17**, all **5,342** transactions pass the two date-order checks; the preceding day still has one pre-opening and three pre-registration flags. | Start source-adapter development from a small deterministic cohort, potentially in the final partition, and apply eligibility checks per row. These counts do not certify every policy, lifecycle or date-time rule. The audit compares calendar dates; same-day ordering is not assessed. |
| Native monetary fields are usable | All 4,425,008 `amount` values parse as finite positive decimals. Every populated `amount_usd` value also parses as finite positive decimal. USD: 2,437,979 transactions; COP: 1,194,444; ARS: 792,585. **No MXN products or transactions** occur anywhere in these local tables. | Return exact stored native amount and currency. Do not imply the source covers all advertised currencies or invent MXN/BRL cases as organizer records. Independently authored fixtures must be labeled as such. |
| Optional facts are genuinely absent | **54,172 of 1,083,406 purchases (5.0002%)** lack a merchant name. `amount_usd` is blank for **all 2,437,979 USD transactions**, plus 59,436 COP and 40,041 ARS transactions. | Keep unknown merchants explicit. Prefer native amounts; missing `amount_usd` on a USD transaction is not evidence that its known native USD amount is unavailable. Do not silently fill or rewrite source conversion fields. |
| Status coverage supports a meaningful demo | Approved: 4,070,681; Declined: 221,234; Pending: 88,343; Reversed: 44,750. All four statuses occur in every year. | The prototype can demonstrate varied stored statuses and clear abstention on absent reasons, refund eligibility, settlement timing and policy details. |
| Fraud-positive records exist, revising the tiny sample | **4,316 positive fraud labels (0.09754%)**, versus zero in the earlier 500-row sample. Positive examples occur in all four years. | The old finding was sample-specific. This still does not justify expanding the 34-hour submission into fraud prediction: class imbalance, feature timing, temporal inconsistencies and independent label validation would add a separate evaluation problem. Do not interpret an unrecognized-charge request as confirmed fraud. |
| **Medium: timestamp interpretation remains unresolved** | Every transaction timestamp lacks explicit timezone information. **1,106,307** transaction calendar dates differ from `process_date`. | Treat the partition as processing metadata. Confirm timezone and business-day rules before claiming event-time or historical-cutoff guarantees. The audit does not establish the cause or direction of every difference. |

The zero orphan/duplicate counts above apply to these three local tables and the tested relations. They neither establish global data quality across other tables nor refute the dictionary's approximate dataset-wide quality claims.

## Coverage by process year

Years 2023 and 2026 are partial years. The temporal columns below overlap.

| Process year | Transaction rows | Fraud-positive labels | Before current product opening | Before current customer registration |
|---|---:|---:|---:|---:|
| 2023 | 801,170 | 814 | 273,430 | 273,922 |
| 2024 | 1,471,814 | 1,485 | 359,195 | 361,132 |
| 2025 | 1,466,502 | 1,414 | 175,218 | 175,175 |
| 2026 | 685,522 | 603 | 19,767 | 19,311 |
| Total | 4,425,008 | 4,316 | 827,610 | 829,540 |

The machine-readable evidence additionally preserves daily and annual currency/status/fraud counts and daily temporal flags. Sparse annual/daily counters omit zero categories; the main checked-defect counters explicitly include zeros. No model accuracy, resolution improvement or operational cost saving has been measured.

## Minimal implementation implications

1. Build a read-only source adapter that validates required fields, exact decimal amounts, customer/product existence, consistent ownership/currency and applicable date order before exposing a record. Preserve a quarantine reason for ineligible records; retain the original file unchanged.
2. Treat exact duplicates as a separately detectable ingestion condition and conflicting primary IDs as a reason to quarantine **every** version until reviewed. Neither condition occurred in this scan; keep the boundary for future inputs without inventing repairs.
3. Enforce authorization outside the model using the trusted principal and both transaction and product ownership. Use an explicit, reviewed policy for customer/product status; a current status is not historical authorization evidence.
4. Select a small, deterministic, eligible recent cohort for local development and demonstrations. Record its source fingerprints and selection rule. Do not move audited examples into the untouched final evaluation or use source outcomes to tune it.
5. Keep the learned component narrow: reviewed bilingual intent routing, with deterministic grounded transaction facts and verified simulated action receipts. Fraud prediction, balance reconstruction and historical dispute adjudication remain separate problems.

This audit strengthens the transaction-inquiry choice while narrowing which source rows are suitable for a trustworthy demonstration. It does not establish Portuguese source coverage, dispute policies, redistribution rights or real ticket/action APIs.
