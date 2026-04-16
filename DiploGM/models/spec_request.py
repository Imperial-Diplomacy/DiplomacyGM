import dataclasses
import json

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from DiploGM.utils.repository import Repository

@dataclass
class SpectatorBan:
    user_id: int
    end_time: str # discord_timestamp

class SpectatorBanRepository(Repository):
    def __init__(self, db_path: Path | str) -> None:
        if isinstance(db_path, str):
            db_path = Path(db_path)

        self.db_path = db_path
        self.bans: dict = {}

        if db_path.exists():
            with open(db_path, "r", encoding="utf-8") as f:
                data = json.loads(f.read())
                for k, v in data.items():
                    self.bans[k] = SpectatorBan(**v)


    def _save_to_file(self):
        curr = self.bans.copy()
        for k, v in curr.items():
            curr[k] = dataclasses.asdict(v)

        if not self.db_path.exists():
            s = self.db_path.open("x", encoding="utf-8")
            s.close()

        with open(self.db_path, "w", encoding="utf-8") as f:
            data = json.dumps(curr)
            f.write(data)

    def save(self, entity: SpectatorBan) -> SpectatorBan:
        self.bans[entity.user_id] = entity
        self._save_to_file()
        return entity

    def load(self, object_id: int) -> Optional[SpectatorBan]:
        return self.bans.get(object_id)

    def delete(self, object_id: int) -> None:
        if object_id in self.bans:
            del self.bans[object_id]
            self._save_to_file()

    def clear(self):
        self.bans = {}
        self._save_to_file()

    def all(self) -> Iterable[SpectatorBan]:
        return self.bans.values().__iter__()

class SpecRequest:
    def __init__(self, server_id: int, user_id: int, role_id: int):
        self.server_id = server_id
        self.user_id = user_id
        self.role_id = role_id
