"""Module to parse commands to edit the game state.
These commands are designed to make changes to the current board and not for game-wide settings.
After these commands are executed, the Units, Provinces, Players, and, Retreat Options tables are saved.
For changes to game-wide settings, see .edit_game in parse_board_params.py."""

import logging

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.models.adjacency import Terrain
from DiploGM.utils import get_keywords, parse_season
from DiploGM.mapper.mapper import Mapper
from DiploGM.models.board import Board
from DiploGM.db.database import get_connection

logger = logging.getLogger(__name__)


def parse_edit_state(
    message: str, board: Board
) -> tuple[str, str, bytes | None, str | None, str | None]:
    """Parses a message containing commands to edit the game state,
    executes those commands, and returns a response message and an updated map if applicable."""
    invalid: list[tuple[str, Exception]] = []
    commands = str.splitlines(message)
    for command in commands:
        try:
            _parse_command(command, board)
        except (ValueError, RuntimeError, IndexError, KeyError) as error:
            invalid.append((command, error))

    embed_colour = None
    if invalid:
        response_title = "Error"
        response_body = "The following commands were invalid:"
        for command in invalid:
            response_body += f"\n`{command[0]}` with error: {command[1]}"

        embed_colour = (
            ERROR_COLOUR if len(invalid) == len(commands) else PARTIAL_ERROR_COLOUR
        )
    else:
        response_title = "Commands validated successfully. Results map updated."
        response_body = ""

    if len(invalid) < len(commands):
        file, file_name = Mapper(board).draw_current_map()
    else:
        file, file_name = None, None

    return (
        response_title,
        response_body,
        file,
        file_name,
        embed_colour,
    )


# TODO: Move to .edit_game be careful about earlier boards
def _set_phase(_, keywords: list[str], board: Board) -> None:
    old_turn = format(board.turn, "%I %S")
    new_turn = parse_season(keywords, board.turn)
    if new_turn is None:
        raise ValueError(f"{' '.join(keywords)} is not a valid phase name")
    board.turn = new_turn
    get_connection().execute_arbitrary_sql(
        "UPDATE boards SET phase=? WHERE board_id=? and phase=?",
        (format(board.turn, "%I %S"), board.board_id, old_turn),
    )
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET phase=? WHERE board_id=? and phase=?",
        (format(board.turn, "%I %S"), board.board_id, old_turn),
    )
    get_connection().execute_arbitrary_sql(
        "UPDATE units SET phase=? WHERE board_id=? and phase=?",
        (format(board.turn, "%I %S"), board.board_id, old_turn),
    )


