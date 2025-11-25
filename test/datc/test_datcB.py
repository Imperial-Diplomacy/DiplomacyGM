import unittest

from DiploGM.models.unit import UnitType
from test.utils import BoardBuilder

# These tests are based off https://webdiplomacy.net/doc/DATC_v3_0.html, with 
# https://github.com/diplomacy/diplomacy/blob/master/diplomacy/tests/test_datc.py being used as a reference as well.

# 6.B. TEST CASES, COASTAL ISSUES
class TestDATC_B(unittest.TestCase):
    def test_6_b_1(self):
        """ 6.B.1. TEST CASE, MOVING WITH UNSPECIFIED COAST WHEN COAST IS NECESSARY
            Coast is significant in this case:
            France: 
            F Portugal - Spain
            Move should fail.
        """
        b = BoardBuilder()
        f_portugal = b.move(b.france, UnitType.FLEET, "Portugal", "Spain")

        b.assertFail(f_portugal)
        b.moves_adjudicate(self)

    def test_6_b_2(self):
        """ 6.B.2. TEST CASE, MOVING WITH UNSPECIFIED COAST WHEN COAST IS NOT NECESSARY
            There is only one coast possible in this case:
            France: 
            F Gascony - Spain
            Since the North Coast is the only coast that can be reached, it seems logical that a move is attempted to the north coast of Spain. See issue 4.B.2.
            I prefer that an attempt is made to the only possible coast, the north coast of Spain.
        """
        b = BoardBuilder()
        f_gascony = b.move(b.france, UnitType.FLEET, "Gascony", "Spain")

        b.assertSuccess(f_gascony)
        b.moves_adjudicate(self)

    def test_6_b_3(self):
        """ 6.B.3. TEST CASE, MOVING WITH WRONG COAST WHEN COAST IS NOT NECESSARY
            If only one coast is possible, but the wrong coast can be specified.
            France: F Gascony - Spain(sc)
            If the rules are played very clemently, a move will be attempted to the north coast of Spain.
            However, since this order is very clear and precise, it is more common that the move fails (see 4.B.3).
            I prefer that the move fails.
        """
        b = BoardBuilder()
        f_gascony = b.move(b.france, UnitType.FLEET, "Gascony", "Spain sc")

        b.assertFail(f_gascony)
        b.moves_adjudicate(self)

    def test_6_b_4(self):
        """ 6.B.4. TEST CASE, SUPPORT TO UNREACHABLE COAST ALLOWED
            A fleet can give support to a coast where it can not go.
            France: F Gascony - Spain(nc)
            France: F Marseilles Supports F Gascony - Spain(nc)
            Italy: F Western Mediterranean - Spain(sc)
            Although the fleet in Marseilles can not go to the north coast it can still
            support targeting the north coast. So, the support is successful, the move of the fleet
            in Gasgony succeeds and the move of the Italian fleet fails.
        """
        b = BoardBuilder()
        f_gascony = b.move(b.france, UnitType.FLEET, "Gascony", "Spain nc")
        f_marseilles = b.supportMove(b.france, UnitType.FLEET, "Marseilles", f_gascony, "Spain nc")
        f_western_mediterranean = b.move(b.italy, UnitType.FLEET, "Western Mediterranean Sea", "Spain sc")

        b.assertSuccess(f_gascony)
        b.assertSuccess(f_marseilles)
        b.assertFail(f_western_mediterranean)
        b.moves_adjudicate(self)

    def test_6_b_5(self):
        """ 6.B.5. TEST CASE, SUPPORT FROM UNREACHABLE COAST NOT ALLOWED
            A fleet can not give support to an area that can not be reached from the current coast of the fleet.
            France: F Marseilles - Gulf of Lyon
            France: F Spain(nc) Supports F Marseilles - Gulf of Lyon
            Italy: F Gulf of Lyon Hold
            The Gulf of Lyon can not be reached from the North Coast of Spain. Therefore, the support of
            Spain is invalid and the fleet in the Gulf of Lyon is not dislodged.
        """
        b = BoardBuilder()
        f_marseilles = b.move(b.france, UnitType.FLEET, "Marseilles", "Gulf of Lyon")
        f_spain_nc = b.supportMove(b.france, UnitType.FLEET, "Spain nc", f_marseilles, "Gulf of Lyon")
        f_gulf_of_lyon = b.hold(b.italy, UnitType.FLEET, "Gulf of Lyon")

        b.assertIllegal(f_spain_nc)
        b.assertFail(f_marseilles)
        b.moves_adjudicate(self)
    
    def test_6_b_6(self):
        """ 6.B.6. TEST CASE, SUPPORT CAN BE CUT WITH OTHER COAST
            Support can be cut from the other coast.
            England: F Irish Sea Supports F North Atlantic Ocean - Mid-Atlantic Ocean
            England: F North Atlantic Ocean - Mid-Atlantic Ocean
            France: F Spain(nc) Supports F Mid-Atlantic Ocean
            France: F Mid-Atlantic Ocean Hold
            Italy: F Gulf of Lyon - Spain(sc)
            The Italian fleet in the Gulf of Lyon will cut the support in Spain. That means
            that the French fleet in the Mid Atlantic Ocean will be dislodged by the English fleet
            in the North Atlantic Ocean.
        """
        b = BoardBuilder()
        f_north_atlantic_ocean = b.move(b.england, UnitType.FLEET, "North Atlantic Ocean", "Mid-Atlantic Ocean")
        f_irish_sea = b.supportMove(b.england, UnitType.FLEET, "Irish Sea", f_north_atlantic_ocean, "Mid-Atlantic Ocean")
        f_mid_atlantic_ocean = b.hold(b.france, UnitType.FLEET, "Mid-Atlantic Ocean")
        f_spain_nc = b.supportHold(b.france, UnitType.FLEET, "Spain nc", f_mid_atlantic_ocean)
        f_gulf_of_lyon = b.move(b.italy, UnitType.FLEET, "Gulf of Lyon", "Spain sc")

        b.assertFail(f_gulf_of_lyon)
        b.assertFail(f_spain_nc)
        b.assertSuccess(f_north_atlantic_ocean)
        b.assertDislodge(f_mid_atlantic_ocean)
        b.moves_adjudicate(self)

    # NOT APPLICABLE 6_b_7; TEST CASE, SUPPORTING WITH UNSPECIFIED COAST

    # NOT APPLICABLE 6_b_8; TEST CASE, SUPPORTING WITH UNSPECIFIED COAST WHEN ONLY ONE COAST IS POSSIBLE

    # NOT APPLICABLE 6_b_9; TEST CASE, SUPPORTING WITH WRONG COAST

    # NOT APPLICABLE 6_b_10; TEST CASE, UNIT ORDERED WITH WRONG COAST

    # NOT APPLICABLE 6_b_11; TEST CASE, COAST CAN NOT BE ORDERED TO CHANGE

    # NOT APPLICABLE 6_b_12; TEST CASE, ARMY MOVEMENT WITH COASTAL SPECIFICATION

    def test_6_b_13(self):
        """ 6.B.13. TEST CASE, COASTAL CRAWL NOT ALLOWED
            If a fleet is leaving a sector from a certain coast while in the opposite direction another fleet
            is moving to another coast of the sector, it is still a head to head battle. This has been decided in
            the great revision of the 1961 rules that resulted in the 1971 rules.
            Turkey: F Bulgaria(sc) - Constantinople
            Turkey: F Constantinople - Bulgaria(ec)
            Both moves fail.
        """
        b = BoardBuilder()
        f_bulgaria_sc = b.move(b.turkey, UnitType.FLEET, "Bulgaria sc", "Constantinople")
        f_constantinople = b.move(b.turkey, UnitType.FLEET, "Constantinople", "Bulgaria ec")
        
        b.assertFail(f_bulgaria_sc)
        b.assertFail(f_constantinople)
        b.moves_adjudicate(self)

    # NOT APPLICABLE 6_b_14; TEST CASE, BUILDING WITH UNSPECIFIED COAST
