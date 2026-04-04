"""Tests for the DP order."""
import unittest

from test.utils import BoardBuilder
from DiploGM.models.order import Move, Support
from DiploGM.models.unit import UnitType

class TestDP(unittest.TestCase):
    """Tests for DP orders, which can be used by players to 'bid' points to give orders to neutral units."""
    def test_dp_1(self):
        """
            Basic test for DP orders.
            England: DP 1: A Serbia - Albania
            Austria: F Trieste - Albania
            Trieste should be bounced out by Serbia
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_albania = b.board.get_province("Albania")
        f_trieste = b.move(b.players["Austria"], UnitType.FLEET, "Trieste", "Albania")
        b.dp_order(b.players["England"], a_serbia, 1, Move(p_albania))

        b.assert_fail(a_serbia, f_trieste)
        b.moves_adjudicate(self)

    def test_dp_2(self):
        """
            Testing that DP works with supports.
            England: DP 1: A Serbia s Trieste = Albania
            Austria: F Trieste - Albania
            Turkey: A Greece - Albania
            Austria should be in Albania
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_trieste = b.board.get_province("Trieste")
        p_albania = b.board.get_province("Albania")
        f_trieste = b.move(b.players["Austria"], UnitType.FLEET, "Trieste", "Albania")
        a_greece = b.move(b.players["Turkey"], UnitType.ARMY, "Greece", "Albania")
        b.dp_order(b.players["England"], a_serbia, 1, Support(p_trieste, p_albania))

        b.assert_success(a_serbia, f_trieste)
        b.assert_fail(a_greece)
        b.moves_adjudicate(self)

    def test_dp_3(self):
        """
            Testing that DP works with support holds.
            England: DP 1: A Serbia s Trieste
            Austria: F Trieste h
            Italy: A Venice - Trieste
            Italy: F Adriatic Sea s Venice - Trieste
            The attack from Venice should fail
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_trieste = b.board.get_province("Trieste")
        p_albania = b.board.get_province("Albania")
        f_trieste = b.hold(b.players["Austria"], UnitType.FLEET, "Trieste")
        a_venice = b.move(b.players["Italy"], UnitType.ARMY, "Venice", "Trieste")
        f_adriatic_sea = b.support_move(b.players["Italy"], UnitType.FLEET, "Adriatic Sea", a_venice, "Trieste")
        b.dp_order(b.players["England"], a_serbia, 1, Support(p_trieste, p_trieste))

        b.assert_success(a_serbia, f_trieste, f_adriatic_sea)
        b.assert_fail(a_venice)
        b.assert_not_dislodge(f_trieste)
        b.moves_adjudicate(self)

    def test_dp_4(self):
        """
            If there are multiple DP bids on a unit, the highest bid should win.
            England: DP 1: A Serbia s Trieste - Albania
            France: DP 2: A Serbia - Albania
            Austria: F Trieste - Albania
            Trieste should be bounced out by Serbia
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_trieste = b.board.get_province("Trieste")
        p_albania = b.board.get_province("Albania")
        f_trieste = b.move(b.players["Austria"], UnitType.FLEET, "Trieste", "Albania")
        b.dp_order(b.players["England"], a_serbia, 1, Support(p_trieste, p_albania))
        b.dp_order(b.players["France"], a_serbia, 2, Move(p_albania))

        b.assert_fail(a_serbia, f_trieste)
        b.moves_adjudicate(self)

    def test_dp_5(self):
        """
            If there is a tie for DP point allocation, the unit should hold.
            England: DP 1: A Serbia s Trieste - Albania
            France: DP 1: A Serbia - Albania
            Austria: F Trieste - Albania
            The order from Trieste should succeed
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_trieste = b.board.get_province("Trieste")
        p_albania = b.board.get_province("Albania")
        f_trieste = b.move(b.players["Austria"], UnitType.FLEET, "Trieste", "Albania")
        b.dp_order(b.players["England"], a_serbia, 1, Support(p_trieste, p_albania))
        b.dp_order(b.players["France"], a_serbia, 1, Move(p_albania))

        b.assert_success(f_trieste)
        b.moves_adjudicate(self)

    def test_dp_6(self):
        """
            If multiple players bid for the same DP order, their bids should be combined
            England: DP 3: A Serbia s Trieste - Albania
            France: DP 2: A Serbia - Albania
            Germany: DP 2: A Serbia - Albania
            Austria: F Trieste - Albania
            The order from Trieste should bounce
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_trieste = b.board.get_province("Trieste")
        p_albania = b.board.get_province("Albania")
        f_trieste = b.move(b.players["Austria"], UnitType.FLEET, "Trieste", "Albania")
        b.dp_order(b.players["England"], a_serbia, 3, Support(p_trieste, p_albania))
        b.dp_order(b.players["France"], a_serbia, 2, Move(p_albania))
        b.dp_order(b.players["Germany"], a_serbia, 2, Move(p_albania))

        b.assert_fail(a_serbia, f_trieste)
        b.moves_adjudicate(self)

    def test_dp_7(self):
        """
            If a player is attacking a unit, any DP bids on it should fail
            England: DP 1: A Serbia - Greece
            Turkey: DP 2: A Serbia - Albania
            Austria: F Trieste - Albania
            Turkey: A Bulgaria - Serbia
            Turkey: F Aegean Sea - Greece
            The move from Aegean Sea should bounce, and the move from Trieste should succeed
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_greece = b.board.get_province("Greece")
        p_albania = b.board.get_province("Albania")
        f_trieste = b.move(b.players["Austria"], UnitType.FLEET, "Trieste", "Albania")
        a_bulgaria = b.move(b.players["Turkey"], UnitType.ARMY, "Bulgaria", "Serbia")
        f_aegean_sea = b.move(b.players["Turkey"], UnitType.FLEET, "Aegean Sea", "Greece")
        b.dp_order(b.players["England"], a_serbia, 1, Move(p_greece))
        b.dp_order(b.players["Turkey"], a_serbia, 2, Move(p_albania))

        b.assert_fail(a_serbia, a_bulgaria, f_aegean_sea)
        b.assert_success(f_trieste)
        b.moves_adjudicate(self)

    def test_dp_8(self):
        """
            If a player is supporting an attack on a unit, any DP bids on it should fail
            England: DP 1: A Serbia - Greece
            Turkey: DP 2: A Serbia - Albania
            Austria: A Trieste - Albania
            Turkey: A Bulgaria s Trieste - Serbia
            Turkey: F Aegean Sea - Greece
            The move from Aegean Sea should bounce, and the move from Trieste should succeed
        """
        b = BoardBuilder()
        a_serbia = b.army("Serbia", None)
        p_greece = b.board.get_province("Greece")
        p_albania = b.board.get_province("Albania")
        a_trieste = b.move(b.players["Austria"], UnitType.ARMY, "Trieste", "Albania")
        a_bulgaria = b.support_move(b.players["Turkey"], UnitType.ARMY, "Bulgaria", a_trieste, "Serbia")
        f_aegean_sea = b.move(b.players["Turkey"], UnitType.FLEET, "Aegean Sea", "Greece")
        b.dp_order(b.players["England"], a_serbia, 1, Move(p_greece))
        b.dp_order(b.players["Turkey"], a_serbia, 2, Move(p_albania))

        b.assert_fail(a_serbia, f_aegean_sea)
        b.assert_success(a_trieste)
        b.moves_adjudicate(self)
