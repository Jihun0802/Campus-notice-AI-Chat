from __future__ import annotations

import sqlite3
from pathlib import Path

from campus_notice_ai.config import PROJECT_ROOT, resolve_db_path


MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = resolve_db_path(str(db_path) if db_path else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0

    while index < len(script):
        char = script[index]
        current.append(char)

        if char == "'" and not in_double_quote:
            if in_single_quote and index + 1 < len(script) and script[index + 1] == "'":
                current.append(script[index + 1])
                index += 1
            else:
                in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        index += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    if all(migration_file.stem in applied for migration_file in migration_files):
        return

    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for migration_file in migration_files:
            version = migration_file.stem
            if version in applied:
                continue
            for statement in split_sql_statements(migration_file.read_text(encoding="utf-8")):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (version,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
