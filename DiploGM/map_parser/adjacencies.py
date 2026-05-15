"""Module to check for potential adjacency issues in a map.
This is not guaranteed to find all issues, but should find the majority of them."""
from itertools import combinations
import os
import shapely
from typing import Optional

from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.models.board import Board
from DiploGM.models.province import Province
from DiploGM.utils.sanitise import parse_variant_path

# We want to ignore manually added adjacencies, since they tend to create four-way junctions,
# and we don't want to catch those
_override_adjacencies: set[tuple[str, str]] = set()

# Gets adjacent provinces, but with High Seas combined into one for the purpose of finding adjacency issues
def _get_adjacent_geom(province: Province) -> set[Province]:
    return {a for a in province.adjacencies.get_all()
            if a.name[-1] not in "23456789"
            and (province.name, a.name) not in _override_adjacencies}

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

# Given a pair of adjacent provinces, checks for potential missing adjacency issues. These usually appear
# as either having no common adjacencies, or a loop of provinces with no internal adjacencies.
# Unless the provinces are on the board edge, they should have two common adjacencies on either side.
def _check_missing_adjacencies(province: Province,
                               adj: Province,
                               visited_provinces: set) -> str | None:
    common_adj = _get_adjacent_geom(province) & _get_adjacent_geom(adj)
    if len(common_adj) == 0:
        return f"Provinces {province.name} and {adj.name} are adjacent but have no common adjacencies"
    # Finding loops of provinces
    if len(common_adj) == 1:
        loop = _find_province_loop(adj, province, [province], visited_provinces)
        # Comparing names of the first and last provinces in the loop so we only report it once
        if loop is None or loop[1].name <= loop[-1].name:
            return None
        min_distance = float("inf")
        closest_pair = (loop[0], loop[2])
        for index1, province1 in enumerate(loop[:-2]):
            for province2 in loop[index1 + 2:]:
                if province2 in _get_adjacent_geom(province1):
                    continue
                distance = shapely.distance(province1.geometry, province2.geometry)
                if distance < min_distance:
                    min_distance = distance
                    closest_pair = (province1, province2)
        return f"Found a loop of provinces {', '.join(p.name for p in loop)}. " + \
               f"Closest pair: {closest_pair[0].name}, {closest_pair[1].name}; distance: {min_distance:.2f}"
    return None

# Checks for groups of four provinces that all border each other, which could mean an x-shaped adjacency
# which should not geometrically happen. However, if one of the provinces are surrounded by the other three,
# then we should flag it as a false positive. We then remove that province from consideration, as it
# does not affect the adjacency viability, but it might hide other such instances.
def _check_cliques(province: Province,
                   adj: Province,
                   visited_provinces: set) -> list[str]:
    # Searching for groups of four provinces that all share a border
    warnings = []
    for third, fourth in combinations(_get_adjacent_geom(province) & _get_adjacent_geom(adj) - visited_provinces, 2):
        if fourth not in _get_adjacent_geom(third):
            continue
        clique = {province, adj, third, fourth}
        if min({len(_get_adjacent_geom(p)) for p in clique}) == 3:
            # Skips provinces that only border the other three, as that's geometrically possible
            continue
        # If all provinces bordering the four in question are on a connected path,
        # then the only way for it to be a valid maximally planar graph is if those provinces
        # surround three of the four, which in turn surrounds the fourth.
        # If the fourth borders any of those, that means it must have an invalid adjacency
        all_adjacent = {p for node in clique for p in _get_adjacent_geom(node)}
        all_adjacent -= clique
        connected_set = {all_adjacent.pop()}
        current_run = connected_set.copy()
        while current_run:
            previous_run = current_run.copy()
            current_run = set()
            for p in previous_run:
                current_run.update(_get_adjacent_geom(p) & all_adjacent)
            current_run -= connected_set
            all_adjacent -= current_run
            connected_set.update(current_run)
        if not all_adjacent:
            max_distance = 0.0
            furthest_pair = (province, adj)
            for province1, province2 in combinations(clique, 2):
                distance = shapely.distance(province1.geometry, province2.geometry)
                if distance > max_distance:
                    max_distance = distance
                    furthest_pair = (province1, province2)
            warnings.append(f"Provinces {province.name}, {adj.name}, {third.name}, " +
                            f"and {fourth.name} all border each other " +
                            f"Furthest pair: {furthest_pair[0].name}, {furthest_pair[1].name}; distance: {max_distance:.2f}")
    return warnings

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
    parser_result = get_parser(variant)
    if isinstance(parser_result, str):
        return parser_result
    board: Board = parser_result.parse()

    global _override_adjacencies
    _override_adjacencies = set()
    for province_name, province_data in board.data.get("overrides", {}).get("provinces", {}).items():
        for adjacency in province_data.get("adjacencies", []):
            _override_adjacencies.add((province_name, adjacency))

    warnings = []
    visited_provinces = set()

    # High Seas
    for province in [p for p in board.provinces if p.name[-1] in "23456789"]:
        try:
            comp_province = board.get_province(province.name[:-1] + "1")
            # Two high seas' adjacencies should differ by only each other
            if (comp_province.adjacencies.get_all() ^ province.adjacencies.get_all()
                != {province, comp_province}):
                warnings.append(f"Province {province.name} and {comp_province.name} have different adjacencies")
            visited_provinces.add(province)
        except ValueError:
            warnings.append(f"Province {province.name} is named like a high seas province " +
                            f"but {province.name[:-1]}1 was not found")
    high_provinces = set(visited_provinces)

    for province in board.provinces - high_provinces:
        if len(province.adjacencies.get_all()) == 0:
            warnings.append(f"Province {province.name} has no adjacencies")
        for adj in _get_adjacent_geom(province) - visited_provinces:
            warning = _check_missing_adjacencies(province, adj, visited_provinces)
            if warning is not None:
                warnings.append(warning)
        visited_provinces.add(province)

    # We should expect some number of loops due to the board edge at the very least
    if len(warnings) == board.data.get("expected_loops", 1):
        warnings = []

    visited_provinces = high_provinces
    for province in board.provinces - high_provinces:
        visited_adjacent = set()
        for adj in _get_adjacent_geom(province) - visited_provinces:
            warnings.extend(_check_cliques(province, adj, visited_provinces | visited_adjacent))
            visited_adjacent.add(adj)
        visited_provinces.add(province)

    return "\n".join(warnings) if warnings else "No adjacency issues found"
