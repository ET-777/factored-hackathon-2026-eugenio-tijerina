# Transaction Support Assistant — timed video draft

English narration; Spanish and Portuguese customer interactions. Target runtime:
**165 seconds (2:45)**, leaving 15 seconds below the three-minute maximum. Timings
below are a recording plan, not a measured video duration. No recording or video URL
is created by this document.

Use the default **keyword** mode with independently authored fictional `DEMO-TX`
records. The optional current guarded learned preview is unscored; do not imply
this recording evaluates it or reproduces the original frozen benchmark.

```powershell
python -B -m bank_service web --port 8765
```

Open the local loopback UI. Do not use `--private-cohort`, source records, evaluation
splits, credential-bearing materials or external banking tools. The two owned demo
purchases are **USD 25.50**, dated **2026-06-16**, with independently authored source
references. They are not organizer-customer transactions.

## Recording sequence and narration

### 0:00–0:17 — Slide 1: a narrow service problem

**Show:** title and the 240,056/686,296 synthetic-corpus contact figure. Keep the
denominator and "synthetic corpus" label visible.

**Narration:**

> Transaction Support Assistant answers a charge question, then supports confirmed
> simulated intake or human review. Transactional contacts represent thirty-five
> percent of the supplied synthetic corpus. That supports a narrow workflow, not
> a claim about real-bank demand.

### 0:17–0:37 — Slide 3: learning and authority

**Show:** architecture and source-language limits. Keep the footnote visible.

**Narration:**

> Source transcript openings were balance requests, with conflicting topic labels
> and no Portuguese coverage. We used justified authored messages and a local
> character n-gram classifier against keyword rules. The service checks identity,
> ownership and permissions; the classifier only proposes intent.

### 0:37–1:09 — Spanish: clarify, select, explain

**Show and do:** in a fresh Spanish session, press `Buscar una compra` (sends
`Quiero consultar una compra`). Type **`25,50 USD del 2026-06-16`**. Show both
matches and deliberately choose **`DEMO-TX-001` / Demo Mercado Sol**. Briefly open
the record-evidence panel. Keep the demo disclosure visible.

**Narration:**

> These are fictional demonstration records. In Spanish, I ask about a purchase
> and provide an amount, currency and date. Two records match, so the assistant
> asks me to choose. The answer shows the selected transaction's facts and evidence,
> preserving its native amount and currency.

### 1:09–1:36 — Spanish: intake has two decisions

**Show and do:** type **`No reconozco esta compra`**. Press **`Sí, preparar solicitud`**.
Pause over the exact draft and the footer that says no case has yet been created.
Then press **`Confirmar y guardar`**. Show **`Caso de revisión · guardado y verificado`**
and its generated receipt reference.

**Narration:**

> Now I say I do not recognize this purchase. Accepting the offer prepares a draft;
> it saves nothing. I review the exact facts and request before confirming. The
> assistant reports a ticket only after persistence and verified readback. This
> completes simulated intake, without resolving the charge.

### 1:36–1:59 — Portuguese: useful human review

**Show and do:** after the intake is verified, select Portuguese. Type
**`Quero falar com uma pessoa sobre a compra que não reconheço`**. Show the draft
packet: its request is `a compra que não reconheço`; the selected transaction facts,
evidence, attempted steps and prior verified intake reference remain available.
The unresolved-questions list is empty because no separate question was supplied;
do not invent one. Press **`Confirmar e salvar`** and show
**`Revisão humana · salva e verificada`**.

**Narration:**

> In Portuguese, I ask for a person about this purchase. The handoff preserves the
> issue, verified facts, attempted steps and existing ticket. I confirm its exact
> packet. The receipt verifies a simulated queue entry; nobody is contacted.

### 1:59–2:14 — Safety and unsupported service

**Show and do:** press **`Nova sessão`**, which starts a fresh Spanish session.
Type **`DEMO-TX-003`** and show the generic denied-reference result. Do not reveal
the fictional foreign merchant or record facts. Then type **`Quiero un préstamo`**
and show the unsupported response/human-review offer. Do not confirm another draft.

