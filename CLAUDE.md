# tm-cli

Last verified: 2026-05-06

## Tech Stack
- Language: Python 3.11+
- CLI framework: Click 8.x
- Persistence: stdlib `sqlite3` + Pydantic v2
- Config loading: python-dotenv (CLI entrypoint loads `.env` at import)
- Build backend: Hatchling
- Package manager: poetry
- Linter/formatter: Ruff
- Testing: pytest + Syrupy (snapshot tests)

## Commands
- `make install-deps` - Install all dependencies into a poetry-managed virtualenv (`poetry install`)
- `make lint` - Run ruff check and format check
- `make test` - Run pytest

## Configuration
- `TM_DB_PATH` (required) - Path to the SQLite database file. Set in `.env` for local dev.
- `DFD_EDITOR_URL` (optional) - Base URL of the dfd_editor server (e.g. `http://localhost:5050`). Used by `tm diagram push`; can also be passed as `--server` at runtime.
- `TM_DIAGRAM_ID` (optional) - Default diagram id for all DFD entity commands (`node`, `container`, `flow`, `data-item`). Overridden by an explicit `--diagram-id` on any command; falls back to a `default`-named diagram scan when unset.
- `.env.example` is committed as the template; `.env` is gitignored.

## Project Structure
- `src/tm_cli/` - Application source (installed as `tm-cli` package)
- `src/tm_cli/main.py` - Click CLI entry point. Defines the `TmGroup` class that funnels parse-time and runtime exceptions through `cli._errors.map_exception`. Calls `load_dotenv()` at import.
- `src/tm_cli/cli/` - Click command modules (one per entity) + shared option/output/error/stdin helpers and introspection. See `src/tm_cli/cli/CLAUDE.md`.
- `src/tm_cli/db/` - SQLite + Pydantic data layer. See `src/tm_cli/db/CLAUDE.md`.
- `tests/cli/` - Click command unit tests (CliRunner + Syrupy snapshots).
- `tests/acceptance/` - End-to-end agent workflow tests that drive the CLI from Python.
- `tests/fixtures/` - Deterministic seed data (`seed.py` → `SeedIds`) and Syrupy masking extension. Fixtures are exposed via `tests/conftest.py` (`db_path`, `db_with_seed`, masked `snapshot`).

## Conventions
- `src/` layout: source lives under `src/tm_cli/`, not at the root, to prevent accidental uninstalled imports
- All dev dependencies (`ruff`, `pytest`, `syrupy`) live in the `[dependency-groups] dev` section of `pyproject.toml`
- The installed CLI command is `tm` (defined in `[project.scripts]`)
- poetry manages the virtualenv; always use `poetry run <tool>` or activate the env (`poetry shell`) before running tools directly
- `poetry.lock` is committed and authoritative; it is locked against public PyPI with no per-package source pins
- All datetimes are timezone-aware UTC (`datetime.now(UTC)`)
- Snapshot tests mask ids and ISO datetimes via `tests/fixtures/syrupy_ext.py` so snapshots are stable across reruns

## Boundaries
- Safe to edit: `src/`, `tests/`, `pyproject.toml`, `Makefile`, `.env.example`
- Never commit: `.venv/`, `.env`, `__pycache__/`, `*.egg-info/`, `dist/`
