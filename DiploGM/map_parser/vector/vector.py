import copy
import itertools
import json
import logging
import time
import numpy as np
from xml.etree.ElementTree import Element, tostring

import shapely
from lxml import etree

from DiploGM.map_parser.vector.transform import TransGL3
from DiploGM.map_parser.vector.utils import get_element_color, get_unit_coordinates, get_svg_element, parse_path, initialize_province_resident_data
from DiploGM.models.turn import Turn
from DiploGM.models.board import Board
from DiploGM.models.player import Player
from DiploGM.models.province import Province, ProvinceType
from DiploGM.models.unit import Unit, UnitType

# TODO: (BETA) all attribute getting should be in utils which we import and call utils.my_unit()
# TODO: (BETA) consistent in bracket formatting
NAMESPACE: dict[str, str] = {
    "inkscape": "{http://www.inkscape.org/namespaces/inkscape}",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
    "svg": "http://www.w3.org/2000/svg",
}

logger = logging.getLogger(__name__)


class Parser:
    def __init__(self, data: str):
        self.datafile = data



        with open(f"variants/{data}/config.json", "r") as f:
            self.data = json.load(f)

        self.data["file"] = f"variants/{data}/{self.data['file']}"

        svg_root = etree.parse(self.data["file"])

        self.layers = self.data["svg config"]
        self.layer_data: dict[str, Element] = {}

        for layer in ["land_layer", "island_borders", "island_fill_layer",
                       "sea_borders", "province_names", "supply_center_icons",
                       "army", "retreat_army", "fleet", "retreat_fleet"]:
            l = get_svg_element(svg_root, self.layers[layer])
            if l is None:
                raise ValueError(f"Layer {layer} not found in SVG")
            self.layer_data[layer] = l

        if self.layers["detect_starting_units"]:
            starting_units = get_svg_element(svg_root, self.layers["starting_units"])
            if starting_units is None:
                raise ValueError("Starting_units layer expected but not found in SVG")
            else:
                self.layer_data["starting_units"] = starting_units

        if "impassibles_layer" in self.layers:
            impassibles_layer = get_svg_element(svg_root, self.layers["impassibles_layer"])
            if impassibles_layer is None:
                raise ValueError(f"Layer impassibles_layer not found in SVG")
            self.layer_data["impassibles_layer"] = impassibles_layer

        self.fow = self.layers.get("fow", False)
        self.year_offset = self.layers.get("year", 1642)

        self.color_to_player: dict[str, Player | None] = {}
        self.name_to_province: dict[str, Province] = {}

        self.cache_provinces: set[Province] | None = None
        self.cache_adjacencies: set[tuple[str, str]] | None = None

    def parse(self) -> Board:
        logger.debug("map_parser.vector.parse.start")
        start = time.time()

        self.players = set()

        self.autodetect_players = self.data["players"] == "chaos"

        if not self.autodetect_players:
            for name, data in self.data["players"].items():
                color = data["color"]
                win_type = self.data["victory_conditions"]
                if win_type == "classic":
                    sc_goal = self.data["victory_count"]
                    starting_scs = data["starting_scs"]
                else:
                    sc_goal = data["vscc"]
                    starting_scs = data["iscc"]
                player = Player(name, color, win_type, sc_goal, starting_scs, set(), set())
                self.players.add(player)
                if isinstance(color, dict):
                    color = color["standard"]
                self.color_to_player[color] = player

            neutral_colors = self.data["svg config"]["neutral"]
            if isinstance(neutral_colors, dict):
                self.color_to_player[neutral_colors["standard"]] = None
            else:
                self.color_to_player[neutral_colors] = None
            self.color_to_player[self.data["svg config"]["neutral_sc"]] = None

        provinces = self._get_provinces()

        units = set()
        for province in provinces:
            unit = province.unit
            if unit:
                units.add(unit)

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
            for coast in province.get_multiple_coasts():
                if province.get_primary_unit_coordinates(UnitType.FLEET, coast) == (0, 0):
                    logger.warning(f"{self.datafile}: Province {province.get_name(coast)} has no fleet coord. Setting to 0,0 ...")
                    province.set_unit_coordinate(None, True, UnitType.FLEET, coast)
                if province.get_retreat_unit_coordinates(UnitType.FLEET, coast) == (0, 0):
                    logger.warning(f"{self.datafile}: Province {province.get_name(coast)} has no fleet retreat coord. Setting to 0,0 ...")
                    province.set_unit_coordinate(None, False, UnitType.FLEET, coast)
            if not province.get_multiple_coasts() and province.get_coastal_adjacent():
                if province.get_primary_unit_coordinates(UnitType.FLEET) == (0, 0):
                    logger.warning(f"{self.datafile}: Province {province.name} has no fleet coord. Setting to 0,0 ...")
                    province.set_unit_coordinate(None, True, UnitType.FLEET)
                if province.get_retreat_unit_coordinates(UnitType.FLEET) == (0, 0):
                    logger.warning(f"{self.datafile}: Province {province.name} has no fleet retreat coord. Setting to 0,0 ...")
                    province.set_unit_coordinate(None, False, UnitType.FLEET)
            if province.type != ProvinceType.SEA:
                if province.get_primary_unit_coordinates(UnitType.ARMY) == (0, 0):
                    logger.warning(f"{self.datafile}: Province {province.name} has no army coord. Setting to 0,0 ...")
                    province.set_unit_coordinate(None, True, UnitType.ARMY)
                if province.get_retreat_unit_coordinates(UnitType.ARMY) == (0, 0):
                    logger.warning(f"{self.datafile}: Province {province.name} has no army retreat coord. Setting to 0,0 ...")
                    province.set_unit_coordinate(None, False, UnitType.ARMY)
        
        initial_turn = Turn(self.year_offset, "Spring Moves", self.year_offset)
        if "adju flags" in self.data and "initial builds" in self.data["adju flags"]:
            initial_turn = initial_turn.get_previous_turn()

        return Board(self.players, provinces, units, initial_turn, self.data, self.datafile, self.fow, self.year_offset)

    def read_map(self) -> tuple[set[Province], set[tuple[str, str]]]:
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
        for province in provinces:
            self.name_to_province[province.name] = province

        if self.cache_adjacencies is None:
            # set adjacencies
            self.cache_adjacencies = self._get_adjacencies(provinces)
        adjacencies = copy.deepcopy(self.cache_adjacencies)

        return (provinces, adjacencies)

    def names_to_provinces(self, names: set[str]):
        provinces = set()
        for n in names:
            p, c = self._get_province_and_coast(n)
            if c:
                provinces.add((p, c))
            else:
                provinces.add(p)
        return provinces

    def add_province_to_board(self, provinces: set[Province], province: Province) -> set[Province]:
        provinces = {x for x in provinces if x.name != province.name}
        provinces.add(province)
        self.name_to_province[province.name] = province
        return provinces

    def json_cheats(self, provinces: set[Province]) -> set[Province]:
        if "overrides" not in self.data:
            return set()
        if "high provinces" in self.data["overrides"]:
            for name, data in self.data["overrides"]["high provinces"].items():
                high_provinces: list[Province] = []
                for index in range(1, data["num"] + 1):
                    province = Province(
                        name + str(index),
                        shapely.Polygon(),
                        dict(),
                        dict(),
                        getattr(ProvinceType, data["type"]),
                        False,
                        set(),
                        set(),
                        None,
                        None,
                        None,
                    )
                    provinces = self.add_province_to_board(provinces, province)
                    high_provinces.append(province)

                # Add connections between each high province
                for provinceA in high_provinces:
                    for provinceB in high_provinces:
                        if provinceA.name != provinceB.name:
                            provinceA.adjacent.add(provinceB)

            for name, data in self.data["overrides"]["high provinces"].items():
                adjacent = set(self.names_to_provinces(data["adjacencies"]))
                for index in range(1, data["num"] + 1):
                    high_province = self.name_to_province[name + str(index)]
                    high_province.adjacent.update(adjacent)
                    for ad in adjacent:
                        ad.adjacent.add(high_province)

        x_offset = 0
        y_offset = 0

        if "loc_x_offset" in self.data["svg config"]:
            x_offset = self.data["svg config"]["loc_x_offset"]
        
        if "loc_y_offset" in self.data["svg config"]:
            x_offset = self.data["svg config"]["loc_y_offset"]

        offset = np.array([x_offset, y_offset])

        if "provinces" in self.data["overrides"]:
            for name, data in self.data["overrides"]["provinces"].items():
                province = self.name_to_province[name]
                # TODO: Some way to specify whether or not to clear other adjacencies?
                if "adjacencies" in data:
                    province.adjacent.update(self.names_to_provinces(data["adjacencies"]))
                if "remove_adjacencies" in data:
                    province.adjacent.difference_update(self.names_to_provinces(data["remove_adjacencies"]))
                if "remove_adjacent_coasts" in data:
                    province.nonadjacent_coasts.update(data["remove_adjacent_coasts"])
                if "coasts" in data:
                    province.fleet_adjacent = {}
                    for coast_name, coast_adjacent in data["coasts"].items():
                        province.fleet_adjacent[coast_name] = set(self.names_to_provinces(coast_adjacent))
                if "unit_loc" in data:
                    # For compatability reasons, we assume these are sea tiles
                    # TODO: Add support for armies/multicoastal tiles
                    for coordinate in data["unit_loc"]:
                        coordinate = tuple((tuple(coordinate) + offset).tolist())
                        if UnitType.FLEET not in province.all_locs:
                            province.all_locs[UnitType.FLEET] = {coordinate}
                        else:
                            province.all_locs[UnitType.FLEET].add(coordinate)
                        province.primary_unit_coordinates[UnitType.FLEET] = coordinate
                if "retreat_unit_loc" in data:
                    for coordinate in data["retreat_unit_loc"]:
                        coordinate = tuple((tuple(coordinate) + offset).tolist())
                        if UnitType.FLEET not in province.all_rets:
                            province.all_rets[UnitType.FLEET] = {coordinate}
                        else:
                            province.all_rets[UnitType.FLEET].add(coordinate)
                        province.retreat_unit_coordinates[UnitType.FLEET] = coordinate

        return provinces

    def _get_provinces(self) -> set[Province]:
        provinces, adjacencies = self.read_map()
        for name1, name2 in adjacencies:
            province1 = self.name_to_province[name1]
            province2 = self.name_to_province[name2]
            province1.set_adjacent(province2)
            province2.set_adjacent(province1)

        provinces = self.json_cheats(provinces)

        # set coasts
        for province in provinces:
            province.set_coasts()

        for province in provinces:
            province.set_adjacent_coasts()

        # impassible provinces aren't in the list; they're "ghost" and only show up
        # when explicitly asked for in costal topology algorithms
        provinces = {p for p in provinces if p.type != ProvinceType.IMPASSIBLE}

        self._initialize_province_owners(self.layer_data["land_layer"])
        self._initialize_province_owners(self.layer_data["island_fill_layer"])

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

        # TODO: There's a better way to do this
        for province in provinces:
            for unit in province.primary_unit_coordinates.keys():
                if unit not in province.all_locs:
                    province.all_locs[unit] = {province.primary_unit_coordinates[unit]}
                else:
                    province.all_locs[unit].add(province.primary_unit_coordinates[unit])
  
                if unit not in province.all_rets:
                    province.all_rets[unit] = {province.retreat_unit_coordinates[unit]}
                else:
                    province.all_rets[unit].add(province.retreat_unit_coordinates[unit])

        return provinces

    def _get_province_coordinates(self) -> set[Province]:
        # TODO: (BETA) don't hardcode translation
        land_provinces = self._create_provinces_type(self.layer_data["land_layer"], ProvinceType.LAND)
        island_provinces = self._create_provinces_type(self.layer_data["island_borders"], ProvinceType.ISLAND)
        sea_provinces = self._create_provinces_type(self.layer_data["sea_borders"], ProvinceType.SEA)
        # detect impassible to allow for better understanding
        # of coastlines
        # they don't go in board.provinces
        impassible_provinces = set()
        if self.layer_data.get("impassibles_layer") is not None:
            impassible_provinces = self._create_provinces_type(self.layer_data["impassibles_layer"], ProvinceType.IMPASSIBLE)
        return land_provinces | island_provinces | sea_provinces | impassible_provinces

    # TODO: (BETA) can a library do all of this for us? more safety from needing to support wild SVG legal syntax
    def _create_provinces_type(
        self,
        provinces_layer: Element,
        province_type: ProvinceType,
    ) -> set[Province]:
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
                #     print(f"MULTIPOLYGON IS NOT VALID (name: {self._get_province_name(province_data)})")
                #     for subpoly in poly.geoms:
                #         plt.plot(*subpoly.exterior.xy)
                #     plt.show()

            province_coordinates = shapely.MultiPolygon()

            name = None
            if self.layers["province_labels"]:
                name = self._get_province_name(province_data)
                if name == None:
                    raise RuntimeError(f"Province name not found in province with data {province_data}")

            province = Province(
                name,
                poly,
                dict(),
                dict(),
                province_type,
                False,
                set(),
                set(),
                None,
                None,
                None,
            )

            provinces.add(province)
        return provinces

    def _initialize_province_owners(self, provinces_layer: Element) -> None:
        for province_data in list(provinces_layer):
            name = self._get_province_name(province_data)
            self.name_to_province[name].owner = self.get_element_player(province_data, province_name=name)

    # Sets province names given the names layer
    def _initialize_province_names(self, provinces: set[Province]) -> None:
        def get_coordinates(name_data: Element) -> tuple[float, float]:
            return float(name_data.get("x")), float(name_data.get("y"))

        def set_province_name(province: Province, name_data: Element, _: str | None) -> None:
            if province.name is not None:
                raise RuntimeError(f"Province already has name: {province.name}")
            province.name = name_data.findall(".//svg:tspan", namespaces=NAMESPACE)[0].text

        initialize_province_resident_data(provinces, list(self.layer_data["names_layer"]), get_coordinates, set_province_name)

    def _initialize_supply_centers_assisted(self) -> None:
        for center_data in list(self.layer_data["supply_center_icons"]):
            name = self._get_province_name(center_data)
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
            province.core = core

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

        initialize_province_resident_data(provinces, self.layer_data["supply_center_icons"], get_coordinates, set_province_supply_center)

    def _set_province_unit(self, province: Province, unit_data: Element, coast: str | None = None) -> None:
        if province.unit:
            return
            raise RuntimeError(f"{province.name} already has a unit")

        unit_type = self._get_unit_type(unit_data)

        # assume that all starting units are on provinces colored in to their color
        player = province.owner
        if player is None:
            raise Exception(f"{province.name} has a unit, but isn't owned by any country")

        # color_data = unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0]
        # player = self.get_element_player(color_data)

        unit = Unit(unit_type, player, province, coast, None)
        province.unit = unit
        unit.player.units.add(unit)
        return

    def _initialize_units_assisted(self) -> None:
        for unit_data in self.layer_data["starting_units"]:
            province_name = self._get_province_name(unit_data)
            if self.data["svg config"]["unit_type_labeled"]:
                province_name = province_name[1:]
            province, coast = self._get_province_and_coast(province_name)
            self._set_province_unit(province, unit_data, coast)

    # Sets province unit values
    def _initialize_units(self, provinces: set[Province]) -> None:
        def get_coordinates(unit_data: Element) -> tuple[float | None, float | None]:
            base_coordinates = tuple(
                map(float, unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0].get("d").split()[1].split(","))
            )
            trans = TransGL3(unit_data)
            return trans.transform(base_coordinates)

        initialize_province_resident_data(provinces, self.layer_data["starting_units"], get_coordinates, self._set_province_unit)

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
                province.set_unit_coordinate(layer_translation.transform(unit_translation.transform(coordinate)), is_primary, UnitType.ARMY)

        fleet_layer_to_key = [
            (self.layer_data["fleet"], True),
            (self.layer_data["retreat_fleet"], False),
        ]
        for layer, is_primary in fleet_layer_to_key:

            layer_translation = TransGL3(layer)
            for unit_data in list(layer):
                unit_translation = TransGL3(unit_data)
                # This could either be a sea province or a land coast
                province_name = self._get_province_name(unit_data)
                # this is me writing bad code to get this out faster, will fix later when we clean up this file
                province, coast = self._get_province_and_coast(province_name)
                coordinate = get_unit_coordinates(unit_data)
                translated_coordinate = layer_translation.transform(unit_translation.transform(coordinate))
                province.set_unit_coordinate(translated_coordinate, is_primary, UnitType.FLEET, coast)

    @staticmethod
    def _get_province_name(province_data: Element) -> str:
        return province_data.get(f"{NAMESPACE.get('inkscape')}label")

    def _get_province(self, province_data: Element) -> Province:
        return self.name_to_province[self._get_province_name(province_data)]

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
            f = open(f"assets/{self.datafile}_adjacencies.txt", "r")
        except FileNotFoundError:
            f = open(f"assets/{self.datafile}_adjacencies.txt", "w")
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
        #FIXME: only works if there's one person per province
        if self.autodetect_players:
            neutral_color = self.data["svg config"]["neutral"]
            if isinstance(neutral_color, dict):
                neutral_color = neutral_color["standard"]
            if color is None or color == neutral_color:
                return None
            player = Player(province_name, color, "chaos", 101, 1, set(), set())
            self.players.add(player)
            self.color_to_player[color] = player
            return player
        elif color in self.color_to_player:
           return self.color_to_player[color]
        else:
            raise Exception(f"Unknown player color: {color} (in object {tostring(element)})")

    def _get_unit_type(self, unit_data: Element) -> UnitType:
        if self.data["svg config"]["unit_type_labeled"]:
            name = self._get_province_name(unit_data)
            if name is None:
                raise RuntimeError("Unit has no name, but unit_type_labeled = true")
            if name.lower().startswith("f"):
                return UnitType.FLEET
            if name.lower().startswith("a"):
                return UnitType.ARMY
            else:
                raise RuntimeError(f"Unit types are labeled, but {name} doesn't start with F or A")

        if "unit_type_from_names" in self.data["svg config"] and self.data["svg config"]["unit_type_from_names"]:
            # unit_data = unit_data.findall(".//svg:path", namespaces=NAMESPACE)[0]
            name = unit_data[1].get(f"{NAMESPACE.get('inkscape')}label")
            if name.lower().startswith("sail"):
                return UnitType.FLEET
            if name.lower().startswith("shield"):
                return UnitType.ARMY
            else:
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


def get_parser(name: str) -> Parser:
    if name not in parsers:
        logger.info(f"Creating new Parser for board named {name}")
        parsers[name] = Parser(name)
    return parsers[name]


# oneTrueParser = Parser()
