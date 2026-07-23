from dataclasses import dataclass

@dataclass
class PlayerSignup:
    scrapper: bool
    first: str | None = None
    second: str | None = None
    third: str | None = None
    fourth: str | None = None
    fifth: str | None = None
