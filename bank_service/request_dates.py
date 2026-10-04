"""Deterministic Spanish/Portuguese calendar dates for customer requests.

Numeric local dates are day first (DD/MM/YYYY or DD-MM-YYYY); ISO dates
retain their exact YYYY-MM-DD width. Month-name dates and DD/MM replies
may omit the year, in which case the caller supplies the trusted reference
date. Relative dates, year-only requests and month-only requests are outside
this small grammar. This module does not use the clock or a language model.
"""

from dataclasses import dataclass
from datetime import date
import re
import unicodedata


class DateParsingError(ValueError):
    """Only fixed invalid_date/ambiguous_date codes; no customer text."""


@dataclass(frozen=True)
class DateInterpretation:
    value: date | None
    assumed_year: bool = False


_MONTHS = {
    "es": {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    },
    "pt": {
        "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    },
}
_NUMERIC = re.compile(
    r"(?<![\w./-])[+-]?[0-9]+(?:[-/][0-9]+){1,3}(?![\w/-]|\.(?=[0-9]))"
)
_MONTH_PATTERNS = {}
for _language, _months in _MONTHS.items():
    _month_words = "(?:" + "|".join(sorted(_months, key=len, reverse=True)) + ")"
    _MONTH_PATTERNS[_language] = (
        re.compile(
            r"(?<![\w./-])(?P<day>[0-9]+)\s+(?:de\s+)?"
            r"(?P<month>" + _month_words + r")(?![\w/-])"
        ),
        re.compile(
            r"(?<![\w/-])(?P<month>" + _month_words + r")\s+"
            r"(?P<day>[0-9]+)(?![\w/-]|\.(?=[0-9]))"
        ),
    )
# A decimal value following a month name belongs to the amount parser. Plain
# year-like integer suffixes are captured even when malformed, so they produce
# a date clarification rather than silently becoming a current-year date.
_YEAR_SUFFIX = re.compile(
    r"\s*,?\s*(?:(?P<connector>de|del|do)\s+)?"
    r"(?P<year>[+-]?[0-9]+)(?![\w/-]|[.,](?=[0-9]))"
)
_YEAR_CONNECTOR = re.compile(r"\s*,?\s*(?:de|del|do)(?=\b|[0-9+-])\s*")
_SUFFIX_TOKEN = re.compile(r"\s*,?\s*(?P<token>[^\s]+)")
_VALID_YEAR_TOKEN = re.compile(r"[0-9]{4}[.!?,;:)\]]*")
_YEAR_LIKE_TOKEN = re.compile(r"[+-]?[0-9]{4}")
_CURRENCY_AFTER = re.compile(
    r"\s*(?:USD|COP|ARS|MXN|BRL|EUR|GBP|PEN|CLP|UYU|BOB|PYG|VES|CRC|"
    r"GTQ|HNL|NIO|DOP|CAD|JPY|CHF|dolares?|dollars?|pesos?)\b",
    re.IGNORECASE,
)
_REPLY_PREFIX = re.compile(
    r"^(?:(?:el|la|a|o|del|de|en|em|fue|foi)\s+)*"
    r"(?:(?:fecha|data)\s*(?:(?:es|e|fue|foi)\s+|[:=]\s*)?)?"
)


@dataclass(frozen=True)
class _DateMatch:
    start: int
    end: int
    raw: str
    day: str | None = None
    month: int | None = None
    year: str | None = None


def _normalize(text: str, language: str) -> str:
    if not isinstance(text, str) or not isinstance(language, str) or language not in _MONTHS:
        raise DateParsingError("invalid_date")
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        character for character in unicodedata.normalize("NFD", normalized)
        if not unicodedata.combining(character)
    ).casefold()


