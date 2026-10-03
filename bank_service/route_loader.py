"""Load only the fixed authored TRAIN artifact for an experimental local preview."""

import json
from pathlib import Path

from bank_service.learned_routing import train_router


TRAINING_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "routing_train.json"
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


def load_preview_router():
    """No browser path, development input or final evaluation file is accepted."""
    invalid = ValueError("invalid_training_artifact")
    try:
        # Refuse file/directory links before reading an unintended input.
        if TRAINING_PATH.resolve() != TRAINING_PATH.absolute():
            raise invalid
        with TRAINING_PATH.open("rb") as stream:
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
        return train_router(payload["examples"])
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError):
        raise invalid from None
