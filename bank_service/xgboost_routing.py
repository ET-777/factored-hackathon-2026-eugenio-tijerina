"""Bounded offline XGBoost challenger using the linear router's exact TF-IDF.

This experiment fits only explicitly supplied rows and is disconnected from
application routing. Vocabulary and IDF are fitted on those rows. Returned
probabilities are uncalibrated scores, never permission or action consent.
Only tree depth is selectable, from the two fixed values below.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from typing import Any

from bank_service.learned_routing import (
    INTENTS, TrainingDataError, _AFFIRMATION, _normalized, _request, train_router,
)
from bank_service.linear_routing import _character_features
from bank_service.routing import IntentProposal, RoutingError


MAX_DEPTH_VALUES = (1, 2)


@dataclass(frozen=True)
class XGBoostIntentRouter:
    """TRAIN-only experimental model with a fixed numeric-to-intent mapping.

    No score threshold or calibration is applied. The training hash describes
    exact authored values, as for the incumbent; fitted objects are private.
    """

    training_hash: str
    training_row_count: int
    vocabulary_size: int
    class_counts: Mapping[str, int]
    language_counts: Mapping[str, int]
    max_depth: int
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
            output = self._estimator.predict_proba(features)
            if len(output) != 1 or (
                hasattr(output, "shape") and tuple(output.shape) != (1, len(self.classes))
            ):
                raise RoutingError("xgboost_inference_failed")
            probabilities = tuple(float(value) for value in output[0])
        except (ValueError, RuntimeError, ArithmeticError, TypeError, IndexError):
            raise RoutingError("xgboost_inference_failed") from None
        if (
            len(probabilities) != len(self.classes)
            or not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in probabilities)
            or not math.isclose(math.fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-6)
        ):
            raise RoutingError("xgboost_inference_failed")
        confidence = max(probabilities)
        winners = [index for index, probability in enumerate(probabilities) if math.isclose(
            probability, confidence, rel_tol=0.0, abs_tol=1e-12,
        )]
        if len(winners) != 1:
            return IntentProposal("unsupported", confidence, False)
        return IntentProposal(self.classes[winners[0]], confidence, True)


def train_xgboost_router(
    training_rows: Sequence[Mapping], max_depth: int = 1,
) -> XGBoostIntentRouter:
    """Fit supplied rows with incumbent validation and fixed XGBoost settings.

    Optional dependencies are imported only here. Labels are explicitly encoded
    as contiguous integers in sorted INTENTS order and mapped back at inference.
    No early stopping, validation rows, search or retry is used.
    """
    if type(max_depth) is not int or max_depth not in MAX_DEPTH_VALUES:
        raise TrainingDataError("invalid_xgboost_max_depth")
    validated = train_router(training_rows)
    ordered = sorted(training_rows, key=lambda row: row["id"])
    texts = [_normalized(row["text"]) for row in ordered]
    encoded_labels = [INTENTS.index(row["intent"]) for row in ordered]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from xgboost import XGBClassifier
    except ImportError:
        raise TrainingDataError("xgboost_dependency_unavailable") from None
    vectorizer = TfidfVectorizer(
        analyzer=_character_features, norm="l2", use_idf=True,
        smooth_idf=True, sublinear_tf=False,
    )
    estimator = XGBClassifier(
        n_estimators=100, learning_rate=0.1, max_depth=max_depth,
        min_child_weight=2, reg_lambda=10, reg_alpha=0,
        subsample=1, colsample_bytree=1,
        objective="multi:softprob", num_class=len(INTENTS),
        random_state=0, n_jobs=1, tree_method="hist", device="cpu",
        verbosity=0,
    )
    try:
        estimator.fit(vectorizer.fit_transform(texts), encoded_labels)
        if tuple(estimator.classes_) != tuple(range(len(INTENTS))):
            raise TrainingDataError("xgboost_training_failed")
    except (ValueError, RuntimeError, ArithmeticError, TypeError):
        raise TrainingDataError("xgboost_training_failed") from None
    return XGBoostIntentRouter(
        training_hash=validated.training_hash,
        training_row_count=validated.training_row_count,
        vocabulary_size=len(vectorizer.vocabulary_),
        class_counts=validated.class_counts,
        language_counts=validated.language_counts,
        max_depth=max_depth, classes=INTENTS,
        _vectorizer=vectorizer, _estimator=estimator,
    )
