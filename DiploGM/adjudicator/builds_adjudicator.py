"""Adjudicator for handling Adjustment phase."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from DiploGM.adjudicator.adjudicator import Adjudicator
from DiploGM.models.player import Player
from DiploGM.models.order import (
    Build,
    Disband,
    TransformBuild,
    Disown,
    Vassal,
    Liege,
    Defect,
    DualMonarchy,
    RebellionMarker
)
from DiploGM.models.province import ProvinceType
from DiploGM.models.unit import UnitType

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.order import Order
    from DiploGM.models.province import Province

logger = logging.getLogger(__name__)

class BuildsAdjudicator(Adjudicator):
    """Adjudicator for handling Adjustment phase."""

    def _vassal_adju(self):
        new_vassals: dict[Player, list[Player]] = {}
        new_lieges: dict[Player, Player | None] = {}
        for player in self._board.players:
            scs = len([c for vassal in player.vassals for c in vassal.centers])
            new_vassals[player] = player.vassals.copy()
            if scs > len(player.centers):
                for order in player.vassal_orders.values():
                    if isinstance(order, Disown) and order.player in player.vassals:
                        new_vassals[player].remove(order.player)
                    scs2 = len([c for vassal in new_vassals[player] for c in vassal.centers])
                    if scs2 > len(player.centers):
                        new_vassals[player] = []
            else:
                for order in player.vassal_orders.values():
                    vassal = order.player
                    can_add_vassal = (isinstance(order, Vassal)
                                      and player in vassal.vassal_orders
                                      and isinstance(vassal.vassal_orders[player], Liege)
                                      and (not vassal.liege
                                           or isinstance(player.vassal_orders.get(vassal.liege), RebellionMarker)))
                    if can_add_vassal:
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
                if (isinstance(order, DualMonarchy)
                    and player in order.player.vassal_orders
                    and isinstance(order.player.vassal_orders[player], DualMonarchy)):
                    other = order.player
                    if other.liege is None and not other.vassals and player.liege is None and not player.vassals:
                        other.vassals = [player]
                        player.vassals = [other]
                        other.liege = player
                        player.liege = other


        for player in self._board.players:
            player.points += len(player.centers)
            if player.liege not in player.vassals:
                for vassal in player.vassals:
                    player.points += len(vassal.centers)
                    player.points += len([c for subvassal in vassal.vassals for c in subvassal.centers])
            else:
                player.points += len(player.liege.centers)
                continue

            if player.liege:
                player.points += len(player.liege.centers) // 2

    def _adjudicate_build(self, order: Build, player: Player) -> int:
        # ignore coast specifications for army
        if (order.unit_type == UnitType.FLEET and order.province.is_landlocked()):
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
        if not order.province.can_build(self.parameters.get("build_options")):
            logger.warning(f"Skipping {order}; build order does not meet build requirements")
            return 0
        self._board.create_unit(order.unit_type, player, order.province, order.coast, None)
        return -1

    def _adjudicate_transform(self, order: TransformBuild):
        if order.province.unit is None:
            logger.warning(f"Skipping {order}; there is no unit there to transform")
        elif not order.province.has_supply_center:
            logger.warning(f"Skipping {order}; tried to transform in a province without a supply center")
        elif order.province.type == ProvinceType.SEA:
            logger.warning(f"Skipping {order}; tried to transform in a sea province")
        elif order.province.is_landlocked():
            logger.warning(f"Skipping {order}; tried to transform in an inland province")
        elif (order.province.unit.unit_type == UnitType.ARMY
                and order.province.get_multiple_coasts()
                and order.coast not in order.province.get_multiple_coasts()):
            logger.warning(f"Skipping {order}; tried to transform to an invalid coast")
        else:
            new_unit_type = UnitType.FLEET if order.province.unit.unit_type == UnitType.ARMY else UnitType.ARMY
            order.province.unit.unit_type = new_unit_type
            order.province.unit.coast = order.coast

    def _adjudicate_order(self, order: Order, available_builds: int, player: Player) -> int:
        if isinstance(order, Build):
            if available_builds <= 0:
                return 0
            return self._adjudicate_build(order, player)

        if available_builds < 0 and isinstance(order, Disband):
            if order.province.unit is None:
                logger.warning(f"Skipping {order}; there is no unit there to disband")
                return 0
            self._board.delete_unit(order.province)
            return 1

        if isinstance(order, TransformBuild):
            self._adjudicate_transform(order)

        return 0

    def _adjudicate_civil_disorder(self, player: Player, needed_disbands: int):
        """Uses the following algorithm to determine civil disorder disbands:
        1. Furthest from an owned supply center
        2. Furthest from an owned core
        3. Alphabetical order"""
        unit_distances: dict[Province, tuple[int, int]] = {}
        supply_centers = sorted(player.centers, key=lambda p: p.name)
        if len(supply_centers) == 0:
            for unit in player.units:
                self._board.delete_unit(unit.province)
            return

        owned_cores = {c for c in supply_centers if c.core_data.core == player}
        for unit in player.units:
            shortest_core_distance = min(unit.province.get_distance(c) for c in owned_cores) if owned_cores else 0
            shortest_sc_distance = min(unit.province.get_distance(c, shortest_core_distance) for c in supply_centers)
            unit_distances[unit.province] = (shortest_sc_distance, shortest_core_distance)

        sorted_units = sorted(player.units, key=lambda u: (unit_distances[u.province][0],
                                                           unit_distances[u.province][1]), reverse=True)
        for i in range(needed_disbands):
            self._board.delete_unit(sorted_units[i].province)

    def run(self) -> Board:
        for player in self._board.players:
            available_builds = len(player.centers) - len(player.units)
            if available_builds == 0:
                continue
            for order in player.build_orders:
                available_builds += self._adjudicate_order(order, available_builds, player)
            if available_builds < 0:
                logger.warning(f"Player {player.get_name()} disbanded less orders than they should have")
                self._adjudicate_civil_disorder(player, -available_builds)

        if self.parameters.get("has_vassals"):
            self._vassal_adju()

        for player in self._board.players:
            player.build_orders = set()
            player.waived_orders = 0
        return self._board
