"""The Mapper module, for drawing maps with or without orders on them."""
import copy
import itertools
import sys
from xml.etree.ElementTree import ElementTree, Element, register_namespace
from xml.etree.ElementTree import tostring as elementToString

import numpy as np
import lxml.etree as etree

# from diplomacy.adjudicator import utils
# from diplomacy.map_parser.vector import config_svg as svgcfg

from DiploGM.map_parser.vector.utils import (
    clear_svg_element, get_element_color, find_svg_element,
    get_unit_coordinates, get_sc_coordinates, initialize_province_resident_data,
    NAMESPACE, SVG_CONFIG_KEY
)
from DiploGM.db.database import logger
from DiploGM.mapper.order_drawer import OrderDrawer
from DiploGM.mapper.panel import PanelDrawer
from DiploGM.mapper.utils import MapperUtils
from DiploGM.models import turn
from DiploGM.models.board import Board
from DiploGM.models.order import Move, Support, RetreatMove, Build, PlayerOrder
from DiploGM.models.player import Player
from DiploGM.models.province import ProvinceType, Province, UnitLocation
from DiploGM.models.unit import Unit, UnitType

from DiploGM.map_parser.vector.transform import TransGL3
from DiploGM.map_parser.vector.vector import Parser

# if you make any rendering changes,
# make sure to sync them with mapper.js

