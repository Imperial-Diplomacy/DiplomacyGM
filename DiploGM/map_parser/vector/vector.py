import copy
import itertools
import json
import logging
import re
import time
import numpy as np
from xml.etree.ElementTree import Element, tostring

import shapely
from deepmerge.merger import Merger
from lxml import etree

from DiploGM.map_parser.vector.transform import TransGL3
from DiploGM.map_parser.vector.utils import (
    find_svg_element, get_element_color, get_unit_coordinates,
    parse_path, initialize_province_resident_data,
    LAYER_DICTIONARY, NAMESPACE, SVG_CONFIG_KEY
)
from DiploGM.models.turn import PhaseName, Turn
from DiploGM.models.board import Board
from DiploGM.models.player import Player
from DiploGM.models.province import Province, ProvinceType, UnitLocation
from DiploGM.models.unit import Unit, UnitType
from DiploGM.utils.sanitise import parse_variant_path

# TODO: (BETA) all attribute getting should be in utils which we import and call utils.my_unit()
# TODO: (BETA) consistent in bracket formatting
HIGH_PROVINCES_KEY = "high provinces"
LAYER_NAMES = set(LAYER_DICTIONARY.keys())

logger = logging.getLogger(__name__)

class Parser:
    def __init__(self, data: str):
        self.datafile = data

        # Loads the config files for the variant
        # We get the variant-wide config, and then apply any version-specific changes, if applicible
        config_merger = Merger(
            [
                (list, ["override"]),
                (dict, ["merge"]),
                (set, ["union"]),
            ],
            ["override"],
            ["override"]
        )
        with open(f"{parse_variant_path(data)}/config.json", "r", encoding="utf-8") as f:
            variant_data = json.load(f)
        try:
            with open(f"{parse_variant_path(data, return_parent=True)}/config.json", "r", encoding="utf-8") as f:
                self.data = json.load(f)
                self.data = config_merger.merge(self.data, variant_data)
        except FileNotFoundError:
            self.data = variant_data
        keys_to_delete = [p[0] for p in self.data["players"].items() if p[1].get("disabled", "False").lower() == "true"]
        for key in keys_to_delete:
            del self.data["players"][key]

        self.data["file"] = f"{parse_variant_path(data)}/{self.data['file']}"

        svg_root = etree.parse(self.data["file"])

        self.layers = self.data[SVG_CONFIG_KEY]
        self.layer_data: dict[str, Element] = {}

        # Gets the SVG elements for each layer, and stores them in the Parser
        for layer in LAYER_NAMES:
            l = find_svg_element(svg_root, layer, self.layers)
            if l is None:
                if layer in {"island_borders", "island_fill_layer"}:
                    logger.warning(f"Layer {layer} not found in SVG, but it might not be necessary")
                    continue
                raise ValueError(f"Layer {layer} not found in SVG")
            self.layer_data[layer] = l

        # If there are starting units in the map, get that layer as well
        if self.layers["detect_starting_units"]:
            starting_units = find_svg_element(svg_root, "starting_units", self.layers)
            if starting_units is None:
                raise ValueError("Starting_units layer expected but not found in SVG")
            self.layer_data["starting_units"] = starting_units

        if "impassibles_layer" in self.layers:
            impassibles_layer = find_svg_element(svg_root, "impassibles_layer", self.layers)
            if impassibles_layer is None:
                raise ValueError("Layer impassibles_layer not found in SVG")
            self.layer_data["impassibles_layer"] = impassibles_layer

        self.fow = self.layers.get("fow", False)
        # TODO: Move this out of SVG layers and update configs accordingly
        self.year_offset = self.layers.get("year", 1901)

        self.color_to_player: dict[str, Player | None] = {}
        self.name_to_province: dict[str, Province] = {}

        self.cache_provinces: set[Province] | None = None
        self.cache_adjacencies: set[tuple[str, str]] | None = None

        self.players: set[Player] = set()
        self.autodetect_players = False

    def verify_svg(self) -> bool:
        """Checks the SVG to try to find parsing issues."""
        is_valid = True
        seen_names: set[str] = set()

        # All provinces should have unique names
        for layer_name in ["land_layer", "island_borders", "sea_borders"]:
            layer = self.layer_data.get(layer_name)
            if layer is None:
                continue
            for element in layer:
                name = element.get(f"{NAMESPACE.get('inkscape')}label")
                if not name:
                    logger.error("[%s] Element has no name: %s",
                                 layer_name, etree.tostring(element, encoding='unicode')[:120])
                    is_valid = False
                    continue

                if name in seen_names:
                    logger.error("[%s] Duplicate name: '%s'", layer_name, name)
                    is_valid = False
                else:
                    seen_names.add(name)

        # All elements in these layers should have names that reference known provinces
        for layer_name in ["island_fill_layer", "supply_center_icons",
                           "army", "retreat_army", "fleet", "retreat_fleet"]:
            layer = self.layer_data.get(layer_name)
            if layer is None:
                continue
            for element in layer:
                name = element.get(f"{NAMESPACE.get('inkscape')}label")
                if not name:
                    logger.error("[%s] Element has no name: %s",
                                 layer_name, etree.tostring(element, encoding='unicode')[:120])
                    is_valid = False
                    continue

                name = re.sub(r" \(?[ensw]c\)?$", "", name)  # Remove coast names
                if name not in seen_names:
                    logger.error("[%s] Name '%s' not found in any province layer",
                                 layer_name, name)
                    is_valid = False

        return is_valid

    def parse(self) -> Board:
        """Parses the SVG and config data to create a Board with the initial state."""
        logger.debug("map_parser.vector.parse.start")
        start = time.time()

        self.players = set()
        self.color_to_player = {}
        self.name_to_province = {}

        # Get the players and their colors from the config, provided it's not a chaos game.
        self.autodetect_players = self.data["players"] == "chaos"
        if not self.autodetect_players:
            for name, data in self.data["players"].items():
                color = data["color"]
                player = Player(name, color, set(), set())
                self.players.add(player)
                if isinstance(color, dict):
                    color = color["standard"]
                self.color_to_player[color] = player
                player.is_active = data.get("active", "true").lower() == "true"

            neutral_colors = self.data[SVG_CONFIG_KEY]["neutral"]
            if isinstance(neutral_colors, dict):
                self.color_to_player[neutral_colors["standard"]] = None
            else:
                self.color_to_player[neutral_colors] = None
            self.color_to_player[self.data[SVG_CONFIG_KEY]["neutral_sc"]] = None

        provinces = self._get_provinces()

        units = {province.unit for province in provinces if province.unit}

        elapsed = time.time() - start
        logger.info(f"map_parser.vector.parse: {elapsed}s")

        # import matplotlib.pyplot as plt
        # for province in provinces:
        #     poly = province.geometry
        #     if isinstance(poly, shapely.Polygon):
        #         plt.plot(*poly.exterior.xy)
        #     else:
        #         for subpoly in poly.geoms:
        #             plt.plot(*subpoly.exterior.xy)
        # plt.show()

        for province in provinces:
            self._warn_missing_coordinates(province)

        initial_turn = Turn(self.year_offset, PhaseName.SPRING_MOVES, self.year_offset)
        if self.data.get("first_season") == "winter":
            initial_turn = initial_turn.get_previous_turn()

        if "victory_count" not in self.data:
            self.data["victory_count"] = int((len([1 for p in provinces if p.has_supply_center]) + 1) / 2)

        # Creates a deepcopy of the game data, and then loads player names and ISCC/VSCC values if needed
        game_data = copy.deepcopy(self.data)
        if (is_chaos := self.data["players"] == "chaos"):
            game_data["players"] = {}
        for player in self.players:
            if is_chaos or player.name not in game_data["players"]:
                game_data["players"][player.name] = {}
            if "iscc" not in game_data["players"][player.name]:
                game_data["players"][player.name]["iscc"] = \
                    len([1 for p in provinces if p.has_supply_center and p.owner == player])
            if "vscc" not in game_data["players"][player.name]:
                game_data["players"][player.name]["vscc"] = game_data["victory_count"]

        return Board(self.players, provinces, units, initial_turn, game_data, self.datafile, self.fow, self.year_offset)

    def _warn_missing_coordinates(self, province: Province) -> None:
        """Log a warning and reset any (0, 0) unit coordinates on a province."""
        checks: list[tuple[UnitType, str | None]] = []

        for coast in province.get_multiple_coasts():
            checks.append((UnitType.FLEET, coast))
        if not province.get_multiple_coasts() and province.get_coastal_adjacent():
            checks.append((UnitType.FLEET, None))
        if province.type != ProvinceType.SEA:
            checks.append((UnitType.ARMY, None))

        for unit_type, coast in checks:
            for is_retreat in (False, True):
                if province.get_unit_coordinates(unit_type, coast, is_retreat) == (0, 0):
                    kind = "retreat " if is_retreat else ""
                    name = province.get_name(coast) if coast else province.name
                    logger.warning(
                        f"{self.datafile}: Province {name} has no "
                        f"{unit_type.name.lower()} {kind}coord. Setting to 0,0 ..."
                    )
                    province.set_unit_coordinate(None, unit_type, is_retreat, coast)

    def read_map(self) -> tuple[set[Province], set[tuple[str, str]]]:
        """Reads the SVG and returns a set of Provinces and a set of adjacencies between province names."""
        if self.cache_provinces is None:
            # set coordinates and names
            raw_provinces: set[Province] = self._get_province_coordinates()
            cache = []
            self.cache_provinces = set()
            for province in raw_provinces:
                if province.name in cache:
                    logger.warning(f"{self.datafile}: {province.name} repeats in map, ignoring...")
                    continue
                cache.append(province.name)
                self.cache_provinces.add(province)

            if not self.layers["province_labels"]:
                self._initialize_province_names(self.cache_provinces)

        provinces = copy.deepcopy(self.cache_provinces)
        # Stores the Provinces in the Parser, and applies Convoyable Islands if applicable
        for province in provinces:
            self.name_to_province[province.name] = province
            if self.data.get("convoyable_islands") == "enabled" and province.type == ProvinceType.ISLAND:
                province.can_convoy = True

        if self.cache_adjacencies is None:
            # set adjacencies
            self.cache_adjacencies = self._get_adjacencies(provinces)
        adjacencies = copy.deepcopy(self.cache_adjacencies)

        return (provinces, adjacencies)

    def add_province_to_board(self, provinces: set[Province], province: Province) -> set[Province]:
        provinces = {x for x in provinces if x.name != province.name}
        provinces.add(province)
        self.name_to_province[province.name] = province
        return provinces

    def add_high_provinces(self, provinces: set[Province]):
        for name, data in self.data["overrides"][HIGH_PROVINCES_KEY].items():
            high_provinces: list[Province] = []
            for index in range(1, data["num"] + 1):
                province = Province(name + str(index), shapely.Polygon(), getattr(ProvinceType, data["type"]))
                provinces = self.add_province_to_board(provinces, province)
                high_provinces.append(province)

            # Add connections between each high province
            for provinceA in high_provinces:
                provinceA.adjacency_data.adjacent.update(provinceB for provinceB in high_provinces
                                        if provinceA.name != provinceB.name)

        for name, data in self.data["overrides"][HIGH_PROVINCES_KEY].items():
            adjacent = {self.name_to_province[n] for n in data["adjacencies"]}
            for index in range(1, data["num"] + 1):
                high_province = self.name_to_province[name + str(index)]
                high_province.adjacency_data.adjacent.update(adjacent)
                for ad in adjacent:
                    ad.adjacency_data.adjacent.add(high_province)
        return provinces

    def json_cheats(self, provinces: set[Province]) -> set[Province]:
        if "overrides" not in self.data:
            return set()
        if HIGH_PROVINCES_KEY in self.data["overrides"]:
            provinces = self.add_high_provinces(provinces)

        x_offset = 0
        y_offset = 0

        if "loc_x_offset" in self.data[SVG_CONFIG_KEY]:
            x_offset = self.data[SVG_CONFIG_KEY]["loc_x_offset"]

        if "loc_y_offset" in self.data[SVG_CONFIG_KEY]:
            x_offset = self.data[SVG_CONFIG_KEY]["loc_y_offset"]

        offset = np.array([x_offset, y_offset])

        if "provinces" not in self.data["overrides"]:
            return provinces

        for name, data in self.data["overrides"]["provinces"].items():
            province = self.name_to_province[name]
            # TODO: Some way to specify whether or not to clear other adjacencies?
            if "adjacencies" in data:
                province.adjacency_data.adjacent.update({self.name_to_province[n] for n in data["adjacencies"]})
            if "remove_adjacencies" in data:
                province.adjacency_data.adjacent.difference_update(
                    {self.name_to_province[n] for n in data["remove_adjacencies"]})
            if "remove_adjacent_coasts" in data:
                province.adjacency_data.nonadjacent_coasts.update(data["remove_adjacent_coasts"])
            if "difficult_adjacency" in data:
                province.adjacency_data.difficult_adjacencies.update(data["difficult_adjacency"])
            if "coasts" in data:
                province.adjacency_data.fleet_adjacent = {}
                for coast_name, coast_adjacent in data["coasts"].items():
                    province.adjacency_data.fleet_adjacent[coast_name] = {
                        self._get_province_and_coast(n) for n in coast_adjacent}
            # For compatability reasons, we assume these are sea tiles
            # TODO: Add support for armies/multicoastal tiles
            unit_locs = data.get("unit_loc", [])
            retreat_locs = data.get("retreat_unit_loc", [])
            for index, coordinate in enumerate(unit_locs):
                primary = tuple((np.array(coordinate) + offset).tolist())
                retreat_coord = retreat_locs[index] if index < len(retreat_locs) else coordinate
                retreat = tuple((np.array(retreat_coord) + offset).tolist())
                loc = UnitLocation(primary, retreat)
                province.all_coordinates.setdefault(UnitType.FLEET.name, set()).add(loc)
                province.unit_coordinates[UnitType.FLEET.name] = loc
        return provinces

    def _get_provinces(self) -> set[Province]:
        provinces, adjacencies = self.read_map()

        # Sets adjacencies for each province based on the adjacencies file
        for name1, name2 in adjacencies:
            province1 = self.name_to_province[name1]
            province2 = self.name_to_province[name2]
            province1.set_adjacent(province2)
            province2.set_adjacent(province1)

        # Apply any manual overrides from the config file (e.g. adding adjacencies, multiple coasts, etc.)
        provinces = self.json_cheats(provinces)

        # set coasts
        for province in provinces:
            province.set_coasts()

        for province in provinces:
            province.set_adjacent_coasts()

        # impassible provinces aren't in the list; they're "ghost" and only show up
        # when explicitly asked for in costal topology algorithms
        provinces = {p for p in provinces if p.type != ProvinceType.IMPASSIBLE}

        self._initialize_province_owners(self.layer_data.get("land_layer"))
        self._initialize_province_owners(self.layer_data.get("island_fill_layer"))

        # set supply centers
        if self.layers["center_labels"]:
            self._initialize_supply_centers_assisted()
        else:
            self._initialize_supply_centers(provinces)

        # set units
        if "starting_units" in self.layer_data:
            if self.layers["unit_labels"]:
                self._initialize_units_assisted()
            else:
                self._initialize_units(provinces)

        # set phantom unit coordinates for optimal unit placements
        self._set_phantom_unit_coordinates()

        for province in provinces:
            for unit in province.unit_coordinates.keys():
                province.all_coordinates.setdefault(unit, set()).add(province.unit_coordinates[unit])

        return provinces

    def _get_province_coordinates(self) -> set[Province]:
        # TODO: (BETA) don't hardcode translation
        land_provinces = self._create_provinces_type(self.layer_data.get("land_layer"), ProvinceType.LAND)
        island_provinces = self._create_provinces_type(self.layer_data.get("island_borders"), ProvinceType.ISLAND)
        sea_provinces = self._create_provinces_type(self.layer_data.get("sea_borders"), ProvinceType.SEA)
        # detect impassible to allow for better understanding
        # of coastlines
        # they don't go in board.provinces
        impassible_provinces = set()
        if self.layer_data.get("impassibles_layer") is not None:
            impassible_provinces = self._create_provinces_type(
                self.layer_data.get("impassibles_layer"), ProvinceType.IMPASSIBLE)
        return land_provinces | island_provinces | sea_provinces | impassible_provinces

    # TODO: (BETA) can a library do all of this for us? more safety from needing to support wild SVG legal syntax
    def _create_provinces_type(
        self,
        provinces_layer: Element | None,
        province_type: ProvinceType,
    ) -> set[Province]:
        if provinces_layer is None:
            return set()
        provinces = set()
        for province_data in list(provinces_layer):
            path_string = province_data.get("d")
            if not path_string:
                print(tostring(province_data))
                continue
                raise RuntimeError("Province path data not found")
            translation = TransGL3(provinces_layer) * TransGL3(province_data)

            province_coordinates = parse_path(path_string, translation)

            if len(province_coordinates) <= 1:
                poly = shapely.Polygon(province_coordinates[0])
            else:
                poly = shapely.MultiPolygon(list(map(shapely.Polygon, province_coordinates)))
                poly = poly.buffer(0.1)
                # import matplotlib.pyplot as plt

                # if not poly.is_valid:
                #     print(f"MULTIPOLYGON IS NOT VALID (name: {self.get_province_name(province_data)})")
                #     for subpoly in poly.geoms:
                #         plt.plot(*subpoly.exterior.xy)
                #     plt.show()

            province_coordinates = shapely.MultiPolygon()

            name = ""
            if self.layers["province_labels"]:
                name = self.get_province_name(province_data)
                if name == "":
                    raise RuntimeError(f"Province name not found in province with data {province_data}")

            province = Province(name, poly, province_type)

            provinces.add(province)
        return provinces

    def _initialize_province_owners(self, provinces_layer: Element | None) -> None:
        if provinces_layer is None:
            return
        for province_data in provinces_layer:
            name = self.get_province_name(province_data)
            self.name_to_province[name].owner = self.get_element_player(province_data, province_name=name)

    # Sets province names given the names layer
    def _initialize_province_names(self, provinces: set[Province]) -> None:
        def get_coordinates(name_data: Element) -> tuple[float, float]:
            x, y = name_data.get("x"), name_data.get("y")
            assert(x is not None and y is not None)
            return float(x), float(y)

        def set_province_name(province: Province, name_data: Element, _: str | None) -> None:
            if province.name != "":
                raise RuntimeError(f"Province already has name: {province.name}")
            new_name = name_data.findall(".//svg:tspan", namespaces=NAMESPACE)[0].text
            assert new_name is not None
            province.name = new_name

        initialize_province_resident_data(provinces,
                                          list(self.layer_data["names_layer"]),
                                          get_coordinates,
                                          set_province_name)

    def _initialize_supply_centers_assisted(self) -> None:
        for center_data in self.layer_data["supply_center_icons"]:
            name = self.get_province_name(center_data)
            province = self.name_to_province[name]

            if province.has_supply_center:
                raise RuntimeError(f"{name} already has a supply center")
            province.has_supply_center = True

            owner = province.owner
            if owner:
                owner.centers.add(province)

            # TODO: (BETA): we cheat assume core = owner if exists because capital center symbols work different
            core = province.owner
            if not core:
                core_data = center_data.findall(".//svg:circle", namespaces=NAMESPACE)
                if len(core_data) >= 2:
                    core = self.get_element_player(core_data[1], province_name=province.name)
            province.core_data.core = core

    # Sets province supply center values
    def _initialize_supply_centers(self, provinces: set[Province]) -> None:

        def get_coordinates(supply_center_data: Element) -> tuple[float | None, float | None]:
            circles = supply_center_data.findall(".//svg:circle", namespaces=NAMESPACE)
            if not circles:
                return None, None
            circle = circles[0]
            cx = circle.get("cx")
            cy = circle.get("cy")
            if cx is None or cy is None:
                return None, None
            base_coordinates = float(cx), float(cy)
            trans = TransGL3(supply_center_data)
            return trans.transform(base_coordinates)

        def set_province_supply_center(province: Province, _element: Element, _coast: str | None) -> None:
            if province.has_supply_center:
                raise RuntimeError(f"{province.name} already has a supply center")
            province.has_supply_center = True

        initialize_province_resident_data(provinces,
                                          self.layer_data["supply_center_icons"],
                                          get_coordinates,
                                          set_province_supply_center)

    def _set_province_unit(self, province: Province, unit_data: Element, coast: str | None = None) -> None:
        if province.unit:
            return
            raise RuntimeError(f"{province.name} already has a unit")

        unit_type = self._get_unit_type(unit_data)

        # assume that all starting units are on provinces colored in to their color
        player = province.owner

        # color_data = unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0]
        # player = self.get_element_player(color_data)

        unit = Unit(unit_type, player, province, coast)
        province.unit = unit
        if unit.player is not None:
            unit.player.units.add(unit)

    def _initialize_units_assisted(self) -> None:
        for unit_data in self.layer_data["starting_units"]:
            province_name = self.get_province_name(unit_data)
            if self.data[SVG_CONFIG_KEY]["unit_type_labeled"]:
                province_name = province_name[1:]
            province, coast = self._get_province_and_coast(province_name)
            self._set_province_unit(province, unit_data, coast)

    # Sets province unit values
    def _initialize_units(self, provinces: set[Province]) -> None:
        def get_coordinates(unit_data: Element) -> tuple[float | None, float | None]:
            base_coordinates = tuple(
                map(float, unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0].get("d").split()[1].split(","))
            )
            assert len(base_coordinates) == 2
            trans = TransGL3(unit_data)
            return trans.transform(base_coordinates)

        initialize_province_resident_data(provinces,
                                          self.layer_data["starting_units"],
                                          get_coordinates,
                                          self._set_province_unit)

    def _set_phantom_unit_coordinates(self) -> None:
        army_layer_to_key = [
            (self.layer_data["army"], True),
            (self.layer_data["retreat_army"], False),
        ]
        for layer, is_primary in army_layer_to_key:
            layer_translation = TransGL3(layer)
            for unit_data in list(layer):
                unit_translation = TransGL3(unit_data)
                province = self._get_province(unit_data)
                coordinate = get_unit_coordinates(unit_data)
                province.set_unit_coordinate(
                    layer_translation.transform(unit_translation.transform(coordinate)),
                    UnitType.ARMY, not is_primary)

        fleet_layer_to_key = [
            (self.layer_data["fleet"], True),
            (self.layer_data["retreat_fleet"], False),
        ]
        for layer, is_primary in fleet_layer_to_key:

            layer_translation = TransGL3(layer)
            for unit_data in list(layer):
                unit_translation = TransGL3(unit_data)
                # This could either be a sea province or a land coast
                province_name = self.get_province_name(unit_data)
                # this is me writing bad code to get this out faster, will fix later when we clean up this file
                province, coast = self._get_province_and_coast(province_name)
                coordinate = get_unit_coordinates(unit_data)
                translated_coordinate = layer_translation.transform(unit_translation.transform(coordinate))
                province.set_unit_coordinate(translated_coordinate, UnitType.FLEET, not is_primary, coast)

    @staticmethod
    def get_province_name(province_data: Element) -> str:
        province_name = province_data.get(f"{NAMESPACE.get('inkscape')}label")
        return province_name or ""

    def _get_province(self, province_data: Element) -> Province:
        return self.name_to_province[self.get_province_name(province_data)]

    def _get_province_and_coast(self, province_name: str) -> tuple[Province, str | None]:
        coast_suffix: str | None = None
        coast_names = {" nc", " sc", " ec", " wc"}
        province_name = province_name.replace("(", "").replace(")", "")

        for coast_name in coast_names:
            if province_name.endswith(coast_name):
                province_name = province_name[:-3]
                coast_suffix = coast_name[1:]
                break

        province = self.name_to_province[province_name]
        return province, coast_suffix

    # Returns province adjacency set
    def _get_adjacencies(self, provinces: set[Province]) -> set[tuple[str, str]]:
        adjacencies = set()
        try:
            f = open(f"assets/{self.datafile}_adjacencies.txt", "r", encoding="utf-8")
        except FileNotFoundError:
            f = open(f"assets/{self.datafile}_adjacencies.txt", "w", encoding="utf-8")
            # Combinations so that we only have (A, B) and not (B, A) or (A, A)
            for province1, province2 in itertools.combinations(provinces, 2):
                if shapely.distance(province1.geometry, province2.geometry) < self.layers["border_margin_hint"]:
                    adjacencies.add((province1.name, province2.name))
                    f.write(f"{province1.name},{province2.name}\n")
        else:
            for line in f:
                adjacencies.add(tuple(line[:-1].split(',')))
        finally:
            f.close()
        return adjacencies

    def get_element_player(self, element: Element, province_name: str="") -> Player | None:
        color = get_element_color(element)
        neutral_color = self.data[SVG_CONFIG_KEY]["neutral"]
        if isinstance(neutral_color, dict):
            neutral_color = neutral_color["standard"]
        #FIXME: only works if there's one person per province
        if self.autodetect_players:
            if color is None or color == neutral_color:
                return None
            player = Player(province_name, color, set(), set())
            self.players.add(player)
            self.color_to_player[color] = player
            return player
        if color in self.color_to_player:
            return self.color_to_player[color]
        if color is not None and color != neutral_color:
            player = Player(province_name, color, set(), set(), is_active = False)
            self.players.add(player)
            self.color_to_player[color] = player
            return player
        if color is None:
            return None

    def _get_unit_type(self, unit_data: Element) -> UnitType:
        if self.data[SVG_CONFIG_KEY]["unit_type_labeled"]:
            name = self.get_province_name(unit_data).lower()
            if name[0] == "f":
                return UnitType.FLEET
            if name[0] == "a":
                return UnitType.ARMY
            raise RuntimeError(f"Unit types are labeled, but {name} doesn't start with F or A")

        if "unit_type_from_names" in self.data[SVG_CONFIG_KEY] and self.data[SVG_CONFIG_KEY]["unit_type_from_names"]:
            # unit_data = unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0]
            name = unit_data[1].get(f"{NAMESPACE.get('inkscape')}label")
            assert name is not None
            if name.lower().startswith("sail"):
                return UnitType.FLEET
            if name.lower().startswith("shield"):
                return UnitType.ARMY
            raise RuntimeError(f"Unit types are labeled, but {name} wasn't sail or shield")

        unit_data = unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0]
        num_sides = unit_data.get("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}sides")
        if num_sides == "3":
            return UnitType.FLEET
        elif num_sides == "6":
            return UnitType.ARMY
        else:
            return UnitType.ARMY
            raise RuntimeError(f"Unit has {num_sides} sides which does not match any unit definition.")


parsers = {}


def get_parser(name: str, force_refresh: bool=False) -> Parser:
    name = parse_variant_path(name, as_filename=False)
    if force_refresh or name not in parsers:
        logger.info(f"Creating new Parser for board named {name}")
        new_parser = Parser(name)
        if new_parser.verify_svg():
            parsers[name] = new_parser
        else:
            raise ValueError(f"SVG verification failed for {name}")
    return parsers[name]


# oneTrueParser = Parser()
