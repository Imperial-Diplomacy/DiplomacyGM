"""Module responsible for drawing the side panel on the map, which includes the date and scoreboard."""
from __future__ import annotations
import re
from typing import TYPE_CHECKING
from xml.etree.ElementTree import ElementTree, Element

import DiploGM.mapper.utils as MapperUtils
from DiploGM.map_parser.vector.utils import get_coordinates, get_element_color, find_svg_element
from DiploGM.map_parser.vector.transform import TransGL3

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.player import Player

class PanelDrawer:
    """Class responsible for drawing the panel on the map."""
    def __init__(self,
                 board_svg: ElementTree,
                 board: Board,
                 player_colors: dict[str, str],
                 restriction: Player | None = None):
        self.board_svg = board_svg
        self.board = board
        self.board_svg_data = board.data["svg config"]
        self.player_colors = player_colors
        self.restriction = restriction

        all_power_banners_element = find_svg_element(
            self.board_svg, "power_banners", self.board_svg_data
        )
        if all_power_banners_element is None:
            return
        self.scoreboard_power_locations: list[complex] = []
        for power_element in all_power_banners_element:
            destination_pretransform_coordinates = TransGL3(power_element[0]).transform(get_coordinates(power_element[0]))
            destination_coordinates = TransGL3(power_element).transform(destination_pretransform_coordinates)
            self.scoreboard_power_locations.append(destination_coordinates)

        # each power is placed in the right spot based on the transform field which has value of
        # "translate($x,$y)" where x,y are floating point numbers; we parse these via regex and sort by y-value
        self.scoreboard_power_locations.sort(key=lambda loc: loc.imag)


    def draw_side_panel(self, svg: ElementTree) -> None:
        """Draws the side panel with the date and scoreboard."""
        self._draw_side_panel_date(svg)
        self._draw_side_panel_scoreboard(svg)

    def _draw_power_banner(self, power_element: Element, player: Player,
                           banner_index: int, high_player_count: bool) -> bool:
        if len(power_element) == 0:
            return False
        initial_pretransform_coordinates = TransGL3(power_element[0]).transform(get_coordinates(power_element[0]))
        banner_coordinates = TransGL3(power_element).transform(initial_pretransform_coordinates)
        if high_player_count and banner_coordinates != self.scoreboard_power_locations[banner_index]:
            return False
        if not high_player_count and get_element_color(power_element[0]) != player.default_color:
            return False
        player_data = self.board.data["players"][player.name]
        if player_data.get("hidden") == "true":
            power_element.clear()
            return True

        MapperUtils.color_element(power_element[0], self.player_colors[player.name])
        if self.board_svg_data.get("scoreboard", {}).get("sort", True):
            new_translation = self.scoreboard_power_locations[banner_index] - initial_pretransform_coordinates
            power_element.set("transform", f"translate({new_translation.real}, {new_translation.imag})")

        for index, value in self.board_svg_data["scoreboard"].get("indexes", {}).items():
            if not index.isnumeric() or int(index) >= len(power_element):
                continue
            if value == "__name__" and not high_player_count and not player_data.get("nickname"):
                continue

            # Fix for Poland-Lithuanian Commonwealth
            if index == 1 and len(power_element[index]) > 1:
                power_element[index][1].text = ""
                power_element[index].set("y", "237.67107")
                power_element[index][0].set("y", "237.67107")
                style = power_element[index].get("style")
                assert style is not None
                style = re.sub(r"font-size:[0-9.]+px", "font-size:42.6667px", style)
                power_element[index].set("style", style)

            value = value.replace("__name__", player.get_name())
            value = value.replace("__score__", str(len(player.centers)))
            value = value.replace("__iscc__", str(player_data["iscc"]))
            value = value.replace("__vscc__", str(player_data["vscc"]))
            power_element[int(index)][0].text = value
        return True

    def _draw_side_panel_scoreboard(self, svg: ElementTree) -> None:
        root = svg.getroot()
        if root is None:
            raise ValueError("SVG root is None")
        all_power_banners_element = find_svg_element(root, "power_banners", self.board_svg_data)
        if all_power_banners_element is None:
            return

        if self.board.data.get("fow", "disabled") == "enabled" and self.restriction is not None:
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
        date = find_svg_element(svg, "season", self.board_svg_data)
        if date is None:
            return
        game_name = self.board.data.get("game_name")
        season_format = self.board_svg_data.get("season_format", "%N( - )?%B %S")
        if isinstance(season_format, str):
            season_format = {"0": season_format}
        for key, value in season_format.items():
            name_text = format(self.board.turn, value)
            if game_name:
                name_text = name_text.replace("%N", game_name)
                name_text = re.sub(r"\((.*?)\)\?", r"\1", name_text)
            else:
                name_text = name_text.replace("%N", "")
                name_text = re.sub(r"\((.*?)\)\?", "", name_text)
            date[int(key)][0].text = name_text
