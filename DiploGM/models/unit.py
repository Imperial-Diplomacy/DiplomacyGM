from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from diplomacy.persistence.province import ProvinceType

if TYPE_CHECKING:
    from DiploGM.models import province, player, order


# TODO: rename to Type and import as unit.Type
class UnitType(Enum):
    ARMY = "A"
    FLEET = "F"


class Unit:
    def __init__(
        self,
        unit_type: UnitType,
        owner: player.Player,
        current_province: province.Province,
        coast: str | None,
        retreat_options: set[(province.Province, str | None)] | None,
    ):
        self.unit_type: UnitType = unit_type
        self.player: player.Player = owner
        self.province: province.Province = current_province
        self.coast: str | None = coast

        # retreat_options is None when not dislodged and {} when dislodged without retreat options
        self.retreat_options: set[(province.Province, str | None)] | None = retreat_options
        self.order: order.UnitOrder | None = None

    def __str__(self):
        return f"{self.unit_type.value} {self.province.get_name(self.coast)}"
    
    def add_retreat_options(self):
        if self.retreat_options is None:
            self.retreat_options = set()
        if self.unit_type == UnitType.ARMY:
            for province in self.province.adjacent:
                if province.type != ProvinceType.SEA:
                    self.retreat_options.add((province, None))
        else:
            for province in self.province.get_coastal_adjacent(self.coast):
                if isinstance(province, tuple):
                    self.retreat_options.add(province)
                else:
                    self.retreat_options.add((province, None))
    
    def remove_retreat_option(self, province: province.Province):
        self.retreat_options -= {(province, None)}
        self.retreat_options -= {(province, coast) for coast in province.get_multiple_coasts()}

    def remove_many_retreat_options(self, provinces: set[province.Province]):
        for retreat in set(self.retreat_options):
            if retreat[0] in provinces:
                self.retreat_options.remove(retreat)