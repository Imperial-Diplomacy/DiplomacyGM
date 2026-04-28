import unittest

from test.utils import BoardBuilder
from DiploGM.models.order import ConvoyTransport, Hold, Move, Support
from DiploGM.models.unit import UnitType
from DiploGM.parse_order import parse_order, parse_remove_order

class TestParseOrder(unittest.TestCase):
    def test_order(self):
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

    def test_remove_order(self):
        b = BoardBuilder()
        a_berlin = b.move(b.players["Germany"], UnitType.ARMY, "Berlin", "Kiel")

        order = "Berlin"
        parse_remove_order(order, b.players["Germany"], b.board)
        self.assertIsNone(a_berlin.order, "Order removal failed for Berlin army")
