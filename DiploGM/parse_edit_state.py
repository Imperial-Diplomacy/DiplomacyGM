import copy
import logging
import string

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.utils import get_unit_type, get_keywords, parse_season
from DiploGM.adjudicator.mapper import Mapper
from DiploGM.models.board import Board
from DiploGM.db.database import get_connection
from DiploGM.manager import Manager
from DiploGM.models.player import Player
from DiploGM.models.province import Province
from DiploGM.models.unit import Unit, UnitType

_set_phase_str = "set phase"
_set_core_str = "set core"
_set_half_core_str = "set half core"
_set_province_owner_str = "set province owner"
_set_total_owner_str = "set total owner"
_set_player_color_str = "set player color"
_create_unit_str = "create unit"
_create_dislodged_unit_str = "create dislodged unit"
_delete_unit_str = "delete unit"
_delete_dislodged_unit_str = "delete dislodged unit"
_move_unit_str = "move unit"
_dislodge_unit_str = "dislodge unit"
_make_units_claim_provinces_str = "make units claim provinces"
_set_player_vassal_str = "set vassal"
_remove_vassal_str = "remove relationship"
_set_game_name_str = "set game name"
_create_player_str = "create player"
_delete_player_str = "delete player"
_load_state_str = "load state"
_bulk_str = "bulk"
_bulk_create_units_str = "bulk create units"

# apocalypse (empty map state)
_apocalypse_str = "apocalypse"

# chaos
_set_player_points_str = "set player points"

logger = logging.getLogger(__name__)
manager = Manager()


def parse_edit_state(message: str, board: Board) -> dict[str, str | bytes | int | None]:
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

        if len(invalid) == len(commands):
            embed_colour = ERROR_COLOUR
        else:
            embed_colour = PARTIAL_ERROR_COLOUR
    else:
        response_title = "Commands validated successfully. Results map updated."
        response_body = ""

    if len(invalid) < len(commands):
        file, file_name = Mapper(board).draw_current_map()
    else:
        file, file_name = None, None

    return {
        "title": response_title,
        "message": response_body,
        "file": file,
        "file_name": file_name,
        "embed_colour": embed_colour,
    }


def _parse_command(command: str, board: Board) -> None:
    command_list: list[str] = get_keywords(command)
    command_type = command_list[0].lower()
    parameter_str = " ".join(command_list[1:])
    keywords = [s.lower() for s in command_list[1:]]

    if command_type == _set_phase_str:
        _set_phase(keywords, board)
    elif command_type == _set_core_str:
        _set_province_core(keywords, board)
    elif command_type == _set_half_core_str:
        _set_province_half_core(keywords, board)
    elif command_type == _set_province_owner_str:
        _set_province_owner(keywords, board)
    elif command_type == _set_total_owner_str:
        _set_total_owner(keywords, board)
    elif command_type == _set_player_color_str:
        _set_player_color(keywords, board)
    elif command_type == _create_unit_str:
        _create_unit(keywords, board)
    elif command_type == _create_dislodged_unit_str:
        _create_dislodged_unit(keywords, board)
    elif command_type == _delete_unit_str:
        _delete_unit(keywords, board)
    elif command_type == _move_unit_str:
        _move_unit(keywords, board)
    elif command_type == _dislodge_unit_str:
        _dislodge_unit(keywords, board)
    elif command_type == _make_units_claim_provinces_str:
        _make_units_claim_provinces(keywords, board)
    elif command_type == _delete_dislodged_unit_str:
        _delete_dislodged_unit(keywords, board)
    elif command_type == _set_player_points_str:
        _set_player_points(keywords, board)
    elif command_type == _set_player_vassal_str:
        _set_player_vassal(keywords, board)
    elif command_type == _remove_vassal_str:
        _remove_player_vassal(keywords, board)
    elif command_type == _set_game_name_str:
        _set_game_name(parameter_str, board)
    elif command_type == _create_player_str:
        _create_player(keywords, board)
    elif command_type == _delete_player_str:
        _delete_player(keywords, board)
    elif command_type == _load_state_str:
        _load_state(keywords, board)
    elif command_type == _apocalypse_str:
        _apocalypse(keywords, board)
    elif command_type == _bulk_str:
        _bulk(keywords, board)
    elif command_type == _bulk_create_units_str:
        _bulk_create_units(keywords, board)
    else:
        raise RuntimeError(f"No command key phrases found")


