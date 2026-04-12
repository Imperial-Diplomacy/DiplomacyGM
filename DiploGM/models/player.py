"""Player information and methods."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from enum import Enum, auto

from DiploGM.models import order
from DiploGM.models.order import Disband, Build


if TYPE_CHECKING:
    from DiploGM.models import province
    from DiploGM.models import unit
    from DiploGM.models.board import Board


class VassalType(Enum):
    """Needed due to ambiguity, especially after fall moves but before fall retreats"""

    VASSAL = "vassal"
    DUAL = "dual"


class PlayerClass(Enum):
    """Used for Chaos. Can be ignored otherwise."""
    DUCHY = 0
    KINGDOM = 1
    EMPIRE = 2


class Player:
    """Represents a player in the game."""
    def __init__(
        self,
        name: str,
        color: str | dict[str, str],
        centers: set[province.Province],
        units: set[unit.Unit],
        is_active: bool = True
    ):
        self.name: str = name
        self.color_dict: dict | None = None
        # color used for rendering vs internal default color
        if isinstance(color, dict):
            self.color_dict = color
            self.default_color = color["standard"]
            self.render_color = color["standard"]
        else:
            self.color_dict = None
            self.default_color = color
            self.render_color = color

        self.centers: set[province.Province] = centers
        self.units: set[unit.Unit] = units

        self.build_orders: set[order.PlayerOrder | order.RelationshipOrder] = set()
        self.waived_orders: int = 0

        self.vassal_orders: dict[Player, order.RelationshipOrder] = {}

        self.points: int = 0
        self.liege: Player | None = None
        self.vassals: list[Player] = []

        self._dp_max: int | None = None

        self.is_active: bool = is_active

        # Must be initialised when the board is made
        self.board: Board | None = None

    @property
    def dp_max(self) -> int:
        """Currently defaults to 1 DP per SC with a max of 3, but can be overwritten"""
        if self._dp_max is not None:
            return self._dp_max
        return min(len(self.centers), 3)

    @dp_max.setter
    def dp_max(self, value: int):
        self._dp_max = value

    def __str__(self):
        return self.name

    def get_name(self):
        """Gets the player's name, or their nickname if it exists."""
        if self.board is None:
            return self.name
        return self.board.data["players"][self.name].get("nickname", self.name)

    def info(self, board: Board) -> str:
        """Gets a string representation about the player's information."""
        bullet = "\n- "

        units = sorted(self.units, key=lambda u: (u.unit_type.value, u.province.get_name(u.coast)))
        centers = sorted(self.centers, key=lambda c: c.name)

        if board.data["players"] == "chaos":
            units = ((bullet + bullet.join([unit.province.get_name(unit.coast) for unit in units]))
                    if len(units) > 0 else 'None')
            centers = ((bullet + bullet.join([center.name for center in centers]))
                      if len(centers) > 0 else 'None')
            out = (
                f"Color: #{self.render_color}\n"
                + f"Points: {self.points}\n"
                + f"Vassals: {', '.join(map(str,self.vassals))}\n"
                + f"Liege: {self.liege if self.liege else 'None'}\n"
                + f"Units ({len(units)}): {units}\n"
                + f"Centers ({len(centers)}): {centers}\n"
            )
            return out

        center_str = "Centers:"
        for center in centers:
            center_str += bullet
            if center.core_data.core == self:
                center_str += f"{center.name} (core)"
            elif center.core_data.half_core == self:
                center_str += f"{center.name} (half-core)"
            else:
                center_str += f"{center.name}"

        unit_str = "Units:"
        for unit in units:
            unit_str += f"{bullet}({unit.unit_type.value}) {unit.province.get_name(unit.coast)}"

        color = (bullet + bullet.join([k + ': ' + v for k, v in self.color_dict.items()])
                if self.color_dict is not None else self.render_color)
        out = (
            ""
            + f"Color: {color}\n"
            + f"Score: [{len(self.centers)}/{int(board.data['players'][self.name]['vscc'])}] "
                + f"{round(board.get_score(self) * 100, 2)}%\n"
            + f"{center_str}\n"
            + f"{unit_str}\n"
        )
        return out

    def get_number_of_builds(self) -> int:
        """Gets how many builds or disbands the player currently has inputted."""
        if not self.board or not self.board.turn.is_builds():
            return 0
        num_builds = self.waived_orders
        for build_order in self.build_orders:
            if isinstance(build_order, Disband):
                num_builds -= 1
            elif isinstance(build_order, Build):
                num_builds += 1
        return num_builds

    def get_class(self) -> PlayerClass:
        """Gets the player's rank. Used for Chaos."""
        scs = len(self.centers)
        if scs >= 6:
            return PlayerClass.EMPIRE
        if scs >= 3:
            return PlayerClass.KINGDOM
        return PlayerClass.DUCHY

class OrdersSubsetOption(Enum):
    FULL = auto()
    MISSING = auto()
    SUBMITTED = auto()

class ForcedDisbandOption(Enum):
    UNMARKED = auto()
    MARK_FORCED = auto()
    ONLY_FREE = auto()

@dataclass
class ViewOrdersTags:
    subset: OrdersSubsetOption
    blind: bool
    forced: ForcedDisbandOption

    @classmethod
    def get_default(cls):
        return ViewOrdersTags(subset=OrdersSubsetOption.FULL, blind=False, forced=ForcedDisbandOption.UNMARKED)
