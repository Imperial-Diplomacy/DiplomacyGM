import asyncio
import logging
import time
import os

from discord import Member, User

from DiploGM.utils.singleton import SingletonMeta
from DiploGM.errors import MapRenderError, NoGameError
from DiploGM.adjudicator.make_adjudicator import make_adjudicator
from DiploGM.adjudicator.defs import Resolution
from DiploGM.mapper.mapper import Mapper
from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.models.turn import Turn
from DiploGM.models.board import Board
from DiploGM.db import database
from DiploGM.models.player import Player
from DiploGM.models.spec_request import SpecRequest
from DiploGM.utils.sanitise import parse_variant_path, simple_player_name

logger = logging.getLogger(__name__)


class Manager(metaclass=SingletonMeta):
    """Manager acts as an intermediary between Bot (the Discord API), Board (the board state), the database."""

    def __init__(self):
        self._database = database.get_connection()
        self._boards: dict[int, Board] = {}
        self._board_locks: dict[int, asyncio.Lock] = {}
        self._spec_requests: dict[int, list[SpecRequest]] = (
            self._database.get_spec_requests()
        )
        self.last_activity: dict[int, dict[str, float]] = {}

        # Stores failed and DP orders here, since we don't want them stored in the board itself
        # As that way we can fetch them for test adjudications without mutating the board state
        # We store the values as strings because we don't want to modify existing Province objects
        # Ideally we should deepcopy the board, but it requires a custom implementation
        self.last_failed_orders: dict[int, set[str]] = {}
        self.last_dp_orders: dict[
            int, dict[str, tuple[str, str | None, str | None]]
        ] = {}

        self.ctx_parameters: dict = self._database.load_ctx_parameters()

    async def ensure_board_loaded(self, server_id: int) -> None:
        """Ensures a board is loaded into memory for the given server.
        Uses per-server locks to prevent race conditions from concurrent commands."""
        if server_id in self._boards:
            return
        if server_id not in self._board_locks:
            self._board_locks[server_id] = asyncio.Lock()

        async with self._board_locks[server_id]:
            if server_id in self._boards:
                return
            loaded = self._database.load_board(server_id)
            if loaded is not None:
                self._boards[server_id] = loaded

    def list_servers(self) -> set[int]:
        """Gets a list of server ids that have games."""
        return self._database.get_active_board_ids()

    def create_game(
        self, server_id: int, gametype: str = "classic", **kwargs
    ) -> tuple[bool, str]:
        """Creates a new game in the specified server and of the specified variant."""
        if self._boards.get(server_id):
            return False, "A game already exists in this server."
        try:
            variant_path = parse_variant_path(gametype)
        except ValueError as e:
            return False, str(e)
        if not os.path.isdir(variant_path):
            return False, f"Game {gametype} does not exist."

        logger.info("Creating new game in server %s", server_id)
        parser_result = get_parser(gametype)
        if isinstance(parser_result, str):
            return False, parser_result
        self._boards[server_id] = parser_result.parse(**kwargs)
        self._boards[server_id].board_id = server_id
        if kwargs.get("fow"):
            self._boards[server_id].set_data("fow", "enabled")
        if kwargs.get("chaos"):
            self._boards[server_id].set_data("chaos", "enabled")
        if kwargs.get("save_board", True) == True:
            self._database.save_board(server_id, self._boards[server_id])

        return True, f"{self._boards[server_id].data['name']} game created"

    def get_spec_request(self, server_id: int, user_id: int) -> SpecRequest | None:
        """Gets a spec request for a user in a server, if it exists."""
        if server_id not in self._spec_requests:
            return None

        for req in self._spec_requests[server_id]:
            if req.user_id == user_id:
                return req

        return None

    def save_spec_request(
        self, server_id: int, user_id: int, role_id: int, override=False
    ) -> str:
        """Saves a spec request for a user in a server."""
        # create new list if first time in server
        if server_id not in self._spec_requests:
            self._spec_requests[server_id] = []

        obj = SpecRequest(server_id, user_id, role_id)

        if self.get_spec_request(server_id, user_id) and not override:
            return "User has already been accepted for a request in this Server."

        self._spec_requests[server_id].append(obj)
        self._database.save_spec_request(obj)

        return "Approved request Logged!"

    def get_board(self, server_id: int) -> Board:
        """Gets the current board for a server.
        Raises a RuntimeError if there is no game in the server."""
        if not (board := self._boards.get(server_id)):
            raise NoGameError("There is no existing game in this server.")
        return board

    def get_board_from_db(self, server_id: int, turn: Turn) -> Board:
        """Loads a fresh board from the database for the given server and turn."""
        cur_board = self.get_board(server_id)
        board = self._database.get_board(cur_board.board_id, turn, cur_board.datafile)
        if board is None:
            raise NoGameError(f"There is no {turn} board for this server")
        return board

    def apply_adjudication_results(self, server_id: int, board: Board) -> None:
        """Applies stored failed orders and DP orders to a fresh board for test drawing."""
        dp_orders = self.last_dp_orders.get(server_id, {})
        for province_name, (order_type, dest_str, source_str) in dp_orders.items():
            province = board.get_province(province_name)
            if province.unit and province.unit.order is None:
                order = board.parse_order(order_type, dest_str, source_str)
                if order:
                    province.unit.order = order

        failed = self.last_failed_orders.get(server_id, set())
        for unit in board.units:
            if unit.order and unit.province.name in failed:
                unit.order.has_failed = True
        for player in board.players:
            for order in player.build_orders:
                if order.province.name in failed:
                    order.has_failed = True

    def total_delete(self, server_id: int):
        """Completely wipes all data for a server."""
        self._database.total_delete(server_id)
        self._boards.pop(server_id, None)

    def draw_map(
        self,
        server_id: int,
        draw_moves: bool = False,
        player_restriction: Player | None = None,
        **kwargs,
    ) -> tuple[bytes, str]:
        """Gets the map for a server.
        draw_moves: whether to draw the moves on the map
        player_restriction: only draws moves that the player knows about
        color_mode: whether to use a special color mode (e.g. dark, pink, etc.)
        turn: whether to draw the map for a previous turn (defaults to current turn)
        movement_only: whether to only draw succcessful moves (used mainly for Carnage)"""
        cur_board = self.get_board(server_id)
        if (turn := kwargs.get("turn")) is None:
            board = cur_board
        else:
            board = self._database.get_board(
                cur_board.board_id,
                turn,
                cur_board.datafile,
            )
            if board is None:
                raise NoGameError(f"There is no {turn} board for this server")
            if board.turn.year < cur_board.turn.year or (
                board.turn.year == cur_board.turn.year
                and board.turn.phase.value < cur_board.turn.phase.value
            ):
                player_restriction = None
            if kwargs.get("fow_player") is not None:
                kwargs["fow_player"] = board.get_player(kwargs["fow_player"].name)
        svg, file_name = self.draw_map_for_board(
            board,
            player_restriction=player_restriction,
            draw_moves=draw_moves,
            **kwargs,
        )
        return svg, file_name

    def draw_map_for_board(
        self,
        board: Board,
        player_restriction: Player | None = None,
        draw_moves: bool = False,
        **kwargs,
    ) -> tuple[bytes, str]:
        """Gets the current map for a board."""
        start = time.time()
        try:
            mapper = Mapper(
                board,
                restriction=kwargs.get("fow_player"),
                color_mode=kwargs.get("color_mode"),
                oil_spill_mode=kwargs.get("oil_spill_mode", False),
                invert_color_mode=kwargs.get("invert_color_mode", False),
                clean_map_mode=kwargs.get("clean_map_mode", False),
            )

            if draw_moves:
                svg, file_name = mapper.draw_moves_map(
                    board.turn,
                    player_restriction=player_restriction,
                    movement_only=kwargs.get("movement_only", False),
                )
            else:
                svg, file_name = mapper.draw_current_map()
        except Exception as e:
            raise MapRenderError("Failed to render map") from e

        elapsed = time.time() - start
        logger.info("manager.draw_map_for_board took %ss", elapsed)
        return svg, file_name

    def adjudicate(
        self, server_id: int, test: bool = False
    ) -> tuple[str | None, Board]:
        """Adjudicates the game for a given board, and saves the result if it's not a test adjudication."""
        start = time.time()

        board = self.get_board(server_id)
        old_board = self._database.get_board(server_id, board.turn, board.datafile)
        assert old_board is not None
        adjudicator = make_adjudicator(old_board)
        adjudicator.save_orders = not test
        new_board = adjudicator.run()
        if old_board.turn.is_builds():
            self.last_failed_orders[server_id] = getattr(
                adjudicator, "failed_build_provinces", set()
            )
        else:
            self.last_failed_orders[server_id] = {
                order.current_province.name
                for order in getattr(adjudicator, "orders", [])
                if order.resolution == Resolution.FAILS
            }
        self.last_dp_orders[server_id] = getattr(adjudicator, "dp_order_strings", {})
        new_board.turn = new_board.turn.get_next_turn()
        message = new_board.run_variant_scripts()
        if message:
            logger.info("Variant script result: %s", message)
        logger.info("Adjudicator ran successfully")
        if not test:
            self._boards[new_board.board_id] = new_board
            self._database.save_board(new_board.board_id, new_board)

        elapsed = time.time() - start
        logger.info("manager.adjudicate.%s.%ss", server_id, elapsed)
        return message, new_board

    def draw_gui_map(
        self,
        server_id: int,
        player_restriction: Player | None = None,
        color_mode: str | None = None,
        fow_player: Player | None = None,
    ) -> tuple[bytes, str]:
        """Draws an GUI map for a board."""
        start = time.time()

        try:
            svg, file_name = Mapper(
                self._boards[server_id], fow_player, color_mode=color_mode
            ).draw_gui_map(self._boards[server_id].turn, player_restriction)
        except Exception as e:
            raise MapRenderError("Failed to render GUI map") from e

        elapsed = time.time() - start
        logger.info("manager.draw_moves_map.%s.%ss", server_id, elapsed)
        return svg, file_name

    def rollback(self, server_id: int) -> tuple[str, bytes, str]:
        """Rolls back the board to the previous turn."""
        logger.info("Rolling back in server %s", server_id)
        board = self.get_board(server_id)
        last_turn = board.turn.get_previous_turn()

        old_board = self._database.get_board(
            board.board_id, last_turn, board.datafile, clear_status=True
        )
        if old_board is None:
            raise ValueError(f"There is no {last_turn} board for this server")

        self._database.delete_board(board)
        self._boards[old_board.board_id] = old_board
        mapper = Mapper(old_board)

        message = f"Rolled back to {old_board.turn:%Y %S}"
        file, file_name = mapper.draw_current_map()
        return message, file, file_name

    def get_previous_board(self, server_id: int) -> Board | None:
        """Gets the previous board for a server. Returns None if it doesn't exist."""
        board = self.get_board(server_id)
        last_turn = board.turn.get_previous_turn()
        old_board = self._database.get_board(board.board_id, last_turn, board.datafile)
        return old_board

    def reload(self, server_id: int) -> tuple[str, bytes, str]:
        """Reloads the board for a server."""
        logger.info("Reloading server %s", server_id)
        board = self.get_board(server_id)

        loaded_board = self._database.get_board(
            board.board_id, board.turn, board.datafile
        )
        if loaded_board is None:
            raise ValueError(f"There is no {board.turn} board for this server")

        self._boards[board.board_id] = loaded_board
        mapper = Mapper(loaded_board)

        message = f"Reloaded board for phase {loaded_board.turn:%Y %S}"
        file, file_name = mapper.draw_current_map()
        return message, file, file_name

    def reload_variant(self, variant: str) -> str:
        """Reloads a variant, including adjacencies and all boards."""
        for server_id, board in self._boards.items():
            if board.datafile == variant:
                logger.info("Reloading board for server %s", server_id)
                loaded_board = self._database.get_board(
                    board.board_id, board.turn, board.datafile
                )
                if loaded_board is None:
                    logger.warning("There is no %s board for this server", board.turn)
                    continue
                self._boards[board.board_id] = loaded_board
        return f"Reloaded variant {variant}"

    def get_member_player_object(self, member: Member | User) -> Player | None:
        """Gets the player object associated with a Discord member, if it exists."""
        if isinstance(member, User):
            return None
        try:
            players = self.get_board(member.guild.id).players
        except NoGameError:
            return None
        for role in member.roles:
            for player in players:
                if simple_player_name(player.name) == simple_player_name(
                    role.name
                ) or simple_player_name(player.get_name()) == simple_player_name(
                    role.name
                ):
                    return player
        return None

    def update_player_activity(self, server_id: int, member: Member) -> None:
        """Updates the last activity by a Player."""
        player = self.get_member_player_object(member)
        if player:
            if server_id not in self.last_activity:
                self.last_activity[server_id] = {}
            self.last_activity[server_id][player.name] = time.time()

    def save_ctx_parameter(
        self, context_id: int, parameter_key: str, parameter_value: str
    ) -> None:
        """Saves a context parameter to the database."""
        self.ctx_parameters[context_id] = self.ctx_parameters.get(context_id, {})
        keys = parameter_key.split("/")
        data = self.ctx_parameters[context_id]
        for key in keys[:-1]:
            data = data.setdefault(key, {})
        data[keys[-1]] = parameter_value
        self._database.execute_arbitrary_sql(
            "INSERT OR REPLACE INTO ctx_parameters (context_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
            (context_id, parameter_key, parameter_value),
        )

    def delete_ctx_parameter(self, context_id: int, parameter_key: str) -> None:
        """Deletes a context parameter from the database."""
        if context_id not in self.ctx_parameters:
            return
        keys = parameter_key.split("/")
        data = self.ctx_parameters[context_id]
        for key in keys[:-1]:
            if key in data:
                data = data[key]
            else:
                return
        if keys[-1] in data:
            del data[keys[-1]]
        self._database.execute_arbitrary_sql(
            "DELETE FROM ctx_parameters WHERE context_id = ? AND parameter_key = ?",
            (context_id, parameter_key),
        )
