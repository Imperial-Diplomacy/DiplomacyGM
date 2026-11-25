"""Game management commands related to deadlines and pinging players."""

import logging
import re

import discord
from discord.ext import commands

from DiploGM.services import deadline_management
from DiploGM.utils import send_message_and_file

from DiploGM.manager import Manager
from DiploGM.utils.request import Request
from DiploGM.utils.sanitise import remove_prefix
from DiploGM.utils.send_message import ErrorMessage, send_error

logger = logging.getLogger(__name__)
manager = Manager()

async def set_deadline(ctx: commands.Context) -> None:
    """Manages the deadline for the current phase."""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    content = remove_prefix(ctx)

    if content.startswith("adjust"):
        content = content.removeprefix("adjust").strip()
        success, response = await deadline_management.adjust_deadline(request, content)
    elif content.startswith("cancel"):
        success, response = deadline_management.cancel_deadline(request)
    else:
        success, response = await deadline_management.set_deadline(request, content)

    if success:
        await send_message_and_file(channel=ctx.channel, message=response)
    else:
        logger.warning(response)
        await send_error(ctx.channel, response)

async def set_phase_length(ctx: commands.Context, move_str: str, retreat_str: str, build_str: str) -> None:
    """Sets the default phase length for movement, retreat, and adjustment phases."""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    success, response = await deadline_management.set_phase_length(request, (move_str, retreat_str, build_str))
    if success:
        await send_message_and_file(channel=ctx.channel, message=response)
    else:
        logger.warning(response)
        await send_error(ctx.channel, response)

async def ping_players(ctx: commands.Context) -> None:
    """Pings all players with withstanding orders"""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    content = remove_prefix(ctx)

    timestamp = None
    if parsed_timestamp := re.match(r"^<t:(\d{10}):[a-zA-Z]>$", content.split(' ')[0]):
        if len(content.split(' ')) > 1:
            content = ' '.join(content.split(' ')[1:])
        else:
            content = ''
        timestamp = parsed_timestamp.group(1)

    success, response = await deadline_management.ping_players(request, timestamp=timestamp, message=content)
    if success:
        await send_message_and_file(channel=ctx.channel, message=response)
    else:
        logger.warning(response)
        await send_error(ctx.channel, response)

async def post_deadline(ctx: commands.Context) -> None:
    """Posts the current deadline to the deadlines channel."""
    assert ctx.guild is not None and isinstance(ctx.channel, discord.TextChannel)
    request = Request(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    success, response = await deadline_management.post_deadline(request)
    if not success:
        if not response:
            await send_error(ctx.channel, ErrorMessage.UNKNOWN_ERROR)
        else:
            logger.warning(response)
            await send_error(ctx.channel, response)