class Mapper:
    """The main Mapper class."""
    def __init__(self, board: Board, restriction: Player | None = None, color_mode: str | None = None):
        register_namespace('', "http://www.w3.org/2000/svg")
        register_namespace('inkscape', "http://www.inkscape.org/namespaces/inkscape")
        register_namespace('sodipodi', "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")
        register_namespace('xlink', "http://www.w3.org/1999/xlink")


        self.board: Board = board
        self.board_svg_data: dict = board.data[SVG_CONFIG_KEY]
        self.utils = MapperUtils(self.board_svg_data)
        self.current_turn: turn.Turn = board.turn
        self.board_svg: ElementTree = etree.parse(self.board.data["file"])
        self.player_restriction: str | None = restriction.name if restriction else None

        # different colors
        self.replacements: dict | None = self.board_svg_data.get("color replacements")
        self.load_colors(color_mode)
        if color_mode is not None:
            self.replace_colors(color_mode)

        self.panel_drawer = PanelDrawer(self.utils, self.board_svg, self.board, self.player_colors, restriction)

        self.utils.add_arrow_definition_to_svg(self.board_svg, self.board, self.player_colors)

        clear_svg_element(self.board_svg, "starting_units", self.board_svg_data)

        self.cached_elements = {}
        for element_name in ["army", "fleet", "retreat_army", "retreat_fleet", "unit_output", "symbol_templates"]:
            self.cached_elements[element_name] = find_svg_element(
                self.board_svg, element_name, self.board_svg_data
            )

        # Load cached unit symbols if they exist, which we can copy over for fancy units
        self.cached_symbols = {}
        for element in self.cached_elements["symbol_templates"] or []:
            label = element.get(f"{NAMESPACE['inkscape']}label")
            if label in {"Armies", "Fleets"}:
                unit_type = UnitType.ARMY if label == "Armies" else UnitType.FLEET
                self.cached_symbols[unit_type] = {}
                for child in element:
                    child_label = child.get(f"{NAMESPACE['inkscape']}label")
                    if child_label is not None:
                        self.cached_symbols[unit_type][child_label] = child

        visible_provinces = (self.board.get_visible_provinces(restriction)
                             if restriction else self.board.provinces)
        self.adjacent_provinces: set[str] = {p.name for p in visible_provinces}

        # TODO: Switch to passing the SVG directly, as that's simpiler (self.svg = draw_units(svg)?)
        self._draw_units()
        self._color_provinces()
        self._color_centers()
        self.panel_drawer.draw_side_panel(self.board_svg)


        self._moves_svg = copy.deepcopy(self.board_svg)
        self.order_drawer = OrderDrawer(self.utils, self._moves_svg, self.board_svg_data, self.adjacent_provinces)
        self.cached_elements["unit_output_moves"] = find_svg_element(
            self._moves_svg, "unit_output", self.board_svg_data
        )

        self.state_svg = copy.deepcopy(self.board_svg)
        self.clean_layers(self.state_svg)

        self._highlight_retreating_units(self.state_svg)

    def clean_layers(self, svg: ElementTree):
        """Clears layers that we won't need in the final display map."""
        for element_name in self.board_svg_data["delete_layer"]:
            clear_svg_element(svg, element_name, self.board_svg_data)

    def draw_moves_and_retreats(self, arrow_layer: Element, current_turn: turn.Turn, movement_only: bool):
        """Draws move and retreat arrows."""
        units = sorted(self.board.units, key=lambda unit: 0 if unit.order is None else unit.order.display_priority)
        for unit in units:
            if not self.order_drawer.utils.is_moveable(unit,
                                                       self.adjacent_provinces,
                                                       self.player_restriction,
                                                       current_turn.is_retreats()):
                continue

            # Only show moves that succeed if requested
            if movement_only and not (
                isinstance(unit.order, (RetreatMove, Move)) and not unit.order.has_failed):
                continue

            unit_locs = self._get_unit_coordinates(unit, current_turn.is_retreats())

            if unit.order is None and unit.dp_allocations:
                if self.player_restriction is not None and self.player_restriction in unit.dp_allocations:
                    order = unit.dp_allocations[self.player_restriction].order
                elif self.player_restriction is None:
                    order = self.board.get_winning_dp_order(unit)
                else:
                    order = None
            else:
                order = unit.order

            # TODO: Maybe there's a better way to handle convoys?
            if isinstance(order, (RetreatMove, Move, Support)):
                new_locs = []
                dest_coords = order.destination.all_coordinates
                if len(dest_coords) == 0:
                    e_list = [UnitLocation((0, 0), (0, 0))]
                elif order.destination_coast and order.destination_coast in dest_coords:
                    e_list = dest_coords[order.destination_coast]
                elif unit.unit_type.name not in dest_coords:
                    e_list = next(iter(dest_coords.values()))
                else:
                    e_list = dest_coords.get(unit.unit_type.name,
                                             dest_coords.get(UnitType.ARMY.name,
                                                             {UnitLocation((0, 0), (0, 0))}))

                for endpoint in e_list:
                    new_locs += [self.utils.normalize(
                        self.utils.get_closest_loc(unit_locs, endpoint.primary_coordinate))]
                unit_locs = new_locs
            try:
                for loc in unit_locs:
                    val = self.order_drawer.draw_order(unit, order, loc, current_turn)
                    if val is None:
                        continue
                    if not isinstance(val, list):
                        val = [val]
                    for path in val:
                        # if something returns, that means it could potentially go across the edge
                        # copy it 3 times (-1, 0, +1)
                        lval = copy.deepcopy(path)
                        rval = copy.deepcopy(path)
                        lval.attrib["transform"] = f"translate({-self.board.data['svg config']['map_width']}, 0)"
                        rval.attrib["transform"] = f"translate({self.board.data['svg config']['map_width']}, 0)"

                        arrow_layer.append(lval)
                        arrow_layer.append(rval)
                        arrow_layer.append(path)
            except Exception as err:
                logger.error("Drawing move failed for %s", unit, exc_info=err)

    def draw_moves_map(self,
                       current_turn: turn.Turn,
                       player_restriction: Player | None,
                       movement_only: bool = False) -> tuple[bytes, str]:
        """Draws the map with orders.
        If player_restriction is not None, then only show orders for that player.
        If movement_only is True, then only show moves that succeed (no failed moves or supports/convoys)."""
        logger.info("mapper.draw_moves_map")

        self._reset_moves_map()
        self.player_restriction = player_restriction.name if player_restriction else None
        self.order_drawer.player_restriction = self.player_restriction
        self.current_turn = current_turn

        t = self._moves_svg.getroot()
        assert t is not None
        arrow_layer = find_svg_element(self._moves_svg, "arrow_output", self.board_svg_data)
        if arrow_layer is None:
            raise ValueError("Arrow layer not found in SVG")

        if not current_turn.is_builds():
            for unit in self.board.units:
                # Since we draw supports before moves, we need to find convoy routes first
                # so the supports can know where to draw support arrows
                if (isinstance(unit.order, Move)
                    and self.utils.is_moveable(unit, self.adjacent_provinces, self.player_restriction)):
                    self.order_drawer.find_convoy_path(unit.province, unit.order.destination)
            self.draw_moves_and_retreats(arrow_layer, current_turn, movement_only)
        else:
            if self.player_restriction is None or (current_player := self.board.get_player(self.player_restriction)) is None:
                build_orders = {(player, order) for player in self.board.players for order in player.build_orders}
            else:
                build_orders = {(current_player, order) for order in current_player.build_orders}
            for player, build_order in build_orders:
                if isinstance(build_order, PlayerOrder) and build_order.province.name in self.adjacent_provinces:
                    self.order_drawer.draw_player_order(build_order)
                if isinstance(build_order, Build) and build_order.province.name in self.adjacent_provinces:
                    self._draw_unit(
                        Unit(build_order.unit_type, player, build_order.province, build_order.coast),
                        use_moves_svg=True)

        self.panel_drawer.draw_side_panel(self._moves_svg)

        self.clean_layers(self._moves_svg)

        svg_file_name = f"{str(self.board.turn).replace(' ', '_')}_moves_map.svg"
        return elementToString(t, encoding="utf-8"), svg_file_name

    def draw_gui_map(self, current_turn: turn.Turn, player_restriction: Player | None) -> tuple[bytes, str]:
        """Draws the interactive GUI map."""
        self.player_restriction = player_restriction.name if player_restriction else None
        self.order_drawer.player_restriction = self.player_restriction
        self.current_turn = current_turn
        self._reset_moves_map()
        self.clean_layers(self._moves_svg)
        root = self._moves_svg.getroot()
        if root is None:
            raise ValueError("SVG root is None")
        clear_svg_element(self._moves_svg, "sidebar", self.board_svg_data)
        clear_svg_element(self._moves_svg, "power_banners", self.board_svg_data)
        with open("DiploGM/mapper/mapper.js", 'r', encoding='utf-8') as f:
            js = f.read()

        locdict = {}

        for province in self.board.provinces:
            coast = None
            if province.unit:
                unit_type = province.unit.unit_type
                coast = province.unit.coast
            else:
                unit_type = UnitType.FLEET if province.type == ProvinceType.SEA else UnitType.ARMY
            locdict[province.name] = list(province.get_unit_coordinates(unit_type, coast))
            for coast in province.get_multiple_coasts():
                locdict[province.get_name(coast)] = list(province.get_unit_coordinates(UnitType.FLEET, coast))

        script = etree.Element("script")

        coast_to_province = {}
        for province in self.board.provinces:
            for coast in province.get_multiple_coasts():
                coast_to_province[province.get_name(coast)] = province.name

        province_to_unit_type = {}
        for province in self.board.provinces:
            s = None
            if province.name not in self.adjacent_provinces:
                s = '?'
            elif province.unit:
                s = 'f' if province.unit.unit_type == UnitType.FLEET else 'a'
            province_to_unit_type[province.name] = s

        province_to_province_type = {}
        for province in self.board.provinces:
            if province.type == ProvinceType.SEA:
                province_type = 'sea'
            elif province.type == ProvinceType.ISLAND:
                province_type = 'island'
            elif province.type == ProvinceType.LAND:
                province_type = 'land'
            else:
                raise ValueError(f"Unknown province type {province.type} for province {province.name}")
            province_to_province_type[province.name] = province_type

        immediate = [unit.province.get_name(unit.coast)
                     for unit in self.board.units
                     if self.order_drawer.utils.is_moveable(unit, self.adjacent_provinces, self.player_restriction)]

        script.text = js % (str(locdict), self.board_svg_data, coast_to_province,
                            province_to_unit_type, province_to_province_type, immediate)
        root.append(script)

        coasts = find_svg_element(root, "coast_markers", self.board_svg_data)
        def get_text_coordinate(e : etree.Element) -> tuple[float, float]:
            trans = TransGL3(e)
            x, y = e.attrib["x"], e.attrib["y"]
            assert x is not None and y is not None
            return trans.transform(tuple([float(x), float(y)] + np.array([3.25, -3.576 / 2])))

        def match(p: Province, e: Element, _:str | None):
            e.set("onclick", f'obj_clicked(event, "{p} {e[0].text}", false)')
            e.set("oncontextmenu", f'obj_clicked(event, "{p} {e[0].text}", false)')

        if coasts is not None:
            initialize_province_resident_data(self.board.provinces, coasts, get_text_coordinate, match)

        def set_province_supply_center(p: Province, e: Element, _:str | None) -> None:
            e.set("onclick", f'obj_clicked(event, "{p.name}", false)')
            e.set("oncontextmenu", f'obj_clicked(event, "{p.name}", false)')

        supply_center_icons = find_svg_element(root, "supply_center_icons", self.board_svg_data)
        if supply_center_icons is None:
            raise ValueError("Supply center icons layer not found in SVG")
        initialize_province_resident_data(self.board.provinces,
                                          supply_center_icons,
                                          get_sc_coordinates,
                                          set_province_supply_center)

        for layer_name in ("land_layer", "island_borders", "island_ring_layer", "island_fill_layer", "sea_borders"):
            layer = find_svg_element(root, layer_name, self.board_svg_data)
            if layer is None:
                raise ValueError(f"Layer {layer_name} not found in SVG")
            for province_data in layer:
                name = Parser.get_province_name(province_data)
                province_data.set("onclick", f'obj_clicked(event, "{name}", false)')
                province_data.set("oncontextmenu", f'obj_clicked(event, "{name}", false)')


        return elementToString(root, encoding="utf-8"), f"{str(self.board.turn).replace(' ', '_')}_gui.svg"


    def load_colors(self, color_mode: str | None = None) -> None:
        """Loads player colors based on the color mode."""
        self.player_colors = {
            "None": "ffffff",
            "Neutral": self.board_svg_data.get("neutral", "ffffff")
        }
        for player in self.board.players:
            if color_mode is not None and player.color_dict and color_mode in player.color_dict:
                color = player.color_dict[color_mode]
            elif color_mode == "custom":
                color = player.render_color
            else:
                color = player.default_color
            self.player_colors[player.name] = color
        neutral_color = self.board_svg_data.get("neutral", "ffffff")
        if isinstance(neutral_color, dict):
            neutral_color = neutral_color.get(color_mode, neutral_color.get("standard", "ffffff"))
        self.player_colors["Neutral"] = neutral_color

        #TODO: draw dual monarchies as stripes
        if color_mode == "empires":
            for player in self.board.players:
                for vassal in player.vassals or []:
                    self.player_colors[vassal.name] = self.player_colors[player.name]
                    for subvassal in vassal.vassals or []:
                        self.player_colors[subvassal.name] = self.player_colors[player.name]
        elif color_mode == "kingdoms":
            for player in self.board.players:
                if player.liege or not player.vassals:
                    continue
                for vassal in player.vassals:
                    self.player_colors[vassal.name] = self.player_colors[player.name]

        neutral_colors = self.board_svg_data["neutral"]
        if isinstance(neutral_colors, str):
            self.neutral_color = neutral_colors
        else:
            self.neutral_color = neutral_colors.get(color_mode, neutral_colors["standard"])
        impassable_colors = self.board_svg_data.get("impassable", "000000")
        if isinstance(impassable_colors, str):
            self.impassable_color = impassable_colors
        else:
            self.impassable_color = impassable_colors.get(color_mode, impassable_colors["standard"])

        self.clear_seas_color = self.board_svg_data["default_sea_color"]
        if (self.replacements is not None
            and self.clear_seas_color in self.replacements
            and color_mode in self.replacements[self.clear_seas_color]):
            self.clear_seas_color = self.replacements[self.clear_seas_color][color_mode]

    def replace_colors(self, color_mode: str) -> None:
        """Replaces colors in the SVG based on the color mode."""
        if self.replacements is None:
            return
        other_fills = find_svg_element(self.board_svg, "other_fills", self.board_svg_data)
        background = find_svg_element(self.board_svg, "background", self.board_svg_data)
        elements_to_process = []
        if other_fills is not None:
            elements_to_process.extend(other_fills)
        if background is not None:
            elements_to_process.extend(background)
        for element in elements_to_process:
            color = get_element_color(element)
            if color in self.replacements:
                if color_mode in self.replacements[color]:
                    self.utils.color_element(element, self.replacements[color][color_mode])
            elif color_mode == "dark":
                self.utils.color_element(element, "ffffff")



        # Difficult to detect correctly using either geometry or province names
        # Marking manually would work, but for all svgs is time consuming. TODO

        # find_svg_element(self.board_svg, "starting_units", self.board_svg_data)
        # province_names = find_svg_element(self.board_svg, "province_names", self.board_svg_data).getchildren()
        # for text_box in province_names:
        #     try:
        #         text = text_box[0].text.lower()
        #     except:
        #         continue
        #     text = re.sub("[\\s\n]+", " ", text )
        #     if text in self.board.name_to_province:
        #         p = self.board.name_to_province[text]
        #         if p.type == ProvinceType.ISLAND or p.type == ProvinceType.SEA:
        #             self.color_element(text_box, "ffffff")
        #     else:
        #         print(text)

    def draw_current_map(self) -> tuple[bytes, str]:
        """Draws the map without orders"""
        logger.info("mapper.draw_current_map")
        svg_file_name = f"{str(self.board.turn).replace(' ', '_')}_map.svg"
        root = self.state_svg.getroot()
        if root is None:
            raise ValueError("SVG root is None")
        return elementToString(root, encoding="utf-8"), svg_file_name

    def _reset_moves_map(self):
        self._moves_svg = copy.deepcopy(self.board_svg)
        self.order_drawer.moves_svg = self._moves_svg

    def _color_provinces(self) -> None:
        province_layer = find_svg_element(self.board_svg, "land_layer", self.board_svg_data)
        island_fill_layer = find_svg_element(self.board_svg, "island_fill_layer", self.board_svg_data)
        island_ring_layer = find_svg_element(self.board_svg, "island_ring_layer", self.board_svg_data)
        sea_layer = find_svg_element(self.board_svg, "sea_borders", self.board_svg_data)
        island_layer = find_svg_element(self.board_svg, "island_borders", self.board_svg_data)
        if sea_layer is None or province_layer is None:
            raise ValueError("Missing a layer in SVG!")
        island_fill_layer = island_fill_layer if island_fill_layer is not None else []
        island_layer = island_layer if island_layer is not None else []
        island_ring_layer = island_ring_layer if island_ring_layer is not None else []

        visited_provinces: set[str] = set()

        for province_element in itertools.chain(province_layer, island_fill_layer, sea_layer, island_layer):
            try:
                province = self._get_province_from_element_by_label(province_element)
            except ValueError as ex:
                print(f"Error during recoloring provinces: {ex}", file=sys.stderr)
                continue

            visited_provinces.add(province.name)
            if province.is_impassable:
                color = self.impassable_color
            elif province.name not in self.adjacent_provinces:
                color = self.board_svg_data["unknown"]
            elif province_element in (island_layer, sea_layer):
                color = self.clear_seas_color
            else:
                color = self.player_colors[province.owner.name] if province.owner else self.neutral_color

            self.utils.color_element(province_element, color)

        # Try to combine this with the code above? A lot of repeated stuff here
        for island_ring in island_ring_layer:
            try:
                province = self._get_province_from_element_by_label(island_ring)
            except ValueError as ex:
                print(f"Error during recoloring provinces: {ex}", file=sys.stderr)
                continue

            if province.is_impassable:
                color = self.impassable_color
            elif province.name not in self.adjacent_provinces:
                color = self.board_svg_data["unknown"]
            else:
                color = self.player_colors[province.owner.name] if province.owner else self.neutral_color

            self.utils.color_element(island_ring, color, key="stroke")

        for province in self.board.provinces:
            if province.name not in visited_provinces:
                print(f"Warning: Province {province.name} was not recolored by mapper!")

    def _color_centers(self) -> None:
        centers_layer = find_svg_element(self.board_svg, "supply_center_icons", self.board_svg_data)
        if centers_layer is None:
            raise ValueError("Supply Center layer not found in SVG")

        capital_provinces = {self.board.data["players"][player_name]["capital"]
                             for player_name in self.board.data["players"]
                             if "capital" in self.board.data["players"][player_name]}
        capital_marker = centers_layer.find('*[@inkscape:label="Capital Marker"]',
            namespaces={"inkscape": "http://www.inkscape.org/namespaces/inkscape"})
        if capital_marker is not None:
            capital_marker.set("transform", "")

        for center_element in centers_layer:
            try:
                province = self._get_province_from_element_by_label(center_element)
            except ValueError as ex:
                print(f"Error during recoloring centers: {ex}", file=sys.stderr)
                continue

            if not province.has_supply_center:
                print(f"Province {province.name} says it has no supply center, but it does", file=sys.stderr)
                continue

            if province.name not in self.adjacent_provinces:
                core_color = self.board_svg_data["unknown"]
                half_color = core_color
            else:
                core_color = self.player_colors[province.core_data.core.name] if province.core_data.core else "#ffffff"
                half_color = self.player_colors[province.core_data.half_core.name] if province.core_data.half_core else core_color

            corename = "None" if not province.core_data.core else province.core_data.core.name
            halfname = "None" if not province.core_data.half_core else province.core_data.half_core.name
            element_color = f"url(#{halfname}_{corename})" if half_color != core_color else core_color

            for elem in center_element:
                self.utils.color_element(elem, element_color)
            if len(center_element) == 0:
                self.utils.color_element(center_element, element_color)
            if province.name in capital_provinces and capital_marker is not None:
                capital_copy = copy.deepcopy(capital_marker)
                capital_coord = get_sc_coordinates(capital_copy)
                center_coord = get_sc_coordinates(center_element)
                if capital_coord[0] is None or capital_coord[1] is None or center_coord[0] is None or center_coord[1] is None:
                    print(f"Could not find coordinates for capital marker or center {province.name}, skipping translation", file=sys.stderr)
                    continue
                capital_copy.set("transform", f"translate({center_coord[0] - capital_coord[0]}, {center_coord[1] - capital_coord[1]})")
                for elem in capital_copy:
                    if get_element_color(elem) != "000000":
                        self.utils.color_element(elem, element_color)
                centers_layer.append(capital_copy)
        if capital_marker is not None:
            centers_layer.remove(capital_marker)

    def _get_province_from_element_by_label(self, element: Element) -> Province:
        province_name = element.get(f"{NAMESPACE['inkscape']}label")
        if province_name is None:
            raise ValueError(f"Unlabeled element {element}")
        province = self.board.get_province(province_name)
        if province is None:
            raise ValueError(f"Could not find province for label {province_name}")
        return province

    def _draw_units(self) -> None:
        for unit in self.board.units:
            if unit.province.name in self.adjacent_provinces:
                self._draw_unit(unit)

    def _get_unit_coordinates(self, unit: Unit, is_retreats: bool) -> set[tuple[float, float]]:
        province_coordinates = unit.province.all_coordinates
        if unit.coast:
            if unit.coast in province_coordinates:
                return {loc.retreat_coordinate if is_retreats else loc.primary_coordinate
                        for loc in province_coordinates[unit.coast]}
        else:
            if unit.unit_type.name in province_coordinates:
                return {loc.retreat_coordinate if is_retreats else loc.primary_coordinate
                        for loc in province_coordinates[unit.unit_type.name]}

        logger.warning(
            "Could not find coordinates for %s in province %s. Trying to find another coordinate to use",
            unit.unit_type,
            unit.province.name,
        )
        if len(province_coordinates) > 0:
            return {loc.retreat_coordinate if is_retreats else loc.primary_coordinate
                    for loc in next(iter(province_coordinates.values()))}
        logger.warning("No coordinates found for province %s, using (0, 0) as fallback", unit.province.name)
        return {(0, 0)}

    def _draw_unit(self, unit: Unit, use_moves_svg=False):
        player_name = unit.player.name if unit.player else "Neutral"
        if (copied_symbol := self.cached_symbols.get(unit.unit_type, {}).get(player_name)) is not None:
            unit_element = copy.deepcopy(copied_symbol)
        else:
            unit_element = self._get_element_for_unit_type(unit.unit_type)
            for path in unit_element:
                self.utils.color_element(path, self.player_colors[player_name])
        province = unit.province


        current_coords = get_unit_coordinates(unit_element)
        current_coords = TransGL3(unit_element).transform(current_coords)

        coord_list = self._get_unit_coordinates(unit, unit == province.dislodged_unit)

        for desired_coords in coord_list:
            elem = copy.deepcopy(unit_element)

            dx = desired_coords[0] - current_coords[0]
            dy = desired_coords[1] - current_coords[1]

            trans = TransGL3(elem) * TransGL3().init(x_c=dx, y_c=dy)

            elem.set("transform", str(trans))
            p = province.get_name(unit.coast)

            elem.set("onclick", f'obj_clicked(event, "{p}", true)')
            elem.set("oncontextmenu", f'obj_clicked(event, "{p}", true)')

            elem.set("id", province.name)
            elem.set("{http://www.inkscape.org/namespaces/inkscape}label", province.name)

            group = self.cached_elements["unit_output"] if not use_moves_svg else self._moves_svg.getroot()
            assert group is not None
            group.append(elem)

    def _highlight_retreating_units(self, svg):
        for unit in self.board.units:
            if unit == unit.province.dislodged_unit and unit.province.name in self.adjacent_provinces:
                self._draw_retreat_options(unit, svg)

    def _get_element_for_unit_type(self, unit_type) -> Element:
        # Just copy a random phantom unit
        if unit_type == UnitType.ARMY:
            layer: Element = self.cached_elements["army"]
        else:
            layer: Element = self.cached_elements["fleet"]
        return copy.deepcopy(layer[0])

    def _draw_retreat_options(self, unit: Unit, svg):
        root = svg.getroot()
        if not unit.retreat_options:
            self.order_drawer.draw_force_disband(
                None, None, unit.province.get_unit_coordinates(unit.unit_type, unit.coast, True), None, svg)
            return

        # TODO: Move into helper function along with logic in draw_moves_and_retreats
        unit_locs = self._get_unit_coordinates(unit, True)

        for retreat_province, retreat_coast in unit.retreat_options:
            new_locs = []
            if unit.unit_type not in retreat_province.all_coordinates:
                e_list = next(iter(retreat_province.all_coordinates.values()))
            elif retreat_coast:
                e_list = retreat_province.all_coordinates[retreat_coast]
            else:
                e_list = retreat_province.all_coordinates.get(
                    unit.unit_type.name,
                    retreat_province.all_coordinates.get(UnitType.ARMY.name, {UnitLocation((0, 0), (0, 0))}))

            # Unspecified coast, so default to army location
            for endpoint in e_list:
                new_locs += [self.utils.normalize(self.utils.get_closest_loc(unit_locs, endpoint.primary_coordinate))]

            for loc in new_locs:
                root.append(
                    self.order_drawer.draw_retreat_move(
                        unit, RetreatMove(destination=retreat_province,
                                          destination_coast=retreat_coast),
                                          loc, None
                    )[0]
                )
