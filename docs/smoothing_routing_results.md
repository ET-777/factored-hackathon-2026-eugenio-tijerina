# Naive Bayes smoothing comparison, October 4

**Alpha 0.1 improved the point estimates, but did not meet the declared promotion
rule. Retain v2 at alpha 1.** The bounded smoothing-only check is complete. No
application selector/default changed, no full-corpus challenger was fitted, and
no further parameter search followed the result.

The [protocol](smoothing_routing_protocol.md) was frozen before predictions. The
[aggregate evidence](../evidence/smoothing_routing_cv_v1.json) preserves the
manifest, all configurations, language/class/fold results, paired changes,
timing and verification. Per-attempt outputs remain in ignored local run
`.local/smoothing_routing_runs/smoothing-cv-v1`, without customer wording or
bank facts. The separate experimental adapter needs only Python's standard
library and never changes the incumbent's global settings.

## Same-fold results

Use the same unchanged 144 authored TRAIN messages, 24 families and 15 semantic
clusters as the preceding model comparisons. Three fixed folds each hold out
48 messages, 24 per language, with whole clusters kept together. Each model's
vocabulary/counts are fitted on the other 96 rows. Character 3–5 counts,
normalization, empirical priors and abstention rules stay fixed; only smoothing
varies. Nine comparison fit calls produced **432 attempts with zero errors**.

| Alpha | Correct / 144 | Accuracy | Macro-F1 | Unsupported correct / 36 |
|---|---:|---:|---:|---:|
| 1, unchanged v2 | 102 | 70.8% | 0.6816 | 10 |
| 0.1 | 106 | 73.6% | 0.7168 | 13 |
| 10 | 96 | 66.7% | 0.6294 | 7 |

Alpha 0.1 ranked first among the declared alternatives. It gained five correct
routes and lost one against v2, net **four additional correct routes**. Accuracy
rose by 2.78 percentage points and macro-F1 by **0.03519**. It passed the zero-error,
four-additional-correct and per-language nonregression criteria, but missed the
required **0.05 macro-F1 gain**. Do not revise that threshold after scoring or
describe the configuration as qualifying. Alpha 10 lost six correct routes and
improved none.

| Alpha | Spanish correct / 72 | ES macro-F1 | Portuguese correct / 72 | PT macro-F1 |
|---|---:|---:|---:|---:|
| 1 | 52 | 0.6981 | 50 | 0.6651 |
| 0.1 | 54 | 0.7303 | 52 | 0.7036 |
| 10 | 50 | 0.6669 | 46 | 0.5900 |

At alpha 0.1, unsupported-request recall improved from 27.8% to **36.1%**,
but 23/36 unsupported messages were still misclassified. Inquiry and dispute
correct counts stayed at 25/36 and 35/36; human-request correct counts rose
from 32/36 to 33/36. Its fold correct counts were 38/48, 33/48 and 35/48, against
v2's 38/48, 32/48 and 32/48. Both completed all rows in 12/24 authored families
and six of 15 semantic clusters. Complete confusion matrices are in the evidence.

Median component inference was 0.219 ms at alpha 1 and 0.233 ms at alpha 0.1;
p95 was 0.543 and 0.523 ms. Median comparison fit time was 0.0063 and 0.0068
seconds. These single-machine component timings exclude UI, networking, human
work and deployment; three fit observations do not establish a service guarantee.

## Limits and verification

These are exploratory TRAIN selection results. The same manually grouped folds
have already informed logistic and XGBoost comparisons; repeated selection
increases optimism. The small balanced authored corpus, previous development
feedback and pending fluent Portuguese review limit generalization claims.
These scores do not establish independent final or end-to-end workflow quality.
All attempts received a matched proposal: coverage is not proof of correctness
or safe abstention. Model scores remain uncalibrated.

The 15 focused toy tests and complete **607-test** regression suite passed. Toy
checks establish exact alpha-1 parity, an independent closed-form smoothing
example, validation, immutability and abstention; they are not performance tests.
Thirty frozen prior code/TRAIN/group/protocol/evidence and readiness-draft hashes
remained unchanged. No old development/test-batch wording, source records,
PDFs/private cohorts or final case contents were opened for this comparison.
The default router, v1/v2 selectors and external authorization/consent/receipt
checks remain unchanged. No external model calls or charges occurred; local
compute/electricity cost is unmeasured. Artifact checking covers Git eligible
working-tree files, not Git history or exact dictionary credentials.

The next step is to freeze the chosen workflow and complete its separately
reviewed source-grounded evaluation. The alpha-0.1 result can be reported as a
modest exploratory gain without retroactively promoting it under a weaker rule.

## Reproduce

Use Python 3.11+, with no additional experiment dependencies:

```powershell
$smoothingProtocolHash = (Get-FileHash -Algorithm SHA256 .\docs\smoothing_routing_protocol.md).Hash.ToLower()
python -B -m scripts.run_smoothing_routing_experiment --run-name smoothing-reproduction --protocol-sha256 $smoothingProtocolHash
```

Use a new run name; existing runs cannot be overwritten. Compute the protocol
hash from the current checkout because Git may normalize line endings.
Reproduction does not authorize further selection or access to final cases.
