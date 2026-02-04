from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from DiploGM.adjudicator.adjudicator import Adjudicator
from DiploGM.models.player import Player
from DiploGM.models.order import (
    Build,
    Disband,
    Disown,
    Vassal,
    Liege,
    Defect,
    DualMonarchy,
    RebellionMarker
)
from DiploGM.models.unit import UnitType

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.order import Order

logger = logging.getLogger(__name__)

class BuildsAdjudicator(Adjudicator):
    def __init__(self, board: Board):
        super().__init__(board)

    def _vassal_adju(self):
        new_vassals: dict[Player, list[Player]] = {}
        new_lieges: dict[Player, Player | None] = {}
        for player in self._board.players:
            scs = 0
            for vassal in player.vassals:
                scs += len(vassal.centers)
            new_vassals[player] = player.vassals.copy()
            if scs > len(player.centers):
                for order in player.vassal_orders.values():
                    if isinstance(order, Disown) and order.player in player.vassals:
                        new_vassals[player].remove(order.player)
                    scs2 = 0
                    for vassal in new_vassals[player]:
                        scs2 += len(vassal.centers)
                    if scs2 > len(player.centers):
                        new_vassals[player] = []
            else:
                for order in player.vassal_orders.values():
                    if isinstance(order, Vassal):
                        vassal = order.player
                        if player in vassal.vassal_orders and isinstance(vassal.vassal_orders[player], Liege):
                            if (not vassal.liege) or (vassal.liege in player.vassal_orders and isinstance(player.vassal_orders[vassal.liege], RebellionMarker)):
                                new_vassals[player].append(vassal)
                
        for player in self._board.players:
            new_liege = None
            overcommited = False
            for liege in self._board.players:
                if player in new_vassals[liege]:
                    if new_liege is None:
                        new_liege = liege
                    else:
                        overcommited = True
                        break
            if overcommited:
                for liege in self._board.players:
                    if player in new_vassals[liege]:
                        new_vassals[liege].remove(player)
            for order in player.vassal_orders:
                if isinstance(order, Defect) and player in new_vassals[order.player]:
                    new_vassals[order.player].remove(player)
                    new_liege = None
            new_lieges[player] = new_liege
            
        for player in self._board.players:
            player.liege = new_lieges[player]
            player.vassals = new_vassals[player]
        for player in self._board.players:
            for order in player.vassal_orders.values():
                if isinstance(order, DualMonarchy) and player in order.player.vassal_orders and isinstance(order.player.vassal_orders[player], DualMonarchy):
                    other = order.player
                    if other.liege == None and not other.vassals and player.liege == None and not player.vassals:
                        other.vassals = [player]
                        player.vassals = [other]
                        other.liege = player
                        player.liege = other


        for player in self._board.players:
            player.points += len(player.centers)
            if player.liege not in player.vassals:
                for vassal in player.vassals:
                    player.points += len(vassal.centers)
                    for subvassal in vassal.vassals:
                        player.points += len(subvassal.centers)
            else:
                player.points += len(player.liege.centers)
                continue

            if player.liege:
                player.points += len(player.liege.centers) // 2

    def _adjudicate_order(self, order: Order, available_builds: int, player: Player) -> int:
        if available_builds > 0 and isinstance(order, Build):
            # ignore coast specifications for army
            if (order.unit_type == UnitType.FLEET and not order.province.fleet_adjacent):
                logger.warning(f"Skipping {order}; tried building an inland fleet")
                return 0
            if (order.unit_type == UnitType.FLEET
                and order.province.get_multiple_coasts()
                and order.coast not in order.province.get_multiple_coasts()):
                logger.warning(f"Skipping {order}; someone didn't specify a valid coast")
                return 0
            if order.province.unit is not None:
                logger.warning(f"Skipping {order}; there is already a unit there")
                return 0
            if not order.province.has_supply_center or order.province.owner != player:
                logger.warning(f"Skipping {order}; tried to build in non-sc, non-owned")
                return 0
            if order.province.core != player and self.build_options != "anywhere":
                logger.warning(f"Skipping {order}; tried to build in non-core")
                return 0
            self._board.create_unit(order.unit_type, player, order.province, order.coast, None)
            return -1

        if available_builds < 0 and isinstance(order, Disband):
            if order.province.unit is None:
                logger.warning(f"Skipping {order}; there is no unit there to disband")
                return 0
            self._board.delete_unit(order.province)
            return 1
        return 0

    def run(self) -> Board:
        for player in self._board.players:
            available_builds = len(player.centers) - len(player.units)
            if available_builds == 0:
                continue
            for order in player.build_orders:
                available_builds += self._adjudicate_order(order, available_builds, player)
            if available_builds < 0:
                logger.warning(f"Player {player.get_name()} disbanded less orders than they should have")

        if self.has_vassals:
            self._vassal_adju()

        for player in self._board.players:
            player.build_orders = set()
            player.waived_orders = 0
        return self._board
