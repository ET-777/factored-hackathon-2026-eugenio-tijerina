# Architecture

The application is a single Python service with a JavaScript interface, a local
intent classifier and SQLite ticket storage. Spanish and Portuguese share the
same workflow and permission checks.

```text
Server-owned session -> request interpretation -> workflow state
                     -> authorized record/action service -> grounded response
```

## Customer journey

1. **Find a transaction.** Collect a date, or an amount with its currency. When
   several records match, require the customer to choose one.
2. **Explain the record.** Display recorded facts and their evidence. Missing
   policy reasons, refund rules and timezone information remain unknown.
3. **Offer review.** An unrecognized-charge request can lead to an offer to
   prepare a ticket. Accepting that offer creates a draft, not a saved case.
4. **Confirm the draft.** The customer reviews the side panel and uses its
   explicit confirmation control. Typing “yes” in chat cannot save the draft.
5. **Verify saving.** Store the case atomically, read it back, and compare it
   with the confirmed packet before returning a success receipt.

A general request for human support first asks what the customer needs help
with, unless the issue is already known. The handoff summary includes the
literal issue, selected record facts, evidence, relevant completed steps,
unresolved questions and earlier verified tickets. It follows the same review
and confirmation process. Saving it does not contact a real support team.

## Controls outside the model

- Identity and permissions come from the server-owned `TrustedSession`.
  Record reading, review-ticket creation and human-handoff creation have
  separate permissions.
- Every record access and action rechecks ownership, permissions and expiry.
  Unknown or foreign references disclose no private transaction facts.
- The classifier proposes intent only. Service rules handle greetings, dates,
  amount/currency continuations, selected-record references and consent.
- A pending draft binds to the reviewed request and transaction. Preparation,
  cancellation and ordinary chat replies do not persist a case.
- Repeated confirmation uses idempotency and returns the same verified receipt.
  A failed or uncertain save cannot produce an unverified success claim.
- Amounts use decimal arithmetic and native currencies. No exchange rate,
  refund decision, fraud determination or bank policy is inferred.

The public server mints opaque fictional sessions. Session state and SQLite
cases are temporary and isolated by session. Hosted requests check the canonical
Host, browser Origin and CSRF token; cookies are Secure, HttpOnly and
SameSite=Strict. Malformed Unicode is rejected. This is a bounded prototype,
not a production identity or banking security system.

## Module map

| Responsibility | Modules |
| --- | --- |
| Browser and hosted HTTP service | `web_app.py`, `hosting.py`, `web/` |
| Conversation state and intent interpretation | `conversation.py`, `routing.py`, `learned_routing.py`, `route_loader.py` |
| Filters, date parsing and record selection | `transactions.py`, `request_dates.py`, `selection.py`, `transaction_references.py` |
| Record validation and optional local cohort loading | `records.py`, `cohort_repository.py` |
| Authorization, action drafts and verified storage | `access.py`, `actions.py`, `case_store.py` |
| Grounded bilingual replies and fictional examples | `responses.py`, `demo_fixtures.py`, `demo.py` |

Hosted mode uses only fictional fixtures and refuses private-cohort identity
overrides. The optional private-cohort path is restricted to local operation;
no organizer records are included in this repository.
