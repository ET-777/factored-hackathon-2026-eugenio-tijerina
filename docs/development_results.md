# First measured development comparison, October 3

The learned router improved this small authored development diagnostic. It has
not passed final evaluation or human output review. The default remains the
keyword router; the candidate stays available through `--router learned-preview`.

The [protocol](development_protocol.md) and implementation were frozen in commit
`79d68ce22f33749d2f67ef93e8ae6ce0a1fed067` before development prediction. The
unchanged candidate was fitted on 96 TRAIN messages only. Both systems received
the same 32 DEVELOPMENT requests and authorized, preselected source contexts.
Exactly 64 component and 64 fresh-session workflow attempts ran, with no retries,
parameter changes, dropped cases or changed inputs/code. All bindings were
available. Results and input/code/runtime hashes are in the identical saved
[aggregate artifact](../evidence/routing_development_v1.json). Private sanitized
per-case outcomes remain ignored under `.local/evaluation_runs/development-v1-20261003/`.

## Primary Spanish results

Owner-approved wording and labels; **16 messages across only eight families**.
Neither outputs nor handoff usefulness have completed human review.

| Measure | Keyword baseline | Learned candidate |
| --- | ---: | ---: |
| Correct component attempts | 6/16 (37.5%) | 15/16 (93.75%) |
| Macro-F1, fixed four classes | 0.3485 | 0.9365 |
| Abstentions | 7/16 | 0/16 |
| Entire families correctly routed | 2/8 | 7/8 |
| Mechanical workflow completion | 8/16 (50%) | 12/16 (75%) |

The candidate added nine correct component attempts, with no baseline-only
correct attempt, and four mechanical completions. The fixed protocol counts
unmatched fallback as ABSTAIN even when its raw label is unsupported. Thus
component recognition and useful business behavior are different metrics:
baseline fallback can still prepare a handoff, while dropping selected transaction
context can fail the human-request oracle. Routing improvement alone is not
automated resolution or proof of production benefit.

## Provisional Portuguese results

Fluent-human input/label/output review is **pending**. These figures are exploratory.

| Measure | Keyword baseline | Learned candidate |
| --- | ---: | ---: |
| Correct component attempts | 5/16 | 16/16 |
| Macro-F1 | 0.3571 | 1.0000 |
| Abstentions | 10/16 | 0/16 |
| Entire families correctly routed | 1/8 | 8/8 |
| Mechanical workflow completion | 7/16 | 13/16 |

Perfect routing on these authored Portuguese messages does not establish natural
language quality or generalization. Translations and paraphrases are correlated;
both language populations are engineered and balanced, and author/reviewer
overlap is disclosed. There are no independence-based significance claims.

Combined 32-message figures mix review quality and are descriptive only:
component 11/32 versus 31/32, macro-F1 0.3590 versus 0.9686, mechanical completion
15/32 versus 25/32. Candidate-minus-baseline gains are +9/+11 component attempts
and +4/+6 mechanical completions for ES/PT respectively.

## Failures and measured boundaries

All **seven candidate incomplete workflows** remain in the denominator:

1. Four cash-not-dispensed requests routed correctly to dispute intake, but the
   related source Withdrawal is ineligible for purchase intake. The controller
   offers preparation then blocks it with `unsupported_intake_state`; it saves
   no case and lacks a useful surfaced human fallback.
2. Two channel questions receive a grounded record summary without explicitly
   saying that channel is unavailable. Required source facts match, but the
   requested missing field is not answered, so completion fails.
3. One Spanish request to continue an existing case is misrouted to dispute
   intake and reaches an eligibility block. This remains a component and
   workflow failure. Its high uncalibrated score is not reliable certainty.

The candidate reproduced required native facts/source-panel references in all
17 workflows with new scored answers. Both systems created 19 cases across their 32 journeys,
including cases that did not meet the expected service outcome. All 19 observed
packets per system passed exact source-snapshot, original-request, consent,
verified readback and duplicate-confirmation checks. No write before explicit
final confirmation was observed in any of the 32 attempts per system. These
are conditional mechanical checks, not a comprehensive safety or semantic claim;
cross-customer, expiry and tool-fault scenarios were not part of this diagnostic.
Structural language checks passed; fluent wording and useful escalation remain
review gates. Safe refusal does not count as completed service.

There were no component exceptions/malformed proposals, unavailable bindings or
technical execution failures. Domain eligibility refusals are retained failures.
The predeclared candidate-consideration criteria were met, but this does not
close Portuguese review, output review or final evaluation, or change the UI default.

## Timing and reproducibility

Python 3.11.0 on Windows/AMD64, 20 logical CPUs; exact processor/runtime and code
hashes are recorded. Component median/p95 was 0.113/1.486 ms baseline and
0.450/0.831 ms candidate. Scored local workflow median/p95 was 6.337/7.485 ms
baseline and 6.173/8.712 ms candidate, with all 32 timings observed per system.
The p95 uses nearest rank. These single-run in-process measurements exclude
loading, fitting, source-context setup, UI/network transport and human think time;
they are not deployed latency or an SLA. No external inference ran: API calls
and API charges were zero; local electricity/hardware cost was not measured.

The freeze passed **422 synthetic unit/integration regressions**, including local
HTTP checks. The scoped Git-eligible artifact check found zero violations in
97 files and passed eight exclusion probes before results were copied. It did
not read the credential dictionary, compare its exact credentials or scan Git
history. Original final cases, source CSVs and PDFs were not read by this runner.
Saved cohort hashes were checked; original CSV hashes were inherited from its
manifest rather than independently rehashed.

To reproduce later, preserve the frozen version and inputs, then use a new run
name. Repeated development runs do not become independent evaluation evidence.

```powershell
$taskProtocolHash = (Get-FileHash -LiteralPath 'docs/development_protocol.md' -Algorithm SHA256).Hash.ToLowerInvariant()
python -B -m scripts.run_routing_development --cohort-run '.\data\private_cohort\june17-v1' --run-name 'development-v1-reproduction' --protocol-sha256 $taskProtocolHash
```

## Next implementation increment

Fix the two shared workflow gaps first: explain unavailable requested channel
information, and offer a consented, grounded human handoff for ineligible intake
without presenting an intake draft. Preserve the frozen first-run results and
tag subsequent work as post-development changes. Address the case-continuation
failure with explicit clarification or safe existing-case handling rather than
inventing case history or treating model confidence as authorization.

Then review outputs, arrange or disclose missing Portuguese human review, and
separately authorize/freeze fresh source-grounded final families before scoring.
The original final remains sealed and cannot silently become that new workload.
Finish the hosted prototype and English 4-6 slides/maximum-three-minute video
for the owner's October 4, 16:00 Monterrey target. The GitHub repository remains
private until the owner explicitly authorizes its required submission visibility.
