"""Game management commands related to adjudication."""

import asyncio
import logging

import discord
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
from DiploGM.models.player import (
    ForcedDisbandOption,
    OrdersSubsetOption,
    ViewOrdersTags,
)
from DiploGM.manager import Manager
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
        tags = ViewOrdersTags(
            subset=OrdersSubsetOption.FULL,
            forced=ForcedDisbandOption.MARK_FORCED,
            blind=False,
            open_cores=False,
            explain=False,
        )
        order_text = get_orders(board, None, ctx, tags=tags, fields=True)
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
            units_to_retreat = sorted(
                [str(u) for u in player.units if len(u.retreat_options or []) > 0]
            )
            if len(units_to_retreat) > 0:
                extra_info[player.name] = "**Units to retreat**:\n" + "\n".join(
                    units_to_retreat
                )
    elif (
        curr_board.turn.is_builds()
        and (old_board := manager.get_previous_board(board.board_id)) is not None
    ):
        for player in curr_board.get_players():
            old_player = old_board.get_player(player.name)
            if not old_player:
                continue
            extra_info[player.name] = ""
            centers_gained = {str(c) for c in player.centers} - {
                str(c) for c in old_player.centers
            }
            if len(centers_gained) > 0:
                centers_gained = sorted([str(c) for c in centers_gained])
                extra_info[player.name] = "**Centers gained**:\n" + "\n".join(
                    centers_gained
                )
            centers_lost = {str(c) for c in old_player.centers} - {
                str(c) for c in player.centers
            }
            if len(centers_lost) > 0:
                centers_lost = sorted([str(c) for c in centers_lost])
                extra_info[player.name] += "\n**Centers lost**:\n" + "\n".join(
                    centers_lost
                )

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
    if board.turn.is_moves():
        phase_length = board.data.get("phase_length", []).get("moves", 60*60*24*2)
    elif board.turn.is_retreats():
        phase_length = board.data.get("phase_length", []).get("retreats", 60*60*24)
    else:
        phase_length = board.data.get("phase_length", []).get("builds", 60*60*24)
    board.set_data("deadline", int(timestamp) + int(phase_length))
    get_connection().execute_arbitrary_sql(
        "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
        (board.board_id, "deadline", board.data["deadline"]),
    )
    await send_message_and_file(
        channel=ctx.channel,
        message=f"Updated deadline to <t:{board.data['deadline']}:f>.",
    )


async def publish_orders(ctx: commands.Context, *args) -> None:
    """Publishes orders to the orders log channel, uploads the map to the archive,
    and informs players about the phase change."""
    guild = ctx.guild
    assert guild is not None
    arguments = [arg.lower() for arg in args]

    board = manager.get_previous_board(guild.id)
    if not board:
        await send_error(ctx.channel, ErrorMessage.NO_PREVIOUS_BOARD)
        return
    log_url = await _post_orders(ctx, board)

    if "silent" not in arguments:
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
            if (
                unit.province.dislodged_unit == unit
                and unit.retreat_options
                and len(unit.retreat_options) > 0
                and unit.order is None
            ):
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


async def _upload_maps(
    ctx: commands.Context,
    args: dict,
    board: Board,
    is_orders: bool,
    maps_channel_id: str | None,
    color_mode: str,
) -> None:
    assert ctx.guild is not None
    file, file_name = manager.draw_map_for_board(
        board,
        draw_moves=is_orders,
        color_mode=color_mode,
    )
    old_turn = board.turn if is_orders else board.turn.get_previous_turn()
    title = (
        f"{board.data.get('game_name')} — " if board.data.get("game_name") else ""
    ) + f"{old_turn}"

    if maps_channel_id is not None:
        map_channel = ctx.guild.get_channel(int(maps_channel_id))
        if not isinstance(map_channel, discord.TextChannel):
            await send_error(ctx.channel, ErrorMessage.INVALID_MAPS_CHANNEL)
            map_channel = None
    else:
        map_channel = None

    image_file: bytes | None = None
    image_file_name: str | None = None
    needs_png = args["return_svg"] or (args["full"] and map_channel is not None)
    if needs_png:
        image_file, image_file_name = await svg_to_png(
            file, file_name, dpi=board.data["svg config"].get("dpi", 200)
        )
    await send_message_and_file(
        channel=ctx.channel,
        title=f"{title} {'Orders' if is_orders else 'Results'} Map",
        message=f"Test adjudication{' results' if not is_orders else ''}"
        if args["test"]
        else "",
        file=image_file if args["return_svg"] else file,
        file_name=image_file_name if args["return_svg"] else file_name,
    )
    if args["full"] and map_channel is not None:
        map_message = await send_message_and_file(
            channel=map_channel,
            title=f"{title} {'Orders' if is_orders else 'Results'} Map",
            file=image_file,
            file_name=image_file_name,
        )
        try:
            await map_message.publish()
        except discord.Forbidden:
            pass


