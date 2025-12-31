from __future__ import annotations
from dataclasses import dataclass, field
import datetime
from typing import Iterable, Optional

from DiploGM.db.database import get_connection
from DiploGM.utils.repository import Repository

@dataclass
class Community:
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

class SQLiteCommunityRepository(Repository):
    def __init__(self) -> None:
        self.conn = get_connection()._connection
        self._initialise_schema()

    def _initialise_schema(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS communities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def save(self, entity: Community) -> Community:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO communities (id, name, description, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description
            """,
            (
                entity.id,
                entity.name,
                entity.description,
                entity.created_at.isoformat()
            ),
        )
        self.conn.commit()
        return entity

    def load(self, id: int) -> Optional[Community]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM communities WHERE id = ?", (id,))
        row = cur.fetchone()
        return self._row_to_model(row) if row else None

    def delete(self, id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM communities WHERE id = ?", (id,))
        self.conn.commit()

    def clear(self) -> None:
        self.conn.execute("DELETE FROM communities")
        self.conn.commit()

    def all(self) -> Iterable[Community]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM communities")
        rows = cur.fetchall()
        return [self._row_to_model(r) for r in rows]

    def _row_to_model(self, row) -> Community:
        return Community(
            id=int(row[0]),
            name=row[1],
            description=row[2],
            created_at=datetime.datetime.fromisoformat(row[3]),
        )

