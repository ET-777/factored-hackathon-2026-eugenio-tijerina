# Submission requirements and open questions

PDFs reviewed 2026-09-26; subsequent user clarifications are identified separately below. Page numbers are 1-based PDF pages, including covers. This is a checklist of requirements, not evidence that the prototype already meets them. User-reported organizer clarifications have not been independently verified with the organizers.

Sources (kept outside this repository in `../Challenge Materials/`):

- **Brief**: `Factored AI & Data Hackathon 2026.pdf`, 6 pages.
- **Kickoff**: `Datathon_2026_Kickoff.pdf`, 24 pages.
- **Summary**: `LATAM_Bank_Dataset_Summary.pdf`, 5 pages, dataset version 1.0.0.
- The complete dictionary is credential-bearing. Never copy its credentials, extracted full text, or source PDF into this repository, logs, or public artifacts. Its schema findings belong in the bounded audit, with safe page references.

## Explicit organizer requirements

| Done | Requirement / evidence to produce | Source |
|---|---|---|
| [ ] | Submit by **October 5, 2026, 23:59 GMT-5** (**22:59 America/Monterrey**). The PDF confirms the date; the user supplied the explicit cutoff clarification. | Kickoff p. 6, visually checked; cutoff: user-confirmed organizer clarification; local timezone conversion checked with Python `zoneinfo` |
| [ ] | Choose one coherent customer-service workflow; use supplied data to justify demand, a baseline, intended outcomes, and operational constraints. | Brief pp. 2-3; Kickoff pp. 10, 13 |
| [ ] | Deliver a working end-to-end prototype with a normal resolution, an ambiguous/unsupported request, and a human-required case. | Brief pp. 2-3; Kickoff pp. 10-11 |
| [ ] | Demonstrate Spanish **and Portuguese**; disclose limitations in source data and language coverage. | Brief p. 3; Kickoff p. 10 |
| [ ] | Preserve conversational context, clarify ambiguity, and ground factual responses in permitted account, transaction, or policy evidence. | Brief p. 3; Kickoff p. 11 |
| [ ] | Enforce identity, customer-record access, action permissions, and policy in the service/tool layer. A customer number or national ID alone is not authentication. A trusted test session is acceptable. | Brief pp. 3, 5 |
| [ ] | Define allowed answers/actions, required confirmation, abstention, and escalation. Report actions only after verifying outcomes. | Brief p. 3; Kickoff pp. 11, 13 |
| [ ] | Produce useful human handoffs: request, verified facts, actions taken, evidence, unresolved questions; avoid a raw-transcript dump. | Brief p. 3; Kickoff p. 11 |
| [ ] | Use repeatable preparation, schema contracts, quality checks, lineage, and a freshness/update policy. Demonstrate static-data updates with labeled fixtures if needed. | Brief pp. 3-4; Kickoff p. 12 |
| [ ] | Evaluate at least one learned component against an appropriate baseline, with valid labels/relevance judgments, leakage prevention, justified representations, thresholds, metrics, and splits. | Brief pp. 3-4; Kickoff p. 12 |
| [ ] | Compare baseline and proposed system on the same held-out workload; report case mix/counts, label quality, model/prompt versions, failures, and relevant repeated-run variability. Validate any model judge against human or deterministic judgments. | Brief p. 5 |
| [ ] | Include incorrect/missing data, expired sessions, unauthorized access, prompt injection, tool failures, and multilingual ambiguity in held-out testing. | Brief pp. 3-4 |
| [ ] | Report safe automated resolution over **all in-scope cases**, automation-attempt share, unsafe counts/denominators, missed/unnecessary escalation, handoff quality, p50/p95 end-to-end latency, and cost per attempt/success. Separate containment from correct resolution. | Brief pp. 4, 6 |
| [ ] | Compare outcomes by language and permitted customer segments; disclose small samples and distinguish offline/simulated/projected outcomes from production results. | Brief p. 6 |
| [ ] | Demonstrate tracing, bounded retries, safe fallback, reproducible setup, and source/policy/execution-based explanations. Explain capacity, monitoring, retention, access controls, risks, and remaining deployment work. Hidden chain-of-thought is not audit evidence. | Brief pp. 2, 4; Kickoff p. 15 |
| [ ] | Use approved data/resources and follow data-use terms. Label real/de-identified/synthetic/team-generated inputs. Keep credentials, private records, and restricted data out of public submissions and external model requests. | Brief p. 5 |
| [ ] | Supply a public GitHub repository named `factored-hackathon-2026-[team-name]`, deployed-tool URL, 4-6 slides, and a mandatory video of **at most 3 minutes** demonstrating the solution and core architecture; the deck names `hackathon.admin@factored.ai` for submission. | Kickoff p. 18, visually checked; video duration: user-confirmed clarification |

