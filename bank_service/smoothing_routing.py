"""Bounded TRAIN-only naive Bayes smoothing challenger.

Normalization, character counts, empirical priors and abstention are shared
with the incumbent. Only per-instance additive smoothing changes. Normalized scores
are uncalibrated and provide no authorization or action consent.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math

from bank_service.learned_routing import (
    INTENTS, TrainingDataError, _AFFIRMATION, _features, _request, train_router,
)
from bank_service.routing import IntentProposal


ALPHA_VALUES = (0.1, 1.0, 10.0)


@dataclass(frozen=True)
class SmoothedCharacterNgramRouter:
    """Immutable count model with an explicit, bounded smoothing parameter."""

    training_hash: str
    training_row_count: int
    vocabulary_size: int
    class_counts: Mapping[str, int]
    language_counts: Mapping[str, int]
    alpha: float
    _vocabulary: frozenset[str] = field(repr=False)
    _feature_counts: tuple[Mapping[str, int], ...] = field(repr=False)
    _log_denominators: tuple[float, ...] = field(repr=False)
    _log_priors: tuple[float, ...] = field(repr=False)

    def route_intent(self, text: str, language: str) -> IntentProposal:
        """Use the incumbent score formula with this instance's fixed alpha."""
        normalized = _request(text, language)
        if _AFFIRMATION.search(normalized):
            return IntentProposal("unsupported", 0.0, False)
        known = {
            feature: count for feature, count in _features(normalized).items()
            if feature in self._vocabulary
        }
        if not known:
            return IntentProposal("unsupported", 0.0, False)
        scores = []
        for counts, denominator, prior in zip(
            self._feature_counts, self._log_denominators, self._log_priors,
        ):
            scores.append(prior + math.fsum(
                frequency * (math.log(counts.get(feature, 0) + self.alpha) - denominator)
                for feature, frequency in sorted(known.items())
            ))
        maximum = max(scores)
        weights = [math.exp(score - maximum) for score in scores]
        total = math.fsum(weights)
        probabilities = [weight / total for weight in weights]
        winners = [index for index, score in enumerate(scores) if math.isclose(
            score, maximum, rel_tol=0.0, abs_tol=1e-12,
        )]
        confidence = max(probabilities)
        if len(winners) != 1:
            return IntentProposal("unsupported", confidence, False)
        return IntentProposal(INTENTS[winners[0]], confidence, True)


def train_smoothed_router(
    training_rows: Sequence[Mapping], alpha: float = 1.0,
) -> SmoothedCharacterNgramRouter:
    """Validate and count explicit rows, then apply one fixed instance alpha.

    Incumbent training supplies its complete validation, canonical row hash,
    count vocabulary and empirical priors. No global parameter is modified.
    No other feature, class-prior or confidence choice is selectable.
    """
    if type(alpha) is not float or alpha not in ALPHA_VALUES:
        raise TrainingDataError("invalid_smoothing_alpha")
    validated = train_router(training_rows)
    return SmoothedCharacterNgramRouter(
        training_hash=validated.training_hash,
        training_row_count=validated.training_row_count,
        vocabulary_size=validated.vocabulary_size,
        class_counts=validated.class_counts,
        language_counts=validated.language_counts,
        alpha=alpha,
        _vocabulary=validated._vocabulary,
        _feature_counts=validated._feature_counts,
        _log_denominators=tuple(math.log(
            sum(counts.values()) + alpha * validated.vocabulary_size,
        ) for counts in validated._feature_counts),
        _log_priors=validated._log_priors,
    )
