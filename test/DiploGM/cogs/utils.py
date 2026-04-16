"""Mock factories and base test class for testing Discord bot cog commands."""
from __future__ import annotations

import unittest
from unittest import mock
from unittest.mock import AsyncMock, MagicMock
from test.utils import BoardBuilder

import discord
from discord.ext import commands

from DiploGM.config import COMMAND_PREFIX

def create_mock_role(name: str) -> MagicMock:
    """Create a mock Discord role with the given name."""
    role = MagicMock(spec=discord.Role)
    role.name = name
    return role

def create_mock_channel(name: str = "test-channel", category_name: str | None = None) -> MagicMock:
    """Create a mock Discord TextChannel with the given name and optional category name."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = name
    if category_name is not None:
        channel.category = MagicMock(spec=discord.CategoryChannel)
        channel.category.name = category_name
    else:
        channel.category = None
    return channel

def create_mock_member(
    roles: list[str] | None = None, username: str = "TestUser", user_id: int = 1
) -> MagicMock:
    """Create a mock Discord Member with the given role names."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.name = username
    member.nick = None
    member.roles = [create_mock_role(r) for r in (roles or [])]
    return member

def create_mock_context(
    guild_id: int = 0,
    guild_name: str = "TestGuild",
    channel: MagicMock | None = None,
    author: MagicMock | None = None,
    message_content: str = "",
) -> MagicMock:
    """Create a mock commands.Context with the minimum fields commands need.

    Attributes wired up:
    - ctx.guild.id, ctx.guild.name, ctx.guild.roles
    - ctx.channel (a mock TextChannel)
    - ctx.author (a mock Member)
    - ctx.message.content, ctx.message.author, ctx.message.created_at
    - ctx.prefix, ctx.invoked_with (for remove_prefix)
    """
    ctx = MagicMock(spec=commands.Context)

    # Guild
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    ctx.guild.name = guild_name
    ctx.guild.roles = []

    ctx.channel = create_mock_channel() if channel is None else channel
    ctx.author = create_mock_member() if author is None else author
    ctx.author.guild = ctx.guild

    # Message
    ctx.message = MagicMock(spec=discord.Message)
    ctx.message.content = message_content
    ctx.message.author = ctx.author
    ctx.message.created_at = None

    # For remove_prefix(ctx): content.removeprefix(f"{ctx.prefix}{ctx.invoked_with}")
    prefix_part = message_content.split()[0] if message_content.strip() else ""
    ctx.prefix = COMMAND_PREFIX if prefix_part.startswith(COMMAND_PREFIX) else ""
    ctx.invoked_with = prefix_part.lstrip(COMMAND_PREFIX) if prefix_part else ""

    ctx.send = AsyncMock()
    return ctx

def create_mock_gm_context(guild_id: int = 0, message_content: str = "") -> MagicMock:
    """Create a context for a GM in a GM channel (gm-bot-commands in 'gm channels' category)."""
    channel = create_mock_channel("gm-bot-commands", category_name="gm channels")
    author = create_mock_member(roles=["GM Team"], user_id=100)
    return create_mock_context(
        guild_id=guild_id,
        channel=channel,
        author=author,
        message_content=message_content,
    )

def create_mock_player_context(
    guild_id: int = 0, player_name: str = "france", message_content: str = ""
) -> MagicMock:
    """Create a context for a player in their orders channel."""
    channel = create_mock_channel(
        f"{player_name}-orders", category_name="orders"
    )
    author = create_mock_member(roles=[player_name], user_id=10)
    return create_mock_context(
        guild_id=guild_id,
        channel=channel,
        author=author,
        message_content=message_content,
    )


