import logging
import re
import numpy as np
from typing import Callable

from shapely.geometry import Point
from xml.etree.ElementTree import Element, ElementTree

from DiploGM.map_parser.vector.transform import TransGL3
from DiploGM.models.province import Province

LAYER_DICTIONARY = {
    "land_layer": {"Region Colors"},
    "island_borders": {"Island Adjacencies"},
    "island_fill_layer": {"Island Fills"},
    "sea_borders": {"Sea Adjacencies"},
    "province_names": {"Titles"},
    "supply_center_icons": {"SC Markers", "SC markers"},
    "army": {"Army Locations"},
    "retreat_army": {"Army Locations (Retreats)"},
    "fleet": {"Fleet Locations"},
    "retreat_fleet": {"Fleet Locations (Retreats)"},
    "starting_units": {"Units"},
    "unit_output": {"Unit Output Layer"},
    "arrow_output": {"Orders Output Layer"},
    "background": {"Background"},
    "season": {"Season Title"},
    "power_banners": {"Power Banners"},
}
LAYER_NAMES = set(LAYER_DICTIONARY.keys())
NAMESPACE: dict[str, str] = {
    "inkscape": "{http://www.inkscape.org/namespaces/inkscape}",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
    "svg": "http://www.w3.org/2000/svg",
}
SVG_CONFIG_KEY: str = "svg config"

logger = logging.getLogger(__name__)

def find_svg_element(svg_root: Element | ElementTree, layer_name: str, config_data: dict) -> Element | None:
    """Given a set of element ids and labels, tries to find a matching element in the SVG or None if none found."""
    layer_id = config_data.get(layer_name)
    if layer_id is not None and isinstance(layer_id, str):
        if (element := svg_root.find(f'*[@id="{layer_id}"]')) is not None:
            return element
    for element_label in LAYER_DICTIONARY.get(layer_name, set()):
        if (element := svg_root.find(f'*[@inkscape:label="{element_label}"]',
            namespaces={"inkscape": "http://www.inkscape.org/namespaces/inkscape"})) is not None:
            return element
    return None

def clear_svg_element(svg_root: Element | ElementTree, layer_name: str, config_data: dict) -> None:
    """Clears an element from the SVG. Tends to run much quicker than deleting it entirely."""
    element = find_svg_element(svg_root, layer_name, config_data)
    if element is not None:
        element.clear()

def get_element_color(element: Element, prefix="fill:") -> str | None:
    """Gets the color of an element, or None if it has none."""
    style_string = element.get("style")
    if style_string is None:
        return None
    style = style_string.split(";")
    for value in style:
        if value.startswith(prefix):
            if value == "none" and prefix == "fill:":
                return get_element_color(element, "stroke:")
            value = value[len(prefix):]
            if value.startswith("#"):
                value = value[1:]
            return value

def get_unit_coordinates(
    unit_data: Element,
) -> tuple[float, float]:
    """Gets the x, y coordinates of a unit."""
    path = unit_data.find("{http://www.w3.org/2000/svg}path")
    assert path is not None

    x = path.get("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}cx")
    y = path.get("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}cy")
    if x is None or y is None:
        # find all the points the objects are at
        # take the center of the bounding box
        path = unit_data.findall("{http://www.w3.org/2000/svg}path")[0]
        pathstr = path.get("d")
        assert pathstr is not None
        coordinates = parse_path(pathstr, TransGL3(path))
        coordinates = np.array(sum(coordinates, start = []))
        minp = np.min(coordinates, axis=0)
        maxp = np.max(coordinates, axis=0)
        return ((minp + maxp) / 2).tolist()

    x = float(x)
    y = float(y)
    return TransGL3(path).transform((x, y))


def move_coordinate(
    former_coordinate: tuple[float, float],
    coordinate: tuple[float, float],
) -> tuple[float, float]:
    """Moves a coordinate by a given offset."""
    return (former_coordinate[0] + coordinate[0], former_coordinate[1] + coordinate[1])