def _set_province_core(command: str, keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    player = board.get_player(keywords[1])
    if command == "set core":
        province.core_data.core = player
    else:
        province.core_data.half_core = player


def _set_player_color(_, keywords: list[str], board: Board) -> None:
    raise NotImplementedError("set_player_color has been moved to `.edit_game`.")


def _set_province_owner(command: str, keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    if keywords[1].lower() == "impassable":
        province.is_impassable = True
        player = None
    else:
        province.is_impassable = False
        player = board.get_player(keywords[1])
    board.change_owner(province, player, force_change=True)
    if "total" in command:
        province.core_data.core = player


def _create_unit(_, keywords: list[str], board: Board) -> None:
    unit_type = board.unit_types.get(keywords[0].strip().upper()[0])
    if unit_type is None:
        raise ValueError(f"Invalid Unit Type received: {unit_type}")

    player = board.get_player(keywords[1])
    province, coast = board.get_province_and_coast(" ".join(keywords[2:]))
    if (
        Terrain.COAST in unit_type.moves_on
        and province.adjacencies.coasts
        and coast not in province.adjacencies.coasts
    ):
        raise ValueError(f"Province '{province.name}' requires a valid coast.")
    if not province.adjacencies.coasts:
        coast = None

    board.create_unit(unit_type, player, province, coast, None)


def _create_dislodged_unit(_, keywords: list[str], board: Board) -> None:
    if not board.turn.is_retreats():
        raise RuntimeError("Cannot create a dislodged unit in move phase")
    unit_type = board.unit_types.get(keywords[0].strip().upper()[0])
    if unit_type is None:
        raise ValueError(f"Invalid Unit Type received: {unit_type}")
    player = board.get_player(keywords[1])
    province, coast = board.get_province_and_coast(keywords[2])
    if (
        Terrain.COAST in unit_type.moves_on
        and province.adjacencies.coasts
        and coast not in province.adjacencies.coasts
    ):
        raise ValueError(f"Province '{province.name}' requires a valid coast.")
    if not province.adjacencies.coasts:
        coast = None
    retreat_options = {
        board.get_province_and_coast(province_name) for province_name in keywords[3:]
    }
    if not all(retreat_options):
        raise ValueError("Could not find at least one province in retreat options.")
    board.create_unit(unit_type, player, province, coast, retreat_options)


def _delete_unit(command: str, keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    unit = board.delete_unit(province, is_dislodged="dislodged" in command)
    if not unit:
        raise RuntimeError(f"No unit to delete in {province}")


def _move_unit(_, keywords: list[str], board: Board) -> None:
    old_province = board.get_province(keywords[0])
    unit = old_province.unit
    if not unit:
        raise RuntimeError(f"No unit to move in {old_province}")
    new_province, new_coast = board.get_province_and_coast(keywords[1])
    if Terrain.COAST not in unit.unit_type.moves_on:
        new_coast = None
    elif (
        new_province.adjacencies.coasts
        and new_coast not in new_province.adjacencies.coasts
    ):
        raise ValueError(f"Province '{new_province.name}' requires a valid coast.")
    if not new_province.adjacencies.coasts:
        new_coast = None
    board.move_unit(unit, new_province, new_coast)


def _transform_unit(_, keywords: list[str], board: Board) -> None:
    unit_types = board.fetch_unit_types()
    if keywords[0] in unit_types:
        new_unit_type = unit_types[keywords[0]]
        province, coast = board.get_province_and_coast(keywords[1])
    else:
        new_unit_type = None
        province, coast = board.get_province_and_coast(keywords[0])
    unit = province.unit
    if not unit:
        raise RuntimeError(f"No unit to transform in {province}")
    new_unit_type = new_unit_type or unit.unit_type.transforms_to
    if not new_unit_type:
        raise RuntimeError(
            f"Unit type {unit.unit_type} cannot transform to any other type"
        )

    if Terrain.COAST not in new_unit_type.moves_on:
        coast = None
    elif province.adjacencies.coasts and coast not in province.adjacencies.coasts:
        raise ValueError(f"Province '{province.name}' requires a valid coast.")
    if not province.adjacencies.coasts:
        coast = None
    unit.unit_type = new_unit_type
    unit.coast = coast


def _dislodge_unit(_, keywords: list[str], board: Board) -> None:
    if not board.turn.is_retreats():
        raise RuntimeError("Cannot create a dislodged unit in move phase")
    province = board.get_province(keywords[0])
    if province.dislodged_unit is not None:
        raise RuntimeError("Dislodged unit already exists in province")
    unit = province.unit
    if unit is None:
        raise RuntimeError("No unit to dislodge in province")
    retreat_options = {
        board.get_province_and_coast(province_name) for province_name in keywords[1:]
    }
    if not all(retreat_options):
        raise ValueError("Could not find at least one province in retreat options.")
    board.create_unit(
        unit.unit_type, unit.player, unit.province, unit.coast, retreat_options
    )
    board.delete_unit(province)


def _make_units_claim_provinces(_, keywords: list[str], board: Board) -> None:
    claim_centers = keywords and keywords[0].lower() == "true"
    for unit in board.units:
        if unit.province.dislodged_unit == unit:
            continue
        if not unit.unit_type.can_capture:
            continue
        if claim_centers or not unit.province.has_supply_center:
            board.change_owner(unit.province, unit.player, force_change=True)


def _set_game_name(_, parameter_str: str, board: Board) -> None:
    raise NotImplementedError("set_game_name has been moved to `.edit_game`.")


def _apocalypse(_, keywords: list[str], board: Board) -> None:
    """
    Keywords:
    all- deletes everything
    army- deletes all armies
    fleet- deletes all fleets
    core- deletes all cores
    province- deletes all ownnership
    """
    delete_all = "all" in keywords
    unit_types = {type.name: type for type in board.unit_types.values()}

    for unit_name in unit_types:
        if delete_all or unit_name.lower() in keywords:
            units = set(
                filter(lambda u: u.unit_type == unit_types[unit_name], board.units)
            )
            board.units -= units
            for player in board.players:
                player.units -= units

    if delete_all or "province" in keywords:
        for province in board.provinces:
            province.owner = None

        for player in board.players:
            player.centers = set()

    if delete_all or "core" in keywords:
        for province in board.provinces:
            province.core_data.core = None
            province.core_data.half_core = None


def _bulk_create_units(command: str, keywords: list[str], board: Board) -> None:
    player = keywords[0]
    unit_type = keywords[1]
    for i in keywords[2:]:
        _create_unit(command, [unit_type, player, i], board)


function_list = {
    "set phase": _set_phase,
    "set core": _set_province_core,
    "set half core": _set_province_core,
    "set province owner": _set_province_owner,
    "set total owner": _set_province_owner,
    "set player color": _set_player_color,
    "create unit": _create_unit,
    "create dislodged unit": _create_dislodged_unit,
    "delete unit": _delete_unit,
    "delete dislodged unit": _delete_unit,
    "move unit": _move_unit,
    "transform unit": _transform_unit,
    "dislodge unit": _dislodge_unit,
    "make units claim provinces": _make_units_claim_provinces,
    "set game name": _set_game_name,
    "bulk create units": _bulk_create_units,
    "apocalypse": _apocalypse,
}


def _bulk(_, keywords: list[str], board: Board) -> None:
    player = keywords[1]
    if keywords[0] in [
        "set core",
        "set half core",
        "set province owner",
        "set total owner",
    ]:
        for i in keywords[2:]:
            function_list[keywords[0]](keywords[0], [i, player], board)
    elif keywords[0] == "transform unit":
        for i in keywords[2:]:
            function_list[keywords[0]](keywords[0], [keywords[1], i], board)
    elif keywords[0] == "delete unit":
        for i in keywords[1:]:
            function_list[keywords[0]](keywords[0], [i], board)
    else:
        raise RuntimeError("You can't use bulk with this commands")


function_list["bulk"] = _bulk


def _parse_command(command: str, board: Board) -> None:
    command_list: list[str] = get_keywords(command)
    command_type = command_list[0].lower()
    if command_type == "set game name":
        keywords = " ".join(command_list[1:])
    else:
        keywords = [s.lower() for s in command_list[1:]]

    if command_type in function_list:
        function_list[command_type](command_type, keywords, board)
    else:
        raise RuntimeError("No command key phrases found")
