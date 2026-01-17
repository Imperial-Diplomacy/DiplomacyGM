from __future__ import annotations

import collections
import logging
from typing import TYPE_CHECKING

from DiploGM.adjudicator.adjudicator import Adjudicator, MapperInformation
from DiploGM.adjudicator.defs import (
    ResolutionState,
    Resolution,
    AdjudicableOrder,
    OrderType,
)
from DiploGM.adjudicator.validate_order import OrderValidity, is_valid_result, order_is_valid
from DiploGM.db import database
from DiploGM.models.order import NMR, Move, Core, Support

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.player import Player
    from DiploGM.models.unit import Unit

logger = logging.getLogger(__name__)

class MovesAdjudicator(Adjudicator):
    # Algorithm from https://diplom.org/Zine/S2009M/Kruijswijk/DipMath_Chp6.htm
    def __init__(self, board: Board):
        super().__init__(board)
 
        self.orders: set[AdjudicableOrder] = set()

        # run supports after everything else since illegal cores / moves should be treated as holds
        units = sorted(board.units, key=lambda unit: isinstance(unit.order, Support))
        for unit in units:
            self._validate_unit(unit)

        self.orders_by_province = {order.current_province.name: order for order in self.orders}
        self.moves_by_destination: dict[str, set[AdjudicableOrder]] = {}
        for order in self.orders:
            if order.type == OrderType.MOVE:
                if order.destination_province.name not in self.moves_by_destination:
                    self.moves_by_destination[order.destination_province.name] = set()
                self.moves_by_destination[order.destination_province.name].add(order)

        for order in self.orders:
            if order.type == OrderType.SUPPORT:
                self.orders_by_province[order.source_province.name].supports.add(order)
            if order.type == OrderType.CONVOY:
                self.orders_by_province[order.source_province.name].convoys.add(order)

        self._dependencies: list[AdjudicableOrder] = []

        self._find_convoy_kidnappings()

    def _validate_unit(self, unit: Unit):
        # Replace invalid orders with holds
        # Importantly, this includes supports for which the corresponding unit didn't make the same move
        # Same for convoys
        
        if unit.order is None:
            unit.order = NMR()

        failed: bool = False
        # indicates that an illegal move / core can't be support held
        not_supportable: bool = False

        # TODO clean up mapper info
        valid, reason = order_is_valid(unit.province, unit.order)
        if not is_valid_result(valid):
            logger.debug(f"Order for {unit} is invalid because {reason}")
            # Invalid moves are considered unsupportable. This deviates from standard adjudication rules
            # To follow standard rules, not_supportable should be false for Invalid moves but true for Mismatched moves
            if isinstance(unit.order, (Core, Move)):
                not_supportable = True
            failed = True

        order = AdjudicableOrder(unit)
        # Kinda hacky
        order.is_convoy = (valid == OrderValidity.VALID_WITH_CONVOY)
        if failed:
            self.failed_or_invalid_units.add(MapperInformation(unit))
            order.is_valid = False
            unit.order.has_failed = True
        if not_supportable:
            order.not_supportable = True

        self.orders.add(order)

    def _find_convoy_kidnappings(self):
        for order in self.orders:
            if order.type != OrderType.MOVE:
                continue

            if len(self.orders_by_province[order.source_province.name].convoys) == 0:
                continue

            # According to the 1971 ruling in DATC, the army only is kidnapped if
            # 1. the army's destination is moving back at it
            # 2.  the convoy isn't disrupted

            if order.destination_province.name in self.orders_by_province:
                attacked_order = self.orders_by_province[order.destination_province.name]
                if attacked_order.destination_province == order.source_province:
                    if self._adjudicate_convoys_for_order(order) == Resolution.SUCCEEDS:
                        order.is_convoy = True

    def run(self) -> Board:
        for order in self.orders:
            order.state = ResolutionState.UNRESOLVED
        for order in self.orders:
            self._resolve_order(order)
            order.get_original_order().has_failed = (order.resolution == Resolution.FAILS)
        if self.save_orders:
            database.get_connection().save_order_for_units(self._board, set(o.base_unit for o in self.orders))
        self._update_board()
        return self._board

    def _update_order(self, order: AdjudicableOrder):
        if order.type == OrderType.CORE and order.resolution == Resolution.SUCCEEDS:
            order.source_province.corer = order.country
        if order.type == OrderType.MOVE and order.resolution == Resolution.SUCCEEDS:
            logger.debug(f"Moving {order.source_province} to {order.destination_province}")
            if order.source_province.unit == order.base_unit:
                order.source_province.unit = None
            if order.source_province.dislodged_unit == order.base_unit:
                # We might have been dislodged by other move, but we shouldn't have been
                order.source_province.dislodged_unit = None
                order.base_unit.retreat_options = None
            # Dislodge whatever is there
            order.destination_province.dislodged_unit = order.destination_province.unit
            # see DATC 4.A.5
            if order.destination_province.dislodged_unit is not None:
                order.destination_province.dislodged_unit.add_retreat_options()
                if not order.is_convoy:
                    order.destination_province.dislodged_unit.remove_retreat_option(order.source_province)
            # Move us there
            order.base_unit.province = order.destination_province
            order.base_unit.coast = order.destination_coast
            order.destination_province.unit = order.base_unit
            if not order.destination_province.has_supply_center or self._board.turn.is_fall():
                self._board.change_owner(order.destination_province, order.country)
        if (order.type == OrderType.HOLD
            and order.resolution == Resolution.SUCCEEDS
            and order.source_province.dislodged_unit != order.base_unit):
            if not order.destination_province.has_supply_center or self._board.turn.is_fall():
                self._board.change_owner(order.destination_province, order.country)

    def _update_board(self):
        if not all(order.state == ResolutionState.RESOLVED for order in self.orders):
            raise RuntimeError("Cannot update board until all orders are resolved!")

        for order in self.orders:
            self._update_order(order)

        for province in self._board.provinces:
            if province.corer:
                if province.half_core == province.corer:
                    province.core = province.corer
                    province.half_core = None
                else:
                    province.half_core = province.corer
            else:
                province.half_core = None
            province.corer = None

        contested = self._find_contested_areas()

        for unit in self._board.units:
            unit.order = None
            if unit.retreat_options is not None:
                unit.remove_many_retreat_options(contested)

            # Update provinces again to capture SCs in fall where units held
            if (self._board.turn.is_fall()
                and unit.province.owner != unit.player):
                self._board.change_owner(unit.province, unit.player)

    def _find_contested_areas(self):
        bounces_and_occupied = set()
        for order in self.orders:
            if order.type != OrderType.MOVE:
                continue

            if order.is_convoy:
                # unsuccessful convoys don't bounce
                if order.resolution == Resolution.SUCCEEDS:
                    bounces_and_occupied.add(order.destination_province)
                continue

            # TODO duplicated head on code
            if order.destination_province.name in self.orders_by_province:
                attacked_order = self.orders_by_province[order.destination_province.name]
                if (
                    attacked_order.type == OrderType.MOVE
                    and attacked_order.destination_province == order.current_province
                ):
                    # if this is a head on attack, and the unit lost the head on, then the area is not contested
                    head_on = not attacked_order.is_convoy and not order.is_convoy
                    if head_on and order.resolution == Resolution.FAILS:
                        continue

            bounces_and_occupied.add(order.destination_province)

        for unit in self._board.units:
            bounces_and_occupied.add(unit.province)

        return bounces_and_occupied

    def _adjudicate_convoys_for_order(self, order: AdjudicableOrder) -> Resolution:
        # Breadth-first search to determine if there is a convoy connection for order.
        # Only considers it a success if it passes through at least one fleet to get to the destination
        assert order.type == OrderType.MOVE
        visited: set[str] = set()
        to_visit = collections.deque()
        to_visit.append(order.source_province)
        while 0 < len(to_visit):
            current = to_visit.popleft()
            # Have to pass through at least one convoying fleet
            if current != order.source_province and order.destination_province in current.adjacent:
                return Resolution.SUCCEEDS

            visited.add(current.name)

            adjacent_convoys = {
                convoy_order for convoy_order in order.convoys if convoy_order.current_province in current.adjacent
            }
            for convoy in adjacent_convoys:
                if convoy.current_province.name in visited:
                    continue
                if self._resolve_order(convoy) == Resolution.SUCCEEDS:
                    to_visit.append(convoy.current_province)
        return Resolution.FAILS

    def _adjudicate_order(self, order: AdjudicableOrder) -> Resolution:
        if order.type == OrderType.HOLD:
            # Resolution is arbitrary for holds; they don't do anything
            return Resolution.SUCCEEDS
        elif order.type == OrderType.CORE or order.type == OrderType.SUPPORT:
            # Both these orders fail if attacked by nation, even if that order isn't successful
            moves_here = self.moves_by_destination.get(order.current_province.name, set()) - {order}
            for move_here in moves_here:
                # coring should fail even if the attack comes from the same nation
                if move_here.country == order.country and order.type == OrderType.SUPPORT:
                    continue
                if not move_here.is_valid:
                    continue
                if not move_here.is_convoy:
                    # If we are being attacked by the place we are supporting against,
                    # our support only fails if they succeed
                    if (move_here.current_province != order.destination_province
                        or self._resolve_order(move_here) == Resolution.SUCCEEDS):
                        return Resolution.FAILS
                    continue
                # decide to fail convoys that cut support to their attack
                if (
                    self._adjudicate_convoys_for_order(move_here) == Resolution.SUCCEEDS
                    and move_here.current_province != order.destination_province
                ):
                    return Resolution.FAILS
            return Resolution.SUCCEEDS
        elif order.type == OrderType.CONVOY:
            moves_here = self.moves_by_destination.get(order.current_province.name, set())
            for move_here in moves_here:
                # see https://webdiplomacy.net/doc/DATC_v3_0.html#5.D
                if self._adjudicate_order(move_here) == Resolution.SUCCEEDS:
                    return Resolution.FAILS
            return Resolution.SUCCEEDS
        # Algorithm from https://diplom.org/Zine/S2009M/Kruijswijk/DipMath_Chp2.htm
        elif order.type == OrderType.MOVE:
            return self._adjudicate_move_order(order)
        raise ValueError("Unknown order type for adjudication")

    def _count_strength(self, order: AdjudicableOrder, attacked_country: Player | None = None) -> int:
        strength = 1
        for support in order.supports:
            if self._resolve_order(support) == Resolution.SUCCEEDS and attacked_country != support.country:
                strength += 1
        return strength

    def _adjudicate_move_order(self, order: AdjudicableOrder) -> Resolution:
        # check that convoy path work
        if order.is_convoy and self._adjudicate_convoys_for_order(order) == Resolution.FAILS:
            return Resolution.FAILS

        # X -> Z, Y -> Z scenario, prevent strength
        orders_to_overcome = self.moves_by_destination[order.destination_province.name] - {order}
        # X -> Y, Y -> Z scenario
        attacked_order: AdjudicableOrder | None = None

        head_on = False
        if order.destination_province.name in self.orders_by_province:
            attacked_order = self.orders_by_province[order.destination_province.name]

            if attacked_order.type == OrderType.MOVE and attacked_order.destination_province == order.current_province:
                # only head on if not convoy
                head_on = not attacked_order.is_convoy and not order.is_convoy

        attack_strength = 1
        attacked_move = (
            attacked_order == None
            or (attacked_order.type == OrderType.MOVE
                and self._resolve_order(attacked_order) == Resolution.SUCCEEDS)
        )

        if attacked_order and (head_on or not attacked_move):
            attacked_country = attacked_order.country

            if attacked_country == order.country:
                return Resolution.FAILS

            attack_strength = self._count_strength(order, attacked_country)

            opponent_strength = 1
            # count supports if it wasn't a failed move
            if head_on or (attacked_order.type != OrderType.MOVE and not attacked_order.not_supportable):
                opponent_strength = self._count_strength(attacked_order)

            if attack_strength <= opponent_strength:
                return Resolution.FAILS
        else:
            attack_strength = self._count_strength(order)

            # If A -> B, and B beats C head on then C can't affect A
            if attacked_order is not None and not attacked_order.is_convoy:
                orders_to_overcome = {
                    order
                    for order in orders_to_overcome
                    if order.source_province != attacked_order.destination_province or order.is_convoy
                }

        for opponent in orders_to_overcome:
            if not opponent.is_valid:
                continue
            # don't need to overcome failed convoys
            if opponent.is_convoy and self._adjudicate_convoys_for_order(opponent) == Resolution.FAILS:
                continue
            prevent_strength = self._count_strength(opponent)
            if attack_strength <= prevent_strength:
                return Resolution.FAILS

        return Resolution.SUCCEEDS

    def _resolve_order(self, order: AdjudicableOrder) -> Resolution:
        # logger.debug(f"Adjudicating order {order}")
        if order.state == ResolutionState.RESOLVED:
            return order.resolution

        if order.state == ResolutionState.GUESSING:
            if order not in self._dependencies:
                self._dependencies.append(order)
            return order.resolution
            
        if not order.is_valid:
            order.resolution = Resolution.FAILS
            order.state = ResolutionState.RESOLVED
            return order.resolution

        old_dependency_count = len(self._dependencies)
        # Guess that this fails
        order.resolution = Resolution.FAILS
        order.state = ResolutionState.GUESSING

        first_result = self._adjudicate_order(order)

        if old_dependency_count == len(self._dependencies):
            # Adjudication has not introduced new dependencies, see backup rule
            if order.state != ResolutionState.RESOLVED:
                order.resolution = first_result
                order.state = ResolutionState.RESOLVED
            return first_result

        if self._dependencies[old_dependency_count] != order:
            # We depend on a guess, but not our own guess
            self._dependencies.append(order)
            order.resolution = first_result
            # State remains Guessing
            return first_result

        # We depend on our own guess; reset all dependencies
        for other_unit in self._dependencies[old_dependency_count:]:
            other_unit.state = ResolutionState.UNRESOLVED
        self._dependencies = self._dependencies[:old_dependency_count]

        # Guess that this succeeds
        order.resolution = Resolution.SUCCEEDS
        order.state = ResolutionState.GUESSING

        second_result = self._adjudicate_order(order)

        if first_result == second_result:
            for other_unit in self._dependencies[old_dependency_count:]:
                other_unit.state = ResolutionState.UNRESOLVED
            self._dependencies = self._dependencies[:old_dependency_count]
            order.state = ResolutionState.RESOLVED
            order.resolution = first_result
            return first_result

        self._backup_rule(old_dependency_count)

        return self._resolve_order(order)

    def _backup_rule(self, old_dependency_count):
        # Deal with paradoxes and circular dependencies
        orders = self._dependencies[old_dependency_count:]
        self._dependencies = self._dependencies[:old_dependency_count]
        logger.warning(f"I think there's a move paradox involving these moves: {[str(x) for x in orders]}")
        # Szykman rule - If any of these orders is a convoy, fail the order
        apply_szykman = False
        for order in orders:
            if order.type == OrderType.CONVOY:
                apply_szykman = True
                break

        if apply_szykman:
            for order in orders:
                if order.type == OrderType.CONVOY:
                    order.resolution = Resolution.FAILS
                    order.state = ResolutionState.RESOLVED
                else:
                    order.state = ResolutionState.UNRESOLVED
            return
        # Circular dependencies
        for order in orders:
            if order.type == OrderType.MOVE:
                order.resolution = Resolution.SUCCEEDS
                order.state = ResolutionState.RESOLVED
            else:
                order.state = ResolutionState.UNRESOLVED