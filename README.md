# Factored banking service prototype

Local foundation for a solo Factored AI & Data Hackathon 2026 submission.
Private development repository: [ET-777/factored-hackathon-2026-claro](https://github.com/ET-777/factored-hackathon-2026-claro).
Keep it private during development; public visibility requires new explicit owner authorization.
The application currently runs locally; a hosted prototype is still pending.

**Status: local bilingual web UI, keyword baseline and experimental learned router, with grounded inquiry,
clarification, confirmed simulated intake/handoff and verified SQLite receipts.**
The keyword UI retains an unfinished search across amount/currency replies and
summarizes distinct handoff steps without inventing unresolved questions.
Supported transaction currencies are **MXN, COP, ARS and USD**. Searches preserve
native amounts and return no match when the available records lack that currency;
the default fictional demo records are USD-only. An optional local private-cohort
mode serves an existing validated source snapshot with a fixed startup test identity.
The offline character n-gram classifier has an experimental local preview. Its authored
96-message training and 32-message development drafts have owner-approved Spanish
wording/labels; Portuguese human review remains pending. The first frozen,
source-backed development comparison is complete: Spanish correct routes improved
from 6/16 to 15/16 and mechanical workflow completion from 8/16 to 12/16.
See [development results](docs/development_results.md) for failures and limits.
Subsequent [shared workflow fixes](docs/post_development_fixes.md) add consented
human review for ineligible disputes, requested channel-limit explanations and
explicit previous-case continuation handling. Complete plain read/search requests
also bypass business classification and request missing details.
Chat prepares a human handoff only from explicit positive human-request wording,
while model-only human predictions clarify without creating a draft or new offer.
These fixes have regression checks; the first comparison scores still describe the earlier frozen code.
Human output review, broader scenario evaluation, deployment and final evaluation
remain pending. These are authored development results, not final performance.

Organizer guidance reviewed October 1 requires English submission deliverables and
Spanish/Portuguese customer interactions. In an October 2 owner-provided Slack screenshot,
Diego permits authored ES/PT evaluation messages using supplied transaction records
and separately labeled simulated safety/tool-failure scenarios: "Yes just make sure
to justify it". Record their purpose, provenance and limits; this does not approve
redistributing source data or every pre-existing fictional-record workload.
Draft families and labels are documented. Spanish wording/labels were approved on
October 3; Portuguese human review remains pending. The first development protocol
was frozen before scoring; a separate final protocol remains pending.
Keep the existing final cases sealed. See
[requirements](docs/requirements.md) and the [evaluation eligibility gate](docs/evaluation.md).

The [bounded source-intent review](docs/source_intent_inventory.md) is complete:
1,098 rows and 42 full-text variants reduce to two balance-request opening families,
both outside the transaction workflow. These transcripts cannot support a four-intent
benchmark. Draft labels remain private; justified authored ES/PT inputs are now
permitted within the exact question's scope, with language review still pending.

Internal submission target: **October 4, 2026, 16:00 America/Monterrey**.
Official deadline, as confirmed by the user: **October 5, 2026, 23:59 GMT-5**
(22:59 America/Monterrey). Approximately 34 work hours total. Video maximum: three minutes.

## Start here

- [Requirements and unresolved questions](docs/requirements.md): organizer requirements, options, and user decisions with PDF page references.
- [Bounded data audit](docs/audit.md): verified findings, sampling limitations, and source claims.
- [Full local-data review and revisions](docs/local_data_review.md): broader evidence from the user-downloaded dataset; the first audit remains historical evidence.
- [Scope recommendation and implementation handoff](docs/scope.md).
- [Evaluation plan and eligibility gate](docs/evaluation.md): baseline, proposed learned component, source-label feasibility, and preserved constructed diagnostics/final seal.
- [Source-intent inventory](docs/source_intent_inventory.md): bounded extraction, provisional label/family counts, first-turn limitations and the scoped organizer answer.
- [Submission plan](docs/submission_plan.md): work budget, deployed prototype, slides, and video.
- [Run and review the local workflow](docs/local_workflow.md): demo commands, module map,
  confirmation rules, checks, and current limitations.
- [Try the local interface](docs/local_ui.md): browser commands, review journey,
  keyword input limits, session/reset behavior and current verification.
- [Private-cohort UI](docs/private_cohort_ui.md): optional loopback mode, trusted startup
  identity/permissions, source snapshot limits and local integration checks.
- [Experimental learned routing](docs/learned_routing.md): local preview,
  fixed algorithm, shared service guards and review status.
- [Spanish review checklist](docs/routing_review_es.md): 64 authored training/development
  messages with October 3 owner wording/label approval, without classifier predictions.
- [Deferred diagnostic scenario adapter](docs/evaluation_adapter.md): preserve the
  independent constructed schema without weakening source validation.

## Local checks

Python 3.11+. The workflow uses the standard library; Windows also needs `tzdata`
for the browser's America/Monterrey calendar (included by `python -m pip install -e .`).
Run from this directory:

```powershell
python -B -m bank_service
python -B -m bank_service web --port 8765
python -B -m bank_service demo --language es
python -B -m bank_service demo --language pt
python -B -m unittest discover -s tests -q
python -B scripts/check_private_artifacts.py
```

Open **http://127.0.0.1:8765** after the `web` command starts. Stop it with Ctrl+C.
Chat dates accept `DD/MM/YYYY`, `DD-MM-YYYY`, strict `YYYY-MM-DD`, and Spanish or
Portuguese month names in either order, such as `3 de mayo del 2026` or
`maio 3, 2026`. Numeric dates are day-first. Without a year, the server uses the
current year in America/Monterrey and shows the interpretation before searching.
Explicit phrases such as `17 de junio de este año` and `17 de junho deste ano`
use that same current year.
Invalid dates and multiple different dates require clarification. This parsing
uses fixed calendar rules, not the learned intent classifier.
The global **DEMO** badge identifies the local simulation; drafts, consent,
permissions and verified readback still apply. The stored action packets keep
their simulation markers.
By default the browser uses fictional records and a server-owned demo session. Cases are
isolated per browser session and temporary; resetting starts a fresh demonstration.
The UI stays on the loopback interface. The optional private-cohort mode loads only
an existing bounded cohort at startup; it never scans the full download. See its
[startup instructions](docs/private_cohort_ui.md). Neither mode loads service evaluation cases.
Adding `--router learned-preview` explicitly fits only `evaluation/routing_train.json`;
it never loads development or final cases. The default remains keyword routing.

The bare module reports status; `demo` exercises the real local workflow using newly
authored fictional records and explicitly scripted confirmation. It creates a temporary
SQLite database by default. An optional `--db .local/demo/cases.sqlite3` keeps simulated
cases between runs; each run is a new conversation. The demo never loads the source
cohort or either evaluation split. Only the explicit `web` command starts a web
server. Only the explicit learned-preview flag invokes the local classifier; no
command calls a cloud provider or real bank tool. Trusted
demo sessions are not production authentication.

`python -B scripts/verify_evaluation.py` is the separate seal-integrity check described
in the evaluation plan; it is not an application evaluation and is not needed for this demo.
See the audit document for its separate optional PDF dependency and bounded rerun command.
For the stronger exact-credential check, use an interpreter with `requirements-audit.txt`
available and run `python scripts/check_private_artifacts.py --dictionary "../Challenge Materials/LATAM_Bank_Complete_Data_Dictionary.pdf"`.
That reads credentials only in memory and reports counts, never their values.

## Repository contents

```text
bank_service/                  guarded workflow, keyword/learned routing, local UI, synthetic demo
docs/                          source-backed requirements, audit, scope and evaluation
evaluation/development.json    public, team-authored development cases
evaluation/routing_*.json      authored routing workload; Spanish approved, Portuguese pending
evaluation/final_manifest.json public final-set commitment; no final case content
evaluation/final_private/      ignored, sealed local cases and labels
evidence/                      aggregate audit evidence only
scripts/                       reproducible audit and verification utilities
tests/                         synthetic record, permission, workflow and storage checks
data/                          ignored source samples and private audit provenance
```

The existing development/final scenario contracts use team-authored fictional banking
fixtures, not extracts or Portuguese translations of organizer customer records.
The October 2 permission addresses authored customer messages using supplied transaction
records and separately labeled simulated scenarios; do not retroactively declare every
old fictional-record case eligible. The [first development protocol](docs/development_protocol.md)
uses supplied records and separately authored families, with disclosed semantic
overlap and Portuguese review limits. A submission-grade final comparison remains
pending. Source dataset text is
documented as Spanish-only; Portuguese evaluation provenance and fluent review remain open.

## Privacy and source handling

Source PDFs remain in `../Challenge Materials/`. The complete dictionary contains
credentials. Never copy the PDF, its access page, credentials, raw records, or full
extracted text into documentation, terminals, issue/PR bodies, Git, or external models.
Audit access reads credentials into memory from the local source only and uses them
only for read-only access to the documented data source. Do not enable SDK debug logs.

`.gitignore` excludes credentials/local configuration, PDFs, raw data, runtime state,
model binaries, scratch files and final evaluation contents. It is a safeguard, not a
secret scanner; never use `git add -f` on those paths. Review the eligible file list
and run the secret check before each commit or push.

The final evaluation set is under an ignored directory in a OneDrive-backed workspace.
It may be synchronized by the user's existing OneDrive setup; “local/private” here means
excluded from this repository, not a claim of an air gap or disabled cloud backup.
Its contents must stay out of model context and development runs until the documented freeze.
Retain it for the final run; regenerate only through an explicit, documented evaluation revision.

## Prototype boundaries

Repository publication does not deploy the application, buy services, call paid
models, move money, or submit material to organizers. Actions are simulated intake
and handoff only;
there is no real chargeback, reimbursement, fraud determination, or lending decision.
The user delegated the workflow decision; transaction inquiry with confirmed simulated
intake and human handoff is selected in `docs/scope.md`. Experimental local training
and learned inference exist. The first component and mechanical workflow development
comparison is complete; human language/output review, final evaluation, deployment
and submission remain future work.