No live lending decisions or movement of money is authorized by the challenge (Brief p. 5). If scope later includes credit eligibility, the additional risk/policy separation and approved-or-labeled-synthetic policy requirements on that page apply.

**Learned-component clarification:** Brief p. 3, item 4, requires an evaluated learned component; Kickoff p. 12 repeats that requirement. Brief p. 4, “Architecture freedom,” makes training a new model optional and permits pretrained/retrieval-based approaches with meaningful component evaluation. A pretrained learned encoder or model can satisfy that role if justified and compared against a baseline. Training/fine-tuning is optional; learned-component evaluation is not. Any earlier planning note calling the learned component optional is superseded by this source review.

## Organizer options and recommendations

- Account/payment inquiry, card support, dispute intake, and credit information are examples, not separate tracks. More workflows do not automatically earn more points (Brief pp. 2-3).
- Conventional ML, pretrained models, retrieval, deterministic workflows, agents, or a justified combination are allowed. New-model training, multiple agents, a target tool count, streaming, demand forecasting, and a dashboard are not mandatory (Brief p. 4).
- Sandbox/mock banking tools are acceptable if their contracts and limits are documented (Brief p. 5). Batch processing may be sufficient; incremental file delivery does not itself require streaming (Brief p. 4).
- Solo participation is explicitly allowed; teaming and mentor/community contact are recommendations (Kickoff p. 17). Suggested discipline tasks are not a mandatory architecture (Kickoff p. 14).
- Tools/languages and cloud platforms shown are options (Kickoff p. 19). No specific stack or paid service is required by these documents.
- The brief expects evidence of readiness and an honest remaining-work account, not operation of a live bank (Brief p. 2). Read the kickoff's broader “production-ready prototype” wording in that explicit context (Kickoff p. 10).

## User decisions and current planning boundaries

