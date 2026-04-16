"""Tests for PlayerCog commands."""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

from discord.ext import commands

from DiploGM.models.turn import Turn, PhaseName
from DiploGM.models.unit import UnitType
from test.DiploGM.cogs.utils import (
    CogTestCase,
    create_mock_context,
    create_mock_channel,
    create_mock_gm_context,
    create_mock_member,
    create_mock_player_context,
)
from DiploGM.cogs.player import PlayerCog
from DiploGM.errors import CommandPermissionError


class PlayerCogTestCase(CogTestCase):
    """Base class for PlayerCog tests — patches send and DB."""

    send_patch_targets = [
        "DiploGM.cogs.player.send_message_and_file",
        "DiploGM.utils.send_message.send_message_and_file",
    ]

    def setUp(self):
        super().setUp()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = PlayerCog(self.bot)

        # Mock DB so save_order_for_units / save_build_orders_for_players don't need real SQLite
        self.mock_db = MagicMock()
        self.db_patcher = mock.patch(
            "DiploGM.cogs.player.get_connection", return_value=self.mock_db
        )
        self.db_patcher.start()

    def tearDown(self):
        self.db_patcher.stop()
        super().tearDown()

class TestOrder(PlayerCogTestCase):
    """Tests for the .order command."""

    def setUp(self):
        super().setUp()
        # Place a French army in Paris for order tests
        self.builder.army("Par", self.players["France"])

    async def test_order_locked_as_player(self):
        self.board.orders_enabled = False
        ctx = create_mock_player_context(message_content=".order Paris hold")
        await self.invoke(self.cog, "order", ctx, None)
        self.mock_send.assert_called()
        self.assert_message_contains("Orders locked")

    async def test_order_success(self):
        ctx = create_mock_player_context(message_content=".order Paris hold")
        await self.invoke(self.cog, "order", ctx, None)
        self.mock_send.assert_called()
        self.assert_message_contains("Orders validated successfully")

    async def test_order_invalid_order(self):
        ctx = create_mock_player_context(message_content=".order Paris - The Moon")
        await self.invoke(self.cog, "order", ctx, None)
        self.mock_send.assert_called()
        self.assert_message_contains("Unable to validate the following orders")
        self.assert_message_contains("does not match any known provinces")

    async def test_order_no_text(self):
        ctx = create_mock_player_context(message_content=".order")
        await self.invoke(self.cog, "order", ctx, None)
        self.mock_send.assert_called()
        self.assert_message_contains("For information about entering orders")

    async def test_gm_can_order_when_locked(self):
        self.board.orders_enabled = False
        ctx = create_mock_gm_context(message_content=".order Paris hold")
        await self.invoke(self.cog, "order", ctx, None)

        self.mock_send.assert_called()
        self.assert_message_contains("Orders validated successfully")

    async def test_order_from_gm_in_player_channel(self):
        channel = create_mock_channel("france-orders", category_name="orders")
        author = create_mock_member(roles=["GM Team"])
        ctx = create_mock_context(
            channel=channel,
            author=author,
            message_content=".order Paris hold",
        )
        await self.invoke(self.cog, "order", ctx, None)

        self.mock_send.assert_called()
        self.assert_message_contains("Orders validated successfully")

    async def test_order_from_arbitrary_channel(self):
        author = create_mock_member(roles=["GM Team"])
        ctx = create_mock_context(author=author, message_content=".order Paris hold")
        with self.assertRaises(CommandPermissionError):
            await self.invoke(self.cog, "order", ctx, None)

class TestRemoveOrder(PlayerCogTestCase):
    """Tests for the .remove_order command."""

    def setUp(self):
        super().setUp()
        self.builder.army("Par", self.players["France"])
        # Give Paris a hold order to remove
        from DiploGM.parse_order import parse_order
        parse_order(".order\nParis hold", self.players["France"], self.board)

    async def test_remove_order_locked(self):
        self.board.orders_enabled = False
        ctx = create_mock_player_context(message_content=".remove_order Paris")
        await self.invoke(self.cog, "remove_order", ctx, None)

        self.mock_send.assert_called()
        self.assert_message_contains("Orders locked")

    async def test_remove_order_success(self):
        ctx = create_mock_player_context(message_content=".remove_order Paris")
        await self.invoke(self.cog, "remove_order", ctx, None)

        self.mock_send.assert_called()
        self.assert_message_contains("Orders removed successfully")

    async def test_remove_order_invalid_province(self):
        ctx = create_mock_player_context(player_name="germany", message_content=".remove_order Paris")
        await self.invoke(self.cog, "remove_order", ctx, None)

        self.mock_send.assert_called()
        self.assert_message_contains("invalid")
        kwargs = self.get_sent_kwargs()
        self.assertIn("embed_colour", kwargs)

