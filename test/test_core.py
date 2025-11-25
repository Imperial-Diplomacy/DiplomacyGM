import unittest

from DiploGM.models.unit import UnitType
from test.utils import BoardBuilder

class TestCore(unittest.TestCase):
    def test_core_1(self):
        """ 
            Coring should fail for non-SCs.
            Germany: A Rumania Cores
            Rumania shouldn't be half-cored by Germany.
        """
        b = BoardBuilder()
        a_rumania = b.core(b.germany, UnitType.ARMY, "Rumania")
        p_rumania = b.board.get_province("Rumania")

        b.assertIllegal(a_rumania)
        b.moves_adjudicate(self)
        self.assertFalse(p_rumania.half_core == b.germany, "Rumania shouldn't be cored")

    def test_core_2(self):
        """ 
            Coring should fail for not owned provinces.
            Germany doesn't own Holland.
            Germany: A Holland Cores
            Holland shouldn't be half-cored by Germany.
        """
        b = BoardBuilder()
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")
        p_holland = b.board.get_province("Holland")

        b.assertIllegal(a_holland)
        b.moves_adjudicate(self)
        self.assertFalse(p_holland.half_core == b.germany, "Holland shouldn't be cored")

    def test_core_3(self):
        """ 
            Coring should turn empty cores into half cores.
            Germany owns Holland.
            Germany: A Holland Cores
            Holland should be half-cored by Germany.
        """
        b = BoardBuilder()
        p_holland = b.board.get_province("Holland")
        p_holland.owner = b.germany
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")

        b.assertSuccess(a_holland)
        b.moves_adjudicate(self)
        self.assertTrue(p_holland.half_core == b.germany, "Holland should be half-cored")

    def test_core_4(self):
        """ 
            Coring should turn half cores into full cores.
            Germany owns Holland.
            Germany: A Holland Cores
            Holland should be cored by Germany.
        """
        b = BoardBuilder()
        p_holland = b.board.get_province("Holland")
        p_holland.owner = b.germany
        p_holland.half_core = b.germany
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")

        b.assertSuccess(a_holland)
        b.moves_adjudicate(self)
        self.assertTrue(p_holland.core == b.germany, "Holland should be cored")

    def test_core_5(self):
        """ 
            Coring should fail when the coring unit is attacked.
            Germany owns Holland.
            Germany: A Holland Cores
            France: A Belgium - Holland
            Holland shouldn't be half-cored by Germany.
        """
        b = BoardBuilder()
        p_holland = b.board.get_province("Holland")
        p_holland.owner = b.germany
        p_holland.half_core = b.germany
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")
        a_belgium = b.move(b.france, UnitType.ARMY, "Belgium", "Holland")

        b.assertFail(a_holland, a_belgium)
        b.assertNotIllegal(a_holland, a_belgium)
        b.moves_adjudicate(self)
        
        self.assertFalse(p_holland.core == b.germany, "Holland shouldn't be cored")

    def test_core_5(self):
        """ 
            Coring should fail when the attacking unit is of the same nationality.
            Germany owns Holland.
            Germany: A Holland Cores
            Germany: A Belgium - Holland
            Holland shouldn't be half-cored by Germany.
        """
        b = BoardBuilder()
        p_holland = b.board.get_province("Holland")
        p_holland.owner = b.germany
        p_holland.half_core = b.germany
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")
        a_belgium = b.move(b.germany, UnitType.ARMY, "Belgium", "Holland")

        b.assertFail(a_holland, a_belgium)
        b.assertNotIllegal(a_holland, a_belgium)
        b.moves_adjudicate(self)
        
        self.assertFalse(p_holland.core == b.germany, "Holland shouldn't be half-cored")

    def test_core_6(self):
        """ 
            Coring should fail when attacked by convoy.
            Germany owns Holland.
            Germany: A Holland Cores
            England: A London - Holland
            England: F North Sea Convoys A London - Holland
            Holland should be half-cored by Germany.
        """
        b = BoardBuilder()
        p_holland = b.board.get_province("Holland")
        p_holland.owner = b.germany
        p_holland.half_core = b.germany
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")
        a_london = b.move(b.england, UnitType.ARMY, "London", "Holland")
        f_north_sea = b.convoy(b.england, "North Sea", a_london, "Holland")

        b.assertFail(a_holland, a_london)
        b.assertNotIllegal(a_holland, f_north_sea, a_london)
        b.moves_adjudicate(self)
        
        self.assertFalse(p_holland.core == b.germany, "Holland shouldn't be half-cored")

    def test_core_7(self):
        """ 
            Coring should fail when attacked by convoy of the same nationality.
            Germany owns Holland.
            Germany: A Holland Cores
            Germany: A London - Holland
            England: F North Sea Convoys A London - Holland
            Holland should be half-cored by Germany.
        """
        b = BoardBuilder()
        p_holland = b.board.get_province("Holland")
        p_holland.owner = b.germany
        p_holland.half_core = b.germany
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")
        a_london = b.move(b.germany, UnitType.ARMY, "London", "Holland")
        f_north_sea = b.convoy(b.england, "North Sea", a_london, "Holland")

        b.assertFail(a_holland, a_london)
        b.assertNotIllegal(a_holland, f_north_sea, a_london)
        b.moves_adjudicate(self)
        
        self.assertFalse(p_holland.core == b.germany, "Holland shouldn't be half-cored")


    def test_core_8(self):
        """ 
            Coring should succeed when only attacked by a disrupted convoy.
            Germany owns Holland.
            Germany: A Holland Cores
            England: A London - Holland
            Holland should be half-cored by Germany.
        """
        b = BoardBuilder()
        p_holland = b.board.get_province("Holland")
        p_holland.owner = b.germany
        p_holland.half_core = b.germany
        a_holland = b.core(b.germany, UnitType.ARMY, "Holland")
        a_london = b.move(b.england, UnitType.ARMY, "London", "Holland")

        b.assertSuccess(a_holland)
        b.moves_adjudicate(self)
        
        self.assertTrue(p_holland.core == b.germany, "Holland should be half-cored")