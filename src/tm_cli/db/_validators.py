"""Shared field validators for Pydantic models."""

from __future__ import annotations

import re

KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

MAX_NAME_LENGTH = 128


def validate_kebab_case(value: str) -> str:
    """Validate that *value* is lower-kebab-case (e.g. ``my-threat-model``).

    Rules:
    - Starts with a lowercase ASCII letter.
    - Subsequent segments separated by single hyphens.
    - Each segment contains only lowercase ASCII letters and digits.
    - Maximum length of 128 characters.

    Raises ``ValueError`` with a human-friendly message on mismatch,
    which Pydantic surfaces as a ``ValidationError``.
    """
    if len(value) > MAX_NAME_LENGTH:
        msg = (
            f"Name is too long ({len(value)} chars). "
            f"Maximum length is {MAX_NAME_LENGTH} characters."
        )
        raise ValueError(msg)
    if not KEBAB_CASE_RE.match(value):
        msg = (
            f"Name must be lower-kebab-case (e.g. 'my-threat-model'), "
            f"got {value!r}."
        )
        raise ValueError(msg)
    return value
