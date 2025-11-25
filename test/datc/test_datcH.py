import unittest

from DiploGM.models.order import (
    Move,
    ConvoyTransport,
    Support,
)
from DiploGM.models.unit import UnitType
from test.utils import BoardBuilder


# These tests are based off https://webdiplomacy.net/doc/DATC_v3_0.html, with 
# https://github.com/diplomacy/diplomacy/blob/master/diplomacy/tests/test_datc.py being used as a reference as well.

# 6.H. TEST CASES, RETREATING
class TestDATC_H(unittest.TestCase):
    def test_6_h_1(self):
        """ 6.H.1. TEST CASE, NO SUPPORTS DURING RETREAT
            Supports are not allowed in the retreat phase.
            Austria: F Trieste Hold
            Austria: A Serbia Hold
            Turkey: F Greece Hold
            Italy: A Venice Supports A Tyrolia - Trieste
            Italy: A Tyrolia - Trieste
            Italy: F Ionian Sea - Greece
            Italy: F Aegean Sea Supports F Ionian Sea - Greece
            The fleet in Trieste and the fleet in Greece are dislodged. If the retreat orders are as follows:
            Austria: F Trieste - Albania
            Austria: A Serbia Supports F Trieste - Albania
            Turkey: F Greece - Albania
            The Austrian support order is illegal. Both dislodged fleets are disbanded.
        """
        b = BoardBuilder()
        f_trieste = b.hold(b.austria, UnitType.FLEET, "Trieste")
        a_serbia = b.hold(b.austria, UnitType.ARMY, "Serbia")
        f_greece = b.hold(b.turkey, UnitType.FLEET, "Greece")
        a_tyrolia = b.move(b.italy, UnitType.ARMY, "Tyrolia", "Trieste")
        a_venice = b.supportMove(b.italy, UnitType.ARMY, "Venice", a_tyrolia, "Trieste")
        f_ionian_sea = b.move(b.italy, UnitType.FLEET, "Ionian Sea", "Greece")
        f_aegean_sea = b.supportMove(b.italy, UnitType.FLEET, "Aegean Sea", f_ionian_sea, "Greece")

        b.assertDislodge(f_trieste, f_greece)
        b.moves_adjudicate(self)

        b.retreat(f_trieste, "Albania")
        a_serbia.order = Support(f_trieste, b.board.get_province("Albania"))
        b.retreat(f_greece, "Albania")
        b.assertForcedDisband(f_trieste, f_greece)
        b.retreats_adjudicate(self)

    def test_6_h_2(self):
        """ 6.H.2. TEST CASE, NO SUPPORTS FROM RETREATING UNIT
            Even a retreating unit can not give support.
            England: A Liverpool - Edinburgh
            England: F Yorkshire Supports A Liverpool - Edinburgh
            England: F Norway Hold
            Germany: A Kiel Supports A Ruhr - Holland
            Germany: A Ruhr - Holland
            Russia: F Edinburgh Hold
            Russia: A Sweden Supports A Finland - Norway
            Russia: A Finland - Norway
            Russia: F Holland Hold
            The English fleet in Norway and the Russian fleets in Edinburgh and Holland are dislodged. If the
            following retreat orders are given:
            England: F Norway - North Sea
            Russia: F Edinburgh - North Sea
            Russia: F Holland Supports F Edinburgh - North Sea
            Although the fleet in Holland may receive an order, it may not support (it is disbanded).
            The English fleet in Norway and the Russian fleet in Edinburgh bounce and are disbanded.
        """
        b = BoardBuilder()
        
        a_liverpool = b.move(b.england, UnitType.ARMY, "Liverpool", "Edinburgh")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", a_liverpool, "Edinburgh")
        f_norway = b.hold(b.england, UnitType.FLEET, "Norway")
        a_ruhr = b.move(b.germany, UnitType.ARMY, "Ruhr", "Holland")
        a_kiel = b.supportMove(b.germany, UnitType.ARMY, "Kiel", a_ruhr, "Holland")
        f_edinburgh = b.hold(b.russia, UnitType.FLEET, "Edinburgh")
        a_finland = b.move(b.russia, UnitType.ARMY, "Finland", "Norway")
        a_sweden = b.supportMove(b.russia, UnitType.ARMY, "Sweden", a_finland, "Norway")
        f_holland = b.hold(b.russia, UnitType.FLEET, "Holland")

        b.assertDislodge(f_norway, f_edinburgh, f_holland)
        b.moves_adjudicate(self)
        
        b.retreat(f_norway, "North Sea")
        f_holland.order = Support(f_edinburgh, b.board.get_province("North Sea"))
        b.retreat(f_edinburgh, "North Sea")

        b.assertForcedDisband(f_norway, f_edinburgh, f_holland)
        b.retreats_adjudicate(self)

    def test_6_h_3(self):
        """ 6.H.3. TEST CASE, NO CONVOY DURING RETREAT
            Convoys during retreat are not allowed.
            England: F North Sea Hold
            England: A Holland Hold
            Germany: F Kiel Supports A Ruhr - Holland
            Germany: A Ruhr - Holland
            The English army in Holland is dislodged. If England orders the following in retreat:
            England: A Holland - Yorkshire
            England: F North Sea Convoys A Holland - Yorkshire
            The convoy order is illegal. The army in Holland is disbanded.
        """
        b = BoardBuilder()
        f_north_sea = b.hold(b.england, UnitType.FLEET, "North Sea")
        a_holland = b.hold(b.england, UnitType.ARMY, "Holland")
        a_ruhr = b.move(b.germany, UnitType.ARMY, "Ruhr", "Holland")
        f_kiel = b.supportMove(b.germany, UnitType.FLEET, "Kiel", a_ruhr, "Holland")

        b.assertDislodge(a_holland)
        b.moves_adjudicate(self)

        b.retreat(a_holland, "Yorkshire")
        f_north_sea.order = ConvoyTransport(a_holland, b.board.get_province("Yorkshire"))
        
        b.assertForcedDisband(a_holland)
        b.retreats_adjudicate(self)

    def test_6_h_4(self):
        """ 6.H.4. TEST CASE, NO OTHER MOVES DURING RETREAT
            Of course you may not do any other move during a retreat. But look if the adjudicator checks for it.
            England: F North Sea Hold
            England: A Holland Hold
            Germany: F Kiel Supports A Ruhr - Holland
            Germany: A Ruhr - Holland
            The English army in Holland is dislodged. If England orders the following in retreat:
            England: A Holland - Belgium
            England: F North Sea - Norwegian Sea
            The fleet in the North Sea is not dislodge, so the move is illegal.
        """
        b = BoardBuilder()
        f_north_sea = b.hold(b.england, UnitType.FLEET, "North Sea")
        a_holland = b.hold(b.england, UnitType.ARMY, "Holland")
        a_ruhr = b.move(b.germany, UnitType.ARMY, "Ruhr", "Holland")
        f_kiel = b.supportMove(b.germany, UnitType.FLEET, "Kiel", a_ruhr, "Holland")

        b.assertDislodge(a_holland)
        b.moves_adjudicate(self)

        b.retreat(a_holland, "Belgium")
        f_north_sea.order = Move(b.board.get_province("Norwegian Sea"))

        b.assertNotForcedDisband(a_holland)
        b.retreats_adjudicate(self)
        self.assertTrue(f_north_sea.province.name == "North Sea", "North Sea fleet should not have moved.")

    def test_6_h_5(self):
        """ 6.H.5. TEST CASE, A UNIT MAY NOT RETREAT TO THE AREA FROM WHICH IT IS ATTACKED
            Well, that would be of course stupid. Still, the adjudicator must be tested on this.
            Russia: F Constantinople Supports F Black Sea - Ankara
            Russia: F Black Sea - Ankara
            Turkey: F Ankara Hold
            Fleet in Ankara is dislodged and may not retreat to Black Sea.
        """
        b = BoardBuilder()
        f_black_sea = b.move(b.russia, UnitType.FLEET, "Black Sea", "Ankara")
        f_constantinople = b.supportMove(b.russia, UnitType.FLEET, "Constantinople", f_black_sea, "Ankara")
        f_ankara = b.hold(b.turkey, UnitType.FLEET, "Ankara")

        b.assertDislodge(f_ankara)
        b.moves_adjudicate(self)
        self.assertTrue("Black Sea" not in f_ankara.retreat_options, "Black Sea should not be in treat options")

        b.retreat(f_ankara, "Black Sea")
        b.assertForcedDisband(f_ankara)
        b.retreats_adjudicate(self)

    def test_6_h_6(self):
        """ 6.H.6. TEST CASE, UNIT MAY NOT RETREAT TO A CONTESTED AREA
            Stand off prevents retreat to the area.
            Austria: A Budapest Supports A Trieste - Vienna
            Austria: A Trieste - Vienna
            Germany: A Munich - Bohemia
            Germany: A Silesia - Bohemia
            Italy: A Vienna Hold
            The Italian army in Vienna is dislodged. It may not retreat to Bohemia.
        """
        b = BoardBuilder()
        
        a_trieste = b.move(b.austria, UnitType.ARMY, "Trieste", "Vienna")
        a_budapest = b.supportMove(b.austria, UnitType.ARMY, "Budapest", a_trieste, "Vienna")
        a_munich = b.move(b.germany, UnitType.ARMY, "Munich", "Bohemia")
        a_silesia = b.move(b.germany, UnitType.ARMY, "Silesia", "Bohemia")
        a_vienna = b.hold(b.italy, UnitType.ARMY, "Vienna")
        
        # Check outcomes for dislodging and success/failure assertions
        b.assertFail(a_munich, a_silesia)
        b.assertDislodge(a_vienna)
        b.moves_adjudicate(self)
        self.assertFalse("Bohemia" in a_vienna.retreat_options, "Bohemia should not be a retreat option")

        b.retreat(a_vienna, "Bohemia")
        b.assertForcedDisband(a_vienna)
        b.retreats_adjudicate(self)

    def test_6_h_7(self):
        """ 6.H.7. TEST CASE, MULTIPLE RETREAT TO SAME AREA WILL DISBAND UNITS
            There can only be one unit in an area.
            Austria: A Budapest Supports A Trieste - Vienna
            Austria: A Trieste - Vienna
            Germany: A Munich Supports A Silesia - Bohemia
            Germany: A Silesia - Bohemia
            Italy: A Vienna Hold
            Italy: A Bohemia Hold
            If Italy orders the following for retreat:
            Italy: A Bohemia - Tyrolia
            Italy: A Vienna - Tyrolia
            Both armies will be disbanded.
        """

        b = BoardBuilder()

        # Austria's units and their moves
        a_trieste = b.move(b.austria, UnitType.ARMY, "Trieste", "Vienna")
        a_budapest = b.supportMove(b.austria, UnitType.ARMY, "Budapest", a_trieste, "Vienna")
        a_silesia = b.move(b.germany, UnitType.ARMY, "Silesia", "Bohemia")
        a_munich = b.supportMove(b.germany, UnitType.ARMY, "Munich", a_silesia, "Bohemia")
        a_vienna = b.hold(b.italy, UnitType.ARMY, "Vienna")
        a_bohemia = b.hold(b.italy, UnitType.ARMY, "Bohemia")

        b.assertDislodge(a_bohemia, a_vienna)
        b.moves_adjudicate(self)

        b.retreat(a_bohemia, "Tyrolia")
        b.retreat(a_vienna, "Tyrolia")
        b.assertForcedDisband(a_bohemia, a_vienna)
        b.retreats_adjudicate(self)

    def test_6_h_8(self):
        """ 6.H.8. TEST CASE, TRIPLE RETREAT TO SAME AREA WILL DISBAND UNITS
            When three units retreat to the same area, then all three units are disbanded.
            England: A Liverpool - Edinburgh
            England: F Yorkshire Supports A Liverpool - Edinburgh
            England: F Norway Hold
            Germany: A Kiel Supports A Ruhr - Holland
            Germany: A Ruhr - Holland
            Russia: F Edinburgh Hold
            Russia: A Sweden Supports A Finland - Norway
            Russia: A Finland - Norway
            Russia: F Holland Hold
            The fleets in Norway, Edinburgh and Holland are dislodged. If the following retreat orders are given:
            England: F Norway - North Sea
            Russia: F Edinburgh - North Sea
            Russia: F Holland - North Sea
            All three units are disbanded.
        """
        b = BoardBuilder()

        a_liverpool = b.move(b.england, UnitType.ARMY, "Liverpool", "Edinburgh")
        f_yorkshire = b.supportMove(b.england, UnitType.FLEET, "Yorkshire", a_liverpool, "Edinburgh")
        f_norway = b.hold(b.england, UnitType.FLEET, "Norway")
        a_ruhr = b.move(b.germany, UnitType.ARMY, "Ruhr", "Holland")
        a_kiel = b.supportMove(b.germany, UnitType.ARMY, "Kiel", a_ruhr, "Holland")
        f_edinburgh = b.hold(b.russia, UnitType.FLEET, "Edinburgh")
        a_finland = b.move(b.russia, UnitType.ARMY, "Finland", "Norway")
        a_sweden = b.supportMove(b.russia, UnitType.ARMY, "Sweden", a_finland, "Norway")
        f_holland = b.hold(b.russia, UnitType.FLEET, "Holland")
        
        b.assertForcedDisband(f_norway, f_edinburgh, f_holland)
        b.moves_adjudicate(self)

        b.retreat(f_norway, "North Sea")
        b.retreat(f_edinburgh, "North Sea")
        b.retreat(f_holland, "North Sea")

        b.assertForcedDisband(f_norway, f_edinburgh, f_holland)
        b.retreats_adjudicate(self)

    def test_6_h_9(self):
        """ 6.H.9. TEST CASE, DISLODGED UNIT WILL NOT MAKE ATTACKERS AREA CONTESTED
            An army can follow.
            England: F Heligoland Bight - Kiel
            England: F Denmark Supports F Heligoland Bight - Kiel
            Germany: A Berlin - Prussia
            Germany: F Kiel Hold
            Germany: A Silesia Supports A Berlin - Prussia
            Russia: A Prussia - Berlin
            The fleet in Kiel can retreat to Berlin.
        """
        b = BoardBuilder()

        f_heligoland_bight = b.move(b.england, UnitType.FLEET, "Heligoland Bight", "Kiel")
        f_denmark = b.supportMove(b.england, UnitType.FLEET, "Denmark", f_heligoland_bight, "Kiel")
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Prussia")
        f_kiel = b.hold(b.germany, UnitType.FLEET, "Kiel")
        a_silesia = b.supportMove(b.germany, UnitType.ARMY, "Silesia", a_berlin, "Prussia")
        a_prussia = b.move(b.russia, UnitType.ARMY, "Prussia", "Berlin")

        b.assertDislodge(f_kiel, a_prussia)
        b.moves_adjudicate(self)
        p_berlin = b.board.get_province("Berlin")
        self.assertTrue((p_berlin, None) in f_kiel.retreat_options,
                        f"Berlin should be a retreat option. Retreat options are {', '.join(p[0].name for p in f_kiel.retreat_options)}.")

        b.retreat(f_kiel, "Berlin")
        b.assertNotForcedDisband(f_kiel)
        b.assertForcedDisband(a_prussia)
        b.retreats_adjudicate(self)

    def test_6_h_10(self):
        """ 6.H.10. TEST CASE, NOT RETREATING TO ATTACKER DOES NOT MEAN CONTESTED
            An army can not retreat to the place of the attacker. The easiest way to program that, is to mark that
            place as "contested". However, this is not correct. Another army may retreat to that place.
            England: A Kiel Hold
            Germany: A Berlin - Kiel
            Germany: A Munich Supports A Berlin - Kiel
            Germany: A Prussia Hold
            Russia: A Warsaw - Prussia
            Russia: A Silesia Supports A Warsaw - Prussia
            The armies in Kiel and Prussia are dislodged. The English army in Kiel can not retreat to Berlin, but
            the army in Prussia can retreat to Berlin. Suppose the following retreat orders are given:
            England: A Kiel - Berlin
            Germany: A Prussia - Berlin
            The English retreat to Berlin is illegal and fails (the unit is disbanded). The German retreat to Berlin is
            successful and does not bounce on the English unit.
        """
        b = BoardBuilder()

        a_kiel = b.hold(b.england, UnitType.ARMY, "Kiel")
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Kiel")
        a_munich = b.supportMove(b.germany, UnitType.ARMY, "Munich", a_berlin, "Kiel")
        a_prussia = b.hold(b.germany, UnitType.ARMY, "Prussia")
        a_warsaw = b.move(b.russia, UnitType.ARMY, "Warsaw", "Prussia")
        a_silesia = b.supportMove(b.russia, UnitType.ARMY, "Silesia", a_warsaw, "Prussia")
        
        b.moves_adjudicate(self)
        p_berlin = b.board.get_province("Berlin")
        self.assertFalse((p_berlin, None) in a_kiel.retreat_options, "Berlin should not be a retreat option for Kiel")
        self.assertTrue((p_berlin, None) in a_prussia.retreat_options, "Berlin should be a retreat option for Kiel")

        b.retreat(a_kiel, "Berlin")
        b.retreat(a_prussia, "Berlin")

        b.assertForcedDisband(a_kiel)
        b.assertNotForcedDisband(a_prussia)
        b.retreats_adjudicate(self)

    def test_6_h_11(self):
        """ 6.H.11. TEST CASE, RETREAT WHEN DISLODGED BY ADJACENT CONVOY
            If a unit is dislodged by an army via convoy, the question arises whether the dislodged army can retreat
            to the original place of the convoyed army. This is only relevant in case the convoy was to an adjacent
            place.
            France: A Gascony - Marseilles via Convoy
            France: A Burgundy Supports A Gascony - Marseilles
            France: F Mid-Atlantic Ocean Convoys A Gascony - Marseilles
            France: F Western Mediterranean Convoys A Gascony - Marseilles
            France: F Gulf of Lyon Convoys A Gascony - Marseilles
            Italy: A Marseilles Hold
            If for issue 4.A.3 choice b or c has been taken, then the army in Gascony will not move with the use of
            the convoy, because the army in Marseilles does not move in opposite direction. This immediately means that
            the army in Marseilles may not move to Gascony when it dislodged by the army there.
            For all other choices of issue 4.A.3, the army in Gascony takes a convoy and does not pass the border of
            Gascony with Marseilles (it went a complete different direction). Now, the result depends on which rule
            is used for retreating (see issue 4.A.5).
            I prefer the 1982/2000 rule for convoying to adjacent places. This means that the move of Gascony happened
            by convoy. Furthermore, I prefer that the army in Marseilles may retreat to Gascony.
        """

        b = BoardBuilder()

        a_gascony = b.move(b.france, UnitType.ARMY, "Gascony", "Marseilles")
        a_burgundy = b.supportMove(b.france, UnitType.ARMY, "Burgundy", a_gascony, "Marseilles")
        f_mid_atlantic_ocean = b.convoy(b.france, "Mid-Atlantic Ocean", a_gascony, "Marseilles")
        f_western_mediterranean = b.convoy(b.france, "Western Mediterranean Sea", a_gascony, "Marseilles")
        f_gulf_of_lyon = b.convoy(b.france, "Gulf of Lyon", a_gascony, "Marseilles")
        a_marseilles = b.hold(b.italy, UnitType.ARMY, "Marseilles")

        b.assertSuccess(a_gascony, a_burgundy, f_mid_atlantic_ocean, f_western_mediterranean, f_gulf_of_lyon)
        b.assertDislodge(a_marseilles)
        b.moves_adjudicate(self)
        p_gascony = b.board.get_province("Gascony")
        self.assertFalse((p_gascony, None) in a_marseilles.retreat_options, "Gascony should not be a retreat option for Kiel")

        b.retreat(a_marseilles, "Gascony")
        b.assertDisbanded(a_marseilles)
        b.retreats_adjudicate(self)

    def test_6_h_12(self):
        """ 6.H.12. TEST CASE, RETREAT WHEN DISLODGED BY ADJACENT CONVOY WHILE TRYING TO DO THE SAME
            The previous test case can be made more extra ordinary, when both armies tried to move by convoy.
            England: A Liverpool - Edinburgh via Convoy
            England: F Irish Sea Convoys A Liverpool - Edinburgh
            England: F English Channel Convoys A Liverpool - Edinburgh
            England: F North Sea Convoys A Liverpool - Edinburgh
            France: F Brest - English Channel
            France: F Mid-Atlantic Ocean Supports F Brest - English Channel
            Russia: A Edinburgh - Liverpool via Convoy
            Russia: F Norwegian Sea Convoys A Edinburgh - Liverpool
            Russia: F North Atlantic Ocean Convoys A Edinburgh - Liverpool
            Russia: A Clyde Supports A Edinburgh - Liverpool
            If for issue 4.A.3 choice c has been taken, then the army in Liverpool will not try to move by convoy,
            because the convoy is disrupted. This has as consequence that army will just advance to Edinburgh by using
            the land route. For all other choices of issue 4.A.3, both the army in Liverpool as in Edinburgh will try
            to move by convoy. The army in Edinburgh will succeed. The army in Liverpool will fail, because of the
            disrupted convoy. It is dislodged by the army of Edinburgh. Now, the question is whether the army in
            Liverpool may retreat to Edinburgh. The result depends on which rule is used for retreating (see issue
            4.A.5). I prefer the 1982/2000 rule for convoying to adjacent places. This means that the army in Liverpool
            tries the disrupted convoy. Furthermore, I prefer that the army in Liverpool may retreat to Edinburgh.
        """

        b = BoardBuilder()
        a_liverpool = b.move(b.england, UnitType.ARMY, "Liverpool", "Edinburgh")
        f_irish_sea = b.convoy(b.england, "Irish Sea", a_liverpool, "Edinburgh")
        f_english_channel = b.convoy(b.england, "English Channel", a_liverpool, "Edinburgh")
        f_north_sea = b.convoy(b.england, "North Sea", a_liverpool, "Edinburgh")
        f_brest = b.move(b.france, UnitType.FLEET, "Brest", "English Channel")
        f_mid_atlantic_ocean = b.supportMove(b.france, UnitType.FLEET, "Mid-Atlantic Ocean", f_brest, "English Channel")
        a_edinburgh = b.move(b.russia, UnitType.ARMY, "Edinburgh", "Liverpool")
        f_norwegian_sea = b.convoy(b.russia, "Norwegian Sea", a_edinburgh, "Liverpool")
        f_north_atlantic_ocean = b.convoy(b.russia, "North Atlantic Ocean", a_edinburgh, "Liverpool")
        a_clyde = b.supportMove(b.russia, UnitType.ARMY, "Clyde", a_edinburgh, "Liverpool")

        b.assertSuccess(a_liverpool)
        b.assertSuccess(f_brest, a_edinburgh)
        b.assertFail(f_english_channel)
        b.assertNotDislodge(a_liverpool)
        b.moves_adjudicate(self)

        # b.retreat(a_liverpool, "Edinburgh")
        
        # b.assertForcedDisband(f_english_channel)
        # b.assertNotForcedDisband(a_liverpool)
        # b.retreats_adjudicate(self)

    def test_6_h_13(self):
        """ 6.H.13. TEST CASE, NO RETREAT WITH CONVOY IN MAIN PHASE
            The places where a unit may retreat to, must be calculated during the main phase. Care should be taken
            that a convoy ordered in the main phase can not be used in the retreat phase.
            England: A Picardy Hold
            England: F English Channel Convoys A Picardy - London
            France: A Paris - Picardy
            France: A Brest Supports A Paris - Picardy
            The dislodged army in Picardy can not retreat to London.
        """
        b = BoardBuilder()

        a_picardy = b.hold(b.england, UnitType.ARMY, "Picardy")
        f_english_channel = b.convoy(b.england, "English Channel", a_picardy, "London")
        
        a_paris = b.move(b.france, UnitType.ARMY, "Paris", "Picardy")
        a_brest = b.supportMove(b.france, UnitType.ARMY, "Brest", a_paris, "Picardy")

        b.assertDislodge(a_picardy)
        b.moves_adjudicate(self)
        self.assertFalse("London" in a_picardy.retreat_options, "London should not be a retreat option for Kiel")

        b.retreat(a_picardy, "London")
        b.assertForcedDisband(a_picardy)
        b.retreats_adjudicate(self)

    def test_6_h_14(self):
        """ 6.H.14. TEST CASE, NO RETREAT WITH SUPPORT IN MAIN PHASE
            Comparable to the previous test case, a support given in the main phase can not be used in the retreat
            phase.
            England: A Picardy Hold
            England: F English Channel Supports A Picardy - Belgium
            France: A Paris - Picardy
            France: A Brest Supports A Paris - Picardy
            France: A Burgundy Hold
            Germany: A Munich Supports A Marseilles - Burgundy
            Germany: A Marseilles - Burgundy
            After the main phase the following retreat orders are given:
            England: A Picardy - Belgium
            France: A Burgundy - Belgium
            Both the army in Picardy and Burgundy are disbanded.
        """
        b = BoardBuilder()

        # England's army holds in Picardy
        a_picardy = b.hold(b.england, UnitType.ARMY, "Picardy")
        f_english_channel = b.supportMove(b.england, UnitType.FLEET, "English Channel", a_picardy, "Belgium")
        
        a_paris = b.move(b.france, UnitType.ARMY, "Paris", "Picardy")
        a_brest = b.supportMove(b.france, UnitType.ARMY, "Brest", a_paris, "Picardy")

        a_burgundy = b.hold(b.france, UnitType.ARMY, "Burgundy")
        a_marseilles = b.move(b.germany, UnitType.ARMY, "Marseilles", "Burgundy")
        a_munich = b.supportMove(b.germany, UnitType.ARMY, "Munich", a_marseilles, "Burgundy")
        
        b.moves_adjudicate(self)

        b.retreat(a_picardy, "Belgium")
        b.retreat(a_burgundy, "Belgium")
        b.assertForcedDisband(a_picardy, a_burgundy)
        b.retreats_adjudicate(self)

    def test_6_h_15(self):
        """ 6.H.15. TEST CASE, NO COASTAL CRAWL IN RETREAT
            You can not go to the other coast from where the attacker came from.
            England: F Portugal Hold
            France: F Spain(sc) - Portugal
            France: F Mid-Atlantic Ocean Supports F Spain(sc) - Portugal
            The English fleet in Portugal is destroyed and can not retreat to Spain(nc).
        """
        b = BoardBuilder()

        f_portugal = b.hold(b.england, UnitType.FLEET, "Portugal")
        f_spain_sc = b.move(b.france, UnitType.FLEET, "Spain sc", "Portugal")
        f_mid_atlantic_ocean = b.supportMove(b.france, UnitType.FLEET, "Mid-Atlantic Ocean", f_spain_sc, "Portugal")

        b.moves_adjudicate(self)
        self.assertTrue(not f_portugal.retreat_options or len(f_portugal.retreat_options) == 0, "Portugal should have no retreat options")

        b.retreat(f_portugal, "Spain nc")
        b.assertForcedDisband(f_portugal)
        b.retreats_adjudicate(self)

    def test_6_h_16(self):
        """ 6.H.16. TEST CASE, CONTESTED FOR BOTH COASTS
            If a coast is contested, the other is not available for retreat.
            France: F Mid-Atlantic Ocean - Spain(nc)
            France: F Gascony - Spain(nc)
            France: F Western Mediterranean Hold
            Italy: F Tunis Supports F Tyrrhenian Sea - Western Mediterranean
            Italy: F Tyrrhenian Sea - Western Mediterranean
            The French fleet in the Western Mediterranean can not retreat to Spain(sc).
        """
        b = BoardBuilder()

        f_mid_atlantic_ocean = b.move(b.france, UnitType.FLEET, "Mid-Atlantic Ocean", "Spain nc")
        f_gascony = b.move(b.france, UnitType.FLEET, "Gascony", "Spain nc")
        f_western_mediterranean = b.hold(b.france, UnitType.FLEET, "Western Mediterranean Sea")
        f_tyrrhenian_sea = b.move(b.italy, UnitType.FLEET, "Tyrrhenian Sea", "Western Mediterranean Sea")
        f_tunis = b.supportMove(b.italy, UnitType.FLEET, "Tunis", f_tyrrhenian_sea, "Western Mediterranean Sea")
        
        b.assertForcedDisband(f_western_mediterranean)
        b.moves_adjudicate(self)
        self.assertFalse(not f_western_mediterranean.retreat_options or b.board.get_province_and_coast("Spain sc") in f_western_mediterranean.retreat_options, "Spain should not be a retreat option")
        b.retreat(f_western_mediterranean, "Spain sc")

        b.assertForcedDisband(f_western_mediterranean)
        b.retreats_adjudicate(self)
