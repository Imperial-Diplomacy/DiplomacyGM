from __future__ import annotations
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING, Sequence

import discord
from discord.ext import commands

from DiploGM import config
from DiploGM.errors import CommandPermissionError
from DiploGM.config import HUB_SERVER_ID, SUPERUSERS, is_player_category
from DiploGM.utils import (simple_player_name)
from DiploGM.manager import Manager
from DiploGM.models.player import Player

if TYPE_CHECKING:
    from discord.abc import Messageable
    from DiploGM.models.board import Board

manager = Manager()


def get_player_by_context(ctx: commands.Context) -> Player | None:
    """Gets the player associated with the command context, if it exists."""
    assert ctx.guild is not None
    # FIXME cleaner way of doing this
    board = manager.get_board(ctx.guild.id)
    # return if in order channel
    weak_channel_checking = "weak channel checking" in board.data.get("flags", [])
    if board.data.get("fow", "disabled") == "enabled" or weak_channel_checking:
        return get_player_by_channel(
            board, ctx.channel, ignore_category=weak_channel_checking
        )
    if not isinstance(ctx.author, discord.Member):
        return None
    return manager.get_member_player_object(ctx.message.author)

def get_player_by_channel(
        board: Board,
        channel: Messageable,
        ignore_category=False,
) -> Player | None:
    """Given a Discord channel, tries to find a matching Player."""
    # thread -> main channel
    if isinstance(channel, discord.Thread):
        assert isinstance(channel.parent, discord.TextChannel)
        channel = channel.parent
    assert isinstance(channel, discord.TextChannel)

    name = channel.name
    if (not ignore_category) and not is_player_category(channel.category):
        return None

    if board.is_chaos() and name.endswith("-void"):
        name = name[:-5]
    else:
        if not name.endswith(config.PLAYER_CHANNEL_SUFFIX):
            return None

        name = name[: -(len(config.PLAYER_CHANNEL_SUFFIX))]

    try:
        return board.get_player(name)
    except ValueError:
        return None

def is_player_channel(player_role: Player, channel: Messageable) -> bool:
    """Checks to see if the given channel is the player's orders channel."""
    if not isinstance(channel, discord.TextChannel) or channel.category is None:
        return False
    player_channel = player_role.name + config.PLAYER_CHANNEL_SUFFIX
    nickname_channel = player_role.get_name() + config.PLAYER_CHANNEL_SUFFIX
    return ((simple_player_name(player_channel) == simple_player_name(channel.name)
             or simple_player_name(nickname_channel) == simple_player_name(channel.name))
            and config.is_player_category(channel.category))

def require_player_by_context(ctx: commands.Context, description: str) -> Player | None:
    """Gets the player associated with the command context, if it exists,
    but requires that the command is run by a player in their orders channel
    or by a GM in a GM channel or a player's orders channel."""
    assert ctx.guild is not None and ctx.message is not None
    # FIXME cleaner way of doing this
    board = manager.get_board(ctx.guild.id)
    # return if in order channel
    weak_channel_checking = "weak channel checking" in board.data.get("flags", [])
    if board.data.get("fow", "disabled") == "enabled" or weak_channel_checking:
        player = get_player_by_channel(
            board, ctx.channel, ignore_category=weak_channel_checking
        )
        if player:
            return player
    else:
        player = manager.get_member_player_object(ctx.message.author)

    if player:
        if not is_player_channel(player, ctx.channel):
            raise CommandPermissionError(
                f"You cannot {description} as a player outside of your orders channel."
            )
    else:
        if not is_gm(ctx.message.author):
            raise CommandPermissionError(
                f"You cannot {description} because you are neither a GM nor a player."
            )
        player_channel = get_player_by_channel(board, ctx.channel)
        if player_channel is not None:
            player = player_channel
        elif not is_gm_channel(ctx.channel):
            raise CommandPermissionError(
                f"You cannot {description} as a GM in non-player and non-GM channels."
            )
    return player

