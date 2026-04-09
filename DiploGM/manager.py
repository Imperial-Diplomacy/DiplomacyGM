import logging
import time
import os
from itertools import combinations
from typing import Optional

from discord import Member, User

from DiploGM.models.province import Province
from DiploGM.utils import SingletonMeta
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

SEVERENCE_A_ID = 1440703393369821248
SEVERENCE_B_ID = 1440703645971644648

class Manager(metaclass=SingletonMeta):
    """Manager acts as an intermediary between Bot (the Discord API), Board (the board state), the database."""

    def __init__(self, board_ids: Optional[list[int]]=None):
        self._database = database.get_connection()
        self._boards: dict[int, Board] = self._database.get_boards(board_ids)
        self._spec_requests: dict[int, list[SpecRequest]] = (
            self._database.get_spec_requests()
        )
        self.last_activity: dict[int, dict[str, float]] = {}

        # Stores failed and DP orders here, since we don't want them stored in the board itself
        # As that way we can fetch them for test adjudications without mutating the board state
        # We store the values as strings because we don't want to modify existing Province objects
        # Ideally we should deepcopy the board, but it requires a custom implementation
        self.last_failed_orders: dict[int, set[str]] = {}
        self.last_dp_orders: dict[int, dict[str, tuple[str, str | None, str | None]]] = {}
        # TODO: have multiple for each variant?
        # do it like this so that the parser can cache data between board initializations

    def list_servers(self) -> set[int]:
        """Gets a list of server ids that have games."""
        return set(self._boards.keys())

    def create_game(self, server_id: int, gametype: str = "classic") -> tuple[bool, str]:
        """Creates a new game in the specified server and of the specified variant."""
        if self._boards.get(server_id):
            return False, "A game already exists in this server."
        if not os.path.isdir(parse_variant_path(gametype)):
            return False, f"Game {gametype} does not exist."

        logger.info(f"Creating new game in server {server_id}")
        self._boards[server_id] = get_parser(gametype).parse()
        self._boards[server_id].board_id = server_id
        self._database.save_board(server_id, self._boards[server_id])

        return True, f"{self._boards[server_id].data['name']} game created"

    # Gets adjacent provinces, but with High Seas combined into one for the purpose of finding adjacency issues
    def _get_adjacent_geom(self, province: Province) -> set[Province]:
        return {a for a in province.adjacency_data.adjacent if a.name[-1] not in "23456789"}

    # A recursive function to find loops of provinces with no internal adjacencies
    # Generally, two adjacent provinces should share exactly two adjacencies on either side
    # If there's only one, that typeically means there's a "hole" or the edge of the board
    # We try to trace a chain of such provinces, and if we reach the start, we have a loop
    def _find_province_loop(self,
                            province: Province,
                            destination: Province,
                            visited: list[Province],
                            ignored_provinces: set[Province]) -> Optional[list[Province]]:
        if province == destination:
            return None if len(visited) == 2 else visited # A -> B -> A shouldn't count
        visited.append(province)
        for adj in self._get_adjacent_geom(province):
            # ignored_provinces prevents us finding the same loop multiple times
            if adj in visited[1:] or adj in ignored_provinces:
                continue
            if len(self._get_adjacent_geom(province) & self._get_adjacent_geom(adj)) > 1:
                continue
            loop = self._find_province_loop(adj, destination, visited, ignored_provinces)
            if loop is not None:
                return loop
        visited.pop()
        return None

    # This is a function that goes through a map and attempts to find adjacency issues
    # It will not be fool-proof, but it should detect the majority of potential errors
    # The list of warnings it generates include the following:
    # - High Seas provinces in the same region that have different adjacencies
    #   (e.g. Cape Khoe bordering SAO1 but not SAO2)
    # - Provinces with zero adjacencies
    # - Adjacent provinces that have no common adjacencies
    # - Loops of provinces that have no internal connections (note that this does detect the board edges)
    # - Groups of four provinces that all border each other
    # TODO: Potentially simplify this function's complexity
    def verify_adjacencies(self, variant: str) -> str:
        """Checks for potential adjacency issues in a variant.
        This is not guaranteed to find all issues, but should find the majority of them.
        Returns a string listing any warnings found."""
        if not os.path.isdir(parse_variant_path(variant)):
            return f"Game {variant} does not exist."
        board: Board = get_parser(variant).parse()
        warnings = []
        visited_provinces = set()

        # High Seas
        for province in [p for p in board.provinces if p.name[-1] in "23456789"]:
            try:
                comp_province = board.get_province(province.name[:-1] + "1")
                # Two high seas' adjacencies should differ by only each other
                if (comp_province.adjacency_data.adjacent ^ province.adjacency_data.adjacent
                    != {province, comp_province}):
                    warnings.append(f"Province {province.name} and {comp_province.name} have different adjacencies")
                visited_provinces.add(province)
            except ValueError:
                warnings.append(f"Province {province.name} is named like a high seas province " +
                                f"but {province.name[:-1]}1 was not found")

        for province in board.provinces - visited_provinces:
            if len(province.adjacency_data.adjacent) == 0:
                warnings.append(f"Province {province.name} has no adjacencies")
            visited_adjacent = set()
            for adj in self._get_adjacent_geom(province) - visited_provinces:
                common_adj = self._get_adjacent_geom(province) & self._get_adjacent_geom(adj)
                if len(common_adj) == 0:
                    warnings.append(f"Provinces {province.name} and {adj.name} are adjacent " +
                                    "but have no common adjacencies")
                    continue
                # Finding loops of provinces
                if len(common_adj) == 1:
                    loop = self._find_province_loop(adj, province, [province], visited_provinces)
                    # Comparing names of the first and last provinces in the loop so we only report it once
                    if loop is not None and loop[1].name > loop[-1].name:
                        warnings.append(f"Found a loop of provinces {', '.join(p.name for p in loop)}. " +
                                        "If they surround an impassable province or the board edge, this is expected")

                # Searching for groups of four provinces that all share a border
                for third, fourth in combinations(common_adj - visited_provinces - visited_adjacent, 2):
                    if fourth not in self._get_adjacent_geom(third):
                        continue
                    if min(len(self._get_adjacent_geom(province)),
                           len(self._get_adjacent_geom(adj)),
                           len(self._get_adjacent_geom(third)),
                           len(self._get_adjacent_geom(fourth))) == 3:
                        # Skips provinces that only border the other three, as that's geometrically possible
                        continue
                    warnings.append(f"Provinces {province.name}, {adj.name}, {third.name}, " +
                                    f"and {fourth.name} all border each other")
                visited_adjacent.add(adj)
            visited_provinces.add(province)
        return "\n".join(warnings) if warnings else "No adjacency issues found"

    def generate_layers(self, variant: str) -> tuple[bytes, str]:
        """Generates the SVG layers for a variant and returns them as bytes."""
        if not os.path.isdir(parse_variant_path(variant)):
            raise ValueError(f"Game {variant} does not exist.")
        board: Board = get_parser(variant).parse()
        return get_parser(variant).generate_layers(), f"{board.data['name']}.svg"

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
        # NOTE: Temporary for Meme's Severence Diplomacy Event
        if server_id == SEVERENCE_B_ID:
            server_id = SEVERENCE_A_ID

        # try:
        board = self._boards.get(server_id)
        # except KeyError:
            # board = self._database.get_latest_board(server_id)

        if not board:
            raise RuntimeError("There is no existing game this this server.")
        return board

    def get_board_from_db(self, server_id: int, turn: Turn) -> Board:
        """Loads a fresh board from the database for the given server and turn."""
        cur_board = self.get_board(server_id)
        board = self._database.get_board(
            cur_board.board_id, turn, cur_board.data.get("fish", 0), cur_board.data.get("name"), cur_board.datafile
        )
        if board is None:
            raise RuntimeError(f"There is no {turn} board for this server")
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

    def total_delete(self, server_id: int):
        """Completely wipes all data for a server."""
        self._database.total_delete(self._boards[server_id])
        del self._boards[server_id]

    def list_variants(self) -> str:
        """Lists all available variants."""
        variants = os.listdir("variants")
        loaded_variants = []
        for v in variants:
            if not os.path.isdir(os.path.join("variants", v)):
                continue
            if os.path.isfile(os.path.join("variants", v, "config.json")):
                loaded_variants.append(f"* {v}")
            else:
                version_list = []
                variant_versions = os.listdir(os.path.join("variants", v))
                for vv in variant_versions:
                    if os.path.isdir(os.path.join("variants", v, vv)) \
                       and os.path.isfile(os.path.join("variants", v, vv, "config.json")):
                        version_list.append(vv)
                version_list.sort()
                loaded_variants.append(f"* {v}:\n    " + "\n    ".join(version_list))
        loaded_variants.sort()
        return "\n".join(loaded_variants)

    def draw_map(
        self,
        server_id: int,
        draw_moves: bool = False,
        player_restriction: Player | None = None,
        color_mode: str | None = None,
        turn: Turn | None = None,
        movement_only: bool = False,
        is_severance: bool = False,
    ) -> tuple[bytes, str]:
        """Gets the map for a server.
        draw_moves: whether to draw the moves on the map
        player_restriction: only draws moves that the player knows about
        color_mode: whether to use a special color mode (e.g. dark, pink, etc.)
        turn: whether to draw the map for a previous turn (defaults to current turn)
        movement_only: whether to only draw succcessful moves (used mainly for Carnage)"""
        cur_board = self.get_board(server_id)
        if turn is None:
            board = cur_board
        else:
            board = self._database.get_board(
                cur_board.board_id,
                turn,
                cur_board.data.get("fish", 0),
                cur_board.data.get("name"),
                cur_board.datafile,
            )
            if board is None:
                raise RuntimeError(
                    f"There is no {turn} board for this server"
                )
            if (
                board.turn.year < cur_board.turn.year
                or (board.turn.year == cur_board.turn.year
                    and board.turn.phase.value < cur_board.turn.phase.value)
            ):
                if is_severance:
                    board = cur_board
                else:
                    player_restriction = None
        svg, file_name = self.draw_map_for_board(
            board,
            player_restriction=player_restriction,
            draw_moves=draw_moves,
            color_mode=color_mode,
            movement_only=movement_only,
        )
        return svg, file_name

    def draw_map_for_board(
        self,
        board: Board,
        player_restriction: Player | None = None,
        draw_moves: bool = False,
        color_mode: str | None = None,
        movement_only: bool = False,
    ) -> tuple[bytes, str]:
        """Gets the current map for a board."""
        start = time.time()

        if draw_moves:
            svg, file_name = Mapper(board, color_mode=color_mode).draw_moves_map(
                board.turn,
                player_restriction=player_restriction,
                movement_only=movement_only,
            )
        else:
            svg, file_name = Mapper(board, color_mode=color_mode).draw_current_map()

        elapsed = time.time() - start
        logger.info(f"manager.draw_map_for_board took {elapsed}s")
        return svg, file_name

    def adjudicate(self, server_id: int, test: bool = False) -> Board:
        """Adjudicates the game for a given board, and saves the result if it's not a test adjudication."""
        start = time.time()

        board = self.get_board(server_id)
        old_board = self._database.get_board(
            server_id, board.turn, board.data.get("fish", 0), board.data.get("name"), board.datafile
        )
        assert old_board is not None
        adjudicator = make_adjudicator(old_board)
        adjudicator.save_orders = not test
        new_board = adjudicator.run()
        self.last_failed_orders[server_id] = {
            order.current_province.name
            for order in getattr(adjudicator, 'orders', [])
            if order.resolution == Resolution.FAILS
        }
        self.last_dp_orders[server_id] = getattr(adjudicator, 'dp_order_strings', {})
        new_board.turn = new_board.turn.get_next_turn()
        new_board.run_variant_scripts()
        logger.info("Adjudicator ran successfully")
        if not test:
            self._boards[new_board.board_id] = new_board
            self._database.save_board(new_board.board_id, new_board)

        elapsed = time.time() - start
        logger.info(f"manager.adjudicate.{server_id}.{elapsed}s")
        return new_board

    def draw_fow_current_map(
        self,
        server_id: int,
        player_restriction: Player | None,
        color_mode: str | None = None,
    ) -> tuple[bytes, str]:
        """Draws the current map for a board with fog of war.
        Should probably be updated."""
        start = time.time()

        svg, file_name = Mapper(
            self._boards[server_id], player_restriction, color_mode
        ).draw_current_map()

        elapsed = time.time() - start
        logger.info(f"manager.draw_fow_current_map.{server_id}.{elapsed}s")
        return svg, file_name

    def draw_fow_players_moves_map(
        self,
        server_id: int,
        player_restriction: Player | None,
        color_mode: str | None = None,
    ) -> tuple[bytes, str]:
        """Draws the moves map for a board with fog of war for a specific player.
        Should probably be updated."""
        start = time.time()

        if player_restriction:
            svg, file_name = Mapper(
                self._boards[server_id], player_restriction, color_mode=color_mode
            ).draw_moves_map(self._boards[server_id].turn, player_restriction)
        else:
            svg, file_name = Mapper(self._boards[server_id], None).draw_moves_map(
                self._boards[server_id].turn, None
            )

        elapsed = time.time() - start
        logger.info(f"manager.draw_fow_players_moves_map.{server_id}.{elapsed}s")
        return svg, file_name

    def draw_fow_moves_map(
        self, server_id: int, player_restriction: Player | None
    ) -> tuple[bytes, str]:
        """Draws the moves map for a board with fog of war.
        Should probably be updated."""
        start = time.time()

        svg, file_name = Mapper(
            self._boards[server_id], player_restriction
        ).draw_moves_map(self._boards[server_id].turn, None)

        elapsed = time.time() - start
        logger.info(f"manager.draw_fow_moves_map.{server_id}.{elapsed}s")
        return svg, file_name

    def draw_fow_gui_map(
        self,
        server_id: int,
        player_restriction: Player | None = None,
        color_mode: str | None = None,
    ) -> tuple[bytes, str]:
        """Draws the GUI map for a board with fog of war.
        Should probably be updated."""
        start = time.time()

        svg, file_name = Mapper(
            self._boards[server_id], player_restriction, color_mode=color_mode
        ).draw_gui_map(self._boards[server_id].turn, None)

        elapsed = time.time() - start
        logger.info(f"manager.draw_fow_moves_map.{server_id}.{elapsed}s")
        return svg, file_name

    def draw_gui_map(
        self,
        server_id: int,
        player_restriction: Player | None = None,
        color_mode: str | None = None,
    ) -> tuple[bytes, str]:
        """Draws an GUI map for a board."""
        start = time.time()

        svg, file_name = Mapper(
            self._boards[server_id], color_mode=color_mode
        ).draw_gui_map(self._boards[server_id].turn, player_restriction)

        elapsed = time.time() - start
        logger.info(f"manager.draw_moves_map.{server_id}.{elapsed}s")
        return svg, file_name

    def rollback(self, server_id: int) -> tuple[str, bytes, str]:
        """Rolls back the board to the previous turn."""
        logger.info(f"Rolling back in server {server_id}")
        board = self.get_board(server_id)
        last_turn = board.turn.get_previous_turn()

        old_board = self._database.get_board(
            board.board_id,
            last_turn,
            board.data.get("fish", 0),
            board.data.get("name"),
            board.datafile,
            clear_status=True,
        )
        if old_board is None:
            raise ValueError(
                f"There is no {last_turn} board for this server"
            )

        self._database.delete_board(board)
        self._boards[old_board.board_id] = old_board
        mapper = Mapper(old_board)

        message = f"Rolled back to {old_board.turn.get_indexed_name()}"
        file, file_name = mapper.draw_current_map()
        return message, file, file_name

    def get_previous_board(self, server_id: int) -> Board | None:
        """Gets the previous board for a server. Returns None if it doesn't exist."""
        board = self.get_board(server_id)
        last_turn = board.turn.get_previous_turn()
        old_board = self._database.get_board(
            board.board_id,
            last_turn,
            board.data.get("fish", 0),
            board.data.get("name"),
            board.datafile,
        )
        return old_board

    def reload(self, server_id: int) -> tuple[str, bytes, str]:
        """Reloads the board for a server."""
        logger.info(f"Reloading server {server_id}")
        board = self.get_board(server_id)

        loaded_board = self._database.get_board(
            server_id, board.turn, board.data.get("fish", 0), board.data.get("name"), board.datafile
        )
        if loaded_board is None:
            raise ValueError(
                f"There is no {board.turn} board for this server"
            )

        self._boards[board.board_id] = loaded_board
        mapper = Mapper(loaded_board)

        message = f"Reloaded board for phase {loaded_board.turn.get_indexed_name()}"
        file, file_name = mapper.draw_current_map()
        return message, file, file_name

    def reload_variant(self, variant: str) -> str:
        """Reloads a variant, including adjacencies and all boards."""
        if not os.path.isdir(parse_variant_path(variant)):
            return f"Variant {variant} does not exist."

        # Remove adjacency cache to force a reload
        if os.path.isfile(f"assets/{variant}_adjacencies.txt"):
            os.remove(f"assets/{variant}_adjacencies.txt")

        get_parser(variant, force_refresh=True).parse()
        for server_id, board in self._boards.items():
            if board.datafile == variant:
                logger.info(f"Reloading board for server {server_id}")
                loaded_board = self._database.get_board(
                    server_id, board.turn, board.data.get("fish", 0), board.data.get("name"), board.datafile
                )
                if loaded_board is None:
                    logger.warning(f"There is no {board.turn} board for this server")
                    continue
                self._boards[board.board_id] = loaded_board
        return f"Reloaded variant {variant}"

    def get_member_player_object(self, member: Member | User) -> Player | None:
        """Gets the player object associated with a Discord member, if it exists."""
        if isinstance(member, User):
            return None
        try:
            players = self.get_board(member.guild.id).players
        except RuntimeError:
            return None
        for role in member.roles:
            for player in players:
                if (simple_player_name(player.name) == simple_player_name(role.name)
                    or simple_player_name(player.get_name()) == simple_player_name(role.name)):
                    return player
        return None

    def update_player_activity(self, server_id: int, member: Member) -> None:
        """Updates the last activity by a Player."""
        player = self.get_member_player_object(member)
        if player:
            if server_id not in self.last_activity:
                self.last_activity[server_id] = {}
            self.last_activity[server_id][player.name] = time.time()
