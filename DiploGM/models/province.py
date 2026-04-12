"""The province module. Handles adjacencies, coordinates, and coasts."""
# TODO: We should separate geometric data about the province (coordinates, adjacencies)
# from game data (cores, ownership, units).
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
import logging

from shapely import Polygon, MultiPolygon
import shapely

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from DiploGM.models import player
    from DiploGM.models import unit
    from DiploGM.models.unit import UnitType

class ProvinceType(Enum):
    """Whether the province is land, sea, or somewhere in between."""
    LAND = 1
    ISLAND = 2
    SEA = 3

@dataclass
class ProvinceCore:
    """Information regarding the status of the province's cores."""
    core: player.Player | None = None
    half_core: player.Player | None = None
    corer: player.Player | None = None

@dataclass
class ProvinceAdjacency:
    """Contains adjacency information about a province.
    At some point this should be moved into a ProvinceGeom class or something."""
    adjacent: set[Province] = field(default_factory=set)
    fleet_adjacent: set[tuple[Province, str | None]] | dict[str, set[tuple[Province, str | None]]] \
                  = field(default_factory=set)
    nonadjacent_coasts: set[str] = field(default_factory=set)
    difficult_adjacencies: set[str] = field(default_factory=set)

@dataclass(frozen=True)
class UnitLocation:
    """Represents the coordinates and retreat coordinates of a unit in a province.
    A province might have multiple of these, usually if it's wrapping around the board."""
    primary_coordinate: tuple[float, float]
    retreat_coordinate: tuple[float, float]

