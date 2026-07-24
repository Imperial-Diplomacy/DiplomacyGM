"""Module within the Game Management cog to handle game creation and exporting/importing game state."""

import json
import logging
import os
import re
import discord
from discord.ext import commands

from DiploGM import config
from DiploGM.db.database import get_connection
from DiploGM import perms
from DiploGM.utils import (
    import_game as import_game_module,
    log_command,
    send_message_and_file,
)
from DiploGM.manager import Manager
from DiploGM.utils.sanitise import remove_prefix
from DiploGM.utils.send_message import send_error, ErrorMessage

logger = logging.getLogger(__name__)
manager = Manager()


async def create_game(ctx: commands.Context, *args) -> None:
    """Create a new game for the server."""
    assert ctx.guild is not None
    args = [arg.lower() for arg in args]
    if len(args) == 0 or args[0] in {"fow", "chaos"}:
        gametype = "classic"
    else:
        gametype = args[0]
    fow = "fow" in args
    chaos = "chaos" in args

    success, message = manager.create_game(ctx.guild.id, gametype, fow=fow, chaos=chaos)

    welcome_message = (
        "Welcome to the game!\n"
        + "To submit orders, use the .order command, entering one order per line.\n"
        + "To view a map including all submitted orders, use the .view_map command.\n"
        + "To see all your units and which orders you have submitted, use the .view_orders command.\n"
        + "To create a private press channel, use .create_press_channel.\n"
        + "For a list of all commands, use the .help command.\n"
        + "Good luck!"
    )
    if success:
        board = manager.get_board(ctx.guild.id)
        for c in [
            cat for cat in ctx.guild.categories if config.is_player_category(cat)
        ]:
            for ch in c.text_channels:
                player = perms.get_player_by_channel(board, ch)
                if not player:
                    continue
                await send_message_and_file(
                    channel=ch,
                    title="Welcome!",
                    message=welcome_message,
                )
    log_command(logger, ctx, message=message)
    await send_message_and_file(channel=ctx.channel, message=message)

async def assign_powers(ctx: commands.Context) -> None:
    """Assigns power roles to players."""
    assert ctx.guild is not None
    guild = ctx.guild

    assigned: list[str] = []
    warnings: list[str] = []
    player_role = discord.utils.get(guild.roles, name="Player")
    if player_role is None:
        logger.error("Could not find the Player role.")
        await send_error(ctx.channel, ErrorMessage.NO_PLAYER_ROLE)
        return

    for line in remove_prefix(ctx).split("\n"):
        if not line.strip():
            continue

        ids = re.findall(r"(\d+)", line)
        if len(ids) < 2:
            warnings.append(f"Expected a user and a role: `{line.strip()}`")
            continue
        member = guild.get_member(int(ids[0]))
        role = guild.get_role(int(ids[1]))
        if member is None or role is None:
            warnings.append(f"Could not find a member or a role in: `{line.strip()}`")
            continue

        if role.name in config.RESTRICTED_ROLE_NAMES or "orders-" in role.name.lower():
            warnings.append(f"Cannot assign restricted role {role.mention}.")
            continue

        try:
            await member.add_roles(role, player_role)
            orders_role = discord.utils.get(guild.roles, name=f"orders-{role.name.lower()}")
            if orders_role:
                await member.add_roles(orders_role)
            else:
                warnings.append(f"Could not find orders role for {role.mention}.")
        except discord.DiscordException as e:
            warnings.append(f"Failed to assign {role.mention} to {member.mention}: {e}")
            continue

        assigned.append(f"Assigned {member.mention} to {role.mention}")

    message_parts: list[str] = []
    colour = config.EMBED_STANDARD_COLOUR
    if assigned:
        message_parts.append("**Assigned:**\n" + "\n".join(assigned))
    if warnings:
        message_parts.append("**Warnings:**\n" + "\n".join(warnings))
        colour = config.PARTIAL_ERROR_COLOUR if assigned else config.ERROR_COLOUR
    if not assigned and not warnings:
        message_parts.append("Please provide a list of users and power roles.")
        colour = config.ERROR_COLOUR

    log_command(logger, ctx, message=f"Assigned {len(assigned)} power role(s)")
    await send_message_and_file(
        channel=ctx.channel,
        title="Assign Powers",
        message="\n\n".join(message_parts),
        embed_colour=colour,
    )

