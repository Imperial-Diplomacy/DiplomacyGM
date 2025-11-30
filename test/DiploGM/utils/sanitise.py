import unittest

from DiploGM.models.turn import Turn
from DiploGM.utils.sanitise import parse_season

class TestSanitise(unittest.TestCase):
    def test_parse_season(self):
        input_phases = [
            "Spring 1901",
            "1901 fm",
            "Fr",
            "1902 wa",
            "1903",
        ]
        output_turns = [
            Turn(1901, "Spring Moves"),
            Turn(1901, "Fall Moves"),
            Turn(1902, "Fall Retreats"),
            Turn(1902, "Winter Builds"),
            Turn(1903, "Spring Moves"),
        ]
        for input_phase, expected_turn in zip(input_phases, output_turns):
            output_turn = parse_season(input_phase.split(" "), Turn(1903, "Spring Retreats"))
            self.assertEqual(output_turn.year, expected_turn.year, f"Failed to get proper year for input '{input_phase}'")
            self.assertEqual(output_turn.get_phase(), expected_turn.get_phase(), f"Failed to get proper phase for input '{input_phase}'")