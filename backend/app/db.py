"""Backward-compatible database proxy forwarding to app.database."""

from app.database import (
    BASE_DIR,
    DB_FILE,
    DB_URL,
    DATABASE_URL,
    engine,
    init_db,
    get_session,
    get_db_context,
    populate_db_if_empty,
    ingest_valmet_data,
)

__all__ = [
    "BASE_DIR",
    "DB_FILE",
    "DB_URL",
    "DATABASE_URL",
    "engine",
    "init_db",
    "get_session",
    "get_db_context",
    "populate_db_if_empty",
    "ingest_valmet_data",
]
