import re
import numpy as np

from xml.etree.ElementTree import Element, ElementTree

from DiploGM.map_parser.vector.transform import TransGL3
import logging

from shapely.geometry import Point
from typing import Callable
from DiploGM.models.province import Province

logger = logging.getLogger(__name__)

def get_svg_element(svg_root: Element | ElementTree, element_id: str) -> Element | None:
    try:
        return svg_root.find(f'*[@id="{element_id}"]')
    except:
        logger.error(f"{element_id} isn't contained in svg_root")

def clear_svg_element(svg_root: Element | ElementTree, element_id: str) -> None:
    element = get_svg_element(svg_root, element_id)
    if element is not None:
        element.clear()

def get_element_color(element: Element, prefix="fill:") -> str | None:
    style_string = element.get("style")
    if style_string is None:
        return None
    style = style_string.split(";")
    for value in style:
        if value.startswith(prefix):
            if value == "none" and prefix == "fill:":
                return get_element_color(element, "stroke:")
            else:
                value = value[len(prefix):]
                if value.startswith("#"):
                    value = value[1:]
                return value

def get_unit_coordinates(
    unit_data: Element,
) -> tuple[float, float]:
    path = unit_data.find("{http://www.w3.org/2000/svg}path")
    assert path is not None

    x = path.get("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}cx")
    y = path.get("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}cy")
    if x == None or y == None:
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

    else:
        x = float(x)
        y = float(y)
        return TransGL3(path).transform((x, y))


def move_coordinate(
    former_coordinate: tuple[float, float],
    coordinate: tuple[float, float],
) -> tuple[float, float]:
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
        if is_absolute:
            return args
        return move_coordinate(coordinate, args)  # Ignore all args except the last
    elif command in ["h", "v"]:
        coordlist = list(coordinate)
        index = 0 if command == "h" else 1
        if is_absolute:
            coordlist[index] = 0
        coordlist[index] += args[0]
        return (coordlist[0], coordlist[1])
    else:
        raise RuntimeError(f"Unknown SVG path command: {command}")

def parse_path(path_string: str, translation: TransGL3):
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
                if start == None:
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

        if start == None:
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

        found = False
        for resident_data in resident_dataset:
            x, y = get_coordinates(resident_data)

            if not x or not y:
                remove.add(resident_data)
                continue

            point = Point((x, y))
            if province.geometry.contains(point):
                found = True
                resident_data_callback(province, resident_data, None)
                remove.add(resident_data)

        # if not found:
        #     print("Not found!")

        for resident_data in remove:
            resident_dataset.remove(resident_data)
