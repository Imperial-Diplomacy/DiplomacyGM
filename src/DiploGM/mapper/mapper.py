"""The Mapper module, for drawing maps with or without orders on them."""

import copy
import itertools
import sys
from xml.etree.ElementTree import ElementTree, Element, register_namespace
from xml.etree.ElementTree import tostring as elementToString

import lxml.etree as etree

# from diplomacy.adjudicator import utils
# from diplomacy.map_parser.vector import config_svg as svgcfg

from DiploGM.map_parser.vector.utils import (
    clear_svg_element,
    get_element_color,
    find_svg_element,
    get_coordinates,
    get_element_unit_coordinates,
    get_sc_coordinates,
    NAMESPACE,
    SVG_CONFIG_KEY,
)
from DiploGM.db.database import logger
from DiploGM.mapper.order_drawer import OrderDrawer
from DiploGM.mapper.panel import PanelDrawer
import DiploGM.mapper.utils as MapperUtils
from DiploGM.models import turn
from DiploGM.models.board import Board
from DiploGM.models.order import Move, Support, RetreatMove, Build, PlayerOrder
from DiploGM.models.player import Player
from DiploGM.models.province import ProvinceType, Province
from DiploGM.models.unit import Unit, UnitType

from DiploGM.utils.color import oklab_random

from DiploGM.map_parser.vector.transform import TransGL3
from DiploGM.map_parser.vector.vector import Parser

# if you make any rendering changes,
# make sure to sync them with mapper.js


