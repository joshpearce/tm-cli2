"""tm CLI entry point — root Click group with structured error handling."""

from __future__ import annotations

import sys
from typing import Any

import click
from dotenv import load_dotenv

from tm_cli.cli._agent_info import agent_info_command
from tm_cli.cli._errors import TmError, map_exception
from tm_cli.cli._introspection import commands_command, schema_command
from tm_cli.cli.containers import container_group
from tm_cli.cli.diagrams import diagram_group
from tm_cli.cli.documents import document_group
from tm_cli.cli.entities import entity_group
from tm_cli.cli.findings import finding_group
from tm_cli.cli.flows import flow_group
from tm_cli.cli.items import data_item_group
from tm_cli.cli.nodes import node_group
from tm_cli.cli.observations import observation_group
from tm_cli.cli.process_components import process_component_group
from tm_cli.cli.terms import term_group
from tm_cli.cli.threat_catalog import threat_catalog_group
from tm_cli.cli.threats import threat_group

load_dotenv()


class TmGroup(click.Group):
    """Click group that funnels every exception through ``map_exception``.

    Click's ``BaseCommand.main()`` already handles ``ClickException`` subclasses
    (it calls ``.show()`` and exits with ``.exit_code``). We override
    ``invoke`` so exceptions raised inside command callbacks are translated to
    ``TmError`` subclasses, and override ``main`` so parse-time exceptions
    (raised in ``make_context`` BEFORE ``invoke`` runs) get the same
    treatment.
    """

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except TmError:
            raise
        except click.exceptions.Exit:
            raise
        except click.ClickException as e:
            raise map_exception(e) from e
        except Exception as e:
            raise map_exception(e) from e

    def main(
        self,
        args: Any = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        try:
            return super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
        except TmError as e:
            if not standalone_mode:
                raise
            e.show()
            sys.exit(e.exit_code)
        except click.exceptions.Exit as e:
            if not standalone_mode:
                raise
            sys.exit(e.exit_code)
        except click.ClickException as e:
            if not standalone_mode:
                raise map_exception(e) from e
            mapped = map_exception(e)
            mapped.show()
            sys.exit(mapped.exit_code)
        except Exception as e:
            if not standalone_mode:
                raise map_exception(e) from e
            mapped = map_exception(e)
            mapped.show()
            sys.exit(mapped.exit_code)


def _default_json_mode() -> bool:
    """Default ``--json`` value: True when stdout is piped, False on a TTY."""
    return not sys.stdout.isatty()


@click.group(cls=TmGroup)
@click.option(
    "--json/--no-json",
    "json_mode",
    default=_default_json_mode,
    show_default="auto-detected from TTY",
    help="Force JSON-mode output (default: detected from stdout TTY).",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose logging.")
@click.option(
    "--id-only",
    "id_only",
    is_flag=True,
    default=False,
    help=(
        "Emit only entity ids on stdout (one id per line). "
        "Single-row payloads print the row's id (or, for payloads without a bare 'id' "
        "field such as 'tm diagram push', the first '*_id'-suffixed field). "
        "List output drops the _pagination footer. "
        "Wins over --json when both are set. Falls back to JSON when no id-bearing "
        "field is present (e.g., tm schema). "
        "Note: idempotent commands (e.g., `delete`) emit the requested id even "
        "when the row didn't exist; check exit codes / non-id-only output "
        "when distinguishing."
    ),
)
@click.pass_context
def cli(ctx: click.Context, json_mode: bool, verbose: bool, id_only: bool) -> None:
    """tm — agent-first threat-model database CLI."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode
    ctx.obj["verbose"] = verbose
    ctx.obj["id_only"] = id_only


cli.add_command(diagram_group)
cli.add_command(document_group)
cli.add_command(entity_group)
cli.add_command(finding_group)
cli.add_command(term_group)
cli.add_command(observation_group)
cli.add_command(data_item_group)
cli.add_command(node_group)
cli.add_command(container_group)
cli.add_command(flow_group)
cli.add_command(process_component_group)
cli.add_command(threat_catalog_group)
cli.add_command(threat_group)
cli.add_command(schema_command)
cli.add_command(commands_command)
cli.add_command(agent_info_command)
