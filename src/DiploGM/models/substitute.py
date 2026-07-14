import datetime
from dataclasses import dataclass, field
from enum import Enum


class SubstituteType(Enum):
    INCOMING = 0
    OUTGOING = 1
    TEMP_INCOMING = 2
    TEMP_OUTGOING = 3

@dataclass
class SubstituteEvent:
    server_id: int
    power: str
    user_id: int
    sub_type: SubstituteType
    days: int = -1
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    id: int = -1

    def __hash__(self):
        code=f"{self.id}{self.server_id}{self.user_id}{self.created_at.isoformat()}"
        return hash(code)

    def __eq__(self, value: object, /) -> bool:
        return self.__hash__() == value.__hash__()
