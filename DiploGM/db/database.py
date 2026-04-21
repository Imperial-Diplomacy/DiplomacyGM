"""Module to handle database interactions."""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from typing import TYPE_CHECKING, Optional

# TODO: Find a better way to do this
# maybe use a copy from manager?
from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.models.turn import Turn
from DiploGM.models.order import (
    PlayerOrder, Build, Disband, TransformBuild,
    Vassal, Liege, DualMonarchy, Disown, Defect, RebellionMarker
)
from DiploGM.models.unit import DPAllocation, UnitType, Unit

from DiploGM.models.spec_request import SpecRequest

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.player import Player
    from DiploGM.models.province import Province

logger = logging.getLogger(__name__)

SQL_FILE_PATH = "bot_db.sqlite"


class _DatabaseConnection:
    def __init__(self, db_file: str = SQL_FILE_PATH):
        try:
            self._connection = sqlite3.connect(db_file)
            logger.info("Connection to SQLite DB successful")
        except IOError as ex:
            logger.error("Could not open SQLite DB", exc_info=ex)
            self._connection = sqlite3.connect(
                ":memory:"
            )  # Special wildcard; in-memory db

        self._initialize_schema()

    def _initialize_schema(self):
        # FIXME: move the sql file somewhere more accessible (maybe it shouldn't be inside the package? /resources ?)
        with open("DiploGM/db/schema.sql", "r", encoding="utf-8") as sql_file:
            cursor = self._connection.cursor()
            cursor.executescript(sql_file.read())
            cursor.close()

    def get_boards(self, board_ids:Optional[list[int]] = None) -> dict[int, Board]:
        """Gets all boards from the database, or a subset if board_ids is provided."""
        cursor = self._connection.cursor()

        if board_ids is not None:
            placeholders = ",".join("?" for _ in board_ids)
            sql = f"SELECT * FROM boards WHERE board_id IN ({placeholders})"
            board_data = cursor.execute(sql, board_ids).fetchall()
        else:
            board_data = cursor.execute("SELECT * FROM boards").fetchall()

        board_keys = [(row[0], row[1]) for row in board_data]
        logger.info("Loading %s boards from DB", len(board_data))
        boards: dict[int, Board] = {}
        for board_row in board_data:
            board_id, phase_string, data_file, _, _ = board_row

            current_turn = Turn.turn_from_string(phase_string)
            if current_turn is None:
                logger.warning("Could not parse turn string '%s' for board %s", phase_string, board_id)
                continue
            if (board_id, str(current_turn.get_next_turn())) in board_keys:
                continue

            board = self._get_board(board_id, current_turn, data_file, cursor)
            board.turn = Turn(board.data["year"] + board.turn.year, board.turn.phase, board.data["year"])

            boards[board_id] = board

        cursor.close()
        logger.info("Successfully loaded")
        return boards

    def get_old_board(self, board: Board, turn: Turn) -> Board | None:
        """Finds an older board from that same game"""
        return self.get_board(board.board_id, turn, board.datafile)

    def get_board(
        self,
        board_id: int,
        turn: Turn,
        data_file: str,
        clear_status: bool = False,
    ) -> Board | None:
        """Gets a board from the database.
        clear_status is used to wipe out failed order information, which we need to do for rollbacks."""
        # TODO: Stuff like fish and name should be board parameters
        cursor = self._connection.cursor()

        board_data = cursor.execute(
            "SELECT * FROM boards WHERE board_id=? and phase=?",
            (board_id, format(turn, "%I %S")),
        ).fetchone()
        if not board_data:
            cursor.close()
            return None

        board = self._get_board(board_id, turn, data_file, cursor, clear_status=clear_status)
        cursor.close()
        return board

    def _load_builds(self, cursor, board_id: int, board: Board):
        builds_data = cursor.execute(
            "SELECT player, location, order_type, unit_type FROM builds WHERE board_id=? and phase=?",
            (board_id, format(board.turn, "%I %S")),
        ).fetchall()

        def get_player_by_name(player_name) -> Player | None:
            player_by_name = {player.name: player for player in board.players}

            if player_name not in player_by_name:
                logger.warning(f"Unknown player: {player_name}")
                return None

            return player_by_name[player_name]

        for player_name, location, order_type, unit_type in builds_data:
            player = get_player_by_name(player_name)

            if player is None:
                continue

            if order_type == "Build":
                player_order = Build(
                    board.get_province(location),
                    UnitType(unit_type[0]),
                    unit_type[-2:] if len(unit_type) > 1 else None,
                )
            elif order_type == "Disband":
                player_order = Disband(board.get_province(location))
            elif order_type == "TransformBuild":
                player_order = TransformBuild(board.get_province(location),
                                              unit_type[-2:] if len(unit_type) > 1 else None)
            else:
                logger.warning(f"Unknown build order type: {order_type}")
                continue

            player.build_orders.add(player_order)

        vassals_data = cursor.execute(
            "SELECT player, target_player, order_type FROM vassal_orders WHERE board_id=? and phase=?",
            (board_id, format(board.turn, "%I %S")),
        ).fetchall()

        order_classes = [
            Vassal,
            Liege,
            DualMonarchy,
            Disown,
            Defect,
            RebellionMarker,
        ]

        for player_name, target_player_name, order_type in vassals_data:
            player = get_player_by_name(player_name)
            target_player = get_player_by_name(target_player_name)
            assert player is not None
            assert target_player is not None
            order_class = next(
                order_class
                for order_class in order_classes
                if order_class.__name__ == order_type
            )

            order = order_class(target_player)

            player.vassal_orders[target_player] = order

    def _load_province(self, board: Board, province: Province, province_info_by_name: dict):
        if province.name not in province_info_by_name:
            logger.warning(f"Couldn't find province {province.name} in DB")
            return

        owner, core, half_core = province_info_by_name[province.name]

        if owner == "Impassable" or owner is None:
            province.owner = None
        else:
            owner_player = board.get_player(owner)
            if owner_player is None:
                logger.warning(
                    f"Couldn't find corresponding player for {owner} in DB"
                )
            else:
                province.owner = owner_player

                if province.has_supply_center:
                    owner_player.centers.add(province)

        province.is_impassable = owner == "Impassable"

        core_player = None
        if core is not None:
            core_player = board.get_player(core)
        province.core_data.core = core_player

        half_core_player = None
        if half_core is not None:
            half_core_player = board.get_player(half_core)
        province.core_data.half_core = half_core_player
        province.unit = None
        province.dislodged_unit = None

    def _load_unit(self, board: Board, board_id: int, unit_info: tuple, cursor):
        (
            location,
            is_dislodged,
            owner,
            is_army,
            order_type,
            order_destination,
            order_source,
            has_failed,
        ) = unit_info
        province, coast = board.get_province_and_coast(location)
        owner_player = None
        if owner is not None and (owner_player := board.get_player(owner)) is None:
            logger.warning("Couldn't find corresponding player for %s in DB", owner)
            return
        if is_dislodged:
            retreat_ops = cursor.execute(
                "SELECT retreat_loc FROM retreat_options WHERE board_id=? and phase=? and origin=?",
                (board_id, format(board.turn, "%I %S"), location),
            )
            retreat_options = set(
                map(board.get_province_and_coast, set().union(*retreat_ops))
            )
        else:
            retreat_options = None
        unit = Unit(
            UnitType.ARMY if is_army else UnitType.FLEET,
            owner_player,
            province,
            coast,
        )
        if is_dislodged:
            province.dislodged_unit = unit
            unit.retreat_options = retreat_options
        else:
            province.unit = unit
        if owner_player is not None:
            owner_player.units.add(unit)
        board.units.add(unit)

        if order_type is None:
            return
        try:
            order = board.parse_order(order_type, order_destination, order_source)
            if order is not None:
                order.has_failed = has_failed
            unit.order = order
        except ValueError:
            logger.warning("BAD UNIT INFO: replacing with hold")

    def _load_dp_orders(self, board: Board, dp_data: tuple):
        location, player_name, points, order_type, order_destination, order_source = dp_data
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
            dp_order = board.parse_order(order_type, order_destination, order_source)
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
        board = get_parser(data_file).parse()
        board.turn = turn
        board.board_id = board_id

        board_params = cursor.execute(
            "SELECT parameter_key, parameter_value FROM board_parameters WHERE board_id=?",
            (board_id,),
        ).fetchall()

        # Turning a key deliniated with slashes into a nested dict
        for key, value in board_params:
            board.set_data(key.split("/"), value)

        if board.data["players"] != "chaos":
            board.update_players()

        player_data = cursor.execute(
            "SELECT player_name, color, liege, points FROM players WHERE board_id=?",
            (board_id,),
        ).fetchall()
        player_info_by_name = {
            player_name: (color, liege, points)
            for player_name, color, liege, points in player_data
        }
        name_to_player = {player.name: player for player in board.players}
        for player in board.players:
            if player.name not in player_info_by_name:
                logger.warning("Couldn't find player %s in DB", player.name)
                continue
            color, liege, points = player_info_by_name[player.name]
            player.render_color = color
            if liege is not None:
                try:
                    player.liege = name_to_player[liege]
                    player.liege.vassals.append(player)
                except KeyError:
                    logger.warning("Invalid liege of player %s: %s", player.name, liege)
            player.points = points
            player.units = set()
            player.centers = set()
        if board.turn.is_builds():
            self._load_builds(cursor, board_id, board)

        province_data = cursor.execute(
            "SELECT province_name, owner, core, half_core FROM provinces WHERE board_id=? and phase=?",
            (board_id, format(board.turn, "%I %S")),
        ).fetchall()
        province_info_by_name = {
            province_name: (owner, core, half_core)
            for province_name, owner, core, half_core in province_data
        }

        if clear_status:
            cursor.execute("UPDATE units SET failed_order=False WHERE board_id=? and phase=?",
                (board_id, format(board.turn, "%I %S")))
        unit_data = cursor.execute(
            "SELECT location, is_dislodged, owner, is_army, order_type, " +
                   "order_destination, order_source, failed_order " +
            "FROM units WHERE board_id=? and phase=?",
            (board_id, format(board.turn, "%I %S")),
        ).fetchall()
        for province in board.provinces:
            self._load_province(board, province, province_info_by_name)

        board.units.clear()
        for unit_info in unit_data:
            self._load_unit(board, board_id, unit_info, cursor)

        dp_data = cursor.execute(
            "SELECT location, player, points, order_type, order_destination, order_source " +
            "FROM dp_orders WHERE board_id=? and phase=?",
            (board_id, format(board.turn, "%I %S")),
        ).fetchall()
        for dp_info in dp_data:
            self._load_dp_orders(board, dp_info)

        board.run_variant_scripts()

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
            "INSERT INTO boards (board_id, phase, data_file, fish, name) VALUES (?, ?, ?, ?, ?)",
            (board_id, format(board.turn, "%I %S"), board.datafile, board.data.get("fish", 0), board.data.get("game_name")),
        )
        cursor.executemany(
            "INSERT INTO players (board_id, player_name, color, liege, points) VALUES (?, ?, ?, ?, ?) ON CONFLICT "
            "DO UPDATE SET "
            "color = ?, "
            "liege = ?, "
            "points = ?",
            [
                (
                    board_id,
                    player.name,
                    player.render_color,
                    (None if player.liege is None else str(player.liege)),
                    player.points,
                    player.render_color,
                    (None if player.liege is None else str(player.liege)),
                    player.points,
                )
                for player in board.players
            ],
        )

        # cache = []
        # for p in board.provinces:
        #     if p.name == "NICE":
        #         print(p.type)
        #         import matplotlib.pyplot as plt
        #         import shapely
        #         if isinstance(p.geometry, shapely.Polygon):
        #             plt.plot(*p.geometry.exterior.xy)
        #         else:
        #             for geo in p.geometry.geoms:
        #                 plt.plot(*geo.exterior.xy)
        # plt.gca().invert_yaxis()
        # plt.show()

        cache = []
        for p in board.provinces:
            if p.name in cache:
                print(f"{p.name} repeats!!!")
            cache.append(p.name)

        cursor.executemany(
            "INSERT INTO provinces (board_id, phase, province_name, owner, core, half_core) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, "%I %S"),
                    province.name,
                    province.get_owner_name(),
                    province.core_data.core.name if province.core_data.core else None,
                    province.core_data.half_core.name if province.core_data.half_core else None,
                )
                for province in board.provinces
            ],
        )
        cursor.executemany(
            "INSERT INTO builds (board_id, phase, player, location, order_type, unit_type) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, "%I %S"),
                    player.name,
                    build_order.province.get_name(build_order.coast),
                    build_order.__class__.__name__,
                    ((build_order.unit_type.value if isinstance(build_order, Build) else "")
                     + ("" if build_order.coast is None else f" {build_order.coast}")),
                )
                for player in board.players
                for build_order in player.build_orders if isinstance(build_order, PlayerOrder)
            ],
        )
        # TODO - this is hacky
        cursor.executemany(
            "INSERT INTO units (board_id, phase, location, is_dislodged, owner, " +
                                "is_army, order_type, order_destination, order_source, failed_order) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, "%I %S"),
                    unit.province.get_name(unit.coast),
                    unit == unit.province.dislodged_unit,
                    unit.player.name if unit.player else None,
                    unit.unit_type == UnitType.ARMY,
                    unit.order.__class__.__name__ if unit.order is not None else None,
                    unit.order.get_destination_str() if unit.order is not None else None,
                    unit.order.get_source_str() if unit.order is not None else None,
                    unit.order.has_failed if unit.order is not None else False
                )
                for unit in board.units
            ],
        )
        cursor.executemany(
            "INSERT INTO retreat_options (board_id, phase, origin, retreat_loc) VALUES (?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, "%I %S"),
                    unit.province.get_name(unit.coast),
                    retreat_option[0].get_name(retreat_option[1]),
                )
                for unit in board.units
                if unit.retreat_options is not None
                for retreat_option in unit.retreat_options
            ],
        )
        cursor.executemany(
            "INSERT INTO dp_orders (board_id, phase, location, player, points, " +
                                   "order_type, order_destination, order_source) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    format(board.turn, "%I %S"),
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
        phase = format(board.turn, "%I %S")

        # We delete and re-create units and retreat options, since some might be removed via command
        cursor.execute("DELETE FROM retreat_options WHERE board_id=? AND phase=?", (board_id, phase))
        cursor.execute("DELETE FROM units WHERE board_id=? AND phase=?", (board_id, phase))

        cursor.executemany(
            "UPDATE players SET color=?, liege=?, points=? WHERE board_id=? AND player_name=?",
            [
                (
                    player.render_color,
                    (None if player.liege is None else str(player.liege)),
                    player.points,
                    board_id,
                    player.name,
                )
                for player in board.players
            ],
        )

        cursor.executemany(
            "UPDATE provinces SET owner=?, core=?, half_core=? "
            "WHERE board_id=? AND phase=? AND province_name=?",
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

        cursor.executemany(
            "INSERT INTO units (board_id, phase, location, is_dislodged, owner, "
            "is_army, order_type, order_destination, order_source, failed_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    board_id,
                    phase,
                    unit.province.get_name(unit.coast),
                    unit == unit.province.dislodged_unit,
                    unit.player.name if unit.player else None,
                    unit.unit_type == UnitType.ARMY,
                    unit.order.__class__.__name__ if unit.order is not None else None,
                    unit.order.get_destination_str() if unit.order is not None else None,
                    unit.order.get_source_str() if unit.order is not None else None,
                    unit.order.has_failed if unit.order is not None else False,
                )
                for unit in board.units
            ],
        )

        cursor.executemany(
            "INSERT INTO retreat_options (board_id, phase, origin, retreat_loc) VALUES (?, ?, ?, ?)",
            [
                (
                    board_id,
                    phase,
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

    def save_order_for_units(self, board: Board, units: Iterable[Unit]):
        """Saves orders for the given units."""
        cursor = self._connection.cursor()
        cursor.executemany(
            "UPDATE units SET order_type=?, order_destination=?, order_source=?, failed_order=? "
            "WHERE board_id=? and phase=? and (location=? or location=?) and is_dislodged=?",
            [
                (
                    unit.order.__class__.__name__ if unit.order is not None else None,
                    unit.order.get_destination_str() if unit.order is not None else None,
                    unit.order.get_source_str() if unit.order is not None else None,
                    unit.order.has_failed if unit.order is not None else False,
                    board.board_id,
                    format(board.turn, "%I %S"),
                    unit.province.get_name(unit.coast),
                    f"{unit.province.get_name()} coast" if not unit.coast else None, # Legacy coast support
                    unit.province.dislodged_unit == unit,
                )
                for unit in units
            ],
        )
        cursor.executemany(
            "DELETE FROM dp_orders WHERE board_id=? and phase=? and location=?",
            [
                (
                    board.board_id,
                    format(board.turn, "%I %S"),
                    unit.province.get_name(unit.coast),
                )
                for unit in units
                if unit.player is None or not unit.player.is_active
            ],
        )
        cursor.executemany(
            "INSERT INTO dp_orders (board_id, phase, location, player, points, order_type, " +
                                   "order_destination, order_source) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
             [
                (
                    board.board_id,
                    format(board.turn, "%I %S"),
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
            "DELETE FROM retreat_options WHERE board_id=? and phase=? and origin=?",
            [
                (
                    board.board_id,
                    format(board.turn, "%I %S"),
                    unit.province.get_name(unit.coast),
                )
                for unit in units
                if unit.retreat_options is not None
            ],
        )
        cursor.executemany(
            "INSERT INTO retreat_options (board_id, phase, origin, retreat_loc) VALUES (?, ?, ?, ?)",
            [
                (
                    board.board_id,
                    format(board.turn, "%I %S"),
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
        """Stores build/disband/vassal/etc. orders for the given player, or all players if None."""
        if player is None:
            players = board.players
        else:
            players = {player}
        cursor = self._connection.cursor()
        cursor.executemany(
            "DELETE FROM builds WHERE board_id=? AND phase=? AND player=?",
            [(board.board_id, format(board.turn, "%I %S"), p.name) for p in players],
        )
        cursor.executemany(
            "DELETE FROM vassal_orders WHERE board_id=? AND phase=? AND player=?",
            [(board.board_id, format(board.turn, "%I %S"), p.name) for p in players],
        )
        cursor.executemany(
            "INSERT INTO builds (board_id, phase, player, location, order_type, unit_type) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (board_id, phase, player, location) DO UPDATE SET order_type=?, unit_type=?",
            [
                (
                    board.board_id,
                    format(board.turn, "%I %S"),
                    player.name,
                    build_order.province.get_name(build_order.coast),
                    build_order.__class__.__name__,
                    ((build_order.unit_type.value if isinstance(build_order, Build) else "")
                     + ("" if build_order.coast is None else f" {build_order.coast}")),
                    build_order.__class__.__name__,
                    ((build_order.unit_type.value if isinstance(build_order, Build) else "")
                     + ("" if build_order.coast is None else f" {build_order.coast}")),
                )
                for player in players
                for build_order in player.build_orders if isinstance(build_order, PlayerOrder)
            ],
        )
        cursor.executemany(
            "INSERT INTO vassal_orders (board_id, phase, player, target_player, order_type) VALUES (?, ?, ?, ?, ?) ",
            [
                (
                    board.board_id,
                    format(board.turn, "%I %S"),
                    player.name,
                    build_order.player.name,
                    build_order.__class__.__name__,
                )
                for player in players
                for build_order in player.vassal_orders.values()
            ],
        )
        cursor.close()
        self._connection.commit()

    def get_spec_requests(self) -> dict[int, list[SpecRequest]]:
        """Gets all spec requests, organized by server ID."""
        requests = {}

        cursor = self._connection.cursor()
        request_data = cursor.execute(
            "SELECT server_id, user_id, role_id FROM spec_requests"
        ).fetchall()
        cursor.close()

        for s_id, u_id, r_id in request_data:
            if s_id not in requests:
                requests[s_id] = []

            request = SpecRequest(s_id, u_id, r_id)
            requests[s_id].append(request)

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

    def delete_board(self, board: Board):
        """Deletes a board and all associated data for that phase."""
        cursor = self._connection.cursor()
        cursor.execute(
            "DELETE FROM boards WHERE board_id=? AND phase=?",
            (board.board_id, format(board.turn, "%I %S")),
        )
        cursor.execute(
            "DELETE FROM provinces WHERE board_id=? AND phase=?",
            (board.board_id, format(board.turn, "%I %S")),
        )
        cursor.execute(
            "DELETE FROM units WHERE board_id=? AND phase=?",
            (board.board_id, format(board.turn, "%I %S")),
        )
        cursor.execute(
            "DELETE FROM dp_orders WHERE board_id=? AND phase=?",
            (board.board_id, format(board.turn, "%I %S")),
        )
        cursor.execute(
            "DELETE FROM builds WHERE board_id=? AND phase=?",
            (board.board_id, format(board.turn, "%I %S")),
        )
        cursor.execute(
            "DELETE FROM retreat_options WHERE board_id=? AND phase=?",
            (board.board_id, format(board.turn, "%I %S")),
        )
        cursor.execute(
            "DELETE FROM vassal_orders WHERE board_id=? AND phase=?",
            (board.board_id, format(board.turn, "%I %S")),
        )
        cursor.close()
        self._connection.commit()

    def total_delete(self, board: Board):
        """Deletes a board and all associated data, regardless of phase."""
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM boards WHERE board_id=?", (board.board_id,))
        cursor.execute("DELETE FROM board_parameters WHERE board_id=?", (board.board_id,))
        cursor.execute("DELETE FROM provinces WHERE board_id=?", (board.board_id,))
        cursor.execute("DELETE FROM units WHERE board_id=?", (board.board_id,))
        cursor.execute("DELETE FROM dp_orders WHERE board_id=?", (board.board_id,))
        cursor.execute("DELETE FROM builds WHERE board_id=?", (board.board_id,))
        cursor.execute(
            "DELETE FROM retreat_options WHERE board_id=?", (board.board_id,)
        )
        cursor.execute("DELETE FROM players WHERE board_id=?", (board.board_id,))
        cursor.execute("DELETE FROM spec_requests WHERE server_id=?", (board.board_id,))
        cursor.close()
        self._connection.commit()

    def execute_arbitrary_sql(self, sql: str, args: tuple):
        # TODO - everywhere using this should just be made into a method probably? idk
        cursor = self._connection.cursor()
        cursor.execute(sql, args)
        cursor.close()
        self._connection.commit()

    def executemany_arbitrary_sql(self, sql: str, args: list[tuple]):
        cursor = self._connection.cursor()
        cursor.executemany(sql, args)
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
