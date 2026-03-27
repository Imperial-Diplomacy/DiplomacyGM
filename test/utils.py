"""Test utilities for building board states and running adjudication assertions."""

import unittest

from DiploGM.models.board import Board
from DiploGM.manager import Manager
from DiploGM.models.order import (
    Core,
    Transform,
    Hold,
    Move,
    RetreatMove,
    ConvoyTransport,
    Support,
    UnitOrder,
    Build,
    Disband,
)
from DiploGM.models.province import Province, ProvinceType
from DiploGM.models.unit import DPAllocation, UnitType, Unit
from DiploGM.models.player import Player
from DiploGM.adjudicator.defs import ResolutionState, Resolution
from DiploGM.adjudicator.builds_adjudicator import BuildsAdjudicator
from DiploGM.adjudicator.moves_adjudicator import MovesAdjudicator
from DiploGM.adjudicator.retreats_adjudicator import RetreatsAdjudicator

# Allows for specifying units, uses the classic diplomacy board as that is used by DATC
class BoardBuilder():
    """Helper for building test board states with units, orders, and assertions.

    Uses the classic diplomacy board. Provides methods to place units,
    assign orders, and run adjudication with assertions.
    """

    def __init__(self):
        """Initialise a fresh board with no units.
        """
        manager = Manager()
        try:
            manager.total_delete(0)
        except:
            pass
        manager.create_game(0, "classic")
        self.board: Board = manager.get_board(0)
        self.board.delete_all_units()

        # here an illegal move is one that is caught and turned into a hold order,
        # which includes supports and convoys which are missing the corresponding part
        # a failed move is one that is resolved by the adjudicator as failed
        result_list_keys = {"illegal","not_illegal",
                            "fail", "success",
                            "dislodge", "not_dislodge",
                            "forced_disband", "not_forced_disband",
                            "created", "not_created",
                            "disbanded", "not_disbanded"}
        self.result_lists = {key: [] for key in result_list_keys}

        self.build_count = None

        self.players = {}
        for player in ["Austria", "England", "France", "Germany", "Italy", "Russia", "Turkey"]:
            self.players[player] = self.board.get_player(player)
            if self.players[player] is None:
                raise RuntimeError(f"Player {player} not found on board")

    def army(self, land: str, player: Player | None) -> Unit:
        """Place an army on the board.

        Args:
            land: The name of the land province to place the army in.
            player: The player who owns the army.

        Returns:
            The created army unit.
        """
        province, _ = self.board.get_province_and_coast(land)
        self.board.delete_unit(province)
        assert province.type == ProvinceType.LAND or ProvinceType.ISLAND

        unit = Unit(
            UnitType.ARMY,
            player,
            province,
            None
        )

        unit.player = player
        province.unit = unit

        if player is not None:
            player.units.add(unit)
        self.board.units.add(unit)

        return unit

    def fleet(self, loc: str, player: Player | None) -> Unit:
        """Place a fleet on the board.

        Args:
            loc: The name of the province (with optional coast) to place the fleet in.
            player: The player who owns the fleet.

        Returns:
            The created fleet unit.
        """
        province, coast = self.board.get_province_and_coast(loc)
        self.board.delete_unit(province)
        unit = Unit(
            UnitType.FLEET,
            player,
            province,
            coast
        )

        province.unit = unit
        if player is not None:
            player.units.add(unit)
        self.board.units.add(unit)

        return unit

    def move(self, player: Player, unit_type: UnitType, place: str, to: str) -> Unit:
        """Create a unit with a move order.

        Args:
            player: The player who owns the unit.
            unit_type: The type of unit.
            place: The province the unit starts in.
            to: The name of the province the unit is moving to.

        Returns:
            The created unit with its move order set.
        """

        if unit_type == UnitType.FLEET:
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        end, end_coast = self.board.get_province_and_coast(to)
        order = Move(end, end_coast)
        unit.order = order

        return unit

    def core(self, player: Player, unit_type: UnitType, place: str) -> Unit:
        """Create a unit with a core order.

        Args:
            player: The player who owns the unit.
            unit_type: The type of unit.
            place: The name of the province the unit is in.

        Returns:
            The created unit with its core order set.
        """
        if unit_type == UnitType.FLEET:
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        order = Core()
        unit.order = order

        return unit

    def transform(self, player: Player, unit_type: UnitType, place: str, coast: str | None = None) -> Unit:
        """Create a unit with a transform order.

        Args:
            player: The player who owns the unit.
            unit_type: The type of unit.
            place: The name of the province the unit is in.
            coast: Optional destination coast of the transformation.

        Returns:
            The created unit with its transform order set.
        """
        if unit_type == UnitType.FLEET:
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        order = Transform(coast)
        unit.order = order

        return unit

    def convoy(self, player: Player, place: str, source: Unit, to: str) -> Unit:
        """Create a fleet with a convoy transport order.

        Args:
            player: The player who owns the fleet.
            place: The name of the sea province the fleet is in.
            source: The unit being convoyed.
            to: The name of the destination province for the convoyed unit.

        Returns:
            The created fleet with its convoy order set.
        """
        unit = self.fleet(place, player)
        order = ConvoyTransport(source.province, self.board.get_province(to))
        unit.order = order

        return unit

    def support_move(self, player: Player, unit_type: UnitType, place: str, source: Unit, to: str) -> Unit:
        """Create a unit with a support-move order.

        Args:
            player: The player who owns the supporting unit.
            unit_type: The type of unit.
            place: The name of the province the supporting unit is in.
            source: The unit being supported.
            to: The name of the province the supported unit is moving to.

        Returns:
            The created unit with its support order set.
        """
        if unit_type == UnitType.FLEET:
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        end, end_coast = self.board.get_province_and_coast(to)
        order = Support(source.province, end, end_coast)
        unit.order = order

        return unit

    def hold(self, player: Player, unit_type: UnitType, place: str) -> Unit:
        """Create a unit with a hold order.

        Args:
            player: The player who owns the unit.
            unit_type: The type of unit.
            place: The name of the province the unit is in.

        Returns:
            The created unit with its hold order set.
        """
        if unit_type == UnitType.FLEET:
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        order = Hold()
        unit.order = order

        return unit

    def support_hold(self, player: Player, unit_type: UnitType, place: str, source: Unit) -> Unit:
        """Create a unit with a support-hold order.

        Args:
            player: The player who owns the supporting unit.
            unit_type: The type of unit.
            place: The province the supporting unit is in.
            source: The unit being supported in hold.

        Returns:
            The created unit with its support order set.
        """
        if unit_type == UnitType.FLEET:
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        order = Support(source.province, source.province)
        unit.order = order

        return unit

    def dp_order(self, player: Player, unit: Unit, points: int, order: UnitOrder) -> Unit:
        """Create a DP order for a unit.

        Args:
            player: The player is giving the DP order.
            unit: The unit to assign the DP order to.
            points: The number of DP points to assign.
            order: The DP order to assign.

        Returns:
            The unit with its DP order set.
        """
        unit.dp_allocations[player.name] = DPAllocation(points, order)
        return unit

    def retreat(self, unit: Unit, place: str):
        """Assign a retreat order to an existing unit.

        Args:
            unit: The unit that is retreating.
            place: The name of the province to retreat to.
        """
        unit.order = RetreatMove(self.board.get_province(place))

    def build(self, player: Player, *places: tuple[UnitType, str]):
        """Add build orders for a player.

        Args:
            player: The player issuing the build orders.
            places: Tuples of (unit_type, province_name) for each build.
        """
        for cur_build in places:
            province, coast = self.board.get_province_and_coast(cur_build[1])
            player.build_orders.add(Build(province, cur_build[0], coast))

    def disband(self, player: Player, *places: str):
        """Add disband orders for a player.

        Args:
            player: The player issuing the disband orders.
            places: Province names of units to disband.
        """
        player.build_orders |= set([Disband(self.board.get_province(place)) for place in places])

    def player_core(self, player: Player, *places: str):
        """Set provinces as owned and cored by a player.

        Args:
            player: The player to own and core the provinces.
            places: Province names to own and core.
        """
        for place in places:
            province = self.board.get_province(place)
            province.owner = player
            province.core_data.core = player
            province.unit = None

    def assert_illegal(self, *units: Unit):
        """Register units whose orders are expected to be illegal."""
        for unit in units:
            loc = unit.province
            self.result_lists["illegal"].append(loc)

    def assert_not_illegal(self, *units: Unit):
        """Register units whose orders are expected to be not illegal."""
        for unit in units:
            loc = unit.province
            self.result_lists["not_illegal"].append(loc)

    def assert_fail(self, *units: Unit):
        """Register units whose orders are expected to fail."""
        for unit in units:
            loc = unit.province
            self.result_lists["fail"].append(loc)

    def assert_success(self, *units: Unit):
        """Register units whose orders are expected to succeed."""
        for unit in units:
            loc = unit.province
            self.result_lists["success"].append(loc)

    def assert_dislodge(self, *units: Unit):
        """Register units expected to be dislodged."""
        for unit in units:
            loc = unit.province
            self.result_lists["dislodge"].append(loc)

    def assert_not_dislodge(self, *units: Unit):
        """Register units expected to not be dislodged."""
        for unit in units:
            loc = unit.province
            self.result_lists["not_dislodge"].append(loc)

    # used for retreat testing
    def assert_forced_disband(self, *units: Unit):
        """Register units expected to be forcibly disbanded during retreats."""
        for unit in units:
            self.result_lists["forced_disband"].append(unit)

    def assert_not_forced_disband(self, *units: Unit):
        """Register units expected to not be forcibly disbanded during retreats."""
        for unit in units:
            self.result_lists["not_forced_disband"].append(unit)

    # used for retreat testing
    def assert_created(self, *provinces: Province):
        """Register provinces expected to have a unit created during builds."""
        for province in provinces:
            self.result_lists["created"].append(province)

    def assert_not_created(self, *provinces: Province):
        """Register provinces expected to not have a unit created during builds."""
        for province in provinces:
            self.result_lists["not_created"].append(province)

    def assert_disbanded(self, *provinces: Province):
        """Register provinces expected to have their unit disbanded during builds."""
        for province in provinces:
            self.result_lists["disbanded"].append(province)

    def assert_not_disbanded(self, *provinces: Province):
        """Register provinces expected to not have their unit disbanded during builds."""
        for province in provinces:
            self.result_lists["not_disbanded"].append(province)

    def assert_build_count(self, count: int):
        """Set the expected net change in unit count after builds adjudication.

        Args:
            count: The expected difference (builds minus disbands).
        """
        self.build_count = count

    # used when testing the move phases of things
    def moves_adjudicate(self, test: unittest.TestCase) -> MovesAdjudicator:
        """Run moves adjudication and verify all registered assertions.

        Args:
            test: The test case instance used for assertions.

        Returns:
            The MovesAdjudicator after resolution and board update.
        """
        adj = MovesAdjudicator(board=self.board)

        for order in adj.orders:
            order.state = ResolutionState.UNRESOLVED

        for order in adj.orders:
            adj._resolve_order(order)

        for order in adj.orders:
            print(order)

        illegal_units = []
        succeeded_units = []
        failed_units = []

        for illegal_order in adj.failed_or_invalid_units:
            illegal_units.append(illegal_order.location)

        for order in adj.orders:
            if order.resolution == Resolution.SUCCEEDS:
                succeeded_units.append(order.current_province)
            else:
                failed_units.append(order.current_province)

        for illegal in self.result_lists["illegal"]:
            test.assertTrue(illegal in illegal_units,
                            f"Move by {illegal.name} expected to be illegal")
        for notillegal in self.result_lists["not_illegal"]:
            test.assertTrue(notillegal not in illegal_units,
                            f"Move by {notillegal.name} expected not to be illegal")

        for fail in self.result_lists["fail"]:
            test.assertTrue(fail in failed_units,
                            f"Move by {fail.name} expected to fail")
        for succeed in self.result_lists["success"]:
            test.assertTrue(succeed in succeeded_units,
                            f"Move by {succeed.name} expected to succeed")

        adj._update_board()

        for dislodge in self.result_lists["dislodge"]:
            test.assertTrue(dislodge.dislodged_unit is not None,
                            f"Expected dislodged unit in {dislodge.name}")
        for notdislodge in self.result_lists["not_dislodge"]:
            test.assertTrue(notdislodge.dislodged_unit is None,
                            f"Expected no dislodged unit in {notdislodge.name}")


        return adj

    def retreats_adjudicate(self, test: unittest.TestCase):
        """Run retreats adjudication and verify all registered assertions.

        Args:
            test: The test case instance used for assertions.
        """
        adj = RetreatsAdjudicator(board=self.board)
        adj.run()
        for disband in self.result_lists["forced_disband"]:
            test.assertTrue(disband.player is None
                            or disband not in disband.player.units,
                            f"Expected unit {disband} to be removed")
        for not_disband in self.result_lists["not_forced_disband"]:
            test.assertTrue(not_disband.player is not None
                            and not_disband in not_disband.player.units,
                            f"Expected unit {not_disband} to not be removed")

    def builds_adjudicate(self, test: unittest.TestCase):
        """Run builds adjudication and verify all registered assertions.

        Args:
            test: The test case instance used for assertions.
        """
        current_units = self.board.units.copy()

        adj = BuildsAdjudicator(board=self.board)
        adj.run()

        # print(current_units)
        # print(self.board.units)

        created_units = self.board.units - current_units
        created_provinces = map(lambda x: x.province, created_units)
        removed_units = current_units - self.board.units
        removed_provinces = map(lambda x: x.province, removed_units)

        for create in self.result_lists["created"]:
            test.assertTrue(create in created_provinces,
                            f"Expected province {create} to have unit created")
        for not_created in self.result_lists["not_created"]:
            test.assertTrue(not_created not in created_provinces,
                            f"Expected province {not_created} to not have unit created")

        for disband in self.result_lists["disbanded"]:
            test.assertTrue(disband in removed_provinces,
                            f"Expected province {disband} to have unit removed")
        for not_disband in self.result_lists["not_disbanded"]:
            test.assertTrue(not_disband not in removed_provinces,
                            f"Expected province {not_disband} to not have unit removed")

        actual = len(self.board.units) - len(current_units)
        test.assertTrue((expected := self.build_count) is None or actual == expected,
                        f"Expected {expected} builds, got {actual} builds")
