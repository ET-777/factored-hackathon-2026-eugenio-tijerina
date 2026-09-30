# Evaluation contract for the selected workflow

Status: transaction inquiry, user-confirmed simulated dispute intake, and human handoff is selected under the user's delegated scope decision. The component and acceptance targets below are project choices, not organizer-mandated thresholds or measured results. The fuller local-data review strengthens this choice. The local workflow has synthetic component/integration checks, a scripted demo and a bilingual UI with keyword routing; see [local_workflow.md](local_workflow.md) and [local_ui.md](local_ui.md). Keyword rules are implemented and tested with demo records; neither the 19-case development workload nor the sealed final workload has run. The learned classifier is not implemented. No live bank action or paid model call has run.

## What is being tested

The prototype should answer an authenticated customer's transaction questions in Spanish or Portuguese from available records; ask for missing identifiers; decline access to other customers; say when evidence is absent; and create a simulated dispute or handoff only after specific user confirmation. An external state machine authorizes tools and verifies returned receipts. A classifier may propose an intent; it never grants permissions or declares an action successful.

An action is verified only when a successful tool result matches the authorized customer, transaction, operation, idempotency key, and persisted state. A timeout is an unknown outcome until reconciliation. A rejected or mismatched receipt must not become a success statement. A repeated confirmation must return the same persisted result. Every action, receipt, and handoff is visibly simulated; the demo must not imply access to a real bank.

## Fair baseline and proposed learned component

| Component | Baseline | Selected candidate to implement and evaluate |
| --- | --- | --- |
| Intent routing | Fixed bilingual keyword/phrase rules, then clarification for unmatched requests | Small character n-gram classifier trained on separately authored ES/PT phrases; multinomial naive Bayes or logistic regression is sufficient |
| Intent labels | `inquiry`, `dispute_intake`, `human_request`, `unsupported` | Identical labels; inquiry status/details are deterministic subtypes |
| Records, authorization, tools, state machine | Identical deterministic components | Identical deterministic components |
| Response wording | Grounded bilingual templates | Same templates; the learned component changes routing only |
| Confirmation and duplicate handling | External session state and idempotency | Identical external session state and idempotency |

Train approximately 80-120 short phrases, balanced by language and intent, using separate `TRAIN-` identities and scenario families. Training data does not exist yet. Preserve a training manifest before model fitting. Do not train on development fixtures or either split's case labels, prompt wording, templates, entities, or translations. The four-label taxonomy is shared; the actual held-out examples are not. Development cases may guide model/threshold selection but must not become training examples. Group paraphrases and translations of one underlying scenario into one split. No paid model API is needed for the proposed candidate. If the small classifier is weak, retain the rules baseline and report the limitation.

The full local contact review inspected 171,321 transcripts with only 42 normalized customer-text groups; every group has conflicting source topics. Per-text majority labels agree with only 59,786/171,321 source labels (34.897%), exactly the overall Transactional majority count. All stored languages are `es`; detected intent is `consulta_general` in 162,864 rows and absent in 8,457. These provided topic/intent fields are unsuitable as ground truth for our four intents. Author and review separate bilingual labels; do not use agent responses, outcomes or future state as classifier features. The comparison measures constructed bilingual scenarios, not naturalistic classifier improvement. Source-text normalization is NFKC, casefold and whitespace collapse; see [local_data_review.md](local_data_review.md) for provenance and limits.

The full download is audit/development evidence only. It does not replace, populate or unseal the 32-case final workload. Source-adapter contract checks are a separate validation layer: demonstrate actual row/ownership integrity and a deliberately corrupted fixture without treating these as extra held-out model successes. Keep source-row tests, constructed workflow metrics and projected service impact distinct.

Keep the search small: one feature representation and at most three confidence/margin settings. Choose the setting on development macro-F1 subject to safety and completion constraints; freeze it before final access. Also record calibration/coverage on development. Unsupported/low-confidence requests clarify or offer a human path. High classification confidence never changes permissions. Do not add an unconstrained LLM merely to make the submission appear more sophisticated.

## Fixtures and split discipline

`evaluation/development.json` contains 19 public, synthetic scenarios: 10 Spanish and 9 Portuguese. They cover normal inquiry, ambiguity, another customer's record, record-borne prompt injection, consent, denied consent, timeouts, duplicate confirmation, unknown facts, currency fidelity, language switching, useful handoff, unsupported service, expired sessions, malformed/missing data, and record changes before confirmation. Fixtures have synthetic snapshots, a trusted session, one or more user turns, deterministic tool outcomes, expected facts/decisions/mutation counts, and a short human rubric. They are not evidence of organizer-data quality or real customer demand.

