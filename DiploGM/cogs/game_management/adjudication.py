"""Game management commands related to adjudication."""
import asyncio
import logging
import random

import discord.utils
from discord import TextChannel, Guild
from discord.ext import commands

from DiploGM import config
from DiploGM.db.database import get_connection
from DiploGM.models.board import Board
from DiploGM import perms
from DiploGM.utils import (
    get_orders,
    log_command,
    send_message_and_file,
    upload_map_to_archive,
)
from DiploGM.utils.image import svg_to_png

from DiploGM.models.order import Disband, Build
from DiploGM.manager import Manager, SEVERENCE_A_ID, SEVERENCE_B_ID
from DiploGM.utils.sanitise import get_colour_option, remove_prefix
from DiploGM.utils.send_message import ErrorMessage, send_error

logger = logging.getLogger(__name__)
manager = Manager()

async def lock_orders(ctx: commands.Context) -> None:
    """Sets board flag to prevent new order submissions"""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)
    board.orders_enabled = False
    log_command(logger, ctx, message="Locked orders")
    await send_message_and_file(
        channel=ctx.channel,
        title="Locked orders",
        message=f"{board.turn}",
    )

async def unlock_orders(ctx: commands.Context) -> None:
    """Sets board flag to enable new order submissions"""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)
    board.orders_enabled = True
    log_command(logger, ctx, message="Unlocked orders")
    await send_message_and_file(
        channel=ctx.channel,
        title="Unlocked orders",
        message=f"{board.turn}",
    )

async def _post_orders(ctx: commands.Context, board: Board) -> str:
    assert ctx.guild is not None

    try:
        order_text = get_orders(board, None, ctx, fields=True)
    except RuntimeError as err:
        logger.error(err, exc_info=True)
        log_command(
            logger,
            ctx,
            message="Failed for an unknown reason",
            level=logging.ERROR,
        )
        await send_error(ctx.channel, ErrorMessage.UNKNOWN_ERROR)
        return ""
    orders_log_channel = _get_orders_log(ctx.guild)
    if not orders_log_channel or not isinstance(orders_log_channel, TextChannel):
        log_command(
            logger,
            ctx,
            message="Could not find orders log channel",
            level=logging.WARN,
        )
        await send_message_and_file(
            channel=ctx.channel,
            title="Could not find orders log channel",
            embed_colour=config.ERROR_COLOUR,
        )
        return ""

    assert isinstance(order_text, list)
    log = await send_message_and_file(
        channel=orders_log_channel,
        title=f"{board.turn}",
        fields=order_text,
    )
    log_command(logger, ctx, message="Successfully published orders")
    await send_message_and_file(
        channel=ctx.channel,
        title=f"Sent Orders to {log.jump_url}",
    )
    return log.jump_url

async def _ping_phase_change(guild: Guild, board: Board, log_url: str) -> None:
    curr_board = manager.get_board(guild.id)

    extra_info = {}
    if curr_board.turn.is_retreats():
        for player in curr_board.get_players():
            units_to_retreat = sorted([str(u) for u in player.units if len(u.retreat_options or []) > 0])
            if len(units_to_retreat) > 0:
                extra_info[player.name] = "**Units to retreat**:\n" + '\n'.join(units_to_retreat)
    elif (curr_board.turn.is_builds()
            and (old_board := manager._database.get_old_board(board, board.turn.get_previous_turn())) is not None):
        for player in curr_board.get_players():
            old_player = old_board.get_player(player.name)
            if not old_player:
                continue
            extra_info[player.name] = ""
            centers_gained = {str(c) for c in player.centers} - {str(c) for c in old_player.centers}
            if len(centers_gained) > 0:
                centers_gained = sorted([str(c) for c in centers_gained])
                extra_info[player.name] = "**Centers gained**:\n" + '\n'.join(centers_gained)
            centers_lost = {str(c) for c in old_player.centers} - {str(c) for c in player.centers}
            if len(centers_lost) > 0:
                centers_lost = sorted([str(c) for c in centers_lost])
                extra_info[player.name] += "\n**Centers lost**:\n" + '\n'.join(centers_lost)

    for c in [cat for cat in guild.categories if config.is_player_category(cat)]:
        for ch in c.text_channels:
            player = perms.get_player_by_channel(board, ch)
            if not player or (len(player.units) + len(player.centers) == 0):
                continue

            additional_info = extra_info.get(player.name, "")
            await ch.send("The game has adjudicated!\n", silent=True)
            await send_message_and_file(
                channel=ch,
                title="Adjudication Information",
                message=(
                    f"**Order Log:** {log_url}\n"
                    f"**From:** {board.turn}\n"
                    f"**To:** {curr_board.turn}\n"
                    f"{additional_info}"
                ),
            )

