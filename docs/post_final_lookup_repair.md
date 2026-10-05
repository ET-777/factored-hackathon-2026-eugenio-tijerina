# Native-reference lookup repair

The application now recognizes the supplied transaction-reference format in chat,
including bare IDs, balanced typing quotes and an `id:` label. A unique match
resolves to the exact stored key, including literal source quotes. Native IDs
remain case exact; legacy `DEMO-TX` uppercase compatibility is retained.

This repair follows the exposed [frozen comparison](final_workflow_results.md).
It is a post-final engineering increment, not a rerun or a new final score.
The original scores and failed qualification criteria remain unchanged. The
keyword router remains the default; optional naive Bayes v2 retains alpha 1.

## Behavior and authorization

The new server-owned `bank_service/transaction_references.py` helper recognizes
identity without giving the classifier access, consent or record facts.
`BrowserSession` passes the exact reference through the existing ownership,
read-permission and session-expiry checks. Foreign and unknown IDs return the
same generic denial. Colliding stored quote aliases also fail with that denial;
invalid or denied new references clear stale selection before further action.
Distinct references require clarification rather than choosing a record.

ID spans are masked before ordinary date, amount and currency parsing, so an ID
containing `USD`, numerals or a date does not create false search filters. Unicode
letters or combining marks beside an ID cannot select a partial reference, and
identifier spelling is not accent-normalized. Actual adjacent dates and amounts
still work. A standalone reference starts an inquiry or continues a trusted
pending search; it cannot independently start a dispute or human handoff.
Explicit dispute prose still requires preparation consent and separate final
confirmation before saving.

## Verification

- The complete regression suite passed **677 tests** in Python 3.11.0, including
  17 new reference tests and eight new safety tests.
- All **50** records in the existing bounded private cohort passed **400** exact
  parsing checks: four input forms in Spanish and Portuguese. Their source
  spelling, evidence and cohort bytes were preserved.
- **100** fresh local read-only HTTP journeys, one per record and language,
  selected the exact record with an answered status, no draft or offer and no
  persisted case. These checks used keyword mode and did not load a trained model.
- **32** invented safety journeys exercised all eight intended conditions:
  foreign access, read-only intake, expiry, declined preparation, chat assent
  without saving, cancellation, duplicate confirmation and persistence failure.
  Each condition ran in both languages with keyword routing and a fixed synthetic
  dispute proposal. Assertions checked that the actual offer, draft, confirmation,
  denial or failure endpoint was reached, plus SQLite/readback behavior.
- Duplicate confirmation produced exactly one persisted case with verified
  readback. Injected persistence failure returned HTTP 409 `unknown_outcome`,
  retained an unverified draft and produced neither a case nor a success receipt.
- A separate read-only code reviewer reproduced the Unicode and alias-collision
  edge cases with invented values and found no remaining blocking issue.
- Working-tree privacy checks passed 165 eligible files with zero violations
  and eight of eight exclusion probes. Git history and dictionary credential
  values were not scanned.

Run the reproducible synthetic regressions from the repository root:

```powershell
python -B -m unittest tests.test_transaction_references tests.test_post_final_safety_paths -q
python -B -m unittest discover -s tests -q
python -B scripts/check_private_artifacts.py
```

The aggregate evidence is [post_final_lookup_repair_v1.json](../evidence/post_final_lookup_repair_v1.json).
The aggregate-only cohort checker and preservation checker are private local
scripts at `.local/check_post_final_native_refs.py` and
`.local/check_post_final_preservation.py`; they can be rerun on the same machine.
They read the existing validated snapshot, not the full raw download, PDFs or
evaluation cases, and never print source values.

## Preserved evidence and limits

Before editing, 90 frozen code/test/UI/protocol/TRAIN files were byte-verified
and archived privately at `.local/frozen_workflow_v1/code_snapshot`. All 114
protected exposed-run artifacts, review files, frozen reports/evidence and the
owner-created readiness file remain byte-identical. The freeze, one-attempt
execution claim and original outcomes are unchanged. Of previously frozen code
files, only `bank_service/web_app.py` changed; the helper and tests are additions.
Routing, TRAIN, evaluator, authorization and persistence modules are unchanged.
The earlier fictional-record final set remains unopened.

The 100 source-backed journeys check lookup integration; the 32 invented
journeys check reached safety behavior. Neither measures new held-out routing
performance, independent conversational generalization or Portuguese naturalness.
Portuguese fluent-human review and review of actual final Spanish outputs remain
pending. This does not retroactively qualify the earlier unexercised safety paths
or justify model promotion. New benchmark claims would require a separate
untouched set and declared protocol.

Next, review the repaired live inquiry and consent flows, then prepare the hosted
prototype and English submission materials with these evaluation limits stated.
