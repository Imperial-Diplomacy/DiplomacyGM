"""The board for a given turn, containing all the game state information."""
from __future__ import annotations
import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

from rapidfuzz.distance import DamerauLevenshtein

from DiploGM.models.order import NMR, Move, Hold, Support, ConvoyTransport, Core, Transform, RetreatMove, RetreatDisband
from DiploGM.models.province import ProvinceType
from DiploGM.models.unit import Unit, UnitType, DPAllocation
from DiploGM.models.turn import Turn
from DiploGM.utils.sanitise import parse_variant_path, sanitise_name, simple_player_name

if TYPE_CHECKING:
    from DiploGM.models.player import Player
    from DiploGM.models.province import Province
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
        datafile: str
    ):
        self.players: set[Player] = players
        self.provinces: set[Province] = provinces
        self.units: set[Unit] = units
        self.turn: Turn = turn
        self.board_id = 0
        self.fish_pop = {
            "fish_pop": float(700),
            "time": time.time()
        }
        self.orders_enabled: bool = True
        self.data: dict = data
        self.data.setdefault("fish", 0)
        self.custom_data: dict = {}
        self.datafile = datafile

        # store as lower case for user input purposes
        self.name_to_player: Dict[str, Player] = {player.name.lower(): player for player in self.players}
        self.name_to_player |= {sanitise_name(player.name.lower()): player for player in self.players}
        self.name_to_player |= {simple_player_name(player.name): player for player in self.players}
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
            self.set_data(["players", name], {"color": color})
        if "iscc" not in self.data["players"][name]:
            self.set_data(["players", name, "iscc"], 1)
        if "vscc" not in self.data["players"][name]:
            self.set_data(["players", name, "vscc"], self.data["victory_count"])

    def run_variant_scripts(self):
        """Runs the variant's scripts.py if it exists, in a sandboxed environment."""
        variant_path = parse_variant_path(self.datafile)
        scripts_path = os.path.join(variant_path, "scripts.py")
        if os.path.isfile(scripts_path):
            with open(scripts_path, "r", encoding="utf-8") as f:
                script_code = f.read()
            allowed_globals = {"__builtins__": __builtins__, "board": self}
            exec(compile(script_code, scripts_path, "exec"), allowed_globals)

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

    def is_player_hidden(self, player: Player) -> bool:
        """Checks to see if a player is hidden in the datafile."""
        return self.data["players"][player.name].get("hidden", "false") == "true"

    def add_nickname(self, player: Player, nickname: str) -> bool:
        """Adds or updates a player's nickname.
        Returns True if the nickname was removed, False if it was added/updated."""
        cleaned_name = sanitise_name(nickname.lower())
        simple_name = simple_player_name(nickname)

        if player.name.lower() in [nickname.lower(), cleaned_name, simple_name]:
            if (old_nick := self.data["players"][player.name].get("nickname")):
                self.name_to_player.pop(old_nick.lower(), None)
                self.name_to_player.pop(sanitise_name(old_nick.lower()), None)
                self.name_to_player.pop(simple_player_name(old_nick), None)
            self.data["players"][player.name].pop("nickname", None)
            self.custom_data.get("players", {}).get(player.name, {}).pop("nickname", None)
            return True

        if (nickname.lower() in self.name_to_player
            or cleaned_name in self.name_to_player
            or simple_name in self.name_to_player):
            raise ValueError(f"A player with {nickname} already exists")

        if (old_nick := self.data["players"][player.name].get("nickname")):
            self.name_to_player.pop(old_nick.lower(), None)
            self.name_to_player.pop(sanitise_name(old_nick.lower()), None)
            self.name_to_player.pop(simple_player_name(old_nick), None)

        self.set_data(["players", player.name, "nickname"], nickname)
        self.name_to_player[nickname.lower()] = player
        self.name_to_player[cleaned_name] = player
        self.name_to_player[simple_name] = player
        return False

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
            key=lambda sort_player: (self.is_player_hidden(sort_player),
                                    -self.get_score(sort_player),
                                    sort_player.get_name().lower()))

    def get_players_sorted_by_points(self) -> list[Player]:
        """Gets a list of players sorted by their points."""
        return sorted(self.get_players(),
            key=lambda sort_player: (-sort_player.points,
                                    -len(sort_player.centers),
                                    sort_player.get_name().lower()))

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
        if name in self.name_to_province:
            return self.name_to_province[name], None

        # failed to match, try to get possible locations
        potential_locations = self._get_possible_locations(name)
        if len(potential_locations) > 5:
            raise ValueError(f"The location {name} is ambiguous. Please type out the full name.")
        if len(potential_locations) > 1:
            raise ValueError(
                f'The location {name} is ambiguous. Possible matches: ' +
                f'{", ".join([loc[0].name for loc in potential_locations])}.'
            )
        elif len(potential_locations) == 0:
            suggestion = self._suggest_province(name)
            message = f"The location {name} does not match any known provinces."
            if suggestion:
                message += f" {suggestion}"
            raise ValueError(message)
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

    def _suggest_province(self, name: str) -> str | None:
        """Given a failed province lookup, calculate similarity to all known provinces and coasts and provide a suggestion, or None if no candidate is close enough to be worth suggesting."""
        MAX_DISTANCE = 0.45 # If distance is too high (i.e. very different), no suggestion provided
        CONFIDENT_GAP = 0.20 # Defines how much better a suggestion has to be than any other to confidently conclude it's the intended province

        # Build (normalized_distance, display_name) for every candidate.
        candidates: list[tuple[float, str]] = []
        for key, province in self.name_to_province.items():
            dist = DamerauLevenshtein.normalized_distance(name, key)
            if dist <= MAX_DISTANCE: # Prefilter this out to make sorting faster
                candidates.append((dist, province.name))

        for key, (province, coast) in self.name_to_coast.items():
            dist = DamerauLevenshtein.normalized_distance(name, key.lower())
            if dist <= MAX_DISTANCE: # Prefilter this out to make sorting faster
                candidates.append((dist, province.get_name(coast)))

        # No candidates similar enough
        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0]) # Sort by distance
        best_dist, best_name = candidates[0]
        second_dist = candidates[1][0] if len(candidates) > 1 else float("inf")

        # One suggestion is clearly superior so we confidently suggest it
        if (second_dist - best_dist) >= CONFIDENT_GAP:
            return f"Did you mean '{best_name}'?"

        close = [display for dist, display in candidates if dist <= best_dist + CONFIDENT_GAP][:3]
        return f"Did you mean one of: {', '.join(close)}?"

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

    def delete_unit(self, province: Province, is_dislodged: bool = False) -> Unit | None:
        """Deletes a unit from the board."""
        unit = province.dislodged_unit if is_dislodged else province.unit
        if not unit:
            return None
        if is_dislodged:
            province.dislodged_unit = None
        else:
            province.unit = None
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
        """We find which orders got the highest bid, and assign that to the unit.
        If a player is ordering an attack or support against that unit, they lose their bid.
        If there is a tie, then the unit holds."""
        if not unit.dp_allocations:
            return None
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
        max_points = 0
        winning_order = None
        for order_str, points in dp_allocations.items():
            if points > max_points:
                max_points = points
                winning_order = str_to_order[order_str]
            elif points == max_points: # If there's a tie, it holds
                winning_order = None
        if isinstance(winning_order, Move):
            winning_order.is_sortie = True
        return winning_order

    def get_player_dp_orders(self, player: Player) -> dict[Unit, DPAllocation]:
        """Gets the units a player has allocated DP to, as well as their orders and allocation amounts."""
        dp_orders: dict[Unit, DPAllocation] = {}
        for unit in self.units:
            if unit.dp_allocations and player.name in unit.dp_allocations:
                dp_orders[unit] = unit.dp_allocations[player.name]
        return dp_orders

    def get_dp_spent(self, player: Player) -> int:
        """Gets the total points a player has allocated across all their DP orders."""
        points_allocated = 0
        for allocation in self.get_player_dp_orders(player).values():
            points_allocated += allocation.points
        return points_allocated

    def has_affiliation(self, player1: Player, player2: Player | None) -> bool:
        """Checks to see if two powers are affilited, used for determining DP multipliers."""
        if player2 is None:
            return False
        affiliations = self.data["players"][player1.name].get("affiliates", [])
        return player2.name in affiliations

    def set_data(self, keys: str | list[str], value: Any) -> None:
        """Sets a value in the board's data dictionary and custom dictionary."""
        data = self.data
        custom_data = self.custom_data
        if isinstance(keys, str):
            keys = [keys]
        for key in keys[:-1]:
            data = data.setdefault(key, {})
            custom_data = custom_data.setdefault(key, {})
        data[keys[-1]] = value
        custom_data[keys[-1]] = value

    def is_chaos(self) -> bool:
        """Checks to see if this is a Chaos game."""
        return self.data["players"] == "chaos"

    def parse_order(self, order_type: str, destination: Optional[str], source: Optional[str]) -> Optional[UnitOrder]:
        """Given an order type and source/destination strings, attempts to parse it into an Order object."""
        order_classes = [
            NMR, Hold, Core, Transform, Move, ConvoyTransport, Support,
            RetreatMove, RetreatDisband
            ]
        order_class = next(
            _class
            for _class in order_classes
            if _class.__name__ == order_type
        )
        source_province, destination_province, destination_coast = None, None, None
        if destination is not None:
            if len(destination) == 2 and destination[1] == "c":
                destination_coast = destination
            else:
                destination_province, destination_coast = (
                    self.get_province_and_coast(destination)
                )
        if source is not None:
            source_province = self.get_province(source)
        if order_class == NMR:
            return None
        if order_class in order_classes:
            return order_class(
                source=source_province,
                destination=destination_province,
                destination_coast=destination_coast
            )
        raise ValueError(f"Could not parse {order_class}")

    def export_game(self) -> str:
        """Returns a JSON string representing the current game state."""
        def add_if_exists(d: dict, key: str, value):
            if value is not None:
                d[key] = str(value)

        def export_order(order: UnitOrder) -> dict:
            order_dict: dict = {"type": order.__class__.__name__}
            add_if_exists(order_dict, "destination", order.get_destination_str())
            add_if_exists(order_dict, "source", order.get_source_str())
            return order_dict

        def export_unit(u: Unit) -> dict:
            result: dict = {
                "type": u.unit_type.value,
            }
            add_if_exists(result, "owner", u.player)
            add_if_exists(result, "coast", u.coast)
            if u.province.dislodged_unit == u:
                result["is_dislodged"] = True
            if u.order is not None:
                result["order"] = export_order(u.order)
            if u.retreat_options is not None:
                result["retreat_options"] = [
                    p.get_name(c) for p, c in u.retreat_options
                ]
            if u.dp_allocations:
                result["dp_allocations"] = {
                    player_name: {"points": dp.points, "order": export_order(dp.order)}
                    for player_name, dp in u.dp_allocations.items()
                }
            return result

        players = []
        for player in sorted(self.players, key=lambda p: p.name):
            player_data: dict = {
                "name": player.name,
                "color": player.render_color,
                "is_active": player.is_active,
            }
            if player.build_orders:
                player_data["build_orders"] = [str(o) for o in player.build_orders]
            players.append(player_data)

        provinces = []
        for province in sorted(self.provinces, key=lambda p: p.name):
            prov_data: dict = {"name": province.name}
            add_if_exists(prov_data, "owner", province.owner)
            if province.is_impassable:
                prov_data["is_impassable"] = True
            add_if_exists(prov_data, "core", province.core_data.core)
            add_if_exists(prov_data, "half_core", province.core_data.half_core)
            if province.unit is not None:
                prov_data["unit"] = export_unit(province.unit)
            if province.dislodged_unit is not None:
                prov_data["dislodged_unit"] = export_unit(province.dislodged_unit)
            provinces.append(prov_data)

        params = {}
        for key, value in self.custom_data.items():
            try:
                json.dumps(value)
                params[key] = value
            except (TypeError, ValueError):
                continue

        export = {
            "turn": str(self.turn),
            "datafile": self.datafile,
            "fish": self.data.get("fish", 0),
            "players": players,
            "provinces": provinces,
            "parameters": params,
        }

        return json.dumps(export, indent=2)