class TestRemoveAll(PlayerCogTestCase):
    """Tests for the .remove_all command."""

    def setUp(self):
        super().setUp()
        self.a_paris = self.builder.hold(self.players["France"], UnitType.ARMY, "Paris")
        self.a_london = self.builder.hold(self.players["England"], UnitType.ARMY, "London")

    async def test_remove_all_as_player(self):
        """Player removes only their own orders."""
        ctx = create_mock_player_context(message_content=".remove_all")
        await self.invoke(self.cog, "remove_all", ctx, None)

        self.mock_send.assert_called()
        self.assert_message_contains("Removed all Orders")
        self.assertIsNone(self.a_paris.order)
        self.assertIsNotNone(self.a_london.order)

    async def test_remove_all_as_gm(self):
        """GM in GM channel removes all orders globally."""
        ctx = create_mock_gm_context(message_content=".remove_all")
        await self.invoke(self.cog, "remove_all", ctx, None)

        self.mock_send.assert_called()
        self.assert_message_contains("Removed all Orders")
        self.assertIsNone(self.a_paris.order)
        self.assertIsNone(self.a_london.order)

class TestViewOrdersMoves(PlayerCogTestCase):
    """Tests for .view_orders during a move phase."""

    def setUp(self):
        super().setUp()
        # France: A Paris (hold order), A Marseilles (no order)
        self.builder.hold(self.players["France"], UnitType.ARMY, "Paris")
        self.builder.army("Mar", self.players["France"])

    async def test_view_full(self):
        """Full view shows both units."""
        ctx = create_mock_player_context(message_content=".view_orders")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_contains("Paris")
        self.assert_message_contains("Marseilles")
        self.assert_message_contains("1/2")

    async def test_view_submitted(self):
        """Submitted filter shows only Paris (has order)."""
        ctx = create_mock_player_context(message_content=".view_orders submitted")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_contains("Paris")
        self.assert_message_contains("Submitted Orders")
        self.assert_message_not_contains("Marseilles")

    async def test_view_missing(self):
        """Missing filter shows only Marseilles (no order)."""
        ctx = create_mock_player_context(message_content=".view_orders missing")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_contains("Marseilles")
        self.assert_message_contains("Missing Orders")
        self.assert_message_not_contains("Paris")

    async def test_view_blind(self):
        """Blind filter shows number of orders but no units."""
        ctx = create_mock_player_context(message_content=".view_orders blind")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_contains("1/2")
        self.assert_message_not_contains("Paris")
        self.assert_message_not_contains("Marseilles")

    async def test_view_as_other_player(self):
        """Germany viewing orders sees nothing about France's units."""
        ctx = create_mock_player_context(player_name="germany", message_content=".view_orders")
        await self.invoke(self.cog, "view_orders", ctx, self.players["Germany"])
        self.mock_send.assert_called()
        self.assert_message_not_contains("Paris")
        self.assert_message_not_contains("Marseilles")

class TestViewOrdersRetreats(PlayerCogTestCase):
    """Tests for .view_orders during a retreat phase."""

    def setUp(self):
        super().setUp()
        self.board.turn = Turn(1901, PhaseName.SPRING_RETREATS)
        self.a_paris = self.board.create_unit(UnitType.ARMY,
                                              self.players["France"],
                                              self.board.get_province("Paris"),
                                              None,
                                              set())

    async def test_view_missing_free_no_retreats(self):
        """No retreat options and 'free' flag."""
        ctx = create_mock_player_context(message_content=".view_orders missing free")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_not_contains("Paris")

    async def test_view_missing_forced_no_retreats(self):
        """No retreat options and 'forced' flag."""
        ctx = create_mock_player_context(message_content=".view_orders missing forced")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_contains("Paris")
        self.assert_message_contains(r"\*")

    async def test_view_missing_with_retreat_option(self):
        """Has a retreat option."""
        self.a_paris.retreat_options = {(self.board.get_province("Burgundy"), None)}
        ctx = create_mock_player_context(message_content=".view_orders missing")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])

        self.mock_send.assert_called()
        self.assert_message_contains("Paris")

