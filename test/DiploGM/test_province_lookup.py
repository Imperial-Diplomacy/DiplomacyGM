import unittest
from test.utils import BoardBuilder

class TestProvinceLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Build the board once for all tests in this class."""
        cls.board = BoardBuilder().board

    def assertLookupContains(self, query: str, *expected: str):
        """Assert that looking up query raises a ValueError whose message
        contains every string in expected."""
        with self.assertRaises(ValueError) as ctx:
            self.board.get_province_and_coast(query)
        error = str(ctx.exception)
        for s in expected:
            self.assertIn(s, error, f"Expected {s!r} in error for query {query!r}, got: {error!r}")

    def test_province_lookup(self):
        province, coast = self.board.get_province_and_coast("Paris")
        self.assertEqual(province.name, "Paris")
        self.assertIsNone(coast)

        province, coast = self.board.get_province_and_coast("Spain sc")
        self.assertEqual(province.name, "Spain")
        self.assertEqual(coast, "sc")

        province, _ = self.board.get_province_and_coast("Nort Sea")
        self.assertEqual(province.name, "North Sea")

        province, _ = self.board.get_province_and_coast("Tyrrhenia")
        self.assertEqual(province.name, "Tyrrhenian Sea")

        self.assertLookupContains("Londn", "Did you mean", "London")
        self.assertLookupContains("Venec", "Did you mean", "Venice")
        self.assertLookupContains("Helgoland", "Did you mean", "Heligoland Bight")
        self.assertLookupContains("Span nc", "Did you mean", "Spain nc", "Spain sc")

        for gibberish in ("qqqqqqqq", "foobarlmnop"):
            with self.assertRaises(ValueError) as ctx:
                self.board.get_province_and_coast(gibberish)
            self.assertNotIn("Did you mean", str(ctx.exception))
