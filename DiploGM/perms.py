from functools import wraps
from typing import Any, Awaitable, Callable

import discord
from discord.ext import commands

from DiploGM import config
from DiploGM.errors import CommandPermissionError
from DiploGM.config import IMPDIP_SERVER_ID, SUPERUSERS
from DiploGM.utils import (simple_player_name)
from DiploGM.manager import Manager
from DiploGM.models.player import Player

manager = Manager()


def get_player_by_context(ctx: commands.Context):
    assert ctx.guild is not None
    # FIXME cleaner way of doing this
    board = manager.get_board(ctx.guild.id)
    # return if in order channel
    weak_channel_checking = "weak channel checking" in board.data.get("flags", [])
    if board.fow or weak_channel_checking:
        player = board.get_player_by_channel(
            ctx.channel, ignore_category=weak_channel_checking
        )
    else:
        if not isinstance(ctx.author, discord.Member):
            return None
        player = manager.get_member_player_object(ctx.message.author)

    return player


def is_player_channel(player_role: str, channel: discord.abc.Messageable) -> bool:
    if not isinstance(channel, discord.TextChannel):
        return False
    player_channel = player_role + config.player_channel_suffix
    return simple_player_name(player_channel) == simple_player_name(
        channel.name
    ) and config.is_player_category(channel.category)



def require_player_by_context(ctx: commands.Context, description: str):
    assert ctx.guild is not None and ctx.message is not None
    # FIXME cleaner way of doing this
    board = manager.get_board(ctx.guild.id)
    # return if in order channel
    weak_channel_checking = "weak channel checking" in board.data.get("flags", [])
    if board.fow or weak_channel_checking:
        player = board.get_player_by_channel(
            ctx.channel, ignore_category=weak_channel_checking
        )
        if player:
            return player
    else:
        player = manager.get_member_player_object(ctx.message.author)

    if player:
        if not is_player_channel(player.name, ctx.channel):
            raise CommandPermissionError(
                f"You cannot {description} as a player outside of your orders channel."
            )
    else:
        if not is_gm(ctx.message.author):
            raise CommandPermissionError(
                f"You cannot {description} because you are neither a GM nor a player."
            )
        player_channel = board.get_player_by_channel(ctx.channel)
        if player_channel is not None:
            player = player_channel
        elif not is_gm_channel(ctx.channel):
            raise CommandPermissionError(
                f"You cannot {description} as a GM in non-player and non-GM channels."
            )
    return player

# Player

# adds one extra argument, player in a player's channel, which is None if run by a GM in a GM channel
def player(description: str = "run this command"):
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
    _hub = ctx.bot.get_guild(IMPDIP_SERVER_ID)
    if not _hub:
        raise CommandPermissionError(
            "Cannot fetch the Imperial Diplomacy Hub server moderator permissions."
        )

    _member = _hub.get_member(ctx.author.id)
    if not _member:
        raise CommandPermissionError(
            f"You cannot {description} as you could not be found as a member of the Imperial Diplomacy Hub server."
        )

    if not is_moderator(_member):
        raise CommandPermissionError(
            f"You cannot {description} as you are not a moderator on the Imperial Diplomacy Hub server."
        )

    if not is_moderator(ctx.author):
        raise CommandPermissionError(
            f"You cannot {description} as you are not a moderator on the current server."
        )

    return True


def mod_only(description: str = "run this command"):
    return commands.check(lambda ctx: assert_mod_only(ctx, description))

def is_moderator(author: discord.Member | discord.User) -> bool:
    if not isinstance(author, discord.Member):
        return False
    for role in author.roles:
        if config.is_mod_role(role.name):
            return True

    return False

# GM

def assert_gm_only(
    ctx: commands.Context, description: str = "run this command", non_gm_alt: str = ""
):
    assert ctx.message is not None
    if not is_gm(ctx.message.author):
        raise CommandPermissionError(
            non_gm_alt or f"You cannot {description} because you are not a GM."
        )
    elif not is_gm_channel(ctx.channel):
        raise CommandPermissionError(f"You cannot {description} in a non-GM channel.")
    else:
        return True


def gm_only(description: str = "run this command"):
    return commands.check(lambda ctx: assert_gm_only(ctx, description))

def is_gm_channel(channel: discord.abc.Messageable) -> bool:
    return (isinstance(channel, discord.TextChannel)
            and config.is_gm_channel(channel.name)
            and config.is_gm_category(channel.category))

def is_gm(author: discord.Member | discord.User) -> bool:
    if not isinstance(author, discord.Member):
        return False
    for role in author.roles:
        if config.is_gm_role(role.name):
            return True
    return False

# Superuser

def assert_superuser_only(ctx: commands.Context, description: str = "run this command"):
    if not is_superuser(ctx.message.author):
        raise CommandPermissionError(
            f"You cannot {description} as you are not an superuser"
        )
    else:
        return True


def superuser_only(description: str = "run this command"):
    return commands.check(lambda ctx: assert_superuser_only(ctx, description))

def is_superuser(author: discord.Member | discord.User) -> bool:
    return author.id in SUPERUSERS
