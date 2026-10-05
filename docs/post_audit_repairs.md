# Audit repairs — October 4, 2026

The requested router, privacy, encoding, installed-package and session fixes are
implemented. The keyword baseline remains the default. Optional v1/v2 learned
previews now use a guarded serving policy around the unchanged character n-gram
Naive Bayes model. No new final evaluation or model-selection experiment was run.

## Behavior changes

- Explicit reads, complaints, human requests and unsupported banking actions take
  precedence over ambiguous model labels. Unrelated messages ask what service is
  needed; a high classifier score cannot invent a complaint or human request.
  Indirect financial inquiries still use the learned classifier. Date/amount
  fragments continue the existing server-owned search. The policy is bounded
  wording recognition and remains experimental.
- Identifier recognition and quote-alias resolution receive only keys authorized
  by the current session's actual read/owner guard. A foreign generic key cannot
  change recognition or make an owned alias ambiguous. Recognizable missing/native
  IDs still fail through the same generic denial, and owned exact source keys
  remain supported. Authorization is independent of the model.
- Unicode is validated before input counters or conversation state mutate.
  Isolated UTF-16 surrogates return a clean error, while valid ES/PT text and emoji
  remain usable. Direct message/action/preparation ports receive the same guard.
- Expired sessions are reclaimed before admission. Busy sessions are skipped
  rather than closed during an action. Limits are 20 registered sessions and
  100 successful mints per rolling minute, replacing the lifetime mint quota.
  A replacement may briefly have one unpublished store. A failed rollback blocks
  further allocations until that one store is cleaned up.
- Rate-limit or replacement-construction failure preserves the old session.
  Active unverified writes block reset with HTTP 409 `action_not_verified`; the
  exact draft/idempotency key survives for receipt reconciliation. Expiry ends
  authority. Explicit reset/expiry disposal closes and deletes only that session's
  local SQLite files; receipts are temporary session state, not a bank archive.
- Both fixed authored TRAIN JSON resources ship inside the Python package.
  Their bytes, raw training algorithm, features and alpha 1 remain unchanged.
  Historical artifact review metadata stays intact; current decisions are separate.
- Portuguese `esta cobrança` preserves the selected transaction. Requests for
  another charge or plural charges do not reuse a singular selection.
- The prospective disclosure oracle checks known foreign-only merchant literals
  in assistant replies and retained/setup messages, including case/accent forms
  and JSON escapes. Owned/shared names and user-only messages remain allowed.
  This conservative literal test can flag an independently used name; it does
  not establish semantic privacy, translation coverage or full answer grounding.

## Verification and preservation

The complete synthetic suite passed **724 tests** in Python 3.11. An independent
privacy review found no remaining bypass: 672 paired foreign-present/absent probes,
48 owned-alias probes and 12 authority probes used invented records and temporary
stores. The committed privacy regressions make the core comparisons reproducible.
Runtime tests cover capacity, rolling admission, concurrency, malformed Unicode,
reset failures, unknown writes and same-key reconciliation. Thirteen new disclosure
oracle controls reproduce the original false pass and reject it after repair.

An isolated wheel build used a disposable source copy and no dependency downloads.
A `python -I -B` child imported only the extracted wheel. Both packaged TRAIN
hashes matched. Four local fictional-record HTTP journeys (v1/v2 × ES/PT) passed
inquiry, ambiguity, selection, grounded answer, complaint, preparation consent,
confirmation, verified receipt and duplicate reuse. Unrelated/unsupported inputs
created no draft. The first wheel probe exposed the Portuguese selection bug;
its failed evidence was retained before the repaired build passed.

The **114 protected artifacts** and **90 archived frozen files** remain byte
unchanged. Raw model definitions and packaged TRAIN byte parity also pass.
Original final results, protocols, owner-created readiness notes and sealed cases
were preserved. Only byte hashes were read for final preservation; no final case
contents were interpreted or rescored. The previous preservation helper's
single-file-change expectation belongs to the earlier lookup-only increment;
the standalone audit-repair checker records the authorized current changes.
Aggregate results are retained in
[post_audit_repairs_v1.json](../evidence/post_audit_repairs_v1.json). The working-tree
privacy check passed with zero violations and all eight exclusion probes; it did
not inspect dictionary credential values or Git history.

Run the synthetic checks from the repository root:

```powershell
python -B -m unittest discover -s tests -q
python -B scripts/check_private_artifacts.py
```

Restart an existing server to load the changes. To try the guarded preview with
the independently authored fictional fixtures:

```powershell
python -B -m bank_service web --port 8765 --router learned-preview-v2
```

Existing private-cohort launch options continue to work with their original
startup identity and permissions; no dataset or credential download is needed.

## Review decision and remaining delivery

The owner approved the existing Spanish review material and actual final-output
review. Portuguese is accepted by the owner's explicit assumption without fluent
human validation. This is recorded in
[post_audit_review_decisions_v1.json](../evidence/post_audit_review_decisions_v1.json),
separately from historical approval records and frozen scores.

The [original comparison](final_workflow_results.md) remains completed and failed
qualification. These repairs are engineering regressions, not new held-out gains.
An untouched evaluation requires a new protocol/workload. Deployed judge access,
English slides/video, remaining automation/missed-escalation metric definitions,
repository publication and verified submission delivery remain separate work.
No deployment, publication or paid provider calls occurred in this increment.
