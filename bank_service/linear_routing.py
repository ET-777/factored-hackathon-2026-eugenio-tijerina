"""Experimental offline character TF-IDF plus L2 logistic intent router.

This module has no connection to default application routing. It fits only the
explicitly supplied training rows, using the incumbent's normalization and
whole-text padded character 3–5 counts. IDF, vocabulary and L2 normalization are
fitted on those rows. Scores are uncalibrated model scores, never authorization
or consent. The only selectable parameter is C, from the bounded values below.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from typing import Any
import warnings

from bank_service.learned_routing import (
    TrainingDataError, _AFFIRMATION, _features, _normalized, _request, train_router,
)
from bank_service.routing import IntentProposal, RoutingError


REGULARIZATION_VALUES = (0.1, 1.0, 10.0)


def _character_features(normalized: str):
    """Supply repeated features to preserve the incumbent's exact counts."""
    return _features(normalized).elements()


@dataclass(frozen=True)
class LinearIntentRouter:
    """TRAIN-only experimental model; no fitted score threshold is applied.

    Class order comes from the estimator, rather than an assumed label order.
    The training hash describes exact authored values, as for the incumbent.
    The fitted sklearn objects are private and excluded from representation.
    """

    training_hash: str
    training_row_count: int
    vocabulary_size: int
    class_counts: Mapping[str, int]
    language_counts: Mapping[str, int]
    regularization: float
    classes: tuple[str, ...]
    _vectorizer: Any = field(repr=False, compare=False)
    _estimator: Any = field(repr=False, compare=False)

    def route_intent(self, text: str, language: str) -> IntentProposal:
        """Propose an intent, abstaining on assent, unseen features and ties."""
        normalized = _request(text, language)
        if _AFFIRMATION.search(normalized):
            return IntentProposal("unsupported", 0.0, False)
        try:
            features = self._vectorizer.transform([normalized])
            if not features.nnz:
                return IntentProposal("unsupported", 0.0, False)
            scores = tuple(float(score) for score in self._estimator.decision_function(features)[0])
        except (ValueError, RuntimeError, ArithmeticError):
            raise RoutingError("linear_inference_failed") from None
        if len(scores) != len(self.classes) or not all(math.isfinite(score) for score in scores):
            raise RoutingError("linear_inference_failed")
        maximum = max(scores)
        weights = tuple(math.exp(score - maximum) for score in scores)
        confidence = max(weights) / math.fsum(weights)
        winners = [index for index, score in enumerate(scores) if math.isclose(
            score, maximum, rel_tol=0.0, abs_tol=1e-12,
        )]
        if len(winners) != 1:
            return IntentProposal("unsupported", confidence, False)
        return IntentProposal(self.classes[winners[0]], confidence, True)


def train_linear_router(
    training_rows: Sequence[Mapping], regularization: float = 1.0,
) -> LinearIntentRouter:
    """Fit supplied rows with the incumbent's complete, fixed-code validation.

    Validation reuses train_router's bounded count fit so the experimental path
    cannot silently accept a different training contract. sklearn is imported
    only here; baseline and application imports gain no new dependency.
    """
    if (
        not isinstance(regularization, float)
        or regularization not in REGULARIZATION_VALUES
    ):
        raise TrainingDataError("invalid_linear_regularization")
    validated = train_router(training_rows)
    ordered = sorted(training_rows, key=lambda row: row["id"])
    texts = [_normalized(row["text"]) for row in ordered]
    labels = [row["intent"] for row in ordered]
    try:
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        raise TrainingDataError("linear_dependency_unavailable") from None
    vectorizer = TfidfVectorizer(
        analyzer=_character_features, norm="l2", use_idf=True,
        smooth_idf=True, sublinear_tf=False,
    )
    # lbfgs with l1_ratio=0 uses L2 regularization. Omitting the deprecated
    # penalty parameter keeps this explicit contract warning-free on sklearn 1.8.
    estimator = LogisticRegression(
        C=float(regularization), l1_ratio=0.0, solver="lbfgs",
        max_iter=1000, random_state=0,
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            estimator.fit(vectorizer.fit_transform(texts), labels)
    except ConvergenceWarning:
        raise TrainingDataError("linear_fit_not_converged") from None
    except (ValueError, RuntimeError, ArithmeticError):
        raise TrainingDataError("linear_training_failed") from None
    return LinearIntentRouter(
        training_hash=validated.training_hash,
        training_row_count=validated.training_row_count,
        vocabulary_size=len(vectorizer.vocabulary_),
        class_counts=validated.class_counts,
        language_counts=validated.language_counts,
        regularization=float(regularization),
        classes=tuple(str(label) for label in estimator.classes_),
        _vectorizer=vectorizer, _estimator=estimator,
    )
