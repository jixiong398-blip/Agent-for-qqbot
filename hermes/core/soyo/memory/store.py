"""First extracted Soyo memory slice for the future DSH Python worker.

This module deliberately has no Hermes imports and no implicit home directory.
The caller must provide an absolute SQLite path, so a DSH profile cannot
silently write into the production Hermes home.

Only the smallest cross-host contract is implemented here: exact long-term
fact upsert/lookup and append/read of session turns.  The legacy Hermes
``MemoryStore`` remains untouched until this boundary has runtime evidence.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional


def _json_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
    return []


@dataclass
class MemoryFact:
    """A source-aware persistent fact with a stable logical category/key."""

    id: int = 0
    category: str = "general"
    key: str = ""
    value: str = ""
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source_session_ids: list[str] = field(default_factory=list)
    source_context: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    active: bool = True


@dataclass
class MemoryTurn:
    """A minimal session turn preserved for later DSH context building."""

    id: int = 0
    session_id: str = ""
    turn_index: int = 0
    role: str = "user"
    speaker_name: str = ""
    chat_type: str = "dm"
    content: str = ""
    topics: list[str] = field(default_factory=list)
    created_at: float = 0.0


class SoyoMemoryStore:
    """Small explicit-path SQLite store independent of the Hermes runtime."""

    def __init__(self, db_path: Path | str):
        self._db_path = Path(db_path)
        if not self._db_path.is_absolute():
            raise ValueError("SoyoMemoryStore requires an absolute db_path")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS soyo_memory_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                fact_key TEXT NOT NULL,
                value TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0.5,
                source_session_ids TEXT NOT NULL DEFAULT '[]',
                source_context TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_soyo_memory_active_key
                ON soyo_memory_facts(category, fact_key) WHERE active = 1;
            CREATE TABLE IF NOT EXISTS soyo_memory_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                speaker_name TEXT NOT NULL DEFAULT '',
                chat_type TEXT NOT NULL DEFAULT 'dm',
                content TEXT NOT NULL,
                topics TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_soyo_memory_turn_session
                ON soyo_memory_turns(session_id, turn_index);
            """
        )
        self._conn.commit()

    def upsert_fact(
        self,
        *,
        category: str,
        key: str,
        value: str,
        tags: Iterable[str] = (),
        confidence: float = 0.5,
        source_session_ids: Iterable[str] = (),
        source_context: str = "",
    ) -> int:
        """Insert or update one active fact without ranking away exact lookup."""

        category = str(category).strip()
        key = str(key).strip()
        if not category or not key:
            raise ValueError("category and key are required")

        now = time.time()
        new_sources = list(dict.fromkeys(str(item) for item in source_session_ids))
        row = self._conn.execute(
            "SELECT id, source_session_ids, created_at FROM soyo_memory_facts "
            "WHERE category = ? AND fact_key = ? AND active = 1 LIMIT 1",
            (category, key),
        ).fetchone()
        if row:
            sources = list(dict.fromkeys(_json_list(row["source_session_ids"]) + new_sources))
            self._conn.execute(
                "UPDATE soyo_memory_facts SET value=?, tags=?, confidence=?, "
                "source_session_ids=?, source_context=?, updated_at=? WHERE id=?",
                (
                    str(value),
                    json.dumps(list(dict.fromkeys(str(item) for item in tags)), ensure_ascii=False),
                    float(confidence),
                    json.dumps(sources, ensure_ascii=False),
                    str(source_context),
                    now,
                    row["id"],
                ),
            )
            self._conn.commit()
            return int(row["id"])

        cursor = self._conn.execute(
            "INSERT INTO soyo_memory_facts "
            "(category, fact_key, value, tags, confidence, source_session_ids, "
            "source_context, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                category,
                key,
                str(value),
                json.dumps(list(dict.fromkeys(str(item) for item in tags)), ensure_ascii=False),
                float(confidence),
                json.dumps(new_sources, ensure_ascii=False),
                str(source_context),
                now,
                now,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_fact(self, *, category: str, key: str) -> Optional[MemoryFact]:
        """Return the exact active fact, independent of confidence ranking."""

        row = self._conn.execute(
            "SELECT * FROM soyo_memory_facts WHERE category = ? AND fact_key = ? "
            "AND active = 1 ORDER BY updated_at DESC, id DESC LIMIT 1",
            (str(category).strip(), str(key).strip()),
        ).fetchone()
        if row is None:
            return None
        return MemoryFact(
            id=int(row["id"]),
            category=str(row["category"]),
            key=str(row["fact_key"]),
            value=str(row["value"]),
            tags=_json_list(row["tags"]),
            confidence=float(row["confidence"]),
            source_session_ids=_json_list(row["source_session_ids"]),
            source_context=str(row["source_context"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            active=bool(row["active"]),
        )

    def append_turn(
        self,
        *,
        session_id: str,
        turn_index: int,
        role: str,
        content: str,
        speaker_name: str = "",
        chat_type: str = "dm",
        topics: Iterable[str] = (),
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO soyo_memory_turns "
            "(session_id, turn_index, role, speaker_name, chat_type, content, topics, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(session_id),
                int(turn_index),
                str(role),
                str(speaker_name),
                str(chat_type),
                str(content),
                json.dumps(list(dict.fromkeys(str(item) for item in topics)), ensure_ascii=False),
                time.time(),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_session_turns(self, session_id: str, *, limit: int = 20) -> list[MemoryTurn]:
        if limit <= 0:
            return []
        rows = self._conn.execute(
            "SELECT * FROM soyo_memory_turns WHERE session_id = ? "
            "ORDER BY turn_index DESC, id DESC LIMIT ?",
            (str(session_id), int(limit)),
        ).fetchall()
        return [
            MemoryTurn(
                id=int(row["id"]),
                session_id=str(row["session_id"]),
                turn_index=int(row["turn_index"]),
                role=str(row["role"]),
                speaker_name=str(row["speaker_name"]),
                chat_type=str(row["chat_type"]),
                content=str(row["content"]),
                topics=_json_list(row["topics"]),
                created_at=float(row["created_at"]),
            )
            for row in reversed(rows)
        ]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SoyoMemoryStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
