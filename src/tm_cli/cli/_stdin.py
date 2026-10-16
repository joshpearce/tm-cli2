"""Read JSON from stdin for ``--stdin`` bulk operations."""

from __future__ import annotations

import json
import sys
from typing import Any

import click


def enforce_stdin_exclusive(stdin: bool, named_values: dict[str, object]) -> None:
    """Raise ``click.UsageError`` when ``--stdin`` is combined with named flags.

    ``named_values`` maps each named-flag's destination name to its value as Click
    parsed it. A flag is "set" if its value is not ``None`` and not the literal
    Click default for that flag (the caller passes only the flags that are not at
    their default — see ``documents.py`` for the convention).
    """

    if not stdin:
        return
    set_flags = [name for name, value in named_values.items() if value is not None]
    if set_flags:
        names = ", ".join(f"--{name.replace('_', '-')}" for name in set_flags)
        raise click.UsageError(f"--stdin cannot be combined with named flags: {names}")


def read_json_stdin() -> dict[str, Any] | list[dict[str, Any]]:
    """Read and parse JSON from stdin.

    Returns either a single object (for a single mutation) or a list of objects
    (for batch mode). Raises ``ValueError`` on empty input, malformed JSON, or
    a top-level type that isn't object or array-of-objects.
    """

    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("No JSON input received on stdin.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON on stdin: {e}") from e

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("Stdin JSON array must contain only objects.")
        return parsed
    raise ValueError("Stdin JSON must be an object or an array of objects.")
