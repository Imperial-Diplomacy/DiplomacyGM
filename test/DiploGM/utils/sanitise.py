import unittest

from DiploGM.models.turn import PhaseName, Turn
from DiploGM.utils.sanitise import parse_season

class TestSanitise(unittest.TestCase):
    def test_parse_season(self):
        input_phases = [
            "Spring 1901",
            "1901 fm",
            "Fr",
            "1902 wa",
            "1903",
            "1903 s r",
            ""
        ]
        output_turns = [
            Turn(1901, PhaseName.SPRING_MOVES),
            Turn(1901, PhaseName.FALL_MOVES),
            Turn(1902, PhaseName.FALL_RETREATS),
            Turn(1902, PhaseName.WINTER_BUILDS),
            Turn(1903, PhaseName.SPRING_MOVES),
            Turn(1903, PhaseName.SPRING_RETREATS),
            Turn(1903, PhaseName.SPRING_RETREATS),
        ]
        for input_phase, expected_turn in zip(input_phases, output_turns):
            output_turn = parse_season(input_phase.split(" "), Turn(1903, PhaseName.SPRING_RETREATS))
            self.assertEqual(output_turn.year, expected_turn.year, f"Failed to get proper year for input '{input_phase}'")
            self.assertEqual(output_turn.get_phase(), expected_turn.get_phase(), f"Failed to get proper phase for input '{input_phase}'")