def _set_phase(keywords: list[str], board: Board) -> None:
    old_turn = board.turn.get_indexed_name()
    new_turn = parse_season(keywords, board.turn)
    if new_turn is None:
        raise ValueError(f"{' '.join(keywords)} is not a valid phase name")
    board.turn = new_turn
    get_connection().execute_arbitrary_sql(
        "UPDATE boards SET phase=? WHERE board_id=? and phase=?",
        (board.turn.get_indexed_name(), board.board_id, old_turn),
    )
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET phase=? WHERE board_id=? and phase=?",
        (board.turn.get_indexed_name(), board.board_id, old_turn),
    )
    get_connection().execute_arbitrary_sql(
        "UPDATE units SET phase=? WHERE board_id=? and phase=?",
        (board.turn.get_indexed_name(), board.board_id, old_turn),
    )


def _set_province_core(keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    player = board.get_player(keywords[1])
    province.core = player
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET core=? WHERE board_id=? and phase=? and province_name=?",
        (
            player.name if player is not None else None,
            board.board_id,
            board.turn.get_indexed_name(),
            province.name,
        ),
    )


def _set_province_half_core(keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    player = board.get_player(keywords[1])
    province.half_core = player
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET half_core=? WHERE board_id=? and phase=? and province_name=?",
        (
            player.name if player is not None else None,
            board.board_id,
            board.turn.get_indexed_name(),
            province.name,
        ),
    )


def _set_player_color(keywords: list[str], board: Board) -> None:
    player = board.get_player(keywords[0])
    if not player:
        raise ValueError(f"Unknown player: {keywords[0]}")
    color = keywords[1].lower()
    if not len(color) == 6 or not all(c in string.hexdigits for c in color):
        raise ValueError(f"Unknown hexadecimal color: {color}")

    player.render_color = color
    get_connection().execute_arbitrary_sql(
        "UPDATE players SET color=? WHERE board_id=? and player_name=?",
        (color, board.board_id, player.name),
    )


def _set_province_owner(keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    player = board.get_player(keywords[1])
    board.change_owner(province, player)
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET owner=? WHERE board_id=? and phase=? and province_name=?",
        (
            player.name if player is not None else None,
            board.board_id,
            board.turn.get_indexed_name(),
            province.name,
        ),
    )


def _set_total_owner(keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    player = board.get_player(keywords[1])
    board.change_owner(province, player)
    province.core = player
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET owner=?, core=? WHERE board_id=? and phase=? and province_name=?",
        (
            player.name if player is not None else None,
            player.name if player is not None else None,
            board.board_id,
            board.turn.get_indexed_name(),
            province.name,
        ),
    )


def _create_unit(keywords: list[str], board: Board) -> None:
    unit_type = get_unit_type(keywords[0])
    if unit_type is None:
        raise ValueError(f"Invalid Unit Type received: {unit_type}")

    player = board.get_player(keywords[1])
    if not player:
        raise ValueError(f"Unknown player: {keywords[1]}")
    province, coast = board.get_province_and_coast(" ".join(keywords[2:]))
    # if unit_type == UnitType.FLEET and coast is None:
    #     coast_name = f"{province} coast"
    #     province, coast = board.get_province_and_coast(coast_name)

    unit = board.create_unit(unit_type, player, province, coast, None)
    get_connection().execute_arbitrary_sql(
        "INSERT INTO units (board_id, phase, location, is_dislodged, owner, is_army) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (board_id, phase, location, is_dislodged) DO UPDATE SET owner=?, is_army=?",
        (
            board.board_id,
            board.turn.get_indexed_name(),
            unit.province.get_name(coast),
            False,
            player.name,
            unit_type == UnitType.ARMY,
            player.name,
            unit_type == UnitType.ARMY,
        ),
    )


def _create_dislodged_unit(keywords: list[str], board: Board) -> None:
    if board.turn.is_retreats():
        unit_type = get_unit_type(keywords[0])
        if not unit_type:
            raise ValueError(f"Invalid Unit Type received: {unit_type}")
        player = board.get_player(keywords[1])
        if not player:
            raise ValueError(f"Unknown player: {keywords[1]}")
        province, coast = board.get_province_and_coast(keywords[2])
        retreat_options = set(
            [board.get_province_and_coast(province_name) for province_name in keywords[3:]]
        )
        if not all(retreat_options):
            raise ValueError(
                f"Could not find at least one province in retreat options."
            )
        unit = board.create_unit(unit_type, player, province, coast, retreat_options)
        get_connection().execute_arbitrary_sql(
            "INSERT INTO units (board_id, phase, location, is_dislodged, owner, is_army) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (board_id, phase, location, is_dislodged) DO UPDATE SET owner=?, is_army=?",
            (
                board.board_id,
                board.turn.get_indexed_name(),
                unit.province.get_name(coast),
                True,
                player.name,
                unit_type == UnitType.ARMY,
                player.name,
                unit_type == UnitType.ARMY,
            ),
        )
        get_connection().executemany_arbitrary_sql(
            "INSERT INTO retreat_options (board_id, phase, origin, retreat_loc) VALUES (?, ?, ?, ?)",
            [
                (
                    board.board_id,
                    board.turn.get_indexed_name(),
                    unit.province.get_name(coast),
                    option[0].get_name(option[1]),
                )
                for option in retreat_options
            ],
        )
    else:
        raise RuntimeError("Cannot create a dislodged unit in move phase")