class Mapper:
    """The main Mapper class."""

    def __init__(
        self,
        board: Board,
        **kwargs,
    ):
        register_namespace("", "http://www.w3.org/2000/svg")
        register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")
        register_namespace(
            "sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
        )
        register_namespace("xlink", "http://www.w3.org/1999/xlink")

        self.board: Board = board
        self.board_svg_data: dict = board.data[SVG_CONFIG_KEY]
        self.current_turn: turn.Turn = board.turn
        self.board_svg: ElementTree = etree.parse(self.board.data["file"])
        fow_player = kwargs.get("fow_player")
        self.player_restriction: str | None = fow_player.name if fow_player else None
        restriction = kwargs.get("restriction")

        # different colors
        self.replacements: dict | None = self.board_svg_data.get("color replacements")
        self.color_mode: str | None = kwargs.get("color_mode")
        self.load_colors(kwargs.get("invert_color_mode", False))
        if self.color_mode is not None:
            self.replace_colors("invert" in kwargs)

        # enable sea adjacency layer (oil spills)
        if kwargs.get("oil_spill_mode", False):
            layer = find_svg_element(self.board_svg, "sea_borders", self.board_svg_data)
            if layer:
                MapperUtils.set_element_visibility(layer, visible=True)
            layer = find_svg_element(self.board_svg, "island_borders", self.board_svg_data)
            if layer:
                MapperUtils.set_element_visibility(layer, visible=True)

        if kwargs.get("clean_map_mode", False):
            layers_to_hide = [
                "province_names",
                "supply_center_icons",
                "unit_output",
                "arrow_output",
                "other_fills",
            ]
            for name in layers_to_hide:
                if layer := find_svg_element(self.board_svg, name, self.board_svg_data):
                    MapperUtils.set_element_visibility(layer, visible=False)

        self.panel_drawer = PanelDrawer(
            self.board_svg, self.board, self.player_colors, restriction
        )
        MapperUtils.add_arrow_definition_to_svg(
            self.board_svg, self.board, self.player_colors
        )

        clear_svg_element(self.board_svg, "starting_units", self.board_svg_data)

        self.cached_elements = {}
        cached_layers = ["unit_output", "symbol_templates"]
        unit_type_layers = []
        for unit_type in self.board.unit_types.values():
            unit_type_layers.append(f"{unit_type.name.lower()}")
            unit_type_layers.append(f"retreat_{unit_type.name.lower()}")
        for element_name in cached_layers + unit_type_layers:
            self.cached_elements[element_name] = find_svg_element(
                self.board_svg, element_name, self.board_svg_data
            )

        # Load cached unit symbols if they exist, which we can copy over for fancy units
        self.cached_symbols: dict[str, etree.Element] = {}
        for element in self.cached_elements.get("symbol_templates") or []:
            label = element.get(f"{NAMESPACE['inkscape']}label", " ")
            if (
                unit_type := board.unit_types.get(label[0])
            ) is not None and unit_type.name == label:
                self.cached_symbols[unit_type.code] = {}
                for child in element:
                    child_label = child.get(f"{NAMESPACE['inkscape']}label")
                    if child_label is not None:
                        self.cached_symbols[unit_type.code][child_label] = child
            if label == "Capital":
                self.cached_symbols["capital"] = element

        visible_provinces = (
            self.board.get_visible_provinces(restriction)
            if restriction
            else self.board.provinces
        )
        self.adjacent_provinces: set[str] = {p.name for p in visible_provinces}

        # TODO: Switch to passing the SVG directly, as that's simpiler (self.svg = draw_units(svg)?)
        if not kwargs.get("clean_map_mode", False):
            for unit in [
                unit
                for unit in self.board.units
                if unit.province.name in self.adjacent_provinces
            ]:
                self._draw_unit(unit)
        self._color_provinces(kwargs.get("oil_spill_mode", False))
        self._color_centers()
        self.panel_drawer.draw_side_panel(self.board_svg)

        self._moves_svg = copy.deepcopy(self.board_svg)
        self.order_drawer = OrderDrawer(
            self._moves_svg, self.board_svg_data, self.adjacent_provinces
        )
        self.cached_elements["unit_output_moves"] = find_svg_element(
            self._moves_svg, "unit_output", self.board_svg_data
        )

        self.state_svg = copy.deepcopy(self.board_svg)
        self.clean_layers(self.state_svg)

        self._highlight_retreating_units(self.state_svg)

    def clean_layers(self, svg: ElementTree):
        """Clears layers that we won't need in the final display map."""
        for element_name in self.cached_elements:
            if element_name in ("unit_output", "unit_output_moves"):
                continue
            clear_svg_element(svg, element_name, self.board_svg_data)

    def draw_moves_and_retreats(
        self, arrow_layer: Element, current_turn: turn.Turn, movement_only: bool
    ):
        """Draws move and retreat arrows."""
        units = sorted(
            self.board.units,
            key=lambda unit: 0 if unit.order is None else unit.order.display_priority,
        )
        for unit in units:
            if not MapperUtils.is_moveable(
                unit,
                self.adjacent_provinces,
                self.player_restriction,
                current_turn.is_retreats(),
            ):
                continue

            # Only show moves that succeed if requested
            if movement_only and not (
                isinstance(unit.order, (RetreatMove, Move))
                and not unit.order.has_failed
            ):
                continue

            unit_locs = MapperUtils.get_all_unit_coordinates(
                unit.province,
                unit.unit_type,
                unit.coast,
                retreat=current_turn.is_retreats(),
            )

            if unit.order is None and unit.dp_allocations:
                if (
                    self.player_restriction is not None
                    and self.player_restriction in unit.dp_allocations
                ):
                    order = unit.dp_allocations[self.player_restriction].order
                elif self.player_restriction is None:
                    order = self.board.get_winning_dp_order(unit)
                else:
                    order = None
            else:
                order = unit.order

            # TODO: Maybe there's a better way to handle convoys?
            if isinstance(order, (RetreatMove, Move, Support)):
                dest_coords = MapperUtils.get_all_unit_coordinates(
                    order.destination, unit.unit_type, order.destination_coast
                )
                unit_locs = [
                    MapperUtils.get_closest_loc(
                        unit_locs, endpoint, self.board_svg_data.get("map_width", 0)
                    )
                    for endpoint in dest_coords
                ]
            width = self.board_svg_data.get("map_width", 0)
            for loc in unit_locs:
                val = self.order_drawer.draw_order(unit, order, loc, current_turn)
                if val is None:
                    continue
                if not isinstance(val, list):
                    val = [val]
                for path in val:
                    arrow_layer.append(path)
                    if width == 0:
                        break
                    # if something returns, that means it could potentially go across the edge
                    # copy it 3 times (-1, 0, +1)
                    lval = copy.deepcopy(path)
                    rval = copy.deepcopy(path)
                    lval.attrib["transform"] = f"translate({-width}, 0)"
                    rval.attrib["transform"] = f"translate({width}, 0)"

                    arrow_layer.append(lval)
                    arrow_layer.append(rval)

    def draw_moves_map(
        self,
        current_turn: turn.Turn,
        player_restriction: Player | None,
        movement_only: bool = False,
    ) -> tuple[bytes, str]:
        """Draws the map with orders.
        If player_restriction is not None, then only show orders for that player.
        If movement_only is True, then only show moves that succeed (no failed moves or supports/convoys)."""
        logger.info("mapper.draw_moves_map")

        self._reset_moves_map()
        self.player_restriction = (
            player_restriction.name if player_restriction else None
        )
        self.order_drawer.player_restriction = self.player_restriction
        self.current_turn = current_turn

        t = self._moves_svg.getroot()
        assert t is not None
        arrow_layer = find_svg_element(
            self._moves_svg, "arrow_output", self.board_svg_data
        )
        if arrow_layer is None:
            raise ValueError("Arrow layer not found in SVG")

        if not current_turn.is_builds():
            for unit in self.board.units:
                # Since we draw supports before moves, we need to find convoy routes first
                # so the supports can know where to draw support arrows
                if isinstance(unit.order, Move) and MapperUtils.is_moveable(
                    unit, self.adjacent_provinces, self.player_restriction
                ):
                    self.order_drawer.find_convoy_path(
                        unit.province, unit.order.destination
                    )
            self.draw_moves_and_retreats(arrow_layer, current_turn, movement_only)
        else:
            if (
                self.player_restriction is None
                or (current_player := self.board.get_player(self.player_restriction))
                is None
            ):
                build_orders = {
                    (player, order)
                    for player in self.board.players
                    for order in player.build_orders
                }
            else:
                build_orders = {
                    (current_player, order) for order in current_player.build_orders
                }
            for player, build_order in build_orders:
                if (
                    isinstance(build_order, PlayerOrder)
                    and build_order.province.name in self.adjacent_provinces
                ):
                    self.order_drawer.draw_player_order(build_order)
                if (
                    isinstance(build_order, Build)
                    and build_order.province.name in self.adjacent_provinces
                ):
                    self._draw_unit(
                        Unit(
                            build_order.unit_type,
                            player,
                            build_order.province,
                            build_order.coast,
                        ),
                        use_moves_svg=True,
                    )

        self.panel_drawer.draw_side_panel(self._moves_svg)

        self.clean_layers(self._moves_svg)

        svg_file_name = f"{str(self.board.turn).replace(' ', '_')}_moves_map.svg"
        return elementToString(t, encoding="utf-8"), svg_file_name

    def draw_gui_map(
        self, current_turn: turn.Turn, player_restriction: Player | None
    ) -> tuple[bytes, str]:
        """Draws the interactive GUI map."""
        self.player_restriction = (
            player_restriction.name if player_restriction else None
        )
        self.order_drawer.player_restriction = self.player_restriction
        self.current_turn = current_turn
        self._reset_moves_map()
        self.clean_layers(self._moves_svg)
        root = self._moves_svg.getroot()
        if root is None:
            raise ValueError("SVG root is None")
        sidebar_layer = find_svg_element(
            self._moves_svg, "sidebar", self.board_svg_data
        )
        if sidebar_layer is not None and len(sidebar_layer) > 0:
            sidebar_corner = get_coordinates(sidebar_layer[0])
            trans = TransGL3(sidebar_layer) * TransGL3(sidebar_layer[0])
            order_list_xy = trans.transform(sidebar_corner) + complex(100.0, 20.0)
            order_list = etree.SubElement(
                root,
                "{http://www.w3.org/2000/svg}text",
                {
                    "id": "order_list_textbox",
                    "x": str(order_list_xy.real),
                    "y": str(order_list_xy.imag),
                    "style": "font-size:32px;fill:#000000;font-family:sans-serif",
                },
            )
            anchor = etree.SubElement(
                order_list,
                "{http://www.w3.org/2000/svg}tspan",
                {"x": str(order_list_xy.real), "y": str(order_list_xy.imag)},
            )
            anchor.text = " "

        clear_svg_element(self._moves_svg, "sidebar", self.board_svg_data)
        clear_svg_element(self._moves_svg, "power_banners", self.board_svg_data)
        clear_svg_element(self._moves_svg, "season", self.board_svg_data)

        with open("src/DiploGM/mapper/mapper.js", "r", encoding="utf-8") as f:
            js = f.read()

        locdict = {}

        for province in self.board.provinces:
            coast = None
            if province.unit:
                unit_type = province.unit.unit_type
                coast = province.unit.coast
            else:
                unit_type = (
                    self.board.unit_types["F"]
                    if province.type == ProvinceType.SEA
                    else self.board.unit_types["A"]
                )
            locdict[province.name] = MapperUtils.get_unit_coordinates(
                province, unit_type, coast
            )
            for coast in province.adjacencies.coasts:
                locdict[province.get_name(coast)] = MapperUtils.get_unit_coordinates(
                    province, self.board.unit_types["F"], coast
                )
        locdict = {k: [v.real, v.imag] for k, v in locdict.items()}
        script = etree.Element("script")

        coast_to_province = {}
        for province in self.board.provinces:
            for coast in province.adjacencies.coasts:
                coast_to_province[province.get_name(coast)] = province.name

        province_to_unit_type = {}
        for province in self.board.provinces:
            s = None
            if province.name not in self.adjacent_provinces:
                s = "?"
            elif province.unit:
                s = province.unit.unit_type.code.lower()
            province_to_unit_type[province.name] = s

        province_to_province_type = {}
        for province in self.board.provinces:
            if province.type == ProvinceType.SEA:
                province_type = "sea"
            elif province.type == ProvinceType.ISLAND:
                province_type = "island"
            elif province.type == ProvinceType.LAND:
                province_type = "land"
            else:
                raise ValueError(
                    f"Unknown province type {province.type} for province {province.name}"
                )
            province_to_province_type[province.name] = province_type

        arrow_layer = find_svg_element(
            self._moves_svg, "arrow_output", self.board_svg_data
        )
        if arrow_layer is None:
            raise ValueError("Arrow output layer not found in SVG")

        immediate = [
            unit.province.get_name(unit.coast)
            for unit in self.board.units
            if MapperUtils.is_moveable(
                unit, self.adjacent_provinces, self.player_restriction
            )
        ]

        script.text = js % (
            str(locdict),
            self.board_svg_data,
            coast_to_province,
            province_to_unit_type,
            province_to_province_type,
            repr(arrow_layer.get("id")),
            immediate,
        )
        root.append(script)

        for layer_name in (
            "land_layer",
            "island_borders",
            "island_ring_layer",
            "island_fill_layer",
            "sea_borders",
        ):
            layer = find_svg_element(root, layer_name, self.board_svg_data)
            if layer is None:
                continue
            for province_data in layer:
                name = Parser.get_province_name(province_data)
                province_data.set("onclick", f'obj_clicked(event, "{name}", false)')
                province_data.set(
                    "oncontextmenu", f'obj_clicked(event, "{name}", false)'
                )

        return elementToString(
            root, encoding="utf-8"
        ), f"{str(self.board.turn).replace(' ', '_')}_gui.svg"

    def load_colors(self, invert_color_mode: bool = False) -> None:
        """Loads player colors based on the color mode."""
        self.player_colors = {
            "None": "ffffff",
            "Neutral": self.board_svg_data.get("neutral", "ffffff"),
        }
        for player in self.board.players:
            if (
                self.color_mode is not None
                and player.color_dict
                and self.color_mode in player.color_dict
            ):
                color = player.color_dict[self.color_mode]
            elif self.color_mode == "custom":
                color = self.board.data["players"][player.name].get(
                    "custom_color", player.default_color
                )
            elif self.color_mode == "random":
                color = oklab_random()
            else:
                color = player.default_color
            self.player_colors[player.name] = color.lower()
        neutral_color = self.board_svg_data.get("neutral", "ffffff")
        if isinstance(neutral_color, dict):
            neutral_color = neutral_color.get(
                self.color_mode, neutral_color.get("standard", "ffffff")
            )

        self.player_colors["Neutral"] = neutral_color.lower()

        neutral_colors = self.board_svg_data["neutral"]
        if isinstance(neutral_colors, str):
            self.neutral_color = neutral_colors
        else:
            self.neutral_color = neutral_colors.get(
                self.color_mode, neutral_colors["standard"]
            )
        impassable_colors = self.board_svg_data.get("impassable", "000000")
        if isinstance(impassable_colors, str):
            self.impassable_color = impassable_colors
        else:
            self.impassable_color = impassable_colors.get(
                self.color_mode, impassable_colors["standard"]
            )

        self.clear_seas_color = self.board_svg_data["default_sea_color"]
        if (
            self.replacements is not None
            and self.clear_seas_color in self.replacements
            and self.color_mode in self.replacements[self.clear_seas_color]
        ):
            self.clear_seas_color = self.replacements[self.clear_seas_color][self.color_mode]

        if invert_color_mode:
            self.player_colors = {
                k: MapperUtils.invert_hexcode(v) for k, v in self.player_colors.items()
            }
            self.neutral_color = MapperUtils.invert_hexcode(self.neutral_color)
            self.impassable_color = MapperUtils.invert_hexcode(self.impassable_color)
            self.clear_seas_color = MapperUtils.invert_hexcode(self.clear_seas_color)

    def replace_colors(self, invert_color_mode: bool = False) -> None:
        """Replaces colors in the SVG based on the color mode."""
        if self.replacements is None:
            return
        other_fills = find_svg_element(
            self.board_svg, "other_fills", self.board_svg_data
        )
        background = find_svg_element(self.board_svg, "background", self.board_svg_data)
        elements_to_process = []
        if other_fills is not None:
            elements_to_process.extend(other_fills)
        if background is not None:
            elements_to_process.extend(background)
        for element in elements_to_process:
            color = get_element_color(element) or "ffffff"
            if color in self.replacements:
                if self.color_mode in self.replacements.get(color, {}):
                    color = self.replacements[color][self.color_mode]
            elif self.color_mode == "dark":
                color = "ffffff"

            if invert_color_mode:
                color = MapperUtils.invert_hexcode(color)

            MapperUtils.color_element(element, color)

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

    def _color_provinces(self, oil_spill_mode: bool = False) -> None:
        province_layer = find_svg_element(
            self.board_svg, "land_layer", self.board_svg_data
        )
        island_fill_layer = find_svg_element(
            self.board_svg, "island_fill_layer", self.board_svg_data
        )
        island_ring_layer = find_svg_element(
            self.board_svg, "island_ring_layer", self.board_svg_data
        )
        sea_layer = find_svg_element(self.board_svg, "sea_borders", self.board_svg_data)
        island_layer = find_svg_element(
            self.board_svg, "island_borders", self.board_svg_data
        )
        if sea_layer is None or province_layer is None:
            raise ValueError("Missing a layer in SVG!")
        island_fill_layer = island_fill_layer if island_fill_layer is not None else []
        island_layer = island_layer if island_layer is not None else []
        island_ring_layer = island_ring_layer if island_ring_layer is not None else []

        visited_provinces: set[str] = set()
        sea_elements = set(sea_layer) | set(island_layer)

        for province_element in itertools.chain(
            province_layer, island_fill_layer, sea_layer, island_layer
        ):
            try:
                province = self._get_province_from_element_by_label(province_element)
            except ValueError as ex:
                logger.warning(
                    "[%s] Error during recoloring provinces: %s",
                    self.board.datafile,
                    ex,
                )
                continue

            visited_provinces.add(province.name)
            color = (
                self.player_colors[province.owner.name]
                if province.owner
                else self.neutral_color
            )
            if province.is_impassable:
                color = self.impassable_color
            elif province.name not in self.adjacent_provinces:
                color = self.board_svg_data.get("unknown", "808080")
            elif province_element in sea_elements:
                if not oil_spill_mode or province.owner is None:
                    color = self.clear_seas_color

            MapperUtils.color_element(province_element, color)

        # Try to combine this with the code above? A lot of repeated stuff here
        for island_ring in island_ring_layer:
            try:
                province = self._get_province_from_element_by_label(island_ring)
            except ValueError as ex:
                logger.warning(
                    "[%s] Error during recoloring provinces: %s",
                    self.board.datafile,
                    ex,
                )
                continue

            if province.is_impassable:
                color = self.impassable_color
            elif province.name not in self.adjacent_provinces:
                color = self.board_svg_data.get("unknown", "808080")
            else:
                color = (
                    self.player_colors[province.owner.name]
                    if province.owner
                    else self.neutral_color
                )

            MapperUtils.color_element(island_ring, color, key="stroke")

        for province in self.board.provinces:
            if province.name not in visited_provinces:
                logger.warning(
                    "[%s] Warning: Province %s was not recolored by mapper!",
                    self.board.datafile,
                    province.name,
                )

    def _color_centers(self) -> None:
        centers_layer = find_svg_element(
            self.board_svg, "supply_center_icons", self.board_svg_data
        )
        if centers_layer is None:
            raise ValueError("Supply Center layer not found in SVG")

        capital_provinces = {
            self.board.data["players"][player_name]["capital"]
            for player_name in self.board.data["players"]
            if "capital" in self.board.data["players"][player_name]
        }
        if (capital_marker := self.cached_symbols.get("capital")) is not None:
            capital_marker.set("transform", "")

        for center_element in list(centers_layer):
            try:
                province = self._get_province_from_element_by_label(center_element)
            except ValueError as ex:
                logger.warning(
                    "[%s] Error during recoloring centers: %s", self.board.datafile, ex
                )
                continue

            if not province.has_supply_center:
                logger.warning(
                    "[%s] Province %s says it has no supply center, but it does",
                    self.board.datafile,
                    province.name,
                )
                continue

            core_data = province.core_data
            if province.is_impassable:
                core_color = half_color = self.impassable_color
            elif province.name not in self.adjacent_provinces:
                core_color = half_color = self.board_svg_data.get("unknown", "808080")
            else:
                core_color = (
                    self.player_colors[core_data.core.name]
                    if core_data.core
                    else "#ffffff"
                )
                half_color = (
                    self.player_colors[core_data.half_core.name]
                    if core_data.half_core
                    else core_color
                )

            corename = "None" if not core_data.core else core_data.core.name
            halfname = "None" if not core_data.half_core else core_data.half_core.name
            element_color = (
                f"url(#{halfname}_{corename})"
                if half_color != core_color
                else core_color
            )

            for elem in center_element:
                MapperUtils.color_element(elem, element_color)
            if len(center_element) == 0:
                MapperUtils.color_element(center_element, element_color)
            if province.name in capital_provinces and capital_marker is not None:
                capital_copy = copy.deepcopy(capital_marker)
                translation = TransGL3(center_element).transform(
                    get_sc_coordinates(center_element)
                ) - get_sc_coordinates(capital_copy)
                capital_copy.set(
                    "transform", f"translate({translation.real}, {translation.imag})"
                )
                for elem in capital_copy:
                    if get_element_color(elem) != "000000":
                        MapperUtils.color_element(elem, element_color)
                centers_layer.append(capital_copy)

    def _get_province_from_element_by_label(self, element: Element) -> Province:
        province_name = element.get(f"{NAMESPACE['inkscape']}label")
        if province_name is None:
            raise ValueError(f"Unlabeled element {element}")
        return self.board.get_province(province_name)

    def _draw_unit(self, unit: Unit, use_moves_svg=False):
        player_name = unit.player.name if unit.player else "Neutral"
        if (
            copied_symbol := self.cached_symbols.get(unit.unit_type.code, {}).get(
                player_name
            )
        ) is not None:
            unit_element = copy.deepcopy(copied_symbol)
        else:
            unit_element = self._get_element_for_unit_type(unit.unit_type)
            for path in unit_element:
                MapperUtils.color_element(path, self.player_colors[player_name])
        province = unit.province

        current_coords = get_element_unit_coordinates(unit_element)
        current_coords = TransGL3(unit_element).transform(current_coords)

        coord_list = MapperUtils.get_all_unit_coordinates(
            unit.province, unit.unit_type, unit.coast, unit == province.dislodged_unit
        )

        for desired_coords in coord_list:
            elem = copy.deepcopy(unit_element)
            distance = desired_coords - current_coords

            trans = TransGL3(elem) * TransGL3().init(
                x_c=distance.real, y_c=distance.imag
            )

            elem.set("transform", str(trans))
            p = province.get_name(unit.coast)

            elem.set("onclick", f'obj_clicked(event, "{p}", true)')
            elem.set("oncontextmenu", f'obj_clicked(event, "{p}", true)')

            elem.set("id", province.name)
            elem.set(
                "{http://www.inkscape.org/namespaces/inkscape}label", province.name
            )

            group = (
                self.cached_elements["unit_output"]
                if not use_moves_svg
                else self._moves_svg.getroot()
            )
            assert group is not None
            group.append(elem)

    def _highlight_retreating_units(self, svg):
        for unit in self.board.units:
            if (
                unit == unit.province.dislodged_unit
                and unit.province.name in self.adjacent_provinces
            ):
                self._draw_retreat_options(unit, svg)

    def _get_element_for_unit_type(self, unit_type: UnitType) -> Element:
        # Just copy a random phantom unit
        layer = self.cached_elements[unit_type.name.lower()]
        return copy.deepcopy(layer[0])

    def _draw_retreat_options(self, unit: Unit, svg):
        root = svg.getroot()
        if not unit.retreat_options:
            coordinate = MapperUtils.get_unit_coordinates(
                unit.province, unit.unit_type, unit.coast, True
            )
            self.order_drawer.draw_force_disband(None, None, coordinate, None, svg)
            return

        unit_locs = MapperUtils.get_all_unit_coordinates(
            unit.province, unit.unit_type, unit.coast, True
        )

        for retreat_province, retreat_coast in unit.retreat_options:
            dest_coords = MapperUtils.get_all_unit_coordinates(
                retreat_province, unit.unit_type, retreat_coast
            )
            new_locs = [
                MapperUtils.get_closest_loc(
                    unit_locs, endpoint, self.board_svg_data.get("map_width", 0)
                )
                for endpoint in dest_coords
            ]

            for loc in new_locs:
                root.append(
                    self.order_drawer.draw_retreat_move(
                        unit,
                        RetreatMove(
                            destination=retreat_province,
                            destination_coast=retreat_coast,
                        ),
                        loc,
                        None,
                    )[0]
                )