async def _update_deadline(ctx: commands.Context, guild_id: int) -> None:
    board = manager.get_board(guild_id)
    if not (timestamp := board.data.get("deadline")):
        return
    phase_length = 2 if board.turn.is_moves() else 1
    board.set_data("deadline", int(timestamp) + 60 * 60 * 24 * phase_length)
    get_connection().execute_arbitrary_sql(
        "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
        (board.board_id, "deadline", board.data["deadline"])
    )
    await send_message_and_file(
        channel=ctx.channel,
        message=f"Updated deadline to <t:{board.data['deadline']}:f>.")

async def publish_orders(ctx: commands.Context, *args) -> None:
    """Publishes orders to the orders log channel, uploads the map to the archive,
    and informs players about the phase change."""
    guild = ctx.guild
    assert guild is not None
    arguments = [arg.lower() for arg in args]

    board = manager.get_previous_board(guild.id)
    if not board:
        await send_message_and_file(
            channel=ctx.channel,
            title="Failed to get previous phase",
            embed_colour=config.ERROR_COLOUR,
        )
        return
    log_url = await _post_orders(ctx, board)

    if "silent" not in arguments and guild.id not in [SEVERENCE_A_ID, SEVERENCE_B_ID]:
        _ = asyncio.create_task(_ping_phase_change(guild, board, log_url))

    if config.MAP_ARCHIVE_SAS_TOKEN:
        file, _ = manager.draw_map_for_board(board, draw_moves=True)
        _ = asyncio.create_task(upload_map_to_archive(ctx, guild.id, board, file))

    if board.data.get("deadline"):
        _ = asyncio.create_task(_update_deadline(ctx, guild.id))

async def _is_missing_orders(board: Board) -> bool:
    if board.turn.is_moves():
        for unit in board.units:
            if unit.order is None:
                return True

    if board.turn.is_retreats():
        for unit in board.units:
            if (unit.province.dislodged_unit == unit
                and unit.retreat_options and len(unit.retreat_options) > 0
                and unit.order is None):
                return True

    if board.turn.is_builds():
        for player in board.get_players():
            count = len(player.centers) - len(player.units)
            current = player.waived_orders
            for order in player.build_orders:
                if isinstance(order, Disband):
                    current -= 1
                elif isinstance(order, Build):
                    current += 1

            if current != count:
                return True
    return False

async def _upload_maps(ctx: commands.Context, args: dict, title: str, board: Board, is_orders: bool) -> None:
    assert ctx.guild is not None
    file, file_name = manager.draw_map_for_board(
        board,
        draw_moves=is_orders,
        color_mode=args["color"],
    )
    converted_file: bytes | None = None
    converted_file_name: str | None = None
    needs_png = args["return_svg"] or (args["full"] and _get_maps_channel(ctx.guild))
    if needs_png:
        converted_file, converted_file_name = await svg_to_png(file, file_name)
    await send_message_and_file(
        channel=ctx.channel,
        title=f"{title} {'Orders' if is_orders else 'Results'} Map",
        message=f"Test adjudication{ ' results' if not is_orders else ''}" if args["test"] else "",
        file=converted_file if args["return_svg"] else file,
        file_name=converted_file_name if args["return_svg"] else file_name,
    )
    if args["full"] and (map_channel := _get_maps_channel(ctx.guild)):
        map_message = await send_message_and_file(
            channel=map_channel,
            title=f"{title} {'Orders' if is_orders else 'Results'} Map",
            file=converted_file,
            file_name=converted_file_name,
        )
        try:
            await map_message.publish()
        except discord.Forbidden:
            pass