async def _adjudication_utils(
    ctx: commands.Context, guild: discord.Guild, new_board: Board, test_adjudicate: bool
) -> None:
    # AUTOMATIC SCOREBOARD OUTPUT FOR DATA SPREADSHEET
    if (
        new_board.turn.is_builds()
        and (
            guild.id != config.BOT_DEV_SERVER_ID
            and guild.name.startswith("Imperial Diplomacy")
        )
        and not test_adjudicate
    ):
        channel = ctx.bot.get_channel(
            config.HUB_SERVER_WINTER_SCOREBOARD_OUTPUT_CHANNEL_ID
        )
        if not channel:
            await send_message_and_file(
                channel=ctx.channel,
                message="Couldn't automatically send off the Winter Scoreboard data",
                embed_colour=config.ERROR_COLOUR,
            )
            return
        title = (
            f"### {guild.name} Centre Counts (alphabetical order) | {new_board.turn}"
        )

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
    args = {
        "return_svg": not ({"true", "t", "svg", "s"} & set(arguments)),
        "color": get_colour_option(board, arguments),
        "test": "test" in arguments,
        "full": "full" in arguments and "test" not in arguments,
        "movement": "movement" in arguments,
        "force": ({"force", "confirm"} & set(arguments)) and "test" not in arguments,
    }

    if not args["force"] and not args["test"] and await _is_missing_orders(board):
        await send_message_and_file(
            channel=ctx.channel,
            title="Missing Orders",
            message="Game has not been adjudicated due to missing orders. "
            + f"To adjudicate anyway, use `{ctx.message.content} confirm`",
            embed_colour=config.ERROR_COLOUR,
        )
        return

    if args["full"]:
        await lock_orders(ctx)

    old_turn = board.turn
    message, new_board = manager.adjudicate(guild.id, test=args["test"])
    if message:
        await send_message_and_file(
            channel=ctx.channel,
            title="Additional adjudication information",
            message=message,
        )

    log_command(
        logger,
        ctx,
        message=f"Adjudication Successful for {board.turn}",
    )

    # We draw the board from the DB to apply failed and DP orders that we want to hide from players
    draw_board = manager.get_board_from_db(guild.id, old_turn)
    manager.apply_adjudication_results(guild.id, draw_board)
    title = (
        f"{board.data.get('game_name')} — " if board.data.get("game_name") else ""
    ) + f"{old_turn}"

    if args["full"]:
        map_channels = dict(
            manager.ctx_parameters.get(guild.id, {}).get("maps_channel", {})
        )
    else:
        map_channels = {}
    default_maps_channel = _get_maps_channel(guild)
    if default_maps_channel and default_maps_channel not in map_channels:
        map_channels[default_maps_channel] = "standard"
    if args.get("color") is not None and default_maps_channel:
        map_channels[default_maps_channel] = args["color"]
    if len(map_channels.items()) == 0:
        log_command(logger, ctx, "No map channel found in this server", level=logging.WARNING)
        await send_error(ctx.channel, ErrorMessage.NO_MAPS_CHANNEL)
        await _upload_maps(ctx, args, draw_board, True, None, "standard")
        await _upload_maps(ctx, args, new_board, False, None, "standard")
    for map_channel, color_mode in map_channels.items():
        await _upload_maps(ctx, args, draw_board, True, map_channel, color_mode)
        await _upload_maps(ctx, args, new_board, False, map_channel, color_mode)

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
            dpi=board.data["svg config"].get("dpi", 200),
        )

    if args["full"]:
        await publish_orders(ctx)
        await unlock_orders(ctx)

    await _adjudication_utils(ctx, guild, new_board, args["test"])


def _get_maps_channel(guild: Guild) -> str | None:
    for channel in guild.channels:
        if (
            channel.name.lower() == config.MAPS_CHANNEL
            and channel.category is not None
            and channel.category.name.lower() == config.GM_CATEGORY
            and isinstance(channel, TextChannel)
        ):
            return str(channel.id)
    return None


def _get_orders_log(guild: Guild) -> TextChannel | None:
    for channel in guild.channels:
        if (
            channel.name.lower() == config.ORDERS_LOG_CHANNEL
            and channel.category is not None
            and channel.category.name.lower() == config.GM_CATEGORY
            and isinstance(channel, TextChannel)
        ):
            return channel
    return None
