"""Shared LIKE-based search helpers for repositories.

`search()` methods on each repository use these to convert a free-text
query into a SQL fragment. Tokens are whitespace-split and AND'd; each
token must match (case-insensitively) some searchable text column.
"""

from __future__ import annotations


def _tokenize(text: str) -> list[str]:
    return text.split()


def _escape_like_token(token: str) -> str:
    # Order matters: escape backslash first so we don't double-escape the
    # backslashes we introduce for % and _.
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_text_clause(
    text: str,
    columns: tuple[str, ...],
) -> tuple[str, list[object]]:
    """Build a parenthesised AND-of-OR LIKE clause for `text` over `columns`.

    Each token in `text` becomes one clause: any one of the columns may match
    that token (OR); all tokens must match somewhere (AND). Comparison is
    case-insensitive (LOWER on both sides) and `%`/`_` in the user input are
    escaped so they match literally. Backslash is the explicit ESCAPE char.

    Returns ("", []) for empty/whitespace-only input — the caller should skip
    appending to its WHERE clause in that case.
    """
    if not columns:
        raise ValueError("at least one searchable column is required")

    tokens = _tokenize(text)
    if not tokens:
        return "", []

    fragments: list[str] = []
    params: list[object] = []
    column_or = " OR ".join(f"LOWER({col}) LIKE ? ESCAPE '\\'" for col in columns)
    for token in tokens:
        pattern = f"%{_escape_like_token(token).lower()}%"
        fragments.append(f"({column_or})")
        params.extend([pattern] * len(columns))
    return "(" + " AND ".join(fragments) + ")", params
