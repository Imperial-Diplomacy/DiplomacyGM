"""Modules containing all of the various Orders."""
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
        self.has_failed = False
        self.destination = None
        self.destination_coast = None
        self.source = None
        self.is_support_holdable = True

    # Used for DB storage
    def get_source_str(self) -> str | None:
        """For Supports and Convoys, the location that they're supporting/convoying from."""
        return None

    # Used for DB storage
    def get_destination_str(self) -> str | None:
        """The destination location or that of the unit being supported/convoyed."""
        return None

class ComplexOrder(UnitOrder):
    """Complex orders are orders that operate on other orders (supports and convoys)."""

    def __init__(self, source: Province):
        super().__init__()
        self.source: Province = source

class NMR(UnitOrder):
    """No Move Recorded. Identical in function to Hold but done when an order is not given."""
    display_priority: int = 20

    def __str__(self):
        return "NMRs"

class Hold(UnitOrder):
    """Unit holds in place."""
    display_priority: int = 20

    def __str__(self):
        return "Holds"


class Core(UnitOrder):
    """Unit cores and over two turns can turn a SC into a home SC. May be supportable depending on game rules."""
    display_priority: int = 20

    def __init__(self):
        super().__init__()
        self.is_support_holdable = False

    def __str__(self):
        return "Cores"

class Transform(UnitOrder):
    """Unit transforms from Army to Fleet or vice versa. This is the Order used in movement phases."""
    display_priority: int = 20

    def __init__(self, destination_coast: str | None = None):
        super().__init__()
        self.destination_coast = destination_coast
        self.is_support_holdable = False

    def __str__(self):
        return "Transforms" + (f" to {self.destination_coast}" if self.destination_coast else "")

    def get_destination_str(self) -> str:
        return self.destination_coast if self.destination_coast else ""

class Move(UnitOrder):
    """Moves a unit from one location to another. Does include moves via convoy."""
    display_priority: int = 30

    def __init__(self, destination: Province, destination_coast: str | None = None):
        super().__init__()
        self.destination: Province = destination
        self.destination_coast: str | None = destination_coast
        self.is_support_holdable = False
        self.is_sortie = False # Should Sortie be its own Order? Seems excessive.

    def __str__(self):
        return f"- {self.get_destination_str()}"

    def get_destination_and_coast(self) -> tuple[Province, str | None]:
        """Move orders can care about the coast of the destination province."""
        return (self.destination, self.destination_coast)

    def get_destination_str(self) -> str:
        return f"{self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")

class ConvoyTransport(ComplexOrder):
    """Convoys an Army from one Province to another."""
    def __init__(self, source: Province, destination: Province):
        super().__init__(source)
        self.destination: Province = destination

    def __str__(self):
        return f"Convoys {self.source} - {self.destination}"

    def get_source_str(self) -> str:
        return f"{self.source}"

    def get_destination_str(self) -> str:
        return f"{self.destination}"


class Support(ComplexOrder):
    """If source and destination are different, this is a support move. If they're the same, it's a support hold."""
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
        """For the rare cases where the move is to one coast but the support is to the other."""
        return (self.destination, self.destination_coast)

    def get_source_str(self) -> str:
        return f"{self.source}"

    def get_destination_str(self) -> str:
        return f"{self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")


class RetreatMove(UnitOrder):
    """For unit retreats."""
    def __init__(self, destination: Province, destination_coast: str | None = None):
        super().__init__()
        self.destination: Province = destination
        self.destination_coast: str | None = destination_coast

    def __str__(self):
        return f"- {self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")

    def get_destination_and_coast(self) -> tuple[Province, str | None]:
        """This should probably be part of UnitOrder."""
        return (self.destination, self.destination_coast)

    def get_destination_str(self) -> str:
        return f"{self.destination}" + (f" {self.destination_coast}" if self.destination_coast else "")

class RetreatDisband(UnitOrder):
    """For disbands during retreats."""

    def __str__(self):
        return "Disbands"


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

    def __str__(self):
        return f"Disband {self.province}"

class TransformBuild(PlayerOrder):
    """This is for Transforming units during adjustment phases."""
    def __init__(self, province: Province, destination_coast: str | None = None):
        super().__init__(province)
        self.coast = destination_coast

    def __str__(self):
        return f"Transform {self.province}" + (f" {self.coast}" if self.coast else "")

class Waive(Order):
    """Waives some number of builds. Doesn't do anything on adjudication."""
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