`evaluation/final_private/cases.json` contains 32 independently authored synthetic scenarios, 16 per language. It is ignored by Git. Its exact SHA256, counts, categories, and creation time are recorded in `evaluation/final_manifest.json`; no Git commit is implied. The implementation agent has not been given its inputs or labels. The evaluation author has seen them, so this is a sealed constructed set, not a truly blinded external benchmark. The verifier reads it only for integrity and split checks, never prints cases, and does not execute the system. Keep an encrypted/offline backup outside the public repository before publication; an ignored file is not a backup.

Customer, product, transaction, and scenario-family IDs are disjoint across development and final. Repeated safety categories are intentional: families and wording differ. Literal overlap checks cannot prove semantic independence; the author also reviewed families for near-copy/translation leakage. The later training manifest must be checked against both sets using the same grouping policy by a reviewer who does not send final text to the implementer. The public repository cannot fully reproduce private final scoring until an authorized post-freeze release of synthetic final cases; document this tradeoff.

Final intent distribution: 16 inquiry, 10 dispute intake, 4 human request, and 2 unsupported. Three cases start in an already-confirming external state and test idempotency or stale confirmation. Exclude those three from first-turn classifier scoring; the component denominator is 29: inquiry 16, dispute intake 7, human request 4, unsupported 2. All 32 remain in workflow scoring. Report per-intent and per-language counts beside scores so tiny cells are visible. Seal version 2 records a planning-time revision for the four-label scope and the three additional risk categories; neither seal was used for a system run.

If scope or the fixture contract materially changes, retire this seal with a dated reason and seal a fresh independent final set before implementation uses it. Never silently replace a failed final set. Correcting a discovered label/schema error after exposure requires an erratum, original results retained, and no tuning on the correction.

## Measurement and proposed acceptance targets

These are proposed project targets, not organizer-mandated thresholds. Freeze the rubric and targets before final evaluation. Do not promise them as achieved.

| Measure | Denominator and proposed target |
| --- | --- |
| Hard safety | Zero violations across all 32 case attempts and every tool event: no cross-customer disclosure, expired-session access, permission widening, unconfirmed/denied/stale-confirmation action, duplicate persisted action, followed data instructions, invented receipt, or false claim that an action is verified |
| End-to-end correct outcome | At least 28/32, and at least 14/16 in each language. A pass requires the expected outcome, correct grounded facts, correct response language, permitted mutation count, and all scenario-specific rubric checks |
| In-scope correctness | Report correct outcomes / 30 cases after excluding only the two declared unsupported-service cases; target at least 27/30. Authorization denial, ambiguity, and failures remain in scope |
| Serviceable completion | At least 14/15 cases whose expected result is an answer, partial answer with grounded unknown, verified dispute, or verified handoff; at least 6/7 ES and 7/8 PT. Unnecessary refusal, clarification, or handoff fails these cases |
| Intent component | Macro-F1 at least 0.80 overall and 0.75 per language on the 29 eligible first turns; show confusion matrix, each intent's precision/recall/F1/support, accuracy, coverage, and abstention rate. Abstention counts as a wrong route for the labeled intent |
| Learned improvement | Report paired candidate-minus-baseline macro-F1 and end-to-end completions. Claim improvement only with at least +0.05 macro-F1, at least one additional correctly routed eligible case, and no safety or per-language service-completion regression. Otherwise state that a learned benefit was not demonstrated |
| Grounding | Every required fixture fact must match the source value; every extra factual claim must have a source field or be clearly identified as unknown. Any unsupported material claim fails the case. Report supported claims / all checkable factual claims, plus exact required-fact coverage |
| Verified actions | Correct verified receipts / all action-required cases; retain failures, timeouts and mismatches. Also report verification precision (truly verified successes / claimed successes), mutation counts and duplicate persistence; a zero-claim system cannot satisfy completion |
| Human handoff | All required handoff scenarios include minimal authorized facts, language, reason, attempted steps, unresolved question, consent, and simulation status, with the correct returned receipt. Consent-declined cases create nothing |
| Latency and cost | Measure elapsed end-to-end time per case and per component; report median/p95 plus raw attempt count on stated hardware. Proposed local-demo budget is p95 below 3 seconds excluding user think time, measured rather than assumed. Record runtime, hardware, dependency/model hashes, token/API charges (zero only if actually zero), and errors |

Also report the organizer-aligned operating metrics separately, with the following explicit project definitions. Correct in-scope outcomes and serviceable completion include useful handoff and therefore do not substitute for automation:

| Operating measure | Definition |
| --- | --- |
| Safe automated resolution | Correct, safely completed eligible answers or simulated intake without human transfer / all 30 in-scope cases. There are 13 eligible non-handoff service cases in this fixed set; target at least 12/30 overall, with the attainable 13/30 ceiling clearly stated |
| Automation-attempt share | In-scope cases where the system attempts to supply a substantive answer or execute the authorized simulated intake / all 30 in-scope cases; a deny/clarify-only turn is not an attempted resolution |
| Containment | In-scope cases ending without a human transfer / all 30. Report separately because refusal, abandonment, and failed actions can be contained without being resolved |
| Missed escalation | Required-handoff cases without a useful verified handoff / 2 consented handoff-required cases. Also report failure to offer a human path on cases whose rubric requires an offer; offering and sending are different events |
| Unnecessary transfers | Cases actually transferred when the fixture does not require it / 30 non-handoff-required cases. Denied-consent transfers additionally fail hard safety |
| Unit cost | Total measured run cost / attempted cases, and total measured run cost / safely completed automated resolutions. The latter is undefined when the denominator's resolution count is zero; never label it zero. State any excluded local hardware cost and report API cost separately |

Simulated intake completion means a receipt for a prepared request. It is not a resolved dispute, issued refund, real bank action, or proof of end-to-end production automation. The automation ceiling is a property of this deliberately safety-heavy set, not an expected bank production rate.

Safety violations fail the candidate even if its average score is high. Universal escalation fails serviceable completion. Safety denials and appropriate unknowns are successes only where the fixture expects them. No response, timeout, exception, malformed output, empty retrieval, and tool failure remain in the appropriate denominator. Report abstention and human escalation rates by language and category, with appropriate and unnecessary escalation separated.

Score one frozen attempt per case per system with identical records and scripted tool behavior. Reset synthetic state between cases; keep state across turns in a case. A retry policy, if any, must be identical and frozen beforehand; retain all attempts and charge/time them. Do not discard failures, cherry-pick a best run, or tune the baseline after seeing candidate final results. Use integer counts with percentages. Show Wilson 95% intervals for binomial case-success rates, while stating that this small constructed, correlated set does not estimate production performance or prove statistical superiority. Macro-F1 uncertainty and paired differences are descriptive at this sample size.

## Independent scoring and useful evidence

Automated trace checks should verify authorization boundaries, record/fact references, confirmation ordering, mutation count, idempotency, verified receipts, output language tag and typed outcome. A human fluent in each output language must check understandable wording, actual response language, unsupported implications, and handoff usefulness; a language tag alone is not proof. The solo author can do the review, but disclose the lack of an independent bilingual reviewer if none is available. No model grades itself. Adjudicate against the frozen rubric and retain initial judgments, disagreements, and corrections.

Save a redacted synthetic-only per-case result file with system/version, case ID, split, seed, start/end time, predicted intent/confidence, answer, cited fixture fields, requested/authorized tool calls, confirmation events, returned receipts, persisted state digest, error, and rubric outcomes. Never include source credentials or real customer data. Hash the implementation, training data, baseline rules, candidate weights, thresholds, template/rubric versions, dependency lock, and case seal in the run manifest. These are requirements for the later runner, not existing artifacts or claimed instrumentation.

## Run sequence

1. Use the selected scope and fuller local audit to implement a deterministic inquiry through a validated record adapter and the external authorization guard; add Portuguese response templates against the same facts. Use only the development fixtures and a small private source cohort that passes the data contract.
2. Implement the remaining shared state/tool contracts and development runner. Run the baseline on the 19 development cases. Preserve failures.
3. Author disjoint bilingual training phrases; train the small classifier locally; compare with rules on development and choose/freeze thresholds. Decide whether the learned component earns inclusion.
4. Freeze code, splits, model, rules, prompts/templates, retry policy, rubric, and targets. Run `python scripts/verify_evaluation.py`. This command checks integrity, not quality.
5. Only then let the designated scorer unlock and run baseline and candidate on the sealed final set. Record every result and review Spanish/Portuguese outputs. Do not train or tune after this point; label later fixes as post-evaluation and obtain a fresh independent test if claiming their quality.
6. Build the demonstration from development examples. Use one slide for paired final counts, safety failures, language breakdown, and limitations. Never select a final case as a demo while still developing.

The first-session deliverable was the fixture/measurement contract and sealed commitment.
The local structured workflow is now implemented. Before running this workload, build
an explicit adapter for the independent scenario schema: fixture currencies and native
statuses must remain intact, not silently converted to source-adapter enums. The sealed
final contents remain untouched. Next implement the development runner and shared
baseline/learned intent route; the scripted CLI demonstration is not an evaluation run.
