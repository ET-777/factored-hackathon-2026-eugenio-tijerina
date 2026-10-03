"""Small offline supervised character n-gram intent model.

This preview uses NFKC/casefold, accent folding and whitespace collapse for both
training and inference; character 3–5 counts, Laplace smoothing alpha=1, and
empirical class priors. Confidence is a normalized model score, not calibrated
probability or authorization. No permissions, slots, actions, files or providers
are handled here. No development/final data or thresholds are consulted.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
import unicodedata

from bank_service.routing import IntentProposal, RoutingError


MAX_TRAINING_ROWS = 256
MAX_TEXT_CHARACTERS = 1000
MAX_VOCABULARY = 20000
NGRAM_SIZES = (3, 4, 5)
ALPHA = 1.0
INTENTS = tuple(sorted(("inquiry", "dispute_intake", "human_request", "unsupported")))
LANGUAGES = frozenset(("es", "pt"))
ROW_FIELDS = frozenset(("id", "family_id", "language", "text", "intent"))
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_AFFIRMATION = re.compile(
    r"^(?:si|sim|yes|ok|okay|de acuerdo)[\s.!?]*$"
    r"|^(?:confirmo|confirmar|confirmado|acepto|aceitar)\b"
)


class TrainingDataError(ValueError):
    """Fixed codes only; never include training text, identities or labels."""


def _normalized(value: str) -> str:
    value.encode("utf-8")  # Refuse malformed Unicode before hashing or fitting.
    folded = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", value).casefold())
    return " ".join("".join(character for character in folded if not unicodedata.combining(character)).split())


def _features(normalized: str) -> Counter[str]:
    padded = " " + normalized + " "
    return Counter(
        padded[index:index + size]
        for size in NGRAM_SIZES
        for index in range(len(padded) - size + 1)
    )


def _request(text: str, language: str) -> str:
    if not isinstance(language, str) or language not in LANGUAGES:
        raise RoutingError("unsupported_language")
    if not isinstance(text, str) or not text.strip():
        raise RoutingError("invalid_request")
    if len(text) > MAX_TEXT_CHARACTERS:
        raise RoutingError("request_too_long")
    try:
        normalized = _normalized(text)
    except UnicodeError:
        raise RoutingError("invalid_request") from None
    if not normalized:
        raise RoutingError("invalid_request")
    if len(normalized) > MAX_TEXT_CHARACTERS:
        raise RoutingError("request_too_long")
    return normalized


@dataclass(frozen=True)
class CharacterNgramRouter:
    """Immutable learned counts from one explicitly supplied training sequence.

    training_hash hashes exact authored row values in canonical JSON, with rows
    sorted by identity and object keys sorted. It is distinct from a file hash.
    Scores abstain for assent, entirely unseen lexical features and top ties.
    No confidence threshold is tuned or applied.
    """
    training_hash: str
    training_row_count: int
    vocabulary_size: int
    class_counts: Mapping[str, int]
    language_counts: Mapping[str, int]
    _vocabulary: frozenset[str]
    _feature_counts: tuple[Mapping[str, int], ...]
    _log_denominators: tuple[float, ...]
    _log_priors: tuple[float, ...]

    def route_intent(self, text: str, language: str) -> IntentProposal:
        """Propose a learned intent; never confirm consent or authorize a tool."""
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
        # Sort feature iteration so results are independent of authored row order.
        for counts, denominator, prior in zip(
            self._feature_counts, self._log_denominators, self._log_priors,
        ):
            scores.append(prior + math.fsum(
                frequency * (math.log(counts.get(feature, 0) + ALPHA) - denominator)
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


def train_router(training_rows: Sequence[Mapping]) -> CharacterNgramRouter:
    """Fit on supplied authored rows; refuse invalid or silently dropped data."""
    if (
        not isinstance(training_rows, Sequence) or isinstance(training_rows, (str, bytes, bytearray))
        or not 4 <= len(training_rows) <= MAX_TRAINING_ROWS
    ):
        raise TrainingDataError("invalid_training_rows")
    validated, identities, normalized_examples, family_intents = [], set(), set(), {}
    class_counts, language_counts = Counter(), Counter()
    for row in training_rows:
        if not isinstance(row, Mapping) or set(row) != ROW_FIELDS:
            raise TrainingDataError("invalid_training_row")
        identity, family = row["id"], row["family_id"]
        if any(not isinstance(value, str) or not _IDENTITY.fullmatch(value) for value in (identity, family)):
            raise TrainingDataError("invalid_training_identity")
        if identity in identities:
            raise TrainingDataError("duplicate_training_identity")
        language, intent, text = row["language"], row["intent"], row["text"]
        if not isinstance(language, str) or language not in LANGUAGES:
            raise TrainingDataError("invalid_training_language")
        if not isinstance(intent, str) or intent not in INTENTS:
            raise TrainingDataError("invalid_training_intent")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARACTERS:
            raise TrainingDataError("invalid_training_text")
        try:
            normalized = _normalized(text)
        except UnicodeError:
            raise TrainingDataError("invalid_training_text") from None
        if not normalized or len(normalized) > MAX_TEXT_CHARACTERS:
            raise TrainingDataError("invalid_training_text")
        if (language, normalized) in normalized_examples:
            raise TrainingDataError("duplicate_training_text")
        if family in family_intents and family_intents[family] != intent:
            raise TrainingDataError("training_family_label_conflict")
        identities.add(identity)
        normalized_examples.add((language, normalized))
        family_intents[family] = intent
        class_counts[intent] += 1
        language_counts[language] += 1
        validated.append((dict(row), normalized))
    if set(class_counts) != set(INTENTS):
        raise TrainingDataError("training_classes_missing")
    validated.sort(key=lambda pair: pair[0]["id"])
    feature_counts = {label: Counter() for label in INTENTS}
    vocabulary = set()
    for row, normalized in validated:
        features = _features(normalized)
        vocabulary.update(features)
        if len(vocabulary) > MAX_VOCABULARY:
            raise TrainingDataError("vocabulary_limit_exceeded")
        feature_counts[row["intent"]].update(features)
    training_hash = hashlib.sha256(json.dumps(
        [row for row, _ in validated], sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return CharacterNgramRouter(
        training_hash=training_hash, training_row_count=len(validated), vocabulary_size=len(vocabulary),
        class_counts=MappingProxyType({label: class_counts[label] for label in INTENTS}),
        language_counts=MappingProxyType({language: language_counts[language] for language in sorted(LANGUAGES)}),
        _vocabulary=frozenset(vocabulary),
        _feature_counts=tuple(MappingProxyType(dict(feature_counts[label])) for label in INTENTS),
        _log_denominators=tuple(math.log(
            sum(feature_counts[label].values()) + ALPHA * len(vocabulary),
        ) for label in INTENTS),
        _log_priors=tuple(math.log(class_counts[label] / len(validated)) for label in INTENTS),
    )
