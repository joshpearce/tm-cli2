"""Error mapping and structured JSON exit for the tm CLI.

All exceptions raised inside command callbacks (and during Click's parsing)
flow through ``map_exception`` to produce a stable exit code and a JSON
payload on stderr. ``TmError`` and its subclasses are ``click.ClickException``
subclasses so Click's existing dispatch (``BaseCommand.main`` → ``exception.show()`` →
``sys.exit(exception.exit_code)``) does the right thing automatically.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from typing import IO, Any, ClassVar

import click
from pydantic import ValidationError

_UNIQUE_RE = re.compile(r"^UNIQUE constraint failed", re.IGNORECASE)
_FK_RE = re.compile(r"^FOREIGN KEY constraint failed", re.IGNORECASE)
_CHECK_RE = re.compile(r"^CHECK constraint failed", re.IGNORECASE)


class TmError(click.ClickException):
    """Base class for all CLI-mapped errors."""

    exit_code: ClassVar[int] = 1
    code: ClassVar[str] = "user_error"

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        input_payload: Any = None,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.hint = hint
        self.input_payload = input_payload
        self.extra: dict[str, Any] = extra

    def to_payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint is not None:
            body["hint"] = self.hint
        if self.input_payload is not None:
            body["input"] = self.input_payload
        body.update(self.extra)
        return {"error": body}

    def show(self, file: IO[str] | None = None) -> None:  # type: ignore[override]
        target = file if file is not None else sys.stderr
        json.dump(self.to_payload(), target, default=str)
        target.write("\n")


class UserError(TmError):
    exit_code: ClassVar[int] = 1
    code: ClassVar[str] = "user_error"


class NotFoundError(TmError):
    exit_code: ClassVar[int] = 2
    code: ClassVar[str] = "not_found"


class ConstraintError(TmError):
    exit_code: ClassVar[int] = 3
    code: ClassVar[str] = "constraint_violation"


class SystemError(TmError):  # noqa: A001  # CLI-internal type, shadows builtin intentionally
    exit_code: ClassVar[int] = 4
    code: ClassVar[str] = "system_error"


def _classify_integrity(msg: str) -> str:
    if _UNIQUE_RE.match(msg):
        return "unique"
    if _FK_RE.match(msg):
        return "foreign_key"
    if _CHECK_RE.match(msg):
        return "check"
    return "unknown"


def map_exception(exc: BaseException, *, input_payload: Any = None) -> TmError:
    """Translate ``exc`` into the appropriate ``TmError`` subclass.

    Already-mapped ``TmError`` instances are returned unchanged so callers can
    re-raise from inside command code without double-wrapping.
    """

    if isinstance(exc, TmError):
        return exc

    if isinstance(exc, ValidationError):
        return UserError(str(exc), input_payload=input_payload)

    if isinstance(exc, sqlite3.IntegrityError):
        return ConstraintError(
            str(exc),
            input_payload=input_payload,
            constraint=_classify_integrity(str(exc)),
        )

    if isinstance(exc, ValueError):
        return UserError(str(exc), input_payload=input_payload)

    if isinstance(exc, click.UsageError):
        return UserError(exc.format_message(), input_payload=input_payload)

    if isinstance(exc, click.ClickException):
        return UserError(exc.format_message(), input_payload=input_payload)

    if isinstance(exc, (PermissionError, OSError)):
        return SystemError(str(exc), input_payload=input_payload)

    return SystemError(f"{type(exc).__name__}: {exc}", input_payload=input_payload)
