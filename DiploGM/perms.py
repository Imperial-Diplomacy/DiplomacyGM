from functools import wraps
from typing import Any, Awaitable, Callable, Union

import discord
from discord import User, Member
from discord.ext import commands

from DiploGM import config
from DiploGM.errors import CommandPermissionError
from DiploGM.config import IMPDIP_SERVER_ID, SUPERUSERS, IMPDIP_MOD_ROLES, GM_PERMISSION_ROLE_NAMES, GM_CATEGORY_NAMES, \
    GM_CHANNEL_NAMES, PLAYER_PERMISSION_ROLE_NAMES, PLAYER_ORDER_CATEGORY_NAMES, GAME_SERVER_MODERATOR_ROLE_NAMES, \
    BUMBLE_ID
from DiploGM.utils import (simple_player_name)
from DiploGM.manager import Manager
from DiploGM.models.player import Player

manager = Manager()


def get_player_by_context(ctx: commands.Context):
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


def is_player_channel(player_role: str, channel: commands.Context.channel) -> bool:
    player_channel = player_role + config.PLAYER_ORDER_CHANNEL_SUFFIX
    return simple_player_name(player_channel) == simple_player_name(
        channel.name
    ) and is_player_category(channel.category.name)



def require_player_by_context(ctx: commands.Context, description: str):
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

def is_player_role(role: str) -> bool:
    return role.lower() in PLAYER_PERMISSION_ROLE_NAMES


def is_player_category(category: str) -> bool:
    return category.lower() in PLAYER_ORDER_CATEGORY_NAMES

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

    for role in ctx.author.roles:
        if role in IMPDIP_MOD_ROLES:
            break
    else:
        raise CommandPermissionError(
            f"You cannot {description} as you are not a moderator on the Imperial Diplomacy Hub server."
        )

    for role in ctx.author.roles:
        if role in GAME_SERVER_MODERATOR_ROLE_NAMES:
            break
    else:
        raise CommandPermissionError(
            f"You cannot {description} as you are not a moderator on the current server."
        )

    return True


def mod_only(description: str = "run this command"):
    return commands.check(lambda ctx: assert_mod_only(ctx, description))

# GM

def is_gm(user: Union[User, Member]) -> bool:
    for role in user.roles:
        if role.lower() in GM_PERMISSION_ROLE_NAMES:
            return True
    return False

def is_gm_channel(channel: commands.Context.channel) -> bool:
    return (channel.name.lower() in GM_CHANNEL_NAMES
            and channel.category.lower() in GM_CATEGORY_NAMES)

def assert_gm_only(
    ctx: commands.Context, description: str = "run this command", non_gm_alt: str = ""
):
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

def is_superuser(user: Union[User, Member]) -> bool:
    return user.id in SUPERUSERS


temporary_bumbles: set[int] = set()
def is_bumble(user: Union[User, Member]) -> bool:
    return user.id == BUMBLE_ID or user.id in temporary_bumbles
