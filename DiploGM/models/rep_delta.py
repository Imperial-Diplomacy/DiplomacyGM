from __future__ import annotations
from dataclasses import dataclass, field
import datetime
from typing import Iterable, Optional

from DiploGM.db.database import get_connection
from DiploGM.utils.repository import Repository

@dataclass
class ReputationDelta:
    user_id: int
    delta: int
    reason: str = "unspecified"
    id: Optional[int] = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "delta": self.delta,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def from_json(data: dict) -> ReputationDelta:
        return ReputationDelta(
            id=int(data["id"]),
            user_id=int(data["user_id"]),
            delta=int(data["delta"]),
            reason=data["reason"],
            created_at=datetime.datetime.fromisoformat(data["created_at"]),
        )


class SQLiteReputationDeltaRepository(Repository):
    def __init__(self) -> None:
        self.conn = get_connection()._connection
        self._initialise_schema()

    def _initialise_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reputation_deltas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
            )
        """)
        self.conn.commit()

    def save(self, entity: ReputationDelta) -> ReputationDelta:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO reputation_deltas (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
            (
                entity.user_id,
                entity.delta,
                entity.reason,
                entity.created_at.isoformat(),
            ),
        )
        return entity

    def load(self, id: int) -> Optional[ReputationDelta]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT (id, user_id, delta, reason, created_at) FROM reputation_deltas WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return None

        return ReputationDelta(
            id=row[0],
            user_id=row[1],
            delta=row[2],
            reason=row[3],
            created_at=datetime.datetime.fromisoformat(row[4])
        )

    def delete(self, id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM reputation_deltas WHERE id = ?", (id,))
        self.conn.commit()

    def clear(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM reputation_deltas")
        self.conn.commit()

    def all(self) -> Iterable[ReputationDelta]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM reputation_deltas")
        rows = cursor.fetchall()

        data = [
            ReputationDelta(
                id=row[0],
                user_id=row[1],
                delta=row[2],
                reason=row[3],
                created_at=datetime.datetime.fromisoformat(row[4])
            ) for row in rows
        ]

        return data

    def get_value_by_user(self, user_id: int) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT SUM(delta) FROM reputation_deltas WHERE user_id = ?", (user_id,))
        data = cursor.fetchone()
        if not data:
            return None

        return int(data)
