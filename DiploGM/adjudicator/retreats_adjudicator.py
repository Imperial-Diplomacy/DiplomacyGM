from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from DiploGM.adjudicator.adjudicator import Adjudicator
from DiploGM.models.order import NMR, RetreatMove, RebellionMarker
from DiploGM.models.player import PlayerClass
from DiploGM.models.unit import Unit

if TYPE_CHECKING:
    from DiploGM.models.board import Board

logger = logging.getLogger(__name__)

class RetreatsAdjudicator(Adjudicator):
    def __init__(self, board: Board):
        super().__init__(board)

    def _validate_orders(self) -> tuple[dict[str, set[Unit]], set[Unit]]:
        retreats_by_destination: dict[str, set[Unit]] = {}
        units_to_delete: set[Unit] = set()
        for unit in self._board.units:
            if unit != unit.province.dislodged_unit:
                continue

            if unit.order is None:
                unit.order = NMR()
                
            if not isinstance(unit.order, RetreatMove):
                logger.warning(f"Unit {unit.province} is doing an unexpected action during retreat phase")
                units_to_delete.add(unit)
                continue

            destination = unit.order.get_destination_and_coast()
            if unit.retreat_options is None or destination not in unit.retreat_options:
                units_to_delete.add(unit)
                continue

            if destination[0].name not in retreats_by_destination:
                retreats_by_destination[destination[0].name] = set()
            retreats_by_destination[destination[0].name].add(unit)

        return retreats_by_destination, units_to_delete

    def _handle_vassals(self):
        for player in self._board.players:
            if player.liege in player.vassals:
                other = player.liege
                if (player.get_class() != PlayerClass.KINGDOM) or (other.get_class() != PlayerClass.KINGDOM):
                    # Dual Monarchy breaks
                    for p in (player, other):
                        p.vassals = []
                        p.liege = None
            
            elif player.liege:
                if player.liege.get_class().value <= player.get_class().value:
                    liege = player.liege
                    player.liege = None
                    liege.vassals.remove(player)
                    player.build_orders.add(RebellionMarker(liege))

    def run(self) -> Board:
        retreats_by_destination, units_to_delete = self._validate_orders()

        for retreating_units in retreats_by_destination.values():
            if len(retreating_units) != 1:
                units_to_delete.update(retreating_units)
                continue

            (unit,) = retreating_units
            if not isinstance(unit.order, RetreatMove):
                units_to_delete.add(unit)
                continue

            destination_province, destination_coast = unit.order.get_destination_and_coast()

            unit.province.dislodged_unit = None
            unit.province = destination_province
            unit.coast = destination_coast
            destination_province.unit = unit
            if not destination_province.has_supply_center or self._board.turn.is_fall():
                self._board.change_owner(destination_province, unit.player)

        for unit in units_to_delete:
            unit.player.units.remove(unit)
            self._board.units.remove(unit)
            unit.province.dislodged_unit = None

        for unit in self._board.units:
            unit.order = None
            unit.retreat_options = None

        if self._board.turn.is_fall() and self.has_vassals:
            self._handle_vassals()

        return self._board