class TestViewOrdersBuilds(PlayerCogTestCase):
    """Tests for .view_orders during a build phase."""

    def setUp(self):
        super().setUp()
        self.board.turn = Turn(1901, PhaseName.WINTER_BUILDS)

    async def test_view_with_build_orders(self):
        """France orders builds → .view shows them."""
        self.builder.build(
            self.players["France"],
            (UnitType.FLEET, "Brest"),
            (UnitType.ARMY, "Paris"),
            (UnitType.ARMY, "Marseilles"),
        )
        ctx = create_mock_player_context(message_content=".view_orders")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_contains("Brest")
        self.assert_message_contains("Paris")
        self.assert_message_contains("Marseilles")

    async def test_view_missing_all_ordered(self):
        """.view missing returns nothing when all builds are submitted."""
        self.builder.build(
            self.players["France"],
            (UnitType.FLEET, "Brest"),
            (UnitType.ARMY, "Paris"),
            (UnitType.ARMY, "Marseilles"),
        )
        ctx = create_mock_player_context(message_content=".view_orders missing")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_not_contains("France")

    async def test_view_submitted_no_orders(self):
        """.view submitted returns nothing when no builds are submitted."""
        ctx = create_mock_player_context(message_content=".view_orders submitted")
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_not_contains("France")

class TestViewOrdersPermissions(PlayerCogTestCase):
    """Tests for .view_orders permission handling."""

    def setUp(self):
        super().setUp()
        self.builder.hold(self.players["France"], UnitType.ARMY, "Paris")

    async def test_gm_in_player_channel(self):
        """GM in France's channel sees only France's orders."""
        channel = create_mock_channel("france-orders", category_name="orders")
        author = create_mock_member(roles=["GM Team"])
        ctx = create_mock_context(
            channel=channel,
            author=author,
            message_content=".view_orders",
        )
        await self.invoke(self.cog, "view_orders", ctx, self.players["France"])
        self.mock_send.assert_called()
        self.assert_message_contains("Paris")

    async def test_arbitrary_channel_errors(self):
        """Calling .view_orders from an arbitrary channel raises permission error."""
        author = create_mock_member(roles=["GM Team"])
        ctx = create_mock_context(author=author, message_content=".view_orders")
        with self.assertRaises(CommandPermissionError):
            await self.invoke(self.cog, "view_orders", ctx, None)


class TestViewMap(PlayerCogTestCase):
    """Tests for the .view_map and .view_current commands."""

    def setUp(self):
        super().setUp()
        self.draw_map_patcher = mock.patch(
            "DiploGM.cogs.player.manager.draw_map",
            return_value=(b"<svg>fake</svg>", "map.svg"),
        )
        self.mock_draw_map = self.draw_map_patcher.start()

    def tearDown(self):
        self.draw_map_patcher.stop()
        super().tearDown()

    async def test_vm_returns_file(self):
        """Basic .vm returns a file with convert_svg=True for a player."""
        ctx = create_mock_player_context(message_content=".vm")
        await self.invoke(self.cog, "view_map", ctx, self.players["France"])

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertEqual(kwargs["file"], b"<svg>fake</svg>")
        self.assertEqual(kwargs["file_name"], "map.svg")
        self.assertTrue(kwargs["convert_svg"])

    async def test_vc_returns_file(self):
        """Basic .vc returns a file with convert_svg=True for a player.
        No need to do separate tests for .vm and .vc since they call the same underlying function."""
        ctx = create_mock_player_context(message_content=".vc")
        await self.invoke(self.cog, "view_current", ctx, self.players["France"])

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertEqual(kwargs["file"], b"<svg>fake</svg>")
        self.assertEqual(kwargs["file_name"], "map.svg")
        self.assertTrue(kwargs["convert_svg"])

    async def test_vm_svg_as_gm(self):
        """.vm svg as GM in GM channel returns SVG (convert_svg=False)."""
        ctx = create_mock_gm_context(message_content=".vm svg")
        await self.invoke(self.cog, "view_map", ctx, None)

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertFalse(kwargs["convert_svg"])

    async def test_vm_true_as_gm(self):
        """.vm true as GM returns SVG."""
        ctx = create_mock_gm_context(message_content=".vm true")
        await self.invoke(self.cog, "view_map", ctx, None)

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertFalse(kwargs["convert_svg"])

    async def test_vm_svg_as_player_still_converts(self):
        """Player passing 'svg' still gets convert_svg=True (only GM gets raw SVG)."""
        ctx = create_mock_player_context(message_content=".vm svg")
        await self.invoke(self.cog, "view_map", ctx, self.players["France"])

        self.mock_send.assert_called()
        kwargs = self.get_sent_kwargs()
        self.assertTrue(kwargs["convert_svg"])
