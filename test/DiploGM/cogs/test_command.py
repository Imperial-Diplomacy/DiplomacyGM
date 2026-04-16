"""Tests for CommandCog (info, get_deadline, etc.)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from test.DiploGM.cogs.utils import CogTestCase, create_mock_context

from discord.ext import commands
from DiploGM.cogs.command import CommandCog
from DiploGM.errors import CommandPermissionError


async def invoke(cog, command_name: str, ctx, *args):
    """Invoke a cog command's underlying callback directly, bypassing discord.py dispatch."""
    cmd = getattr(cog, command_name)
    await cmd.callback(cog, ctx, *args)

class TestUptime(CogTestCase):
    """Tests for the .uptime command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.bot.creation_time = datetime.fromtimestamp(1234567890)
        self.cog = CommandCog(self.bot)

    async def test_uptime(self):
        ctx = create_mock_context(message_content=".uptime")
        self.cog.bot.last_command_time = None
        ctx.message.created_at = datetime.fromtimestamp(1234567895)
        await invoke(self.cog, "uptime", ctx)

        self.mock_send.assert_called_once()
        msg = self.get_sent_message()
        self.assertIn("has been awake", msg)
        self.assertIn("5 seconds", msg)
        self.assertIn("None so far in this uptime", msg)

    async def test_uptime_with_last_message_time(self):
        ctx = create_mock_context(message_content=".uptime")
        self.cog.bot.last_command_time = datetime.fromtimestamp(1234567892)
        ctx.message.created_at = datetime.fromtimestamp(1234567895)
        await invoke(self.cog, "uptime", ctx)

        self.mock_send.assert_called_once()
        msg = self.get_sent_message()
        self.assertIn("Last processed command", msg)
        self.assertIn("3 seconds ago", msg)

class TestScoreboard(CogTestCase):
    """Tests for the .scoreboard command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = CommandCog(self.bot)

    async def test_scoreboard_no_game(self):
        ctx = create_mock_context(guild_id=99999, message_content=".scoreboard")
        await invoke(self.cog, "scoreboard", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("no game")

    async def test_scoreboard(self):
        ctx = create_mock_context(message_content=".scoreboard")
        await invoke(self.cog, "scoreboard", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("Russia")

    async def test_scoreboard_alphabetically(self):
        ctx = create_mock_context(message_content=".scoreboard alpha")
        await invoke(self.cog, "scoreboard", ctx)

        self.mock_send.assert_called_once()
        self.assertRegex(self.get_sent_message(), r"(?s)Austria.*Russia")

    async def test_scoreboard_csv(self):
        ctx = create_mock_context(message_content=".scoreboard csv")
        await invoke(self.cog, "scoreboard", ctx)

        self.assert_ctx_send_contains(ctx, "3\n3\n3\n3\n3\n4\n3")

class TestInfo(CogTestCase):
    """Tests for the .info command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = CommandCog(self.bot)

    async def test_info_shows_data_with_no_deadline(self):
        ctx = create_mock_context(message_content=".info")
        await invoke(self.cog, "info", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("Turn:")
        self.assert_message_contains("Turn:")
        self.assert_message_contains("Open")
        self.assert_message_contains("Game Type:")
        self.assert_message_not_contains("Deadline:")

    async def test_info_shows_deadline_when_set(self):
        self.board.data["deadline"] = 1234567890
        ctx = create_mock_context(message_content=".info")
        await invoke(self.cog, "info", ctx)

        self.assert_message_contains("Deadline:")
        self.assert_message_contains("1234567890")

    async def test_info_no_game(self):
        """When no game exists for the guild, should report that."""
        ctx = create_mock_context(guild_id=99999, message_content=".info")
        await invoke(self.cog, "info", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("no game")

class TestDev(CogTestCase):
    """Tests for the .dev command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = CommandCog(self.bot)

    async def test_dev(self):
        self.bot.get_command.return_value = self.cog.info
        ctx = create_mock_context(message_content=".dev info")
        await invoke(self.cog, "dev", ctx, "info")

        self.mock_send.assert_called_once()
        self.assert_message_contains("Command Definition")
        self.assert_message_contains("info")

    async def test_dev_unknown_command(self):
        self.bot.get_command.return_value = None
        ctx = create_mock_context(message_content=".dev foo")
        await invoke(self.cog, "dev", ctx, "foo")

        self.mock_send.assert_called_once()
        self.assert_message_contains("No command found for name: foo")

class TestProvinceInfo(CogTestCase):
    """Tests for the .province_info command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = CommandCog(self.bot)

    async def test_province_info_no_game(self):
        ctx = create_mock_context(guild_id=99999, message_content=".province_info Paris")
        with self.assertRaises(RuntimeError):
            await invoke(self.cog, "province_info", ctx)

    async def test_province_info_orders_locked(self):
        self.board.orders_enabled = False
        ctx = create_mock_context(message_content=".province_info Paris")
        with self.assertRaises(CommandPermissionError):
            await invoke(self.cog, "province_info", ctx)

    async def test_province_info_with_space(self):
        ctx = create_mock_context(message_content=".province_info North Africa")
        await invoke(self.cog, "province_info", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("North Africa")
        self.assert_message_contains("Type:")
        self.assert_message_contains("Adjacent Provinces:")

    async def test_province_info_not_found(self):
        ctx = create_mock_context(message_content=".province_info Atlantis")
        await invoke(self.cog, "province_info", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("Could not find province")

class TestPlayerInfo(CogTestCase):
    """Tests for the .player_info command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = CommandCog(self.bot)

    async def test_player_info_no_game(self):
        ctx = create_mock_context(guild_id=99999, message_content=".player_info France")
        with self.assertRaises(RuntimeError):
            await invoke(self.cog, "player_info", ctx)

    async def test_player_info_orders_locked(self):
        self.board.orders_enabled = False
        ctx = create_mock_context(message_content=".player_info France")
        with self.assertRaises(CommandPermissionError):
            await invoke(self.cog, "player_info", ctx)

    async def test_player_info_existing_player(self):
        ctx = create_mock_context(message_content=".player_info France")
        await invoke(self.cog, "player_info", ctx)

        self.mock_send.assert_called_once()
        self.assertEqual(self.get_sent_title(), "France")

    async def test_player_info_not_found(self):
        ctx = create_mock_context(message_content=".player_info Narnia")
        await invoke(self.cog, "player_info", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("Could not find player")

class TestAllProvinceData(CogTestCase):
    """Tests for the .all_province_data command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = CommandCog(self.bot)

    async def test_all_province_data_no_game(self):
        ctx = create_mock_context(guild_id=99999, message_content=".all_province_data")
        with self.assertRaises(RuntimeError):
            await invoke(self.cog, "all_province_data", ctx)

    async def test_all_province_data_orders_locked(self):
        self.board.orders_enabled = False
        ctx = create_mock_context(message_content=".all_province_data")
        with self.assertRaises(CommandPermissionError):
            await invoke(self.cog, "all_province_data", ctx)

    async def test_all_province_data(self):
        ctx = create_mock_context(message_content=".all_province_data")
        await invoke(self.cog, "all_province_data", ctx)

        self.mock_send.assert_called_once()
        msg = self.get_sent_message()
        self.assertIn("Paris", msg)

# TODO: Tests for nick

class TestGetDeadline(CogTestCase):
    """Tests for the .deadline / .get_deadline command."""

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = CommandCog(self.bot)

    async def test_no_deadline_set(self):
        ctx = create_mock_context(message_content=".deadline")
        await invoke(self.cog, "get_deadline", ctx)

        self.mock_send.assert_called_once()
        self.assert_message_contains("No deadline set")

    async def test_deadline_format(self):
        self.board.data["deadline"] = 9999999999
        ctx = create_mock_context(message_content=".get_deadline")
        await invoke(self.cog, "get_deadline", ctx)

        msg = self.get_sent_message()
        self.assertIn("<t:9999999999:f>", msg)
