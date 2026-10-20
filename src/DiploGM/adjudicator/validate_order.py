"""This module contains validation logic for orders during movement phases."""

from __future__ import annotations

import collections
from enum import Enum
from typing import TYPE_CHECKING

from DiploGM.models.adjacency import Terrain
from DiploGM.models.order import (
    Order,
    Hold,
    Move,
    Support,
    ConvoyTransport,
    Core,
    Transform,
    RetreatMove,
    RetreatDisband,
    NMR,
)
from DiploGM.models.province import ProvinceType
from DiploGM.models.unit import Unit

if TYPE_CHECKING:
    from DiploGM.models.province import Province


class OrderValidity(Enum):
    """How valid an order is.
    Could be valid, valid but requires a convoy, invalid due to mismatched orders
    (e.g. support order doesn't match move order), or invalid."""

    VALID = 0
    VALID_WITH_CONVOY = 1
    MISMATCHED_ORDER = 2
    INVALID = 3


def is_valid_result(result: OrderValidity | tuple[OrderValidity, str | None]) -> bool:
    """Helper function to check if result of order_is_valid is valid or would be with a convoy."""
    if isinstance(result, tuple):
        result = result[0]
    return result == OrderValidity.VALID or result == OrderValidity.VALID_WITH_CONVOY


def convoy_is_possible(
    start: Province, end: Province, check_fleet_orders: bool = True
) -> bool:
    """
    Breadth-first search to figure out if start -> end is possible passing over fleets

    :param start: Start province
    :param end: End province
    :param check_fleet_orders: if True, check that the fleets along the way are actually convoying the unit
    :return: True if there are fleets connecting start -> end
    """
    visited: set[str] = set()
    to_visit: collections.deque[Province] = collections.deque()
    to_visit.append(start)
    while 0 < len(to_visit):
        current = to_visit.popleft()

        if current.name in visited:
            continue
        visited.add(current.name)

        for adjacent_province in current.adjacencies.get_all():
            if adjacent_province == end:
                return True
            adjacent_could_convoy = (
                adjacent_province.can_convoy
                and adjacent_province.unit is not None
                and adjacent_province.unit.unit_type.can_convoy
            )
            adjacent_did_convoy = (
                adjacent_could_convoy
                and adjacent_province.unit is not None
                and isinstance(adjacent_province.unit.order, ConvoyTransport)
                and (adjacent_province.unit.order.source is start)
                and (adjacent_province.unit.order.destination is end)
            )
            if adjacent_could_convoy and (
                not check_fleet_orders or adjacent_did_convoy
            ):
                to_visit.append(adjacent_province)

    return False


def _validate_coastal_move(
    province: Province,
    order: Move | RetreatMove,
    unit: Unit,
    strict_coast_movement: bool,
) -> tuple[OrderValidity, str | None]:
    destination_coast = order.destination_coast if strict_coast_movement else None
    if order.destination not in province.adjacencies.get_all(
        terrain=Terrain.COAST, coast=unit.coast
    ):
        return (
            OrderValidity.INVALID,
            f"{province.get_name(unit.coast)} does not border {order.get_destination_str()}",
        )
    if not strict_coast_movement:
        return OrderValidity.VALID, None
    if (
        destination_coast is not None
        and destination_coast
        not in province.adjacencies.get_coasts(order.destination, unit.coast)
    ):
        return (
            OrderValidity.INVALID,
            f"{province.get_name(unit.coast)} does not border {order.get_destination_str()}",
        )
    if strict_coast_movement and not destination_coast:
        reachable_coasts = unit.province.adjacencies.get_coasts(
            order.destination, unit.coast
        )
        if len(reachable_coasts) > 1:
            return (
                OrderValidity.INVALID,
                f"{province} and {order.destination} have multiple coastal paths",
            )
        if reachable_coasts:
            order.destination_coast = reachable_coasts.pop()
    return OrderValidity.VALID, None


