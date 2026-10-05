# XGBoost routing comparison, October 4

**Decision: retain naive Bayes v2.** Neither of the two declared XGBoost settings
met the improvement criteria. The trial is complete; no challenger was fitted on
the full corpus or connected to the UI, and the application default is unchanged.

The [protocol](xgboost_routing_protocol.md) was frozen before predictions. The
[aggregate evidence](../evidence/xgboost_routing_cv_v1.json) retains the manifest,
all configurations, class/language/fold results, paired changes, timing and
preservation checks. Per-attempt outputs remain in ignored local run
`.local/xgboost_routing_runs/xgboost-cv-v1`, without customer wording or bank facts.

## Results on the same grouped folds

All systems used the same 144 unchanged authored TRAIN messages and three fixed
folds. Each component trained on 96 rows and predicted the remaining 48. Whole
semantic clusters, with both languages, stayed together. Vocabulary and TF-IDF
were fitted within each training partition. Nine comparison fit calls yielded
**432 attempts with zero execution errors**; every system's denominator is 144.

| Model | Correct / 144 | Accuracy | Macro-F1 |
|---|---:|---:|---:|
| Naive Bayes v2 | 102 | 70.8% | 0.6816 |
| XGBoost, depth 1 | 50 | 34.7% | 0.3502 |
| XGBoost, depth 2 | 51 | 35.4% | 0.3579 |

Depth 2 ranked higher under the declared rule. Against v2 it gained five correct
routes and lost 56, a net loss of 51; macro-F1 fell by 0.3238. It regressed in both
languages. Zero-error criteria passed; the required F1 gain, four additional
correct routes and no language regression all failed.

| Model | Spanish correct / 72 | ES macro-F1 | Portuguese correct / 72 | PT macro-F1 |
|---|---:|---:|---:|---:|
| Naive Bayes v2 | 52 | 0.6981 | 50 | 0.6651 |
| XGBoost, depth 1 | 25 | 0.3476 | 25 | 0.3504 |
| XGBoost, depth 2 | 26 | 0.3526 | 25 | 0.3531 |

Unsupported requests remain a weakness: v2 correctly identified 10/36 (27.8%
recall), versus 9/36 (25.0%) for each XGBoost setting. Depth 2 identified 14/36
inquiries, 20/36 disputes and 8/36 human requests; v2 identified 25, 35 and 32.
Depth 2's fold correct counts were 13/48, 17/48 and 21/48, compared with v2's
38/48, 32/48 and 32/48. V2 completed all rows in six of 15 semantic clusters;
neither challenger completed any cluster. Complete counts and confusion
matrices are retained in the evidence.

Median component inference was approximately 0.266 ms for v2 and 1.194 ms for
depth 2; p95 was 0.526 and 1.724 ms. Median fit time was 0.008 and 0.472 seconds.
The first depth-1 fit took 3.374 seconds including lazy dependency import. These
single-machine measurements exclude UI, network, human work and deployment;
three fit observations do not establish a service latency guarantee.

## Interpretation and limits

The tested shallow, strongly regularized trees underperformed on this small,
sparse text corpus. This result concerns these two configurations and features;
it does not establish that XGBoost is unsuitable for other tasks or settings.
No additional parameter search is warranted within this bounded increment.

These are TRAIN selection scores on manually grouped authored messages. The
same folds were already exposed during the logistic trial, increasing selection
optimism. They are neither an untouched test nor end-to-end workflow evidence.
Spanish labels have owner approval; fluent Portuguese review remains pending.
Confidence scores are uncalibrated. All 144 requests received a matched model
proposal, which is coverage rather than proof of correctness or safe abstention.

Permissions, consent, selected-record identity, final confirmation and receipt
verification remain outside intent classification. The main next step remains
the separately frozen, source-grounded workflow evaluation of keyword routing
and v2, followed by deployment and submission preparation within their own scope.

## Verification and reproduction

The 18 focused toy tests and complete **592-test** regression suite passed in
the isolated XGBoost environment. Existing TRAIN, semantic grouping, historical
evidence, frozen prior protocol/code and the owner's readiness draft retained
their hashes. No final cases, old development messages, source records, PDFs or
private cohort contents were opened for this trial. Artifact checks cover Git
eligible working-tree files, not Git history or exact dictionary credentials.

The application needs no new dependency. To reproduce the experimental module
with Python 3.11 in a separate environment:

```powershell
python -m venv .local\xgb-reproduction
.\.local\xgb-reproduction\Scripts\python.exe -m pip install -r requirements-xgboost-experiment.txt
$xgbProtocolHash = (Get-FileHash -Algorithm SHA256 .\docs\xgboost_routing_protocol.md).Hash.ToLower()
.\.local\xgb-reproduction\Scripts\python.exe -B -m scripts.run_xgboost_routing_experiment --run-name xgboost-reproduction --protocol-sha256 $xgbProtocolHash
```

The run name must be new. Hashes and package versions are saved before fitting;
compute the protocol hash from the current checkout because Git can normalize
line endings. Package installation used public PyPI; no customer information
was sent externally. There were no external model calls or charges; local
compute and electricity cost were not measured.
