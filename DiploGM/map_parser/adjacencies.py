"""Module to check for potential adjacency issues in a map.
This is not guaranteed to find all issues, but should find the majority of them."""
from itertools import combinations
import os
from typing import Optional

from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.models.board import Board
from DiploGM.models.province import Province
from DiploGM.utils.sanitise import parse_variant_path

# Gets adjacent provinces, but with High Seas combined into one for the purpose of finding adjacency issues
def _get_adjacent_geom(province: Province) -> set[Province]:
    return {a for a in province.adjacency_data.adjacent if a.name[-1] not in "23456789"}

# A recursive function to find loops of provinces with no internal adjacencies
# Generally, two adjacent provinces should share exactly two adjacencies on either side
# If there's only one, that typeically means there's a "hole" or the edge of the board
# We try to trace a chain of such provinces, and if we reach the start, we have a loop
def _find_province_loop(province: Province,
                        destination: Province,
                        visited: list[Province],
                        ignored_provinces: set[Province]) -> Optional[list[Province]]:
    if province == destination:
        return None if len(visited) == 2 else visited # A -> B -> A shouldn't count
    visited.append(province)
    for adj in _get_adjacent_geom(province):
        # ignored_provinces prevents us finding the same loop multiple times
        if adj in visited[1:] or adj in ignored_provinces:
            continue
        if len(_get_adjacent_geom(province) & _get_adjacent_geom(adj)) > 1:
            continue
        loop = _find_province_loop(adj, destination, visited, ignored_provinces)
        if loop is not None:
            return loop
    visited.pop()
    return None

# Given a pair of adjacent provinces, checks for potential adjacency issues, including:
# - No common adjacencies
# - Loops of provinces with no internal adjacencies
# - Groups of four provinces that all border each other
def _check_common_adjacencies(province: Province,
                              adj: Province,
                              visited_provinces: set,
                              visited_adjacent: set) -> str | None:
    common_adj = _get_adjacent_geom(province) & _get_adjacent_geom(adj)
    if len(common_adj) == 0:
        return f"Provinces {province.name} and {adj.name} are adjacent but have no common adjacencies"
    # Finding loops of provinces
    if len(common_adj) == 1:
        loop = _find_province_loop(adj, province, [province], visited_provinces)
        # Comparing names of the first and last provinces in the loop so we only report it once
        if loop is not None and loop[1].name > loop[-1].name:
            return f"Found a loop of provinces {', '.join(p.name for p in loop)}. " + \
                   "If they surround an impassable province or the board edge, this is expected"

    # Searching for groups of four provinces that all share a border
    warnings = []
    for third, fourth in combinations(common_adj - visited_provinces - visited_adjacent, 2):
        if fourth not in _get_adjacent_geom(third):
            continue
        if min(len(_get_adjacent_geom(province)),
                len(_get_adjacent_geom(adj)),
                len(_get_adjacent_geom(third)),
                len(_get_adjacent_geom(fourth))) == 3:
            # Skips provinces that only border the other three, as that's geometrically possible
            continue
        warnings.append(f"Provinces {province.name}, {adj.name}, {third.name}, " +
                        f"and {fourth.name} all border each other")
    visited_adjacent.add(adj)
    return "\n".join(warnings) if warnings else None

# This is a function that goes through a map and attempts to find adjacency issues
# It will not be fool-proof, but it should detect the majority of potential errors
# The list of warnings it generates include the following:
# - High Seas provinces in the same region that have different adjacencies
#   (e.g. Cape Khoe bordering SAO1 but not SAO2)
# - Provinces with zero adjacencies
# - Adjacent provinces that have no common adjacencies
# - Loops of provinces that have no internal connections (note that this does detect the board edges)
# - Groups of four provinces that all border each other
def verify_adjacencies(variant: str) -> str:
    """Checks for potential adjacency issues in a variant.
    This is not guaranteed to find all issues, but should find the majority of them.
    Returns a string listing any warnings found."""
    if not os.path.isdir(parse_variant_path(variant)):
        return f"Game {variant} does not exist."
    board: Board = get_parser(variant).parse()
    warnings = []
    visited_provinces = set()

    # High Seas
    for province in [p for p in board.provinces if p.name[-1] in "23456789"]:
        try:
            comp_province = board.get_province(province.name[:-1] + "1")
            # Two high seas' adjacencies should differ by only each other
            if (comp_province.adjacency_data.adjacent ^ province.adjacency_data.adjacent
                != {province, comp_province}):
                warnings.append(f"Province {province.name} and {comp_province.name} have different adjacencies")
            visited_provinces.add(province)
        except ValueError:
            warnings.append(f"Province {province.name} is named like a high seas province " +
                            f"but {province.name[:-1]}1 was not found")

    for province in board.provinces - visited_provinces:
        if len(province.adjacency_data.adjacent) == 0:
            warnings.append(f"Province {province.name} has no adjacencies")
        visited_adjacent = set()
        for adj in _get_adjacent_geom(province) - visited_provinces:
            warning = _check_common_adjacencies(province, adj, visited_provinces, visited_adjacent)
            if warning is not None:
                warnings.append(warning)
        visited_provinces.add(province)
    return "\n".join(warnings) if warnings else "No adjacency issues found"
