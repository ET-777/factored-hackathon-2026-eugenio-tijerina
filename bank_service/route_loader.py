"""Load only fixed authored TRAIN artifacts for experimental local previews."""

from collections import Counter
import json
from pathlib import Path

from bank_service.learned_routing import INTENTS, LANGUAGES, train_router


TRAINING_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "routing_train.json"
SHORT_TRAINING_PATH = TRAINING_PATH.with_name("routing_train_short_v2.json")
MAX_TRAINING_BYTES = 256 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_training_artifact")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("invalid_training_artifact")


def _read_training(path):
    """Read a bounded, unredirected TRAIN artifact with sanitized failures."""
    invalid = ValueError("invalid_training_artifact")
    try:
        # Refuse file/directory links before reading an unintended input.
        if path.resolve() != path.absolute():
            raise invalid
        with path.open("rb") as stream:
            body = stream.read(MAX_TRAINING_BYTES + 1)
        if len(body) > MAX_TRAINING_BYTES:
            raise invalid
        payload = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant)
        if (not isinstance(payload, dict)
                or set(payload) != {"schema_version", "split", "provenance", "review_status", "examples"}
                or type(payload["schema_version"]) is not int or payload["schema_version"] != 1
                or payload["split"] != "train" or payload["provenance"] != "codex_authored"
                or payload["review_status"] != "draft_pending_owner_and_portuguese_review"):
            raise invalid
        return payload["examples"]
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError):
        raise invalid from None


def load_preview_router():
    """The original v1 preview accepts no caller-supplied path or evaluation data."""
    try:
        return train_router(_read_training(TRAINING_PATH))
    except (ValueError, TypeError, RuntimeError):
        raise ValueError("invalid_training_artifact") from None


def load_short_preview_router():
    """Opt in to v2, retaining v1's exact 96 rows and 48 balanced additions."""
    invalid = ValueError("invalid_training_artifact")
    try:
        original = _read_training(TRAINING_PATH)
        candidate = _read_training(SHORT_TRAINING_PATH)
        if (not isinstance(original, list) or len(original) != 96
                or not isinstance(candidate, list) or len(candidate) != 144):
            raise invalid
        # Compare exact row values by identity; ordering is not a training feature.
        originals = {}
        for row in original:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                    or row["id"] in originals):
                raise invalid
            originals[row["id"]] = row
        seen, additions = set(), Counter()
        for row in candidate:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                    or row["id"] in seen):
                raise invalid
            seen.add(row["id"])
            if row["id"] in originals:
                if row != originals[row["id"]]:
                    raise invalid
            else:
                language, intent = row.get("language"), row.get("intent")
                if (not isinstance(language, str) or language not in LANGUAGES
                        or not isinstance(intent, str) or intent not in INTENTS):
                    raise invalid
                additions[language, intent] += 1
        expected = Counter({(language, intent): 6
                            for language in LANGUAGES for intent in INTENTS})
        if not set(originals).issubset(seen) or additions != expected:
            raise invalid
        return train_router(candidate)
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError):
        raise invalid from None
