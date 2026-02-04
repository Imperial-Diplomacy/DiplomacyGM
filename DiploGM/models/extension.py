from __future__ import annotations
from dataclasses import dataclass, field
import datetime
import logging
from typing import Iterable, Optional

from DiploGM.db.database import get_connection
from DiploGM.utils.repository import Repository

logger = logging.getLogger(__name__)

@dataclass
class ExtensionEvent:
    user_id: int
    server_id: int
    hours: int
    id: Optional[int] = None
    reason: str = "unspecified"
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_json(self) -> dict:
        return {
            "user_id": self.user_id,
            "server_id": self.server_id,
            "hours": self.hours,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_json(cls, data: dict) -> ExtensionEvent:
        return ExtensionEvent(
            user_id=data["user_id"],
            server_id=data["server_id"],
            hours=data["hours"],
            reason=data["reason"],
            created_at=datetime.datetime.fromisoformat(data["created_at"])
        )

class SQLiteExtensionEventRepository(Repository):
    def __init__(self) -> None:
        self.conn = get_connection()
        self._initialise_schema()

    def _initialise_schema(self):
        cursor = self.conn._connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extension_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                server_id INTEGER NOT NULL,
                hours INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self.conn._connection.commit()

    def save(self, entity: ExtensionEvent) -> ExtensionEvent:
        cursor = self.conn._connection.cursor()
        cursor.execute(
            "INSERT INTO extension_events (user_id, server_id, hours, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (entity.user_id, entity.server_id, entity.hours, entity.reason, entity.created_at.isoformat()),
        )
        self.conn._connection.commit()
        entity.id = cursor.lastrowid

        return entity

    def load(self, id: int) -> Optional[ExtensionEvent]:
        cursor = self.conn._connection.cursor()
        cursor.execute(
            "SELECT (id, user_id, server_id, hours, reason, created_at) FROM extension_events WHERE id = ?;",
            (id,),
        )
        data = cursor.fetchone()
        if not data:
            return None

        entity = ExtensionEvent(
            id=data[0],
            user_id=data[1],
            server_id=data[2],
            hours=data[3],
            reason=data[4],
            created_at=datetime.datetime.fromisoformat(data[5])
        )

        return entity

    def delete(self, id: int) -> None:
        cursor = self.conn._connection.cursor()
        cursor.execute(
            "DELETE FROM extension_events WHERE id = ?;",
            (id,),
        )
        self.conn._connection.commit()

    def clear(self) -> None:
        cursor = self.conn._connection.cursor()
        cursor.execute(
            "DELETE FROM extension_events;",
            (id,),
        )
        self.conn._connection.commit()

    def all(self) -> Iterable[ExtensionEvent]:
        cursor = self.conn._connection.cursor()
        cursor.execute(
            "SELECT id, user_id, server_id, hours, reason, created_at FROM extension_events;",
        )
        data = cursor.fetchall()
        if not data:
            return []

        return [
            ExtensionEvent(
            id=row[0],
            user_id=row[1],
            server_id=row[2],
            hours=row[3],
            reason=row[4],
            created_at=datetime.datetime.fromisoformat(row[5])
            ) for row in data
        ]

    def load_by_user(self, user_id: int) -> list[ExtensionEvent]:
        cursor = self.conn._connection.cursor()
        cursor.execute(
            "SELECT id, user_id, server_id, hours, reason, created_at FROM extension_events WHERE user_id = ?;",
            (user_id,),
        )
        data = cursor.fetchall()
        if not data:
            return []

        return [
            ExtensionEvent(
            id=row[0],
            user_id=row[1],
            server_id=row[2],
            hours=row[3],
            reason=row[4],
            created_at=datetime.datetime.fromisoformat(row[5])
            ) for row in data
        ]

    def load_by_server(self, server_id: int) -> list[ExtensionEvent]:
        cursor = self.conn._connection.cursor()
        cursor.execute(
            "SELECT id, user_id, server_id, hours, reason, created_at FROM extension_events WHERE server_id = ?;",
            (server_id,),
        )
        data = cursor.fetchall()
        if not data:
            return []

        return [
            ExtensionEvent(
            id=row[0],
            user_id=row[1],
            server_id=row[2],
            hours=row[3],
            reason=row[4],
            created_at=datetime.datetime.fromisoformat(row[5])
            ) for row in data
        ]
