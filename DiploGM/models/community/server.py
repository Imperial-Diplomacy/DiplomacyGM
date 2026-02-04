from dataclasses import dataclass, field
import datetime
from typing import Iterable, Optional

from DiploGM.db.database import get_connection
from DiploGM.utils.repository import Repository

@dataclass
class Server:
    id: int
    name: str
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    active: bool = True
    deactivated_at: Optional[datetime.datetime] = None


class SQLiteServerRepository(Repository[Server]):
    def __init__(self) -> None:
        self.conn = get_connection()._connection
        self._initialise_schema()

    def _initialise_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS community_servers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL CHECK (active IN (0, 1)),
                deactivated_at TEXT
            );
        """)

    def save(self, entity: Server) -> Server:
        self.conn.execute(
            """
            INSERT INTO community_servers (id, name, created_at, active, deactivated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                active = excluded.active,
                deactivated_at = excluded.deactivated_at
            """,
            (
                entity.id,
                entity.name,
                entity.created_at.isoformat(),
                int(entity.active),
                entity.deactivated_at.isoformat() if entity.deactivated_at else None,
            ),
        )
        self.conn.commit()
        return entity

    def load(self, id: int) -> Optional[Server]:
        row = self.conn.execute(
            "SELECT * FROM community_servers WHERE id = ?", (id,)
        ).fetchone()
        return self._row_to_model(row) if row else None

    def delete(self, id: int) -> None:
        self.conn.execute("DELETE FROM servers WHERE id = ?", (id,))
        self.conn.commit()

    def soft_delete(self, id: int) -> None:
        self.conn.execute("""
            UPDATE community_servers 
            SET active = 0,
                deactivated_at = ?
            WHERE id = ?
        """, (datetime.datetime.now().isoformat(), id,))

    def clear(self) -> None:
        self.conn.execute("DELETE FROM community_servers")
        self.conn.commit()

    def all(self) -> Iterable[Server]:
        rows = self.conn.execute("SELECT * FROM community_servers").fetchall()
        return [self._row_to_model(r) for r in rows]

    def _row_to_model(self, row) -> Server:
        return Server(
            id=row[0],
            name=row[1],
            created_at=datetime.datetime.fromisoformat(row[2]),
            active=bool(row[3]),
            deactivated_at=datetime.datetime.fromisoformat(row[4]) if row[4] else None,
        )

