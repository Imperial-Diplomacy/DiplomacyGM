"""Module responsible for drawing the side panel on the map, which includes the date and scoreboard."""
from __future__ import annotations
import re
from typing import TYPE_CHECKING
from xml.etree.ElementTree import ElementTree, Element

from DiploGM.map_parser.vector.utils import get_element_color, get_svg_element
from DiploGM.map_parser.vector.transform import TransGL3

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.player import Player
    from DiploGM.mapper.utils import MapperUtils

class PanelDrawer:
    """Class responsible for drawing the panel on the map."""
    def __init__(self,
                 utils: MapperUtils,
                 board_svg: ElementTree,
                 board: Board,
                 player_colors: dict[str, str],
                 restriction: Player | None = None):
        self.utils = utils
        self.board_svg = board_svg
        self.board = board
        self.board_svg_data = board.data["svg config"]
        self.player_colors = player_colors
        self.restriction = restriction

        if not self.board_svg_data["power_banners"]:
            return
        all_power_banners_element = get_svg_element(
            self.board_svg, self.board_svg_data["power_banners"]
        )
        self.scoreboard_power_locations: list[tuple[float, float]] = []
        for power_element in all_power_banners_element or []:
            destination_pretransform_coordinates = TransGL3(power_element[0]).transform((float(power_element[0].get("x", 0)),
                                                                                         float(power_element[0].get("y", 0))))
            destination_coordinates = TransGL3(power_element).transform(destination_pretransform_coordinates)
            self.scoreboard_power_locations.append(destination_coordinates)

        # each power is placed in the right spot based on the transform field which has value of
        # "translate($x,$y)" where x,y are floating point numbers; we parse these via regex and sort by y-value
        self.scoreboard_power_locations.sort(key=lambda loc: loc[1])


    def draw_side_panel(self, svg: ElementTree) -> None:
        """Draws the side panel with the date and scoreboard."""
        self._draw_side_panel_date(svg)
        self._draw_side_panel_scoreboard(svg)

    def _draw_power_banner(self, power_element: Element, player: Player,
                           banner_index: int, high_player_count: bool) -> bool:
        if len(power_element) == 0:
            return False
        initial_pretransform_coordinates = TransGL3(power_element[0]).transform((float(power_element[0].get("x", 0)),
                                                                                 float(power_element[0].get("y", 0))))
        banner_coordinates = TransGL3(power_element).transform(initial_pretransform_coordinates)
        if high_player_count and banner_coordinates != self.scoreboard_power_locations[banner_index]:
            return False
        if not high_player_count and get_element_color(power_element[0]) != player.default_color:
            return False
        player_data = self.board.data["players"][player.name]
        if player_data.get("hidden") == "true":
            power_element.clear()
            return True

       # TODO: Add support for chaos "points" and perhaps simplify this whole thing
        name_index = self.board_svg_data.get("power_name_index", 1)
        sc_index = self.board_svg_data.get("power_sc_index", 5)
        iscc_index = self.board_svg_data.get("power_iscc_index", 6)
        vscc_index = self.board_svg_data.get("power_vscc_index", 7)

        self.utils.color_element(power_element[0], self.player_colors[player.name])
        new_translation = (self.scoreboard_power_locations[banner_index][0] - initial_pretransform_coordinates[0],
                            self.scoreboard_power_locations[banner_index][1] - initial_pretransform_coordinates[1])
        power_element.set("transform", f"translate({new_translation[0]}, {new_translation[1]})")
        if high_player_count or player_data.get("nickname"):
            power_element[name_index][0].text = player.get_name()
            # Fix for Poland-Lithuanian Commonwealth
            if len(power_element[name_index]) > 1:
                power_element[name_index][1].text = ""
                power_element[name_index].set("y", "237.67107")
                power_element[name_index][0].set("y", "237.67107")
                style = power_element[name_index].get("style")
                assert style is not None
                style = re.sub(r"font-size:[0-9.]+px", "font-size:42.6667px", style)
                power_element[name_index].set("style", style)
        power_element[sc_index][0].text = (str(len(player.centers))
            if (self.restriction is None or self.restriction == player) else "???")
        if iscc_index > -1:
            power_element[iscc_index][0].text = str(player_data["iscc"])
        if self.board.data["victory_conditions"] == "classic" and vscc_index > -1:
            power_element[vscc_index][0].text = str(self.board.data["victory_count"])
        elif vscc_index > -1:
            power_element[vscc_index][0].text = str(player_data["vscc"])
        return True

    def _draw_side_panel_scoreboard(self, svg: ElementTree) -> None:
        """
        format is a list of each power; for each power, its children nodes are as follows:
        0: colored rectangle
        1: full name ("Dutch Empire", ...)
        2-4: "current", "victory", "start" text labels in that order
        5-7: SC counts in that same order
        """

        root = svg.getroot()
        if root is None:
            raise ValueError("SVG root is None")
        all_power_banners_element = get_svg_element(root, self.board_svg_data["power_banners"])
        if all_power_banners_element is None:
            return

        if self.board.fow and self.restriction is not None:
            # don't get info
            players = sorted(self.board.get_players(), key=lambda sort_player: sort_player.name)
        else:
            players = self.board.get_players_sorted_by_score()
        players = sorted(players, key=lambda hidden_player:
                                  self.board.is_player_hidden(hidden_player))

        high_player_count = (len(self.board.get_players()) > len(self.scoreboard_power_locations)
                             or self.board.data.get("vassals") == "enabled")
        for i, player in enumerate(self.board.get_players_sorted_by_score()):
            if i >= len(self.scoreboard_power_locations):
                break
            for power_element in all_power_banners_element:
                if self._draw_power_banner(power_element, player, i, high_player_count):
                    break

    def _draw_side_panel_date(self, svg: ElementTree) -> None:
        date = get_svg_element(svg, self.board_svg_data["season"])
        if date is None:
            return
        game_name = self.board.name
        name_text = "" if game_name is None else f"{game_name} — "
        # TODO: this is hacky; I don't know a better way
        date[0][0].text = name_text + str(self.board.turn)
