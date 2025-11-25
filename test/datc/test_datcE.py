import unittest

from DiploGM.models.unit import UnitType
from test.utils import BoardBuilder

# These tests are based off https://webdiplomacy.net/doc/DATC_v3_0.html, with 
# https://github.com/diplomacy/diplomacy/blob/master/diplomacy/tests/test_datc.py being used as a reference as well.

# 6.E. TEST CASES, HEAD-TO-HEAD BATTLES AND BELEAGUERED GARRISON
class TestDATC_E(unittest.TestCase):
    def test_6_e_1(self):
        """ 6.E.1. TEST CASE, DISLODGED UNIT HAS NO EFFECT ON ATTACKERS AREA
            An army can follow.
            Germany: A Berlin - Prussia
            Germany: F Kiel - Berlin
            Germany: A Silesia Supports A Berlin - Prussia
            Russia: A Prussia - Berlin
            The army in Kiel will move to Berlin.
        """
        b = BoardBuilder()
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Prussia")
        f_kiel = b.move(b.germany, UnitType.FLEET, "Kiel", "Berlin")
        a_silesia = b.supportMove(b.germany, UnitType.ARMY, "Silesia", a_berlin, "Prussia")
        a_prussia = b.move(b.russia, UnitType.ARMY, "Prussia", "Berlin")

        b.assertSuccess(f_kiel, a_berlin, a_silesia)
        b.assertFail(a_prussia)
        b.moves_adjudicate(self)

    def test_6_e_2(self):
        """ 6.E.2. TEST CASE, NO SELF DISLODGEMENT IN HEAD TO HEAD BATTLE
            Self dislodgement is not allowed. This also counts for head to head battles.
            Germany: A Berlin - Kiel
            Germany: F Kiel - Berlin
            Germany: A Munich Supports A Berlin - Kiel
            No unit will move.
        """
        b = BoardBuilder()
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Kiel")
        f_kiel = b.move(b.germany, UnitType.FLEET, "Kiel", "Berlin")
        a_munich = b.supportMove(b.germany, UnitType.ARMY, "Munich", a_berlin, "Kiel")

        b.assertFail(a_berlin, f_kiel)
        b.assertSuccess(a_munich)
        b.moves_adjudicate(self)

    def test_6_e_3(self):
        """ 6.E.3. TEST CASE, NO HELP IN DISLODGING OWN UNIT
            To help a foreign power to dislodge own unit in head to head battle is not possible.
            Germany: A Berlin - Kiel
            Germany: A Munich Supports F Kiel - Berlin
            England: F Kiel - Berlin
            No unit will move.
        """
        b = BoardBuilder()
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Kiel")
        f_kiel = b.move(b.germany, UnitType.FLEET, "Kiel", "Berlin")
        a_munich = b.supportMove(b.germany, UnitType.ARMY, "Munich", f_kiel, "Berlin")

        b.assertFail(a_berlin, f_kiel)
        b.assertSuccess(a_munich)
        b.moves_adjudicate(self)

    def test_6_e_4(self):
        """ 6.E.4. TEST CASE, NON-DISLODGED LOSER HAS STILL EFFECT
            If in an unbalanced head to head battle the loser is not dislodged, it has still effect on the area of
            the attacker.
            Germany: F Holland - North Sea
            Germany: F Heligoland Bight Supports F Holland - North Sea
            Germany: F Skagerrak Supports F Holland - North Sea
            France: F North Sea - Holland
            France: F Belgium Supports F North Sea - Holland
            England: F Edinburgh Supports F Norwegian Sea - North Sea
            England: F Yorkshire Supports F Norwegian Sea - North Sea
            England: F Norwegian Sea - North Sea
            Austria: A Kiel Supports A Ruhr - Holland
            Austria: A Ruhr - Holland
            The French fleet in the North Sea is not dislodged due to the beleaguered garrison. Therefore,
            the Austrian army in Ruhr will not move to Holland.
        """
        b = BoardBuilder()
        f_holland = b.move(b.germany, UnitType.FLEET, "Holland", "North Sea")
        f_heligoland_bight = b.supportMove(b.germany, UnitType.FLEET, "Heligoland Bight", f_holland, "North Sea")
        f_skagerrak = b.supportMove(b.germany, UnitType.FLEET, "Skagerrak", f_holland, "North Sea")
        f_north_sea = b.move(b.france, UnitType.FLEET, "North Sea", "Holland")
        f_belgium = b.supportMove(b.france, UnitType.FLEET, "Belgium", f_north_sea, "Holland")
        f_norwegian_sea = b.move(b.england, UnitType.FLEET, "Norwegian Sea", "North Sea")
        f_edinburgh = b.supportMove(b.england, UnitType.FLEET, "Edinburgh", f_norwegian_sea, "North Sea")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", f_norwegian_sea, "North Sea")
        a_ruhr = b.move(b.austria, UnitType.ARMY, "Ruhr", "Holland")
        a_kiel = b.supportMove(b.austria, UnitType.ARMY, "Kiel", a_ruhr, "Holland")

        b.assertSuccess(f_heligoland_bight, f_skagerrak, f_edinburgh, f_yorkshire, a_kiel, f_belgium)
        b.assertFail(f_holland, f_norwegian_sea, f_north_sea, a_ruhr)
        b.assertNotDislodge(f_holland, f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_5(self):
        """ 6.E.5. TEST CASE, LOSER DISLODGED BY ANOTHER ARMY HAS STILL EFFECT
            If in an unbalanced head to head battle the loser is dislodged by a unit not part of the head to head
            battle, the loser has still effect on the place of the winner of the head to head battle.
            Germany: F Holland - North Sea
            Germany: F Heligoland Bight Supports F Holland - North Sea
            Germany: F Skagerrak Supports F Holland - North Sea
            France: F North Sea - Holland
            France: F Belgium Supports F North Sea - Holland
            England: F Edinburgh Supports F Norwegian Sea - North Sea
            England: F Yorkshire Supports F Norwegian Sea - North Sea
            England: F Norwegian Sea - North Sea
            England: F London Supports F Norwegian Sea - North Sea
            Austria: A Kiel Supports A Ruhr - Holland
            Austria: A Ruhr - Holland
            The French fleet in the North Sea is dislodged but not by the German fleet in Holland. Therefore,
            the French fleet can still prevent that the Austrian army in Ruhr will move to Holland. So, the Austrian
            move in Ruhr fails and the German fleet in Holland is not dislodged.
        """
        b = BoardBuilder()
        f_holland = b.move(b.germany, UnitType.FLEET, "Holland", "North Sea")
        f_heligoland_bight = b.supportMove(b.germany, UnitType.FLEET, "Heligoland Bight", f_holland, "North Sea")
        f_skagerrak = b.supportMove(b.germany, UnitType.FLEET, "Skagerrak", f_holland, "North Sea")
        f_north_sea = b.move(b.france, UnitType.FLEET, "North Sea", "Holland")
        f_belgium = b.supportMove(b.france, UnitType.FLEET, "Belgium", f_north_sea, "Holland")
        f_norwegian_sea = b.move(b.england, UnitType.FLEET, "Norwegian Sea", "North Sea")
        f_edinburgh = b.supportMove(b.england, UnitType.FLEET, "Edinburgh", f_norwegian_sea, "North Sea")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", f_norwegian_sea, "North Sea")
        f_london = b.supportMove(b.england, UnitType.FLEET, "London", f_norwegian_sea, "North Sea")
        a_ruhr = b.move(b.austria, UnitType.ARMY, "Ruhr", "Holland")
        a_kiel = b.supportMove(b.austria, UnitType.ARMY, "Kiel", a_ruhr, "Holland")

        b.assertSuccess(f_heligoland_bight, f_skagerrak, f_edinburgh, f_yorkshire, a_kiel, f_belgium, f_london, f_norwegian_sea)
        b.assertFail(f_holland, f_north_sea, a_ruhr)
        b.assertNotDislodge(f_holland)
        b.assertDislodge(f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_6(self):
        """ 6.E.6. TEST CASE, NOT DISLODGE BECAUSE OF OWN SUPPORT HAS STILL EFFECT
            If in an unbalanced head to head battle the loser is not dislodged because the winner had help of a unit
            of the loser, the loser has still effect on the area of the winner.
            Germany: F Holland - North Sea
            Germany: F Heligoland Bight Supports F Holland - North Sea
            France: F North Sea - Holland
            France: F Belgium Supports F North Sea - Holland
            France: F English Channel Supports F Holland - North Sea
            Austria: A Kiel Supports A Ruhr - Holland
            Austria: A Ruhr - Holland
            Although the German force from Holland to North Sea is one larger than the French force from North Sea
            to Holland,
            the French fleet in the North Sea is not dislodged, because one of the supports on the German movement is
            French.
            Therefore, the Austrian army in Ruhr will not move to Holland.
        """
        b = BoardBuilder()
        f_holland = b.move(b.germany, UnitType.FLEET, "Holland", "North Sea")
        f_heligoland_bight = b.supportMove(b.germany, UnitType.FLEET, "Heligoland Bight", f_holland, "North Sea")
        f_north_sea = b.move(b.france, UnitType.FLEET, "North Sea", "Holland")
        f_belgium = b.supportMove(b.france, UnitType.FLEET, "Belgium", f_north_sea, "Holland")
        f_english_channel = b.supportMove(b.france, UnitType.FLEET, "English Channel", f_holland, "North Sea")
        a_ruhr = b.move(b.austria, UnitType.ARMY, "Ruhr", "Holland")
        a_kiel = b.supportMove(b.austria, UnitType.ARMY, "Kiel", a_ruhr, "Holland")

        b.assertSuccess(f_heligoland_bight, a_kiel, f_belgium)
        b.assertFail(f_holland, f_north_sea, a_ruhr)
        b.assertNotDislodge(f_holland, f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_7(self):
        """ 6.E.7. TEST CASE, NO SELF DISLODGEMENT WITH BELEAGUERED GARRISON
            An attempt to self dislodgement can be combined with a beleaguered garrison. Such self dislodgment is still
            not possible.
            England: F North Sea Hold
            England: F Yorkshire Supports F Norway - North Sea
            Germany: F Holland Supports F Heligoland Bight - North Sea
            Germany: F Heligoland Bight - North Sea
            Russia: F Skagerrak Supports F Norway - North Sea
            Russia: F Norway - North Sea
            Although the Russians beat the German attack (with the support of Yorkshire) and the two Russian fleets
            are enough to dislodge the fleet in the North Sea, the fleet in the North Sea is not dislodged, since it
            would not be dislodged if the English fleet in Yorkshire would not give support. According to the DPTG the
            fleet in the North Sea would be dislodged. The DPTG is incorrect in this case.
        """
        b = BoardBuilder()
        f_north_sea = b.hold(b.england, UnitType.FLEET, "North Sea")
        f_heligoland_bight = b.move(b.germany, UnitType.FLEET, "Heligoland Bight", "North Sea")
        f_holland = b.supportMove(b.germany, UnitType.FLEET, "Holland", f_heligoland_bight, "North Sea")
        f_norway = b.move(b.russia, UnitType.FLEET, "Norway", "North Sea")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", f_norway, "North Sea")
        f_skagerrak = b.supportMove(b.russia, UnitType.FLEET, "Skagerrak", f_norway, "North Sea")

        b.assertSuccess(f_holland, f_yorkshire, f_skagerrak)
        b.assertFail(f_norway, f_heligoland_bight)
        b.assertNotDislodge(f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_8(self):
        """ 6.E.8. TEST CASE, NO SELF DISLODGEMENT WITH BELEAGUERED GARRISON AND HEAD TO HEAD BATTLE
            Similar to the previous test case, but now the beleaguered fleet is also engaged in a head to head battle.
            England: F North Sea - Norway
            England: F Yorkshire Supports F Norway - North Sea
            Germany: F Holland Supports F Heligoland Bight - North Sea
            Germany: F Heligoland Bight - North Sea
            Russia: F Skagerrak Supports F Norway - North Sea
            Russia: F Norway - North Sea
            Again, none of the fleets move.
        """
        b = BoardBuilder()
        f_north_sea = b.move(b.england, UnitType.FLEET, "North Sea", "Norway")
        f_heligoland_bight = b.move(b.germany, UnitType.FLEET, "Heligoland Bight", "North Sea")
        f_holland = b.supportMove(b.germany, UnitType.FLEET, "Holland", f_heligoland_bight, "North Sea")
        f_norway = b.move(b.russia, UnitType.FLEET, "Norway", "North Sea")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", f_norway, "North Sea")
        f_skagerrak = b.supportMove(b.russia, UnitType.FLEET, "Skagerrak", f_norway, "North Sea")

        b.assertSuccess(f_holland, f_yorkshire, f_skagerrak)
        b.assertFail(f_norway, f_heligoland_bight, f_north_sea)
        b.assertNotDislodge(f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_9(self):
        """ 6.E.9. TEST CASE, ALMOST SELF DISLODGEMENT WITH BELEAGUERED GARRISON
            Similar to the previous test case, but now the beleaguered fleet is moving away.
            England: F North Sea - Norwegian Sea
            England: F Yorkshire Supports F Norway - North Sea
            Germany: F Holland Supports F Heligoland Bight - North Sea
            Germany: F Heligoland Bight - North Sea
            Russia: F Skagerrak Supports F Norway - North Sea
            Russia: F Norway - North Sea
            Both the fleet in the North Sea and the fleet in Norway move.
        """
        b = BoardBuilder()
        f_north_sea = b.move(b.england, UnitType.FLEET, "North Sea", "Norwegian Sea")
        f_heligoland_bight = b.move(b.germany, UnitType.FLEET, "Heligoland Bight", "North Sea")
        f_holland = b.supportMove(b.germany, UnitType.FLEET, "Holland", f_heligoland_bight, "North Sea")
        f_norway = b.move(b.russia, UnitType.FLEET, "Norway", "North Sea")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", f_norway, "North Sea")
        f_skagerrak = b.supportMove(b.russia, UnitType.FLEET, "Skagerrak", f_norway, "North Sea")

        b.assertSuccess(f_holland, f_yorkshire, f_skagerrak, f_north_sea, f_norway)
        b.assertFail(f_heligoland_bight)
        b.assertNotDislodge(f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_10(self):
        """ 6.E.10. TEST CASE, ALMOST CIRCULAR MOVEMENT WITH NO SELF DISLODGEMENT WITH BELEAGUERED GARRISON
            Similar to the previous test case, but now the beleaguered fleet is in circular movement with the weaker
            attacker. So, the circular movement fails.
            England: F North Sea - Denmark
            England: F Yorkshire Supports F Norway - North Sea
            Germany: F Holland Supports F Heligoland Bight - North Sea
            Germany: F Heligoland Bight - North Sea
            Germany: F Denmark - Heligoland Bight
            Russia: F Skagerrak Supports F Norway - North Sea
            Russia: F Norway - North Sea
            There is no movement of fleets.
        """
        b = BoardBuilder()
        f_north_sea = b.move(b.england, UnitType.FLEET, "North Sea", "Denmark")
        f_heligoland_bight = b.move(b.germany, UnitType.FLEET, "Heligoland Bight", "North Sea")
        f_holland = b.supportMove(b.germany, UnitType.FLEET, "Holland", f_heligoland_bight, "North Sea")
        f_norway = b.move(b.russia, UnitType.FLEET, "Norway", "North Sea")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", f_norway, "North Sea")
        f_skagerrak = b.supportMove(b.russia, UnitType.FLEET, "Skagerrak", f_norway, "North Sea")
        f_denmark = b.move(b.germany, UnitType.FLEET, "Denmark", "Heligoland Bight")

        b.assertSuccess(f_holland, f_yorkshire, f_skagerrak)
        b.assertFail(f_heligoland_bight, f_north_sea, f_denmark, f_norway)
        b.assertNotDislodge(f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_11(self):
        """ 6.E.11. TEST CASE, NO SELF DISLODGEMENT WITH BELEAGUERED GARRISON, UNIT SWAP WITH ADJACENT CONVOYING AND
            TWO COASTS
            Similar to the previous test case, but now the beleaguered fleet is in a unit swap with the stronger
            attacker. So, the unit swap succeeds. To make the situation more complex, the swap is on an area with
            two coasts.
            France: A Spain - Portugal via Convoy
            France: F Mid-Atlantic Ocean Convoys A Spain - Portugal
            France: F Gulf of Lyon Supports F Portugal - Spain(nc)
            Germany: A Marseilles Supports A Gascony - Spain
            Germany: A Gascony - Spain
            Italy: F Portugal - Spain(nc)
            Italy: F Western Mediterranean Supports F Portugal - Spain(nc)
            The unit swap succeeds. Note that due to the success of the swap, there is no beleaguered garrison anymore.
        """
        b = BoardBuilder()
        a_spain = b.move(b.france, UnitType.ARMY, "Spain", "Portugal")
        f_portugal = b.move(b.italy, UnitType.FLEET, "Portugal", "Spain nc")
        f_western_mediterranean = b.supportMove(b.italy, UnitType.FLEET, "Western Mediterranean Sea", f_portugal, "Spain nc")
        f_mid_atlantic_ocean = b.convoy(b.france, "Mid-Atlantic Ocean", a_spain, "Portugal")
        f_gulf_of_lyon = b.supportMove(b.france, UnitType.FLEET, "Gulf of Lyon", f_portugal, "Spain nc")
        a_gascony = b.move(b.germany, UnitType.ARMY, "Gascony", "Spain")
        a_marseilles = b.supportMove(b.germany, UnitType.ARMY, "Marseilles", a_gascony, "Spain")

        b.assertSuccess(a_spain, f_portugal, f_western_mediterranean, f_gulf_of_lyon, f_mid_atlantic_ocean, a_marseilles)
        b.assertFail(a_gascony)
        b.moves_adjudicate(self)

    def test_6_e_12(self):
        """ 6.E.12. TEST CASE, SUPPORT ON ATTACK ON OWN UNIT CAN BE USED FOR OTHER MEANS
            A support on an attack on your own unit has still effect. It can prevent that another army will dislodge
            the unit.
            Austria: A Budapest - Rumania
            Austria: A Serbia Supports A Vienna - Budapest
            Italy: A Vienna - Budapest
            Russia: A Galicia - Budapest
            Russia: A Rumania Supports A Galicia - Budapest
            The support of Serbia on the Italian army prevents that the Russian army in Galicia will advance.
            No army will move.
        """
        b = BoardBuilder()
        a_budapest = b.move(b.austria, UnitType.ARMY, "Budapest", "Rumania")
        a_vienna = b.move(b.italy, UnitType.ARMY, "Vienna", "Budapest")
        a_serbia = b.supportMove(b.austria, UnitType.ARMY, "Serbia", a_vienna, "Budapest")
        a_galicia = b.move(b.russia, UnitType.ARMY, "Galicia", "Budapest")
        a_rumania = b.supportMove(b.russia, UnitType.ARMY, "Rumania", a_galicia, "Budapest")

        b.assertFail(a_galicia, a_vienna, a_budapest)
        b.assertSuccess(a_serbia, a_rumania)
        b.assertNotDislodge(a_budapest)
        b.moves_adjudicate(self)

    def test_6_e_13(self):
        """ 6.E.13. TEST CASE, THREE WAY BELEAGUERED GARRISON
            In a beleaguered garrison from three sides, the adjudicator may not let two attacks fail and then let the
            third succeed.
            England: F Edinburgh Supports F Yorkshire - North Sea
            England: F Yorkshire - North Sea
            France: F Belgium - North Sea
            France: F English Channel Supports F Belgium - North Sea
            Germany: F North Sea Hold
            Russia: F Norwegian Sea - North Sea
            Russia: F Norway Supports F Norwegian Sea - North Sea
            None of the fleets move. The German fleet in the North Sea is not dislodged.
        """
        b = BoardBuilder()
        f_yorkshire = b.move(b.england, UnitType.FLEET, "Yorkshire", "North Sea")
        f_edinburgh = b.supportMove(b.england, UnitType.FLEET, "Edinburgh", f_yorkshire, "North Sea")
        f_belgium = b.move(b.france, UnitType.FLEET, "Belgium", "North Sea")
        f_english_channel = b.supportMove(b.france, UnitType.FLEET, "English Channel", f_belgium, "North Sea")
        f_north_sea = b.hold(b.germany, UnitType.FLEET, "North Sea")
        f_norwegian_sea = b.move(b.russia, UnitType.FLEET, "Norwegian Sea", "North Sea")
        f_norway = b.supportMove(b.russia, UnitType.FLEET, "Norway", f_norwegian_sea, "North Sea")

        b.assertSuccess(f_edinburgh, f_english_channel, f_norway)
        b.assertFail(f_yorkshire, f_belgium, f_norwegian_sea)
        b.assertNotDislodge(f_north_sea)
        b.moves_adjudicate(self)

    def test_6_e_14(self):
        """ 6.E.14. TEST CASE, ILLEGAL HEAD TO HEAD BATTLE CAN STILL DEFEND
            If in a head to head battle, one of the units makes an illegal move, than that unit has still the
            possibility to defend against attacks with strength of one.
            England: A Liverpool - Edinburgh
            Russia: F Edinburgh - Liverpool
            The move of the Russian fleet is illegal, but can still prevent the English army to enter Edinburgh. So,
            none of the units move.
        """
        b = BoardBuilder()
        a_liverpool = b.move(b.england, UnitType.ARMY, "Liverpool", "Edinburgh")
        f_edinburgh = b.move(b.russia, UnitType.FLEET, "Edinburgh", "Liverpool")

        b.assertIllegal(f_edinburgh)
        b.assertFail(a_liverpool)
        b.moves_adjudicate(self)

    def test_6_e_15(self):
        """ 6.E.15. TEST CASE, THE FRIENDLY HEAD TO HEAD BATTLE
            In this case both units in the head to head battle prevent that the other one is dislodged.
            England: F Holland Supports A Ruhr - Kiel
            England: A Ruhr - Kiel
            France: A Kiel - Berlin
            France: A Munich Supports A Kiel - Berlin
            France: A Silesia Supports A Kiel - Berlin
            Germany: A Berlin - Kiel
            Germany: F Denmark Supports A Berlin - Kiel
            Germany: F Heligoland Bight Supports A Berlin - Kiel
            Russia: F Baltic Sea Supports A Prussia - Berlin
            Russia: A Prussia - Berlin
            None of the moves succeeds. This case is especially difficult for sequence based adjudicators. They will
            start adjudicating the head to head battle and continue to adjudicate the attack on one of the units part
            of the head to head battle. In this self.process, one of the sides of the head to head battle might be
            cancelled out. This happens in the DPTG. If this is adjudicated according to the DPTG, the unit in Ruhr or
            in Prussia will advance (depending on the order the units are adjudicated). This is clearly a bug in the
            DPTG.
        """
        b = BoardBuilder()
        a_ruhr = b.move(b.england, UnitType.ARMY, "Ruhr", "Kiel")
        f_holland = b.supportMove(b.england, UnitType.FLEET, "Holland", a_ruhr, "Kiel")
        a_kiel = b.move(b.france, UnitType.ARMY, "Kiel", "Berlin")
        a_munich = b.supportMove(b.france, UnitType.ARMY, "Munich", a_kiel, "Berlin")
        a_silesia = b.supportMove(b.france, UnitType.ARMY, "Silesia", a_kiel, "Berlin")
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Kiel")
        f_denmark = b.supportMove(b.germany, UnitType.FLEET, "Denmark", a_berlin, "Kiel")
        f_heligoland_bight = b.supportMove(b.germany, UnitType.FLEET, "Heligoland Bight", a_berlin, "Kiel")
        a_prussia = b.move(b.russia, UnitType.ARMY, "Prussia", "Berlin")
        f_baltic_sea = b.supportMove(b.russia, UnitType.FLEET, "Baltic Sea", a_prussia, "Berlin")

        b.assertSuccess(f_holland, a_munich, a_silesia, f_denmark, f_heligoland_bight, f_baltic_sea)
        b.assertFail(a_ruhr, a_kiel, a_berlin, a_prussia)
        b.moves_adjudicate(self)
