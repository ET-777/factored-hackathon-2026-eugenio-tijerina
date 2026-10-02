# Local UI with a bounded private source cohort

This optional mode connects the existing validated cohort to the same transaction
workflow. It uses an organizer-data snapshot locally; intake and handoff remain
explicitly simulated. This is integration evidence, not a learned-model benchmark
or production banking authentication. The default fictional demo is unchanged.

## Trusted startup

Use an existing completed cohort, such as the owner's `june17-v1` run with 50
transactions. Do not rerun a full-dataset audit or download. Select a customer ID
from that private cohort locally; never paste it into project documentation or Git.
Identity and permissions are fixed before the server binds and cannot be supplied
through chat, cookies or browser fields.

The following placeholder must be replaced locally. This command grants read only:

```powershell
python -B -m bank_service web --port 8766 `
  --cohort-run '.\data\private_cohort\june17-v1' `
  --customer-id 'CUSTOMER_ID_FROM_YOUR_PRIVATE_COHORT'
```

For the complete simulated journey, grant each scope explicitly at startup:

```powershell
python -B -m bank_service web --port 8766 `
  --cohort-run '.\data\private_cohort\june17-v1' `
  --customer-id 'CUSTOMER_ID_FROM_YOUR_PRIVATE_COHORT' `
  --permission transaction:read `
  --permission intake:create_simulated `
  --permission handoff:create_simulated
```

Open **http://127.0.0.1:8766**. The host stays loopback; there is no remote-host option.
No model/provider, evaluation split or full source dataset is loaded. Invalid cohort,
unknown customer or missing read permission refuses startup without a demo fallback.
The fixed error does not echo the path, customer, rows or loader exception.

## Review and boundaries

- Only the configured customer's records appear. Cross-customer and missing IDs
  receive the same generic denial; a chat ID never grants access.
- Amounts, currencies, statuses, dates and relative row references come from the
  validated snapshot. No currency conversion, date repair or invented merchant occurs.
  Source timestamps do not establish a real-time account view or historical ownership.
- Spanish and Portuguese captions identify supplied historical records and simulated
  local actions. The record source does not imply native Portuguese transcript coverage.
- A purchase must meet the existing explicitly synthetic intake rule before a draft
  can be prepared. Confirmed intake is a local ticket, not a refund or dispute resolution.
- Reset and new browsers mint fresh server-owned sessions for the same fixed customer
  and scopes, with separate temporary case stores. They cannot select a different owner.
- Relative dataset filenames, row numbers and hashes support owner inspection. Local
  absolute paths, raw manifests and customer/product dimension fields are not returned.
  HTTP logging remains disabled; do not commit source-mode screenshots or exports.
- The bounded snapshot is loaded once at server startup. Files changing on disk do not
  silently change a running session; restart deliberately to load a new validated run.

Database cleanup occurs on normal server shutdown. Sessions last 20 minutes; drafts
last five minutes. These local test sessions do not replace production authentication.

## Verification

October 2 verification: **319 tests passed**, including eight new CLI tests and
13 new private-mode tests. These cover startup, owner isolation, read-only denials,
fresh/reset session behavior, snapshot preservation, bilingual copy and confirmed
simulated receipts. JavaScript syntax, ES/PT mode captions, exact decimal-string
display and Git whitespace checks passed.

A source-backed loopback HTTP smoke check loaded only the existing **50-transaction**
cohort. It displayed one authorized customer's record, preserved its exact native
facts, exercised Spanish startup and Portuguese inquiry, verified a simulated intake
and human-handoff receipt, denied foreign/missing records identically, and preserved
the fixed identity/source through reset. Eleven fixed integration stages passed.
The harness and aggregate result remain ignored under `.local/private-ui/`; no
source values, identifiers or screenshots are exported to Git.

The working-tree artifact check found zero violations across 72 eligible files and
passed 8/8 exclusion probes. It read no dictionary credentials and did not scan Git
history. The existing source adapter, access/action services, selection, responses,
cohort repository, conversation/store and public evaluation files have no diff.
Final case contents were not read. New browser rendering was not visually reviewed;
independent Portuguese review and learned-component performance remain separate work.

Next establish a justified source-grounded authored ES/PT workload with reviewed
labels and independent request families, then commit the shared baseline/candidate
protocol before fitting. Keep the existing sealed final set untouched.
