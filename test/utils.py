from DiploGM.models.board import Board
from DiploGM.manager import Manager
from DiploGM.models.order import (
    Core,
    Hold,
    Move,
    RetreatMove,
    ConvoyTransport,
    Support,
    Build,
    Disband,
)
from DiploGM.models.province import Province, ProvinceType
from DiploGM.models.unit import UnitType, Unit
from DiploGM.models.player import Player
from DiploGM.models.turn import Turn
from DiploGM.adjudicator.adjudicator import MovesAdjudicator, RetreatsAdjudicator, BuildsAdjudicator, ResolutionState, Resolution

import unittest

# Allows for specifying units, uses the classic diplomacy board as that is used by DATC 
# Only implements the subset of adjacencies necessary to run the DATC tests as of now
class BoardBuilder():
    def __init__(self, season: str = "Spring"):
        manager = Manager()
        try:
            manager.total_delete(0)
        except:
            pass
        manager.create_game(0, "classic")
        self.board: Board = manager.get_board(0)
        self.board.delete_all_units()

        # here an illegal move is one that is caught and turned into a hold order, which includes supports and convoys 
        # which are missing the corresponding part
        # a failed move is one that is resolved by the adjudicator as failed, succeeded moved is similar
        self._listIllegal: list[Province] = []
        self._listNotIllegal: list[Province] = []
        self._listFail: list[Province] = []
        self._listSuccess: list[Province] = []
        self._listDislodge: list[Province] = []
        self._listNotDislodge: list[Province] = []
        self._listForcedDisband: list[Unit] = []
        self._listNotForcedDisband: list[Unit] = []

        self._listCreated: list[Province] = []
        self._listNotCreated: list[Province] = []

        self._listDisbanded: list[Province] = []
        self._listNotDisbanded: list[Province] = []

        self.build_count = None

        self.france = self.board.get_player("France")
        self.england = self.board.get_player("England")
        self.germany = self.board.get_player("Germany")
        self.italy = self.board.get_player("Italy")
        self.austria = self.board.get_player("Austria")
        self.russia = self.board.get_player("Russia")
        self.turkey = self.board.get_player("Turkey")

    def army(self, land: str, player: Player) -> Unit:
        province, _ = self.board.get_province_and_coast(land)
        self.board.delete_unit(province)
        assert province.type == ProvinceType.LAND or ProvinceType.ISLAND

        unit = Unit(
            UnitType.ARMY,
            player,
            province,
            None,
            None
        )

        unit.player = player
        province.unit = unit

        player.units.add(unit)
        self.board.units.add(unit)

        return unit
    
    def fleet(self, loc: str, player: Player):
        province, coast = self.board.get_province_and_coast(loc)
        self.board.delete_unit(province)
        unit = Unit(
            UnitType.FLEET,
            player,
            province,
            coast,
            None
        )

        province.unit = unit
        player.units.add(unit)
        self.board.units.add(unit)

        return unit

    def move(self, player: Player, type: UnitType, place: str, to: str) -> Unit:

        if (type == UnitType.FLEET):
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        end, end_coast = self.board.get_province_and_coast(to)
        order = Move(end, end_coast)
        unit.order = order

        return unit

    def core(self, player: Player, type: UnitType, place: str) -> Unit:
        if (type == UnitType.FLEET):
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        order = Core()
        unit.order = order

        return unit

    def convoy(self, player: Player, place: str, source: Unit, to: str) -> Unit:
        unit = self.fleet(place, player)
        
        order = ConvoyTransport(source.province, self.board.get_province(to))
        unit.order = order

        return unit
    
    def supportMove(self, player: Player, type: UnitType, place: str, source: Unit, to: str) -> Unit:
        if (type == UnitType.FLEET):
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        end, end_coast = self.board.get_province_and_coast(to)
        order = Support(source.province, end, end_coast)
        unit.order = order

        return unit

    def hold(self, player: Player, type: UnitType, place: str) -> Unit:
        if (type == UnitType.FLEET):
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        order = Hold()
        unit.order = order

        return unit

    def supportHold(self, player: Player, type: UnitType, place: str, source: Unit) -> Unit:
        if (type == UnitType.FLEET):
            unit = self.fleet(place, player)
        else:
            unit = self.army(place, player)

        order = Support(source.province, source.province)
        unit.order = order

        return unit
    
    def retreat(self, unit: Unit, place: str):
        unit.order = RetreatMove(self.board.get_province(place))
        pass

    def build(self, player: Player, *places: tuple[UnitType, str]):
        for cur_build in places:
            province, coast = self.board.get_province_and_coast(cur_build[1])
            player.build_orders.add(Build(province, cur_build[0], coast))

    def disband(self, player: Player, *places: str):
        player.build_orders |= set([Disband(self.board.get_province(place)) for place in places])

    def player_core(self, player: Player, *places: str):
        for place in places:
            province = self.board.get_province(place)
            province.owner = player
            province.core = player
            province.unit = None

    def assertIllegal(self, *units: Unit):
        for unit in units:
            loc = unit.province
            self._listIllegal.append(loc)

    def assertNotIllegal(self, *units: Unit):
        for unit in units:
            loc = unit.province
            self._listNotIllegal.append(loc)

    def assertFail(self, *units: Unit):
        for unit in units:
            loc = unit.province
            self._listFail.append(loc)

    def assertSuccess(self, *units: Unit):
        for unit in units:
            loc = unit.province
            self._listSuccess.append(loc)

    def assertDislodge(self, *units: Unit):
        for unit in units:
            loc = unit.province
            self._listDislodge.append(loc)

    def assertNotDislodge(self, *units: Unit):
        for unit in units:
            loc = unit.province
            self._listNotDislodge.append(loc)

    # used for retreat testing
    def assertForcedDisband(self, *units: Unit):
        for unit in units:
            self._listForcedDisband.append(unit)

    def assertNotForcedDisband(self, *units: Unit):
        for unit in units:
            self._listNotForcedDisband.append(unit)

    # used for retreat testing
    def assertCreated(self, *provinces: Province):
        for province in provinces:
            self._listCreated.append(province)

    def assertNotCreated(self, *provinces: Province):
        for province in provinces:
            self._listNotCreated.append(province)

    def assertDisbanded(self, *provinces: Province):
        for province in provinces:
            self._listDisbanded.append(province)

    def assertNotDisbanded(self, *provinces: Province):
        for province in provinces:
            self._listNotDisbanded.append(province)

    def assertBuildCount(self, count: int):
        self.build_count = count

    # used when testing the move phases of things
    def moves_adjudicate(self, test: unittest.TestCase):
        adj = MovesAdjudicator(board=self.board)
        
        for order in adj.orders:
            order.state = ResolutionState.UNRESOLVED

        for order in adj.orders:
            adj._resolve_order(order)

        # for order in adj.orders:
        #     print(order)

        illegal_units = []
        succeeded_units = []
        failed_units = []

        for illegal_order in adj.failed_or_invalid_units:
            illegal_units.append(illegal_order.location)

        for order in adj.orders:
            if (order.resolution == Resolution.SUCCEEDS):
                succeeded_units.append(order.current_province)
            else:
                failed_units.append(order.current_province)

        for illegal in self._listIllegal:
            test.assertTrue(illegal in illegal_units, f"Move by {illegal.name} expected to be illegal")
        for notillegal in self._listNotIllegal:
            test.assertTrue(notillegal not in illegal_units, f"Move by {notillegal.name} expected not to be illegal")

        for fail in self._listFail:
            test.assertTrue(fail in failed_units, f"Move by {fail.name} expected to fail")
        for succeed in self._listSuccess:
            test.assertTrue(succeed in succeeded_units, f"Move by {succeed.name} expected to succeed")

        adj._update_board()

        for dislodge in self._listDislodge:
            test.assertTrue(dislodge.dislodged_unit != None, f"Expected dislodged unit in {dislodge.name}")
        for notdislodge in self._listNotDislodge:
            test.assertTrue(notdislodge.dislodged_unit == None, f"Expected no dislodged unit in {notdislodge.name}")


        return adj
    
    def retreats_adjudicate(self, test: unittest.TestCase):
        adj = RetreatsAdjudicator(board=self.board)
        adj.run()
        for disband in self._listForcedDisband:
            test.assertTrue(disband not in disband.player.units, f"Expected unit {disband} to be removed")
        for notDisband in self._listNotForcedDisband:
            test.assertTrue(notDisband in notDisband.player.units, f"Expected unit {notDisband} to not be removed")

    def builds_adjudicate(self, test: unittest.TestCase):
        current_units = self.board.units.copy()
        
        adj = BuildsAdjudicator(board=self.board)
        adj.run()

        # print(current_units)
        # print(self.board.units)

        created_units = self.board.units - current_units
        created_provinces = map(lambda x: x.province, created_units)
        removed_units = current_units - self.board.units
        removed_provinces = map(lambda x: x.province, removed_units)
        
        for create in self._listCreated:
            test.assertTrue(create in created_provinces, f"Expected province {create} to have unit created")
        for notCreated in self._listNotCreated:
            test.assertTrue(notCreated not in created_provinces, f"Expected province {notCreated} to not have unit created")

        for disband in self._listDisbanded:
            test.assertTrue(disband in removed_provinces, f"Expected province {disband} to have unit removed")
        for notDisband in self._listNotDisbanded:
            test.assertTrue(notDisband not in removed_provinces, f"Expected province {notDisband} to not have unit removed")

        test.assertTrue(self.build_count == None or (len(self.board.units) - len(current_units)) == self.build_count, f"Expected {self.build_count} builds, got {len(self.board.units) - len(current_units)} builds")
