# Delivery preparation — October 4, 2026

This increment prepares a fictional hosted runtime, a portable release package,
an editable English five-slide draft and an English recording script. It does
not deploy, publish, record a video or submit. The development repository remains
private. Portuguese is owner-accepted by assumption without fluent review.

## Reviewable deliverables

- [Portable export and Render settings](deployment.md): literal runtime allowlist,
  canonical HTTPS authority, Secure session cookie, stateless health check and
  explicit rejection of private cohort/customer/permission overrides.
- [Five-slide PowerPoint](../submission/transaction-support-draft-v4.pptx): English
  explanation and independently authored fictional UI screenshot; three editable
  native tables. All five slides were rendered and inspected. Package integrity,
  layout, font policy and first-party reimport passed. Native PowerPoint execution
  has not been verified.
- [Slide copy and source index](submission_slide_copy.md).
- [Video script](submission_video_script.md): target 165 seconds, with Spanish
  inquiry and confirmed intake, Portuguese useful handoff, generic access denial,
  unsupported service and honest evaluation results. The actual recording, its
  duration and viewer access have not been verified.

The tested release snapshot is in the ignored directory
`.local/deployment-package-v2`, containing 29 allowlisted files and one SHA256
manifest. It contains required code/assets and the two fixed authored TRAIN
resources; no organizer records, private cohort, final cases, credentials, PDFs,
experiment/evaluation modules, caches or Git history. The manifest describes
exact working-tree bytes; its source commit is ancestry metadata, not proof that
all exported bytes were already committed. The export refuses nonempty targets.

## Verification and findings

`python -B -m unittest discover -s tests -q` passed **752 tests in 32.417 seconds**,
including all 28 new hosted/package checks and real filesystem-link checks in
the permitted verification run. The earlier restricted package-only runs skipped
four filesystem-link checks; those skips do not apply to this final full run.

An offline wheel built from a copy of the clean export was imported outside the
checkout. Four fictional HTTP workflows covered guarded learned v1/v2 × ES/PT.
Two further workflows used an actual hosted CLI process with the keyword default:
ambiguous search → explicit choice → grounded facts → preparation consent → draft
without a case → explicit save → verified receipt → duplicate reuse → consented
human handoff. Exact Host/Origin denial, Secure cookie attributes and stateless
health were checked. The HTTP client manually sent Secure cookies to simulate
trusted TLS termination; this does not verify real HTTPS or browser cookie behavior.
Two initial rehearsal runs failed on incorrect field names in the temporary
verification script; both diagnostics remain private, and product code was unchanged.

Independent review reproduced a Docker context inclusion bug: directory exceptions
re-admitted unlisted descendants. The corrected rules re-exclude descendants
before allowing exact runtime files. A new behavioral regression produces eight
failures under the old rules and passes under the repaired rules. The Docker
client's own legacy context archive was captured through a fake local named-pipe
daemon using synthetic files. The repaired archive held exactly **28 expected
files**, with **zero missing/unexpected files and 0/12 exclusion sentinels admitted**.
This proves that client/filter check; it is not a Docker build, BuildKit run or
container-execution result. Docker's actual Linux engine was unavailable.
The native archive checks are preserved in the independent reviewer's tool
transcript; no retained archive/helper artifact is available for hashing. The
behavioral regression is retained in `tests/test_demo_package.py`.

Preservation checks confirmed **114/114 protected artifacts** and **90/90 archived
frozen files** unchanged; raw-model definitions and authored TRAIN resource bytes
are preserved. Final-case semantic contents were not decoded, rescored or tuned
against. Original failed qualification and current guarded serving being unscored
remain explicit in the deck and script.

[Aggregate delivery evidence](../evidence/deployment_readiness_v1.json) records
the package/wheel/deck fingerprints and the scope of these checks. The deck is a
draft: final access statuses must be replaced only after actual verification.

## Next external step

Recommended host: Render Free for this narrow fictional prototype. It supports
managed TLS and private Git integration, but sleeps after 15 idle minutes, takes
about a minute to resume and loses filesystem receipts on spin-down/restart.
Use no payment method; included-resource exhaustion can disable the free service
instead of incurring overage charges. Account usage and current terms must be
checked when setting it up. [Render Free](https://render.com/docs/free),
[Render FAQ](https://render.com/docs/faq).

The [deployment guide](deployment.md) proposes a separate private release repository
containing only the reviewed export, so the provider does not receive the research
checkout. Owner authorization is required for that upload/Git connection and
deployment. Account creation terms must be handled by the owner. The next work is
the real image build, canonical HTTPS configuration and bilingual judge-access
checks; then record the video and update actual links. Public repository visibility
and final submission remain separate owner decisions.
