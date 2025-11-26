from __future__ import annotations
import re
import logging
import time
from typing import Dict, Optional, TYPE_CHECKING

from discord import Thread
from discord.ext import commands

from DiploGM.config import player_channel_suffix, is_player_category
from DiploGM.models.unit import Unit, UnitType

if TYPE_CHECKING:
    from DiploGM.models.turn import Turn
    from DiploGM.models.player import Player
    from DiploGM.models.province import Province, ProvinceType


logger = logging.getLogger(__name__)

class Board:
    def __init__(
        self, players: set[Player], provinces: set[Province], units: set[Unit], turn: Turn, data, datafile: str, fow: bool, year_offset: int = 1642
    ):
        from DiploGM.utils.sanitise import sanitise_name
        from DiploGM.utils import simple_player_name

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
        self.name = None
        self.fow = fow

        # store as lower case for user input purposes
        self.name_to_player: Dict[str, Player] = {player.name.lower(): player for player in self.players}
        # remove periods and apostrophes
        self.cleaned_name_to_player: Dict[str, Player] = {sanitise_name(player.name.lower()): player for player in self.players}
        self.simple_player_name_to_player: Dict[str, Player] = {simple_player_name(player.name): player for player in self.players}
        self.name_to_province: Dict[str, Province] = {}
        self.name_to_coast: Dict[str, tuple[Province, str | None]] = {}
        for location in self.provinces:
            self.name_to_province[location.name.lower()] = location
            for coast in location.get_multiple_coasts():
                self.name_to_coast[location.get_name(coast)] = (location, coast)

        for player in self.players:
            player.board = self

    def get_player(self, name: str) -> Optional[Player]:
        if name.lower() == "none":
            return None
        if name.lower() not in self.name_to_player:
            raise ValueError(f"Player {name} not found")
        return self.name_to_player.get(name.lower())

    def get_cleaned_player(self, name: str) -> Optional[Player]:
        if name.lower() == "none":
            return None
        if name.lower() not in self.cleaned_name_to_player:
            raise ValueError(f"Player {name} not found")
        return self.cleaned_name_to_player.get(sanitise_name(name.lower()))

    def get_player_sanitised(self, name:str) -> Optional[Player]:
        name = simple_player_name(name)
        if name == "none":
            return None
        if name not in self.simple_player_name_to_player:
            raise ValueError(f"Player {name} not found")
        return self.simple_player_name_to_player.get(simple_player_name(name))


    # TODO: break ties in a fixed manner
    def get_players_sorted_by_score(self) -> list[Player]:
        return sorted(self.players, key=lambda sort_player: (-sort_player.score(), sort_player.name.lower()))

    def get_players_sorted_by_points(self) -> list[Player]:
        return sorted(self.players, key=lambda sort_player: (-sort_player.points, -len(sort_player.centers), sort_player.name.lower()))

    # TODO: this can be made faster if necessary
    def get_province(self, name: str) -> Province:
        province, _ = self.get_province_and_coast(name)
        return province

    def get_province_and_coast(self, name: str) -> tuple[Province, str | None]:
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
        potential_locations = self.get_possible_locations(name)
        if len(potential_locations) > 5:
            raise Exception(f"The location {name} is ambiguous. Please type out the full name.")
        elif len(potential_locations) > 1:
            raise Exception(
                f'The location {name} is ambiguous. Possible matches: {", ".join([loc[0].name for loc in potential_locations])}.'
            )
        elif len(potential_locations) == 0:
            raise Exception(f"The location {name} does not match any known provinces.")
        else:
            return potential_locations[0]

    def get_visible_provinces(self, player: Player) -> set[Province]:
        visible: set[Province] = set()
        for province in self.provinces:
            for unit in player.units:
                if unit.unit_type == UnitType.ARMY:
                    if province in unit.province.adjacent and province.type != ProvinceType.SEA:
                        visible.add(province)
                if unit.unit_type == UnitType.FLEET:
                    if unit.province.is_coastally_adjacent((province, None), unit.coast):
                        visible.add(province)

        for unit in player.units:
            visible.add(unit.province)

        for province in player.centers:
            if province.core == player:
                visible.update(province.adjacent)
            visible.add(province)

        return visible

    def get_possible_locations(self, name: str) -> list[tuple[Province, str | None]]:
        pattern = r"^{}.*$".format(re.escape(name.strip()).replace("\\ ", r"\S*\s*"))
        matches = []
        for province in self.provinces:
            if re.search(pattern, province.name.lower()):
                matches.append((province, None))
            else:
                matches += [(province, coast) for coast in province.get_multiple_coasts()
                            if re.search(pattern, province.get_name(coast).lower())]
        return matches

    def get_build_counts(self) -> list[tuple[str, int]]:
        build_counts = []
        for player in self.players:
            build_counts.append((player.name, len(player.centers) - len(player.units)))
        build_counts = sorted(build_counts, key=lambda counts: counts[1])
        return build_counts

    def change_owner(self, province: Province, player: Player):
        if province.has_supply_center:
            if province.owner:
                province.owner.centers.remove(province)
            if player:
                player.centers.add(province)
        province.owner = player

    def create_unit(
        self,
        unit_type: UnitType,
        player: Player,
        province: Province,
        coast: str | None,
        retreat_options: set[Province] | None,
    ) -> Unit:
        unit = Unit(unit_type, player, province, coast, retreat_options)
        if retreat_options is not None:
            if province.dislodged_unit:
                raise RuntimeError(f"{province.name} already has a dislodged unit")
            province.dislodged_unit = unit
        else:
            if province.unit:
                raise RuntimeError(f"{province.name} already has a unit")
            province.unit = unit
        player.units.add(unit)
        self.units.add(unit)
        return unit

    def move_unit(self, unit: Unit, new_province: Province, new_coast: str | None = None) -> Unit:
        if new_province.unit:
            raise RuntimeError(f"{new_province.name} already has a unit")
        new_province.unit = unit
        unit.province.unit = None
        unit.province = new_province
        unit.coast = new_coast
        return unit

    def delete_unit(self, province: Province) -> Unit:
        unit = province.unit
        province.unit = None
        unit.player.units.remove(unit)
        self.units.remove(unit)
        return unit

    def delete_dislodged_unit(self, province: Province) -> Unit:
        unit = province.dislodged_unit
        province.dislodged_unit = None
        unit.player.units.remove(unit)
        self.units.remove(unit)
        return unit

    def delete_all_units(self) -> None:
        for unit in self.units:
            unit.province.unit = None

        for player in self.players:
            player.units = set()

        self.units = set()

    def delete_dislodged_units(self) -> None:
        dislodged_units = set()
        for unit in self.units:
            if unit.retreat_options:
                dislodged_units.add(unit)

        for unit in dislodged_units:
            unit.province.dislodged_unit = None
            unit.player.units.remove(unit)
            self.units.remove(unit)

    def clear_failed_orders(self) -> None:
        for unit in self.units:
            unit.province.unit = None

        for player in self.players:
            player.units = set()

        self.units = set()

    def get_year_int(self) -> int:
        return self.turn.year

    @staticmethod
    def convert_year_int_to_str(year: int) -> str:
        # No 0 AD / BC
        if year <= 0:
            return f"{str(1-year)} BC"
        else:
            return str(year)

    def get_year_str(self) -> str:
        if self.turn.year <= 0:
            return f"{str(1-self.turn.year)} BC"
        else:
            return str(self.turn.year)
        
    def is_chaos(self) -> bool:
        return self.data["players"] == "chaos"

    def get_player_by_channel(
            self,
            channel: commands.Context.channel,
            ignore_category=False,
    ) -> Player | None:
        # thread -> main channel
        if isinstance(channel, Thread):
            channel = channel.parent

        name = channel.name
        if (not ignore_category) and not is_player_category(channel.category.name):
            return None

        if self.is_chaos() and name.endswith("-void"):
            name = name[:-5]
        else:
            if not name.endswith(player_channel_suffix):
                return None

            name = name[: -(len(player_channel_suffix))]

        try:
            return self.get_cleaned_player(name)
        except ValueError:
            pass
        try:
            return self.get_cleaned_player(simple_player_name(name))
        except ValueError:
            return None