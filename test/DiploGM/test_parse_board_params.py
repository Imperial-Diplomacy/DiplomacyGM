import unittest

from test.utils import BoardBuilder
from DiploGM.parse_board_params import _parse_command

class TestParseBoardParams(unittest.TestCase):
    """Tests for parse_board_params._parse_command (the .edit_game commands)."""

    def test_set_build_options(self):
        """Tests that the build options can be set correctly."""
        b = BoardBuilder()
        _parse_command("building cores", b.board)
        self.assertEqual(b.board.data["build_options"], "cores")

    def test_set_transformation(self):
        """Tests that the transformation options can be set correctly."""
        b = BoardBuilder()
        _parse_command("transformation moves", b.board)
        self.assertEqual(b.board.data["transformation"], "moves")

    def test_toggle_dp(self):
        """Tests that the dp option can be toggled correctly."""
        b = BoardBuilder()
        _parse_command("dp enabled", b.board)
        self.assertEqual(b.board.data["dp"], "enabled")

    def test_toggle_convoyable_islands(self):
        """Tests that the convoyable_islands option can be toggled correctly."""
        b = BoardBuilder()
        _parse_command("convoyable_islands enabled", b.board)
        self.assertEqual(b.board.data["convoyable_islands"], "enabled")

    def test_set_victory_conditions(self):
        """Tests that the victory conditions can be set correctly."""
        b = BoardBuilder()
        _parse_command("victory_conditions vscc", b.board)
        self.assertEqual(b.board.data["victory_conditions"], "vscc")

    def test_set_victory_count(self):
        """Tests that the victory count can be set correctly."""
        b = BoardBuilder()
        _parse_command("victory_count 20", b.board)
        self.assertEqual(b.board.data["victory_count"], "20")

    def test_set_iscc(self):
        """Tests that the ISCC for a player can be set correctly."""
        b = BoardBuilder()
        _parse_command("iscc France 5", b.board)
        self.assertEqual(b.board.data["players"]["France"]["iscc"], "5")

    def test_set_vscc(self):
        """Tests that the VSCC for a player can be set correctly."""
        b = BoardBuilder()
        _parse_command("vscc England 10", b.board)
        self.assertEqual(b.board.data["players"]["England"]["vscc"], "10")

    def test_set_capital(self):
        """Tests that the capital for a player can be set correctly."""
        b = BoardBuilder()
        _parse_command("capital France Marseilles", b.board)
        self.assertEqual(b.board.data["players"]["France"]["capital"], "Marseilles")

    def test_set_player_name(self):
        """Tests that the name for a player can be set correctly."""
        b = BoardBuilder()
        _parse_command("player_name France Gaul", b.board)
        # Should be findable by new name
        self.assertIsNotNone(b.board.get_player("Gaul"))

    def test_hide_player(self):
        """Tests that a player can be hidden correctly."""
        b = BoardBuilder()
        _parse_command("hide_player Germany true", b.board)
        self.assertEqual(b.board.data["players"]["Germany"]["hidden"], "true")

    def test_add_player(self):
        """Tests that a player can be added correctly."""
        b = BoardBuilder()
        _parse_command("add_player Norway ff00ff", b.board)
        self.assertIsNotNone(b.board.get_player("Norway"))
