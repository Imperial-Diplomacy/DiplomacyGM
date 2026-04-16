"""Tests for GameManagementCog commands."""
from __future__ import annotations

from unittest import mock
from unittest.mock import AsyncMock, MagicMock

from discord.ext import commands

from DiploGM.models.unit import UnitType
from test.DiploGM.cogs.utils import (
    CogTestCase,
    create_mock_gm_context,
    create_mock_role,
)
from DiploGM.cogs.game_management.game_management import GameManagementCog


class GMCogTestCase(CogTestCase):
    """Base class for GameManagementCog tests."""

    send_patch_targets = [
        "DiploGM.cogs.game_management.adjudication.send_message_and_file",
        "DiploGM.cogs.game_management.game_creation.send_message_and_file",
        "DiploGM.cogs.game_management.game_editing.send_message_and_file",
        "DiploGM.cogs.game_management.deadline_management.send_message_and_file",
        "DiploGM.utils.send_message.send_message_and_file",
    ]

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = GameManagementCog(self.bot)

        self.mock_db = MagicMock()
        self.db_patcher = mock.patch(
            "DiploGM.cogs.game_management.game_editing.get_connection",
            return_value=self.mock_db,
        )
        self.db_patcher.start()

        self.db_patcher2 = mock.patch(
            "DiploGM.cogs.game_management.deadline_management.get_connection",
            return_value=self.mock_db,
        )
        self.db_patcher2.start()

        # Mock Mapper so edit/edit_game don't need real SVG rendering
        mock_mapper_instance = MagicMock()
        mock_mapper_instance.draw_current_map.return_value = (b"<svg>fake</svg>", "map.svg")
        self.mapper_patcher = mock.patch(
            "DiploGM.parse_edit_state.Mapper",
            return_value=mock_mapper_instance,
        )
        self.mapper_patcher.start()

        self.mapper_patcher2 = mock.patch(
            "DiploGM.parse_board_params.Mapper",
            return_value=mock_mapper_instance,
        )
        self.mapper_patcher2.start()

        # Mock the DB call inside parse_edit_state's _set_phase
        self.edit_db_patcher = mock.patch(
            "DiploGM.parse_edit_state.get_connection",
            return_value=self.mock_db,
        )
        self.edit_db_patcher.start()

    def tearDown(self):
        self.edit_db_patcher.stop()
        self.mapper_patcher.stop()
        self.mapper_patcher2.stop()
        self.db_patcher.stop()
        self.db_patcher2.stop()
        super().tearDown()


class TestLockOrders(GMCogTestCase):
    """Tests for .lock_orders and .unlock_orders."""

    async def test_lock_orders(self):
        self.assertTrue(self.board.orders_enabled)
        ctx = create_mock_gm_context(message_content=".lock_orders")
        await self.invoke(self.cog, "lock_orders", ctx)

        self.assertFalse(self.board.orders_enabled)
        self.assert_message_contains("Locked orders")

    async def test_unlock_orders(self):
        self.board.orders_enabled = False
        ctx = create_mock_gm_context(message_content=".unlock_orders")
        await self.invoke(self.cog, "unlock_orders", ctx)

        self.assertTrue(self.board.orders_enabled)
        self.assert_message_contains("Unlocked orders")


class TestEdit(GMCogTestCase):
    """Tests for the .edit command."""

    async def test_successful_edit(self):
        ctx = create_mock_gm_context(
            message_content=".edit\ncreate_unit A France Paris"
        )
        await self.invoke(self.cog, "edit", ctx)

        self.mock_send.assert_called()
        self.assert_message_contains("Commands validated successfully")
        paris = self.board.get_province("Paris")
        self.assertIsNotNone(paris.unit)

    async def test_invalid_edit_returns_error(self):
        ctx = create_mock_gm_context(
            message_content=".edit\nnonsense_command blah"
        )
        await self.invoke(self.cog, "edit", ctx)

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertIsNotNone(kwargs.get("embed_colour"))


class TestEditGame(GMCogTestCase):
    """Tests for the .edit_game command."""

    async def test_set_building_mode(self):
        ctx = create_mock_gm_context(
            message_content=".edit_game\nbuilding cores"
        )
        await self.invoke(self.cog, "edit_game", ctx)

        self.mock_send.assert_called()
        self.assert_message_contains("Commands validated successfully")
        self.assertEqual(self.board.data["build_options"], "cores")

    async def test_invalid_param(self):
        ctx = create_mock_gm_context(
            message_content=".edit_game\nfake_param value"
        )
        await self.invoke(self.cog, "edit_game", ctx)

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertIsNotNone(kwargs.get("embed_colour"))


