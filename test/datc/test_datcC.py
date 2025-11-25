import unittest

from DiploGM.models.unit import UnitType
from test.utils import BoardBuilder

# These tests are based off https://webdiplomacy.net/doc/DATC_v3_0.html, with 
# https://github.com/diplomacy/diplomacy/blob/master/diplomacy/tests/test_datc.py being used as a reference as well.

# 6.C. TEST CASES, CIRCULAR MOVEMENT
class TestDATC_C(unittest.TestCase):
    def test_6_c_1(self):
        """ 6.C.1. TEST CASE, THREE ARMY CIRCULAR MOVEMENT
            Three units can change place, even in spring 1901.
            Turkey: F Ankara - Constantinople
            Turkey: A Constantinople - Smyrna
            Turkey: A Smyrna - Ankara
            All three units will move.
        """
        b = BoardBuilder()
        f_ankara = b.move(b.turkey, UnitType.FLEET, "Ankara", "Constantinople")
        a_constantinople = b.move(b.turkey, UnitType.ARMY, "Constantinople", "Smyrna")
        a_smyrna = b.move(b.turkey, UnitType.ARMY, "Smyrna", "Ankara")
        
        b.assertSuccess(f_ankara, a_constantinople, a_smyrna)
        b.moves_adjudicate(self)

    def test_6_c_2(self):
        """ 6.C.2. TEST CASE, THREE ARMY CIRCULAR MOVEMENT WITH SUPPORT
            Three units can change place, even when one gets support.
            Turkey: F Ankara - Constantinople
            Turkey: A Constantinople - Smyrna
            Turkey: A Smyrna - Ankara
            Turkey: A Bulgaria Supports F Ankara - Constantinople
            Of course the three units will move, but knowing how programs are written, this can confuse the adjudicator.
        """
        b = BoardBuilder()
        f_ankara = b.move(b.turkey, UnitType.FLEET, "Ankara", "Constantinople")
        a_constantinople = b.move(b.turkey, UnitType.ARMY, "Constantinople", "Smyrna")
        a_smyrna = b.move(b.turkey, UnitType.ARMY, "Smyrna", "Ankara")
        a_bulgaria = b.supportMove(b.turkey, UnitType.ARMY, "Bulgaria", f_ankara, "Constantinople")

        b.assertSuccess(f_ankara, a_constantinople, a_smyrna, a_bulgaria)
        b.moves_adjudicate(self)

    def test_6_c_3(self):
        """ 6.C.3. TEST CASE, A DISRUPTED THREE ARMY CIRCULAR MOVEMENT
            When one of the units bounces, the whole circular movement will hold.
            Turkey: F Ankara - Constantinople
            Turkey: A Constantinople - Smyrna
            Turkey: A Smyrna - Ankara
            Turkey: A Bulgaria - Constantinople
            Every unit will keep its place.
        """
        b = BoardBuilder()
        f_ankara = b.move(b.turkey, UnitType.FLEET, "Ankara", "Constantinople")
        a_constantinople = b.move(b.turkey, UnitType.ARMY, "Constantinople", "Smyrna")
        a_smyrna = b.move(b.turkey, UnitType.ARMY, "Smyrna", "Ankara")
        a_bulgaria = b.move(b.turkey, UnitType.ARMY, "Bulgaria", "Constantinople")

        b.assertFail(f_ankara, a_constantinople, a_smyrna, a_bulgaria)
        b.moves_adjudicate(self)

    def test_6_c_4(self):
        """ 6.C.4. TEST CASE, A CIRCULAR MOVEMENT WITH ATTACKED CONVOY
            When the circular movement contains an attacked convoy, the circular movement succeeds.
            The adjudication algorithm should handle attack of convoys before calculating circular movement.
            Austria: A Trieste - Serbia
            Austria: A Serbia - Bulgaria
            Turkey: A Bulgaria - Trieste
            Turkey: F Aegean Sea Convoys A Bulgaria - Trieste
            Turkey: F Ionian Sea Convoys A Bulgaria - Trieste
            Turkey: F Adriatic Sea Convoys A Bulgaria - Trieste
            Italy: F Naples - Ionian Sea
            The fleet in the Ionian Sea is attacked but not dislodged. The circular movement succeeds.
            The Austrian and Turkish armies will advance.
        """
        b = BoardBuilder()
        a_trieste = b.move(b.austria, UnitType.ARMY, "Trieste", "Serbia")
        a_serbia = b.move(b.austria, UnitType.ARMY, "Serbia", "Bulgaria")
        a_bulgaria = b.move(b.turkey, UnitType.ARMY, "Bulgaria", "Trieste")
        f_aegean_sea = b.convoy(b.turkey, "Aegean Sea", a_bulgaria, "Trieste")
        f_ionian_sea = b.convoy(b.turkey, "Ionian Sea", a_bulgaria, "Trieste")
        f_adriatic_sea = b.convoy(b.turkey, "Adriatic Sea", a_bulgaria, "Trieste")
        f_naples = b.move(b.italy, UnitType.FLEET, "Naples", "Ionian Sea")

        b.assertSuccess(a_trieste, a_serbia, a_bulgaria, f_aegean_sea, f_ionian_sea, f_adriatic_sea)
        b.assertFail(f_naples)
        b.moves_adjudicate(self)

    def test_6_c_5(self):
        """ 6.C.5. TEST CASE, A DISRUPTED CIRCULAR MOVEMENT DUE TO DISLODGED CONVOY
            When the circular movement contains a convoy, the circular movement is disrupted when the convoying
            fleet is dislodged. The adjudication algorithm should disrupt convoys before calculating circular movement.
            Austria: A Trieste - Serbia
            Austria: A Serbia - Bulgaria
            Turkey: A Bulgaria - Trieste
            Turkey: F Aegean Sea Convoys A Bulgaria - Trieste
            Turkey: F Ionian Sea Convoys A Bulgaria - Trieste
            Turkey: F Adriatic Sea Convoys A Bulgaria - Trieste
            Italy: F Naples - Ionian Sea
            Italy: F Tunis Supports F Naples - Ionian Sea
            Due to the dislodged convoying fleet, all Austrian and Turkish armies will not move.
        """
        b = BoardBuilder()
        a_trieste = b.move(b.austria, UnitType.ARMY, "Trieste", "Serbia")
        a_serbia = b.move(b.austria, UnitType.ARMY, "Serbia", "Bulgaria")
        a_bulgaria = b.move(b.turkey, UnitType.ARMY, "Bulgaria", "Trieste")

        f_aegean_sea = b.convoy(b.turkey, "Aegean Sea", a_bulgaria, "Trieste")
        f_ionian_sea = b.convoy(b.turkey, "Ionian Sea", a_bulgaria, "Trieste")
        f_adriatic_sea = b.convoy(b.turkey, "Adriatic Sea", a_bulgaria, "Trieste")

        f_naples = b.move(b.italy, UnitType.FLEET, "Naples", "Ionian Sea")
        f_tunis = b.supportMove(b.italy, UnitType.FLEET, "Tunis", f_naples, "Ionian Sea")
        b.assertFail(a_trieste, a_serbia, a_bulgaria, f_ionian_sea)
        b.assertSuccess(f_naples, f_tunis, f_aegean_sea, f_adriatic_sea)
        b.moves_adjudicate(self)

    def test_6_c_6(self):
        """ 6.C.6. TEST CASE, TWO ARMIES WITH TWO CONVOYS
            Two armies can swap places even when they are not adjacent.
            England: F North Sea Convoys A London - Belgium
            England: A London - Belgium
            France: F English Channel Convoys A Belgium - London
            France: A Belgium - London
            Both convoys should succeed.
        """
        b = BoardBuilder()
        a_london = b.move(b.england, UnitType.ARMY, "London", "Belgium")
        f_north_sea = b.convoy(b.england, "North Sea", a_london, "Belgium")
        a_belgium = b.move(b.france, UnitType.ARMY, "Belgium", "London")
        f_english_channel = b.convoy(b.england, "English Channel", a_belgium, "London")
        
        b.assertSuccess(a_london, f_north_sea, a_belgium, f_english_channel)
        b.moves_adjudicate(self)

    def test_6_c_7(self):
        """ 6.C.7. TEST CASE, DISRUPTED UNIT SWAP
            If in a swap one of the unit bounces, then the swap fails.
            England: F North Sea Convoys A London - Belgium
            England: A London - Belgium
            France: F English Channel Convoys A Belgium - London
            France: A Belgium - London
            France: A Burgundy - Belgium
            None of the units will succeed to move.
    """
        b = BoardBuilder()
        a_london = b.move(b.england, UnitType.ARMY, "London", "Belgium")
        f_north_sea = b.convoy(b.england, "North Sea", a_london, "Belgium")
        a_belgium = b.move(b.france, UnitType.ARMY, "Belgium", "London")
        f_english_channel = b.convoy(b.england, "English Channel", a_belgium, "London")
        a_burgundy = b.move(b.france, UnitType.ARMY, "Burgundy", "Belgium")

        b.assertSuccess(f_north_sea, f_english_channel)
        b.assertFail(a_london, a_belgium, a_burgundy)
        b.moves_adjudicate(self)