"""Module within the Game Management cog to handle game creation and exporting/importing game state."""
import json
import logging
import os
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

logger = logging.getLogger(__name__)
manager = Manager()

async def create_game(ctx: commands.Context) -> None:
    """Create a new game for the server."""
    assert ctx.guild is not None
    gametype = remove_prefix(ctx)
    if gametype == "":
        gametype = "classic"
    else:
        gametype = gametype.removeprefix(" ")

    success, message = manager.create_game(ctx.guild.id, gametype)

    welcome_message = "Welcome to the game!\n" + \
        "To submit orders, use the .order command, entering one order per line.\n" + \
        "To view a map including all submitted orders, use the .view_map command.\n" + \
        "To see all your units and which orders you have submitted, use the .view_orders command.\n" + \
        "To create a private press channel, use .create_press_channel.\n" + \
        "For a list of all commands, use the .help command.\n" + \
        "Good luck!"
    if success:
        board = manager.get_board(ctx.guild.id)
        for c in [cat for cat in ctx.guild.categories if config.is_player_category(cat)]:
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
            if os.path.isdir(os.path.join("variants", v, vv)) \
                and os.path.isfile(os.path.join("variants", v, vv, "config.json")):
                version_list.append(vv)
        version_list.sort()
        if len(version_list) > 0:
            loaded_variants.append(f"* {v}:\n    " + "\n    ".join(version_list))
        elif os.path.isfile(os.path.join("variants", v, "config.json")):
            loaded_variants.append(f"* {v}")
    loaded_variants.sort()
    message = "\n".join(loaded_variants)
    log_command(logger, ctx, message=message)
    await send_message_and_file(channel=ctx.channel, title="Currently loaded variants", message=message)
