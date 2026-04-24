"""Utility functions for the mapper."""
from __future__ import annotations
import copy
import math
import re
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import ElementTree, Element
import lxml.etree as etree
import numpy as np

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.province import Province
    from DiploGM.models.unit import Unit, UnitType
    from DiploGM.models.player import Player
    from DiploGM.models.turn import Turn

class MapperUtils:
    """Utility functions for the mapper."""
    def __init__(self, board_svg_data: dict[str, Any]):
        self.board_svg_data = board_svg_data

    def create_element(self, tag: str, attributes: dict[str, Any]) -> Element:
        """Creates an XML element with the given tag and attributes."""
        attributes_str = {key: str(val) for key, val in attributes.items()}
        return etree.Element(tag, attributes_str)

    def is_moveable(self,
                    unit: Unit,
                    adjacent_provinces: set[str],
                    player_restriction: str | None,
                    is_retreats: bool = False) -> bool:
        """Checks if a unit is moveable."""
        if unit.province.name not in adjacent_provinces:
            return False
        if player_restriction and unit.player is not None and unit.player.name != player_restriction:
            return False
        if is_retreats and unit.province.dislodged_unit != unit:
            return False
        return True

    def normalize(self, point: complex) -> complex:
        """Normalizes a point to be within the bounds of the map, wrapping horizontally."""
        return complex(point.real % self.board_svg_data["map_width"], point.imag)

    def get_closest_loc(self, possibilities: set[complex], coord: complex) -> complex:
        """Gets the closest point to the given coordinate, accounting for horizontal wrapping of the map."""
        possibilities_list = list(possibilities)
        crossed_pos = []
        crossed = []
        map_width = self.board_svg_data["map_width"]
        for p in possibilities_list:
            x = p.real
            cx = coord.real
            if abs(x - cx) > map_width / 2:
                crossed += [1]
                x += map_width if x < cx else -map_width
            else:
                crossed += [0]
            crossed_pos += [complex(x, p.imag)]

        crossed = np.array(crossed)
        crossed_pos = np.array(crossed_pos)

        dists = np.abs(np.array(crossed_pos) - coord)
        # penalty for crossing map is 500 px
        short_ind = int(np.argmin(dists + 500 * np.array(crossed)))
        return crossed_pos[short_ind]

    def loc_to_point(self, loc: Province, unit_type: UnitType, coast: str | None,
                    current: complex, use_retreats=False) -> complex:
        """Gets the coordinates to draw a unit in a province, given the unit type and coast.
        If there are multiple possibilities, gets the one closest to the current coordinates."""
        # If we're moving to somewhere that's inhabitted, draw to the proper coast
        if loc.unit:
            unit_type = loc.unit.unit_type
            coast = loc.unit.coast

        if coast and coast in loc.all_coordinates:
            coords = loc.all_coordinates[coast]
        elif unit_type.name in loc.all_coordinates:
            coords = loc.all_coordinates[unit_type.name]
        else:
            coords = next(iter(loc.all_coordinates.values()))
        coords = {c.retreat_coordinate if use_retreats else c.primary_coordinate for c in coords}

        return self.get_closest_loc(coords, current)

    def pull_coordinate(
        self,
        anchor: complex,
        coordinate: complex,
        pull=None,
        limit=0.25) -> complex:
        """
        Pull coordinate toward anchor by a small margin to give unit view breathing room. The pull will be limited to be
        no more than the given percent of the distance because otherwise small province size areas are hard to see.
        """
        if pull is None:
            pull = 1.5 * self.board_svg_data["unit_radius"]

        distance = anchor - coordinate
        if abs(distance) == 0:
            return coordinate

        # if the area is small, the pull can become too large of the percent of the total arrow length
        pull = min(pull, abs(distance) * limit)
        return coordinate + pull * distance / abs(distance)

    def add_arrow_definition_to_svg(self,
                                    svg: ElementTree,
                                    board: Board,
                                    player_colors: dict[str, str]) -> None:
        """ Adds arrow marker definitions and half-core gradients to the SVG."""
        defs = svg.find("{http://www.w3.org/2000/svg}defs")
        if defs is None:
            defs = self.create_element("defs", {})
            root = svg.getroot()
            assert root is not None
            root.append(defs)
        # TODO: Check if 'arrow' id is already defined in defs

        arrow_data: dict[str, str] = {
            "id": "arrow",
            "viewbox": "0 0 3 3",
            "refX": "1.5",
            "refY": "1.5",
            "markerWidth": "3",
            "markerHeight": "3",
            "orient": "auto-start-reverse",
        }
        arrow_marker: Element = self.create_element(
            "marker",
            arrow_data
        )
        arrow_path: Element = self.create_element(
            "path",
            {"d": "M 0,0 L 3,1.5 L 0,3 z"},
        )
        arrow_marker.append(arrow_path)
        defs.append(arrow_marker)

        red_arrow_data: dict[str, str] = copy.deepcopy(arrow_data)
        red_arrow_data["id"] = "redarrow"
        red_arrow_marker: Element = self.create_element(
            "marker",
            red_arrow_data
        )
        red_arrow_path: Element = self.create_element(
            "path",
            {"d": "M 0,0 L 3,1.5 L 0,3 z", "fill": "red"},
        )
        red_arrow_marker.append(red_arrow_path)
        defs.append(red_arrow_marker)

        ball_marker_data: dict[str, str] = {
            "id": "ball",
            "viewbox": "0 0 3 3",
            # "refX": "1.5",
            # "refY": "1.5",
            "markerWidth": "3",
            "markerHeight": "3",
            "orient": "auto-start-reverse",
            "shape-rendering": "geometricPrecision", # Needed bc firefox is weird
            "overflow": "visible"
        }
        ball_marker: Element = self.create_element(
            "marker",
            ball_marker_data
        )
        ball_def: Element = self.create_element(
            "circle",
            {"r": "2", "fill": "black"},
        )
        ball_marker.append(ball_def)
        defs.append(ball_marker)

        red_ball_data: dict[str, str] = copy.deepcopy(ball_marker_data)
        red_ball_data["id"] = "redball"
        red_ball_marker: Element = self.create_element(
            "marker",
            red_ball_data
        )
        red_ball_def: Element = self.create_element(
            "circle",
            {"r": "2", "fill": "red"},
        )
        red_ball_marker.append(red_ball_def)
        defs.append(red_ball_marker)

        if board.data.get("build_options") != "cores":
            return
        created_defs = set()

        for province in board.provinces:
            if not province.has_supply_center or province.core_data.half_core is None:
                continue
            mapping = (province.core_data.half_core.name,
                        "None" if province.core_data.core is None else province.core_data.core.name)
            if mapping in created_defs:
                continue

            created_defs.add(mapping)

            gradient_def: Element = self.create_element("linearGradient", {"id": f"{mapping[0]}_{mapping[1]}"})
            first: Element = self.create_element(
                "stop", {"offset": "50%", "stop-color": f"#{player_colors[mapping[0]]}"}
            )
            second: Element = self.create_element(
                "stop", {"offset": "50%", "stop-color": f"#{player_colors[mapping[1]]}"}
            )
            gradient_def.append(first)
            gradient_def.append(second)
            defs.append(gradient_def)

    def color_element(self, element: Element, color: str, key="fill"):
        """Colors a specific element with a given color."""
        if len(color) == 6:  # Potentially buggy hack; just assume everything with length 6 is rgb without #
            color = f"#{color}"
        if element.get(key) is not None:
            element.set(key, color)
        if element.get("style") is not None and key in (element.get("style") or ""):
            style = element.get("style")
            assert style is not None
            style = re.sub(key + r":#[0-9a-fA-F]{6}", f"{key}:{color}", style)
            element.set("style", style)