async def assign_chaos_powers(ctx: commands.Context) -> None:
    """Assigns power roles to players in Chaos games, where players don't have roles."""
    assert ctx.guild is not None
    guild = ctx.guild

    assigned: list[str] = []
    warnings: list[str] = []
    player_role = discord.utils.get(guild.roles, name="Player")
    if player_role is None:
        logger.error("Could not find the Player role.")
        await send_error(ctx.channel, ErrorMessage.NO_PLAYER_ROLE)
        return

    for line in remove_prefix(ctx).split("\n"):
        if not line.strip():
            continue

        linedata = line.strip().split(maxsplit=1)
        if len(linedata) < 2:
            warnings.append(f"Expected a user and a role: `{line.strip()}`")
            continue
        memberid = re.search(r"<@!?(\d+)>", linedata[0])
        if memberid is None or (member := guild.get_member(int(memberid.group(1)))) is None:
            warnings.append(f"Could not find a member in: `{line.strip()}`")
            continue
        power = linedata[1].strip()
        power_channel = discord.utils.get(guild.text_channels, name=f"{power.lower()}-orders")
        if power_channel is None:
            warnings.append(f"Could not find a channel for power {power} in: `{line.strip()}`")
            continue
        try:
            await member.add_roles(player_role)
            await power_channel.set_permissions(member, read_messages=True, send_messages=True)
        except discord.DiscordException as e:
            warnings.append(f"Failed to give {member.mention} access to {power_channel.mention}: {e}")
            continue

        assigned.append(f"Assigned {member.mention} to {power_channel.mention}")

    message_parts: list[str] = []
    colour = config.EMBED_STANDARD_COLOUR
    if assigned:
        message_parts.append("**Assigned:**\n" + "\n".join(assigned))
    if warnings:
        message_parts.append("**Warnings:**\n" + "\n".join(warnings))
        colour = config.PARTIAL_ERROR_COLOUR if assigned else config.ERROR_COLOUR
    if not assigned and not warnings:
        message_parts.append("Please provide a list of users and power roles.")
        colour = config.ERROR_COLOUR

    log_command(logger, ctx, message=f"Assigned {len(assigned)} power role(s)")
    await send_message_and_file(
        channel=ctx.channel,
        title="Assign Powers",
        message="\n\n".join(message_parts),
        embed_colour=colour,
    )

async def export_game(ctx: commands.Context) -> None:
    """Exports the current game state (players, provinces, parameters) as a JSON file."""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)
    json_str = board.export_game()
    file_name = f"{board.datafile}_{str(board.turn).replace(' ', '_')}_export.json"
    log_command(logger, ctx, message="Exported game state")
    await send_message_and_file(
        channel=ctx.channel,
        title="Game Export",
        file=json_str.encode("utf-8"),
        file_name=file_name,
    )


async def import_game(ctx: commands.Context) -> None:
    """Imports a game from an uploaded JSON file."""
    assert ctx.guild is not None

    file = await ctx.message.attachments[0].read() if ctx.message.attachments else None
    if file is None:
        await send_message_and_file(
            channel=ctx.channel,
            message="No file attached. Please attach a JSON file to import a game.",
            embed_colour=config.ERROR_COLOUR,
        )
        return
    decoded_file = json.loads(file)
    gametype = decoded_file.get("datafile", "classic")

    success, message = manager.create_game(ctx.guild.id, gametype)
    if not success:
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)
        return
    board = manager.get_board(ctx.guild.id)
    get_connection().delete_board(board)
    message = import_game_module.import_game(board, decoded_file)
    get_connection().save_board(ctx.guild.id, board)
    log_command(logger, ctx, message=message)
    await send_message_and_file(channel=ctx.channel, message=message)


async def end_game(ctx: commands.Context, *args) -> None:
    """Marks a game as finished."""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)
    args = [arg.lower() for arg in args]
    if "false" in args:
        board.set_data("has_finished", "false")
        board.set_data("winners", "")
        message = "Marked game as not ended"
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)
        return

    board.set_data("has_finished", "true")
    power_roles = ctx.message.role_mentions
    winners = []
    for role in power_roles:
        try:
            power = board.get_player(role.name)
        except ValueError:
            logger.warning("Could not find power for %s", role.name)
            continue
        if power is not None:
            winners.append(power.get_name())
    message = "Marked game as finished."
    if len(winners) > 0:
        winner_text = "|".join(sorted(winners))
        board.set_data("winners", winner_text)
        message += f"\nRecorded {', '.join(sorted(winners))} as winners"
    log_command(logger, ctx, message=message)
    await send_message_and_file(channel=ctx.channel, message=message)


async def delete_game(ctx: commands.Context) -> None:
    """Completely deletes the game in the server. Cannot be undone."""
    assert ctx.guild is not None
    manager.total_delete(ctx.guild.id)
    log_command(logger, ctx, message="Deleted game")
    await send_message_and_file(channel=ctx.channel, title="Deleted game")


async def list_variants(ctx: commands.Context) -> None:
    """Lists all variants currently loaded into the bot."""
    assert ctx.guild is not None
    variants = os.listdir("variants")
    loaded_variants = []
    for v in variants:
        if not os.path.isdir(os.path.join("variants", v)):
            continue
        version_list = []
        variant_versions = os.listdir(os.path.join("variants", v))
        for vv in variant_versions:
            if os.path.isdir(os.path.join("variants", v, vv)) and os.path.isfile(
                os.path.join("variants", v, vv, "config.json")
            ):
                version_list.append(vv)
        version_list.sort()
        if len(version_list) > 0:
            loaded_variants.append(f"* {v}:\n    " + "\n    ".join(version_list))
        elif os.path.isfile(os.path.join("variants", v, "config.json")):
            loaded_variants.append(f"* {v}")
    loaded_variants.sort()
    message = "\n".join(loaded_variants)
    log_command(logger, ctx, message=message)
    await send_message_and_file(
        channel=ctx.channel, title="Currently loaded variants", message=message
    )