async def _adjudication_utils(ctx: commands.Context,
                              guild: discord.Guild,
                              new_board: Board,
                              test_adjudicate: bool) -> None:
    # NOTE: Temporary for Meme's Severence Diplomacy Event
    if guild.id in [SEVERENCE_A_ID, SEVERENCE_B_ID]:
        seva = ctx.bot.get_guild(SEVERENCE_A_ID)
        sevb = ctx.bot.get_guild(SEVERENCE_B_ID)

        aperms = discord.utils.find(lambda r: r.name == "Player", seva.roles).permissions
        bperms = discord.utils.find(lambda r: r.name == "Player", sevb.roles).permissions

        a_allowed = ("Spring" in format(new_board.turn, "%S")
                    or ("Winter" in format(new_board.turn, "%S")
                        and random.choice([0, 1]) == 0))
        await send_message_and_file(channel=ctx.channel,
                                    message=f"Game {'A' if a_allowed else 'B'} is permitted to play.")
        aperms.update(send_messages = a_allowed)
        bperms.update(send_messages = not a_allowed)

    # AUTOMATIC SCOREBOARD OUTPUT FOR DATA SPREADSHEET
    if (new_board.turn.is_builds()
        and (guild.id != config.BOT_DEV_SERVER_ID and guild.name.startswith("Imperial Diplomacy"))
        and not test_adjudicate):
        channel = ctx.bot.get_channel(config.HUB_SERVER_WINTER_SCOREBOARD_OUTPUT_CHANNEL_ID)
        if not channel:
            await send_message_and_file(channel=ctx.channel,
                                        message="Couldn't automatically send off the Winter Scoreboard data",
                                        embed_colour=config.ERROR_COLOUR)
            return
        title = f"### {guild.name} Centre Counts (alphabetical order) | {new_board.turn}"

        players = sorted(new_board.get_players(), key=lambda p: p.get_name())
        counts = "\n".join(map(lambda p: str(len(p.centers)), players))

        await channel.send(title)
        await channel.send(counts)

async def adjudicate(ctx: commands.Context) -> None:
    """Adjudicates the game, and publishes the orders and results maps."""
    guild = ctx.guild
    assert guild is not None

    board = manager.get_board(guild.id)

    arguments = remove_prefix(ctx).lower().split()
    args = {"return_svg": not ({"true", "t", "svg", "s"} & set(arguments)),
            "color": get_colour_option(board, arguments),
            "test": "test" in arguments,
            "full": "full" in arguments and not "test" in arguments,
            "movement": "movement" in arguments,
            "force": ({"force", "confirm"} & set(arguments)) and not "test" in arguments}

    if not args["force"] and not args["test"] and await _is_missing_orders(board):
        await send_message_and_file(
            channel=ctx.channel,
            title="Missing Orders",
            message="Game has not been adjudicated due to missing orders. " +
                    f"To adjudicate anyway, use `{ctx.message.content} confirm`",
            embed_colour=config.ERROR_COLOUR,
        )
        return

    if args["full"]:
        await lock_orders(ctx)

    old_turn = board.turn
    new_board = manager.adjudicate(guild.id, test=args["test"])

    log_command(
        logger,
        ctx,
        message=f"Adjudication Successful for {board.turn}",
    )

    # We draw the board from the DB to apply failed and DP orders that we want to hide from players
    draw_board = manager.get_board_from_db(guild.id, old_turn)
    manager.apply_adjudication_results(guild.id, draw_board)
    title = (f"{board.data.get('game_name')} — " if board.data.get("game_name") else "") + f"{old_turn}"

    await _upload_maps(ctx, args, title, draw_board, True)

    if args["movement"]:
        file, file_name = manager.draw_map_for_board(
            draw_board,
            draw_moves=True,
            color_mode=args["color"],
            movement_only=True,
        )
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{title} Movement Map",
            message="Test adjudication" if args["test"] else "",
            file=file,
            file_name=file_name,
            convert_svg=args["return_svg"],
        )

    await _upload_maps(ctx, args, title, new_board, False)

    if args["full"]:
        await publish_orders(ctx)
        await unlock_orders(ctx)

    await _adjudication_utils(ctx, guild, new_board, args["test"])

def _get_maps_channel(guild: Guild) -> TextChannel | None:
    for channel in guild.channels:
        if (
            channel.name.lower() == "maps"
            and channel.category is not None
            and channel.category.name.lower() == "gm channels"
            and isinstance(channel, TextChannel)
        ):
            return channel
    return None


def _get_orders_log(guild: Guild) -> TextChannel | None:
    for channel in guild.channels:
        # FIXME move "orders" and "gm channels" to bot.config
        if (
            channel.name.lower() == "orders-log"
            and channel.category is not None
            and channel.category.name.lower() == "gm channels"
            and isinstance(channel, TextChannel)
        ):
            return channel
    return None
