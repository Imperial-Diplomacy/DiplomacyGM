"""Enums and AdjudicatableOrder helper class for adjudication."""

from enum import Enum

from DiploGM.models.order import NMR, Hold, Core, Move, Support, ConvoyTransport, Transform, UnitOrder
from DiploGM.models.province import Province
from DiploGM.models.unit import Unit, UnitType


class Resolution(Enum):
    """Whether an order succeeds or fails."""
    SUCCEEDS = 0
    FAILS = 1


class ResolutionState(Enum):
    """Resolution status for an order (unresolved, guessing, resolved)."""
    UNRESOLVED = 0
    GUESSING = 1
    RESOLVED = 2


class OrderType(Enum):
    """The type of order."""
    HOLD = 0
    CORE = 1
    MOVE = 2
    SUPPORT = 3
    CONVOY = 4
    TRANSFORM = 5


class AdjudicableOrder:
    """Helper class for adjudicating orders.
    Contains order information and information about the unit's adjudication state."""
    def __init__(self, unit: Unit):
        self.state = ResolutionState.UNRESOLVED
        self.resolution = Resolution.FAILS

        if unit.order is None:
            raise ValueError(f"Order for unit {unit} is missing")

        self.country = unit.player
        self.is_army = unit.unit_type == UnitType.ARMY
        self.current_province = unit.province
        self.current_coast = unit.coast

        self.supports: set[AdjudicableOrder] = set()
        self.convoys: set[AdjudicableOrder] = set()

        self.type: OrderType
        self.destination_province: Province = self.current_province
        self.destination_coast: str | None = self.current_coast
        self.source_province: Province = self.current_province
        self.is_convoy: bool = False
        self.is_sortie: bool = False
        # indicates that a move is also a convoy that failed, so no support holds
        self.not_supportable = False
        self.is_valid = True
        if isinstance(unit.order, (Hold, NMR)):
            self.type = OrderType.HOLD
        elif isinstance(unit.order, Core):
            self.type = OrderType.CORE
        elif isinstance(unit.order, Transform):
            self.type = OrderType.TRANSFORM
            self.destination_coast = unit.order.destination_coast
        elif isinstance(unit.order, Move):
            self.type = OrderType.MOVE
            (self.destination_province, self.destination_coast) = unit.order.get_destination_and_coast()
            self.is_sortie = unit.order.is_sortie
        elif isinstance(unit.order, Support):
            self.type = OrderType.SUPPORT
            self.source_province = unit.order.source
            (self.destination_province, self.destination_coast) = unit.order.get_destination_and_coast()
        elif isinstance(unit.order, ConvoyTransport):
            self.type = OrderType.CONVOY
            self.source_province = unit.order.source
            self.destination_province = unit.order.destination
        else:
            raise ValueError(f"Can't parse {unit.order.__class__.__name__} to OrderType")

        self.base_unit = unit

    def __str__(self):
        # This could be improved
        return f"{self.current_province} {self.type} " + \
               f"{self.source_province if self.source_province else ''} " + \
               f"{self.destination_province} [{self.state}:{self.resolution}]"

    def get_original_order(self) -> UnitOrder:
        """Get the original order."""
        if self.base_unit.order is None:
            raise ValueError("AdjudicableOrder can't find source order somehow")
        return self.base_unit.order