- Solo build with approximately **34 reserved work hours**.
- Internal submission target: **2026-10-04 16:00, America/Monterrey**, unchanged. Official cutoff is now **2026-10-05 23:59 GMT-5** (**22:59 America/Monterrey**), based on the user's explicit clarification, not a newly verified organizer source.
- The initial session covered source review, minimal local scaffold, a bounded audit, scope recommendation, and evaluation design. The user subsequently authorized a fuller **offline review of their downloaded `../Data/` directory** and delegated selection of the strongest feasible narrow workflow to Codex. The completed [local review](local_data_review.md) records row-level inspection of six relevant tables and metadata/header coverage of all 13; it does not certify download completeness against the organizer source.
- **Selected under the user's delegation:** transaction inquiry -> confirmed simulated dispute intake -> verified receipt or useful human handoff, in Spanish and Portuguese. The [scope decision](scope.md) follows the local review; no further scope-approval question is needed. Compare a local character n-gram intent classifier trained on independently authored, reviewed bilingual examples with keyword rules; do not supervise it with contradictory source topic labels. This decision preserves the 34-hour budget and one workflow, with no promised model gain or winning outcome.
- Preserve existing work and keep source PDFs, credentials, and raw records excluded from Git. The initial audit avoided a full download; the follow-up used files the user already downloaded, with no additional data access. The user subsequently authorized GitHub repository publication; deployment and paid model calls remain outside the current work.
- The user explicitly confirmed that bucket credentials must not be shared. No separate data license has been discovered; this does not grant unrestricted redistribution of source records or permission to send them to external APIs.
- The user knows of no extra rules or numerical rubric weights beyond the supplied PDFs. No video file format, presentation template, or additional submission procedure has been specified. These are limits of currently available information, not proof that no other organizer instructions exist.
- The user suspects “public*” may mean accessible only to participants, but that interpretation is unconfirmed. Continue planning a conventional public code repository with independently authored synthetic fixtures; retain the PDF's public-repository requirement until a definitive clarification replaces it.
- The user authorized GitHub publication on 2026-09-29. The public code repository is [ET-777/factored-hackathon-2026-claro](https://github.com/ET-777/factored-hackathon-2026-claro); the deployed prototype, 4-6 slides and demonstration video remain planned. Repository creation alone does not complete the submission-bundle requirement.

## Documented data claims, not yet verified by this checklist

The Summary describes entirely synthetic banking data, roughly 19 million rows across 13 tables for Mexico, Colombia, and Argentina, dated 2023-06-17 through 2026-06-17. It claims Spanish-only text with regional variations, approximate duplicate/null rates, possible late arrivals/schema evolution, and occasional orphaned references (Summary pp. 1-3, 5). These are organizer descriptions, not audit results. In particular, Portuguese coverage must be assessed separately; translated or newly authored Portuguese cases must be labeled as team-generated and must not be presented as native dataset coverage.

The [completed local review](local_data_review.md) separates these descriptions from observed counts and quality: all 171,321 transcript language tags are `es`, source topic labels conflict across all 42 normalized customer-text groups, and 1,450,689 transactions require chronology quarantine. Current owner/currency joins pass, but current snapshots are not proof of historical ownership. The original bounded audit remains historical evidence; source limitations must carry into the serving contract and submission narrative.

## Clarifications resolved by the user

| Topic | Current planning fact and source status |
|---|---|
| Official deadline | **October 5, 2026, 23:59 GMT-5** (**22:59 America/Monterrey**); explicit user-reported organizer clarification. Internal target remains October 4 at 16:00 America/Monterrey. |
| Video length | **At most 3 minutes**, per user clarification. Plan 165 seconds total to leave a 15-second margin. |
| Workflow selection | Delegated to Codex and now recorded in [scope.md](scope.md): transaction inquiry, confirmed simulated intake, verified receipt/human handoff. One workflow, with local bilingual intent learning evaluated against rules. |
| Additional known rules/weights | The user identifies only the supplied PDFs and reports no extra rules or numerical weights; none should be invented. |
| Credential sharing | Explicitly prohibited by the user, consistent with Brief p. 5. |

## Remaining unresolved questions / implementation decisions

| Question | Why it matters / current handling |
|---|---|
| What is the final submission procedure, acknowledgment/confirmation process, and any later template? | The deck specifies an email address, but no further procedure or template has been confirmed. Deadline and video duration are now resolved through the user clarification. |
| Where are the authoritative data-use/license terms and permitted external-resource rules? What data, derived fixtures, aggregates, or model artifacts may be redistributed or sent to external providers? | The brief requires compliance but these PDFs do not supply a complete license. Keep records private and publish only approved or independently authored synthetic fixtures pending clarification. |
| What does the asterisk on “public*” repository mean? Are there repository visibility exceptions? | The rendered Kickoff p. 18 has no explanatory footnote. The user's participants-only interpretation remains a hypothesis. Plan conventional public code plus synthetic fixtures until clarified. |
| What file/link format, judging access window, authentication constraints, or slide template apply? | The user confirmed a video maximum of 3 minutes; no formats/templates were specified. Retain 4-6 slides from Kickoff p. 18 and test links without an owner-authenticated browser. |
| How will verified source limitations be enforced when serving records? | The [local review](local_data_review.md) establishes checked coverage, consistent current owner/currency references, chronology conflicts, and unusable source topic supervision. Implement a validated adapter and small private cohort, quarantine conflicting dates, preserve snapshot/timezone uncertainty, and keep public fixtures independently authored. Remaining untested semantics and historical ownership must not be inferred from the passing joins. |
| Who can review Portuguese wording and labels fluently? | Review development templates with the owner if fluent; otherwise seek an independent fluent reviewer when available. Record reviewer role, reviewed material, and corrections. If no fluent reviewer is available, keep the Portuguese demo, label linguistic review incomplete, and do not claim native or human-validated language quality. No reviewer is currently promised. |
| Does the selected learned component provide a useful improvement? | This remains an evaluation question, not a scope-approval question. Use reviewed independent training labels, development-only selection, and the frozen baseline/final-set protocol. Keep the sealed final cases untouched during implementation; report no gain or regression honestly. |

Codex has not contacted organizers in this work. User-provided clarifications are recorded with their provenance. No completion boxes above imply organizer acceptance or production qualification.
