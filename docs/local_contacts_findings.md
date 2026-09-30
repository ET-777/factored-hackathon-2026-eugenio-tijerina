# Full local contact-corpus audit

## Decision

Retain **grounded transaction inquiry, followed when needed by user-confirmed simulated dispute intake and useful human handoff**. The full local corpus strengthens the demand rationale and the case for a narrow workflow. It does not support a pivot to automated dispute resolution, refund decisions, or training directly on supplied transcript labels.

Keep a small locally trained bilingual intent classifier as a **bounded candidate compared with a rules baseline**, trained on independently authored, manually reviewed intent examples. Do not spend the solo 34-hour budget fine-tuning or benchmarking against these source topic labels. The compelling work should be trustworthy data preparation, external permissions, grounded answers, verified simulated actions, and honest Spanish/Portuguese evaluation. Include the learned candidate only if the frozen comparison demonstrates a benefit; no benefit is currently measured.

## Scope and reproducibility

This audit read every CSV present in the three specified local directories under `../Data`, one daily partition at a time. It made no network requests, read no PDFs or credentials, wrote no source files, and neither opened nor changed the sealed final cases. It completed in 66.844 seconds, inside a 600-second runtime cap.

| Local table | CSV files | Verified rows | Bytes read |
|---|---:|---:|---:|
| Call-center interactions | 1,097 | 686,296 | 139,734,950 |
| Call transcripts | 1,097 | 171,321 | 137,235,657 |
| Complaints | 1,097 | 67,095 | 17,990,612 |
| Total | 3,291 | 924,712 | 294,961,219 |

All three tables span process dates **2023-06-17 through 2026-06-17**. These are verified counts for files present locally. They are below the previously reported approximate 800,000/200,000/80,000 table sizes. Local date coverage and file counts do not establish completeness against remote objects, source checksums, or exact organizer targets; no remote reconciliation was performed.

The ignored `data/local_review/contacts_manifest.json` records each input's relative path, byte count, and SHA256. Public aggregate evidence is [`../evidence/local_contacts_summary.json`](../evidence/local_contacts_summary.json). The ordered input corpus commitment is:

`7718b699bc879a77dfec8e214fb1b2d0f21a89ed5d16e30576d13b2678c3d819`

The hash uses compact UTF-8 JSON of per-file `{relative_path, bytes, sha256}` records sorted by relative path. The public evidence also records the exact private-manifest SHA256. Raw text, identifiers, source rows, and unexpected category strings are excluded from public outputs. Source size/modification metadata remained stable while each file was read; this is not a promise that files cannot change afterward.

Reproduce offline with the standard library:

```powershell
python -X utf8 scripts/audit_local_contacts.py --data-root ../Data --max-seconds 600
```

The runner is inspectable in [`../scripts/audit_local_contacts.py`](../scripts/audit_local_contacts.py). Seven isolated synthetic checks verified join matches, owner matching, normalization, conflicting-label counts, the majority-label bound, and overlapping-flag union logic. The full output also passed monthly/yearly/category/key/file reconciliation. These are audit checks, not model or end-to-end application scores.

## Demand across time

Transactional contacts are **240,056 / 686,296 = 34.9785%**, the largest broad category. Product contacts number 150,863; complaints 117,021; technical 102,899; commercial 54,879; retention 20,578. `contact_reason` exactly equals `reason_category` on all 686,296 rows, so these fields cannot distinguish transaction status questions from unrecognized-charge reports or other finer-grained transactional requests.

| Process year | All contacts | Transactional contacts | Share |
|---|---:|---:|---:|
| 2023, from June 17 | 123,545 | 43,303 | 35.0504% |
| 2024 | 228,210 | 79,978 | 35.0458% |
| 2025 | 229,056 | 79,936 | 34.8980% |
| 2026, through June 17 | 105,485 | 36,839 | 34.9234% |

Across all 37 process months, the transactional share ranges from **34.1512% in July 2025 to 35.6519% in April 2026**. The broad demand mix is stable in these local synthetic records. Partial first/last years are not comparable on raw volume; shares use their own observed denominators. These figures describe the supplied corpus, not real-bank production demand or addressable automated-resolution volume.

Among the 240,056 transactional contacts:

| Stored outcome flag | Rows | Share of transactional contacts |
|---|---:|---:|
| Unresolved | 20,385 | 8.4918% |
| Escalated | 23,841 | 9.9314% |
| Requires follow-up | 53,137 | 22.1353% |
| At least one of these three | 71,701 | 29.8684% |

The flags overlap; do not add their percentages. Most transactional contacts are marked resolved, and a follow-up/escalation flag does not prove a failure or an automatable opportunity. These stored outcomes motivate a useful handoff path but do not establish action policy, eligibility, expected savings, or causal impact.

## Transcript labels fail the intended learning use

**High severity; high confidence in the complete local counts.** The 171,321 transcript rows contain only **42 distinct normalized customer texts**. All 42 groups have multiple `main_topics`; every transcript belongs to a conflicting group. Each of the 37 process months contains all 42 texts, with all rows in conflicting groups. This is a corpus-wide issue, not a first-day sampling accident.

