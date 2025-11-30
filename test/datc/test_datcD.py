import unittest

from DiploGM.models.order import Support
from DiploGM.models.unit import UnitType
from test.utils import BoardBuilder

# These tests are based off https://webdiplomacy.net/doc/DATC_v3_0.html, with 
# https://github.com/diplomacy/diplomacy/blob/master/diplomacy/tests/test_datc.py being used as a reference as well.

# 6.D. TEST CASES, SUPPORTS AND DISLODGES
class TestDATC_D(unittest.TestCase):
    def test_6_d_1(self):
        """ 6.D.1. TEST CASE, SUPPORTED HOLD CAN PREVENT DISLODGEMENT
            The most simple support to hold order.
            Austria: F Adriatic Sea Supports A Trieste - Venice
            Austria: A Trieste - Venice
            Italy: A Venice Hold
            Italy: A Tyrolia Supports A Venice
            The support of Tyrolia prevents that the army in Venice is dislodged. The army in Trieste will not move.
        """
        b = BoardBuilder()
        a_trieste = b.move(b.austria, UnitType.ARMY, "Trieste", "Venice")
        f_adriatic_sea = b.supportMove(b.austria, UnitType.FLEET, "Adriatic Sea", a_trieste, "Venice")
        a_venice = b.hold(b.italy, UnitType.ARMY, "Venice")
        a_tyrolia = b.supportHold(b.italy, UnitType.ARMY, "Tyrolia", a_venice)

        b.assertNotDislodge(a_venice)
        b.assertSuccess(f_adriatic_sea, a_tyrolia)
        b.assertFail(a_trieste)
        b.moves_adjudicate(self)
        
    def test_6_d_2(self):
        """ 6.D.2. TEST CASE, A MOVE CUTS SUPPORT ON HOLD
            The most simple support on hold cut.
            Austria: F Adriatic Sea Supports A Trieste - Venice
            Austria: A Trieste - Venice
            Austria: A Vienna - Tyrolia
            Italy: A Venice Hold
            Italy: A Tyrolia Supports A Venice
            The support of Tyrolia is cut by the army in Vienna. That means that the army in Venice is dislodged by the
            army from Trieste.
        """
        b = BoardBuilder()
        a_trieste = b.move(b.austria, UnitType.ARMY, "Trieste", "Venice")
        f_adriatic_sea = b.supportMove(b.austria, UnitType.FLEET, "Adriatic Sea", a_trieste, "Venice")
        a_vienna = b.move(b.austria, UnitType.ARMY, "Vienna", "Tyrolia")
        a_venice = b.hold(b.italy, UnitType.ARMY, "Venice")
        a_tyrolia = b.supportHold(b.italy, UnitType.ARMY, "Tyrolia", a_venice)

        b.assertDislodge(a_venice)
        b.assertSuccess(a_trieste)
        b.assertFail(a_vienna)
        b.moves_adjudicate(self)

    def test_6_d_3(self):
        """ 6.D.3. TEST CASE, A MOVE CUTS SUPPORT ON MOVE
            The most simple support on move cut.
            Austria: F Adriatic Sea Supports A Trieste - Venice
            Austria: A Trieste - Venice
            Italy: A Venice Hold
            Italy: F Ionian Sea - Adriatic Sea
            The support of the fleet in the Adriatic Sea is cut. That means that the army in Venice will not be
            dislodged and the army in Trieste stays in Trieste.
        """
        b = BoardBuilder()
        a_trieste = b.move(b.austria, UnitType.ARMY, "Trieste", "Venice")
        f_adriatic_sea = b.supportMove(b.austria, UnitType.FLEET, "Adriatic Sea", a_trieste, "Venice")
        a_venice = b.hold(b.italy, UnitType.ARMY, "Venice")
        f_ionian_sea = b.move(b.italy, UnitType.FLEET, "Ionian Sea", "Adriatic Sea")

        b.assertNotDislodge(a_venice)
        b.assertFail(a_trieste, f_ionian_sea, f_adriatic_sea)
        b.moves_adjudicate(self)

    def test_6_d_4(self):
        """ 6.D.4. TEST CASE, SUPPORT TO HOLD ON UNIT SUPPORTING A HOLD ALLOWED
            A unit that is supporting a hold, can receive a hold support.
            Germany: A Berlin Supports F Kiel
            Germany: F Kiel Supports A Berlin
            Russia: F Baltic Sea Supports A Prussia - Berlin
            Russia: A Prussia - Berlin
            The Russian move from Prussia to Berlin fails.
        """
        b = BoardBuilder()
        a_berlin = b.army("Berlin", b.germany)
        f_kiel = b.fleet("Kiel", b.germany)
        a_berlin = b.supportHold(b.germany, UnitType.ARMY, "Berlin", f_kiel)
        f_kiel = b.supportHold(b.germany, UnitType.ARMY, "Kiel", a_berlin)
        a_prussia = b.move(b.russia, UnitType.ARMY, "Prussia", "Berlin")
        f_baltic_sea = b.supportMove(b.russia, UnitType.FLEET, "Baltic Sea", a_prussia, "Berlin")

        b.assertFail(a_prussia, a_berlin)
        b.assertSuccess(f_kiel)
        b.moves_adjudicate(self)
        
    def test_6_d_5(self):
        """ 6.D.5. TEST CASE, SUPPORT TO HOLD ON UNIT SUPPORTING A MOVE ALLOWED
            A unit that is supporting a move, can receive a hold support.
            Germany: A Berlin Supports A Munich - Silesia
            Germany: F Kiel Supports A Berlin
            Germany: A Munich - Silesia
            Russia: F Baltic Sea Supports A Prussia - Berlin
            Russia: A Prussia - Berlin
            The Russian move from Prussia to Berlin fails.
        """
        b = BoardBuilder()
        a_munich = b.move(b.germany, UnitType.ARMY, "Munich", "Silesia")
        a_berlin = b.supportMove(b.germany, UnitType.ARMY, "Berlin", a_munich, "Silesia")
        f_kiel = b.supportHold(b.germany, UnitType.FLEET, "Kiel", a_berlin)
        a_berlin = b.supportHold(b.germany, UnitType.ARMY, "Berlin", f_kiel)
        f_kiel = b.supportHold(b.germany, UnitType.ARMY, "Kiel", a_berlin)
        a_prussia = b.move(b.russia, UnitType.ARMY, "Prussia", "Berlin")
        f_baltic_sea = b.supportMove(b.russia, UnitType.FLEET, "Baltic Sea", a_prussia, "Berlin")

        b.assertFail(a_berlin, a_prussia)
        b.assertSuccess(f_kiel, a_munich)
        b.moves_adjudicate(self)

    def test_6_d_6(self):
        """ 6.D.6. TEST CASE, SUPPORT TO HOLD ON CONVOYING UNIT ALLOWED
            A unit that is convoying, can receive a hold support.
            Germany: A Berlin - Sweden
            Germany: F Baltic Sea Convoys A Berlin - Sweden
            Germany: F Prussia Supports F Baltic Sea
            Russia: F Livonia - Baltic Sea
            Russia: F Gulf of Bothnia Supports F Livonia - Baltic Sea
            The Russian move from Livonia to the Baltic Sea fails. The convoy from Berlin to Sweden succeeds.
        """
        b = BoardBuilder()
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Sweden")
        f_baltic_sea = b.convoy(b.germany, "Baltic Sea", a_berlin, "Sweden")
        f_prussia = b.supportHold(b.germany, UnitType.FLEET, "Prussia", f_baltic_sea)
        f_livonia = b.move(b.russia, UnitType.FLEET, "Livonia", "Baltic Sea")
        f_gulf_of_bothnia = b.supportMove(b.russia, UnitType.FLEET, "Gulf of Bothnia", f_livonia, "Baltic Sea")
        
        b.assertFail(f_livonia)
        b.assertSuccess(f_prussia, f_baltic_sea, a_berlin)
        b.moves_adjudicate(self)

    def test_6_d_7(self):
        """ 6.D.7. TEST CASE, SUPPORT TO HOLD ON MOVING UNIT NOT ALLOWED
            A unit that is moving, can not receive a hold support for the situation that the move fails.
            Germany: F Baltic Sea - Sweden
            Germany: F Prussia Supports F Baltic Sea
            Russia: F Livonia - Baltic Sea
            Russia: F Gulf of Bothnia Supports F Livonia - Baltic Sea
            Russia: A Finland - Sweden
            The support of the fleet in Prussia fails. The fleet in Baltic Sea will bounce on the Russian army
            in Finland and will be dislodged by the Russian fleet from Livonia when it returns to the Baltic Sea.
        """
        b = BoardBuilder()
        f_baltic_sea = b.move(b.germany, UnitType.FLEET, "Baltic Sea", "Sweden")
        f_prussia = b.supportHold(b.germany, UnitType.FLEET, "Prussia", f_baltic_sea)
        f_livonia = b.move(b.russia, UnitType.FLEET, "Livonia", "Baltic Sea")
        f_gulf_of_bothnia = b.supportMove(b.russia, UnitType.FLEET, "Gulf of Bothnia", f_livonia, "Baltic Sea")
        a_finland = b.move(b.russia, UnitType.ARMY, "Finland", "Sweden")

        b.assertFail(a_finland, f_baltic_sea)
        b.assertIllegal(f_prussia)
        b.assertSuccess(f_livonia)
        b.assertDislodge(f_baltic_sea)
        b.moves_adjudicate(self)

    def test_6_d_8(self):
        """ 6.D.8. TEST CASE, FAILED CONVOY CAN NOT RECEIVE HOLD SUPPORT
            If a convoy fails because of disruption of the convoy or when the right convoy orders are not given,
            then the army to be convoyed can not receive support in hold, since it still tried to move.
            Austria: F Ionian Sea Hold
            Austria: A Serbia Supports A Albania - Greece
            Austria: A Albania - Greece
            Turkey: A Greece - Naples
            Turkey: A Bulgaria Supports A Greece
            There was a possible convoy from Greece to Naples, before the orders were made public (via the Ionian Sea).
            This means that the order of Greece to Naples should never be treated as illegal order and be changed in a
            hold order able to receive hold support (see also issue VI.A). Therefore, the support in Bulgaria fails and
            the army in Greece is dislodged by the army in Albania.
        """
        b = BoardBuilder()
        f_ionian_sea = b.hold(b.austria, UnitType.FLEET, "Ionian Sea")
        a_albania = b.move(b.austria, UnitType.ARMY, "Albania", "Greece")
        a_serbia = b.supportMove(b.austria, UnitType.ARMY, "Serbia", a_albania, "Greece")
        a_greece = b.move(b.turkey, UnitType.ARMY, "Greece", "Naples")
        a_bulgaria = b.supportHold(b.turkey, UnitType.ARMY, "Bulgaria", a_greece)

        b.assertIllegal(a_greece)
        b.assertSuccess(f_ionian_sea, a_albania, a_serbia)
        b.assertFail(a_bulgaria)
        b.assertDislodge(a_greece)
        b.moves_adjudicate(self)

    def test_6_d_9(self):
        """ 6.D.9. TEST CASE, SUPPORT TO MOVE ON HOLDING UNIT NOT ALLOWED
            A unit that is holding can not receive a support in moving.
            Italy: A Venice - Trieste
            Italy: A Tyrolia Supports A Venice - Trieste
            Austria: A Albania Supports A Trieste - Serbia
            Austria: A Trieste Hold
            The support of the army in Albania fails and the army in Trieste is dislodged by the army from Venice.
        """
        b = BoardBuilder()
        a_venice = b.move(b.italy, UnitType.ARMY, "Venice", "Trieste")
        a_tyrolia = b.supportMove(b.italy, UnitType.ARMY, "Tyrolia", a_venice, "Trieste")
        a_trieste = b.hold(b.austria, UnitType.ARMY, "Trieste")
        a_albania = b.supportMove(b.austria, UnitType.ARMY, "Albania", a_trieste, "Serbia")

        b.assertIllegal(a_albania)
        b.assertDislodge(a_trieste)
        b.moves_adjudicate(self)

    def test_6_d_10(self):
        """ 6.D.10. TEST CASE, SELF DISLODGMENT PROHIBITED
            A unit may not dislodge a unit of the same great power.
            Germany: A Berlin Hold
            Germany: F Kiel - Berlin
            Germany: A Munich Supports F Kiel - Berlin
            Move to Berlin fails.
        """
        b = BoardBuilder()
        a_berlin = b.hold(b.germany, UnitType.ARMY, "Berlin")
        f_kiel = b.move(b.germany, UnitType.FLEET, "Kiel", "Berlin")
        a_munich = b.supportMove(b.germany, UnitType.ARMY, "Munich", f_kiel, "Berlin")

        b.assertFail(f_kiel)
        b.assertSuccess(a_berlin, a_munich)
        b.moves_adjudicate(self)

    def test_6_d_11(self):
        """ 6.D.11. TEST CASE, NO SELF DISLODGMENT OF RETURNING UNIT
            Idem.
            Germany: A Berlin - Prussia
            Germany: F Kiel - Berlin
            Germany: A Munich Supports F Kiel - Berlin
            Russia: A Warsaw - Prussia
            Army in Berlin bounces, but is not dislodged by own unit.
        """
        b = BoardBuilder()
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Prussia")
        f_kiel = b.move(b.germany, UnitType.FLEET, "Kiel", "Berlin")
        a_munich = b.supportMove(b.germany, UnitType.ARMY, "Munich", f_kiel, "Berlin")
        a_prussia = b.move(b.russia, UnitType.ARMY, "Warsaw", "Prussia")

        b.assertFail(f_kiel, a_berlin, a_prussia)
        b.assertSuccess(a_munich)
        b.assertNotDislodge(a_berlin)
        b.moves_adjudicate(self)

    def test_6_d_12(self):
        """ 6.D.12. TEST CASE, SUPPORTING A FOREIGN UNIT TO DISLODGE OWN UNIT PROHIBITED
            You may not help another power in dislodging your own unit.
            Austria: F Trieste Hold
            Austria: A Vienna Supports A Venice - Trieste
            Italy: A Venice - Trieste
            No dislodgment of fleet in Trieste.
        """
        b = BoardBuilder()
        a_venice = b.move(b.italy, UnitType.ARMY, "Venice", "Trieste")
        f_trieste = b.hold(b.austria, UnitType.FLEET, "Trieste")
        a_vienna = b.supportMove(b.austria, UnitType.ARMY, "Vienna", a_venice, "Trieste")

        b.assertFail(a_venice)
        b.assertNotDislodge(f_trieste)
        b.moves_adjudicate(self)

    def test_6_d_13(self):
        """ 6.D.13. TEST CASE, SUPPORTING A FOREIGN UNIT TO DISLODGE A RETURNING OWN UNIT PROHIBITED
            Idem.
            Austria: F Trieste - Adriatic Sea
            Austria: A Vienna Supports A Venice - Trieste
            Italy: A Venice - Trieste
            Italy: F Apulia - Adriatic Sea
            No dislodgment of fleet in Trieste.
        """
        b = BoardBuilder()
        a_venice = b.move(b.italy, UnitType.ARMY, "Venice", "Trieste")
        f_apulia = b.move(b.italy, UnitType.FLEET, "Apulia", "Adriatic Sea")
        f_trieste = b.move(b.austria, UnitType.FLEET, "Trieste", "Adriatic Sea")
        a_vienna = b.supportMove(b.austria, UnitType.ARMY, "Vienna", a_venice, "Trieste")

        b.assertFail(a_venice, f_trieste, f_apulia)
        b.assertNotDislodge(f_trieste)
        b.moves_adjudicate(self)

    def test_6_d_14(self):
        """  6.D.14. TEST CASE, SUPPORTING A FOREIGN UNIT IS NOT ENOUGH TO PREVENT DISLODGEMENT
            If a foreign unit has enough support to dislodge your unit, you may not prevent that dislodgement by
            supporting the attack.
            Austria: F Trieste Hold
            Austria: A Vienna Supports A Venice - Trieste
            Italy: A Venice - Trieste
            Italy: A Tyrolia Supports A Venice - Trieste
            Italy: F Adriatic Sea Supports A Venice - Trieste
            The fleet in Trieste is dislodged.
        """
        b = BoardBuilder()
        f_trieste = b.hold(b.austria, UnitType.FLEET, "Trieste")
        a_venice = b.move(b.italy, UnitType.ARMY, "Venice", "Trieste")
        a_vienna = b.supportMove(b.austria, UnitType.ARMY, "Vienna", a_venice, "Trieste")
        a_tyrolia = b.supportMove(b.italy, UnitType.ARMY, "Tyrolia", a_venice, "Trieste")
        f_adriatic_sea = b.supportMove(b.italy, UnitType.FLEET, "Adriatic Sea", a_venice, "Trieste")

        b.assertDislodge(f_trieste)
        b.assertSuccess(a_venice, a_vienna, f_trieste, a_tyrolia, f_adriatic_sea)
        b.moves_adjudicate(self)

    def test_6_d_15(self):
        """ 6.D.15. TEST CASE, DEFENDER CAN NOT CUT SUPPORT FOR ATTACK ON ITSELF
            A unit that is attacked by a supported unit can not prevent dislodgement by guessing which of the units
            will do the support.
            Russia: F Constantinople Supports F Black Sea - Ankara
            Russia: F Black Sea - Ankara
            Turkey: F Ankara - Constantinople
            The support of Constantinople is not cut and the fleet in Ankara is dislodged by the fleet in the Black Sea.
        """
        b = BoardBuilder()
        f_black_sea = b.move(b.russia, UnitType.FLEET, "Black Sea", "Ankara")
        f_constantinople = b.supportMove(b.russia, UnitType.FLEET, "Constantinople", f_black_sea, "Ankara")
        f_ankara = b.move(b.turkey, UnitType.FLEET, "Ankara", "Constantinople")

        b.assertSuccess(f_constantinople, f_black_sea)
        b.assertFail(f_ankara)
        b.assertDislodge(f_ankara)
        b.moves_adjudicate(self)

    def test_6_d_16(self):
        """ 6.D.16. TEST CASE, CONVOYING A UNIT DISLODGING A UNIT OF SAME POWER IS ALLOWED
            It is allowed to convoy a foreign unit that dislodges your own unit is allowed.
            England: A London Hold
            England: F North Sea Convoys A Belgium - London
            France: F English Channel Supports A Belgium - London
            France: A Belgium - London
            The English army in London is dislodged by the French army coming from Belgium.
        """
        b = BoardBuilder()
        a_london = b.hold(b.england, UnitType.ARMY, "London")
        a_belgium = b.move(b.france, UnitType.ARMY, "Belgium", "London")
        f_north_sea = b.convoy(b.england, "North Sea", a_belgium, "London")
        f_english_channel = b.supportMove(b.france, UnitType.FLEET, "English Channel", a_belgium, "London")

        b.assertDislodge(a_london)
        b.assertSuccess(a_london, a_belgium, f_north_sea, f_english_channel)
        b.moves_adjudicate(self)

    def test_6_d_17(self):
        """ 6.D.17. TEST CASE, DISLODGEMENT CUTS SUPPORTS
            The famous dislodge rule.
            Russia: F Constantinople Supports F Black Sea - Ankara
            Russia: F Black Sea - Ankara
            Turkey: F Ankara - Constantinople
            Turkey: A Smyrna Supports F Ankara - Constantinople
            Turkey: A Armenia - Ankara
            The Russian fleet in Constantinople is dislodged. This cuts the support to from Black Sea to Ankara.
            Black Sea will bounce with the army from Armenia.
        """
        b = BoardBuilder()
        f_black_sea = b.move(b.russia, UnitType.FLEET, "Black Sea", "Ankara")
        f_constantinople = b.supportMove(b.russia, UnitType.FLEET, "Constantinople", f_black_sea, "Ankara")
        f_ankara = b.move(b.turkey, UnitType.FLEET, "Ankara", "Constantinople")
        a_smyrna = b.supportMove(b.turkey, UnitType.ARMY, "Smyrna", f_ankara, "Constantinople")
        a_armenia = b.move(b.turkey, UnitType.ARMY, "Armenia", "Ankara")
        
        b.assertDislodge(f_constantinople)
        b.assertFail(f_black_sea, a_armenia)
        b.moves_adjudicate(self)

    def test_6_d_18(self):
        """ 6.D.18. TEST CASE, A SURVIVING UNIT WILL SUSTAIN SUPPORT
            Idem. But now with an additional hold that prevents dislodgement.
            Russia: F Constantinople Supports F Black Sea - Ankara
            Russia: F Black Sea - Ankara
            Russia: A Bulgaria Supports F Constantinople
            Turkey: F Ankara - Constantinople
            Turkey: A Smyrna Supports F Ankara - Constantinople
            Turkey: A Armenia - Ankara
            The Russian fleet in the Black Sea will dislodge the Turkish fleet in Ankara.
        """
        b = BoardBuilder()
        f_black_sea = b.move(b.russia, UnitType.FLEET, "Black Sea", "Ankara")
        f_constantinople = b.supportMove(b.russia, UnitType.FLEET, "Constantinople", f_black_sea, "Ankara")
        a_bulgaria = b.supportHold(b.russia, UnitType.ARMY, "Bulgaria", f_constantinople)
        f_ankara = b.move(b.turkey, UnitType.FLEET, "Ankara", "Constantinople")
        a_smyrna = b.supportMove(b.turkey, UnitType.ARMY, "Smyrna", f_ankara, "Constantinople")
        a_armenia = b.move(b.turkey, UnitType.ARMY, "Armenia", "Ankara")

        b.assertDislodge(f_ankara)
        b.assertFail(a_armenia)
        b.assertSuccess(a_bulgaria, a_smyrna, f_constantinople)
        b.moves_adjudicate(self)

    def test_6_d_19(self):
        """ 6.D.19. TEST CASE, EVEN WHEN SURVIVING IS IN ALTERNATIVE WAY
            Now, the dislodgement is prevented because the supports comes from a Russian army:
            Russia: F Constantinople Supports F Black Sea - Ankara
            Russia: F Black Sea - Ankara
            Russia: A Smyrna Supports F Ankara - Constantinople
            Turkey: F Ankara - Constantinople
            The Russian fleet in Constantinople is not dislodged, because one of the support is of Russian origin.
            The support from Black Sea to Ankara will sustain and the fleet in Ankara will be dislodged.
        """        
        b = BoardBuilder()
        f_black_sea = b.move(b.russia, UnitType.FLEET, "Black Sea", "Ankara")
        f_constantinople = b.supportMove(b.russia, UnitType.FLEET, "Constantinople", f_black_sea, "Ankara")
        f_ankara = b.move(b.turkey, UnitType.FLEET, "Ankara", "Constantinople")
        a_smyrna = b.supportMove(b.russia, UnitType.ARMY, "Smyrna", f_ankara, "Constantinople")

        b.assertDislodge(f_ankara)
        b.assertNotDislodge(f_constantinople)
        b.assertSuccess(a_smyrna, f_black_sea, f_constantinople)
        b.moves_adjudicate(self)

    def test_6_d_20(self):
        """ 6.D.20. TEST CASE, UNIT CAN NOT CUT SUPPORT OF ITS OWN COUNTRY
            Although this is not mentioned in all rulebooks, it is generally accepted that when a unit attacks
            another unit of the same Great Power, it will not cut support.
            England: F London Supports F North Sea - English Channel
            England: F North Sea - English Channel
            England: A Yorkshire - London
            France: F English Channel Hold
            The army in York does not cut support. This means that the fleet in the English Channel is dislodged by the
            fleet in the North Sea.
        """
        b = BoardBuilder()
        f_north_sea = b.move(b.england, UnitType.FLEET, "North Sea", "English Channel")
        f_london = b.supportMove(b.england, UnitType.FLEET, "London", f_north_sea, "English Channel")
        a_yorkshire = b.move(b.england, UnitType.ARMY, "Yorkshire", "London")
        f_english_channel = b.hold(b.france, UnitType.FLEET, "English Channel")

        b.assertFail(a_yorkshire)
        b.assertSuccess(f_london, f_north_sea)
        b.assertDislodge(f_english_channel)
        b.moves_adjudicate(self)

    def test_6_d_21(self):
        """ 6.D.21. TEST CASE, DISLODGING DOES NOT CANCEL A SUPPORT CUT
            Sometimes there is the question whether a dislodged moving unit does not cut support (similar to the
            dislodge rule). This is not the case.
            Austria: F Trieste Hold
            Italy: A Venice - Trieste
            Italy: A Tyrolia Supports A Venice - Trieste
            Germany: A Munich - Tyrolia
            Russia: A Silesia - Munich
            Russia: A Berlin Supports A Silesia - Munich
            Although the German army is dislodged, it still cuts the Italian support. That means that the Austrian
            Fleet is not dislodged.
        """
        b = BoardBuilder()
        f_trieste = b.hold(b.austria, UnitType.FLEET, "Trieste")
        a_venice = b.move(b.italy, UnitType.ARMY, "Venice", "Trieste")
        a_tyrolia = b.supportMove(b.italy, UnitType.ARMY, "Tyrolia", a_venice, "Trieste")
        a_munich = b.move(b.germany, UnitType.ARMY, "Munich", "Tyrolia")
        a_silesia = b.move(b.russia, UnitType.ARMY, "Silesia", "Munich")
        a_berlin = b.supportMove(b.russia, UnitType.ARMY, "Berlin", a_silesia, "Munich")

        b.assertDislodge(a_munich)
        b.assertFail(a_tyrolia, a_venice, a_munich)
        b.assertSuccess(a_berlin, a_silesia)
        b.assertNotDislodge(f_trieste)
        b.moves_adjudicate(self)

    def test_6_d_22(self):
        """ 6.D.22. TEST CASE, IMPOSSIBLE FLEET MOVE CAN NOT BE SUPPORTED
            If a fleet tries moves to a land area it seems pointless to support the fleet, since the move will fail
            anyway. However, in such case, the support is also invalid for defense purposes.
            Germany: F Kiel - Munich
            Germany: A Burgundy Supports F Kiel - Munich
            Russia: A Munich - Kiel
            Russia: A Berlin Supports A Munich - Kiel
            The German move from Kiel to Munich is illegal (fleets can not go to Munich). Therefore, the support from
            Burgundy fails and the Russian army in Munich will dislodge the fleet in Kiel. Note that the failing of the
            support is not explicitly mentioned in the rulebooks (the DPTG is more clear about this point). If you take
            the rulebooks very literally, you might conclude that the fleet in Munich is not dislodged, but this is an
            incorrect interpretation.
        """
        b = BoardBuilder()
        f_kiel = b.move(b.germany, UnitType.FLEET, "Kiel", "Munich")
        a_burgundy = b.supportMove(b.germany, UnitType.ARMY, "Burgundy", f_kiel, "Munich")
        a_munich = b.move(b.russia, UnitType.ARMY, "Munich", "Kiel")
        a_berlin = b.supportMove(b.russia, UnitType.ARMY, "Berlin", a_munich, "Kiel")

        b.assertIllegal(f_kiel, a_burgundy)
        b.assertSuccess(a_munich, a_berlin)
        b.assertDislodge(f_kiel)
        b.moves_adjudicate(self)

    def test_6_d_23(self):
        """ 6.D.23. TEST CASE, IMPOSSIBLE COAST MOVE CAN NOT BE SUPPORTED
            Comparable with the previous test case, but now the fleet move is impossible for coastal reasons.
            Italy: F Gulf of Lyon - Spain(sc)
            Italy: F Western Mediterranean Supports F Gulf of Lyon - Spain(sc)
            France: F Spain(nc) - Gulf of Lyon
            France: F Marseilles Supports F Spain(nc) - Gulf of Lyon
            The French move from Spain North Coast to Gulf of Lyon is illegal (wrong coast). Therefore, the support
            from Marseilles fails and the fleet in Spain is dislodged.
        """
        b = BoardBuilder()
        f_gulf_of_lyon = b.move(b.italy, UnitType.FLEET, "Gulf of Lyon", "Spain sc")
        f_western_mediterranean = b.supportMove(b.italy, UnitType.FLEET, "Western Mediterranean Sea", f_gulf_of_lyon, "Spain sc")
        f_spain_nc = b.move(b.france, UnitType.FLEET, "Spain nc", "Gulf of Lyon")
        f_marseilles = b.supportMove(b.france, UnitType.FLEET, "Marseilles", f_spain_nc, "Gulf of Lyon")

        b.assertIllegal(f_spain_nc, f_marseilles)
        b.assertSuccess(f_gulf_of_lyon, f_western_mediterranean)
        b.assertDislodge(f_spain_nc)
        b.moves_adjudicate(self)

    def test_6_d_24(self):
        """ 6.D.24. TEST CASE, IMPOSSIBLE ARMY MOVE CAN NOT BE SUPPORTED
            Comparable with the previous test case, but now an army tries to move into sea and the support is used in a
            beleaguered garrison.
            France: A Marseilles - Gulf of Lyon
            France: F Spain(sc) Supports A Marseilles - Gulf of Lyon
            Italy: F Gulf of Lyon Hold
            Turkey: F Tyrrhenian Sea Supports F Western Mediterranean - Gulf of Lyon
            Turkey: F Western Mediterranean - Gulf of Lyon
            The French move from Marseilles to Gulf of Lyon is illegal (an army can not go to sea). Therefore,
            the support from Spain fails and there is no beleaguered garrison. The fleet in the Gulf of Lyon is
            dislodged by the Turkish fleet in the Western Mediterranean.
        """
        b = BoardBuilder()
        a_marseilles = b.move(b.france, UnitType.ARMY, "Marseilles", "Gulf of Lyon")
        a_spain_sc = b.supportMove(b.france, UnitType.FLEET, "Spain sc", a_marseilles, "Gulf of Lyon")
        f_gulf_of_lyon = b.hold(b.italy, UnitType.FLEET, "Gulf of Lyon")
        f_western_mediterranean = b.move(b.turkey, UnitType.FLEET, "Western Mediterranean Sea", "Gulf of Lyon")
        f_tyrrhenian_sea = b.supportMove(b.turkey, UnitType.FLEET, "Tyrrhenian Sea", f_western_mediterranean, "Gulf of Lyon")

        b.assertIllegal(a_marseilles, a_spain_sc)
        b.assertDislodge(f_gulf_of_lyon)
        b.assertSuccess(f_western_mediterranean, f_tyrrhenian_sea)
        b.moves_adjudicate(self)

    def test_6_d_25(self):
        """ 6.D.25. TEST CASE, FAILING HOLD SUPPORT CAN BE SUPPORTED
            If an adjudicator fails on one of the previous three test cases, then the bug should be removed with care.
            A failing move can not be supported, but a failing hold support, because of some preconditions (unmatching
            order) can still be supported.
            Germany: A Berlin Supports A Prussia
            Germany: F Kiel Supports A Berlin
            Russia: F Baltic Sea Supports A Prussia - Berlin
            Russia: A Prussia - Berlin
            Although the support of Berlin on Prussia fails (because of unmatching orders), the support of Kiel on
            Berlin is still valid. So, Berlin will not be dislodged.
        """
        b = BoardBuilder()
        a_prussia = b.move(b.russia, UnitType.ARMY, "Prussia", "Berlin")
        f_baltic_sea = b.supportMove(b.russia, UnitType.FLEET, "Baltic Sea", a_prussia, "Berlin")
        a_berlin = b.supportHold(b.germany, UnitType.ARMY, "Berlin", a_prussia)
        f_kiel = b.supportHold(b.germany, UnitType.FLEET, "Kiel", a_berlin)

        b.assertIllegal(a_berlin)
        b.assertFail(a_prussia)
        b.assertSuccess(f_kiel, f_baltic_sea)
        b.assertNotDislodge(a_berlin)
        b.moves_adjudicate(self)

    def test_6_d_26(self):
        """ 6.D.26. TEST CASE, FAILING MOVE SUPPORT CAN BE SUPPORTED
            Similar as the previous test case, but now with an unmatched support to move.
            Germany: A Berlin Supports A Prussia - Silesia
            Germany: F Kiel Supports A Berlin
            Russia: F Baltic Sea Supports A Prussia - Berlin
            Russia: A Prussia - Berlin
            Again, Berlin will not be dislodged.
        """
        b = BoardBuilder()
        a_prussia = b.move(b.russia, UnitType.ARMY, "Prussia", "Berlin")
        f_baltic_sea = b.supportMove(b.russia, UnitType.FLEET, "Baltic Sea", a_prussia, "Berlin")
        a_berlin = b.supportMove(b.germany, UnitType.ARMY, "Berlin", a_prussia, "Silesia")
        f_kiel = b.supportHold(b.germany, UnitType.FLEET, "Kiel", a_berlin)

        b.assertIllegal(a_berlin)
        b.assertFail(a_prussia)
        b.assertSuccess(f_kiel, f_baltic_sea)
        b.assertNotDislodge(a_berlin)
        b.moves_adjudicate(self)

    def test_6_d_27(self):
        """ 6.D.27. TEST CASE, FAILING CONVOY CAN BE SUPPORTED
            Similar as the previous test case, but now with an unmatched convoy.
            England: F Sweden - Baltic Sea
            England: F Denmark Supports F Sweden - Baltic Sea
            Germany: A Berlin Hold
            Russia: F Baltic Sea Convoys A Berlin - Livonia
            Russia: F Prussia Supports F Baltic Sea
            The convoy order in the Baltic Sea is unmatched and fails. However, the support of Prussia on the Baltic Sea
            is still valid and the fleet in the Baltic Sea is not dislodged.
        """
        b = BoardBuilder()
        f_sweden = b.move(b.england, UnitType.FLEET, "Sweden", "Baltic Sea")
        f_denmark = b.supportMove(b.england, UnitType.FLEET, "Denmark", f_sweden, "Baltic Sea")
        a_berlin = b.hold(b.germany, UnitType.ARMY, "Berlin")
        f_baltic_sea = b.convoy(b.russia, "Baltic Sea", a_berlin, "Livonia")
        f_prussia = b.supportHold(b.russia, UnitType.FLEET, "Prussia", f_baltic_sea)

        b.assertIllegal(f_baltic_sea)
        b.assertSuccess(f_prussia, f_denmark)
        b.assertFail(f_sweden)
        b.assertNotDislodge(f_baltic_sea)
        b.moves_adjudicate(self)

    # DEVIATES
    def test_6_d_28(self):
        """ 6.D.28. TEST CASE, IMPOSSIBLE MOVE AND SUPPORT
            If a move is impossible then it can be treated as "illegal", which makes a hold support possible.
            Austria: A Budapest Supports F Rumania
            Russia: F Rumania - Holland
            Turkey: F Black Sea - Rumania
            Turkey: A Bulgaria Supports F Black Sea - Rumania
            The move of the Russian fleet is impossible. But the question is, whether it is "illegal" (see issue 4.E.1).
            If the move is "illegal" it must be ignored and that makes the hold support of the army in Budapest valid
            and the fleet in Rumania will not be dislodged.
            I prefer that the move is "illegal", which means that the fleet in the Black Sea does not dislodge the
            supported Russian fleet.
            
            Note that we treat impossible moves as unsupportable, so the test case has been adjusted accordingly.
        """ 
        b = BoardBuilder()
        f_rumania = b.move(b.russia, UnitType.FLEET, "Rumania", "Holland")
        a_budapest = b.supportHold(b.austria, UnitType.ARMY, "Budapest", f_rumania)
        f_black_sea = b.move(b.turkey, UnitType.FLEET, "Black Sea", "Rumania")
        a_bulgaria = b.supportMove(b.turkey, UnitType.ARMY, "Bulgaria", f_black_sea, "Rumania")

        b.assertIllegal(f_rumania)
        b.assertSuccess(f_black_sea)
        b.assertFail(a_budapest)
        b.assertDislodge(f_rumania)
        b.moves_adjudicate(self)

    def test_6_d_29(self):
        """ 6.D.29. TEST CASE, MOVE TO IMPOSSIBLE COAST AND SUPPORT
            Similar to the previous test case, but now the move can be "illegal" because of the wrong coast.
            Austria: A Budapest Supports F Rumania
            Russia: F Rumania - Bulgaria(sc)
            Turkey: F Black Sea - Rumania
            Turkey: A Bulgaria Supports F Black Sea - Rumania
            Again the move of the Russian fleet is impossible. However, some people might correct the coast
            (see issue 4.B.3). If the coast is not corrected, again the question is whether it is "illegal" (see
            issue 4.E.1). If the move is "illegal" it must be ignored and that makes the hold support of the army in
            Budapest valid and the fleet in Rumania will not be dislodged.
            I prefer that unambiguous orders are not changed and that the move is "illegal". That means that the fleet
            in the Black Sea does not dislodge the supported Russian fleet.
            
            Note that we treat impossible moves as unsupportable, so the test case has been adjusted accordingly.
        """
        b = BoardBuilder()
        f_rumania = b.move(b.russia, UnitType.FLEET, "Rumania", "Bulgaria sc")
        a_budapest = b.supportHold(b.austria, UnitType.ARMY, "Budapest", f_rumania)
        f_black_sea = b.move(b.turkey, UnitType.FLEET, "Black Sea", "Rumania")
        a_bulgaria = b.supportMove(b.turkey, UnitType.ARMY, "Bulgaria", f_black_sea, "Rumania")

        b.assertIllegal(f_rumania)
        b.assertSuccess(f_black_sea)
        b.assertFail(a_budapest)
        b.assertDislodge(f_rumania)
        b.moves_adjudicate(self)

    def test_6_d_30(self):
        """ 6.D.30. TEST CASE, MOVE WITHOUT COAST AND SUPPORT
            Similar to the previous test case, but now the move can be "illegal" because of missing coast.
            Italy: F Aegean Sea Supports F Constantinople
            Russia: F Constantinople - Bulgaria
            Turkey: F Black Sea - Constantinople
            Turkey: A Bulgaria Supports F Black Sea - Constantinople
            Again the order to the Russian fleet is with problems, because it does not specify the coast, while both
            coasts of Bulgaria are possible. If no default coast is taken (see issue 4.B.1), then also here it must be
            decided whether the order is "illegal" (see issue 4.E.1). If the move is "illegal" it must be ignored and
            that makes the hold support of the fleet in the Aegean Sea valid and the Russian fleet will not be
            dislodged. I don't like default coasts and I prefer that the move is "illegal". That means that the fleet
            in the Black Sea does not dislodge the supported Russian fleet.
            
            Note that we treat impossible moves as unsupportable, so the test case has been adjusted accordingly.
        """
        b = BoardBuilder()
        f_constantinople = b.move(b.russia, UnitType.FLEET, "Constantinople", "Bulgaria")
        f_aegean_sea = b.supportHold(b.italy, UnitType.FLEET, "Aegean Sea", f_constantinople)
        f_black_sea = b.move(b.turkey, UnitType.FLEET, "Black Sea", "Constantinople")
        a_bulgaria = b.supportMove(b.turkey, UnitType.ARMY, "Bulgaria", f_black_sea, "Constantinople")

        b.assertDislodge(f_constantinople)
        b.assertFail(f_aegean_sea)
        b.assertSuccess(f_black_sea, a_bulgaria)
        b.moves_adjudicate(self)

    def test_6_d_31(self):
        """ 6.D.31. TEST CASE, A TRICKY IMPOSSIBLE SUPPORT
            A support order can be impossible for complex reasons.
            Austria: A Rumania - Armenia
            Turkey: F Black Sea Supports A Rumania - Armenia
            Although the army in Rumania can move to Armenia and the fleet in the Black Sea can also go to Armenia,
            the support is still not possible. The reason is that the only possible convoy is through the Black Sea and
            a fleet can not convoy and support at the same time.
            This is relevant for computer programs that show only the possible orders. In the list of possible orders,
            the support as given to the fleet in the Black Sea, should not be listed. Furthermore, if the fleet in the
            Black Sea gets a second order, then this may fail, because of double orders (although it can also be ruled
            differently, see issue 4.D.3). However, when the support order is considered "illegal" (see issue 4.E.1),
            then this impossible support must be ignored and the second order must be carried out.
            I prefer that impossible orders are "illegal" and ignored. If there would be a second order for the fleet
            in the Black Sea, that order should be carried out.
            
            Note that we treat impossible moves as unsupportable, so the test case has been adjusted accordingly.
        """
        b = BoardBuilder()
        a_rumania = b.move(b.austria, UnitType.ARMY, "Rumania", "Armenia")
        f_black_sea = b.supportMove(b.turkey, UnitType.FLEET, "Black Sea", a_rumania, "Armenia")

        b.assertIllegal(a_rumania, f_black_sea)
        b.moves_adjudicate(self)

    def test_6_d_32(self):
        """ 6.D.32. TEST CASE, A MISSING FLEET
            The previous test cases contained an order that was impossible even when some other pieces on the board
            where changed. In this test case, the order is impossible, but only for that situation.
            England: F Edinburgh Supports A Liverpool - Yorkshire
            England: A Liverpool - Yorkshire
            France: F London Supports A Yorkshire
            Germany: A Yorkshire - Holland
            The German order to Yorkshire can not be executed, because there is no fleet in the North Sea. In other
            situations (where there is a fleet in the North Sea), the exact same order would be possible. It should be
            determined whether this is "illegal" (see issue 4.E.1) or not. If it is illegal, then the order should be
            ignored and the support of the French fleet in London succeeds. This means that the army in Yorkshire is
            not dislodged.
            I prefer that impossible orders, even if it is only impossible for the current situation, are "illegal" and
            ignored. The army in Yorkshire is not dislodged.
        """
        b = BoardBuilder()
        a_liverpool = b.move(b.england, UnitType.ARMY, "Liverpool", "Yorkshire")
        f_edinburgh = b.supportMove(b.england, UnitType.FLEET, "Edinburgh", a_liverpool, "Yorkshire")
        a_yorkshire = b.move(b.germany, UnitType.ARMY, "Yorkshire", "Holland")
        f_london = b.supportHold(b.france, UnitType.FLEET, "London", a_yorkshire)

        b.assertDislodge(a_yorkshire)
        b.assertIllegal(a_yorkshire)
        b.assertSuccess(f_edinburgh)
        b.assertFail(f_london)
        # deviates since we consider invalid moves as not support holdable
        b.assertSuccess(a_liverpool)
        b.moves_adjudicate(self)

    def test_6_d_33(self):
        """ 6.D.33. TEST CASE, UNWANTED SUPPORT ALLOWED
            A self stand-off can be broken by an unwanted support.
            Austria: A Serbia - Budapest
            Austria: A Vienna - Budapest
            Russia: A Galicia Supports A Serbia - Budapest
            Turkey: A Bulgaria - Serbia
            Due to the Russian support, the army in Serbia advances to Budapest. This enables Turkey to capture
            Serbia with the army in Bulgaria.
        """
        b = BoardBuilder()
        a_serbia = b.move(b.austria, UnitType.ARMY, "Serbia", "Budapest")
        a_vienna = b.move(b.austria, UnitType.ARMY, "Vienna", "Budapest")
        a_galicia = b.supportMove(b.russia, UnitType.ARMY, "Galicia", a_serbia, "Budapest")
        a_bulgaria = b.move(b.turkey, UnitType.ARMY, "Bulgaria", "Serbia")

        b.assertSuccess(a_serbia, a_bulgaria)
        b.assertFail(a_vienna)
        b.moves_adjudicate(self)

    def test_6_d_34(self):
        """ 6.D.34. TEST CASE, SUPPORT TARGETING OWN AREA NOT ALLOWED
            Support targeting the area where the supporting unit is standing, is illegal.
            Germany: A Berlin - Prussia
            Germany: A Silesia Supports A Berlin - Prussia
            Germany: F Baltic Sea Supports A Berlin - Prussia
            Italy: A Prussia Supports Livonia - Prussia
            Russia: A Warsaw Supports A Livonia - Prussia
            Russia: A Livonia - Prussia
            Russia and Italy wanted to get rid of the Italian army in Prussia (to build an Italian fleet somewhere
            else). However, they didn't want a possible German attack on Prussia to succeed. They invented this odd
            order of Italy. It was intended that the attack of the army in Livonia would have strength three, so it
            would be capable to prevent the possible German attack to succeed. However, the order of Italy is illegal,
            because a unit may only support to an area where the unit can go by itself. A unit can't go to the area it
            is already standing, so the Italian order is illegal and the German move from Berlin succeeds. Even if it
            would be legal, the German move from Berlin would still succeed, because the support of Prussia is cut by
            Livonia and Berlin.
        """
        b = BoardBuilder()
        a_berlin = b.move(b.germany, UnitType.ARMY, "Berlin", "Prussia")
        a_silesia = b.supportMove(b.germany, UnitType.ARMY, "Silesia", a_berlin, "Prussia")
        f_baltic_sea = b.supportMove(b.germany, UnitType.FLEET, "Baltic Sea", a_berlin, "Prussia")
        a_prussia = b.supportMove(b.italy, UnitType.ARMY, "Prussia", a_berlin, "Prussia") # illegal
        a_livonia = b.move(b.russia, UnitType.ARMY, "Livonia", "Prussia")
        a_warsaw = b.supportMove(b.russia, UnitType.ARMY, "Warsaw", a_livonia, "Prussia")

        b.assertIllegal(a_prussia)
        b.assertSuccess(a_berlin, a_silesia, f_baltic_sea, a_warsaw)
        b.assertFail(a_livonia)
        b.assertDislodge(a_prussia)
        b.moves_adjudicate(self)