def _validate_move_order(
    province: Province, order: Move | RetreatMove, strict_coast_movement: bool
) -> tuple[OrderValidity, str | None]:
    unit = province.unit
    assert unit is not None
    destination_province = order.destination
    if destination_province.is_impassable:
        return OrderValidity.INVALID, "Cannot move to an impassable province"
    adjacency = province.adjacencies.get(destination_province)
    if adjacency is None:
        return (
            OrderValidity.INVALID,
            f"{province} does not border {destination_province}",
        )
    if (
        Terrain.LAND in unit.unit_type.moves_on
        and Terrain.SEA in unit.unit_type.moves_on
    ):
        return OrderValidity.VALID, None
    terrain_intersection = unit.unit_type.moves_on & adjacency.terrain
    if not terrain_intersection:
        return (
            OrderValidity.INVALID,
            f"{unit.unit_type.name} cannot move from {province} to {destination_province}",
        )
    if Terrain.COAST in terrain_intersection:
        valid, reason = _validate_coastal_move(
            province, order, unit, strict_coast_movement
        )
        if valid != OrderValidity.VALID:
            return valid, reason

    if isinstance(order, RetreatMove) and destination_province.unit is not None:
        return OrderValidity.INVALID, "Cannot retreat to occupied provinces"
    return OrderValidity.VALID, None


def _validate_convoymove_order(
    province: Province, order: Move
) -> tuple[OrderValidity, str | None]:
    unit = province.unit
    assert unit is not None
    destination_province = order.destination
    if not unit.unit_type.can_be_convoyed:
        return OrderValidity.INVALID, "This unit cannot be convoyed"
    if destination_province.type == ProvinceType.SEA:
        return OrderValidity.INVALID, "Cannot convoy to a sea space"
    if destination_province == unit.province:
        return OrderValidity.INVALID, "Cannot convoy unit to its previous space"
    if convoy_is_possible(province, destination_province, check_fleet_orders=True):
        return OrderValidity.VALID_WITH_CONVOY, None
    if convoy_is_possible(destination_province, province, check_fleet_orders=False):
        return (
            OrderValidity.MISMATCHED_ORDER,
            f"A convoy path exists from {destination_province} to {province}, but units did not convoy",
        )
    if not convoy_is_possible(province, destination_province):
        return (
            OrderValidity.INVALID,
            f"No valid convoy path from {province} to {destination_province}",
        )
    return OrderValidity.VALID, None


def _validate_transform_order(
    province: Province, order: Transform
) -> tuple[OrderValidity, str | None]:
    assert province.unit is not None
    if not province.has_supply_center:
        return OrderValidity.INVALID, "Transformation must be done in a supply center"
    if province.owner != province.unit.player:
        return OrderValidity.INVALID, "Units can only transform in owned supply centers"
    if (new_type := province.unit.unit_type.transforms_to) is None:
        return OrderValidity.INVALID, "This unit cannot transform"
    if province.is_landlocked() and Terrain.LAND not in new_type.moves_on:
        return OrderValidity.INVALID, "Cannot transform in an inland province"
    if (
        Terrain.COAST in new_type.moves_on
        and province.adjacencies.coasts
        and order.destination_coast not in province.adjacencies.coasts
    ):
        return OrderValidity.INVALID, "Unit needs to transform to a valid coast"
    return OrderValidity.VALID, None


def _validate_convoy_order(
    province: Province, order: ConvoyTransport
) -> tuple[OrderValidity, str | None]:
    unit = province.unit
    assert unit is not None
    if not unit.unit_type.can_convoy:
        return OrderValidity.INVALID, "This unit cannot convoy"
    if not province.can_convoy:
        return OrderValidity.INVALID, "Units in this province cannot convoy"
    source_unit = order.source.unit
    if not isinstance(source_unit, Unit):
        return OrderValidity.INVALID, "There is no unit to convoy"
    if (
        not isinstance(source_unit.order, Move)
        or source_unit.order.destination != order.destination
    ):
        return (
            OrderValidity.MISMATCHED_ORDER,
            f"Convoyed unit {order.source} did not make corresponding order",
        )
    valid_move, reason = order_is_valid(
        order.source, Move(destination=order.destination), strict_coast_movement=False
    )
    if not is_valid_result(valid_move):
        return valid_move, reason
    # Check we are actually part of the convoy chain
    destination_province = order.destination
    if not convoy_is_possible(order.source, destination_province):
        return (
            OrderValidity.INVALID,
            f"No valid convoy path from {order.source} to {province}",
        )
    return OrderValidity.VALID, None


