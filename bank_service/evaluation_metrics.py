"""Pure arithmetic for a four-intent routing comparison; no execution or I/O.

``score_routes(rows)`` accepts a finite iterable of mappings with exactly:
    gold_intent: one of LABELS
    language: "es" or "pt"
    family_id: a nonblank string
    prediction: IntentProposal or None
and optionally ``error: bool`` (default False). Metadata/schema errors reject the
whole calculation with a fixed MetricsError; they never silently drop attempts.
An unmatched valid proposal is an abstention. None, a malformed proposal, or an
explicit error is an abstention AND an error. Abstention never counts as a correct
unsupported prediction. Confidence is validated but no threshold is selected.

Rates are fractions, not percentages. Per-intent zero-denominator P/R/F1 is zero;
macro-F1 averages all four labels when attempts exist. Empty population aggregate
rates, macro-F1, and family rates are None, avoiding a performance claim on no data.
Families group all rows bearing the same family_id, including translations; a
family is correct only if every attempt in that population is correct.

``summarize_latencies(seconds)`` accepts one finite nonnegative int/float or None
per attempt. None remains a missing observation; no time is imputed. Median and
nearest-rank p95 use only observed durations, with that denominator explicit.
Neither function implies human label review, independence, or workflow success.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import math

from bank_service.routing import IntentProposal


LABELS = ("inquiry", "dispute_intake", "human_request", "unsupported")
ABSTAIN = "ABSTAIN"
PREDICTION_COLUMNS = LABELS + (ABSTAIN,)
REQUIRED_ROW_KEYS = frozenset({"gold_intent", "language", "family_id", "prediction"})


class MetricsError(ValueError):
    """Fixed codes only; input values never appear in error messages."""


def _require(condition, code):
    if not condition:
        raise MetricsError(code)


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _proposal_result(prediction, explicit_error):
    if explicit_error:
        return ABSTAIN, True
    valid = (
        isinstance(prediction, IntentProposal)
        and isinstance(prediction.intent, str)
        and prediction.intent in LABELS
        and type(prediction.matched) is bool
        and _finite_number(prediction.confidence)
        and 0 <= prediction.confidence <= 1
    )
    if not valid:
        return ABSTAIN, True
    if not prediction.matched:
        return ABSTAIN, False
    return prediction.intent, False


def _validated_attempts(rows):
    _require(isinstance(rows, Iterable) and not isinstance(rows, (str, bytes, Mapping)),
             "invalid_rows")
    attempts = []
    for row in rows:
        _require(isinstance(row, Mapping), "invalid_row")
        _require(REQUIRED_ROW_KEYS.issubset(row)
                 and set(row).issubset(REQUIRED_ROW_KEYS | {"error"}), "invalid_row_schema")
        gold, language, family = row["gold_intent"], row["language"], row["family_id"]
        _require(isinstance(gold, str) and gold in LABELS, "invalid_gold_intent")
        _require(isinstance(language, str) and language in ("es", "pt"), "invalid_language")
        _require(isinstance(family, str) and bool(family.strip()) and family == family.strip(),
                 "invalid_family_id")
        explicit_error = row.get("error", False)
        _require(type(explicit_error) is bool, "invalid_error_flag")
        prediction, error = _proposal_result(row["prediction"], explicit_error)
        attempts.append((gold, language, family, prediction, error))
    return attempts


def _rate(count, total):
    return count / total if total else None


def _population(attempts):
    confusion = {gold: {prediction: 0 for prediction in PREDICTION_COLUMNS} for gold in LABELS}
    family_correct = {}
    correct = abstentions = errors = 0
    for gold, _, family, prediction, error in attempts:
        confusion[gold][prediction] += 1
        is_correct = prediction == gold
        correct += int(is_correct)
        abstentions += int(prediction == ABSTAIN)
        errors += int(error)
        family_correct[family] = family_correct.get(family, True) and is_correct

    per_intent = {}
    for label in LABELS:
        true_positive = confusion[label][label]
        support = sum(confusion[label].values())
        predicted = sum(confusion[gold][label] for gold in LABELS)
        false_positive = predicted - true_positive
        false_negative = support - true_positive
        f1_denominator = 2 * true_positive + false_positive + false_negative
        per_intent[label] = {
            "support": support,
            "predicted": predicted,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": true_positive / predicted if predicted else 0.0,
            "recall": true_positive / support if support else 0.0,
            "f1": 2 * true_positive / f1_denominator if f1_denominator else 0.0,
        }

    total = len(attempts)
    families = len(family_correct)
    families_correct = sum(family_correct.values())
    return {
        "attempts": total,
        "correct": correct,
        "incorrect": total - correct,
        "covered": total - abstentions,
        "abstentions": abstentions,
        "errors": errors,
        "accuracy": _rate(correct, total),
        "coverage": _rate(total - abstentions, total),
        "abstention_rate": _rate(abstentions, total),
        "error_rate": _rate(errors, total),
        "macro_f1": sum(per_intent[label]["f1"] for label in LABELS) / len(LABELS) if total else None,
        "confusion": confusion,
        "per_intent": per_intent,
        "family_exact_all_correct": {
            "families": families,
            "correct": families_correct,
            "incorrect": families - families_correct,
            "rate": _rate(families_correct, families),
        },
    }


def score_routes(rows):
    """Score all attempts overall and separately for ES/PT, without I/O or mutation."""
    attempts = _validated_attempts(rows)
    return {
        "labels": list(LABELS),
        "prediction_columns": list(PREDICTION_COLUMNS),
        "overall": _population(attempts),
        "by_language": {language: _population([row for row in attempts if row[1] == language])
                        for language in ("es", "pt")},
    }


def summarize_latencies(seconds):
    """Retain missing attempts; summarize observed seconds with nearest-rank p95."""
    _require(isinstance(seconds, Iterable) and not isinstance(seconds, (str, bytes, Mapping)),
             "invalid_latencies")
    observed, attempts = [], 0
    for value in seconds:
        attempts += 1
        if value is None:
            continue
        _require(_finite_number(value) and value >= 0, "invalid_latency")
        observed.append(float(value))
    observed.sort()
    count = len(observed)
    observed_median = None
    if count:
        left, right = observed[(count - 1) // 2], observed[count // 2]
        # Durations are nonnegative; this equivalent midpoint cannot overflow
        # for finite inputs as (left + right) / 2 can.
        observed_median = left + (right - left) / 2
    return {
        "unit": "seconds",
        "attempts": attempts,
        "observed": count,
        "missing": attempts - count,
        "coverage": _rate(count, attempts),
        "median": observed_median,
        "p95": observed[math.ceil(0.95 * count) - 1] if count else None,
        "p95_method": "nearest_rank_on_observed",
    }