def find_discord_role(user: Player,
                      roles: Sequence[discord.Role],
                      get_order_role: bool = False) -> Optional[discord.Role]:
    """Gets the Discord role associated with this player, if it exists."""
    suffix = config.PLAYER_CHANNEL_SUFFIX if get_order_role else ""
    for role in roles:
        if simple_player_name(role.name) == simple_player_name(user.get_name()) + suffix:
            return role
    for role in roles:
        if simple_player_name(role.name) == simple_player_name(user.name) + suffix:
            return role
    return None

# Player

def player(description: str = "run this command"):
    """Adds one extra argument, player in a player's channel, which is None if run by a GM in a GM channel"""
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(self, ctx: commands.Context, player: Player | None):
            # manager should live on bot or cog; here I assume cog
            player = require_player_by_context(ctx, description)

            # Inject the resolved player into the *real* function call
            return await func(self, ctx, player)

        return wrapper

    return decorator

# Moderator

async def assert_mod_only(
    ctx: commands.Context, description: str = "run this command"
) -> bool:
    """Checks that the command invoker is a moderator on the Hub server and the current server.
    Raises a CommandPermissionError if not, otherwise returns True."""
    _hub = ctx.bot.get_guild(HUB_SERVER_ID)
    if not _hub:
        raise CommandPermissionError(
            "Cannot fetch the Hub server moderator permissions."
        )

    _member = _hub.get_member(ctx.author.id)
    if not _member:
        raise CommandPermissionError(
            f"You cannot {description} as you could not be found as a member of the Hub server."
        )

    if not is_moderator(_member):
        raise CommandPermissionError(
            f"You cannot {description} as you are not a moderator on the Hub server."
        )

    if not is_moderator(ctx.author):
        raise CommandPermissionError(
            f"You cannot {description} as you are not a moderator on the current server."
        )

    return True


def mod_only(description: str = "run this command"):
    """Checks that the command invoker is a moderator on the Hub server and the current server.
    Raises a CommandPermissionError if not, otherwise returns True."""
    return commands.check(lambda ctx: assert_mod_only(ctx, description))

def is_moderator(author: discord.Member | discord.User) -> bool:
    """Checks if the given author is a moderator on the current server."""
    if not isinstance(author, discord.Member):
        return False
    for role in author.roles:
        if config.is_mod_role(role):
            return True

    return False

# GM

def assert_gm_only(
    ctx: commands.Context, description: str = "run this command", non_gm_alt: str = ""
):
    """Checks that the command invoker is a GM and the command is run in a GM channel.
    Raises a CommandPermissionError if not, otherwise returns True."""
    assert ctx.message is not None
    if not is_gm(ctx.message.author):
        raise CommandPermissionError(
            non_gm_alt or f"You cannot {description} because you are not a GM."
        )
    if not is_gm_channel(ctx.channel):
        raise CommandPermissionError(f"You cannot {description} in a non-GM channel.")
    return True


def gm_only(description: str = "run this command"):
    """Checks that the command invoker is a GM and the command is run in a GM channel.
    Raises a CommandPermissionError if not, otherwise returns True."""
    return commands.check(lambda ctx: assert_gm_only(ctx, description))

def is_gm_channel(channel: Messageable) -> bool:
    """Checks if the given channel is a GM channel in the GM category."""
    return (isinstance(channel, discord.TextChannel)
            and config.is_gm_channel(channel)
            and config.is_gm_category(channel.category))

def is_gm(author: discord.Member | discord.User) -> bool:
    """Checks if the given author is a GM on the current server."""
    if isinstance(author, discord.User):
        return False
    for role in author.roles:
        if config.is_gm_role(role):
            return True
    return False

# Superuser

def assert_superuser_only(ctx: commands.Context, description: str = "run this command"):
    """Checks that the command invoker is a superuser.
    Raises a CommandPermissionError if not, otherwise returns True."""
    if not is_superuser(ctx.message.author):
        raise CommandPermissionError(
            f"You cannot {description} as you are not a superuser"
        )
    return True


def superuser_only(description: str = "run this command"):
    """Checks that the command invoker is a superuser.
    Raises a CommandPermissionError if not, otherwise returns True."""
    return commands.check(lambda ctx: assert_superuser_only(ctx, description))

def is_superuser(author: discord.Member | discord.User) -> bool:
    """Checks if the given author is a superuser."""
    return author.id in SUPERUSERS
