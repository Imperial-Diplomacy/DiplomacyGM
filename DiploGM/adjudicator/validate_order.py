from __future__ import annotations

import collections
from typing import TYPE_CHECKING

from DiploGM.models.order import Order, Hold, Move, Support, ConvoyTransport, Core, RetreatMove, RetreatDisband, NMR
from DiploGM.models.province import ProvinceType
from DiploGM.models.unit import Unit, UnitType

if TYPE_CHECKING:
    from DiploGM.models.province import Province

def convoy_is_possible(start: Province, end: Province) -> bool:
    """
    Breadth-first search to figure out if start -> end is possible passing over fleets

    :param start: Start province
    :param end: End province
    :param check_fleet_orders: if True, check that the fleets along the way are actually convoying the unit
    :return: True if there are fleets connecting start -> end
    """
    visited: set[str] = set()
    to_visit = collections.deque()
    to_visit.append(start)
    while 0 < len(to_visit):
        current = to_visit.popleft()

        if current.name in visited:
            continue
        visited.add(current.name)

        for adjacent_province in current.adjacent:
            if adjacent_province == end:
                return True
            if (adjacent_province.type == ProvinceType.SEA
                and adjacent_province.unit is not None
                and adjacent_province.unit.unit_type == UnitType.FLEET
                and (fleet_order := adjacent_province.unit.order) is not None
                and isinstance(fleet_order, ConvoyTransport)
                and fleet_order.source is start
                and fleet_order.destination is end):
                to_visit.append(adjacent_province)

    return False

def _validate_move_army(province: Province, destination_province: Province) -> tuple[bool, str | None]:
    if destination_province not in province.adjacent:
        return False, f"{province} does not border {destination_province}"
    if destination_province.type == ProvinceType.SEA:
        return False, "Armies cannot move to sea provinces"
    return True, None


def _validate_move_fleet(province: Province, order: Move | RetreatMove, unit: Unit, strict_coast_movement: bool) -> tuple[bool, str | None]:
    destination_coast = order.destination_coast if strict_coast_movement else None
    if not province.is_coastally_adjacent(order.get_destination_and_coast(), unit.coast):
        return False, f"{province.get_name(unit.coast)} does not border {order.get_destination_str()}"
    if strict_coast_movement and not destination_coast:
        reachable_coasts = {c for c in order.destination.get_multiple_coasts() if province.is_coastally_adjacent((order.destination, c), unit.coast)}
        if len(reachable_coasts) > 1:
            return False, f"{province} and {order.destination} have multiple coastal paths"
        if reachable_coasts:
            order.destination_coast = reachable_coasts.pop()
    return True, None

def _validate_move_order(province: Province, order: Move | RetreatMove, strict_coast_movement: bool) -> tuple[bool, str | None]:
    unit = province.unit
    assert unit is not None
    destination_province = order.destination
    if unit.unit_type == UnitType.ARMY:
        valid, reason = _validate_move_army(province, destination_province)
        if not valid:
            return valid, reason
    elif unit.unit_type == UnitType.FLEET:
        valid, reason = _validate_move_fleet(province, order, unit, strict_coast_movement)
        if not valid:
            return valid, reason
    else:
        raise ValueError("Unknown type of unit. Something has broken in the bot. Please report this")

    if isinstance(order, RetreatMove) and destination_province.unit is not None:
        return False, "Cannot retreat to occupied provinces"
    return True, None

def _validate_convoymove_order(province: Province, order: Move) -> tuple[bool, str | None]:
    unit = province.unit
    assert unit is not None
    if unit.unit_type != UnitType.ARMY:
        return False, "Only armies can be convoyed"
    destination_province = order.destination
    if destination_province.type == ProvinceType.SEA:
        return False, "Cannot convoy to a sea space"
    if destination_province == unit.province:
        return False, "Cannot convoy army to its previous space"
    if not convoy_is_possible(province, destination_province):
        return False, f"No valid convoy path from {province} to {order.destination}"
    return True, "convoy"

def _validate_convoy_order(province: Province, order: ConvoyTransport) -> tuple[bool, str | None]:
    unit = province.unit
    assert unit is not None
    if unit.unit_type != UnitType.FLEET:
        return False, "Only fleets can convoy"
    source_unit = order.source.unit
    if not isinstance(source_unit, Unit):
        return False, "There is no unit to convoy"
    if not isinstance(source_unit.order, Move) or source_unit.order.destination != order.destination:
        return False, f"Convoyed unit {order.source} did not make corresponding order"
    valid_move, reason = order_is_valid(
        order.source, Move(order.destination), potential_convoy=True
    )
    if not valid_move:
        return valid_move, reason
    # Check we are actually part of the convoy chain
    destination_province = order.destination
    if not convoy_is_possible(order.source, destination_province):
        return False, f"No valid convoy path from {order.source} to {province}"
    return True, None

def _validate_support_order(province: Province, order: Support) -> tuple[bool, str | None]:
    source_unit = order.source.unit
    if not isinstance(source_unit, Unit):
        return False, "There is no unit to support"
    if isinstance(source_unit.order, Core) and order_is_valid(order.source, source_unit.order):
        return False, "Cannot support a unit that is coring"

    move_valid, _ = order_is_valid(province, Move(order.destination), potential_convoy=True, strict_coast_movement=False)
    if not move_valid:
        return False, "Cannot support somewhere you can't move to"

    is_support_hold = order.source == order.destination
    source_to_destination_valid = (
        is_support_hold
        or order_is_valid(order.source, Move(order.destination), potential_convoy=True, strict_coast_movement=False)[0]
    )

    if not source_to_destination_valid:
        return False, "Supported unit can't reach destination"

    # if move is invalid then it doesn't go through
    if is_support_hold:
        if isinstance(source_unit.order, Move):
            return False, f"Supported unit {order.source} made a move order"
        return True, None

    if not isinstance(source_unit.order, Move):
        return False, f"Supported unit {order.source} did not make a move order"
    if source_unit.order.destination != order.destination:
        return False, f"Supported unit {order.source} moved to a different province"
    if order.destination_coast is not None and source_unit.order.destination_coast != order.destination_coast:
        return False, f"Supported unit {order.source} moved to a different coast"

    return True, None

def order_is_valid(province: Province, order: Order, potential_convoy=False, strict_coast_movement=True) -> tuple[bool, str | None]:
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
    if order is None:
        return False, "Order is missing"

    if ((isinstance(order, Support) or isinstance(order, ConvoyTransport))
        and order.source.unit is None):
        return False, f"No unit for supporting / convoying at {order.source}"

    if province.unit is None:
        return False, f"There is no unit in {province}"

    if isinstance(order, Hold) or isinstance(order, RetreatDisband) or isinstance(order, NMR):
        return True, None
    elif isinstance(order, Core):
        if not province.has_supply_center:
            return False, f"{province} does not have a supply center to core"
        if province.get_owner() != province.unit.player:
            return False, "Units can only core in owned supply centers"
        return True, None
    elif isinstance(order, Move) or isinstance(order, RetreatMove):
        valid, reason = _validate_move_order(province, order, strict_coast_movement)
        if not valid and potential_convoy and isinstance(order, Move) and province.unit.unit_type == UnitType.ARMY:
            # Try convoy validation if move is invalid
            return _validate_convoymove_order(province, order)
        return valid, reason
    elif isinstance(order, ConvoyTransport):
        return _validate_convoy_order(province, order)
    elif isinstance(order, Support):
        return _validate_support_order(province, order)

    return False, f"Unknown move type: {order.__class__.__name__}"