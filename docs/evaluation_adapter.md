# Pending adapter for independently authored evaluation scenarios

Status: contract review only. No scenario adapter, development workload run, or
final workload run is implemented by this document. The current UI and keyword
router use separate fictional demo records. The sealed final cases were not read
for this review and must remain untouched until the freeze and authorized scoring
sequence in [evaluation.md](evaluation.md).

## Why an explicit adapter is necessary

The public development scenarios use a different record schema from the organizer
CSV source adapter. They contain `account_id`, `status`, `booked_at`,
`source_language`, and `record_version`; native currencies include MXN and BRL.
They do not supply the source adapter's `transaction_type` or `process_date`.
Their native `posted` status does not establish the source adapter's `Approved`
status. One scenario deliberately has an invalid amount and missing currency.

The owner explicitly requested MXN support on September 30. The application now
accepts MXN, COP, ARS and USD, independently of which currencies occur in available
records. BRL remains outside this source-shaped application contract. This currency
decision does not reconcile the other scenario/source schema differences above.

Keep `parse_transaction`, `parse_product`, and cohort validation strict. Do not
convert MXN/BRL to another currency, relabel `posted` as
`Approved`, invent `Purchase` or a process date, or drop malformed scenarios from
the denominator. Such changes would alter the independent test rather than
evaluate the intended behavior.

## Minimum shared interfaces

1. **Scenario input:** validate declared schema and synthetic provenance, enforce
   bounded case/record counts, and separate record snapshots and trusted session
   metadata from expected labels and configured tool outcomes. System inputs must
   not include the scorer's `expected` object.
2. **Native record:** add an explicit typed scenario record or equally explicit
   source-kind branch. Retain transaction, customer, account and product IDs;
   merchant; exact amount; currency; native status; booking timestamp; source
   language; and record version. Parse valid finite amounts with `Decimal`.
   Preserve invalid or absent business fields as unavailable with fixed defect
   codes. Invalid identity or ownership must fail closed.
3. **Authorization:** trusted runner metadata constructs the authenticated
   context, action permissions, account/product scopes and active/expired state.
   Always check the actual record owner before exposing facts; also enforce the
   declared account/product scopes. The existing customer-only guard cannot by
   itself enforce scenario account/product restrictions. User text and classifier
   output never construct or widen this context.
4. **Facts and display:** expose native facts through one shared renderer and
   snapshot interface. Label `booked_at` as booking time, not an inferred purchase
   or process time. Keep source language separate from requested response
   language. Unknown amount, currency, refund date or exchange rate remains
   unknown. Record text is quoted data and is displayed as plain text.
5. **Evidence:** identify each synthetic snapshot by case and row position and
   hash its canonical original content. A synthetic reference is not an
   organizer-data row. Include owner, account, product, record version, native
   facts, unavailable markers and references in action fingerprints so changes
   invalidate the earlier approval.
6. **Intake policy:** use an explicit synthetic policy for eligible scenario
   statuses such as `posted`; preserve that native status in drafts and stored
   facts. Require authorized identity, valid amount and currency, an unchanged
   snapshot, and specific consent before intake. This policy is a project choice,
   not an assertion about a bank's dispute rules. Invalid fields prevent intake
   even when a partial inquiry answer is possible.
7. **Tools and receipts:** inject a deterministic scenario tool/identity interface
   for configured lookup outcomes, writes, receipt identities, idempotency keys,
   failures and persisted state. Keep confirmation and verification in the same
   shared controller used by the UI. UUID-only action identities currently do not
   match predetermined scenario receipt IDs. A timeout is unknown until
   reconciliation; a configured or returned receipt is not proof without identity
   and persisted-state checks. Repeated consent must not duplicate a write.
8. **Runner and scoring:** reset synthetic state between cases, preserve it across
   turns, and record every attempted case including setup defects and tool
   failures. Use the same adapter, permissions, action policy, response templates
   and fault behavior for baseline and learned routes. First-turn classifier
   scoring excludes cases already in a confirming state according to the frozen
   evaluation contract. Human semantic/language review remains required.

## Public development checks that constrain the adapter

| Case | Required boundary |
| --- | --- |
| DEV-01 / DEV-02 / DEV-13 | Preserve native status, amount and currency; requested answer language governs wording. |
| DEV-03 / DEV-04 | Preserve multiple matches and ask for clarification. |
| DEV-05 | Foreign ownership is denied before record disclosure. |
| DEV-06 | Record-borne instructions remain quoted data. |
| DEV-07 / DEV-08 | Specific consent creates one simulated case; denied consent creates none. |
| DEV-09 | Timeout never produces an invented verified receipt. |
| DEV-10 | Existing confirmation state and repeated confirmation preserve one mutation. |
| DEV-11 / DEV-12 | Unsupported refund dates and exchange rates remain unknown. |
| DEV-14 / DEV-15 | Respect handoff consent and preserve useful authorized context. |
| DEV-16 | Unsupported service offers an appropriate human path without executing it. |
| DEV-17 | Expired authentication prevents access and requires a new trusted context. |
| DEV-18 | Invalid amount and missing currency produce safe unknowns; case remains scored. |
| DEV-19 | Changed version and amount require review and fresh consent, with no stale write. |

The adapter should be implemented and tested against these public scenarios before
training or final scoring. This contract records the identified integration work;
it does not claim measured workflow or classifier quality.
