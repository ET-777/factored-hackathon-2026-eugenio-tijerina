# Local router comparison, October 4

**Decision: retain the v2 naive Bayes preview.** The best logistic regression
setting did not improve routing overall or in either language. The bounded
search is complete; no new model was connected to the UI and no default changed.

The [protocol](linear_routing_protocol.md) and the
[semantic grouping](../evaluation/linear_routing_groups_v1.json) were declared
before predictions. The [aggregate evidence](../evidence/linear_routing_cv_v1.json)
contains the frozen manifest, all four settings' results, language/class/fold
counts, paired changes, fit details, verification and preservation checks.
The ignored local run is `.local/linear_routing_runs/linear-cv-v1`; its per-attempt
outputs contain labels and IDs, never customer wording or private bank facts.

## Same-fold comparison

The 144 unchanged TRAIN messages were split into three fixed folds, after an
independent Codex review merged close paraphrases across family IDs. All 24
authored families remain in 15 semantic clusters. Each fold holds out 48 rows,
24 Spanish and 24 Portuguese, including whole clusters in both languages.
Every model trains on the other 96 rows; its vocabulary and TF-IDF weights, when
applicable, are fitted inside that training partition. Class/subtype populations
differ across folds; pooled results below include all attempts.

| System | Correct / 144 | Accuracy | Macro-F1 |
|---|---:|---:|---:|
| Naive Bayes v2, alpha 1 | 102 | 70.8% | 0.6816 |
| Character TF-IDF + logistic regression, C=0.1 | 46 | 31.9% | 0.3039 |
| Character TF-IDF + logistic regression, C=1 | 87 | 60.4% | 0.5893 |
| Character TF-IDF + logistic regression, C=10 | 99 | 68.8% | 0.6702 |

| Language | Naive Bayes correct / 72 | Best logistic correct / 72 | NB macro-F1 | Logistic macro-F1 |
|---|---:|---:|---:|---:|
| Spanish | 52 | 50 | 0.6981 | 0.6796 |
| Portuguese, fluent review pending | 50 | 49 | 0.6651 | 0.6600 |

The best logistic setting corrected three cases that NB missed but lost six
cases that NB got right: a net loss of three. Its macro-F1 was lower by 0.0114.
It failed the predeclared improvement and language non-regression criteria.
All 12 component fit calls and 576 planned predictions completed with zero
execution/convergence errors. All systems matched an intent on every attempt;
zero abstentions here does not establish useful uncertainty handling.

NB's accuracy varied from 32/48 to 38/48 across folds; the best logistic model
varied from 31/48 to 37/48. Both got every row correct in 12/24 original families
and 6/15 merged clusters. These counts show the limited and correlated sample.

## What the check revealed

The clearest shared weakness is recognizing unsupported services when the
corresponding request family is absent from training. Both models correctly
routed only 10/36 unsupported messages in these folds. NB correctly routed
25/36 inquiries, 35/36 dispute requests and 32/36 human requests. Its four-class
macro-F1 exposes this imbalance more clearly than accuracy alone.

This result supports retaining the existing implementation over the tested
alternative. It does not demonstrate reliable broad conversational understanding.
The shared service rules, permissions and consent controls still require their
own grounded workflow assessment. Intent mistakes are not evidence of actual
unauthorized actions: this comparison executed no banking tools or workflows.

The earlier [short-message results](short_message_results.md), including 79.2%
on 48 coverage messages and 96.9% on 32 follow-up messages, remain unchanged.
Those used a model fitted on all 144 TRAIN rows and different authored inputs.
This check trains on 96 rows per fold and withholds whole related request
clusters. The percentages are not directly comparable and do not show a code
regression or a measured production accuracy change.

Cross-validation also selected C, so its score is development selection evidence,
not an independent final estimate. The folds were reviewed using TRAIN semantics,
not predictions; manual grouping cannot prove semantic independence. Other limits
include only 15 clusters, authored language, shared task concepts, prior
development-guided training expansion and unequal subtype/class support by fold.
Spanish input wording/labels have owner approval; output semantics and handoff
usefulness were not reviewed here. Fluent Portuguese review remains pending.
No confidence threshold, additional model family, training rewrite or second
search was tried after seeing these results. No full-TRAIN logistic candidate was
fitted or promoted after the failed comparison.

## Timing and verification

On this local Windows/Python 3.11 runtime, median/p95 raw intent-call timing was
0.266/0.625 ms for NB and 0.613/1.119 ms for logistic C=10, with 144 observations
per system. These timings exclude model loading, output serialization, UI,
networking, human time and deployment; they are not response-time promises.
Complete fit-call timing includes validation, and the first logistic fit also
includes cold optional dependency imports. The hardware snapshot was captured
after the run, not frozen before timing. External model calls and API charges
were zero; local compute/electricity cost remains unmeasured.

The 18 focused toy tests passed. The first full-suite attempt encountered sandbox
restrictions on loopback HTTP and temporary files; the unchanged suite then
passed **574 tests** with those local restrictions lifted. Independent saved-
evidence review recomputed metrics/pairs and verified all recorded input/code/
protocol/grouping hashes. These checks verify software and arithmetic, not final
language quality, record grounding or service completion.

Original TRAIN bytes, the v2 TRAIN bytes, historical development/short-message
evidence and the owner's readiness draft have unchanged hashes. The original
sealed final set was not opened. No old development messages, short-message test
batch contents, raw source files, PDFs or private source records were used.

## Reproduce the fixed experiment

The default application retains its lightweight dependencies. The experimental
module has a separate optional extra; this run used scikit-learn 1.8.0, NumPy
2.2.6, SciPy 1.16.3, joblib 1.5.3 and threadpoolctl 3.6.0. Install the optional
extra only when reproducing the experiment:

```powershell
python -m pip install -e '.[routing-experiment]'
$routingProtocolHash = (Get-FileHash -Algorithm SHA256 .\docs\linear_routing_protocol.md).Hash.ToLower()
python -B -m scripts.run_linear_routing_experiment --run-name linear-cv-reproduction --protocol-sha256 $routingProtocolHash
```

The run name must be new: existing runs cannot be overwritten. Runtime versions
and file hashes are recorded before fitting. Git may normalize line endings, so
compute the protocol hash from the actual checkout. Reproduction is not an
authorization for further parameter selection or access to final cases.

The next useful increment is the separately frozen, source-grounded end-to-end
comparison of the existing keyword baseline and v2 workflow, with explicit
language, completion, grounding, safety and handoff denominators. Final workload
review/freeze and Portuguese review remain separate requirements.