**Narration:**

> A new session cannot read this unauthorized reference. A loan request stays
> outside the workflow and offers human review. Neither message creates a case.

### 2:14–2:37 — Slide 4: original results and current checks

**Show:** frozen ES/PT component and service counts with full denominators; separate
current engineering strip. Leave "Qualification failed" and "guarded serving
unscored" visible.

**Narration:**

> The frozen comparison improved intent recognition but failed workflow
> qualification. Spanish service completion fell from ten to eight of sixteen;
> Portuguese rose from seven to nine. Keyword routing remains default. Later
> repairs and delivery checks passed seven hundred fifty-two synthetic tests, preserving the original
> failures. Current guarded learned serving has no new held-out score.

### 2:37–2:45 — Slide 5: access and unfinished work

**Show:** run command, evidence links and the conspicuous pending-access panel.

**Narration:**

> Run locally and inspect the evidence. Portuguese lacks fluent review. Public
> judge access, deployment and verified submission remain pending.

## Demo readiness and exact-action check

The scripted ES ambiguity → selected fictional purchase → consented intake →
verified receipt → Portuguese consented handoff, and the separate foreign-ID/loan
denial sequence were reproduced through the current `BrowserSession` service with
temporary fictional-only stores on October 4. No source records, final cases,
credentials or network were used. The intake retry also reused one receipt and
kept one persisted intake. This verifies the planned service path; it is not a
browser recording or benchmark result.

Receipt identifiers vary per run. Capture the actual reference produced while
recording; never insert a fabricated receipt. The UI does not expose a second
confirmation button after success, so do not stage a nonexistent retry click.
If duplicate delivery needs additional footage, use the separately labeled
fictional CLI demo or a truthful engineering-test excerpt outside this 165-second
core sequence.

## Recording and viewer-access checklist

- Start a clean fictional demo and rehearse the exact prompts above. Verify both
  matches, explicit preparation, separate final confirmation, verified receipts,
  meaningful PT handoff and generic denial appear in the current browser.
- Capture only the demo window and approved English slides. Clear private tabs,
  notification overlays, credential-bearing material and private filesystem views.
- Record audible English narration and legible ES/PT customer interactions; show
  the actual controls and results, not only presentation mockups. Preserve the
  simulation disclosure and do not claim a real bank or human was contacted.
- Allow action pauses when recording. Rehearse or trim the final export to **at
  most 180 seconds**; measure the exported file's actual duration. Narration word
  count and target timings alone do not prove compliance.
- Watch the complete export: verify sound, visible receipts, legible qualification
  limits and both languages. English captions may aid review without replacing
  the bilingual UI.
- Upload the actual recording to the owner's chosen host and verify the link from
  a viewer context that does not rely on the owner's login. Record the real video
  URL and measured duration; leave placeholders visibly pending until then.
- Verify public repository access and the actual deployed-tool URL separately.
  A loopback address or private repository is not judge access. Replace the last
  slide's status only after those facts change and are verified.

## Source index

The slide/narration data rationale comes from [scope](scope.md),
[local data review](local_data_review.md) and public
[contact aggregates](../evidence/local_contacts_summary.json). Authored-language
justification and scoped permission are in [source-intent inventory](source_intent_inventory.md)
and [requirements](requirements.md). UI controls and fixture facts are documented in
[local UI](local_ui.md), [fictional fixtures](../bank_service/demo_fixtures.py) and
[UI copy](../bank_service/web/app.js). Scores remain those in
[frozen results](final_workflow_results.md) and
[public aggregate evidence](../evidence/final_workflow_results_v1.json). Current
engineering/review status is in [audit repairs](post_audit_repairs.md) and
[delivery checks](deployment_readiness.md). The current
[README](../README.md) is the run/status entry point. Historical records, balanced
authored requests and tests do not establish production benefit, independent
language generalization or a qualified deployed service.