For each identical normalized customer text, take its most common supplied topic. Summing those counts yields only **59,786 / 171,321 = 34.8971%** agreement. That is exactly the overall Transactional majority count. A deterministic model choosing one supplied topic for each normalized text cannot exceed this in-sample agreement; even memorizing the texts supplies no gain over always predicting the majority topic. This is a descriptive empirical conflict bound, **not a trained-model score, held-out performance estimate, or proof that no useful intent can be learned with corrected labels**.

Full conversation text contains 546 normalized groups, all conflicting, with a corresponding bound of 59,887/171,321 = 34.9560%. Full/agent text would also include response-side information that is unavailable when routing the initial customer request, so it must not become a shortcut feature.

- Stored `detected_intents` is `consulta_general` on 162,864 rows and null on 8,457. It supplies no useful multi-intent supervision.
- Stored `detected_language` is `es` on all 171,321 rows, in every month; no stored Portuguese examples were observed. This is not independent language annotation.
- All 171,321 transcript rows join to an interaction, with matching customer ID, agent ID, `main_topics`/`reason_category`, and a true parent `has_transcript` flag. Relational agreement therefore does **not** establish semantic correctness: the inconsistent labels propagate consistently through the join.

The pattern is consistent with templated text and independently assigned or weakly associated metadata, but generator internals were not inspected and that cause remains an interpretation. A random row split would put the same 42 texts in train and test and conceal the lack of language diversity. Split reviewed examples by scenario/template family, keep translations together, and evaluate Spanish and Portuguese separately. Keep the existing final set unexposed.

## Complaint records support intake, not historical transaction resolution

**High severity for any historical dispute-outcome claim; high confidence in counts.**

- All 67,095 `origin_interaction_id` fields are blank. There are zero available complaint-to-interaction origin links; an orphan rate among nonnull links is **undefined**, not 0% successful linkage.
- `affected_product_id` is missing in **22,525/67,095 = 33.5718%**; 44,570 rows have a value. Product ownership or validity is not established by mere presence and was not joined by this audit.
- None of the 1,097 complaint CSV headers contains `transaction_id`.
- Complaint/category counts are Transactions 13,580; Fees 13,553; Technical 13,407; Branch 13,361; Service 13,194.
- `Cargo no reconocido` appears on **12,297/67,095 = 18.3277%** of all complaints; `Cobro indebido` appears on **12,194/67,095 = 18.1742%**. Subcategory is missing in 6,698 rows. Categories and subcategories are different dimensions; their counts must not be added as disjoint demand.

Unrecognized/undue-charge labels provide useful corpus evidence for an intake demonstration. They cannot link a particular historical transaction to a dispute outcome, substantiate reimbursement eligibility, or authorize automated refunds. The prototype should create its own explicitly simulated, idempotent receipt tied to the authorized selected transaction and carry a minimal factual summary to a human.

## Structural quality and temporal limits

Across all three tables, there are zero malformed parsed rows, missing primary keys, duplicate primary-key excess rows, or exact duplicate rows. Each table has one unchanged column layout across all 1,097 files. Process dates parse successfully and match their filename partition dates. No new stored language or broad topic category appeared in later months. This does not prove that all data types, business semantics, event timestamps, or every distribution are valid.

Structural uniqueness should not be confused with linguistic diversity: transcript primary keys are unique while their customer text has only 42 normalized values. Important missing fields persist at corpus scale: transcript duration is absent on 24,029 rows, and complaint product/origin links have the gaps above. Monthly null counts and categorical distributions are retained in the aggregate JSON for inspection; no untested claim of stable null rates or independent language quality is made.

Month/year cuts use `process_date`. Event-time timezone, late-arrival semantics, full customer/product ownership consistency, and source completeness remain outside this three-table audit. The dataset's synthetic provenance comes from organizer documentation, rather than something these checks can independently prove.

## Implication for the submission

The defensible story is: **transactional demand is consistently the largest supplied contact category; the text supervision is unreliable; therefore the system uses reviewed intent examples and verifiable records, with permissions and action confirmation enforced outside the model.** Keep source-data engineering evidence separate from constructed bilingual task evaluation.

Proceed with the current four-intent scope (`inquiry`, `dispute_intake`, `human_request`, `unsupported`). Use the rules baseline first, then a small local character n-gram classifier trained on separately reviewed bilingual examples. It is a routing component, not an authority or a fraud model. Do not train on `main_topics`, `detected_intents`, agent text, outcome fields, or duplicated source templates as if they were representative supervised examples. A label-cleaning/retraining project or an expanded predictive dispute model is not justified within the remaining solo budget.

This audit changes the confidence and scope rationale; it does not claim a trained model, a better baseline score, a resolved dispute, a deployed prototype, or business impact. The next implementation step remains an authorized transaction lookup with exact evidence-backed bilingual answers, followed by the shared confirmation and simulated-action path.
