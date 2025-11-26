from __future__ import annotations

from abc import abstractmethod
from enum import Enum
from typing import TYPE_CHECKING
import logging

from shapely import Polygon, MultiPolygon

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from DiploGM.models import player
    from DiploGM.models import unit
    from DiploGM.models.unit import UnitType

class ProvinceType(Enum):
    LAND = 1
    ISLAND = 2
    SEA = 3
    IMPASSIBLE = 4


class Province():
    def __init__(
        self,
        name: str,
        coordinates: Polygon | MultiPolygon,
        primary_unit_coordinates: dict[UnitType | str, tuple[float, float]],
        retreat_unit_coordinates: dict[UnitType | str, tuple[float, float]],
        province_type: ProvinceType,
        has_supply_center: bool,
        adjacent: set[Province],
        fleet_adjacent: set[tuple[Province, str | None]] | dict[str, set[tuple[Province, str | None]]],
        core: player.Player | None,
        owner: player.Player | None,
        local_unit: unit.Unit | None,  # TODO: probably doesn't make sense to init with a unit
    ):
        self.name: str = name
        self.geometry: Polygon | MultiPolygon = coordinates
        self.primary_unit_coordinates: dict[UnitType | str, tuple[float, float]] = primary_unit_coordinates
        self.retreat_unit_coordinates: dict[UnitType | str, tuple[float, float]] = retreat_unit_coordinates
        self.type: ProvinceType = province_type
        self.has_supply_center: bool = has_supply_center
        self.adjacent: set[Province] = adjacent
        self.fleet_adjacent: set[tuple[Province, str | None]] | dict[str, set[tuple[Province, str | None]]] = fleet_adjacent
        self.impassible_adjacent: set[Province] = set()
        self.corer: player.Player | None = None
        self.core: player.Player | None = core
        self.half_core: player.Player | None = None
        self.owner: player.Player | None = owner
        self.unit: unit.Unit | None = local_unit
        self.dislodged_unit: unit.Unit | None = None
        self.nonadjacent_coasts: set[str] = set()

        # primary/retreat unit coordinates are of the form {unit_type/coast: (x, y)}
        # all_locs/all_rets are of the form {unit_type/coast: set((x, y), (x2, y2), ...)}
        # This assumes that only fleet units have to deal with multiple coasts
        # TODO: Bundle primary and retreat coordinates into a single structure
        self.all_locs = {}
        self.all_rets = {}
        if primary_unit_coordinates:
            self.all_locs = {key: {value} for key, value in self.primary_unit_coordinates.items()}
        if retreat_unit_coordinates:
            self.all_rets = {key: {value} for key, value in self.retreat_unit_coordinates.items()}

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Province {self.name}"
    
    def get_name(self, coast: str | None = None):
        if coast in self.fleet_adjacent:
            return f"{self.name} {coast}"
        return self.name
    
    def get_primary_unit_coordinates(self, unit_type: UnitType, coast = None) -> tuple[float, float]:
        if coast in self.primary_unit_coordinates:
            return self.primary_unit_coordinates[coast]
        elif unit_type in self.primary_unit_coordinates:
            return self.primary_unit_coordinates[unit_type]
        return (0, 0)

    def get_retreat_unit_coordinates(self, unit_type: UnitType, coast = None) -> tuple[float, float]:
        if coast in self.retreat_unit_coordinates:
            return self.retreat_unit_coordinates[coast]
        elif unit_type in self.retreat_unit_coordinates:
            return self.retreat_unit_coordinates[unit_type]
        return (0, 0)
    
    def set_unit_coordinate(self, coord, is_primary, unit_type, coast = None):
        # Set default cooordinate if none are found
        if coord is None:
            coord = (0, 0)

        if is_primary:
            unit_coords = self.primary_unit_coordinates
        else:
            unit_coords = self.retreat_unit_coordinates
        if coast:
            unit_coords[coast] = coord
        else:
            unit_coords[unit_type] = coord

    def get_owner(self) -> player.Player | None:
        return self.owner

    def get_unit(self) -> unit.Unit | None:
        return self.unit
    
    # Gets a set of all coasts if multiple exist, otherwise returns an empty set (== False)
    def get_multiple_coasts(self) -> set:
        if self.fleet_adjacent and isinstance(self.fleet_adjacent, dict):
            return set(self.fleet_adjacent.keys())
        return set()
    
    # Gets all provinces adjacent via fleet, optionally from a given coast
    # If there are multiple coasts, coast must be specified
    def get_coastal_adjacent(self, coast: str | None = None) -> set[tuple[Province, str | None]]:
        if coast:
            if not isinstance(self.fleet_adjacent, dict):
                raise ValueError(f"Province {self.name} does not have multiple coasts.")
            if coast not in self.fleet_adjacent:
                raise ValueError(f"Province {self.name} does not have a coast {coast}.")
            return self.fleet_adjacent[coast]
        if isinstance(self.fleet_adjacent, dict):
            raise ValueError(f"Province {self.name} has multiple coasts.")
        return self.fleet_adjacent
    
    # Checks if other province (and optionally coast) is adjacent via fleet
    def is_coastally_adjacent(self, other: Province | tuple[Province, str | None], coast: str | None = None) -> bool:
        if isinstance(other, tuple) and other[1] == None:
            dest = other[0]
        else:
            dest = other
        adjacencies = self.get_coastal_adjacent(coast)
        
        for province in adjacencies:
            if province == dest or (isinstance(province, tuple) and province[0] == dest):
                return True
        return False

    def set_adjacent(self, other: Province):
        if other.type == ProvinceType.IMPASSIBLE:
            self.impassible_adjacent.add(other)
        else:
            self.adjacent.add(other)

    # After all provinces have been initialised, set sea and island fleet adjacencies
    def set_coasts(self):
        """This should only be called once all province adjacencies have been set."""

        # Externally set, i. e. by json_cheats()
        if self.fleet_adjacent:
            return
        
        if isinstance(self.fleet_adjacent, dict):
            raise ValueError(f"Province {self.name} has multiple coasts and should have manually-assigned fleet adjacencies.")

        if self.type == ProvinceType.SEA or self.type == ProvinceType.ISLAND:
            for province in self.adjacent:
                self.fleet_adjacent.add((province, None))
            return
        
        self.fleet_adjacent = set()
        for province in self.adjacent:
            if province.type == ProvinceType.SEA or province.type == ProvinceType.ISLAND:
                self.fleet_adjacent.add((province, None))

        if not self.fleet_adjacent:
            # this is not a coastal province
            return

    # Once sea and island adjacencies have been set, set land adjacencies for fleets
    def set_adjacent_coasts(self):
        # Multi-coast provinces are currently manually set
        if isinstance(self.fleet_adjacent, dict):
            return
        # TODO: (BETA) this will generate false positives (e.g. mini province keeping 2 big province coasts apart)
        for province2 in self.adjacent:
            if province2.get_multiple_coasts():
                for coast2 in province2.get_multiple_coasts():
                    # Since we know the other province has manually-assigned coasts
                    if province2.is_coastally_adjacent(self, coast2):
                    # if (province2.get_name(coast2) not in self.nonadjacent_coasts
                    #     and Province.detect_coastal_connection(self, province2, coast2)):
                        self.fleet_adjacent.add((province2, coast2))
            elif self.type != ProvinceType.LAND:
                self.fleet_adjacent.add((province2, None))
            elif (province2.fleet_adjacent
                  and province2.get_name() not in self.nonadjacent_coasts
                  and Province.detect_coastal_connection(self, province2)):
                self.fleet_adjacent.add((province2, None))

    @staticmethod
    def detect_coastal_connection(p1: Province, p2: Province, coast: str | None = None):
        # multiple possible tripoints could happen if there was a scenario
        # where two canals were blocked from connecting on one side by a land province but not the other
        # or by multiple rainbow-shaped seas
        possible_tripoints = p1.get_coastal_adjacent() & p2.get_coastal_adjacent(coast)
        for possible_tripoint, _ in possible_tripoints:
            if possible_tripoint.type == ProvinceType.LAND:
                continue
            # check for situations where one of the provinces is situated in the other two

            if min(len(possible_tripoint.adjacent), len(p1.adjacent), len(p2.adjacent)) == 2:
                return True

            # the algorithm is as follows
            # connect all adjacent to the three provinces as possible
            # if they all connect, they form a ring around forcing connection
            # if not, they must form rings inside and outside, meaning there is no connection
            
            # initialise the process queue and the connection sets
            procqueue: list[Province] = []
            connected_sets: set[frozenset[Province]] = set()

            for adjacent in p1.adjacent | p1.impassible_adjacent | \
                            p2.adjacent | p2.impassible_adjacent | \
                            possible_tripoint.adjacent | possible_tripoint.impassible_adjacent:
                if adjacent not in (p1, p2, possible_tripoint):
                    procqueue.append(adjacent)
                    connected_sets.add(frozenset({adjacent}))
            
            def find_set_with_element(element):
                for subgraph in connected_sets:
                    if element in subgraph:
                        return subgraph
                raise Exception("Error in costal_connection algorithm")

            # we will retain the invariant that no two elements of connected_sets contain the same element
            for to_process in procqueue:
                for neighbor in to_process.adjacent:
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

            # find connected sets which are adjacent to tripoint and two provinces (so portugal is eliminated from contention if MAO, Gascony, and Spain nc are the locations being tested)
            # FIXME: this leads to false positives
            for candidate in connected_sets:
                needed_neighbors = set([p1, p2, possible_tripoint])

                for province in candidate:
                    needed_neighbors.difference_update(province.adjacent)

                if len(needed_neighbors) == 0:
                    l += 1

            # If there is 1, that means there was 1 ring (yes)
            # 2, there was two (no)
            # Else, something has gone wrong
            if l == 1:
                return True
            elif l != 2:
                logger.error(f"WARNING: len(connected_sets) should've been 1 or 2, but got {l}.\n"
                            f"hint: between coasts {p1} and {p2}, when looking at mutual sea {possible_tripoint}\n"
                            f"Final state: {connected_sets}")

        # no connection worked
        return False