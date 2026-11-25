"""Game management commands related to adjudication."""

import logging

import discord
from discord.ext import commands

from DiploGM.utils import (
    log_command,
    send_message_and_file,
)
from DiploGM.manager import Manager
from DiploGM.utils.request import Request
from DiploGM.services import adjudication
from DiploGM.utils.sanitise import get_map_options, remove_prefix
from DiploGM.utils.send_message import ErrorMessage, send_error

logger = logging.getLogger(__name__)
manager = Manager()


async def lock_orders(ctx: commands.Context) -> None:
    """Sets board flag to prevent new order submissions"""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    adjudication.lock_orders(request, lock=True)
    log_command(logger, ctx, message="Locked orders")
    await send_message_and_file(
        channel=ctx.channel,
        title="Locked orders"
    )


async def unlock_orders(ctx: commands.Context) -> None:
    """Sets board flag to enable new order submissions"""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    adjudication.lock_orders(request, lock=False)
    log_command(logger, ctx, message="Unlocked orders")
    await send_message_and_file(
        channel=ctx.channel,
        title="Unlocked orders"
    )


async def publish_orders(ctx: commands.Context, *args) -> None:
    """Publishes orders to the orders log channel, uploads the map to the archive,
    and informs players about the phase change."""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    success, response = await adjudication.publish_orders(request, *args)
    if success:
        log_command(logger, ctx, message="Published orders")
    else:
        if response is not None:
            logger.error(response)
            await send_error(ctx.channel, response)
        else:
            await send_error(ctx.channel, ErrorMessage.UNKNOWN_ERROR)

async def adjudicate(ctx: commands.Context) -> None:
    """Adjudicates the game, and publishes the orders and results maps."""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    board = manager.get_board(ctx.guild.id)
    arguments = remove_prefix(ctx).lower().split()
    args = {
        "return_svg": not ({"true", "t", "svg", "s"} & set(arguments)),
        "map_modes": get_map_options(board, arguments, None),
        "test": "test" in arguments,
        "full": "full" in arguments and "test" not in arguments,
        "movement": "movement" in arguments,
        "force": ({"force", "confirm"} & set(arguments)) and "test" not in arguments,
    }
    success, response = await adjudication.adjudicate(request, ctx.bot.scheduler, args)
    if success:
        log_command(logger, ctx, message="Adjudicated")
    else:
        if response is not None:
            logger.error(response)
            await send_error(ctx.channel, response)
        else:
            await send_error(ctx.channel, ErrorMessage.UNKNOWN_ERROR)
