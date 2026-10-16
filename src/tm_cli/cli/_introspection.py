"""Introspection commands: tm schema and tm commands --json."""

from __future__ import annotations

import json
from typing import Any

import click
from pydantic import BaseModel, TypeAdapter

from tm_cli.cli._output import emit
from tm_cli.db import (
    Container,
    ContainerCreate,
    ContainerUpdate,
    DataFlow,
    DataFlowCreate,
    DataFlowUpdate,
    DataItem,
    DataItemCreate,
    DataItemUpdate,
    Diagram,
    DiagramCreate,
    DiagramUpdate,
    Document,
    DocumentCreate,
    DocumentSummary,
    DocumentUpdate,
    Node,
    NodeCreate,
    NodeUpdate,
    Observation,
    ObservationCreate,
    ObservationUpdate,
    Term,
    TermCreate,
    TermUpdate,
)


def _schema_for(model: Any) -> dict[str, Any]:
    """Return JSON Schema for a Pydantic model class OR a typing union (TypeAdapter)."""
    if isinstance(model, type) and issubclass(model, BaseModel):
        return model.model_json_schema()
    return TypeAdapter(model).json_schema()


_REGISTRY: dict[str, dict[str, Any]] = {
    "document": {
        "read": Document,
        "create": DocumentCreate,
        "update": DocumentUpdate,
        "summary": DocumentSummary,
    },
    "term": {"read": Term, "create": TermCreate, "update": TermUpdate},
    "observation": {
        "read": Observation,
        "create": ObservationCreate,
        "update": ObservationUpdate,
    },
    "diagram": {"read": Diagram, "create": DiagramCreate, "update": DiagramUpdate},
    "node": {"read": Node, "create": NodeCreate, "update": NodeUpdate},
    "container": {
        "read": Container,
        "create": ContainerCreate,
        "update": ContainerUpdate,
    },
    "flow": {"read": DataFlow, "create": DataFlowCreate, "update": DataFlowUpdate},
    "data-item": {
        "read": DataItem,
        "create": DataItemCreate,
        "update": DataItemUpdate,
    },
}


def _entity_schema(name: str) -> dict[str, Any]:
    triple = _REGISTRY[name]
    return {kind: _schema_for(model) for kind, model in triple.items()}


@click.command(name="schema")
@click.argument("entity", required=False)
@click.option(
    "--all",
    "all_entities",
    is_flag=True,
    default=False,
    help="Return schemas for every known entity, keyed by name.",
)
@click.pass_context
def schema_command(ctx, entity: str | None, *, all_entities: bool) -> None:
    """Pydantic JSON Schema for read + Create + Update models.

    With no argument, lists available entity names.
    """
    if all_entities:
        emit(ctx, {name: _entity_schema(name) for name in _REGISTRY})
        return
    if entity is None:
        emit(ctx, {"entities": list(_REGISTRY)})
        return
    if entity not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise click.UsageError(f"Unknown entity: {entity!r}. Known entities: {known}")
    emit(ctx, _entity_schema(entity))


def _serialize_param(p: click.Parameter) -> dict[str, Any]:
    """Serialize a Click ``Option`` or ``Argument`` for tm commands --json output."""
    type_name = type(p.type).__name__ if p.type else None
    serialized: dict[str, Any] = {
        "name": p.name,
        "type": type_name,
        "required": bool(p.required),
    }
    if isinstance(p, click.Option):
        serialized["opts"] = list(p.opts)
        serialized["secondary_opts"] = list(p.secondary_opts)
        serialized["is_flag"] = bool(p.is_flag)
        serialized["hidden"] = bool(p.hidden)
        serialized["multiple"] = bool(p.multiple)
        # Skip Click Sentinel values (UNSET, etc.) for JSON serialization
        if p.default is not None and not callable(p.default):
            try:
                json.dumps(p.default)  # Check if it's JSON serializable
                serialized["default"] = p.default
            except (TypeError, ValueError):
                serialized["default"] = None
        else:
            serialized["default"] = None
        serialized["help"] = p.help
        # Add choices if this option has a Choice type
        if isinstance(p.type, click.Choice):
            serialized["choices"] = list(p.type.choices)
    return serialized


def _serialize_command(cmd: click.Command, name: str | None = None) -> dict[str, Any]:
    """Recursively serialize a Click Command (may be a Group) to JSON dict."""
    options = [_serialize_param(p) for p in cmd.params if isinstance(p, click.Option)]
    arguments = [
        _serialize_param(p) for p in cmd.params if isinstance(p, click.Argument)
    ]
    out: dict[str, Any] = {
        "name": name or cmd.name,
        "description": (cmd.help or cmd.short_help or "").strip(),
        "options": options,
        "arguments": arguments,
    }
    if isinstance(cmd, click.Group):
        out["subcommands"] = [
            _serialize_command(sub, sub_name)
            for sub_name, sub in sorted(cmd.commands.items())
        ]
    return out


@click.command(name="commands")
@click.pass_context
def commands_command(ctx) -> None:
    """Walk the full command tree and emit a stable JSON document.

    The top-level --json/--no-json flag controls output format (JSON by default).

    Hidden options are included with ``"hidden": true`` so curious agents can
    discover them programmatically.
    """
    from tm_cli.main import cli  # local import to avoid circular import at module load

    tree = _serialize_command(cli, name="tm")
    emit(ctx, tree)