def _validate_support_order(
    province: Province, order: Support
) -> tuple[OrderValidity, str | None]:
    source_unit = order.source.unit
    destination = order.destination
    if not isinstance(source_unit, Unit):
        return OrderValidity.INVALID, "There is no unit to support"

    move_valid, _ = order_is_valid(province, Move(destination=destination), False)
    if move_valid != OrderValidity.VALID:
        return OrderValidity.INVALID, "Cannot support somewhere you can't move to"
    if province.adjacencies.is_difficult(destination):
        return (
            OrderValidity.INVALID,
            f"Cannot support to {destination} from {province} due to difficult adjacency",
        )
    is_support_hold = order.source == destination
    source_to_destination_valid = is_support_hold or is_valid_result(
        order_is_valid(order.source, Move(destination=destination), False)
    )

    if not source_to_destination_valid:
        return OrderValidity.INVALID, "Supported unit can't reach destination"

    # if move is invalid then it doesn't go through
    if is_support_hold:
        if source_unit.order is not None and not source_unit.order.is_support_holdable:
            return (
                OrderValidity.INVALID,
                f"Supported unit {order.source} cannot be supported",
            )
        return OrderValidity.VALID, None

    mismatched_reason = ""
    if not isinstance(source_unit.order, Move):
        mismatched_reason = "did not make a move order"
    elif source_unit.order.destination != destination:
        mismatched_reason = "moved to a different province"
    elif (
        order.destination_coast is not None
        and source_unit.order.destination_coast != order.destination_coast
    ):
        mismatched_reason = "moved to a different coast"
    if mismatched_reason:
        return (
            OrderValidity.MISMATCHED_ORDER,
            f"Supported unit {order.source} {mismatched_reason}",
        )

    return OrderValidity.VALID, None


def _validate_core_order(
    province: Province, core_options: dict
) -> tuple[OrderValidity, str | None]:
    assert province.unit is not None
    if not province.has_supply_center:
        return (
            OrderValidity.INVALID,
            f"{province} does not have a supply center to core",
        )
    if province.owner != province.unit.player:
        return OrderValidity.INVALID, "Units can only core in owned supply centers"
    if (
        adj_requirement := core_options.get("require_adjacent_ownership", "false")
    ) != "false":
        for p in province.adjacencies.get_all():
            if p.owner == province.unit.player:
                continue
            if adj_requirement == "all" and p.type != ProvinceType.SEA:
                return (
                    OrderValidity.INVALID,
                    "Cannot core if there are unowned adjacent provinces",
                )
            if adj_requirement == "sc" and p.has_supply_center:
                return (
                    OrderValidity.INVALID,
                    "Cannot core if there are unowned adjacent supply centers",
                )
    if (
        unit_requirement := core_options.get("require_no_enemy_units", "false")
    ) != "false":
        for p in province.adjacencies.get_all():
            if p.unit is None or p.unit.player == province.unit.player:
                continue
            if unit_requirement == "all":
                return (
                    OrderValidity.INVALID,
                    "Cannot core if there are adjacent enemy units",
                )
            if unit_requirement == "sc" and p.has_supply_center:
                return (
                    OrderValidity.INVALID,
                    "Cannot core if there are adjacent enemy units in supply centers",
                )
    return OrderValidity.VALID, None


def order_is_valid(
    province: Province,
    order: Order,
    strict_coast_movement=True,
    core_options: dict | None = None,
) -> tuple[OrderValidity, str | None]:
    """
    Checks if order from given location is valid for configured board

    :param province: Province the order originates from
    :param order: Order to check
    :param potential_convoy: Defaults False. When True, will try a Move as a convoy if necessary
    :param strict_coast_movement: Defaults True. Checks movement regarding coasts, should be false when checking
                                    for support holds.
    :return: tuple(result, reason)
        - bool result is True if the order is valid, False otherwise
        - str reason is "convoy" if order is valid but requires a convoy, provides reasoning if invalid
    """
    order_functions = {
        Transform: _validate_transform_order,
        ConvoyTransport: _validate_convoy_order,
        Support: _validate_support_order,
    }
    if order is None:
        return OrderValidity.INVALID, "Order is missing"

    if isinstance(order, (Support, ConvoyTransport)) and order.source.unit is None:
        return (
            OrderValidity.INVALID,
            f"No unit for supporting / convoying at {order.source}",
        )
    if province.unit is None:
        return OrderValidity.INVALID, f"There is no unit in {province}"

    if type(order) in order_functions:
        return order_functions[type(order)](province, order)
    if isinstance(order, (Hold, RetreatDisband, NMR)):
        return OrderValidity.VALID, None
    if isinstance(order, Core):
        return _validate_core_order(province, core_options or {})
    if isinstance(order, (Move, RetreatMove)):
        valid, reason = _validate_move_order(province, order, strict_coast_movement)
        if (
            valid != OrderValidity.VALID
            and isinstance(order, Move)
            and province.unit.unit_type.can_be_convoyed
        ):
            # Try convoy validation if move is invalid
            return _validate_convoymove_order(province, order)
        return valid, reason

    return OrderValidity.INVALID, f"Unknown move type: {order.__class__.__name__}"