def _find_dates(text: str, language: str) -> list[_DateMatch]:
    found = [_DateMatch(match.start(), match.end(), match.group(0))
             for match in _NUMERIC.finditer(text)]
    for pattern in _MONTH_PATTERNS[language]:
        for match in pattern.finditer(text):
            end = match.end()
            year = None
            suffix = _YEAR_SUFFIX.match(text, end)
            connector = _YEAR_CONNECTOR.match(text, end)
            token = _SUFFIX_TOKEN.match(text, connector.end() if connector else end)
            # A visible year marker or a four-digit year-like token is an
            # explicit attempt. Do not silently fall back to the current year
            # when it is dangling, contains letters, or is a decimal value.
            # The full invalid token remains a recognized date reply so the
            # caller can clarify it before asking an intent model.
            invalid_suffix = (
                connector is not None
                and (suffix is None or token is None
                     or _VALID_YEAR_TOKEN.fullmatch(token.group("token")) is None)
            ) or (
                connector is None and token is not None
                and _YEAR_LIKE_TOKEN.match(token.group("token")) is not None
                and _VALID_YEAR_TOKEN.fullmatch(token.group("token")) is None
            )
            if invalid_suffix:
                year = "invalid"
                end = token.end() if token else connector.end()
                found.append(_DateMatch(
                    match.start(), end, text[match.start():end],
                    match.group("day"), _MONTHS[language][match.group("month")], year,
                ))
                continue
            if suffix:
                candidate = suffix.group("year")
                # "3 de mayo, 25 USD" is an omitted-year date plus an amount.
                # An explicit connector or a four-digit token denotes a year.
                amount_follows = (
                    not suffix.group("connector")
                    and len(candidate) != 4
                    and _CURRENCY_AFTER.match(text, suffix.end()) is not None
                )
                if not amount_follows:
                    year = candidate
                    end = suffix.end()
            found.append(_DateMatch(
                match.start(), end, text[match.start():end],
                match.group("day"), _MONTHS[language][match.group("month")], year,
            ))
    found.sort(key=lambda match: (match.start, -match.end))
    # Month-name patterns cannot overlap each other on the accepted grammar;
    # conservatively retain the longest match if a numeric candidate overlaps.
    disjoint = []
    for match in found:
        if not disjoint or match.start >= disjoint[-1].end:
            disjoint.append(match)
    return disjoint


def _validated_value(match: _DateMatch, reference_date: date) -> tuple[date, bool]:
    if match.month is not None:
        if not re.fullmatch(r"[0-9]{1,2}", match.day or ""):
            raise DateParsingError("invalid_date")
        if match.year is not None and not re.fullmatch(r"[0-9]{4}", match.year):
            raise DateParsingError("invalid_date")
        year = int(match.year) if match.year is not None else reference_date.year
        month = match.month
        day = int(match.day)
        assumed = match.year is None
    else:
        parts = re.split(r"[-/]", match.raw)
        separators = re.findall(r"[-/]", match.raw)
        if len(set(separators)) != 1:
            raise DateParsingError("invalid_date")
        if len(parts) == 3 and len(parts[0]) >= 3:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", match.raw):
                raise DateParsingError("invalid_date")
            year, month, day = map(int, parts)
            assumed = False
        elif len(parts) in (2, 3):
            if any(len(part) != 2 for part in parts[:2]):
                raise DateParsingError("invalid_date")
            if len(parts) == 3 and len(parts[2]) != 4:
                raise DateParsingError("invalid_date")
            day, month = map(int, parts[:2])
            year = int(parts[2]) if len(parts) == 3 else reference_date.year
            assumed = len(parts) == 2
        else:
            raise DateParsingError("invalid_date")
    try:
        return date(year, month, day), assumed
    except ValueError:
        raise DateParsingError("invalid_date") from None


def extract_request_date(
    text: str, language: str, *, reference_date: date,
) -> DateInterpretation:
    """Extract one calendar date; duplicate references to the same day are okay.

    Every recognized date is validated before ambiguity is checked. Missing
    years use exactly ``reference_date.year``; datetime values are rejected.
    """
    if type(reference_date) is not date:
        raise DateParsingError("invalid_date")
    normalized = _normalize(text, language)
    values = set()
    assumed_year = False
    for match in _find_dates(normalized, language):
        value, assumed = _validated_value(match, reference_date)
        values.add(value)
        assumed_year = assumed_year or assumed
    if len(values) > 1:
        raise DateParsingError("ambiguous_date")
    return DateInterpretation(next(iter(values)) if values else None, assumed_year)


def is_date_reply(text: str, language: str) -> bool:
    """Whether a complete reply is one date expression, even if invalid.

    This recognition is independent of the current year and deliberately does
    not classify business requests containing dates as standalone date replies.
    """
    normalized = _normalize(text, language).strip()
    normalized = _REPLY_PREFIX.sub("", normalized, count=1).strip()
    found = _find_dates(normalized, language)
    return (
        len(found) == 1 and found[0].start == 0
        and not normalized[found[0].end:].strip(" \t\r\n.!?,;¿?¡")
    )


def mask_request_dates(text: str, language: str) -> str:
    """Accentfold/casefold text and blank date spans before extracting amounts.

    Positions refer to this normalized output, not the original string. Dates
    are recognized but not validated here; extraction performs validation.
    """
    normalized = _normalize(text, language)
    characters = list(normalized)
    for match in _find_dates(normalized, language):
        characters[match.start:match.end] = " " * (match.end - match.start)
    return "".join(characters)
