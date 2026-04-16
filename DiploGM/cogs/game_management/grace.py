"""Game management commands related to grace."""
import logging
from typing import Optional
import discord
from discord.ext import commands
from DiploGM.config import ERROR_COLOUR
from DiploGM.utils import send_message_and_file
from DiploGM.models.extension import ExtensionEvent, SQLiteExtensionEventRepository
from DiploGM.manager import Manager

grace_repo = SQLiteExtensionEventRepository()
logger = logging.getLogger(__name__)
manager = Manager()

async def grace_log(ctx: commands.Context, user: discord.User, hours: float, reason: str = "Unspecified") -> None:
    """Store a record of grace in a game"""
    assert ctx.guild is not None

    if user.bot:
        await send_message_and_file(channel=ctx.channel,
                                    message="Can't log grace for a bot",
                                    embed_colour=ERROR_COLOUR)
        return

    event = ExtensionEvent(
        user_id=user.id,
        server_id=ctx.guild.id,
        hours=hours,
        reason=reason
    )

    grace_repo.save(event)
    await send_message_and_file(channel=ctx.channel,
                                title=f"Grace (No. {event.id}) logged!",
                                message=f"Logged under: {user.mention}\nHours: {hours}")

async def grace_delete(ctx: commands.Context, grace_id: int) -> None:
    """Delete a record of grace from the database"""
    grace_repo.delete(grace_id)
    await send_message_and_file(channel=ctx.channel,
                                message=f"If a grace with ID {grace_id} existed, it exists no longer :fire:")

async def grace_view_user(ctx: commands.Context, user: discord.User) -> None:
    """View the grace record for a specific user

    Usage: 
        `.grace view user <user>`

    Note: 
        Groups by server graces are logged in
        Records sorted by server_id (newer servers?) then creation datetime

    Args:
        user (discord.User): User to check
    """
    events = grace_repo.load_by_user(user.id)

    handled_servers = set()
    out = ""
    for e in sorted(events, key=lambda e: (e.server_id, e.created_at), reverse=True):
        if e.server_id not in handled_servers:
            server = ctx.bot.get_guild(e.server_id)
            identifier = server.name if server else f"Guild {e.server_id}"
            out += f"### For: {identifier}\n"
            handled_servers.add(e.server_id)

        out += f"ID({e.id}):  {user.mention}\n"
        out += f"- Hours: {e.hours}\n"
        out += f"- Reason: {e.reason}\n"
        out += f"- Time: {e.created_at}\n"

    if len(events) == 0:
        out = "None logged, this is a good user!"

    await send_message_and_file(channel=ctx.channel, title=f"Graces caused by {user.name}", message=out)

async def grace_view_server(ctx: commands.Context, server_id: Optional[int] = None) -> None:
    """View the grace record for the current server"""
    assert ctx.guild is not None

    gname = ctx.guild.name
    guildid = ctx.guild.id
    if server_id is not None:
        try:
            guild = await ctx.bot.fetch_guild(server_id)
            gname = guild.name
            guildid = server_id
        except discord.HTTPException:
            gname = str(server_id)
            await send_message_and_file(channel=ctx.channel,
                                        message="Could not find that guild object",
                                        embed_colour=ERROR_COLOUR)

    events = grace_repo.load_by_server(guildid)
    out = ""
    if len(events) == 0:
        out = "This server is yet to have a grace! Congratulations!"
    else:
        for e in sorted(events, key=lambda e: e.created_at, reverse=True):
            user = ctx.bot.get_user(e.user_id)
            out += f"ID({e.id}):  {user.mention}\n"
            out += f"- Hours: {e.hours}\n"
            out += f"- Reason: {e.reason}\n"
            out += f"- Time: {e.created_at}\n"

    await send_message_and_file(channel=ctx.channel, title=f"Graces in {gname}", message=out)
