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


class Player:
    """Represents a player in the game."""

    def __init__(
        self,
        name: str,
        color: str | dict[str, str],
        centers: set[province.Province],
        units: set[unit.Unit],
        is_active: bool = True,
    ):
        self.name: str = name
        self.color_dict: dict | None = None
        # color used for rendering vs internal default color
        if isinstance(color, dict):
            self.color_dict = {k: v.lower() for k, v in color.items()}
            self.default_color = color["standard"].lower()
        else:
            self.color_dict = None
            self.default_color = color.lower()

        self.centers: set[province.Province] = centers
        self.units: set[unit.Unit] = units
        self.build_orders: set[order.PlayerOrder] = set()
        self.waived_orders: int = 0

        self._dp_max: int | None = None
        self.is_active: bool = is_active
        self.sc_history: dict[int, int] = {}

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

        units = sorted(
            self.units, key=lambda u: (u.unit_type.code, u.province.get_name(u.coast))
        )
        unit_str = f"({len(units)}):"
        for unit in units:
            unit_str += (
                f"{bullet}({unit.unit_type.code}) {unit.province.get_name(unit.coast)}"
            )

        capital_str = (board.data
            .get("players", {})
            .get(self.name, {})
            .get("capital", "None")
        )

        centers = sorted(self.centers, key=lambda c: c.name)
        center_str = f"({len(centers)}):"
        for center in centers:
            core_str = (
                " (core)"
                if center.core_data.core == self
                else " (half-core)"
                if center.core_data.half_core == self
                else ""
            )
            center_str += f"{bullet}{center.name}{core_str}"

        player_data = board.data["players"][self.name]
        color = player_data.get("custom_color", self.default_color)
        score = ""
        if not board.is_chaos():
            color = (
                bullet
                + color
                + (
                    bullet
                    + bullet.join([k + ": " + v for k, v in self.color_dict.items()])
                    if self.color_dict is not None
                    else ""
                )
            )
            score = (
                f"Score: [{len(self.centers)}/{int(player_data.get('vscc', 0))}] "
                + f"{round(board.get_score(self) * 100, 2)}%\n"
            )

        out = f"Capital: {capital_str}\nCenters: {center_str}\nUnits: {unit_str}\nColor: {color}\n{score}"
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


class OrdersSubsetOption(Enum):
    """Whether to show all orders, only submitted orders, or only missing orders."""

    FULL = auto()
    MISSING = auto()
    SUBMITTED = auto()


class ForcedDisbandOption(Enum):
    """Whether to mark dislodged units that must be disbanded, or even hide them entirely."""

    UNMARKED = auto()
    MARK_FORCED = auto()
    ONLY_FREE = auto()


@dataclass
class ViewOrdersTags:
    """Tags for viewing orders with various options."""

    subset: OrdersSubsetOption
    blind: bool
    forced: ForcedDisbandOption
    open_cores: bool
    explain: bool


@dataclass
class ViewOpenCoresTags:
    """Tags for viewing open cores with various options."""

    blind: bool