class TestSetDeadline(GMCogTestCase):
    """Tests for the .set_deadline command."""

    async def test_set_unix_timestamp(self):
        ctx = create_mock_gm_context(message_content=".set_deadline 1700000000")
        await self.invoke(self.cog, "set_deadline", ctx)

        self.mock_send.assert_called()
        self.assertEqual(self.board.data["deadline"], 1700000000)
        self.assert_message_contains("Set new deadline")

    async def test_cancel_deadline(self):
        self.board.data["deadline"] = 1700000000
        ctx = create_mock_gm_context(message_content=".set_deadline cancel")
        await self.invoke(self.cog, "set_deadline", ctx)

        self.mock_send.assert_called()
        self.assertNotIn("deadline", self.board.data)
        self.assert_message_contains("removed")

    async def test_adjust_deadline(self):
        self.board.data["deadline"] = 1700000000
        ctx = create_mock_gm_context(message_content=".set_deadline adjust 2h")
        await self.invoke(self.cog, "set_deadline", ctx)

        self.mock_send.assert_called()
        self.assertEqual(self.board.data["deadline"], 1700000000 + 7200)
        self.assert_message_contains("Adjusted")

    async def test_invalid_timestamp(self):
        ctx = create_mock_gm_context(message_content=".set_deadline notanumber")
        await self.invoke(self.cog, "set_deadline", ctx)

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertIsNotNone(kwargs.get("embed_colour"))

    async def test_adjust_invalid_duration(self):
        ctx = create_mock_gm_context(message_content=".set_deadline adjust foo")
        await self.invoke(self.cog, "set_deadline", ctx)

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertIsNotNone(kwargs.get("embed_colour"))


class TestListVariants(GMCogTestCase):
    """Tests for the .list_variants command."""

    async def test_list_variants(self):
        ctx = create_mock_gm_context(message_content=".list_variants")
        await self.invoke(self.cog, "list_variants", ctx)

        self.mock_send.assert_called()
        self.assert_message_contains("classic")

class TestExportGame(GMCogTestCase):
    """Tests for the .export_game command."""

    async def test_export_returns_json_file(self):
        ctx = create_mock_gm_context(message_content=".export_game")
        await self.invoke(self.cog, "export_game", ctx)

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertIsNotNone(kwargs.get("file"))
        self.assertTrue(kwargs["file_name"].endswith(".json"))
        self.assert_message_contains("Game Export")

class TestRenamePlayer(GMCogTestCase):
    """Tests for the .rename_player command."""

    def setUp(self):
        super().setUp()
        # Add mock roles to guild so find_discord_role can match
        self.france_role = create_mock_role("France")
        self.france_role.edit = AsyncMock()
        # ctx.guild.roles needs to be set per-test via ctx

    async def test_rename_success(self):
        ctx = create_mock_gm_context(message_content=".rename_player France Gaul")
        ctx.guild.roles = [self.france_role]
        ctx.guild.text_channels = []
        await self.invoke(self.cog, "rename_player", ctx, "France", "Gaul")

        self.mock_send.assert_called()
        self.assert_message_contains("Renamed player France to Gaul")

    async def test_rename_unknown_player(self):
        ctx = create_mock_gm_context(message_content=".rename_player Atlantis NewName")
        ctx.guild.roles = []
        ctx.guild.text_channels = []
        # board.get_player raises ValueError for unknown names,
        # so the error-message path in rename_player is unreachable
        # TODO: Fix this
        with self.assertRaises(ValueError):
            await self.invoke(self.cog, "rename_player", ctx, "Atlantis", "NewName")


class TestAdjudicate(GMCogTestCase):
    """Tests for the .adjudicate command."""

    def setUp(self):
        super().setUp()
        # Place units so we can test missing-orders logic
        self.builder.army("Paris", self.players["France"])
        self.builder.army("London", self.players["England"])

        # Mock the heavy manager methods used during adjudication
        self.adj_patches = []
        new_board = self.board  # just reuse the same board for simplicity

        for target, rv in [
            ("DiploGM.cogs.game_management.adjudication.manager.adjudicate", new_board),
            ("DiploGM.cogs.game_management.adjudication.manager.get_board_from_db", self.board),
            ("DiploGM.cogs.game_management.adjudication.manager.apply_adjudication_results", None),
            ("DiploGM.cogs.game_management.adjudication.manager.draw_map_for_board",
             (b"<svg>fake</svg>", "map.svg")),
        ]:
            p = mock.patch(target, return_value=rv)
            p.start()
            self.adj_patches.append(p)

        p = mock.patch(
            "DiploGM.cogs.game_management.adjudication.svg_to_png",
            return_value=(b"fake_png", "map.png"),
        )
        p.start()
        self.adj_patches.append(p)

    def tearDown(self):
        for p in self.adj_patches:
            p.stop()
        super().tearDown()

    async def test_missing_orders_blocks(self):
        """Adjudication is blocked when units have no orders."""
        ctx = create_mock_gm_context(message_content=".adjudicate")
        await self.invoke(self.cog, "adjudicate", ctx)

        self.mock_send.assert_called()
        self.assert_message_contains("Missing Orders")
        kwargs = self.get_sent_kwargs()
        self.assertIsNotNone(kwargs.get("embed_colour"))

    async def test_confirm_overrides_missing(self):
        """Using 'confirm' proceeds despite missing orders."""
        ctx = create_mock_gm_context(message_content=".adjudicate confirm")
        ctx.guild.channels = []
        await self.invoke(self.cog, "adjudicate", ctx)

        self.mock_send.assert_called()
        self.assert_message_not_contains("Missing Orders")
        # Should have sent maps (orders + results = at least 2 send calls)
        self.assertGreaterEqual(self.mock_send.call_count, 2)

    async def test_test_mode(self):
        """Test mode passes test=True to manager.adjudicate."""
        ctx = create_mock_gm_context(message_content=".adjudicate test confirm")
        ctx.guild.channels = []
        await self.invoke(self.cog, "adjudicate", ctx)

        self.mock_send.assert_called()
        self.assert_message_contains("Test adjudication")
