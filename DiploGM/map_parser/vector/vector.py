import copy
import itertools
import json
import logging
import os
import re
import time
import tomllib
from xml.etree.ElementTree import Element, tostring

import shapely
from deepmerge.merger import Merger
from lxml import etree

from DiploGM.map_parser.vector.transform import TransGL3
from DiploGM.map_parser.vector.utils import (
    get_coordinates, find_svg_element, get_element_color, get_sc_coordinates,
    get_unit_coordinates, parse_path, initialize_province_resident_data,
    LAYER_DICTIONARY, NAMESPACE, SVG_CONFIG_KEY
)
from DiploGM.models.adjacency import Terrain
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
INKSCAPE_LABEL = f"{NAMESPACE.get('inkscape')}label"

logger = logging.getLogger(__name__)

class Parser:
    def __init__(self, data: str):
        self.datafile = data

        # Loads the config files for the variant
        # We get the variant-wide config, and then apply any version-specific changes, if applicible
        self.data = self._load_config(data)
        self.unit_types = self._load_unit_types()

        svg_root = etree.parse(self.data["file"])

        # Fetches the SVG elements for each layer, and stores them in the Parser
        self.layers = self.data[SVG_CONFIG_KEY]
        self.layer_data = self._load_layer_data(svg_root)

        self.impassable_color = self.data[SVG_CONFIG_KEY].get("impassable", "000000")
        if isinstance(self.impassable_color, dict):
            self.impassable_color = self.impassable_color.get("standard", "000000")

        self.color_to_player: dict[str, Player | None] = {}
        self.name_to_province: dict[str, Province] = {}

        self.cache_provinces: set[Province] | None = None
        self.cache_adjacencies: set[tuple[str, str]] | None = None

        self.players: set[Player] = set()
        self.autodetect_players = False

    def _load_config(self, variant_name: str) -> dict:
        config_merger = Merger(
            [
                (list, ["override"]),
                (dict, ["merge"]),
                (set, ["union"]),
            ],
            ["override"],
            ["override"]
        )
        with open(f"{parse_variant_path(variant_name)}/config.json", "r", encoding="utf-8") as f:
            variant_data = json.load(f)
        try:
            with open(f"{parse_variant_path(variant_name, return_parent=True)}/config.json",
                      "r", encoding="utf-8") as f:
                data = json.load(f)
                data = config_merger.merge(data, variant_data)
        except FileNotFoundError:
            data = variant_data
        # If a config override removes a player, delete it
        if isinstance(data["players"], dict):
            keys_to_delete = [p[0] for p in data["players"].items()
                              if p[1].get("disabled", "False").lower() == "true"]
            for key in keys_to_delete:
                del data["players"][key]

        data["file"] = f"{parse_variant_path(variant_name)}/{data['file']}"
        return data

    def _load_unit_types(self) -> dict[str, UnitType]:
        unit_files = ["assets/unit_types/army.toml", "assets/unit_types/fleet.toml"]
        for folder in [parse_variant_path(self.datafile, return_parent=True), parse_variant_path(self.datafile)]:
            if os.path.isdir(f"{folder}/units"):
                unit_files.extend([f"{folder}/units/{f}" for f in os.listdir(f"{folder}/units") if f.endswith(".toml")])
        unit_types: dict[str, UnitType] = {}
        transforms: dict[str, str] = {}
        for unit_file in unit_files:
            with open(unit_file, "rb") as f:
                unit_data = tomllib.load(f)
                unit_code = unit_data.get("code", unit_data["name"][0].upper())
                unit_types[unit_code] = UnitType(
                    name = unit_data["name"],
                    code = unit_code,
                    aliases = set(unit_data.get("aliases", [])),
                    can_convoy = unit_data.get("can_convoy", False),
                    can_be_convoyed = unit_data.get("can_be_convoyed", False),
                    can_capture = unit_data.get("can_capture", True),
                    moves_on = {Terrain[terrain.upper()] for terrain in unit_data.get("moves_on", ["Land"])},
                    transforms_to = None
                )
                if unit_data.get("transforms_to"):
                    transforms[unit_code] = unit_data["transforms_to"]
        for unit_code, transform_code in transforms.items():
            unit_types[unit_code].transforms_to = unit_types[transform_code]
        return unit_types

    def _create_retreat_layer(self, svg_root: etree._ElementTree, layer_name: str, config_data: dict) -> Element:
        """If a retreat layer is not found, we create one by copying the normal unit layer."""
        move_layer_name = layer_name.replace("retreat_", "")
        print(f"Retreat layer {layer_name} not found. Creating one by copying {move_layer_name} layer.")
        move_layer = find_svg_element(svg_root, move_layer_name, config_data)
        if move_layer is None:
            raise ValueError(f"Neither {layer_name} nor {move_layer_name} layers were found in the SVG")
        retreat_layer = copy.deepcopy(move_layer)
        retreat_layer.set("id", config_data.get(layer_name, f"{move_layer_name}_retreat"))
        retreat_layer.set(f"{NAMESPACE.get('inkscape')}label", f"{move_layer_name.capitalize()} Locations (Retreats)")
        translation = -self.data[SVG_CONFIG_KEY].get("unit_radius", 0)
        retreat_layer.set("transform", f"translate({translation}, {translation}) {retreat_layer.get('transform', '')}")
        svg_root.getroot().append(retreat_layer)
        return retreat_layer

    def _load_layer_data(self, svg_root: etree._ElementTree) -> dict[str, Element]:
        layer_data: dict[str, Element] = {}

        # Gets the SVG elements for each layer, and stores them in the Parser
        for layer in LAYER_NAMES:
            l = find_svg_element(svg_root, layer, self.layers)
            if l is None:
                if layer in {"retreat_army", "retreat_fleet"}:
                    logger.info("Layer %s not found in SVG. Duplicating army/fleet layer.", layer)
                    l = self._create_retreat_layer(svg_root, layer, self.layers)
                else:
                    logger.debug("Layer %s not found in SVG", layer)
            layer_data[layer] = Element("empty") if l is None else l

        # If there are starting units in the map, get that layer as well
        if self.layers["detect_starting_units"]:
            starting_units = find_svg_element(svg_root, "starting_units", self.layers)
            if starting_units is None:
                raise ValueError("Starting_units layer expected but not found in SVG")
            layer_data["starting_units"] = starting_units
        return layer_data

    def verify_svg(self) -> list[str]:
        """Checks the SVG to try to find parsing issues."""
        errors = []
        seen_names: set[str] = set()
        for province, data in self.data.get("overrides", {}).get("high provinces", {}).items():
            seen_names.update(f"{province}{i}" for i in range(1, data["num"] + 1))
        high_province_names = seen_names.copy()

        # All provinces should have unique names
        for layer_name in ["land_layer", "island_borders", "sea_borders"]:
            layer = self.layer_data.get(layer_name, [])
            for element in layer:
                name = element.get(INKSCAPE_LABEL)
                if not name:
                    error = f"[{layer_name}] Element has no name: {element.get('id')}"
                    logger.error(error)
                    errors.append(error)
                    continue

                if name in seen_names and name not in high_province_names:
                    error = f"[{layer_name}] Duplicate name: '{name}'"
                    logger.error(error)
                    errors.append(error)
                else:
                    seen_names.add(name)

        # All elements in these layers should have names that reference known provinces
        for layer_name in ["island_fill_layer", "supply_center_icons",
                           "army", "retreat_army", "fleet", "retreat_fleet"]:
            layer = self.layer_data.get(layer_name, [])
            for element in layer:
                name = element.get(INKSCAPE_LABEL)
                if not name:
                    error = f"[{layer_name}] Element has no name: {element.get('id')}"
                    logger.error(error)
                    errors.append(error)
                    continue

                name = re.sub(r" \(?[ensw]c\)?$", "", name)  # Remove coast names
                if name not in seen_names:
                    error = f"[{layer_name}] Name '{name}' not found in any province layer"
                    logger.error(error)
                    errors.append(error)

        return errors

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

        provinces, adjacencies = self._read_map()
        provinces = self._get_provinces(provinces, adjacencies)

        units = {province.unit for province in provinces if province.unit}

        elapsed = time.time() - start
        logger.info("map_parser.vector.parse: %ss", elapsed)

        self.data["year"] = self.data.get("year", 1901)
        initial_turn = Turn(self.data["year"], PhaseName.SPRING_MOVES, self.data["year"])
        if self.data.get("first_season", "spring").lower() == "winter":
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

        return Board(self.players, provinces, self.unit_types, units, initial_turn, game_data, self.datafile)

    def _read_map(self) -> tuple[set[Province], set[tuple[str, str]]]:
        """Reads the SVG, gets provinces information and coordinates,
        and returns a set of Provinces and a set of adjacencies between province names."""
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

    def _add_province_to_board(self, provinces: set[Province], province: Province) -> set[Province]:
        provinces = {x for x in provinces if x.name != province.name}
        provinces.add(province)
        self.name_to_province[province.name] = province
        return provinces

    def _json_cheats(self, provinces: set[Province]) -> set[Province]:
        if "overrides" not in self.data:
            return provinces

        offset = complex(self.data[SVG_CONFIG_KEY].get("loc_x_offset", 0),
                         self.data[SVG_CONFIG_KEY].get("loc_y_offset", 0))

        for name, data in self.data["overrides"].get("provinces", {}).items():
            province = self.name_to_province.get(name)
            if not province:
                logger.debug("Province %s in overrides not found in map, skipping...", name)
                continue
            # Add/remove adjacencies and coasts
            for n in data.get("adjacencies", []):
                province.adjacencies.add(self.name_to_province[n])
            for n in data.get("remove_adjacencies", []):
                province.adjacencies.remove(self.name_to_province[n])
            for n in data.get("difficult_adjacency", []):
                if (adj := province.adjacencies.get(self.name_to_province[n])) is not None:
                    adj.is_difficult = True
            if "coasts" in data:
                for coast_name, coast_adjacent in data.get("coasts", {}).items():
                    for adjacent_name in coast_adjacent:
                        p, c = self._get_province_and_coast(adjacent_name)
                        province.adjacencies.add_coast(p, coast_name, c)
            # Add extra unit locations for provinces that wrap around or have weird shapes
            # For compatability reasons, we assume these are sea tiles
            # TODO: Add support for other unit types
            unit_locs = data.get("unit_loc", [])
            retreat_locs = data.get("retreat_unit_loc", [])
            for index, coordinate in enumerate(unit_locs):
                primary = complex(*coordinate) + offset
                retreat_coord = retreat_locs[index] if index < len(retreat_locs) else coordinate
                retreat = complex(*retreat_coord) + offset
                loc = UnitLocation(primary, retreat)
                province.all_coordinates.setdefault("Fleet", set()).add(loc)
                province.unit_coordinates["Fleet"] = loc
        return provinces

    def _remove_unit_adjacencies(self, provinces: set[Province]) -> set[Province]:
        if "overrides" not in self.data:
            return provinces
        for name, data in self.data["overrides"].get("provinces", {}).items():
            province = self.name_to_province.get(name)
            if not province:
                logger.debug("Province %s in overrides not found in map, skipping...", name)
                continue
            for n in data.get("remove_adjacent_coasts", []):
                province.adjacencies.remove(self.name_to_province[n], Terrain.COAST)
            for n in data.get("remove_adjacent_land", []):
                province.adjacencies.remove(self.name_to_province[n], Terrain.LAND)
        return provinces


    def _get_provinces(self, provinces: set[Province], adjacencies: set[tuple[str, str]]) -> set[Province]:
        # Sets adjacencies for each province based on the adjacencies file
        for name1, name2 in adjacencies:
            province1 = self.name_to_province[name1]
            province2 = self.name_to_province[name2]
            province1.adjacencies.add(province2)
            province2.adjacencies.add(province1)

        # Apply any manual overrides from the config file (e.g. adding adjacencies, multiple coasts, etc.)
        provinces = self._json_cheats(provinces)

        # Set fleet adjacencies
        for province in provinces:
            province.set_coasts()
        # We set land-land fleet adjacencies afterwards, since we need to figure out which adjacencies are valid
        for province in provinces:
            province.set_adjacent_coasts()
        provinces = self._remove_unit_adjacencies(provinces)

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

        # Add a default unit coordinate to provinces without one, just in case
        for province in provinces:
            center = shapely.centroid(province.geometry)
            center = complex(center.x, center.y) if center else complex(0)
            province.unit_coordinates["default"] = UnitLocation(primary_coordinate=center,
                                                                retreat_coordinate=center)
            for unit in province.unit_coordinates.keys():
                province.all_coordinates.setdefault(unit, set()).add(province.unit_coordinates[unit])

        return provinces

    def _get_province_coordinates(self) -> set[Province]:
        # Creates Provinces objects for each province element in the SVG, and stores them in a set.
        # This includes the geometry of the province, its name, and its type.
        # Adjacency, ownership, and other information is added later.
        provinces = set()
        province_types = {"land_layer": ProvinceType.LAND,
                          "island_borders": ProvinceType.ISLAND,
                          "sea_borders": ProvinceType.SEA}
        for layer_name, province_type in province_types.items():
            if (cur_layer := self.layer_data.get(layer_name)) is None:
                continue
            layer_transformation = TransGL3(cur_layer)
            for province_data in list(cur_layer):
                provinces.add(self._create_province(province_data, province_type, layer_transformation))
        return provinces

    # TODO: (BETA) can a library do all of this for us? more safety from needing to support wild SVG legal syntax
    def _create_province(
        self,
        province_data: Element,
        province_type: ProvinceType,
        layer_transformation: TransGL3
    ) -> Province:
        # Given an SVG element for a province, creates a Province object with the correct geometry and name.
        path_string = province_data.get("d")
        if not path_string:
            print(tostring(province_data))
            raise RuntimeError("Province path data not found")
        translation = layer_transformation * TransGL3(province_data)

        province_coordinates = parse_path(path_string, translation)
        if len(province_coordinates) <= 1:
            poly = shapely.Polygon([(p.real, p.imag) for p in province_coordinates[0]])
        else:
            poly = shapely.MultiPolygon(list(map(lambda coords: shapely.Polygon([(p.real, p.imag) for p in coords]),
                                                 province_coordinates)))
            poly = poly.buffer(0.1)

        name = ""
        if self.layers["province_labels"]:
            name = self.get_province_name(province_data)
            if name == "":
                raise RuntimeError(f"Province name not found in province with data {province_data}")

        province = Province(name, poly, province_type)

        # We set impassability here, though it might be better to do it elsewhere
        color = get_element_color(province_data)
        if color == self.impassable_color:
            province.is_impassable = True

        return province

    def _initialize_province_owners(self, provinces_layer: Element | None) -> None:
        if provinces_layer is None:
            return
        for province_data in provinces_layer:
            name = self.get_province_name(province_data)
            if self.name_to_province[name].is_impassable:
                continue
            self.name_to_province[name].owner = self._get_element_player(province_data, province_name=name)

    # Sets province names given the names layer
    def _initialize_province_names(self, provinces: set[Province]) -> None:
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
        sc_layer_transformation = TransGL3(self.layer_data["supply_center_icons"])
        for center_data in self.layer_data["supply_center_icons"]:
            name = self.get_province_name(center_data)
            province = self.name_to_province[name]
            supply_center_coords = sc_layer_transformation.transform(get_sc_coordinates(center_data))
            supply_center_point = shapely.Point(supply_center_coords.real, supply_center_coords.imag)
            if not shapely.dwithin(supply_center_point, province.geometry, self.data[SVG_CONFIG_KEY].get("unit_radius", 10)):
                logger.warning(f"{self.datafile}: Supply center icon for '{name}' is not within its province")

            if province.has_supply_center:
                raise RuntimeError(f"{name} already has a supply center")
            province.has_supply_center = True

            owner = province.owner
            if owner:
                owner.centers.add(province)

            # TODO: (BETA): we cheat assume core = owner if exists because capital center symbols work different
            core = province.owner
            if not core:
                sc_circles = center_data.findall(".//svg:circle", namespaces=NAMESPACE)
                if len(sc_circles) > 0:
                    core = self._get_element_player(sc_circles[-1], province_name=province.name)
                else:
                    core = self._get_element_player(center_data, province_name=province.name)
            province.core_data.core = core

    # Sets province supply center values
    def _initialize_supply_centers(self, provinces: set[Province]) -> None:
        def set_province_supply_center(province: Province, _element: Element, _coast: str | None) -> None:
            if province.has_supply_center:
                raise RuntimeError(f"{province.name} already has a supply center")
            province.has_supply_center = True

        initialize_province_resident_data(provinces,
                                          self.layer_data["supply_center_icons"],
                                          get_sc_coordinates,
                                          set_province_supply_center)

    def _set_province_unit(self, province: Province, unit_data: Element, coast: str | None = None) -> None:
        if province.unit:
            return
            # raise RuntimeError(f"{province.name} already has a unit")

        unit_type = self.unit_types[self._get_unit_type(unit_data)]

        # assume that all starting units are on provinces colored in to their color
        player = province.owner

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
        def get_coordinates(unit_data: Element) -> complex:
            path = unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0]
            points = parse_path(path.get("d"), TransGL3(unit_data))
            return points[0][0]

        initialize_province_resident_data(provinces,
                                          self.layer_data["starting_units"],
                                          get_coordinates,
                                          self._set_province_unit)

    def _set_phantom_unit_coordinates(self) -> None:
        layers = []
        for unit_type in self.unit_types.values():
            layers.append((unit_type.name.lower(), unit_type, False))
            layers.append((f"retreat_{unit_type.name.lower()}", unit_type, True))

        for layer_name, unit_type, is_retreat in layers:
            if (layer := self.layer_data.get(layer_name)) is None:
                continue
            layer_translation = TransGL3(layer)
            for unit_data in list(layer):
                unit_translation = TransGL3(unit_data)
                province, coast = self._get_province_and_coast(self.get_province_name(unit_data))
                coordinate = get_unit_coordinates(unit_data)
                translated_coordinate = layer_translation.transform(unit_translation.transform(coordinate))
                province.set_unit_coordinate(translated_coordinate, unit_type, is_retreat, coast)

    @staticmethod
    def get_province_name(province_data: Element) -> str:
        """Gets the province name from the SVG element, using Inkscape labels."""
        province_name = province_data.get(INKSCAPE_LABEL)
        return province_name or ""

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

    # Attempts to get adjacencies from the cache file
    # If one doesn't exist, we go through each pair of provinces and see if they're within a certain distance
    # If they are, we add them to the adjacencies and write that to the cache file for next time
    def _get_adjacencies(self, provinces: set[Province]) -> set[tuple[str, str]]:
        adjacencies = set()
        try:
            f = open(f"assets/{self.datafile}_adjacencies.txt", "r", encoding="utf-8")
            for line in f:
                adjacencies.add(tuple(line[:-1].split(',')))
        except FileNotFoundError:
            f = open(f"assets/{self.datafile}_adjacencies.txt", "w", encoding="utf-8")
            # Combinations so that we only have (A, B) and not (B, A) or (A, A)
            for province1, province2 in itertools.combinations(provinces, 2):
                if shapely.dwithin(province1.geometry, province2.geometry, self.layers["border_margin_hint"]):
                    adjacencies.add((province1.name, province2.name))
                    f.write(f"{province1.name},{province2.name}\n")
        f.close()
        return adjacencies

    def _get_element_player(self, element: Element, province_name: str="") -> Player | None:
        color = get_element_color(element)
        neutral_color = self.data[SVG_CONFIG_KEY]["neutral"]
        if isinstance(neutral_color, dict):
            neutral_color = neutral_color["standard"]
        #FIXME: only works if there's one person per province
        if self.autodetect_players:
            if color is None or color == neutral_color or color == self.impassable_color:
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
        return None

    def _get_unit_type(self, unit_data: Element) -> str:
        # Might not be the best if there's overlap, I guess
        # TODO: Figure out how best to represent custom units here
        data_to_unit = {"f": "F", "a": "A",
                        "sail": "F", "shield": "A",
                        "3": "F", "6": "A"}

        if self.data[SVG_CONFIG_KEY]["unit_type_labeled"]:
            name = self.get_province_name(unit_data).lower()
            if name[0] in data_to_unit:
                return data_to_unit[name[0]]
            raise RuntimeError(f"Unit types are labeled, but {name} doesn't start with F or A")

        if "unit_type_from_names" in self.data[SVG_CONFIG_KEY] and self.data[SVG_CONFIG_KEY]["unit_type_from_names"]:
            name = unit_data[1].get(INKSCAPE_LABEL)
            if name is None:
                raise RuntimeError("Unit has no label, but unit_type_from_names is enabled")
            if name.lower() in data_to_unit:
                return data_to_unit[name.lower()]
            raise RuntimeError(f"Unit types are labeled, but {name} wasn't sail or shield")

        unit_data = unit_data.findall(".//svg:path", namespaces=NAMESPACE)[-1]
        num_sides = unit_data.get("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}sides")
        if num_sides in data_to_unit:
            return data_to_unit[num_sides]
        return "A"
        # raise RuntimeError(f"Unit has {num_sides} sides which does not match any unit definition.")

parsers = {}


def get_parser(name: str, force_refresh: bool=False) -> Parser | str:
    """Gets the Parser for the given variant,
    creating a new one if it doesn't already exist or if force_refresh is True."""
    name = parse_variant_path(name, as_filename=False)
    if force_refresh or name not in parsers:
        logger.info("Creating new Parser for board named %s", name)
        new_parser = Parser(name)
        errors = new_parser.verify_svg()
        if not errors:
            parsers[name] = new_parser
        else:
            logger.error("SVG verification failed for %s:\n* %s", name, "\n* ".join(errors))
            return f"SVG verification failed for {name}:" + "\n* " + "\n* ".join(errors)
    return parsers[name]
