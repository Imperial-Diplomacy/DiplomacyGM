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
import lxml.etree as etree

from DiploGM.map_parser.vector.transform import TransGL3
from DiploGM.map_parser.vector.utils import (
    get_coordinates, find_svg_element, get_element_color, get_sc_coordinates,
    get_element_unit_coordinates, parse_path, initialize_province_resident_data, weighted_random_color,
    LAYER_DICTIONARY, NAMESPACE, SVG_CONFIG_KEY
)
from DiploGM.models.adjacency import Terrain
from DiploGM.models.turn import PhaseName, Turn
from DiploGM.models.board import Board
from DiploGM.models.player import Player
from DiploGM.models.province import Province
from DiploGM.models.tile import Tile, ProvinceType, UnitLocation
from DiploGM.models.unit import Unit, UnitType
from DiploGM.utils.sanitise import parse_variant_path

# TODO: (BETA) all attribute getting should be in utils which we import and call utils.my_unit()
# TODO: (BETA) consistent in bracket formatting
LAYER_NAMES = set(LAYER_DICTIONARY.keys())
INKSCAPE_LABEL = f"{NAMESPACE.get('inkscape')}label"
COAST_REGEX_PATTERN = re.compile(r"^(.*?)\s*(?: \(([neswc]+c)\)| ([neswc]+c))$", re.IGNORECASE)

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
        self.name_to_tile: dict[str, Tile] = {}

        self.tiles: set[Tile] | None = None

        self.players: set[Player] = set()
        self.is_chaos = False

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

        def fetch_config_data(variant_name: str, parent: bool = False) -> dict:
            variant_path = f"{parse_variant_path(variant_name, return_parent=parent)}/config.toml"
            use_toml = os.path.isfile(variant_path)
            if not use_toml:
                variant_path = variant_path[:-4] + "json"

            with open(variant_path, 'rb') as f:
                return tomllib.load(f) if use_toml else json.load(f)

        variant_data = fetch_config_data(variant_name)
        try:
            data = fetch_config_data(variant_name, parent=True)
            data = config_merger.merge(data, variant_data)
        except FileNotFoundError:
            data = variant_data

        match data.get("config_version"):
            case None | "0.1":
                pass

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

                name = re.sub(r" \(?[ensw]+c\)?$", "", name, flags=re.IGNORECASE)  # Remove coast names
                if name not in seen_names:
                    error = f"[{layer_name}] Name '{name}' not found in any province layer"
                    logger.error(error)
                    errors.append(error)

        return errors

    def parse(self, **kwargs) -> Board:
        """Parses the SVG and config data to create a Board with the initial state."""
        logger.debug("map_parser.vector.parse.start")
        start = time.time()

        self.players = set()
        self.color_to_player = {}
        self.name_to_province = {}

        # Get the players and their colors from the config, provided it's not a chaos game.
        self.is_chaos = kwargs.get("chaos", False)
        self.is_chaos |= isinstance(self.data["players"], str)
        if not self.is_chaos:
            for name, data in self.data["players"].items():
                color = data["color"]
                player = Player(name, color, set(), set())
                self.players.add(player)
                if isinstance(color, dict):
                    color = color["standard"]
                self.color_to_player[color.lower()] = player
                player.is_active = data.get("active", "true").lower() == "true"

            neutral_colors = self.data[SVG_CONFIG_KEY]["neutral"]
            if isinstance(neutral_colors, dict):
                self.color_to_player[neutral_colors["standard"].lower()] = None
            else:
                self.color_to_player[neutral_colors.lower()] = None
            self.color_to_player[self.data[SVG_CONFIG_KEY]["neutral_sc"].lower()] = None

        tiles = self._build_tiles()
        provinces = self._get_provinces(tiles)

        units = {province.unit for province in provinces if province.unit}

        elapsed = time.time() - start
        logger.info("map_parser.vector.parse: %ss", elapsed)

        self.data["year"] = self.data.get("year", 1901)
        initial_turn = Turn(self.data["year"], PhaseName.SPRING_MOVES, self.data["year"])
        if self.data.get("first_season", "spring").lower() == "winter" or self.is_chaos:
            initial_turn = initial_turn.get_previous_turn()

        if "victory_count" not in self.data:
            self.data["victory_count"] = int((len([1 for p in provinces if p.has_supply_center]) + 1) / 2)

        # Creates a deepcopy of the game data, and then loads player names and ISCC/VSCC values if needed
        game_data = copy.deepcopy(self.data)
        if self.is_chaos:
            game_data["players"] = {}
            game_data["build_options"] = "anywhere"
        for player in self.players:
            if self.is_chaos or player.name not in game_data["players"]:
                game_data["players"][player.name] = {}
            if "iscc" not in game_data["players"][player.name]:
                game_data["players"][player.name]["iscc"] = \
                    len([1 for p in provinces if p.has_supply_center and p.owner == player])
            if "vscc" not in game_data["players"][player.name]:
                game_data["players"][player.name]["vscc"] = game_data["victory_count"]

        return Board(self.players, provinces, self.unit_types, units, initial_turn, game_data, self.datafile)

    def _build_tiles(self) -> set[Tile]:
        """Creates Tiles for the variant. If they already exist, we can skip this step."""
        if self.tiles is not None:
            return self.tiles

        raw_tiles: set[Tile] = self._create_all_tiles()
        cache: list[str] = []
        tiles: set[Tile] = set()
        for tile in raw_tiles:
            if tile.name in cache:
                logger.warning("%s: %s repeats in map, ignoring...", self.datafile, tile.name)
                continue
            cache.append(tile.name)
            tiles.add(tile)

        if not self.layers["province_labels"]:
            self._initialize_province_names(tiles)

        for tile in tiles:
            self.name_to_tile[tile.name] = tile

        # Sets adjacencies for each tile based on the adjacencies file
        for name1, name2 in self._get_adjacencies(tiles):
            self.name_to_tile[name1].adjacencies.add(self.name_to_tile[name2])
            self.name_to_tile[name2].adjacencies.add(self.name_to_tile[name1])

        # Apply any manual overrides from the config file (e.g. adding adjacencies, multiple coasts, etc.)
        self._json_cheats()

        # Set fleet adjacencies
        for tile in tiles:
            tile.set_coasts()
        # We set land-land fleet adjacencies afterwards, since we need to figure out which adjacencies are valid
        for tile in tiles:
            tile.set_adjacent_coasts()
        self._remove_unit_adjacencies()

        # Set phantom unit coordinates for optimal unit placements
        self._set_phantom_unit_coordinates()

        # Add a default unit coordinate to tiles without one, just in case
        for tile in tiles:
            center = shapely.centroid(tile.geometry)
            center = complex(center.x, center.y) if center else complex(0)
            tile.unit_coordinates["default"] = UnitLocation(center, center)
            for unit in tile.unit_coordinates.keys():
                tile.all_coordinates.setdefault(unit, set()).add(tile.unit_coordinates[unit])

        # Do a pass-through to ensure that SC markers are in the right spot
        self._verify_supply_center_locations()

        self.tiles = tiles
        return tiles

    def _create_all_tiles(self) -> set[Tile]:
        # Creates Tile objects for each province element in the SVG, and stores them in a set.
        # This includes the geometry of the province, its name, and its type.
        # Adjacency, ownership, and other information is added later.
        tiles = set()
        province_types = {"land_layer": ProvinceType.LAND,
                          "island_borders": ProvinceType.ISLAND,
                          "sea_borders": ProvinceType.SEA}
        for layer_name, province_type in province_types.items():
            if (cur_layer := self.layer_data.get(layer_name)) is None:
                continue
            layer_transformation = TransGL3(cur_layer)
            for province_data in list(cur_layer):
                tiles.add(self._create_tile(province_data, province_type, layer_transformation))
        return tiles

    # TODO: (BETA) can a library do all of this for us? more safety from needing to support wild SVG legal syntax
    def _create_tile(
        self,
        province_data: Element,
        province_type: ProvinceType,
        layer_transformation: TransGL3
    ) -> Tile:
        # Given an SVG element for a province, creates a Tile object with the correct geometry and name.
        path_string = province_data.get("d")
        if not path_string:
            logger.error("Province path data not found in province with data %s", tostring(province_data))
            raise RuntimeError("Province path data not found")
        translation = TransGL3(province_data) * layer_transformation

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
                raise RuntimeError(f"Province name not found in province with data {tostring(province_data)}")

        tile = Tile(name, poly, province_type)

        # The starting impassability is static per variant, so it lives on the Tile.
        # Province takes the live value from it and games can change it from there.
        color = get_element_color(province_data)
        if color == self.impassable_color:
            tile.default_impassable = True

        return tile

    # Sets province names given the names layer
    # TODO: Refactor this, probably
    def _initialize_province_names(self, tiles: set[Tile]) -> None:
        def set_province_name(tile: Tile, name_data: etree.Element, _: str | None) -> None:
            if tile.name != "":
                raise RuntimeError(f"Province already has name: {tile.name}")
            new_name = name_data.findall(".//svg:tspan", namespaces=NAMESPACE)[0].text
            assert new_name is not None
            tile.name = new_name

        initialize_province_resident_data(tiles,
                                          list(self.layer_data["names_layer"]),
                                          get_coordinates,
                                          set_province_name)

    # Attempts to get adjacencies from the cache file
    # If one doesn't exist, we go through each pair of provinces and see if they're within a certain distance
    # If they are, we add them to the adjacencies and write that to the cache file for next time
    def _get_adjacencies(self, tiles: set[Tile]) -> set[tuple[str, str]]:
        adjacencies = set()
        try:
            f = open(f"assets/{self.datafile}_adjacencies.txt", "r", encoding="utf-8")
            for line in f:
                adjacencies.add(tuple(line[:-1].split(',')))
        except FileNotFoundError:
            f = open(f"assets/{self.datafile}_adjacencies.txt", "w", encoding="utf-8")
            # Combinations so that we only have (A, B) and not (B, A) or (A, A)
            for tile1, tile2 in itertools.combinations(tiles, 2):
                if shapely.dwithin(tile1.geometry, tile2.geometry, self.layers["border_margin_hint"]):
                    adjacencies.add((tile1.name, tile2.name))
                    f.write(f"{tile1.name},{tile2.name}\n")
        f.close()
        return adjacencies

    def _json_cheats(self):
        if "overrides" not in self.data:
            return

        offset = complex(self.data[SVG_CONFIG_KEY].get("loc_x_offset", 0),
                         self.data[SVG_CONFIG_KEY].get("loc_y_offset", 0))

        for name, data in self.data["overrides"].get("provinces", {}).items():
            tile = self.name_to_tile.get(name)
            if not tile:
                logger.debug("Province %s in overrides not found in map, skipping...", name)
                continue
            # Add/remove adjacencies and coasts
            cheats_list = {
                (command, province)
                for command in data.keys()
                for province in data.get(command)
                if isinstance(province, str)
            }
            for command, province in cheats_list:
                if (target := self.name_to_tile.get(province)) is None:
                    continue
                if command == "adjacencies":
                    tile.adjacencies.add(target)
                elif command == "coastal_adjacencies":
                    tile.adjacencies.add_terrain(target, Terrain.COAST)
                elif command == "remove_adjacencies":
                    tile.adjacencies.remove(target)
                elif command == "difficult_adjacency":
                    if (adj := tile.adjacencies.get(target)) is not None:
                        adj.is_difficult = True
            if "coasts" in data:
                for coast_name, coast_adjacent in data.get("coasts", {}).items():
                    for adjacent_name in coast_adjacent:
                        adj_tile, c = self._get_tile_and_coast(adjacent_name)
                        tile.adjacencies.add_coast(adj_tile, coast_name, c)
            # Add extra unit locations for provinces that wrap around or have weird shapes
            # For compatability reasons, we assume these are sea tiles
            # TODO: Add support for other unit types
            unit_locs = data.get("unit_loc", [])
            retreat_locs = data.get("retreat_unit_loc", [])
            for index, coordinate in enumerate(unit_locs):
                unit_name = coordinate[2] if(len(coordinate) > 2) else "Fleet"
                retreat_coord = retreat_locs[index] if index < len(retreat_locs) else coordinate
                loc = UnitLocation(complex(*coordinate[:2]) + offset, complex(*retreat_coord[:2]) + offset)
                tile.all_coordinates.setdefault(unit_name, set()).add(loc)
                tile.unit_coordinates[unit_name] = loc

    def _remove_unit_adjacencies(self):
        if "overrides" not in self.data:
            return
        for name, data in self.data["overrides"].get("provinces", {}).items():
            tile = self.name_to_tile.get(name)
            if not tile:
                logger.debug("Province %s in overrides not found in map, skipping...", name)
                continue
            for n in data.get("remove_adjacent_coasts", []):
                tile.adjacencies.remove(self.name_to_tile[n], Terrain.COAST)
            for n in data.get("remove_adjacent_land", []):
                tile.adjacencies.remove(self.name_to_tile[n], Terrain.LAND)

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
                tile, coast = self._get_tile_and_coast(self.get_province_name(unit_data))
                coordinate = get_element_unit_coordinates(unit_data)
                translated_coordinate = layer_translation.transform(unit_translation.transform(coordinate))
                tile.set_unit_coordinate(translated_coordinate, unit_type, is_retreat, coast)

    def _verify_supply_center_locations(self) -> None:
        """Warns if any supply center icon sits outside its province's geometry.
        This doesn't break anything, but it can be an indication of a mis-labeled SC."""
        sc_layer_transformation = TransGL3(self.layer_data["supply_center_icons"])
        unit_radius = self.data[SVG_CONFIG_KEY].get("unit_radius", 10)
        for center_data in self.layer_data["supply_center_icons"]:
            name = self.get_province_name(center_data)
            tile = self.name_to_tile.get(name)
            if tile is None or tile.geometry is None:
                continue
            sc_coords = sc_layer_transformation.transform(
                TransGL3(center_data).transform(get_sc_coordinates(center_data)))
            sc_point = shapely.Point(sc_coords.real, sc_coords.imag)
            if not shapely.dwithin(sc_point, tile.geometry, unit_radius):
                logger.warning("%s: Supply center icon for '%s' is not within its province",
                               self.datafile, name)

    def _get_provinces(self, tiles: set[Tile]) -> set[Province]:
        province_map: dict[Tile, Province] = {}
        provinces: set[Province] = set()
        convoyable_islands = self.data.get("convoyable_islands") == "enabled"
        for tile in tiles:
            province = Province(tile, province_map)
            if convoyable_islands and tile.type == ProvinceType.ISLAND:
                province.can_convoy = True
            province_map[tile] = province # All provinces share the same province_map, so it's fine
            self.name_to_province[province.name] = province
            provinces.add(province)

        self._initialize_supply_centers()
        self._initialize_province_owners()

        # set units
        if "starting_units" in self.layer_data and not self.is_chaos:
            self._initialize_units()

        for province in provinces:
            # For Chaos games, remove ownership of non-SC provinces
            if self.is_chaos and not province.has_supply_center:
                province.owner = None
            if province.owner and province.has_supply_center:
                province.owner.centers.add(province)

        return provinces

    def _initialize_supply_centers(self) -> None:
        for center_data in self.layer_data["supply_center_icons"]:
            name = self.get_province_name(center_data)
            province = self.name_to_province[name]

            if province.has_supply_center:
                raise RuntimeError(f"{name} already has a supply center")
            province.has_supply_center = True

            if not self.is_chaos:
                sc_circles = center_data.findall(".//svg:circle", namespaces=NAMESPACE)
                sc_circles.extend(center_data.findall(".//svg:path", namespaces=NAMESPACE))
                if len(sc_circles) > 0:
                    element = next((c for c in sc_circles
                                    if get_element_color(c) not in (None, "none", "000000")), sc_circles[-1])
                else:
                    element = center_data
                core = self._get_element_player(element, province_name=province.name)
                province.core_data.core = core

    def _initialize_province_owners(self) -> None:
        land = self.layer_data.get("land_layer")
        layers: list[Element] = list(land) if land is not None else []
        if (islands := self.layer_data.get("island_fill_layer")) is not None:
            layers.extend(islands)
        for province_data in layers:
            name = self.get_province_name(province_data)
            if self.name_to_tile[name].default_impassable:
                continue
            self.name_to_province[name].owner = self._get_element_player(province_data, province_name=name)

    def _get_element_player(self, element: Element, province_name: str="") -> Player | None:
        color = get_element_color(element)
        if color is not None:
            color = color.lower()
        neutral_color = self.data[SVG_CONFIG_KEY]["neutral"]
        if isinstance(neutral_color, dict):
            neutral_color = neutral_color["standard"]
        neutral_color = neutral_color.lower()
        if self.is_chaos:
            if color in (None, self.impassable_color) or not self.name_to_province[province_name].has_supply_center:
                return None
            if color == neutral_color or color in self.color_to_player:
                color = weighted_random_color(province_name)
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

    def _initialize_units(self) -> None:
        for unit_data in self.layer_data["starting_units"]:
            province_name = self.get_province_name(unit_data)
            if not province_name:
                logger.error("Unit data %s has no province name", tostring(unit_data))
                continue
            if self.data[SVG_CONFIG_KEY]["unit_type_labeled"]:
                province_name = province_name[1:]
            tile, coast = self._get_tile_and_coast(province_name)
            self._set_province_unit(self.name_to_province[tile.name], unit_data, coast)

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

        sides_attr = "{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}sides"
        paths = unit_data.findall(".//svg:path", namespaces=NAMESPACE)
        shape_paths = [path for path in paths if path.get(sides_attr) is not None]
        num_sides = (shape_paths or paths)[-1].get(sides_attr) if paths else None
        if num_sides in data_to_unit:
            return data_to_unit[num_sides]
        return "A"
        # raise RuntimeError(f"Unit has {num_sides} sides which does not match any unit definition.")

    def _get_tile_and_coast(self, province_name: str) -> tuple[Tile, str | None]:
        coast_suffix: str | None = None

        match = COAST_REGEX_PATTERN.match(province_name)
        if match:
            province_name = match.group(1).strip()
            coast_suffix = (match.group(2) or match.group(3)).lower()

        tile = self.name_to_tile[province_name]
        return tile, coast_suffix

    @staticmethod
    def get_province_name(province_data: Element) -> str:
        """Gets the province name from the SVG element, using Inkscape labels."""
        province_name = province_data.get(INKSCAPE_LABEL)
        return province_name or ""

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
