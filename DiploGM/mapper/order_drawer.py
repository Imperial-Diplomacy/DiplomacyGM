"""Module to draw orders (moves, support, etc.) on the map."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import ElementTree
import numpy as np

from DiploGM.db.database import logger
from DiploGM.models.order import (
    Hold, Core, Transform, Move, Support, ConvoyTransport,
    Build, Disband, TransformBuild, RetreatMove, RetreatDisband
)
from DiploGM.models.unit import UnitType
import DiploGM.mapper.utils as MapperUtils

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element
    from DiploGM.models.province import Province
    from DiploGM.models.unit import Unit
    from DiploGM.models.turn import Turn
    from DiploGM.models.order import UnitOrder, PlayerOrder

class OrderDrawer:
    """Class to draw orders on the map."""
    def __init__(self,
                 moves_svg: ElementTree,
                 board_svg_data: dict[str, Any],
                 adjacent_provinces: set[str],
                 player_restriction: str | None = None):
        self.moves_svg: ElementTree = moves_svg
        self.board_svg_data = board_svg_data
        self.adjacent_provinces = adjacent_provinces
        self.player_restriction = player_restriction
        self.convoy_paths: dict[Province, list[list[Province]]] = {}

    def draw_order(self,
                   unit: Unit,
                   order: UnitOrder | None,
                   coordinate: complex,
                   current_turn: Turn) -> list[Element] | None:
        """Draws a specific order on the map.
        If the order can potentially go off-board (i.e. move/support),
        return a list of elements to be copied across the board."""
        function_list = {Hold: self._draw_hold,
                         Core: self._draw_core,
                         Transform: self._draw_transform,
                         Move: self._draw_convoyed_move,
                         Support: self._draw_support,
                         ConvoyTransport: self._draw_convoy,
                         RetreatMove: self.draw_retreat_move,
                         RetreatDisband: self.draw_force_disband}

        order_function = function_list.get(type(order), None)
        if order_function is None:
            logger.debug("None order found: %s drawn. Coordinates: %s",
                         'hold' if current_turn.is_moves() else 'disband', coordinate)
            order_function = self._draw_hold if current_turn.is_moves() else self.draw_force_disband
        # Unit and order are optional and are _ or __ in the definitions of functions that don't need them
        return order_function(unit, order, coordinate, order.has_failed if order else False)

    def draw_player_order(self, order: PlayerOrder) -> None:
        """Draws a Player Order (e.g. build, disband, etc.) on the map."""
        if isinstance(order, Build):
            self._draw_build(order)
        elif isinstance(order, Disband):
            assert order.province.unit is not None
            disbanding_unit: Unit = order.province.unit
            if disbanding_unit.coast:
                coord_list = order.province.all_coordinates[disbanding_unit.coast]
            else:
                coord_list = order.province.all_coordinates[disbanding_unit.unit_type.name]
            for coord in coord_list:
                self.draw_force_disband(None, None, coord.primary_coordinate, None, self.moves_svg)
        elif isinstance(order, TransformBuild):
            assert order.province.unit is not None
            transforming_unit: Unit = order.province.unit
            if transforming_unit.coast:
                coord_list = order.province.all_coordinates[transforming_unit.coast]
            else:
                coord_list = order.province.all_coordinates[transforming_unit.unit_type.name]
            for coord in coord_list:
                self._draw_transform(None, None, coord.primary_coordinate, False)
        else:
            logger.error("Could not draw player order %s", order)

    def _draw_hold(self, _, __, coordinate: complex, has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = MapperUtils.create_element(
            "circle",
            {
                "cx": coordinate.real,
                "cy": coordinate.imag,
                "r": self.board_svg_data["unit_radius"],
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def _draw_core(self, _, __, coordinate: complex, has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = MapperUtils.create_element(
            "rect",
            {
                "x": coordinate.real - self.board_svg_data["unit_radius"],
                "y": coordinate.imag - self.board_svg_data["unit_radius"],
                "width": self.board_svg_data["unit_radius"] * 2,
                "height": self.board_svg_data["unit_radius"] * 2,
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-width": self.board_svg_data["order_stroke_width"],
                "transform": f"rotate(45 {coordinate.real} {coordinate.imag})",
            },
        )
        element.append(drawn_order)

    def _draw_transform(self, _, __, coordinate: complex, has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = MapperUtils.create_element(
            "rect",
            {
                "x": coordinate.real - self.board_svg_data["unit_radius"],
                "y": coordinate.imag - self.board_svg_data["unit_radius"],
                "width": self.board_svg_data["unit_radius"] * 2,
                "height": self.board_svg_data["unit_radius"] * 2,
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def draw_retreat_move(self, unit: Unit,
                          order: RetreatMove,
                          coordinate: complex,
                          _) -> list[Element]:
        """Draws a retreat move on the map, returning the elements to be copied across the board if necessary.
        This is a public method since we need to draw potential retreats on the current map."""
        destination = MapperUtils.loc_to_point(order.destination,
                                               unit.unit_type,
                                               order.destination_coast,
                                               coordinate,
                                               self.board_svg_data["map_width"])
        if order.destination.unit:
            destination = MapperUtils.pull_coordinate(coordinate,
                                                      destination,
                                                      1.5 * self.board_svg_data["unit_radius"])
        order_path = MapperUtils.create_element(
            "path",
            {
                "d": f"M {coordinate.real},{coordinate.imag} L {destination.real},{destination.imag}",
                "fill": "none",
                "stroke": "red",
                "stroke-width": self.board_svg_data["order_stroke_width"],
                "stroke-linecap": "round",
                "marker-end": "url(#redarrow)",
            },
        )
        return [order_path]

    def _path_helper(
        self, source: Province, destination: Province, current: Province, already_checked=()
    ) -> list[list[Province]]:
        if current in already_checked:
            return []
        options = []
        new_checked = already_checked + (current,)
        for possibility in current.adjacency_data.adjacent:
            if possibility.name not in self.adjacent_provinces:
                continue

            if possibility == destination:
                options += [[destination]]
                continue
            if (unit := possibility.unit) is None:
                continue
            is_convoying_fleet = (
                possibility.can_convoy
                and unit is not None
                and unit.unit_type == UnitType.FLEET
                and isinstance(unit.order, ConvoyTransport)
                and unit.order.source == source
                and unit.order.destination == destination
            )
            if (self.player_restriction is not None
                and (unit.player is None or unit.player.name != self.player_restriction)):
                continue # Don't draw if the player doesn't know that fleet is convoying
            if is_convoying_fleet:
                options += self._path_helper(source, destination, possibility, new_checked)
        return list(map((lambda t: [current] + t), options))

    def _draw_path(self, d: str, marker_end="arrow", stroke_color="black") -> Element:
        order_path = MapperUtils.create_element(
            "path",
            {
                "d": d,
                "fill": "none",
                "stroke": stroke_color,
                "stroke-width": self.board_svg_data["order_stroke_width"],
                "stroke-linecap": "round",
                "marker-end": f"url(#{marker_end})",
            },
        )
        return order_path

    def find_convoy_path(self, start: Province, end: Province) -> list[list[Province]]:
        """Finds convoy paths between two provinces, if they exist. Caches results.
        We need to do this before drawing anything, as otherwise supports won't know where to draw to."""
        valid_convoys = self._path_helper(start, end, start)
        if valid_convoys:
            if len(valid_convoys) > 1 and [start, end] in valid_convoys:
                valid_convoys.remove([start, end])
        else:
            valid_convoys = [[start, end]]
        valid_convoys.sort(key = len)
        shortest_convoys: list[list[Province]] = []
        for convoy in valid_convoys:
            if not any(set(shortest).issubset(convoy) for shortest in shortest_convoys):
                shortest_convoys.append(convoy)
        self.convoy_paths[start] = shortest_convoys
        return shortest_convoys

    def _draw_convoyed_move(self,
                            unit: Unit,
                            order: Move,
                            coordinate: complex,
                            has_failed: bool) -> list[Element]:
        def f(point: complex):
            return f"{point.real},{point.imag}"

        valid_convoys = self.convoy_paths.get(unit.province, [[unit.province, order.destination]])
        latest_paths = []
        for path in valid_convoys:
            p = [coordinate]
            start = coordinate
            for loc in path[1:]:
                p += [MapperUtils.loc_to_point(loc, unit.unit_type, order.destination_coast, start, self.board_svg_data["map_width"])]
                start = p[-1]

            if path[-1].unit:
                p[-1] = MapperUtils.pull_coordinate(p[-2], p[-1], 1.5 * self.board_svg_data["unit_radius"])

            p = np.array(p)

            # given surrounding points, generate a control point
            def g(point: np.ndarray) -> complex:
                centered = point[::2] - point[1]

                # TODO: possible div / 0 if the two convoyed points are in a straight line with the convoyer on one side
                vec = centered[0] - centered[1] / abs(centered[1])
                return vec / abs(vec) * 30 + point[1]

            # this is a bit weird, because the loop is in-between two values
            # (S LO)(OP LO)(OP E)
            s = f"M {f(p[0])} C {f(p[1])}, "
            for x in range(1, len(p) - 1):
                s += f"{f(g(p[x-1:x+2]))}, {f(p[x])} S "

            s += f"{f(p[-2])}, {f(p[-1])}"
            stroke_color = "red" if has_failed else "black"
            marker_color = "redarrow" if has_failed else "arrow"
            latest_paths.append(self._draw_path(s, marker_end = marker_color, stroke_color = stroke_color))
        return latest_paths

    def _draw_support(self,
                      unit: Unit,
                      order: Support,
                      coordinate: complex,
                      has_failed: bool) -> list[Element]:
        source: Province = order.source
        if source.unit is None:
            raise ValueError("Support order has no source unit")
        source_coord = MapperUtils.loc_to_point(source, unit.unit_type, source.unit.coast,
                                                coordinate, self.board_svg_data["map_width"])
        if (isinstance(source.unit.order, Move)
            and source.unit.order.destination == order.destination
            and (not order.destination_coast
                 or source.unit.order.destination_coast == order.destination_coast)):
            dest_coast = source.unit.order.destination_coast
            # If the supported move is a convoy, draw the support arrow from the last fleet instead
            if source in self.convoy_paths:
                source_coord = MapperUtils.loc_to_point(self.convoy_paths[source][0][-2],
                                                       UnitType.FLEET, None, coordinate,
                                                       self.board_svg_data["map_width"])
        else:
            dest_coast = order.destination_coast
        dest_coord = MapperUtils.loc_to_point(order.destination, source.unit.unit_type, dest_coast, source_coord, self.board_svg_data["map_width"])
        marker_start = ""
        if order.destination.unit:
            if order.is_support_hold():
                dest_coord = MapperUtils.pull_coordinate(coordinate, dest_coord, 1.5 * self.board_svg_data["unit_radius"])
            else:
                dest_coord = MapperUtils.pull_coordinate(source_coord, dest_coord, 1.5 * self.board_svg_data["unit_radius"])
            # Draw hold around unit that can be support-held
            if (order.is_support_hold()
                and isinstance(source.unit.order, (ConvoyTransport, Support))
                and MapperUtils.is_moveable(source.unit, self.adjacent_provinces, self.player_restriction)):
                for coord in source.all_coordinates[source.unit.coast if source.unit.coast else source.unit.unit_type.name]:
                    self._draw_hold(None, None, coord.primary_coordinate, False)

            # if two units are support-holding each other
            destorder = order.destination.unit.order

            if (
                isinstance(destorder, Support)
                and destorder.is_support_hold()
                and order.is_support_hold()
                and destorder.source == unit.province
                and (self.player_restriction is None
                     or order.destination.unit.player.name == self.player_restriction)
            ):
                # This check is so we only do it once, so it doesn't overlay
                # it doesn't matter which one is the origin & which is the dest
                if id(order.destination.unit) < id(unit):
                    return []
                marker_start = f"url(#{'red' if has_failed else ''}ball)"
                # doesn't matter that v3 has been pulled, as it's still collinear
                coordinate = source_coord = MapperUtils.pull_coordinate(
                    dest_coord, coordinate, self.board_svg_data["unit_radius"]
                )

        dasharray_size = 2.5 * self.board_svg_data["order_stroke_width"]
        drawn_order = MapperUtils.create_element(
            "path",
            {
                "d": f"M {coordinate.real},{coordinate.imag} " + \
                     f"Q {source_coord.real},{source_coord.imag} " \
                     f"{dest_coord.real},{dest_coord.imag}",
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-dasharray": f"{dasharray_size} {dasharray_size}",
                "stroke-width": self.board_svg_data["order_stroke_width"],
                "stroke-linecap": "round",
                "marker-start": marker_start,
                "marker-end": f"url(#{'red' if has_failed else ''}{'ball' if order.is_support_hold() else 'arrow'})",
            },
        )
        return [drawn_order]

    def _draw_convoy(self, _, __, coordinate: complex, has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = MapperUtils.create_element(
            "circle",
            {
                "cx": coordinate.real,
                "cy": coordinate.imag,
                "r": self.board_svg_data["unit_radius"] / 2,
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-width": self.board_svg_data["order_stroke_width"] * 2 / 3,
            },
        )
        element.append(drawn_order)

    def _draw_build(self, order: Build) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        build_location = order.province.get_unit_coordinates(order.unit_type, order.coast)
        drawn_order = MapperUtils.create_element(
            "circle",
            {
                "cx": build_location.real,
                "cy": build_location.imag,
                "r": self.board_svg_data["unit_radius"],
                "fill": "none",
                "stroke": "green",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def _draw_disband(self, coordinate: complex, svg) -> None:
        element = svg.getroot()
        drawn_order = MapperUtils.create_element(
            "circle",
            {
                "cx": coordinate.real,
                "cy": coordinate.imag,
                "r": self.board_svg_data["unit_radius"],
                "fill": "none",
                "stroke": "red",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def draw_force_disband(self, _, __, coordinate: complex, ___, svg = None) -> None:
        """Draws a disband order on the map.
        This method is public since we need to forced disbands on the current map."""
        element = (svg if svg is not None else self.moves_svg).getroot()
        cross_width = self.board_svg_data["order_stroke_width"] / (2**0.5)
        square_rad = self.board_svg_data["unit_radius"] / (2**0.5)
        # two corner and a center point. Rotate and concat them to make the correct object
        init = np.array(
            [
                (-square_rad + cross_width, -square_rad),
                (-square_rad, -square_rad + cross_width),
                (-cross_width, 0),
            ]
        )
        rotate_90 = np.array([[0, -1], [1, 0]])
        points = np.concatenate((init, init @ rotate_90, -init, -init @ rotate_90)) + np.array([coordinate.real, coordinate.imag])
        drawn_order = MapperUtils.create_element(
            "polygon",
            {
                "points": " ".join(map(lambda a: ",".join(map(str, a)), points)),
                "fill": "red",
                "stroke": "black",
                "stroke-width": self.board_svg_data["order_stroke_width"] / 4,
            },
        )

        element.append(drawn_order)
