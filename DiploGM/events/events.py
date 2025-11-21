import datetime
import uuid


class Event:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.timestamp = datetime.datetime.now(datetime.timezone.utc)

    def __str__(self) -> str:
        return f"{type(self).__name__}[{self.id}]"


class OrderSubmitted(Event):
    def __init__(self) -> None:
        super().__init__()
