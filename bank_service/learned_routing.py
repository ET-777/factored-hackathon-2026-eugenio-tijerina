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

from bank_service.routing import (
    IntentProposal, RoutingError, is_explicit_human_request, is_explicit_inquiry,
    is_greeting, is_search_followup, route_intent,
)


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


_TRANSACTION_NOUN = (
    r"(?:pagos?|pagamentos?|cargos?|cobros?|cobrancas?|compras?|"
    r"transaccion(?:es)?|transacao|transacoes|movimientos?|movimentos?|"
    r"movimentacao|movimentacoes|operacion(?:es)?|operacao|operacoes|"
    r"debitos?|lancamentos?|retiros?|saques?)"
)
_BUSINESS_CONTEXT = re.compile(
    r"\b(?:" + _TRANSACTION_NOUN + r"|comercio|tienda|vendedor|establecimiento|"
    r"estabelecimento|importe|monto|quantia|divisa|moneda|moeda|"
    r"reembolso|prestamo|emprestimo|tarjeta|cartao|saldo)\b"
)


def _positive_read_request(normalized: str) -> bool:
    """A read verb plus record noun may include filters, never a negated read."""
    verb = (r"(?:ver|consultar|consulta|consulte|buscar|busca|busco|busque|"
            r"encontrar|localizar|mostrar|muestra|muestrame|mostre|"
            r"conferir|confira|verificar|revisar|mirar|mira|cotejar|comparar)")
    if re.search(r"\b(?:no|nao|nunca|ni|nem)\b", normalized):
        return False
    return bool(re.search(r"\b" + verb + r"\b[^.;!?]{0,90}\b"
                          + _TRANSACTION_NOUN + r"\b", normalized))


def _positive_dispute_request(normalized: str, language: str) -> bool:
    """Require a literal complaint or request, rather than the model's label.

    This is a bounded wording check, not a truth check or consent to a write.
    Unsupported actions retain priority in the wrapper. Ambiguous narrative or
    negated intentions require clarification instead of opening a dispute route.
    """
    if re.search(r"\b(?:no|nao)\s+(?:(?:quiero|quero|necesito|preciso|deseo|desejo)\s+)?"
                 r"(?:disputar|contestar|reclamar|abrir|crear|criar|reportar|impugnar)\b", normalized):
        return False
    # Complete short denials are useful before a transaction has been selected;
    # the workflow will still collect details, authorize the record and offer
    # preparation consent separately. The two misspellings are bounded aliases.
    short_denial = (r"(?:yo\s+)?no\s+(?:fui\s+yo|(?:hice|hize|pague|compre|"
                    r"autorice|autorize|realice)\s+(?:esto|eso))"
                    if language == "es" else
                    r"(?:eu\s+)?nao\s+(?:fui\s+eu|(?:fiz|fis|paguei|comprei|"
                    r"autorizei|realizei)\s+(?:isso|isto))")
    if re.fullmatch(r"[\s¡!]*" + short_denial + r"[\s.!¡]*", normalized):
        return True
    # Customers may describe a discrepancy first, then explicitly ask to report
    # it or register a review request. Require both an existing financial-record
    # context and a first-person request at the start of its own clause; quoted,
    # historical or third-party requests cannot establish customer intent.
    financial_context = bool(re.search(r"\b" + _TRANSACTION_NOUN + r"\b", normalized))
    request_prefix = (r"^(?:(?:yo|eu)\s+)?(?:quiero|quisiera|necesito|deseo|quero|"
                      r"queria|preciso|desejo|me\s+gustaria|gostaria\s+de)\s+")
    review_object = (r"(?:ticket|caso|reclamo|reclamacion|reclamacao|contestacion|"
                     r"contestacao|queja|queixa|chamado|protocolo|"
                     r"(?:solicitud|solicitacao|pedido)\s+de\s+(?:revision|revisao|"
                     r"analisis|analise|investigacion|investigacao))")
    for clause in re.split(r"[,;.!?\n]+", normalized):
        clause = clause.strip(" \t\r\n¡¿")
        if financial_context:
            request = re.match(request_prefix, clause)
            if request is not None:
                purpose = clause[request.end():]
                if re.match(r"(?:dejar|registrar|presentar|apresentar|iniciar|abrir|crear|criar|"
                            r"documentar|tramitar)\s+(?:(?:un|una|um|uma|el|la|o|a|"
                            r"mi|meu|minha|nuevo|nueva|novo|nova)\s+){0,2}"
                            + review_object + r"\b", purpose):
                    return True
                if re.fullmatch(r"reportar(?:la|lo)", purpose):
                    return True
                if re.match(r"(?:reportar|comunicar|informar|relatar)\s+"
                            r"(?:(?:un|una|um|uma|el|la|o|a|este|esta|esse|essa)\s+)?"
                            r"(?:problema|error|erro|incidencia|discrepancia|"
                            r"divergencia|reclamo|reclamacion|reclamacao)\b", purpose):
                    return True
        if re.fullmatch(r"(?:(?:yo|eu)\s+)?(?:no\s+(?:lo\s+)?reconozco|"
                        r"nao\s+reconheco|desconozco|desconheco)(?:\s+(?:(?:este|esta|"
                        r"ese|esa|el|la|mi|un|una|esse|essa|o|a|meu|minha|um|uma)\s+)?"
                        + _TRANSACTION_NOUN + r"\b[^.;!?]*)?", clause):
            return True
        if re.search(r"\b" + _TRANSACTION_NOUN + r"\b", clause):
            # A past-action denial differs from declining a future request.
            if re.match(r"^(?:(?:yo|eu)\s+)?(?:no|nao)\s+(?:(?:la|lo|el|a|o)\s+)?"
                        r"(?:hice|hize|pague|compre|autorice|autorize|realice|fiz|fis|"
                        r"paguei|comprei|autorizei|realizei)\b", clause):
                return True
            if re.search(r"\b(?:no\s+es\s+mi[oa]|nao\s+e\s+(?:meu|minha))\b", clause):
                return True
            if re.search(r"\b" + _TRANSACTION_NOUN + r"\s+(?:no\s+reconocid[oa]|"
                         r"nao\s+reconhecid[oa])\b", clause):
                return True
            if not re.search(r"\b(?:no|nao|nunca|ni|nem|sin|sem)\b", clause):
                if re.search(r"\b(?:duplicad[oa]|repetid[oa]|indebid[oa]|"
                             r"dos\s+veces|duas\s+vezes)\b", clause):
                    return True
        # A requested review must name the financial record or support case;
        # generic uses of contestar/reclamar are not financial intent evidence.
        if re.match(r"^(?:(?:quiero|quisiera|necesito|deseo|quero|queria|preciso|"
                    r"desejo|gostaria\s+de)\s+)?(?:disputar|contestar|reclamar|"
                    r"impugnar|reportar|abrir|crear|criar)\b", clause):
            if re.search(r"\b(?:" + _TRANSACTION_NOUN
                         + r"|reclamo|reclamacion|reclamacao|contestacao|caso)\b", clause):
                return True
    return False


