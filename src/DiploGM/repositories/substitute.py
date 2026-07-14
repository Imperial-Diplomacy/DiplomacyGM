from __future__ import annotations
import datetime
from typing import Iterable, Optional

from DiploGM.db import database
from DiploGM.models import SubstituteEvent
from DiploGM.repositories.base import BaseRepository

class SubstituteEventRepository(BaseRepository[SubstituteEvent]):
    def __init__(self) -> None:
        self.conn = database.get_connection()._connection
        self._initialise_schema()

    def _initialise_schema(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS substitution_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                power TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                type INTEGER NOT NULL,
                days INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def save(self, entity: SubstituteEvent) -> SubstituteEvent:
        cursor = self.conn.cursor()

        cursor.execute(
            "INSERT (server_id, power, user_id, type, days, created_at) INTO substitution_events VALUES (?, ?, ?, ?, ?)", 
            (
                entity.server_id,
                entity.power,
                entity.user_id,
                entity.sub_type,
                entity.days,
                entity.created_at.isoformat()
            )
        )

        entity.id = cursor.lastrowid
        return entity

    def load(self, object_id: int) -> Optional[SubstituteEvent]: 
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT (id, server_id, power, user_id, sub_type, days, created_at) FROM substitution_events WHERE id = ?;", (object_id,)
        )

        data = cursor.fetchone()
        if data is None:
            return None

        event = SubstituteEvent(
            id=data[0],
            server_id=data[1], 
            power=data[2],
            user_id=data[3],
            sub_type=data[4],
            days=data[5],
            created_at=datetime.datetime.fromisoformat(data[6])
        )
        return event

    def delete(self, object_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM substitution_events WHERE id = ?;",
            (object_id,),
        )
        self.conn.commit()

    def clear(self) -> None: 
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM substitution_events;",
        )
        self.conn.commit()

    def all(self) -> Iterable[SubstituteEvent]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT (id, server_id, power, user_id, sub_type, days, created_at) FROM substitution_events;"
        )
        data = cursor.fetchall()
        if not data:
            return []

        return [
            SubstituteEvent(
                id=row[0],
                server_id=row[1],
                power=row[2],
                user_id=row[3],
                sub_type=row[4],
                days=row[5],
                created_at=datetime.datetime.fromisoformat(row[6]),
            )
            for row in data
        ]

substitute_repo = SubstituteEventRepository()
