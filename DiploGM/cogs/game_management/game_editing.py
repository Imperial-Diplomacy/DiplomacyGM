"""Game management commands related to editing the game and rolling/reloading the game."""
import logging

import discord.utils
from discord.ext import commands

from DiploGM import config
from DiploGM.config import PLAYER_CHANNEL_SUFFIX
from DiploGM.db.database import get_connection
from DiploGM.parse_edit_state import parse_edit_state
from DiploGM.parse_board_params import parse_board_params
from DiploGM.utils import log_command, send_message_and_file

from DiploGM.manager import Manager
from DiploGM.utils.sanitise import find_discord_role, remove_prefix, sanitise_name

logger = logging.getLogger(__name__)
manager = Manager()

async def rollback(ctx: commands.Context) -> None:
    """Rolls back the game board to the previous phase"""
    assert ctx.guild is not None
    message, file, file_name = manager.rollback(ctx.guild.id)
    log_command(logger, ctx, message=message)
    await send_message_and_file(channel=ctx.channel, message=message, file=file, file_name=file_name)

async def reload(ctx: commands.Context) -> None:
    """Reloads the board state currently saved in the database."""
    assert ctx.guild is not None
    message, file, file_name = manager.reload(ctx.guild.id)
    log_command(logger, ctx, message=message)
    await send_message_and_file(channel=ctx.channel, message=message, file=file, file_name=file_name)

async def edit(ctx: commands.Context) -> None:
    """Edits the current board state"""
    assert ctx.guild is not None
    edit_commands = remove_prefix(ctx)
    board = manager.get_board(ctx.guild.id)
    title, message, file, file_name, embed_colour = parse_edit_state(edit_commands, board)
    if file is not None:
        get_connection().save_board_state(ctx.guild.id, board)
    log_command(logger, ctx, message=title)
    await send_message_and_file(channel=ctx.channel,
                                title=title,
                                message=message,
                                file=file,
                                file_name=file_name,
                                embed_colour=embed_colour)

async def edit_game(ctx: commands.Context) -> None:
    """Edits game parameters."""
    assert ctx.guild is not None
    param_commands = remove_prefix(ctx)
    title, message, file, file_name, embed_colour = parse_board_params(param_commands,
                                                                        manager.get_board(ctx.guild.id))
    log_command(logger, ctx, message=title)
    await send_message_and_file(channel=ctx.channel,
                                title=title,
                                message=message,
                                file=file,
                                file_name=file_name,
                                embed_colour=embed_colour)

async def rename_player(ctx: commands.Context, old_name: str, new_name: str) -> None:
    """Renames a player, and updates their role and channel names if possible."""
    assert ctx.guild is not None
    message = ""
    board = manager.get_board(ctx.guild.id)
    if not (player := board.get_player(old_name)):
        await send_message_and_file(
            channel=ctx.channel,
            message=f"Could not find a player with the name {old_name}",
            embed_colour=config.ERROR_COLOUR,
        )
        return

    old_role = find_discord_role(player, ctx.guild.roles)
    old_order_role = find_discord_role(player, ctx.guild.roles, get_order_role=True)
    order_channel_name = player.get_name().lower().replace(" ", "-") + PLAYER_CHANNEL_SUFFIX
    void_channel_name = player.get_name().lower().replace(" ", "-") + "-void"

    has_removed_nickname = board.add_nickname(player, new_name)
    if has_removed_nickname:
        get_connection().execute_arbitrary_sql(
            "DELETE FROM board_parameters WHERE board_id = ? AND parameter_key = ?",
            (board.board_id, f"players/{player.name}/nickname")
        )
    else:
        get_connection().execute_arbitrary_sql(
            "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
            (board.board_id, f"players/{player.name}/nickname", new_name)
        )
    message += f"Renamed player {old_name} to {new_name}."

    if old_role:
        await old_role.edit(name = sanitise_name(new_name))
        message += f"\nUpdated role {sanitise_name(old_name)} to {sanitise_name(new_name)}."
    if old_order_role:
        await old_order_role.edit(name = "orders-" + sanitise_name(new_name))
        message += f"\nUpdated order role {sanitise_name(old_name)}{PLAYER_CHANNEL_SUFFIX} " + \
                    f"to {sanitise_name(new_name)}{PLAYER_CHANNEL_SUFFIX}."

    order_channel = discord.utils.find(lambda c: c.name == order_channel_name, ctx.guild.text_channels)
    if order_channel:
        await order_channel.edit(name = new_name.lower().replace(" ", "-") + PLAYER_CHANNEL_SUFFIX)
        message += f"\nUpdated order channel {order_channel_name} to " + \
                    f"{new_name.lower().replace(' ', '-')}{PLAYER_CHANNEL_SUFFIX}."

    void_channel = discord.utils.find(lambda c: c.name == void_channel_name, ctx.guild.text_channels)
    if void_channel:
        await void_channel.edit(name = new_name.lower().replace(" ", "-") + "-void")
        message += f"\nUpdated void channel {void_channel_name} to {new_name.lower().replace(' ', '-')}-void."

    log_command(logger, ctx, message=message)
    await send_message_and_file(
        channel=ctx.channel,
        message=message,
    )
