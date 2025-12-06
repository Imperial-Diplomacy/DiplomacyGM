from __future__ import annotations

from typing import TYPE_CHECKING

from DiploGM.models.province import Province

if TYPE_CHECKING:
    from DiploGM.models.unit import UnitType
    from DiploGM.models.player import Player


class Order:
    """Order is a player's game state API."""

    def __init__(self):
        pass


# moves, holds, etc.
class UnitOrder(Order):
    """Unit orders are orders that units execute themselves."""
    display_priority: int = 0
    
    def __init__(self):
        super().__init__()
        self.hasFailed = False
        self.destination = None
        self.destination_coast = None
        self.source = None
    
    # Used for DB storage
    def get_source_str(self) -> str | None:
        return None

    # Used for DB storage
    def get_destination_str(self) -> str | None:
        return None

class ComplexOrder(UnitOrder):
    """Complex orders are orders that operate on other orders (supports and convoys)."""

    def __init__(self, source: Province):
        super().__init__()
        self.source: Province = source

class NMR(UnitOrder):
    display_priority: int = 20

    def __init__(self):
        super().__init__()

    def __str__(self):
        return "NMRs"

class Hold(UnitOrder):
    display_priority: int = 20

    def __init__(self):
        super().__init__()

    def __str__(self):
        return "Holds"


class Core(UnitOrder):
    display_priority: int = 20
    
    def __init__(self):
        super().__init__()

    def __str__(self):
        return "Cores"


class Move(UnitOrder):
    display_priority: int = 30
    
    def __init__(self, destination: Province, destination_coast: str | None = None):
        super().__init__()
        self.destination: Province = destination
        self.destination_coast: str | None = destination_coast

    def __str__(self):
        return f"- {self.get_destination_str()}"
    
    def get_destination_and_coast(self) -> tuple[Province, str | None]:
        return (self.destination, self.destination_coast)
    
    def get_destination_str(self) -> str:
        return f"{self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")

class ConvoyMove(UnitOrder):
    display_priority: int = 30
    
    def __init__(self, destination: Province, destination_coast: str | None = None):
        super().__init__()
        self.destination: Province = destination
        self.destination_coast: None = None

    def __str__(self):
        return f"Convoys - {self.destination}"
    
    def get_destination_and_coast(self) -> tuple[Province, None]:
        return (self.destination, None)
    
    def get_destination_str(self) -> str:
        return f"{self.destination}"


class ConvoyTransport(ComplexOrder):
    def __init__(self, source: Province, destination: Province, destination_coast: str | None = None):
        super().__init__(source)
        self.destination: Province = destination

    def __str__(self):
        return f"Convoys {self.source} - {self.destination}"
    
    def get_source_str(self) -> str:
        return f"{self.source}"
    
    def get_destination_str(self) -> str:
        return f"{self.destination}"


class Support(ComplexOrder):
    display_priority: int = 10
    
    def __init__(self, source: Province, destination: Province, destination_coast: str | None = None):
        super().__init__(source)
        self.destination: Province = destination
        self.destination_coast: str | None = destination_coast

    def __str__(self):
        suffix = "Hold"

        if self.source != self.destination:
            suffix = f"- {self.destination}"
            if self.destination_coast:
                suffix += f" {self.destination_coast}"
        return f"Supports {self.source} {suffix}"
        
    def get_destination_and_coast(self) -> tuple[Province, str | None]:
        return (self.destination, self.destination_coast)
    
    def get_source_str(self) -> str:
        return f"{self.source}"
    
    def get_destination_str(self) -> str:
        return f"{self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")


class RetreatMove(UnitOrder):
    def __init__(self, destination: Province, destination_coast: str | None = None):
        super().__init__()
        self.destination: Province = destination
        self.destination_coast: str | None = destination_coast

    def __str__(self):
        return f"- {self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")
        
    def get_destination_and_coast(self) -> tuple[Province, str | None]:
        return (self.destination, self.destination_coast)

    def get_destination_str(self) -> str:
        return f"{self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")

class RetreatDisband(UnitOrder):
    def __init__(self):
        super().__init__()

    def __str__(self):
        return f"Disbands"


class PlayerOrder(Order):
    """Player orders are orders that belong to a player rather than a unit e.g. builds."""

    def __init__(self, province: Province):
        super().__init__()
        self.province: Province = province
        self.coast = None

    def __hash__(self):
        return hash(self.province.name)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.province.name == other.province.name


class Build(PlayerOrder):
    """Builds are player orders because the unit does not yet exist."""

    def __init__(self, province: Province, unit_type: UnitType, coast: str | None = None):
        super().__init__(province)
        self.unit_type: UnitType = unit_type
        self.coast: str | None = coast

    def __str__(self):
        return f"Build {self.unit_type.value} {self.province}" + (f" {self.coast}" if self.coast else "")


class Disband(PlayerOrder):
    """Disbands are player order because builds are."""

    def __init__(self, province: Province):
        super().__init__(province)

    def __str__(self):
        return f"Disband {self.province}"

class Waive(Order):
    def __init__(self, quantity: int):
        super().__init__()
        self.quantity: int = quantity

    def __str__(self):
        return f"Waive {self.quantity}"

class RelationshipOrder(Order):
    """Vassal, Dual Monarchy, etc"""

    nameId: str | None = None

    def __init__(self, player: Player):
        super().__init__()
        self.player = player
        self.coast = None
    
    def __hash__(self):
        return hash(self.player)
    
    def __eq__(self, other):
        return isinstance(other, type(self)) and self.player == other.player

class Vassal(RelationshipOrder):
    """Specifies player to vassalize."""

    def __str__(self):
        return f"Vassalize {self.player}"

class Liege(RelationshipOrder):
    """Specifies player to swear allegiance to."""

    def __str__(self):
        return f"Liege {self.player}"

class DualMonarchy(RelationshipOrder):
    """Specifies player to swear allegiance to."""

    def __str__(self):
        return f"Dual Monarchy with {self.player}"

class Disown(RelationshipOrder):
    """Specifies player to drop as a vassal."""

    def __str__(self):
        return f"Disown {self.player}"

class Defect(RelationshipOrder):
    """Defect. Player is always your liege"""

    def __str__(self):
        return "Defect"

class RebellionMarker(RelationshipOrder):
    """Psudorder to mark rebellion from player due to class"""

    def __str__(self):
        return f"(Rebelling from {self.player})"