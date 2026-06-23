from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


ONLY_DIGITS_RE = re.compile(r"\D+")
WHITESPACE_RE = re.compile(r"\s+")


def only_digits(value: object | None) -> str | None:
    """Return only numeric characters from a value."""
    if value is None:
        return None
    digits = ONLY_DIGITS_RE.sub("", str(value))
    return digits or None


def normalize_cpf(value: object | None) -> str | None:
    """Normalize CPF to 11 digits, left-padding short numeric values."""
    digits = only_digits(value)
    if not digits:
        return None
    return digits.zfill(11)[-11:]


def normalize_cnpj(value: object | None) -> str | None:
    """Normalize CNPJ to 14 digits, left-padding short numeric values."""
    digits = only_digits(value)
    if not digits:
        return None
    return digits.zfill(14)[-14:]


def normalize_document(value: object | None) -> str | None:
    """Normalize CPF or CNPJ based on the amount of digits present."""
    digits = only_digits(value)
    if not digits:
        return None
    if len(digits) <= 11:
        return normalize_cpf(digits)
    return normalize_cnpj(digits)


def normalize_name(value: object | None) -> str | None:
    """Normalize names for cross-source matching."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = WHITESPACE_RE.sub(" ", text.upper()).strip()
    return text or None


def decimal_from_brl(value: object | None) -> Decimal | None:
    """Parse Brazilian decimal strings without converting through float."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None
