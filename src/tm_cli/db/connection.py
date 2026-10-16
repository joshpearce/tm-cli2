# pattern: Imperative Shell
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("datetime", lambda b: datetime.fromisoformat(b.decode()))

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY,
    last_updated  TEXT NOT NULL,
    last_imported TEXT NOT NULL,
    title         TEXT NOT NULL,
    author        TEXT NOT NULL,
    content       TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS terms (
    id           INTEGER PRIMARY KEY,
    term         TEXT NOT NULL UNIQUE,
    definition   TEXT NOT NULL,
    last_updated TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS document_terms (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    term_id     INTEGER NOT NULL REFERENCES terms(id)     ON DELETE CASCADE,
    PRIMARY KEY (document_id, term_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_document_terms_term_id
    ON document_terms(term_id);

CREATE TABLE IF NOT EXISTS observations (
    id               INTEGER PRIMARY KEY,
    content          TEXT NOT NULL,
    observation_type TEXT NOT NULL CHECK (observation_type IN (
        'potential_threat',
        'incomplete_information',
        'question',
        'todo'
    )),
    status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
        'open',
        'closed'
    )),
    last_updated     TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS diagram (
    id                      INTEGER PRIMARY KEY,
    name                    TEXT,
    description             TEXT,
    author                  TEXT,
    created                 TEXT NOT NULL,
    dfd_editor_diagram_id   TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS entity (
    id          INTEGER PRIMARY KEY,
    diagram_id  INTEGER NOT NULL REFERENCES diagram(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN (
        'node', 'container', 'data_flow', 'data_item', 'process_component'
    ))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_entity_diagram_id ON entity(diagram_id);

CREATE TABLE IF NOT EXISTS node (
    id                    INTEGER PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
    type                  TEXT NOT NULL CHECK (type IN (
        'process', 'external_entity', 'data_store'
    )),
    name                  TEXT NOT NULL,
    description           TEXT NOT NULL,
    trust_level           TEXT CHECK (trust_level IS NULL OR trust_level IN (
        'public', 'authenticated', 'admin', 'system'
    )),
    assumptions           TEXT CHECK (assumptions IS NULL OR json_valid(assumptions)),
    entity_type           TEXT CHECK (entity_type IS NULL OR entity_type IN (
        'user', 'service', 'system', 'device'
    )),
    out_of_scope          INTEGER
        CHECK (out_of_scope IS NULL OR out_of_scope IN (0, 1)),
    storage_type          TEXT CHECK (storage_type IS NULL OR storage_type IN (
        'database', 'cache', 'file', 'queue', 'bucket'
    )),
    contains_pii          INTEGER
        CHECK (contains_pii IS NULL OR contains_pii IN (0, 1)),
    encryption_at_rest    INTEGER
        CHECK (encryption_at_rest IS NULL OR encryption_at_rest IN (0, 1)),
    CHECK (
        (type = 'process'
            AND trust_level IS NOT NULL AND assumptions IS NOT NULL
            AND entity_type IS NULL AND out_of_scope IS NULL
            AND storage_type IS NULL AND contains_pii IS NULL
            AND encryption_at_rest IS NULL)
        OR
        (type = 'external_entity'
            AND entity_type IS NOT NULL AND out_of_scope IS NOT NULL
            AND trust_level IS NULL AND assumptions IS NULL
            AND storage_type IS NULL AND contains_pii IS NULL
            AND encryption_at_rest IS NULL)
        OR
        (type = 'data_store'
            AND storage_type IS NOT NULL AND contains_pii IS NOT NULL
            AND encryption_at_rest IS NOT NULL
            AND trust_level IS NULL AND assumptions IS NULL
            AND entity_type IS NULL AND out_of_scope IS NULL)
    )
) STRICT;

CREATE TABLE IF NOT EXISTS container (
    id                INTEGER PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
    type              TEXT NOT NULL CHECK (type IN ('trust_boundary', 'container')),
    name              TEXT NOT NULL,
    description       TEXT NOT NULL,
    privilege_level   TEXT CHECK (privilege_level IS NULL OR privilege_level IN (
        'internet', 'dmz', 'corporate', 'restricted'
    )),
    CHECK (
        (type = 'trust_boundary' AND privilege_level IS NOT NULL)
        OR
        (type = 'container' AND privilege_level IS NULL)
    )
) STRICT;

CREATE TABLE IF NOT EXISTS container_membership (
    child_id   INTEGER PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
    parent_id  INTEGER NOT NULL REFERENCES container(id) ON DELETE CASCADE,
    CHECK (child_id != parent_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_container_membership_parent
    ON container_membership(parent_id);

CREATE TABLE IF NOT EXISTS data_flow (
    id            INTEGER PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
    node1_id      INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    node2_id      INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    protocol      TEXT NOT NULL,
    authenticated INTEGER NOT NULL CHECK (authenticated IN (0, 1)),
    encrypted     INTEGER NOT NULL CHECK (encrypted IN (0, 1)),
    CHECK (node1_id < node2_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_data_flow_node1 ON data_flow(node1_id);
CREATE INDEX IF NOT EXISTS idx_data_flow_node2 ON data_flow(node2_id);

CREATE TABLE IF NOT EXISTS data_item (
    id              INTEGER PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
    identifier      TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    classification  TEXT NOT NULL DEFAULT 'unclassified' CHECK (classification IN (
        'unclassified', 'pii', 'secret', 'public', 'internal'
    )),
    parent_node_id  INTEGER REFERENCES node(id) ON DELETE SET NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_data_item_parent_node ON data_item(parent_node_id);

CREATE TABLE IF NOT EXISTS flow_payload (
    flow_id          INTEGER NOT NULL REFERENCES data_flow(id) ON DELETE CASCADE,
    data_item_id     INTEGER NOT NULL REFERENCES data_item(id) ON DELETE CASCADE,
    source_endpoint  INTEGER NOT NULL CHECK (source_endpoint IN (1, 2)),
    PRIMARY KEY (flow_id, data_item_id, source_endpoint)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_flow_payload_data_item ON flow_payload(data_item_id);

CREATE TABLE IF NOT EXISTS entity_documents (
    entity_id    INTEGER NOT NULL REFERENCES entity(id)    ON DELETE CASCADE,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, document_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_entity_documents_document_id
    ON entity_documents(document_id);

CREATE TABLE IF NOT EXISTS entity_observations (
    entity_id      INTEGER NOT NULL REFERENCES entity(id)       ON DELETE CASCADE,
    observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, observation_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_entity_observations_observation_id
    ON entity_observations(observation_id);

CREATE TABLE IF NOT EXISTS process_component (
    id                INTEGER PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
    parent_process_id INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL,
    component_type    TEXT NOT NULL CHECK (component_type IN (
        'controller', 'service', 'filter', 'repository', 'utility',
        'client', 'handler', 'interceptor', 'configuration'
    ))
) STRICT;

CREATE INDEX IF NOT EXISTS idx_process_component_parent
    ON process_component(parent_process_id);

CREATE TRIGGER IF NOT EXISTS process_component_delete_entity
AFTER DELETE ON process_component
FOR EACH ROW
BEGIN
    DELETE FROM entity WHERE id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS tactic (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE IF NOT EXISTS threat_catalog (
    id            INTEGER PRIMARY KEY,
    mitre_id      TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    platforms     TEXT NOT NULL,
    description   TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS technique_tactics (
    technique_id INTEGER NOT NULL REFERENCES threat_catalog(id) ON DELETE CASCADE,
    tactic_id    INTEGER NOT NULL REFERENCES tactic(id) ON DELETE CASCADE,
    PRIMARY KEY (technique_id, tactic_id)
) STRICT;

CREATE TABLE IF NOT EXISTS threat (
    id                      INTEGER PRIMARY KEY,
    threat_catalog_id       INTEGER REFERENCES threat_catalog(id),
    title                   TEXT NOT NULL,
    scenario                TEXT NOT NULL,
    rating                  TEXT NOT NULL CHECK (rating IN ('low', 'medium', 'high')),
    description             TEXT NOT NULL,
    mitre_reference         TEXT NOT NULL,
    observed_mitigations    TEXT NOT NULL,
    recommendations         TEXT NOT NULL,
    last_updated            TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS threat_observations (
    threat_id      INTEGER NOT NULL REFERENCES threat(id) ON DELETE CASCADE,
    observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    PRIMARY KEY (threat_id, observation_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_threat_observations_observation_id
    ON threat_observations(observation_id);

CREATE TABLE IF NOT EXISTS threat_entities (
    threat_id  INTEGER NOT NULL REFERENCES threat(id) ON DELETE CASCADE,
    entity_id  INTEGER NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    PRIMARY KEY (threat_id, entity_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_threat_entities_entity_id
    ON threat_entities(entity_id);

CREATE TABLE IF NOT EXISTS validation_finding (
    id          INTEGER PRIMARY KEY,
    diagram_id  INTEGER NOT NULL REFERENCES diagram(id) ON DELETE CASCADE,
    entity_id   INTEGER REFERENCES entity(id) ON DELETE CASCADE,
    severity    TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    message     TEXT NOT NULL,
    source      TEXT NOT NULL,
    code        TEXT,
    created     TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_validation_finding_diagram
    ON validation_finding(diagram_id);

CREATE INDEX IF NOT EXISTS idx_validation_finding_entity
    ON validation_finding(entity_id);
"""

_initialized_paths: set[str] = set()


def _resolve_db_path() -> Path:
    raw = os.environ.get("TM_DB_PATH")
    if not raw:
        raise RuntimeError(
            "TM_DB_PATH is not set. Set it in your environment or .env file "
            "(see .env.example)."
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = path if path is not None else _resolve_db_path()
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        key = str(db_path)
        if key not in _initialized_paths:
            init_schema(conn)
            _initialized_paths.add(key)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
