"""Exact transaction references for the server-owned, bounded record snapshot.

Repository-derived recognition must receive only authorized identifiers. It is
not authorization: callers must still use get_transaction or Conversation.inquire.
Native identity spelling, ownership and records are never
rewritten. This helper supplies no facts or permissions to a learned model.
"""
from dataclasses import dataclass, replace
from datetime import date
import re
import unicodedata

from bank_service.access import AccessDenied
from bank_service.routing import RoutingError, _checked_text, extract_slots


_NATIVE_ID = re.compile(r"(?<![\w-])TRX[-_][A-Za-z0-9][A-Za-z0-9_-]*(?![\w-])", re.IGNORECASE)
_LEGACY_ID = re.compile(
    r"(?<![\w-])(?:[A-Za-z0-9]+-TX-[A-Za-z0-9_-]+|TX[-_][A-Za-z0-9_-]+)(?![\w-])",
    re.IGNORECASE,
)
_LABELED_ID = re.compile(
    r"(?<![\w-])(?:transacci[oó]n|transa[çc][aã]o|transaction|tx|id)"
    r"\s*(?:id\s*)?[:#]?\s+[\"']?([A-Za-z0-9][A-Za-z0-9_-]{2,63})(?![\w-])",
    re.IGNORECASE,
)
_CORE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}")
_LABEL_ONLY = re.compile(
    r"\s*(?:(?:id|tx|transacci[oó]n|transa[çc][aã]o|transaction|refer[eê]ncia|referencia)"
    r"\s*(?:id\s*)?[:#]?\s*)?[.!?¿¡]*\s*", re.IGNORECASE)


@dataclass(frozen=True)
class TransactionReference:
    transaction_id: str | None
    masked_text: str
    slot_only: bool


def _core(identifier):
    if len(identifier) >= 2 and identifier[0] == identifier[-1] and identifier[0] in {'"', "'"}:
        return identifier[1:-1]
    return identifier


def _canonical(token):
    return token.upper() if token.upper().startswith("DEMO-TX-") else token


def _whole_identifier(text, start, end):
    # Python's \w excludes combining marks. Those still belong to the adjacent
    # spelling and cannot authorize a partial ASCII ID.
    return all(character not in "_-" and unicodedata.category(character)[0] not in "LNM"
               for character in (text[start - 1:start] if start else "") + text[end:end + 1])


def parse_transaction_reference(text, language, record_ids):
    """Find bounded ASCII references, rejecting ambiguity before navigation.

    Balanced outer quotes are a typing convention. They can also be literal
    source characters: resolve a unique authorized core to its exact stored key,
    and reject collisions within the supplied authorized scope. Independently
    recognized unknown references reach the normal generic access denial.
    Native IDs are case exact; only legacy DEMO-TX compatibility
    uses the existing uppercase convention.
    """
    _checked_text(text, language)
    checked = text  # Validate the request without normalizing identity spelling.
    if not isinstance(record_ids, (dict, tuple, list)) and not hasattr(record_ids, "keys"):
        raise RoutingError("invalid_repository")
    keys = list(record_ids)
    if any(not isinstance(key, str) for key in keys):
        raise RoutingError("invalid_repository")
    cores = {}
    for key in keys:
        core = _core(key)
        if _CORE_ID.fullmatch(core):
            cores.setdefault(core, set()).add(key)
    spans = {}
    for pattern in (_LEGACY_ID, _NATIVE_ID):
        for match in pattern.finditer(checked):
            if _whole_identifier(checked, *match.span()):
                spans[match.span()] = match.group()
    for match in _LABELED_ID.finditer(checked):
        token = match.group(1)
        if (any(c.isdigit() for c in token) and any(c.isalpha() for c in token)
                and not token.upper().startswith(("CUSTOMER", "CUST-", "CLIENTE", "PRODUCT", "PROD-"))
                and _whole_identifier(checked, *match.span(1))):
            spans[match.span(1)] = token
    # Exact known IDs support other native spellings. No fuzzy matching or
    # merchant/amount search is involved; foreign IDs still require authorization.
    for core in cores:
        pattern = re.compile(r"(?<![\w-])" + re.escape(core) + r"(?![\w-])")
        for match in pattern.finditer(checked):
            if _whole_identifier(checked, *match.span()):
                spans[match.span()] = match.group()
    identities = set()
    masked = list(checked)
    for (start, end), token in sorted(spans.items()):
        if len(token) > 64:
            raise RoutingError("invalid_transaction_id")
        # Prefix/suffix matches inside a longer recognized reference are not a
        # second ID. Token boundaries already exclude ordinary concatenation.
        if any(a <= start and end <= b and (a, b) != (start, end) for a, b in spans):
            continue
        before = checked[start - 1] if start else None
        after = checked[end] if end < len(checked) else None
        if before in {'"', "'"} or after in {'"', "'"}:
            if before != after:
                raise RoutingError("invalid_transaction_id")
            start, end = start - 1, end + 1
        canonical = _canonical(token)
        candidates = cores.get(canonical, set())
        if len(candidates) > 1:
            # Repository alias existence must not be distinguished from an
            # inaccessible/missing reference, especially for foreign records.
            raise AccessDenied("Access denied")
        identities.add(next(iter(candidates)) if candidates else canonical)
        masked[start:end] = " " * (end - start)
    if len(identities) > 1:
        raise RoutingError("ambiguous_transaction_id")
    identifier = next(iter(identities)) if identities else None
    remaining = "".join(masked)
    slot_only = identifier is not None and _LABEL_ONLY.fullmatch(remaining) is not None
    return TransactionReference(identifier, remaining, slot_only)


def extract_record_slots(text, language, record_ids, *, reference_date: date):
    """Parse ordinary slots with reference spans masked, preserving native IDs."""
    reference = parse_transaction_reference(text, language, record_ids)
    # extract_slots rejects a wholly empty request. An innocuous literal cannot
    # become a date, currency, amount or transaction reference.
    other = reference.masked_text if reference.masked_text.strip() else "detalle"
    slots = extract_slots(other, language, reference_date=reference_date)
    # The legacy slot extractor normalizes accents for ordinary language. It
    # must never invent or normalize an identity that this exact parser rejected.
    return replace(slots, transaction_id=reference.transaction_id)
