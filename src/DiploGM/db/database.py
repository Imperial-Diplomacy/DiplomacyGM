"""Module to handle database interactions."""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from typing import TYPE_CHECKING

# TODO: Find a better way to do this
# maybe use a copy from manager?
from DiploGM.config import DB_LOCATION, DB_SCHEMA_LOCATION
from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.models.turn import Turn, PhaseName
from DiploGM.models.order import PlayerOrder, Build, Disband, TransformBuild
from DiploGM.models.unit import DPAllocation, Unit

from DiploGM.models.spec_request import SpecRequest

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.player import Player
    from DiploGM.models.province import Province

logger = logging.getLogger(__name__)
DATE_STRING_FORMAT = "%I %S" # EG: 0 Spring Moves

class _DatabaseConnection:
    def __init__(self, db_file: str = DB_LOCATION):
        try:
            self._connection = sqlite3.connect(db_file)
            logger.info("Connection to SQLite DB successful")
        except IOError as ex:
            logger.error("Could not open SQLite DB", exc_info=ex)
            self._connection = sqlite3.connect(
                ":memory:"
            )  # Special wildcard; in-memory db

        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._initialize_schema()

    def _initialize_schema(self):
        # FIXME: move the sql file somewhere more accessible (maybe it shouldn't be inside the package? /resources ?)
        with open(DB_SCHEMA_LOCATION, "r", encoding="utf-8") as sql_file:
            cursor = self._connection.cursor()
            cursor.executescript(sql_file.read())
            cursor.close()

    def get_active_board_ids(self) -> set[int]:
        """Gets all board IDs that have games in the database, without loading full board state."""
        cursor = self._connection.cursor()
        rows = cursor.execute("SELECT DISTINCT board_id FROM boards").fetchall()
        cursor.close()
        return {row[0] for row in rows}


    def _save_units(self, board_id: int, board: Board):
        """Saves the units for the given board."""
        cursor = self._connection.cursor()
        cursor.executemany(
            "INSERT INTO units (board_id, phase, phase_index, location, is_dislodged, owner, "
            "unit_type, order_type, order_destination, order_source, failed_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    unit.province.get_name(unit.coast),
                    unit == unit.province.dislodged_unit,
                    unit.player.name if unit.player else None,
                    unit.unit_type.code,
                    unit.order.__class__.__name__ if unit.order is not None else None,
                    unit.order.get_destination_str() if unit.order is not None else None,
                    unit.order.get_source_str() if unit.order is not None else None,
                    unit.order.has_failed if unit.order is not None else False,
                )
                for unit in board.units
            ],
        )
        cursor.close()
        self._connection.commit()

    def _save_retreat_options(self, board_id: int, board: Board):
        """Saves the retreat options for the given board."""
        cursor = self._connection.cursor()
        cursor.executemany(
            "INSERT INTO retreat_options (board_id, phase, phase_index, origin, retreat_loc) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    unit.province.get_name(unit.coast),
                    retreat_option[0].get_name(retreat_option[1]),
                )
                for unit in board.units
                if unit.retreat_options is not None
                for retreat_option in unit.retreat_options
            ],
        )
        cursor.close()
        self._connection.commit()

    def _load_board_history(self, board: Board, cursor):
        # Gets how many SCs each power has had over the course of a game
        # TODO: For each SC, store how long it has been an SC
        scs = {p.name for p in board.provinces if p.has_supply_center}
        start_string = f"{board.data.get('year', 1901)} "
        start_string += "Winter Builds" if board.data.get("first_season") == "Winter" else "Spring Moves"
        phase = Turn.turn_from_string(start_string)
        if phase is None:
            raise ValueError(f"Unable to get turn from string {start_string}")
        phase.start_year = board.turn.start_year
        while(not phase.is_later(board.turn)):
            province_data = cursor.execute(
                "SELECT province_name, owner FROM provinces WHERE board_id=? AND phase_index=?",
                (board.board_id, format(phase, "%i"))
            ).fetchall()
            if phase.phase == PhaseName.SPRING_MOVES:
                phase = phase.get_previous_turn() # We'd want to look at Winter, but games start in Spring usually
            for province, owner in province_data:
                if province in scs and owner is not None and (player := board.get_player(owner)) is not None:
                    player.sc_history[phase.year] = player.sc_history.get(phase.year, 0) + 1
            phase = phase.get_next_year()
            # If SC ownership has changed but it's not the next year yet, we still want that SC data anyway
            if phase.is_later(board.turn) and board.turn.phase == PhaseName.WINTER_BUILDS:
                phase = Turn(board.turn.year, board.turn.phase, board.turn.start_year)

    def load_board(self, board_id: int) -> Board | None:
        """Gets a specific board from the database."""
        cursor = self._connection.cursor()
        phase_index, data_file = cursor.execute("SELECT phase_index, data_file FROM boards WHERE board_id=? ORDER BY phase_index DESC", (board_id,)).fetchone()
        current_turn = Turn.turn_from_int(phase_index)
        if current_turn is None:
            raise ValueError("Could not parse turn index '%s' for board %s", phase_index, board_id)
        board = self._get_board(board_id, current_turn, data_file, cursor)

        if board is not None:
            self._load_board_history(board, cursor)
        cursor.close()
        logger.info("Successfully loaded")
        return board

    def get_board(
        self,
        board_id: int,
        turn: Turn,
        data_file: str,
        clear_status: bool = False,
    ) -> Board | None:
        """Gets a board from the database.
        clear_status is used to wipe out failed order information, which we need to do for rollbacks."""
        cursor = self._connection.cursor()

        board_data = cursor.execute(
            "SELECT 1 FROM boards WHERE board_id=? and phase_index=?",
            (board_id, format(turn, "%i")),
        ).fetchone()
        if not board_data:
            cursor.close()
            return None

        board = self._get_board(board_id, turn, data_file, cursor, clear_status=clear_status)
        cursor.close()
        return board

    def _load_builds(self, cursor, board_id: int, board: Board):
        builds_data = cursor.execute(
            "SELECT player, location, order_type, unit_type, failed_order FROM builds WHERE board_id=? and phase_index=?",
            (board_id, format(board.turn, "%i")),
        ).fetchall()

        player_by_name = {player.name: player for player in board.players}
        for player_name, location, order_type, unit_type, failed_order in builds_data:
            player = player_by_name.get(player_name)
            if player is None:
                logger.warning("Unknown player: %s", player_name)
                continue

            if order_type == "Build":
                player_order = Build(
                    board.get_province(location),
                    board.unit_types[unit_type[0]],
                    unit_type[-2:] if len(unit_type) > 1 else None,
                )
            elif order_type == "Disband":
                player_order = Disband(board.get_province(location))
            elif order_type == "TransformBuild":
                player_order = TransformBuild(board.get_province(location),
                                              unit_type[-2:] if len(unit_type) > 1 else None)
            elif order_type == "Waive":
                player.waived_orders = int(location)
                continue
            else:
                logger.warning("Unknown build order type: %s", order_type)
                continue

            player_order.has_failed = failed_order
            player.build_orders.add(player_order)

    def _load_province(self, board: Board, province: Province, province_info_by_name: dict):
        if province.name not in province_info_by_name:
            if not province.is_impassable:
                logger.warning("Couldn't find province %s in DB", province.name)
            return

        owner, core, half_core = province_info_by_name[province.name]
        if owner == "Impassable" or owner is None:
            province.owner = None
        else:
            owner_player = board.get_player(owner)
            province.owner = owner_player
            if province.has_supply_center and owner_player is not None:
                owner_player.centers.add(province)

        province.is_impassable = owner == "Impassable"
        province.core_data.core = board.get_player(core) if core is not None else None
        province.core_data.half_core = board.get_player(half_core) if half_core is not None else None
        province.unit = None
        province.dislodged_unit = None

    def _load_unit(self, board: Board, board_id: int, unit_info: tuple, cursor):
        (location, is_dislodged, owner, unit_type, order_type, destination, source, has_failed) = unit_info
        province, coast = board.get_province_and_coast(location)
        owner_player = None
        if owner is not None and (owner_player := board.get_player(owner)) is None:
            logger.warning("Couldn't find corresponding player for %s in DB", owner)
            return
        owner_player = board.get_player(owner) if owner is not None else None
        unit = Unit(board.unit_types[unit_type], owner_player, province, coast)

        if is_dislodged:
            province.dislodged_unit = unit
            retreat_ops = cursor.execute(
                "SELECT retreat_loc FROM retreat_options WHERE board_id=? and phase_index=? and origin=?",
                (board_id, format(board.turn, "%i"), location),
            )
            unit.retreat_options = set(map(board.get_province_and_coast, set().union(*retreat_ops)))
        else:
            province.unit = unit

        if owner_player is not None:
            owner_player.units.add(unit)
        board.units.add(unit)

        if order_type is None:
            return
        try:
            unit.order = board.parse_order(order_type, destination, source)
            if unit.order is not None:
                unit.order.has_failed = has_failed
        except ValueError:
            logger.warning("BAD UNIT INFO: replacing with hold")

    def _load_dp_orders(self, board: Board, dp_data: tuple):
        location, player_name, points, order_type, destination, source = dp_data
        province = board.get_province(location)
        unit = province.unit
        if unit is None:
            logger.warning("Couldn't find unit for DP order at %s", location)
            return
        player = board.get_player(player_name)
        if player is None:
            logger.warning("Couldn't find player %s for DP order at %s", player_name, location)
            return
        try:
            dp_order = board.parse_order(order_type, destination, source)
            if dp_order is not None:
                unit.dp_allocations[player.name] = DPAllocation(int(points), dp_order)
        except ValueError:
            logger.warning("BAD UNIT INFO: replacing with hold")

    def _get_board(
        self,
        board_id: int,
        turn: Turn,
        data_file: str,
        cursor,
        clear_status: bool = False,
    ) -> Board:
        logger.info("Loading board with ID %s", board_id)
        # TODO - we should eventually store things like coords, adjacencies, etc
        #  so we don't have to reparse the whole board each time
        parser_result = get_parser(data_file)
        if isinstance(parser_result, str):
            logger.error("Failed to load board %s: %s", board_id, parser_result)
            raise ValueError(f"Failed to load board {board_id}: {parser_result}")

        chaos_query = cursor.execute(
            "SELECT parameter_value FROM board_parameters WHERE board_id=? AND parameter_key=?",
            (board_id, "chaos"),
        ).fetchone()
        board = parser_result.parse(chaos=chaos_query[0] == "enabled" if chaos_query else False)
        board.turn = turn
        board.board_id = board_id

        board_params = cursor.execute(
            "SELECT parameter_key, parameter_value FROM board_parameters WHERE board_id=?",
            (board_id,),
        ).fetchall()
        # Turning a key deliniated with slashes into a nested dict
        for key, value in board_params:
            board.set_data(key.split("/"), value)

        if not board.is_chaos():
            board.update_players()

        for player in board.players:
            player.units = set()
            player.centers = set()
        if board.turn.is_builds():
            self._load_builds(cursor, board_id, board)

        province_data = cursor.execute(
            "SELECT province_name, owner, core, half_core FROM provinces WHERE board_id=? and phase_index=?",
            (board_id, board.turn.get_index()),
        ).fetchall()
        province_info_by_name = {
            province_name: (owner, core, half_core)
            for province_name, owner, core, half_core in province_data
        }

        if clear_status:
            cursor.execute("UPDATE units SET failed_order=False WHERE board_id=? and phase_index=?",
                (board_id, board.turn.get_index()))
            cursor.execute("UPDATE builds SET failed_order=False WHERE board_id=? and phase_index=?",
                (board_id, board.turn.get_index()))
        unit_data = cursor.execute(
            "SELECT location, is_dislodged, owner, unit_type, order_type, " +
                   "order_destination, order_source, failed_order " +
            "FROM units WHERE board_id=? and phase_index=?",
            (board_id, board.turn.get_index()),
        ).fetchall()
        for province in board.provinces:
            self._load_province(board, province, province_info_by_name)

        board.units.clear()
        for unit_info in unit_data:
            self._load_unit(board, board_id, unit_info, cursor)

        dp_data = cursor.execute(
            "SELECT location, player, points, order_type, order_destination, order_source " +
            "FROM dp_orders WHERE board_id=? and phase_index=?",
            (board_id, board.turn.get_index()),
        ).fetchall()
        for dp_info in dp_data:
            self._load_dp_orders(board, dp_info)

        return board

    def save_board(self, board_id: int, board: Board):
        """Saves a board to the database."""
        def flatten_dict(d: dict, parent_key: str = "", sep: str = "/") -> dict:
            items = {}
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.update(flatten_dict(v, new_key, sep=sep))
                else:
                    items[new_key] = v
            return items

        # TODO: Check if board already exists
        cursor = self._connection.cursor()

        cursor.execute("DELETE FROM board_parameters WHERE board_id=?", (board_id,))
        cursor.executemany(
            "INSERT INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
            [
                (board_id, key, str(value))
                for key, value in flatten_dict(board.custom_data).items()
            ],
        )

        cursor.execute(
            "INSERT INTO boards (board_id, phase, phase_index, data_file) VALUES (?, ?, ?, ?)",
            (board_id, format(board.turn, DATE_STRING_FORMAT), format(board.turn, "%i"), board.datafile),
        )
        cursor.executemany(
            "INSERT OR REPLACE INTO players (board_id, player_name, color, liege, points) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    player.name,
                    board.data["players"][player.name].get("custom_color", player.default_color),
                    None,
                    0,
                )
                for player in board.players
            ],
        )

        cursor.executemany(
            "INSERT INTO provinces (board_id, phase, phase_index, province_name, owner, core, half_core) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    province.name,
                    province.get_owner_name(),
                    province.core_data.core.name if province.core_data.core else None,
                    province.core_data.half_core.name if province.core_data.half_core else None,
                )
                for province in board.provinces
            ],
        )
        cursor.executemany(
            "INSERT INTO builds (board_id, phase, phase_index, player, location, order_type, unit_type, failed_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    player.name,
                    build_order.province.get_name(build_order.coast),
                    build_order.__class__.__name__,
                    ((build_order.unit_type.code if isinstance(build_order, Build) else "")
                     + ("" if build_order.coast is None else f" {build_order.coast}")),
                    build_order.has_failed,
                )
                for player in board.players
                for build_order in player.build_orders if isinstance(build_order, PlayerOrder)
            ],
        )
        self._save_units(board_id, board)
        self._save_retreat_options(board_id, board)
        cursor.executemany(
            "INSERT INTO dp_orders (board_id, phase, phase_index, location, player, points, " +
                                   "order_type, order_destination, order_source) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    unit.province.get_name(unit.coast),
                    dp_player,
                    dp_order.points,
                    dp_order.order.__class__.__name__,
                    dp_order.order.get_destination_str() if dp_order.order is not None else None,
                    dp_order.order.get_source_str() if dp_order.order is not None else None,
                )
                for unit in board.units
                if unit.player is None or not unit.player.is_active
                for dp_player, dp_order in unit.dp_allocations.items()
            ],
        )
        cursor.close()
        self._connection.commit()

    def save_board_state(self, board_id: int, board: Board):
        """Atomically persists the current in-memory board state
        for players, provinces, units, and retreat options.
        Used to save the board after .edit commands
        """
        cursor = self._connection.cursor()
        phase = board.turn.get_index()

        # We delete and re-create units and retreat options, since some might be removed via command
        cursor.execute("DELETE FROM retreat_options WHERE board_id=? AND phase_index=?", (board_id, phase))
        cursor.execute("DELETE FROM units WHERE board_id=? AND phase_index=?", (board_id, phase))

        cursor.executemany(
            "UPDATE provinces SET owner=?, core=?, half_core=? "
            "WHERE board_id=? AND phase_index=? AND province_name=?",
            [
                (
                    province.get_owner_name(),
                    province.core_data.core.name if province.core_data.core else None,
                    province.core_data.half_core.name if province.core_data.half_core else None,
                    board_id,
                    phase,
                    province.name,
                )
                for province in board.provinces
            ],
        )

        self._save_units(board_id, board)
        self._save_retreat_options(board_id, board)

        cursor.close()
        self._connection.commit()

    def save_order_for_units(self, board: Board, units: Iterable[Unit]):
        """Saves orders for the given units."""
        cursor = self._connection.cursor()
        cursor.executemany(
            "UPDATE units SET order_type=?, order_destination=?, order_source=?, failed_order=? "
            "WHERE board_id=? and phase_index=? and (location=? or location=?) and is_dislodged=?",
            [
                (
                    unit.order.__class__.__name__ if unit.order is not None else None,
                    unit.order.get_destination_str() if unit.order is not None else None,
                    unit.order.get_source_str() if unit.order is not None else None,
                    unit.order.has_failed if unit.order is not None else False,
                    board.board_id,
                    board.turn.get_index(),
                    unit.province.get_name(unit.coast),
                    f"{unit.province.get_name()} coast" if not unit.coast else None, # Legacy coast support
                    unit.province.dislodged_unit == unit,
                )
                for unit in units
            ],
        )
        cursor.executemany(
            "DELETE FROM dp_orders WHERE board_id=? and phase_index=? and location=?",
            [
                (
                    board.board_id,
                    board.turn.get_index(),
                    unit.province.get_name(unit.coast),
                )
                for unit in units
                if unit.player is None or not unit.player.is_active
            ],
        )
        cursor.executemany(
            "INSERT INTO dp_orders (board_id, phase, phase_index, location, player, points, order_type, " +
                                   "order_destination, order_source) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
             [
                (
                    board.board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    unit.province.get_name(unit.coast),
                    dp_player,
                    dp_order.points,
                    dp_order.order.__class__.__name__,
                    dp_order.order.get_destination_str() if dp_order.order is not None else None,
                    dp_order.order.get_source_str() if dp_order.order is not None else None,
                )
                for unit in units
                if unit.player is None or not unit.player.is_active
                for dp_player, dp_order in unit.dp_allocations.items()
            ],
        )
        cursor.executemany(
            "DELETE FROM retreat_options WHERE board_id=? and phase_index=? and origin=?",
            [
                (
                    board.board_id,
                    board.turn.get_index(),
                    unit.province.get_name(unit.coast),
                )
                for unit in units
                if unit.retreat_options is not None
            ],
        )
        cursor.executemany(
            "INSERT INTO retreat_options (board_id, phase, phase_index, origin, retreat_loc) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    board.board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    unit.province.get_name(unit.coast),
                    retreat_option[0].get_name(retreat_option[1]),
                )
                for unit in units
                if unit.retreat_options is not None
                for retreat_option in unit.retreat_options
            ],
        )
        cursor.close()
        self._connection.commit()

    def save_build_orders_for_players(self, board: Board, player: Player | None):
        """Stores build/disband/etc. orders for the given player, or all players if None."""
        if player is None:
            players = board.players
        else:
            players = {player}
        cursor = self._connection.cursor()
        cursor.executemany(
            "DELETE FROM builds WHERE board_id=? AND phase_index=? AND player=?",
            [(board.board_id, board.turn.get_index(), p.name) for p in players],
        )
        cursor.executemany(
            "INSERT OR REPLACE INTO builds (board_id, phase, phase_index, player, location, order_type, unit_type, failed_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ",
            [
                (
                    board.board_id,
                    format(board.turn, DATE_STRING_FORMAT),
                    format(board.turn, "%i"),
                    player.name,
                    build_order.province.get_name(build_order.coast),
                    build_order.__class__.__name__,
                    ((build_order.unit_type.code if isinstance(build_order, Build) else "")
                     + ("" if build_order.coast is None else f" {build_order.coast}")),
                    build_order.has_failed,
                )
                for player in players
                for build_order in player.build_orders if isinstance(build_order, PlayerOrder)
            ],
        )
        cursor.executemany(
            "INSERT OR REPLACE INTO builds (board_id, phase, phase_index, player, location, order_type, unit_type, failed_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (board.board_id, format(board.turn, DATE_STRING_FORMAT), format(board.turn, "%i"), player.name, player.waived_orders, "Waive", "", False)
                for player in players
            ]
        )
        cursor.close()
        self._connection.commit()

    def get_spec_requests(self) -> dict[int, list[SpecRequest]]:
        """Gets all spec requests, organized by server ID."""
        requests = {}
        cursor = self._connection.cursor()
        request_data = cursor.execute("SELECT server_id, user_id, role_id FROM spec_requests").fetchall()
        cursor.close()

        for s_id, u_id, r_id in request_data:
            request = SpecRequest(s_id, u_id, r_id)
            requests.setdefault(s_id, []).append(request)

        return requests

    def save_spec_request(self, request: SpecRequest):
        """Saves a spec request to the database."""
        cursor = self._connection.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO spec_requests (server_id, user_id, role_id) VALUES (?, ?, ?)",
            (request.server_id, request.user_id, request.role_id),
        )
        cursor.close()
        self._connection.commit()

    def load_ctx_parameters(self) -> dict:
        """Loads all context parameters from the database."""
        parameters = {}
        cursor = self._connection.cursor()
        result = cursor.execute("SELECT context_id, parameter_key, parameter_value FROM ctx_parameters").fetchall()
        for context_id, parameter_key, parameter_value in result:
            parameters[context_id] = parameters.get(context_id, {})
            keys = parameter_key.split('/')
            data = parameters[context_id]
            for key in keys[:-1]:
                data = data.setdefault(key, {})
            data[keys[-1]] = parameter_value
        cursor.close()
        return parameters

    def delete_board(self, board: Board):
        """Deletes a board and all associated data for that phase."""
        cursor = self._connection.cursor()
        phase = board.turn.get_index()
        cursor.execute("DELETE FROM boards WHERE board_id=? AND phase_index=?", (board.board_id, phase))
        cursor.execute("DELETE FROM provinces WHERE board_id=? AND phase_index=?", (board.board_id, phase))
        cursor.execute("DELETE FROM units WHERE board_id=? AND phase_index=?", (board.board_id, phase))
        cursor.execute("DELETE FROM dp_orders WHERE board_id=? AND phase_index=?", (board.board_id, phase))
        cursor.execute("DELETE FROM builds WHERE board_id=? AND phase_index=?", (board.board_id, phase))
        cursor.execute("DELETE FROM retreat_options WHERE board_id=? AND phase_index=?", (board.board_id, phase))
        cursor.close()
        self._connection.commit()

    def total_delete(self, board_id: int):
        """Deletes a board and all associated data by board_id, regardless of phase."""
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM boards WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM board_parameters WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM provinces WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM units WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM dp_orders WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM builds WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM retreat_options WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM players WHERE board_id=?", (board_id,))
        cursor.execute("DELETE FROM spec_requests WHERE server_id=?", (board_id,))
        cursor.close()
        self._connection.commit()

    def execute_arbitrary_sql(self, sql: str, args: tuple):
        """Executes an arbitrary SQL command. Probably should be deprecated in the future."""
        # TODO - everywhere using this should just be made into a method probably? idk
        cursor = self._connection.cursor()
        cursor.execute(sql, args)
        cursor.close()
        self._connection.commit()

    def __del__(self):
        self._connection.commit()
        self._connection.close()


_db_class: _DatabaseConnection | None = None


def get_connection() -> _DatabaseConnection:
    global _db_class
    if _db_class:
        return _db_class
    _db_class = _DatabaseConnection()
    return _db_class
