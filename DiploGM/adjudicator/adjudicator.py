from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.unit import Unit

logger = logging.getLogger(__name__)

class MapperInformation:
    def __init__(self, unit: Unit):
        self.location = unit.province
        self.coast = unit.coast
        self.order = unit.order


class Adjudicator:
    __metaclass__ = abc.ABCMeta

    def __init__(self, board: Board):
        self._board = board
        self.save_orders = True
        self.flags = board.data.get("adju flags", [])
        self.build_options = board.data.get("build_options", "classic")
        self.has_vassals = "vassal system" in self.flags
        self.failed_or_invalid_units: set[MapperInformation] = set()

    @abc.abstractmethod
    def run(self) -> Board:
        pass
