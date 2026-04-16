"""Module to parse commands to edit the game state."""
import logging
import string

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.utils import get_unit_type, get_keywords, parse_season
from DiploGM.mapper.mapper import Mapper
from DiploGM.models.board import Board
from DiploGM.db.database import get_connection
from DiploGM.models.unit import UnitType

logger = logging.getLogger(__name__)


def parse_edit_state(message: str, board: Board) -> tuple[str, str, bytes | None, str | None, str | None]:
    """Parses a message containing commands to edit the game state,
    executes those commands, and returns a response message and an updated map if applicable."""
    invalid: list[tuple[str, Exception]] = []
    commands = str.splitlines(message)
    for command in commands:
        try:
            _parse_command(command, board)
        except Exception as error:
            invalid.append((command, error))

    embed_colour = None
    if invalid:
        response_title = "Error"
        response_body = "The following commands were invalid:"
        for command in invalid:
            response_body += f"\n`{command[0]}` with error: {command[1]}"

        embed_colour = ERROR_COLOUR if len(invalid) == len(commands) else PARTIAL_ERROR_COLOUR
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
    player = board.get_player(keywords[0])
    if not player:
        raise ValueError(f"Unknown player: {keywords[0]}")
    color = keywords[1].lower()
    if len(color) != 6 or not all(c in string.hexdigits for c in color):
        raise ValueError(f"Unknown hexadecimal color: {color}")

    player.render_color = color


def _set_province_owner(command: str, keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    if keywords[1].lower() == "impassable":
        province.is_impassable = True
        player = None
    else:
        province.is_impassable = False
        player = board.get_player(keywords[1])
    board.change_owner(province, player)
    if "total" in command:
        province.core_data.core = player

def _create_unit(_, keywords: list[str], board: Board) -> None:
    unit_type = get_unit_type(keywords[0])
    if unit_type is None:
        raise ValueError(f"Invalid Unit Type received: {unit_type}")

    player = board.get_player(keywords[1])
    province, coast = board.get_province_and_coast(" ".join(keywords[2:]))
    if unit_type == UnitType.FLEET and province.get_multiple_coasts() and coast not in province.get_multiple_coasts():
        raise ValueError(f"Province '{province.name}' requires a valid coast.")
    if not province.get_multiple_coasts():
        coast = None

    board.create_unit(unit_type, player, province, coast, None)


def _create_dislodged_unit(_, keywords: list[str], board: Board) -> None:
    if not board.turn.is_retreats():
        raise RuntimeError("Cannot create a dislodged unit in move phase")
    unit_type = get_unit_type(keywords[0])
    if not unit_type:
        raise ValueError(f"Invalid Unit Type received: {unit_type}")
    player = board.get_player(keywords[1])
    province, coast = board.get_province_and_coast(keywords[2])
    if province.get_multiple_coasts() and coast not in province.get_multiple_coasts():
        raise ValueError(f"Province '{province.name}' requires a valid coast.")
    if not province.get_multiple_coasts():
        coast = None
    retreat_options = {board.get_province_and_coast(province_name) for province_name in keywords[3:]}
    if not all(retreat_options):
        raise ValueError(
            "Could not find at least one province in retreat options."
        )
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
    if new_province.get_multiple_coasts() and new_coast not in new_province.get_multiple_coasts():
        raise ValueError(f"Province '{new_province.name}' requires a valid coast.")
    if not new_province.get_multiple_coasts():
        new_coast = None
    board.move_unit(unit, new_province, new_coast)


def _dislodge_unit(_, keywords: list[str], board: Board) -> None:
    if not board.turn.is_retreats():
        raise RuntimeError("Cannot create a dislodged unit in move phase")
    province = board.get_province(keywords[0])
    if province.dislodged_unit is not None:
        raise RuntimeError("Dislodged unit already exists in province")
    unit = province.unit
    if unit is None:
        raise RuntimeError("No unit to dislodge in province")
    retreat_options = {board.get_province_and_coast(province_name) for province_name in keywords[1:]}
    if not all(retreat_options):
        raise ValueError(
            "Could not find at least one province in retreat options."
        )
    board.create_unit(
        unit.unit_type, unit.player, unit.province, unit.coast, retreat_options
    )
    board.delete_unit(province)


def _make_units_claim_provinces(_, keywords: list[str], board: Board) -> None:
    claim_centers = keywords and keywords[0].lower() == "true"
    for unit in board.units:
        if claim_centers or not unit.province.has_supply_center:
            board.change_owner(unit.province, unit.player)


def _set_player_points(_, keywords: list[str], board: Board) -> None:
    player = board.get_player(keywords[0])
    if not player:
        raise ValueError("Unknown player specified")
    points = int(keywords[1])
    if points < 0:
        raise ValueError("Can't have a negative number of points!")

    player.points = points


def _set_player_vassal(_, keywords: list[str], board: Board) -> None:
    liege = board.get_player(keywords[0])
    vassal = board.get_player(keywords[1])
    if not liege or not vassal:
        raise ValueError("Unknown player specified")
    vassal.liege = liege
    liege.vassals.append(vassal)


def _remove_player_vassal(_, keywords: list[str], board: Board) -> None:
    player1 = board.get_player(keywords[0])
    player2 = board.get_player(keywords[1])
    if not player1 or not player2:
        raise ValueError("Unknown player specified")
    for vassal, liege in ((player1, player2), (player2, player1)):
        if vassal.liege == liege:
            vassal.liege = None
            liege.vassals.remove(vassal)


def _set_game_name(_, parameter_str: str, board: Board) -> None:
    newname = None if parameter_str == "None" else parameter_str
    board.data["name"] = newname
    board.custom_data["name"] = newname
    get_connection().execute_arbitrary_sql(
        "INSERT OR REPLACE INTO board_parameters (board_id, key, value) VALUES (?, ?, ?)",
        (board.board_id, "name", newname)
    )

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

    if delete_all or "army" in keywords:
        armies = set(filter(lambda u: u.unit_type == UnitType.ARMY, board.units))
        board.units -= armies
        for player in board.players:
            player.units -= armies

    if delete_all or "fleet" in keywords:
        fleets = set(filter(lambda u: u.unit_type == UnitType.FLEET, board.units))
        board.units -= fleets
        for player in board.players:
            player.units -= fleets

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
    "dislodge unit": _dislodge_unit,
    "make units claim provinces": _make_units_claim_provinces,
    "set vassal": _set_player_vassal,
    "remove relationship": _remove_player_vassal,
    "set game name": _set_game_name,
    "bulk create units": _bulk_create_units,
    "apocalypse": _apocalypse,
    "set player points": _set_player_points
}

def _bulk(keywords: list[str], board: Board) -> None:
    player = keywords[1]
    if keywords[0] in ["set core", "set half core", "set province owner", "set total owner", "delete unit"]:
        for i in keywords[2:]:
            function_list[keywords[0]](keywords[0], [i, player], board)
        return

    raise RuntimeError(
        "You can't use bulk with this commands"
    )

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
