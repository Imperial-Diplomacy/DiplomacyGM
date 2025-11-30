import unittest

from DiploGM.models.turn import Turn
from DiploGM.models.unit import UnitType
from DiploGM.parse_edit_state import _parse_command
from test.utils import BoardBuilder

class TestParseEditState(unittest.TestCase):
    def test_set_phase(self):
        b = BoardBuilder()
        _parse_command("set_phase Fall 1902", b.board)
        self.assertEqual(b.board.turn.year, 1902, "Failed to set year to 1902")
        self.assertEqual(b.board.turn.get_phase(), "Fall Moves", "Failed to set season to Fall")

    def test_set_core(self):
        b = BoardBuilder()
        _parse_command("set_core Belgium England", b.board)
        self.assertEqual(b.board.get_province("Belgium").core, b.england, "Failed to set core ownership for Belgium")
        _parse_command("set_core Belgium None", b.board)
        self.assertIsNone(b.board.get_province("Belgium").core, "Failed to remove core ownership for Belgium")

    def test_set_half_core(self):
        b = BoardBuilder()
        _parse_command("set_half_core Spain France", b.board)
        self.assertEqual(b.board.get_province("Spain").half_core, b.france, "Failed to add half-core ownership for Spain")
        _parse_command("set_half_core Spain None", b.board)
        self.assertIsNone(b.board.get_province("Spain").half_core, "Failed to remove half-core ownership for Spain")
    
    def test_set_player_color(self):
        b = BoardBuilder()
        _parse_command("set_player_color Italy FF5733", b.board)
        self.assertEqual(b.italy.render_color, "ff5733", "Failed to set Italy's color")

    def test_set_province_owner(self):
        b = BoardBuilder()
        _parse_command("set_province_owner Warsaw Austria", b.board)
        self.assertEqual(b.board.get_province("Warsaw").owner, b.austria, "Failed to set owner of Warsaw to Austria")
        _parse_command("set_province_owner Warsaw None", b.board)
        self.assertIsNone(b.board.get_province("Warsaw").owner, "Failed to remove owner of Warsaw")
    
    def test_set_total_owner(self):
        b = BoardBuilder()
        _parse_command("set_total_owner Vienna Germany", b.board)
        self.assertEqual(b.board.get_province("Vienna").owner, b.germany, "Failed to set owner of Vienna to Germany")
        self.assertEqual(b.board.get_province("Vienna").core, b.germany, "Failed to set core of Vienna to Germany")
        _parse_command("set_total_owner Vienna None", b.board)
        self.assertIsNone(b.board.get_province("Vienna").owner, "Failed to remove owner of Vienna")
        self.assertIsNone(b.board.get_province("Vienna").core, "Failed to remove core of Vienna")
    
    def test_create_unit(self):
        b = BoardBuilder()
        p_silesia = b.board.get_province("Silesia")
        p_kiel = b.board.get_province("Kiel")

        _parse_command("create_unit A Germany Silesia", b.board)
        a_silesia = p_silesia.unit
        self.assertIsNotNone(a_silesia, "Failed to create Army unit in Silesia")
        assert a_silesia is not None
        self.assertEqual(a_silesia.unit_type, UnitType.ARMY, "Created unit in Silesia is not an Army")
        self.assertEqual(a_silesia.player, b.germany, "Created unit in Silesia does not belong to Germany")
        
        _parse_command("create_unit F Germany Kiel", b.board)
        f_kiel = p_kiel.unit
        self.assertIsNotNone(f_kiel, "Failed to create Fleet unit in Kiel")
        assert f_kiel is not None
        self.assertEqual(f_kiel.unit_type, UnitType.FLEET, "Created unit in Kiel is not a Fleet")
        self.assertEqual(f_kiel.player, b.germany, "Created unit in Kiel does not belong to Germany")
    
    def test_create_dislodged_unit(self):
        b = BoardBuilder()
        b.board.turn = Turn(1901, "Spring Retreats")
        p_serbia = b.board.get_province("Serbia")
        p_trieste = b.board.get_province("Trieste")
        p_budapest = b.board.get_province("Budapest")
        p_bulgaria = b.board.get_province("Bulgaria")

        _parse_command("create_dislodged_unit A Germany Serbia Trieste Budapest", b.board)
        a_serbia = p_serbia.dislodged_unit
        self.assertIsNotNone(a_serbia, "Failed to create dislodged Army unit in Serbia")
        assert a_serbia is not None
        self.assertEqual(a_serbia.unit_type, UnitType.ARMY, "Created dislodged unit in Serbia is not an Army")
        self.assertEqual(a_serbia.player, b.germany, "Created dislodged unit in Serbia does not belong to Germany")
        self.assertIsNotNone(a_serbia.retreat_options, "Dislodged unit in Serbia has no retreat options initialized")
        self.assertIn((p_trieste, None), a_serbia.retreat_options or [], "Dislodged unit in Serbia missing retreat option to Bulgaria")
        self.assertIn((p_budapest, None), a_serbia.retreat_options or [], "Dislodged unit in Serbia missing retreat option to Budapest")

        _parse_command("create_dislodged_unit F Austria Bulgaria_ec", b.board)
        f_bulgaria = p_bulgaria.dislodged_unit
        assert f_bulgaria is not None
        self.assertIsNotNone(f_bulgaria, "Failed to create dislodged Fleet unit in Bulgaria_ec")
        self.assertEqual(f_bulgaria.coast, "ec", "Created dislodged Fleet in Bulgaria does not have correct coast 'ec'")
        self.assertEqual(f_bulgaria.unit_type, UnitType.FLEET, "Created dislodged unit in Bulgaria_ec is not a Fleet")
        self.assertEqual(f_bulgaria.player, b.austria, "Created dislodged unit in Bulgaria_ec does not belong to Austria")
        self.assertFalse(f_bulgaria.retreat_options, "Dislodged Fleet unit in Bulgaria_ec should have no retreat options")
    
    def test_delete_unit(self):
        b = BoardBuilder()
        f_liverpool = b.fleet("Liverpool", b.england)
        _parse_command("delete_unit Liverpool", b.board)
        self.assertIsNone(f_liverpool.province.unit, "Failed to delete Fleet unit in Liverpool")
    
    def test_delete_dislodged_unit(self):
        b = BoardBuilder()
        a_burgundy = b.move(b.germany, UnitType.ARMY, "Burgundy", "Paris")
        a_gascony = b.supportMove(b.germany, UnitType.ARMY, "Gascony", a_burgundy, "Paris")
        a_paris = b.hold(b.france, UnitType.ARMY, "Paris")
        p_paris = b.board.get_province("Paris")
        b.moves_adjudicate(self)
        b.board.turn = Turn(1901, "Spring Retreats")

        _parse_command("delete_dislodged_unit Paris", b.board)
        self.assertIsNone(p_paris.dislodged_unit, "Failed to delete dislodged Army unit in Paris")

    def test_move_unit(self):
        b = BoardBuilder()
        a_berlin = b.army("Berlin", b.germany)
        _parse_command("move_unit Berlin Prussia", b.board)
        self.assertEqual(a_berlin.province.name, "Prussia", "Failed to move Army unit from Berlin to Prussia")
        self.assertIsNone(b.board.get_province("Berlin").unit, "Old province Berlin still has unit after move")
        self.assertEqual(b.board.get_province("Prussia").unit, a_berlin, "New province Prussia does not have the moved unit")
    
    def test_dislodge_unit(self):
        b = BoardBuilder()
        b.board.turn = Turn(1901, "Spring Retreats")
        a_munich = b.army("Munich", b.germany)
        p_munich = b.board.get_province("Munich")
        
        _parse_command("dislodge_unit Munich", b.board)
        self.assertIsNone(p_munich.unit, "Province Munich still has standard unit after dislodging")
        self.assertIsNotNone(p_munich.dislodged_unit, "Dislodged unit in Munich not created after dislodging")
        assert p_munich.dislodged_unit is not None
        self.assertEqual(p_munich.dislodged_unit.player, b.germany, "Dislodged unit in Munich does not belong to Germany")
    
    def test_make_units_claim_provinces(self):
        b = BoardBuilder()
        f_tunis = b.fleet("Tunis", b.italy)
        a_north_africa = b.army("North Africa", b.italy)
        p_tunis = b.board.get_province("Tunis")
        p_north_africa = b.board.get_province("North Africa")

        _parse_command("make_units_claim_provinces", b.board)
        self.assertNotEqual(p_tunis.owner, b.italy, "Tunis should not be owned by Italy, as it is a supply center")
        self.assertEqual(p_north_africa.owner, b.italy, "North Africa should be owned by Italy")
        
        _parse_command("make_units_claim_provinces true", b.board)
        self.assertEqual(p_tunis.owner, b.italy, "Tunis should be owned by Italy after claiming all supply centers")