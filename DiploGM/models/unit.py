"""Armies and fleets and so forth."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from DiploGM.models.province import ProvinceType

if TYPE_CHECKING:
    from DiploGM.models import province, player, order


# TODO: rename to Type and import as unit.Type
class UnitType(Enum):
    """Type of unit."""
    ARMY = "A"
    FLEET = "F"

@dataclass
class DPAllocation:
    """Dataclass for storing DP allocation information."""
    points: int
    order: order.UnitOrder

class Unit:
    """Units information. They don't have a lot of logic to them aside from retreat options at the moment."""
    def __init__(
        self,
        unit_type: UnitType,
        owner: player.Player | None,
        current_province: province.Province,
        coast: str | None,
    ):
        self.unit_type: UnitType = unit_type
        self.player: player.Player | None = owner
        self.province: province.Province = current_province
        self.coast: str | None = coast

        # retreat_options is None when not dislodged and {} when dislodged without retreat options
        # When there are retreat options, they are stored as a set of (Province, coast) tuples
        self.retreat_options: set[tuple[province.Province, str | None]] | None = None
        self.order: order.UnitOrder | None = None

        self.dp_allocations: dict[str, DPAllocation] = {}

    def __str__(self):
        return f"{self.unit_type.value} {self.province.get_name(self.coast)}"

    def add_retreat_options(self):
        """Adds all valid retreat options based on unit type and current province."""
        if self.retreat_options is None:
            self.retreat_options = set()
        if self.unit_type == UnitType.ARMY:
            for province in self.province.adjacency_data.adjacent:
                if province.type != ProvinceType.SEA:
                    self.retreat_options.add((province, None))
        else:
            for province in self.province.get_coastal_adjacent(self.coast):
                if isinstance(province, tuple):
                    self.retreat_options.add(province)
                else:
                    self.retreat_options.add((province, None))

    def remove_retreat_option(self, province: province.Province):
        """Removes a specific retreat option."""
        if self.retreat_options is None:
            return
        # Use discard to avoid KeyError if an option is not present
        self.retreat_options.discard((province, None))
        for coast in province.get_multiple_coasts():
            self.retreat_options.discard((province, coast))

    def remove_many_retreat_options(self, provinces: set[province.Province]):
        """Removes multiple retreat options.
        Since the set is relatively large compared to retreat_options,
        we iterate over a copy of retreat_options instead."""
        if self.retreat_options is None:
            return
        for retreat in set(self.retreat_options):
            if retreat[0] in provinces:
                self.retreat_options.discard(retreat)
