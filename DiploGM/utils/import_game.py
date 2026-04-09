from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from DiploGM.models.unit import UnitType, DPAllocation
from DiploGM.models.turn import Turn

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.province import Province

logger = logging.getLogger(__name__)

def _parse_unit(board: Board, province: Province, unit_data: dict, is_dislodged: bool = False) -> None:
    retreat_options = ({board.get_province_and_coast(loc)
                        for loc in unit_data.get("retreat_options", [])}
                        if is_dislodged else None)
    unit = board.create_unit(UnitType(unit_data["type"]),
                            board.get_player(unit_data.get("owner", "None")),
                            province,
                            unit_data.get("coast"),
                            retreat_options)
    if "order" in unit_data:
        order_data = unit_data["order"]
        try:
            unit.order = board.parse_order(order_data["type"],
                                            order_data.get("destination"),
                                            order_data.get("source"))
        except (ValueError, KeyError) as e:
            logger.warning("Could not parse order for %s: %s", province.name, e)
    for player_name, dp_data in unit_data.get("dp_allocations", {}).items():
        try:
            dp_order = board.parse_order(dp_data["order"]["type"],
                                            dp_data["order"].get("destination"),
                                            dp_data["order"].get("source"))
            if dp_order is not None:
                unit.dp_allocations[player_name] = DPAllocation(dp_data["points"], dp_order)
        except (ValueError, KeyError) as e:
            logger.warning("Could not parse DP order for %s: %s", province.name, e)

def _parse_province(province: Province, province_data: dict, board: Board) -> None:
    if province_data.get("is_impassable", False) is True:
        province.is_impassable = True

    if (owner_name := province_data.get("owner")) is not None:
        board.change_owner(province, board.get_player(owner_name))
    if (core_power := province_data.get("core")) is not None:
        province.core_data.core = board.get_player(core_power)
    if (half_core_power := province_data.get("half_core")) is not None:
        province.core_data.half_core = board.get_player(half_core_power)

    if "unit" in province_data:
        _parse_unit(board, province, province_data["unit"])

    # Dislodged unit
    if "dislodged_unit" in province_data:
        _parse_unit(board, province, province_data["dislodged_unit"], is_dislodged=True)

def import_game(board: Board, data: dict) -> str:
    """Applies a game state from an export JSON dict or string."""

    if "turn" in data:
        new_turn = Turn.turn_from_string(data["turn"])
        if new_turn is not None:
            board.turn = new_turn

    if "fish" in data:
        board.data["fish"] = int(data["fish"])

    # Update player data
    for player_data in data.get("players", []):
        if player_data["name"].lower() not in board.name_to_player:
            board.add_new_player(player_data["name"], player_data.get("color", "00FF00"))
        player = board.get_player(player_data["name"])
        if player is None:
            continue
        player.render_color = player_data.get("color", player.render_color)
        player.is_active = player_data.get("is_active", player.is_active)

    # Clear all units
    board.delete_all_units()
    board.delete_dislodged_units()

    # Apply province data
    province_data_by_name = {p["name"]: p for p in data.get("provinces", [])}
    for province in board.provinces:
        if province.name not in province_data_by_name:
            continue
        pdata = province_data_by_name[province.name]
        _parse_province(province, pdata, board)

    # Apply custom parameters
    if "parameters" in data:
        for key, value in data["parameters"].items():
            board.data[key] = value
        board.custom_data = data["parameters"]

    return "Successfully imported board."
