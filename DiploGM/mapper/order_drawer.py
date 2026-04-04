"""Module to draw orders (moves, support, etc.) on the map."""
from __future__ import annotations
import numpy as np
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import ElementTree

from DiploGM.db.database import logger
from DiploGM.models.order import (
    Hold, Core, Transform, Move, Support, ConvoyTransport,
    Build, Disband, TransformBuild, RetreatMove, RetreatDisband
)
from DiploGM.models.unit import UnitType

if TYPE_CHECKING:
    from DiploGM.models.province import Province
    from DiploGM.models.unit import Unit
    from DiploGM.models.player import Player
    from DiploGM.models.turn import Turn
    from DiploGM.models.order import UnitOrder, PlayerOrder
    from DiploGM.mapper.utils import MapperUtils

class OrderDrawer:
    """Class to draw orders on the map."""
    def __init__(self,
                 utils: MapperUtils,
                 moves_svg: ElementTree,
                 board_svg_data: dict[str, Any],
                 adjacent_provinces: set[str],
                 player_restriction: Player | None = None):
        self.utils = utils
        self.moves_svg: ElementTree = moves_svg
        self.board_svg_data = board_svg_data
        self.adjacent_provinces = adjacent_provinces
        self.player_restriction = player_restriction

    def draw_order(self, unit: Unit, order: UnitOrder | None, coordinate: tuple[float, float], current_turn: Turn) -> None:
        """Draws a specific order on the map."""
        if isinstance(order, Hold):
            self._draw_hold(coordinate, order.has_failed)
        elif isinstance(order, Core):
            self._draw_core(coordinate, order.has_failed)
        elif isinstance(order, Transform):
            self._draw_transform(coordinate, order.has_failed)
        elif isinstance(order, Move):
            # moves are just convoyed moves that have no convoys
            return self._draw_convoyed_move(unit, order, coordinate, order.has_failed)
        elif isinstance(order, Support):
            return self._draw_support(unit, order, coordinate, order.has_failed)
        elif isinstance(order, ConvoyTransport):
            self._draw_convoy(order, coordinate, order.has_failed)
        elif isinstance(order, RetreatMove):
            return self.draw_retreat_move(order, unit.unit_type, coordinate)
        elif isinstance(order, RetreatDisband):
            self.draw_force_disband(coordinate, self.moves_svg)
        else:
            if current_turn.is_moves():
                self._draw_hold(coordinate, False)
            else:
                self.draw_force_disband(coordinate, self.moves_svg)
            logger.debug("None order found: hold drawn. Coordinates: %s", coordinate)

    def draw_player_order(self, order: PlayerOrder):
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
                self.draw_force_disband(coord.primary_coordinate, self.moves_svg)
        elif isinstance(order, TransformBuild):
            assert order.province.unit is not None
            transforming_unit: Unit = order.province.unit
            if transforming_unit.coast:
                coord_list = order.province.all_coordinates[transforming_unit.coast]
            else:
                coord_list = order.province.all_coordinates[transforming_unit.unit_type.name]
            for coord in coord_list:
                self._draw_transform(coord.primary_coordinate, False)
        else:
            logger.error("Could not draw player order %s", order)

    def _draw_hold(self, coordinate: tuple[float, float], has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = self.utils.create_element(
            "circle",
            {
                "cx": coordinate[0],
                "cy": coordinate[1],
                "r": self.board_svg_data["unit_radius"],
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def _draw_core(self, coordinate: tuple[float, float], has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = self.utils.create_element(
            "rect",
            {
                "x": coordinate[0] - self.board_svg_data["unit_radius"],
                "y": coordinate[1] - self.board_svg_data["unit_radius"],
                "width": self.board_svg_data["unit_radius"] * 2,
                "height": self.board_svg_data["unit_radius"] * 2,
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-width": self.board_svg_data["order_stroke_width"],
                "transform": f"rotate(45 {coordinate[0]} {coordinate[1]})",
            },
        )
        element.append(drawn_order)

    def _draw_transform(self, coordinate: tuple[float, float], has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = self.utils.create_element(
            "rect",
            {
                "x": coordinate[0] - self.board_svg_data["unit_radius"],
                "y": coordinate[1] - self.board_svg_data["unit_radius"],
                "width": self.board_svg_data["unit_radius"] * 2,
                "height": self.board_svg_data["unit_radius"] * 2,
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def draw_retreat_move(self,
                          order: RetreatMove,
                          unit_type: UnitType,
                          coordinate: tuple[float, float]) -> None:
        destination = self.utils.loc_to_point(order.destination, unit_type, order.destination_coast, coordinate)
        if order.destination.unit:
            destination = self.utils.pull_coordinate(coordinate, destination)
        order_path = self.utils.create_element(
            "path",
            {
                "d": f"M {coordinate[0]},{coordinate[1]} L {destination[0]},{destination[1]}",
                "fill": "none",
                "stroke": "red",
                "stroke-width": self.board_svg_data["order_stroke_width"],
                "stroke-linecap": "round",
                "marker-end": "url(#redarrow)",
            },
        )
        return order_path

    def _path_helper(
        self, source: Province, destination: Province, current: Province, already_checked=()
    ) -> list[tuple[Province, Province]]:
        if current in already_checked:
            return []
        options = []
        new_checked = already_checked + (current,)
        for possibility in current.adjacency_data.adjacent:
            if possibility.name not in self.adjacent_provinces:
                continue

            if possibility == destination:
                return [
                    (
                        current,
                        destination,
                    )
                ]
            if (
                possibility.can_convoy
                and possibility.unit is not None
                and (self.player_restriction is None or possibility.unit.player == self.player_restriction)
                and possibility.unit.unit_type == UnitType.FLEET
                and isinstance(possibility.unit.order, ConvoyTransport)
                and possibility.unit.order.source is source
                and possibility.unit.order.destination is destination
            ):
                options += self._path_helper(source, destination, possibility, new_checked)
        return list(map((lambda t: (current,) + t), options))

    def _draw_path(self, d: str, marker_end="arrow", stroke_color="black"):
        order_path = self.utils.create_element(
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

    def _get_all_paths(self, source: Province, order: Move) -> list[tuple[Province, Province]]:
        assert order.destination is not None
        paths = self._path_helper(source, order.destination, source)
        if not paths:
            return [(source, order.destination)]
        return paths

    # removes unnecessary convoys, for instance [A->B->C & A->C] -> [A->C]
    def _get_shortest_paths(self, args: list[tuple]) -> list[tuple]:
        args.sort(key=len)
        min_subsets = []
        for s in args:
            if not any(set(min_subset).issubset(s) for min_subset in min_subsets):
                min_subsets.append(s)

        return min_subsets

    def _draw_convoyed_move(self, unit: Unit, order: Move, coordinate: tuple[float, float], has_failed: bool):
        def f(point: tuple[float, float]):
            return " ".join(map(str, point))

        def norm(point: tuple[float, float]) -> tuple[float, float]:
            return point / ((np.sum(np.array(point)**2)) ** 0.5)

        valid_convoys = self._get_all_paths(unit.province, order)
        # TODO: make this a setting
        if False:
            if len(valid_convoys):
                valid_convoys = valid_convoys[0:1]
        valid_convoys = self._get_shortest_paths(valid_convoys)
        for path in valid_convoys:
            p = [coordinate]
            start = coordinate
            for loc in path[1:]:
                p += [self.utils.loc_to_point(loc, unit.unit_type, order.destination_coast, start)]
                start = p[-1]

            if path[-1].unit:
                p[-1] = self.utils.pull_coordinate(p[-2], p[-1])

            p = np.array(p)

            # given surrounding points, generate a control point
            def g(point: np.ndarray) -> tuple[float, float]:
                centered = point[::2] - point[1]

                # TODO: possible div / 0 if the two convoyed points are in a straight line with the convoyer on one side
                vec = tuple(np.subtract(centered[0], norm(centered[1])))
                return norm(vec) * 30 + point[1]

            # this is a bit weird, because the loop is in-between two values
            # (S LO)(OP LO)(OP E)
            s = f"M {f(p[0])} C {f(p[1])}, "
            for x in range(1, len(p) - 1):
                s += f"{f(g(p[x-1:x+2]))}, {f(p[x])} S "

            s += f"{f(p[-2])}, {f(p[-1])}"
            stroke_color = "red" if has_failed else "black"
            marker_color = "redarrow" if has_failed else "arrow"
            return self._draw_path(s, marker_end = marker_color, stroke_color = stroke_color)

    def _draw_support(self, unit: Unit, order: Support, coordinate: tuple[float, float], has_failed: bool) -> None:
        source: Province = order.source
        if source.unit is None:
            raise ValueError("Support order has no source unit")
        source_coord = self.utils.loc_to_point(source, unit.unit_type, source.unit.coast, coordinate)
        if (isinstance(source.unit.order, Move)
            and source.unit.order.destination == order.destination
            and (not order.destination_coast
                 or source.unit.order.destination_coast == order.destination_coast)):
            dest_coast = source.unit.order.destination_coast
        else:
            dest_coast = order.destination_coast
        dest_coord = self.utils.loc_to_point(order.destination, source.unit.unit_type, dest_coast, source_coord)
        marker_start = ""
        ball_type = "redball" if has_failed else "ball"
        arrow_type = "redarrow" if has_failed else "arrow"
        if order.destination.unit:
            if order.source == order.destination:
                dest_coord = self.utils.pull_coordinate(coordinate, dest_coord)
            else:
                dest_coord = self.utils.pull_coordinate(source_coord, dest_coord)
            # Draw hold around unit that can be support-held
            if (order.source == order.destination
                and isinstance(source.unit.order, (ConvoyTransport, Support))
                and self.utils.is_moveable(source.unit, self.adjacent_provinces, self.player_restriction)):
                for coord in source.all_coordinates[source.unit.coast if source.unit.coast else source.unit.unit_type.name]:
                    self._draw_hold(coord.primary_coordinate, False)

            # if two units are support-holding each other
            destorder = order.destination.unit.order

            if (
                isinstance(destorder, Support)
                and destorder.source == destorder.destination == unit.province
                and order.source == order.destination
                and (self.player_restriction is None
                     or order.destination.unit.player == self.player_restriction)
            ):
                # This check is so we only do it once, so it doesn't overlay
                # it doesn't matter which one is the origin & which is the dest
                if id(order.destination.unit) < id(unit):
                    return
                marker_start = f"url(#{ball_type})"
                # doesn't matter that v3 has been pulled, as it's still collinear
                coordinate = source_coord = self.utils.pull_coordinate(
                    dest_coord, coordinate, self.board_svg_data["unit_radius"]
                )

        dasharray_size = 2.5 * self.board_svg_data["order_stroke_width"]
        drawn_order = self.utils.create_element(
            "path",
            {
                "d": f"M {coordinate[0]},{coordinate[1]} " + \
                     f"Q {source_coord[0]},{source_coord[1]} " \
                     f"{dest_coord[0]},{dest_coord[1]}",
                "fill": "none",
                "stroke": "red" if has_failed else "black",
                "stroke-dasharray": f"{dasharray_size} {dasharray_size}",
                "stroke-width": self.board_svg_data["order_stroke_width"],
                "stroke-linecap": "round",
                "marker-start": marker_start,
                "marker-end": f"url(#{ball_type if order.source == order.destination else arrow_type})",
            },
        )
        return drawn_order

    def _draw_convoy(self, order: ConvoyTransport, coordinate: tuple[float, float], has_failed: bool) -> None:
        element = self.moves_svg.getroot()
        assert element is not None
        drawn_order = self.utils.create_element(
            "circle",
            {
                "cx": coordinate[0],
                "cy": coordinate[1],
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
        drawn_order = self.utils.create_element(
            "circle",
            {
                "cx": build_location[0],
                "cy": build_location[1],
                "r": 10,
                "fill": "none",
                "stroke": "green",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def _draw_disband(self, coordinate: tuple[float, float], svg) -> None:
        element = svg.getroot()
        drawn_order = self.utils.create_element(
            "circle",
            {
                "cx": coordinate[0],
                "cy": coordinate[1],
                "r": self.board_svg_data["unit_radius"],
                "fill": "none",
                "stroke": "red",
                "stroke-width": self.board_svg_data["order_stroke_width"],
            },
        )
        element.append(drawn_order)

    def draw_force_disband(self, coordinate: tuple[float, float], svg) -> None:
        element = svg.getroot()
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
        points = np.concatenate((init, init @ rotate_90, -init, -init @ rotate_90)) + coordinate
        drawn_order = self.utils.create_element(
            "polygon",
            {
                "points": " ".join(map(lambda a: ",".join(map(str, a)), points)),
                "fill": "red",
            },
        )

        element.append(drawn_order)
