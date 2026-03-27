"""The board for a given turn, containing all the game state information."""
from __future__ import annotations
import re
import logging
import time
from typing import Dict, Optional, TYPE_CHECKING

from discord import Thread, TextChannel

from DiploGM.config import player_channel_suffix, is_player_category
from DiploGM.models.order import Move
from DiploGM.models.unit import Unit, UnitType
from DiploGM.utils.sanitise import sanitise_name
from DiploGM.utils.sanitise import simple_player_name

if TYPE_CHECKING:
    from discord.abc import Messageable
    from DiploGM.models.turn import Turn
    from DiploGM.models.player import Player
    from DiploGM.models.province import Province, ProvinceType
    from DiploGM.models.order import UnitOrder


logger = logging.getLogger(__name__)

class Board:
    """The board for a given turn, containing all the game state information."""
    def __init__(
        self,
        players: set[Player],
        provinces: set[Province],
        units: set[Unit],
        turn: Turn,
        data: dict,
        datafile: str,
        fow: bool = False,
        year_offset: int = 1642
    ):
        self.players: set[Player] = players
        self.provinces: set[Province] = provinces
        self.units: set[Unit] = units
        self.turn: Turn = turn
        self.year_offset = year_offset
        self.board_id = 0
        self.fish = 0
        self.fish_pop = {
            "fish_pop": float(700),
            "time": time.time()
        }
        self.orders_enabled: bool = True
        self.data: dict = data
        self.datafile = datafile
        self.name: str | None = None
        self.fow = fow

        # store as lower case for user input purposes
        self.name_to_player: Dict[str, Player] = {player.name.lower(): player for player in self.players}
        # remove periods and apostrophes
        cleaned_names: Dict[str, Player] = {sanitise_name(player.name.lower()): player for player in self.players}
        simple_names: Dict[str, Player] = {simple_player_name(player.name): player for player in self.players}
        self.name_to_player = self.name_to_player | cleaned_names | simple_names
        self.name_to_province: Dict[str, Province] = {}
        self.name_to_coast: Dict[str, tuple[Province, str | None]] = {}
        for location in self.provinces:
            self.name_to_province[location.name.lower()] = location
            for coast in location.get_multiple_coasts():
                self.name_to_coast[location.get_name(coast)] = (location, coast)

        for player in self.players:
            player.board = self

    def add_new_player(self, name: str, color: str):
        """Adds a new player to the board with a given color."""
        from DiploGM.models.player import Player
        new_player = Player(name, color, set(), set())
        new_player.board = self
        self.players.add(new_player)
        self.name_to_player[name.lower()] = new_player
        self.name_to_player[sanitise_name(name.lower())] = new_player
        self.name_to_player[simple_player_name(name)] = new_player
        if name not in self.data["players"]:
            self.data["players"][name] = {"color": color}
        if "iscc" not in self.data["players"][name]:
            self.data["players"][name]["iscc"] = 1
        if "vscc" not in self.data["players"][name]:
            self.data["players"][name]["vscc"] = self.data["victory_count"]

    def update_players(self):
        """Goes through the datafile and adds any missing players/nicknames."""
        for player_name, player_data in self.data["players"].items():
            if player_name.lower() not in self.name_to_player:
                self.add_new_player(player_name, player_data["color"])
        for player in self.players:
            if (nickname := self.data["players"][player.name].get("nickname")):
                self.add_nickname(player, nickname)

    def get_player(self, name: str) -> Optional[Player]:
        """Gets a player by their name or nickname."""
        name = sanitise_name(name)
        if name.lower() == "none":
            return None
        if name.lower() not in self.name_to_player:
            raise ValueError(f"Player {name} not found")
        return self.name_to_player.get(name.lower())

    def get_players(self, active_only: bool = True) -> set[Player]:
        """Gets all players, potentially including inactive ones."""
        if active_only:
            return {player for player in self.players if player.is_active}
        return self.players

    def add_nickname(self, player: Player, nickname: str):
        """Adds or updates a player's nickname."""
        cleaned_name = sanitise_name(nickname.lower())
        simple_name = simple_player_name(nickname)
        if (nickname.lower() in self.name_to_player
            or cleaned_name in self.name_to_player
            or simple_name in self.name_to_player):
            raise ValueError(f"A player with {nickname} already exists")

        if (old_nick := self.data["players"][player.name].get("nickname")):
            self.name_to_player.pop(old_nick.lower(), None)
            self.name_to_player.pop(sanitise_name(old_nick.lower()), None)
            self.name_to_player.pop(simple_player_name(old_nick), None)

        self.data["players"][player.name]["nickname"] = nickname
        self.name_to_player[nickname.lower()] = player
        self.name_to_player[cleaned_name] = player
        self.name_to_player[simple_name] = player

    def get_score(self, player: Player) -> float:
        """Gets the player's score as a percentage towards victory, depending on the victory conditions."""
        if self.data["victory_conditions"] == "classic":
            return len(player.centers) / int(self.data["victory_count"])
        if self.data["victory_conditions"] == "vscc":
            if (centers:= len(player.centers)) > (iscc := int(self.data["players"][player.name]["iscc"])):
                return (centers - iscc) / (int(self.data["players"][player.name]["vscc"]) - iscc)
            return (centers / iscc) - 1
        raise ValueError("Unknown scoring system found")

    def get_players_sorted_by_score(self) -> list[Player]:
        """Gets a list of players sorted by their score."""
        return sorted(self.get_players(),
            key=lambda sort_player: (self.data["players"][sort_player.name].get("hidden", "false"),
                                    -self.get_score(sort_player),
                                    sort_player.get_name().lower()))

    def get_players_sorted_by_points(self) -> list[Player]:
        """Gets a list of players sorted by their points."""
        return sorted(self.get_players(), key=lambda sort_player: (-sort_player.points, -len(sort_player.centers), sort_player.get_name().lower()))

    def get_province(self, name: str) -> Province:
        """Gets a province by its name, ignoring coasts."""
        province, _ = self.get_province_and_coast(name)
        return province

    def get_province_and_coast(self, name: str) -> tuple[Province, str | None]:
        """Given a string, attempts to find a matching province and coast.
        If an exact match is not found, will see if any provinces being with the string."""
        # FIXME: This should not be raising exceptions many places already assume it returns None on failure.
        # TODO: (BETA) we build this everywhere, let's just have one live on the Board on init
        # we ignore capitalization because this is primarily used for user input
        # People input apostrophes that don't match what the province names are
        name = re.sub(r"[‘’`´′‛]", "'", name)
        name = name.lower()

        # Legacy back-compatibility for coasts
        if name.endswith(" coast"):
            name = name[:-6]

        if "abbreviations" in self.data and name in self.data["abbreviations"]:
            name = self.data["abbreviations"][name].lower()

        if name in self.name_to_coast:
            return self.name_to_coast[name]
        elif name in self.name_to_province:
            return self.name_to_province[name], None

        # failed to match, try to get possible locations
        potential_locations = self._get_possible_locations(name)
        if len(potential_locations) > 5:
            raise ValueError(f"The location {name} is ambiguous. Please type out the full name.")
        elif len(potential_locations) > 1:
            raise ValueError(
                f'The location {name} is ambiguous. Possible matches: ' +
                f'{", ".join([loc[0].name for loc in potential_locations])}.'
            )
        elif len(potential_locations) == 0:
            raise ValueError(f"The location {name} does not match any known provinces.")
        else:
            return potential_locations[0]

    def get_visible_provinces(self, player: Player) -> set[Province]:
        """Gets a set of provinces that a player can see in Fog of War games."""
        visible: set[Province] = set()
        for province in self.provinces:
            for unit in player.units:
                if (unit.unit_type == UnitType.ARMY
                    and province in unit.province.adjacency_data.adjacent
                    and province.type != ProvinceType.SEA):
                    visible.add(province)

                if (unit.unit_type == UnitType.FLEET
                    and unit.province.is_coastally_adjacent((province, None), unit.coast)):
                    visible.add(province)

        for unit in player.units:
            visible.add(unit.province)

        for province in player.centers:
            if province.core_data.core == player:
                visible.update(province.adjacency_data.adjacent)
            visible.add(province)

        return visible

    def _get_possible_locations(self, name: str) -> list[tuple[Province, str | None]]:
        pattern = r"^{}.*$".format(re.escape(name.strip()).replace("\\ ", r"\S*\s*"))
        matches = []
        for province in self.provinces:
            if re.search(pattern, province.name.lower()):
                matches.append((province, None))
            else:
                matches += [(province, coast) for coast in province.get_multiple_coasts()
                            if re.search(pattern, province.get_name(coast).lower())]
        return matches

    def change_owner(self, province: Province, player: Player | None):
        """Changes the owner of a province, including supply center, if applicable."""
        if province.has_supply_center:
            if province.owner:
                province.owner.centers.remove(province)
            if player:
                player.centers.add(province)
        province.owner = player

    def create_unit(
        self,
        unit_type: UnitType,
        player: Player | None,
        province: Province,
        coast: str | None,
        retreat_options: set[tuple[Province, str | None]] | None,
    ) -> Unit:
        """Creates a new unit on the board."""
        if (unit_type == UnitType.FLEET
            and province.get_multiple_coasts()
            and coast not in province.get_multiple_coasts()):
            raise RuntimeError(f"Cannot create unit. Province '{province.name}' requires a valid coast.")
        if not province.get_multiple_coasts():
            coast = None
        unit = Unit(unit_type, player, province, coast)
        if retreat_options is not None:
            if province.dislodged_unit:
                raise RuntimeError(f"{province.name} already has a dislodged unit")
            unit.retreat_options = retreat_options
            province.dislodged_unit = unit
        else:
            if province.unit:
                raise RuntimeError(f"{province.name} already has a unit")
            province.unit = unit
        if player is not None:
            player.units.add(unit)
        self.units.add(unit)
        return unit

    def move_unit(self, unit: Unit, new_province: Province, new_coast: str | None = None) -> Unit:
        """Moves an existing unit to a new province"""
        if new_province.unit:
            raise RuntimeError(f"{new_province.name} already has a unit")
        new_province.unit = unit
        unit.province.unit = None
        unit.province = new_province
        unit.coast = new_coast
        return unit

    def delete_unit(self, province: Province) -> Unit | None:
        """Deletes a unit from the board."""
        unit = province.unit
        if not unit:
            return None
        province.unit = None
        if unit.player is not None:
            unit.player.units.remove(unit)
        self.units.remove(unit)
        return unit

    def delete_dislodged_unit(self, province: Province) -> Unit | None:
        """Deletes a dislodged unit from the board."""
        unit = province.dislodged_unit
        if not unit:
            return None
        province.dislodged_unit = None
        if unit.player is not None:
            unit.player.units.remove(unit)
        self.units.remove(unit)
        return unit

    def delete_all_units(self) -> None:
        """Deletes all units from the board."""
        for unit in self.units:
            unit.province.unit = None

        for player in self.players:
            player.units = set()

        self.units = set()

    def delete_dislodged_units(self) -> None:
        """Deletes all dislodged units from the board."""
        dislodged_units = set()
        for unit in self.units:
            if unit.retreat_options:
                dislodged_units.add(unit)

        for unit in dislodged_units:
            unit.province.dislodged_unit = None
            if unit.player is not None:
                unit.player.units.remove(unit)
            self.units.remove(unit)


    def get_winning_dp_order(self, unit: Unit) -> UnitOrder | None:
        # We find which orders got the highest bid, and assign that to the unit.
        # If a player is ordering an attack or support against that unit, they lose their bid.
        # If there is a tie, then the unit holds.
        if not unit.dp_allocations:
            return
        dp_allocations: dict[str, int] = {}
        str_to_order: dict[str, UnitOrder] = {}
        for player_name, allocation in unit.dp_allocations.items():
            player = self.get_player(player_name)
            if player is None:
                continue
            order = allocation.order
            # First, let's check to see if the player isn't attacking the unit
            destinations = [u.order.destination for u in player.units if u.order is not None]
            if unit.province in destinations:
                continue

            multiplier = 2 if self.has_affiliation(player, unit.player) else 1
            if str(order) in dp_allocations:
                dp_allocations[str(order)] += allocation.points * multiplier
            else:
                str_to_order[str(order)] = order
                dp_allocations[str(order)] = allocation.points * multiplier
        # Now let's see which order got the highest bid
        has_tie = False
        max_points = 0
        best_order_str = ""
        for order_str, points in dp_allocations.items():
            if points > max_points:
                max_points = points
                best_order_str = order_str
                has_tie = False
            elif points == max_points:
                has_tie = True
        if has_tie:
            return None
        winning_order = str_to_order[best_order_str]
        if isinstance(winning_order, Move):
            winning_order.is_sortie = True
        return winning_order

    def has_affiliation(self, player1: Player, player2: Player | None) -> bool:
        """Checks to see if two powers are affilited, used for determining DP multipliers."""
        if player2 is None:
            return False
        affiliations = self.data["players"][player1.name].get("affiliates", [])
        return player2.name in affiliations

    def get_year_str(self) -> str:
        """Gets the string representation of the current year, accounting for BC/AD."""
        if self.turn.year <= 0:
            return f"{str(1-self.turn.year)} BC"
        return str(self.turn.year)

    def is_chaos(self) -> bool:
        """Checks to see if this is a Chaos game."""
        return self.data["players"] == "chaos"

    def get_player_by_channel(
            self,
            channel: Messageable,
            ignore_category=False,
    ) -> Player | None:
        """Given a Discord channel, tries to find a matching Player."""
        # thread -> main channel
        if isinstance(channel, Thread):
            assert isinstance(channel.parent, TextChannel)
            channel = channel.parent
        assert isinstance(channel, TextChannel)

        name = channel.name
        if (not ignore_category) and not is_player_category(channel.category):
            return None

        if self.is_chaos() and name.endswith("-void"):
            name = name[:-5]
        else:
            if not name.endswith(player_channel_suffix):
                return None

            name = name[: -(len(player_channel_suffix))]

        try:
            return self.get_player(name)
        except ValueError:
            return None