class Province():
    """Represents a province on the map."""
    def __init__(
        self,
        name: str,
        coordinates: Polygon | MultiPolygon,
        province_type: ProvinceType,
    ):
        self.name: str = name
        self.geometry: Polygon | MultiPolygon = coordinates
        self.unit_coordinates: dict[str, UnitLocation] = {}
        self.type: ProvinceType = province_type
        self.is_impassable: bool = False
        self.can_convoy: bool = province_type == ProvinceType.SEA
        self.has_supply_center: bool = False
        self.owner: player.Player | None = None
        self.core_data: ProvinceCore = ProvinceCore()
        self.unit: unit.Unit | None = None
        self.dislodged_unit: unit.Unit | None = None
        self.adjacency_data: ProvinceAdjacency = ProvinceAdjacency()

        # primary/retreat unit coordinates are of the form {unit_type/coast: (x, y)}
        # all_locs/all_rets are of the form {unit_type/coast: set((x, y), (x2, y2), ...)}
        # This assumes that only fleet units have to deal with multiple coasts
        self.all_coordinates: dict[str, set[UnitLocation]] = {}

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Province {self.name}"

    def get_name(self, coast: str | None = None):
        """Gets the name of the province, including the coast if applicable."""
        if coast in self.adjacency_data.fleet_adjacent:
            return f"{self.name} {coast}"
        return self.name

    def get_owner_name(self) -> str | None:
        """Gets the name of the province's owner, 'Impassable' if it is impassable, or None if it has no owner."""
        if self.is_impassable:
            return "Impassable"
        if self.owner is None:
            return None
        return self.owner.name

    def get_unit_coordinates(self,
                             unit_type: UnitType,
                             coast: str | None = None,
                             is_retreat: bool = False) -> tuple[float, float]:
        """Gets the coordinates of a unit given its type, coast, and whether it's retreating."""
        index = coast if coast in self.unit_coordinates else unit_type.name
        if is_retreat:
            return (self.unit_coordinates[index].retreat_coordinate if index in self.unit_coordinates
                    else self.unit_coordinates.get("default", UnitLocation((0, 0), (0, 0))).retreat_coordinate)
        return (self.unit_coordinates[index].primary_coordinate if index in self.unit_coordinates
                else self.unit_coordinates.get("default", UnitLocation((0, 0), (0, 0))).primary_coordinate)

    def set_unit_coordinate(self,
                            coord: tuple[float, float] | None,
                            unit_type: UnitType,
                            is_retreat: bool = False,
                            coast: str | None = None):
        """Sets the coordinates of a unit given its type, coast, and whether it's retreating."""
        # Set default cooordinate if none are found
        center = shapely.centroid(self.geometry)
        center_coord = (center.x, center.y)
        coord = coord if coord else center_coord
        index = coast if coast else unit_type.name

        if is_retreat:
            self.unit_coordinates[index] = UnitLocation(
                primary_coordinate = (self.unit_coordinates[index].primary_coordinate
                                      if index in self.unit_coordinates else center_coord),
                retreat_coordinate = coord
            )
        else:
            self.unit_coordinates[index] = UnitLocation(
                primary_coordinate = coord,
                retreat_coordinate = (self.unit_coordinates[index].retreat_coordinate
                                      if index in self.unit_coordinates else center_coord)
            )

    def can_build(self, build_options) -> bool:
        """Checks to see if a unit can be built in this province given the game's build options."""
        if not self.has_supply_center or self.owner is None or self.unit is not None:
            return False
        if self.core_data.core == self.owner or build_options == "anywhere":
            return True
        if build_options == "control":
            for adj in self.adjacency_data.adjacent:
                if (not adj.is_impassable
                    and adj.type in (ProvinceType.LAND, ProvinceType.ISLAND)
                    and adj.owner != self.owner):
                    return False
            return True
        return False

    def get_multiple_coasts(self) -> set:
        """Gets a set of all coasts if multiple exist, otherwise returns an empty set (== False)"""
        if self.adjacency_data.fleet_adjacent and isinstance(self.adjacency_data.fleet_adjacent, dict):
            return set(self.adjacency_data.fleet_adjacent.keys())
        return set()

    def get_coastal_adjacent(self, coast: str | None = None) -> set[tuple[Province, str | None]]:
        """Gets all provinces adjacent via fleet, optionally from a given coast.
        If there are multiple coasts, coast must be specified."""
        if coast:
            if not isinstance(self.adjacency_data.fleet_adjacent, dict):
                raise ValueError(f"Province {self.name} does not have multiple coasts.")
            if coast not in self.adjacency_data.fleet_adjacent:
                raise ValueError(f"Province {self.name} does not have a coast {coast}.")
            return self.adjacency_data.fleet_adjacent[coast]
        if isinstance(self.adjacency_data.fleet_adjacent, dict):
            raise ValueError(f"Province {self.name} has multiple coasts.")
        return self.adjacency_data.fleet_adjacent

    def is_landlocked(self) -> bool:
        """Checks to see if the province is landlocked, i.e. has no fleet adjacencies."""
        return self.type == ProvinceType.LAND and not self.adjacency_data.fleet_adjacent

    def is_coastally_adjacent(self, other: Province | tuple[Province, str | None], coast: str | None = None) -> bool:
        """Checks to see if the other province is adjacent via fleet, optionally from a given coast."""
        if isinstance(other, tuple) and other[1] is None:
            dest = other[0]
        else:
            dest = other
        adjacencies = self.get_coastal_adjacent(coast)

        for province in adjacencies:
            if province == dest or (isinstance(province, tuple) and province[0] == dest):
                return True
        return False

    def set_adjacent(self, other: Province | tuple[Province, str | None]):
        """Manually sets two provinces as adjacent."""
        if isinstance(other, tuple):
            other = other[0]
        self.adjacency_data.adjacent.add(other)

    def get_distance(self, other: Province, max_distance: int = 100) -> int:
        """Gets the distance between two provinces in number of moves.
        max_distance is used if we only care if the provinces are within a certain distance."""
        visited = set()
        queue: list[tuple[Province, int]] = [(self, 0)]
        while queue:
            current, distance = queue.pop(0)
            if current.name == other.name:
                return distance
            if distance >= max_distance:
                continue
            visited.add(current)
            for neighbor in current.adjacency_data.adjacent:
                if neighbor not in visited and not neighbor.is_impassable:
                    queue.append((neighbor, distance + 1))
        return max_distance + 1

    def set_coasts(self):
        """After all provinces have been initialised, set sea and island fleet adjacencies.
        This should only be called once all province adjacencies have been set."""

        # Externally set, i. e. by json_cheats()
        if self.adjacency_data.fleet_adjacent:
            return

        if isinstance(self.adjacency_data.fleet_adjacent, dict):
            raise ValueError(f"Province {self.name} has multiple coasts " +
                             "and should have manually-assigned fleet adjacencies.")

        if self.type in (ProvinceType.SEA, ProvinceType.ISLAND):
            for province in self.adjacency_data.adjacent:
                self.adjacency_data.fleet_adjacent.add((province, None))
            return

        self.adjacency_data.fleet_adjacent = set()
        for province in self.adjacency_data.adjacent:
            if province.type in (ProvinceType.SEA, ProvinceType.ISLAND):
                self.adjacency_data.fleet_adjacent.add((province, None))

        if not self.adjacency_data.fleet_adjacent:
            # this is not a coastal province
            return

    def set_adjacent_coasts(self):
        """Once sea and island adjacencies have been set, set land adjacencies for fleets"""
        # Multi-coast provinces are currently manually set
        if isinstance(self.adjacency_data.fleet_adjacent, dict):
            return
        # TODO: (BETA) this will generate false positives (e.g. mini province keeping 2 big province coasts apart)
        for province2 in self.adjacency_data.adjacent:
            if province2.get_multiple_coasts():
                for coast2 in province2.get_multiple_coasts():
                    # Since we know the other province has manually-assigned coasts
                    if province2.is_coastally_adjacent(self, coast2):
                    # if (province2.get_name(coast2) not in self.nonadjacent_coasts
                    #     and Province.detect_coastal_connection(self, province2, coast2)):
                        self.adjacency_data.fleet_adjacent.add((province2, coast2))
            elif self.type != ProvinceType.LAND:
                self.adjacency_data.fleet_adjacent.add((province2, None))
            elif (province2.adjacency_data.fleet_adjacent
                  and province2.get_name() not in self.adjacency_data.nonadjacent_coasts
                  and Province.detect_coastal_connection(self, province2)):
                self.adjacency_data.fleet_adjacent.add((province2, None))

    @staticmethod
    def detect_coastal_connection(p1: Province, p2: Province, coast: str | None = None):
        """Detects whether two coastal provinces are actually connected via a common coast."""
        # multiple possible tripoints could happen if there was a scenario
        # where two canals were blocked from connecting on one side by a land province but not the other
        # or by multiple rainbow-shaped seas
        possible_tripoints = p1.get_coastal_adjacent() & p2.get_coastal_adjacent(coast)
        for possible_tripoint, _ in possible_tripoints:
            if possible_tripoint.type == ProvinceType.LAND:
                continue
            # check for situations where one of the provinces is situated in the other two

            if min(len(possible_tripoint.adjacency_data.adjacent),
                   len(p1.adjacency_data.adjacent),
                   len(p2.adjacency_data.adjacent)) == 2:
                return True

            # If the two provinces only share one adjacent province (the sea tile), they must be coastally adjacent
            if len(p1.adjacency_data.adjacent & p2.adjacency_data.adjacent) == 1:
                return True

            # the algorithm is as follows
            # connect all adjacent to the three provinces as possible
            # if they all connect, they form a ring around forcing connection
            # if not, they must form rings inside and outside, meaning there is no connection

            # initialise the process queue and the connection sets
            procqueue: list[Province] = []
            connected_sets: set[frozenset[Province]] = set()

            for adjacent in (p1.adjacency_data.adjacent |
                             p2.adjacency_data.adjacent |
                             possible_tripoint.adjacency_data.adjacent
                             ).difference({p1, p2, possible_tripoint}):
                procqueue.append(adjacent)
                connected_sets.add(frozenset({adjacent}))

            def find_set_with_element(element):
                for subgraph in connected_sets:
                    if element in subgraph:
                        return subgraph
                raise RuntimeError("Error in coastal_connection algorithm")

            # we will retain the invariant that no two elements of connected_sets contain the same element
            for to_process in procqueue:
                for neighbor in to_process.adjacency_data.adjacent:
                    # going further into or out of rings won't help us
                    if neighbor not in procqueue:
                        continue

                    # Now that we have found two connected subgraphs,
                    # we remove them and merge them
                    this = find_set_with_element(to_process)
                    other = find_set_with_element(neighbor)
                    connected_sets = connected_sets - {this, other}
                    connected_sets.add(this | other)

            l = 0

            # find connected sets which are adjacent to tripoint and two provinces(so portugal is eliminated
            # from contention if MAO, Gascony, and Spain nc are the locations being tested)
            # FIXME: this leads to false positives
            for candidate in connected_sets:
                needed_neighbors = set([p1, p2, possible_tripoint])

                for province in candidate:
                    needed_neighbors.difference_update(province.adjacency_data.adjacent)

                if len(needed_neighbors) == 0:
                    l += 1

            # If there is 1, that means there was 1 ring (yes)
            # 2, there was two (no)
            # Else, something has gone wrong
            if l == 1:
                return True
            if l != 2:
                logger.error(f"WARNING: len(connected_sets) should've been 1 or 2, but got {l}.\n"
                            f"hint: between coasts {p1} and {p2}, when looking at mutual sea {possible_tripoint}\n"
                            f"Final state: {connected_sets}")

        # no connection worked
        return False
