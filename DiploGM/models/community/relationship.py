from dataclasses import dataclass, field
import datetime
from enum import StrEnum
from typing import Iterable, Optional

from DiploGM.db.database import get_connection
from DiploGM.utils.repository import Repository

class RelationshipType(StrEnum):
    SERVER_MEMBER = "SERVER_MEMBER"
    SERVER_MODERATOR = "SERVER_MODERATOR"
    COMMUNITY_MEMBER = "COMMUNITY_MEMBER"
    COMMUNITY_SERVER = "COMMUNITY_SERVER"
    COMMUNITY_MODERATOR = "COMMUNITY_MODERATOR"
    COMMUNITY_ADMIN = "COMMUNITY_ADMIN"
    COMMUNITY_OWNER = "COMMUNITY_OWNER"

@dataclass
class Relationship:
    subject_id: int
    object_id: int
    type: RelationshipType
    id: Optional[int] = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

class SQLiteRelationshipRepository(Repository[Relationship]):
    def __init__(self) -> None:
        self.conn = get_connection()._connection
        self._initialise_schema()

    def _initialise_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                object_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (subject_id, object_id, type)
            );
        """)
        self.conn.commit()

    def save(self, entity: Relationship) -> Relationship:
        self.conn.execute(
            """
            INSERT INTO relationships
            (subject_id, object_id, type, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                entity.subject_id,
                entity.object_id,
                entity.type,
                entity.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return entity

    def save_many(self, entities: list[Relationship]):
        self.conn.executemany(
            """
            INSERT INTO relationships
            (subject_id, object_id, type, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            [(
                entity.subject_id,
                entity.object_id,
                entity.type,
                entity.created_at.isoformat(),
            ) for entity in entities]
        )
        self.conn.commit()

    def load(self, id: int) -> Optional[Relationship]:
        row = self.conn.execute(
            "SELECT * FROM relationships WHERE id = ?", (id,)
        ).fetchone()
        return self._row_to_model(row) if row else None

    def delete(self, id: int) -> None:
        self.conn.execute("DELETE FROM relationships WHERE id = ?", (id,))
        self.conn.commit()

    def delete_many(self, ids: list[int]):
        self.conn.executemany("DELETE FROM relationships WHERE id = ?", [(id,) for id in ids])
        self.conn.commit()

    def clear(self) -> None:
        self.conn.execute("DELETE FROM relationships")
        self.conn.commit()

    def all(self) -> Iterable[Relationship]:
        rows = self.conn.execute("SELECT * FROM relationships").fetchall()
        return [self._row_to_model(r) for r in rows]

    def _row_to_model(self, row) -> Relationship:
        return Relationship(
            id=row[0],
            subject_id=row[1],
            object_id=row[2],
            type=RelationshipType(row[3]),
            created_at=row[4],
        )