@dataclass(frozen=True)
class GuardedPreviewRouter:
    """Live-preview policy around the unchanged, closed-set learned model.

    Deterministic explicit requests take precedence; generic character overlap
    cannot establish a complaint or a request for a person. Indirect, in-scope
    inquiry/unsupported wording still uses the learned classifier. This policy
    includes separately recorded post-exposure engineering repairs; it does not
    establish held-out model performance.
    Model scores remain uncalibrated, and no score threshold is introduced.
    """
    model: CharacterNgramRouter

    @property
    def training_hash(self):
        return self.model.training_hash

    @property
    def training_row_count(self):
        return self.model.training_row_count

    @property
    def vocabulary_size(self):
        return self.model.vocabulary_size

    @property
    def class_counts(self):
        return self.model.class_counts

    @property
    def language_counts(self):
        return self.model.language_counts

    def route_intent(self, text: str, language: str) -> IntentProposal:
        normalized = _request(text, language)
        abstain = IntentProposal("unsupported", 0.0, False)
        if _AFFIRMATION.search(normalized) or is_greeting(text, language):
            return abstain
        baseline = route_intent(text, language)
        if baseline.intent == "unsupported" and baseline.matched:
            return baseline
        if is_explicit_human_request(text, language):
            return IntentProposal("human_request", 1.0, True)
        if _positive_dispute_request(normalized, language):
            return IntentProposal("dispute_intake", 1.0, True)
        if re.search(r"\b(?:no|nao)\s+(?:(?:quiero|quero|necesito|preciso|deseo|desejo)\s+)?"
                     r"(?:ver|consultar|buscar|cotejar|comparar|disputar|contestar|reclamar|abrir|crear|criar|"
                     r"reportar|hablar|falar)\b", normalized):
            return abstain
        if (is_explicit_inquiry(text, language) or is_search_followup(text, language)
                or _positive_read_request(normalized)):
            return IntentProposal("inquiry", 1.0, True)
        if not _BUSINESS_CONTEXT.search(normalized):
            return abstain
        proposal = self.model.route_intent(text, language)
        if proposal.intent in ("dispute_intake", "human_request"):
            return abstain
        return proposal


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