def _delete_unit(keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    unit = board.delete_unit(province)
    if not unit:
        raise RuntimeError(f"No unit to delete in {province}")
    get_connection().execute_arbitrary_sql(
        "DELETE FROM units WHERE board_id=? and phase=? and location=? and is_dislodged=?",
        (
            board.board_id,
            board.turn.get_indexed_name(),
            unit.province.get_name(unit.coast),
            False,
        ),
    )


def _delete_dislodged_unit(keywords: list[str], board: Board) -> None:
    province = board.get_province(keywords[0])
    unit = board.delete_dislodged_unit(province)
    if not unit:
        raise RuntimeError(f"No dislodged unit to delete in {province}")
    get_connection().execute_arbitrary_sql(
        "DELETE FROM units WHERE board_id=? and phase=? and location=? and is_dislodged=?",
        (board.board_id, board.turn.get_indexed_name(), unit.province.get_name(unit.coast), True),
    )
    get_connection().execute_arbitrary_sql(
        "DELETE FROM retreat_options WHERE board_id=? and phase=? and origin=?",
        (board.board_id, board.turn.get_indexed_name(), unit.province.get_name(unit.coast)),
    )


def _move_unit(keywords: list[str], board: Board) -> None:
    old_province = board.get_province(keywords[0])
    unit = old_province.unit
    if not unit:
        raise RuntimeError(f"No unit to move in {old_province}")
    new_province, new_coast = board.get_province_and_coast(keywords[1])
    board.move_unit(unit, new_province, new_coast)
    get_connection().execute_arbitrary_sql(
        "DELETE FROM units WHERE board_id=? and phase=? and location=? and is_dislodged=?",
        (board.board_id, board.turn.get_indexed_name(), old_province.get_name(unit.coast), False),
    )
    get_connection().execute_arbitrary_sql(
        "INSERT INTO units (board_id, phase, location, is_dislodged, owner, is_army) VALUES (?, ?, ?, ?, ?, ?)",
        (
            board.board_id,
            board.turn.get_indexed_name(),
            new_province.get_name(new_coast),
            False,
            unit.player.name,
            unit.unit_type == UnitType.ARMY,
        ),
    )


def _dislodge_unit(keywords: list[str], board: Board) -> None:
    if board.turn.is_retreats():
        province = board.get_province(keywords[0])
        if province.dislodged_unit != None:
            raise RuntimeError("Dislodged unit already exists in province")
        unit = province.unit
        if unit == None:
            raise RuntimeError("No unit to dislodge in province")
        retreat_options = set(
            [board.get_province_and_coast(province_name) for province_name in keywords[1:]]
        )
        if not all(retreat_options):
            raise ValueError(
                f"Could not find at least one province in retreat options."
            )
        dislodged_unit = board.create_unit(
            unit.unit_type, unit.player, unit.province, unit.coast, retreat_options
        )
        unit = board.delete_unit(province)
        get_connection().execute_arbitrary_sql(
            "UPDATE units SET is_dislodged = True where board_id=? and phase=? and location=?",
            (board.board_id, board.turn.get_indexed_name(), province.name),
        )
    else:
        raise RuntimeError("Cannot create a dislodged unit in move phase")


def _make_units_claim_provinces(keywords: list[str], board: Board) -> None:
    claim_centers = False
    if keywords:
        claim_centers = keywords[0].lower() == "true"
    for unit in board.units:
        if claim_centers or not unit.province.has_supply_center:
            board.change_owner(unit.province, unit.player)
            get_connection().execute_arbitrary_sql(
                "UPDATE provinces SET owner=? WHERE board_id=? and phase=? and province_name=?",
                (
                    unit.player.name,
                    board.board_id,
                    board.turn.get_indexed_name(),
                    unit.province.name,
                ),
            )


def _set_player_points(keywords: list[str], board: Board) -> None:
    player = board.get_player(keywords[0])
    if not player:
        raise ValueError("Unknown player specified")
    points = int(keywords[1])
    if points < 0:
        raise ValueError("Can't have a negative number of points!")

    player.points = points
    get_connection().execute_arbitrary_sql(
        "UPDATE players SET points=? WHERE board_id=? and player_name=?",
        (points, board.board_id, player.name),
    )


def _set_player_vassal(keywords: list[str], board: Board) -> None:
    liege = board.get_player(keywords[0])
    vassal = board.get_player(keywords[1])
    if not liege or not vassal:
        raise ValueError("Unknown player specified")
    vassal.liege = liege
    liege.vassals.append(vassal)
    get_connection().execute_arbitrary_sql(
        "UPDATE players SET liege=? WHERE board_id=? and player_name=?",
        (liege.name, board.board_id, vassal.name),
    )


def _remove_player_vassal(keywords: list[str], board: Board) -> None:
    player1 = board.get_player(keywords[0])
    player2 = board.get_player(keywords[1])
    if not player1 or not player2:
        raise ValueError("Unknown player specified")
    for vassal, liege in ((player1, player2), (player2, player1)):
        if vassal.liege == liege:
            vassal.liege = None
            liege.vassals.remove(vassal)
            get_connection().execute_arbitrary_sql(
                "UPDATE players SET liege=? WHERE board_id=? and player_name=?",
                (None, board.board_id, vassal.name),
            )


def _set_game_name(parameter_str: str, board: Board) -> None:
    newname = None if parameter_str == "None" else parameter_str
    board.name = newname
    get_connection().execute_arbitrary_sql(
        "UPDATE boards SET name=? WHERE board_id=?", (newname, board.board_id)
    )


# FIXME: issues with board structure (board_id/phase is tied everywhere)
# need a custom way to deepcopy to avoid recursion limits
def _load_state(keywords: list[str], board: Board) -> None:
    raise NotImplementedError()

    curr_board_id = copy.deepcopy(board.board_id)

    logger.error(keywords)
    server = int(keywords[0])
    turn = parse_season(keywords[1:], board.turn)

    year = int(keywords[2])
    epoch_year = board.year_offset - turn.year

    if other := manager._boards.get(server, None):
        if other.datafile != board.datafile:
            raise ValueError(
                f"This game state does not share the same datafile as your game: '{other.datafile}' vs. '{board.datafile}'"
            )
        else:
            # trailing elses are pain
            pass
    else:
        raise ValueError(f"Could not find any game state for this server: '{server}'")

    other = manager._database.get_board(
        server,
        turn.get_phase(),
        turn.get_year_index(),
        board.fish,
        name=board.name,
        data_file=board.datafile,
    )
    if not other:
        raise KeyError(
            f"Could not find a board for server '{server}' in phase: {turn}"
        )

    new_board = Board(
        other.players,
        other.provinces,
        other.units,
        other.turn,
        other.data,
        other.datafile,
        fow=board.fow,
    )
    new_board.board_id = curr_board_id

    manager._boards[curr_board_id] = new_board
    manager._database.delete_board(board)
    manager._database.save_board(curr_board_id, new_board)


def _apocalypse(keywords: list[str], board: Board) -> None:
    """
    Keywords:
    all- deletes everything
    army- deletes all armies
    fleet- deletes all fleets
    core- deletes all cores
    province- deletes all ownnership
    """
    all = "all" in keywords

    armies = {}
    if all or "army" in keywords:
        armies = set(filter(lambda u: u.unit_type == UnitType.ARMY, board.units))
        board.units -= armies
        for player in board.players:
            player.units -= armies

        get_connection().execute_arbitrary_sql(
            "DELETE FROM units WHERE board_id=? AND phase=? AND is_army=1",
            (
                board.board_id,
                board.turn.get_indexed_name(),
            ),
        )

    if all or "fleet" in keywords:
        fleets = set(filter(lambda u: u.unit_type == UnitType.FLEET, board.units))
        board.units -= fleets
        for player in board.players:
            player.units -= fleets

        get_connection().execute_arbitrary_sql(
            "DELETE FROM units WHERE board_id=? AND phase=? AND is_army=0",
            (
                board.board_id,
                board.turn.get_indexed_name(),
            ),
        )

    if all or "province" in keywords:
        for province in board.provinces:
            province.owner = None

        for player in board.players:
            player.centers = set()

        get_connection().execute_arbitrary_sql(
            "UPDATE provinces SET owner=? WHERE board_id=? AND phase=?",
            (None, board.board_id, board.turn.get_indexed_name()),
        )

    if all or "core" in keywords:
        for province in board.provinces:
            province.core = None
            province.half_core = None

        get_connection().execute_arbitrary_sql(
            "UPDATE provinces SET core=?, half_core=? WHERE board_id=? AND phase=?",
            (None, None, board.board_id, board.turn.get_indexed_name()),
        )


def _bulk(keywords: list[str], board: Board) -> None:

    player = keywords[1]

    if keywords[0] == _set_core_str:
        for i in keywords[2:]:
            _set_province_core([i, player], board)
        return
    elif keywords[0] == _set_half_core_str:
        for i in keywords[2:]:
            _set_province_half_core([i, player], board)
        return
    elif keywords[0] == _set_province_owner_str:
        for i in keywords[2:]:
            _set_province_owner([i, player], board)
        return
    elif keywords[0] == _set_total_owner_str:
        for i in keywords[2:]:
            _set_total_owner([i, player], board)
        return
    elif keywords[0] == _delete_unit_str:
        for i in keywords[1:]:
            _delete_unit([i], board)
        return

    raise RuntimeError(
        "You can't use bulk with this commands"
    )


def _bulk_create_units(keywords: list[str], board: Board) -> None:
    player = keywords[0]
    unit_type = keywords[1]
    for i in keywords[2:]:
        _create_unit([unit_type, player, i], board)


# FIXME: Works but inconsistent with DB Storage NOT PERSISTENT
def _create_player(keywords: list[str], board: Board) -> None:
    raise NotImplementedError(
        "This feature is planned, but not currently implemented due to technical limitations."
    )

    name = keywords[0]
    color = keywords[1].replace("#", "")

    try:
        if len(color) != 6 or not color.isalnum():
            raise ValueError
        elif int(color, 16) and not color.startswith("0x"):
            pass
    except ValueError:
        raise ValueError("Invalid Hex color code provided.")

    SUPPORTED_WIN_TYPES = ["classic", "vscc"]
    win_type = keywords[2].lower()
    if win_type not in SUPPORTED_WIN_TYPES:
        raise ValueError(
            f"Invalid win type provided: {win_type} not in {SUPPORTED_WIN_TYPES}"
        )

    vscc = keywords[3]
    iscc = keywords[4]
    if not vscc.isnumeric() or int(vscc) <= 0:
        raise ValueError(
            f"Invalid VSCC value given {vscc}: Please provide a number greater than 0"
        )
    if not iscc.isnumeric() or int(iscc) <= 0:
        raise ValueError(
            f"Invalid ISCC value given {iscc}: Please provide a number greater than 0"
        )

    new_player = Player(
        name=name,
        color=color,
        win_type=win_type,
        vscc=int(vscc),
        iscc=int(iscc),
        centers=set(),
        units=set(),
    )
    board.players.add(new_player)
    board.name_to_player[name.lower()] = new_player

    get_connection().execute_arbitrary_sql(
        "INSERT INTO players VALUES (?, ?, ?, ?, ?, ?)",
        (
            board.board_id,
            name,
            new_player.default_color,
            None,
            None,
            None,
        ),
    )


def _delete_player(keywords: list[str], board: Board) -> None:
    name = keywords[0]
    player = board.get_player(name)
    if not player:
        raise ValueError(f"There is no player named: {name}")

    units: set[Unit] = set(filter(lambda u: u.player == player, board.units))
    player.units = set()
    board.units -= units
    get_connection().execute_arbitrary_sql(
        "DELETE FROM units WHERE board_id=? AND phase=? AND owner=?",
        (board.board_id, board.turn.get_indexed_name(), player.name),
    )

    provinces: set[Province] = set(filter(lambda u: u.owner == player, board.provinces))
    player.centers = set()
    for p in provinces:
        p.owner = None
        if p.core == player:
            p.core = None
        if p.half_core == player:
            p.half_core = None
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET owner=? WHERE board_id=? and phase=?",
        (None, board.board_id, board.turn.get_indexed_name()),
    )
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET core=? WHERE board_id=? and phase=? AND core=?",
        (None, board.board_id, board.turn.get_indexed_name(), player.name),
    )
    get_connection().execute_arbitrary_sql(
        "UPDATE provinces SET half_core=? WHERE board_id=? and phase=? AND half_core=?",
        (None, board.board_id, board.turn.get_indexed_name(), player.name),
    )

    # NOTE: Players are not tied to individual Phase boards, but the server as a whole

    # board.players.remove(player)
    # get_connection().execute_arbitrary_sql(
    #     "DELETE FROM units WHERE board_id=? AND phase=? AND owner=?",
    #     (board.board_id, board.turn.get_indexed_name(), player.name),
    # )