# returns:
# new base_coordinate (= base_coordinate if not applicable),
# new former_coordinate (= former_coordinate if not applicable),
def _parse_path_command(
    command: str,
    args: tuple[float, float],
    coordinate: tuple[float, float],
) -> tuple[float, float]:
    is_absolute = command.isupper()
    command = command.lower()

    if command in ["m", "c", "l", "t", "s", "q", "a"]:
        return args if is_absolute else move_coordinate(coordinate, args)  # Ignore all args except the last
    if command in ["h", "v"]:
        coordlist = list(coordinate)
        index = 0 if command == "h" else 1
        if is_absolute:
            coordlist[index] = 0
        coordlist[index] += args[0]
        return (coordlist[0], coordlist[1])
    raise RuntimeError(f"Unknown SVG path command: {command}")

def parse_path(path_string: str, translation: TransGL3) -> list[list[tuple[float, float]]]:
    """Parses an SVG path string into a list of coordinates."""
    province_coordinates = [[]]
    command = None
    arguments_by_command = {"a": 7, "c": 6, "h": 1, "l": 2, "m": 2, "q": 4, "s": 4, "t": 2, "v": 1}
    expected_arguments = 0
    current_index = 0
    path: list[str] = re.split(r"[ ,]+", path_string.strip())

    start = None
    coordinate = (0, 0)
    while current_index < len(path):
        if path[current_index][0].isalpha():
            if len(path[current_index]) != 1:
                # m20,70 is valid syntax, so move the 20,70 to the next element
                path.insert(current_index + 1, path[current_index][1:])
                path[current_index] = path[current_index][0]

            command = path[current_index]
            if command.lower() == "z":
                if start is None:
                    raise Exception("Invalid geometry: got 'z' on first element in a subgeometry")
                province_coordinates[-1].append(translation.transform(start))
                start = None
                current_index += 1
                if current_index < len(path):
                    # If we are closing, and there is more, there must be a second polygon (Chukchi Sea)
                    province_coordinates += [[]]
                    continue
                else:
                    break

            elif command.lower() in arguments_by_command:
                expected_arguments = arguments_by_command[command.lower()]
            else:
                raise RuntimeError(f"Unknown SVG path command {command}")

            current_index += 1

        if command is None:
            raise RuntimeError("Path string does not start with a command")
        if command.lower() == "z":
            raise Exception("Invalid path, 'z' was followed by arguments")

        final_index = current_index + expected_arguments
        if len(path) < final_index:
            raise RuntimeError(f"Ran out of arguments for {command}")

        if expected_arguments == 1:
            args = (float(path[current_index]), 0.0)
        else:
            args = (float(path[final_index - 2]), float(path[final_index - 1]))

        coordinate = _parse_path_command(
            command, args, coordinate
        )

        if start is None:
            start = coordinate

        province_coordinates[-1].append(translation.transform(coordinate))
        current_index = final_index
    return province_coordinates

# Initializes relevant province data
# resident_dataset: SVG element whose children each live in some province
# get_coordinates: functions to get x and y child data coordinates in SVG
# function: method in Province that, given the province and a child element corresponding to that province, initializes
# that data in the Province
def initialize_province_resident_data(
    provinces: set[Province],
    resident_dataset: Element | list[Element],
    get_coordinates: Callable[[Element], tuple[float | None, float | None]],
    resident_data_callback: Callable[[Province, Element, str | None], None],
) -> None:
    resident_dataset = list(resident_dataset)
    for province in provinces:
        remove = set()

        # found = False
        for resident_data in resident_dataset:
            x, y = get_coordinates(resident_data)

            if not x or not y:
                remove.add(resident_data)
                continue

            point = Point((x, y))
            if province.geometry.contains(point):
                # found = True
                resident_data_callback(province, resident_data, None)
                remove.add(resident_data)

        # if not found:
        #     print("Not found!")

        for resident_data in remove:
            resident_dataset.remove(resident_data)