class CogTestCase(unittest.IsolatedAsyncioTestCase):
    """Base test class that sets up a game board and patches send_message_and_file."""

    # Subclasses should list all import sites of send_message_and_file to patch
    send_patch_targets: list[str] = []

    @staticmethod
    async def invoke(cog, command_name: str, ctx, *args):
        """Invoke a cog command's underlying callback directly, bypassing discord.py dispatch."""
        cmd = getattr(cog, command_name)
        await cmd.callback(cog, ctx, *args)

    def setUp(self):
        self.builder = BoardBuilder()
        self.board = self.builder.board
        self.players = self.builder.players

        # Patch send_message_and_file at all import sites
        self._patches = []
        self.mock_send = AsyncMock()

        for target in self.send_patch_targets:
            p = mock.patch(target, self.mock_send)
            p.start()
            self._patches.append(p)

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def get_sent_kwargs(self, call_index: int = -1) -> dict:
        """Return kwargs from a specific send_message_and_file call (default: last)."""
        calls = self.mock_send.call_args_list
        if not calls:
            raise AssertionError("send_message_and_file was never called")
        return calls[call_index].kwargs

    def get_sent_message(self, call_index: int = -1) -> str:
        """Return the 'message' kwarg from a send call."""
        kwargs = self.get_sent_kwargs(call_index)
        return kwargs.get("message", "")

    def get_sent_title(self, call_index: int = -1) -> str:
        """Return the 'title' kwarg from a send call."""
        kwargs = self.get_sent_kwargs(call_index)
        return kwargs.get("title", "")

    def assert_message_contains(self, text: str, call_index: int = -1):
        """Assert that the sent message, messages, or title contains the given text."""
        kwargs = self.get_sent_kwargs(call_index)
        message = kwargs.get("message", "") or ""
        title = kwargs.get("title", "") or ""
        messages = "\n".join(kwargs.get("messages", []) or [])
        combined = f"{title}\n{message}\n{messages}"
        if text not in combined:
            raise AssertionError(
                f"Expected '{text}' in sent output, got:\n"
                f"  title: {title!r}\n  message: {message!r}\n  messages: {messages!r}"
            )

    def assert_message_not_contains(self, text: str, call_index: int = -1):
        """Assert that the sent message, messages, and title do not contain the given text."""
        kwargs = self.get_sent_kwargs(call_index)
        message = kwargs.get("message", "") or ""
        title = kwargs.get("title", "") or ""
        messages = "\n".join(kwargs.get("messages", []) or [])
        combined = f"{title}\n{message}\n{messages}"
        if text in combined:
            raise AssertionError(
                f"Did not expect '{text}' in sent output, got:\n"
                f"  title: {title!r}\n  message: {message!r}\n  messages: {messages!r}"
            )

    def assert_file_sent(self, call_index: int = -1):
        """Assert that a file was included in the send call."""
        kwargs = self.get_sent_kwargs(call_index)
        if not kwargs.get("file"):
            raise AssertionError(
                f"Expected file in send call, got kwargs: {list(kwargs.keys())}"
            )

    def get_ctx_send_text(self, ctx: MagicMock, call_index: int = -1) -> str:
        """Return the text from a ctx.send() call."""
        calls = ctx.send.call_args_list
        if not calls:
            raise AssertionError("ctx.send() was never called")
        args, kwargs = calls[call_index]
        return args[0] if args else kwargs.get("content", "")

    def assert_ctx_send_contains(self, ctx: MagicMock, text: str, call_index: int = -1):
        """Assert that ctx.send() was called with text containing the given string."""
        calls = ctx.send.call_args_list
        if not calls:
            raise AssertionError(
                f"ctx.send() was never called, expected text containing '{text}'"
            )
        args, kwargs = calls[call_index]
        content = args[0] if args else kwargs.get("content", "")
        if text not in content:
            raise AssertionError(
                f"Expected '{text}' in ctx.send() output, got: {content!r}"
            )

    def get_all_output(self, ctx: MagicMock, mock_send: AsyncMock | None = None) -> str:
        """Combine all text from both ctx.send() and send_message_and_file() calls."""
        if mock_send is None:
            mock_send = self.mock_send
        parts = []
        for args, kwargs in ctx.send.call_args_list:
            parts.append(args[0] if args else kwargs.get("content", ""))
        for call in mock_send.call_args_list:
            title = call.kwargs.get("title", "") or ""
            message = call.kwargs.get("message", "") or ""
            parts.append(f"{title}\n{message}")
        return "\n".join(parts)
