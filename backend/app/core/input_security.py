"""Canonical identifiers; free text and passwords must retain their exact meaning."""

import re
import unicodedata


def normalize_account(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("account must be a string")  # noqa: TRY004 - Pydantic validators require ValueError.
    value = unicodedata.normalize("NFKC", value).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,99}", value):
        raise ValueError("account must use letters, digits, dot, underscore, @ or hyphen")
    return value


def validate_person_name(value: str) -> str:
    if any(unicodedata.category(char).startswith("C") or char in '<>:/\\"|?*' for char in value):
        raise ValueError("name contains an invisible control or unsafe filename character")
    return value
