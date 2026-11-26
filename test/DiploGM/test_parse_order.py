"""Tests for the order parsing functions."""
import unittest

from test.utils import BoardBuilder
from DiploGM.models.order import ConvoyTransport, Hold, Move, Support
from DiploGM.parse_order import parse_order, parse_remove_order

class TestParseOrder(unittest.TestCase):
    """Tests for the order parsing functions."""
    def test_order(self):
        """Tests that orders are parsed correctly from a .order string."""
        b = BoardBuilder()
        f_black_sea = b.fleet("Black Sea", b.players["Russia"])
        a_sevastopol = b.army("Sevastopol", b.players["Russia"])
        a_armenia = b.army("Armenia", b.players["Russia"])
        f_rumania = b.fleet("Rumania", b.players["Russia"])
        a_moscow = b.army("Moscow", b.players["Russia"])
        p_ankara = b.board.get_province("Ankara")

        order = ".order\n" + \
            "A Sevastopol - Ankara\n" + \
            "black sea convoy sevastopol to ankara\n" + \
            "armen s sEvAsToPoL to ankara\n" + \
            "f rumania s black sea holds\n" + \
            "a Moscow h"


        parse_order(order, b.players["Russia"], b.board)

        self.assertIsInstance(a_sevastopol.order, Move, "Sevastopol army order not parsed correctly")
        assert isinstance(a_sevastopol.order, Move)
        self.assertEqual(a_sevastopol.order.destination, p_ankara, "Sevastopol army move destination incorrect")

        self.assertIsInstance(f_black_sea.order, ConvoyTransport, "Black Sea fleet order not parsed correctly")
        assert isinstance(f_black_sea.order, ConvoyTransport)
        self.assertEqual(f_black_sea.order.source, a_sevastopol.province, "Black Sea fleet convoy source incorrect")
        self.assertEqual(f_black_sea.order.destination, p_ankara, "Black Sea fleet convoy destination incorrect")

        self.assertIsInstance(a_armenia.order, Support, "Armenia army order not parsed correctly")
        assert isinstance(a_armenia.order, Support)
        self.assertEqual(a_armenia.order.source, a_sevastopol.province, "Armenia army support source incorrect")
        self.assertEqual(a_armenia.order.destination, p_ankara, "Armenia army support destination incorrect")

        self.assertIsInstance(f_rumania.order, Support, "Rumania fleet order not parsed correctly")
        assert isinstance(f_rumania.order, Support)
        self.assertEqual(f_rumania.order.source, f_black_sea.province, "Rumania fleet support source incorrect")
        self.assertEqual(f_rumania.order.destination, f_black_sea.province, "Rumania fleet support destination incorrect")

        self.assertIsInstance(a_moscow.order, Hold, "Moscow army order not parsed correctly")

    def test_fow_order(self):
        """Tests for Fog of War scenarios."""
        b = BoardBuilder()
        b.board.data["fow"] = "enabled"
        a_berlin = b.army("Berlin", b.players["Germany"])
        a_munich = b.army("Munich", b.players["Germany"])
        f_naples = b.fleet("Naples", b.players["Italy"])
        order = ".order\n" + \
            "A Berlin - Sweden\n" + \
            "A Munich s Warsaw - Silesia\n" + \
            "F Naples - Rome\n" + \
            "A Paris - Gascony"

        result = parse_order(order, b.players["Germany"], b.board)

        p_sweden = b.board.get_province("Sweden")
        self.assertIsInstance(a_berlin.order, Move)
        assert isinstance(a_berlin.order, Move)
        self.assertEqual(a_berlin.order.destination, p_sweden)

        p_warsaw = b.board.get_province("Warsaw")
        p_silesia = b.board.get_province("Silesia")
        self.assertIsInstance(a_munich.order, Support)
        assert isinstance(a_munich.order, Support)
        self.assertEqual(a_munich.order.source, p_warsaw)
        self.assertEqual(a_munich.order.destination, p_silesia)

        self.assertIsNone(f_naples.order)
        output = "\n".join(result["messages"])
        self.assertEqual(output.count("You cannot order units in the Fog of War"), 2)
        self.assertIn("`F Naples - Rome`: You cannot order units in the Fog of War", output)
        self.assertIn("`A Paris - Gascony`: You cannot order units in the Fog of War", output)

    def test_remove_order(self):
        """Tests that orders can be removed via the .remove_order command."""
        b = BoardBuilder()
        a_berlin = b.move(b.players["Germany"], "A", "Berlin", "Kiel")

        order = "Berlin"
        parse_remove_order(order, b.players["Germany"], b.board)
        self.assertIsNone(a_berlin.order, "Order removal failed for Berlin army")
