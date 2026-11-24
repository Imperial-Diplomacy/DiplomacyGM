"""Game management commands related to adjudication."""

import asyncio
import logging

import discord
from discord import Guild

from DiploGM import config
from DiploGM.config import ChannelName, CHANNEL_DEFAULTS
from DiploGM.db.database import get_connection
from DiploGM.models.board import Board
from DiploGM.utils.request import Request
from DiploGM import perms
from DiploGM.utils import (
    get_orders,
    send_message_and_file,
    upload_map_to_archive,
)
from DiploGM.utils.channels import get_guild_channel
from DiploGM.utils.image import svg_to_png

from DiploGM.models.order import Disband, Build
from DiploGM.models.player import (
    ForcedDisbandOption,
    OrdersSubsetOption,
    ViewOrdersTags,
)
from DiploGM.manager import Manager
from DiploGM.utils.sanitise import find_discord_role
from DiploGM.utils.send_message import ErrorMessage, send_error

logger = logging.getLogger(__name__)
manager = Manager()

def _guild_not_found(request: Request) -> str:
    logger.error("Server with ID %s not found", request.guild.id)
    return f"Server with ID {request.guild.id} not found"


def lock_orders(request: Request, lock: bool = True) -> tuple[bool, str | None]:
    """Sets board flag to prevent new order submissions"""
    board = manager.get_board(request.guild.id)
    board.orders_enabled = not lock
    return True, None


async def _post_orders(request: Request, board: Board) -> tuple[bool, str]:
    try:
        tags = ViewOrdersTags(
            subset=OrdersSubsetOption.FULL,
            forced=ForcedDisbandOption.MARK_FORCED,
            blind=False,
            open_cores=False,
            explain=False,
        )
        order_text = get_orders(board, None, tags=tags, fields=True)
        assert isinstance(order_text, list)
        for cur_player in board.players:
            role = find_discord_role(cur_player, request.guild.roles)
            replace = role.mention if role is not None else cur_player.name
            for index, (title, body) in enumerate(order_text):
                order_text[index] = (title, body.replace(f"@{cur_player.name}", replace))
    except RuntimeError as err:
        logger.error(err, exc_info=True)
        return False, ErrorMessage.UNKNOWN_ERROR
    orders_log_channel = get_guild_channel(request.guild, manager, ChannelName.ORDERS_LOG_CHANNEL)
    if not orders_log_channel:
        return False, "Could not find orders log channel"

    log = await send_message_and_file(
        channel=orders_log_channel,
        title=f"{board.turn}",
        fields=order_text,
    )
    await send_message_and_file(
        channel=request.channel,
        title=f"Sent Orders to {log.jump_url}",
    )
    return True, log.jump_url


async def _ping_phase_change(guild: Guild, board: Board, log_url: str | None) -> None:
    curr_board = manager.get_board(guild.id)
    ping_players = manager.ctx_parameters.get(guild.id, {}).get("ping_phase_change", "false") == "true"

    extra_info = {}
    if curr_board.turn.is_retreats():
        for player in curr_board.get_players():
            units_to_retreat = sorted([str(u) for u in player.units if len(u.retreat_options or []) > 0])
            if len(units_to_retreat) > 0:
                extra_info[player.name] = "**Units to retreat**:\n" + "\n".join(units_to_retreat)
    elif curr_board.turn.is_builds() and (old_board := manager.get_previous_board(board.board_id)) is not None:
        for player in curr_board.get_players():
            old_player = old_board.get_player(player.name)
            if not old_player:
                continue
            extra_info[player.name] = ""
            centers_gained = {str(c) for c in player.centers} - {str(c) for c in old_player.centers}
            if len(centers_gained) > 0:
                centers_gained = sorted([str(c) for c in centers_gained])
                extra_info[player.name] = "**Centers gained**:\n" + "\n".join(centers_gained)
            centers_lost = {str(c) for c in old_player.centers} - {str(c) for c in player.centers}
            if len(centers_lost) > 0:
                centers_lost = sorted([str(c) for c in centers_lost])
                extra_info[player.name] += "\n**Centers lost**:\n" + "\n".join(centers_lost)

    for c in [cat for cat in guild.categories if config.is_player_category(cat)]:
        for ch in c.text_channels:
            player = perms.get_player_by_channel(board, ch)
            if not player or (len(player.units) + len(player.centers) == 0):
                continue

            message = "The game has adjudicated!\n"
            if ping_players:
                role = find_discord_role(player, guild.roles)
                message = f"Hey **{role.mention if role else player.name}**, {message}"
            await ch.send(message)

            message = (
                (f"**Order Log:** {log_url}\n" if log_url else "")
                + f"**From:** {board.turn}\n"
                + f"**To:** {curr_board.turn}\n"
                + extra_info.get(player.name, "")
            )
            await send_message_and_file(
                channel=ch,
                title="Adjudication Information",
                message=message,
            )


async def _update_deadline(request: Request) -> None:
    board = manager.get_board(request.guild.id)
    if not (timestamp := board.data.get("deadline")):
        return
    if board.turn.is_moves():
        phase_length = board.data.get("phase_length", {}).get("moves", 60*60*24*2)
    elif board.turn.is_retreats():
        phase_length = board.data.get("phase_length", {}).get("retreats", 60*60*24)
    else:
        phase_length = board.data.get("phase_length", {}).get("builds", 60*60*24)
    board.set_data("deadline", int(timestamp) + int(phase_length))
    get_connection().execute_arbitrary_sql(
        "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
        (board.board_id, "deadline", board.data["deadline"]),
    )
        # await refresh_repeated_tasks(ctx) TODO: Get Scheduler working
    await send_message_and_file(
        channel=request.channel,
        message=f"Updated deadline to <t:{board.data['deadline']}:f>.",
    )


async def publish_orders(request: Request, *args) -> tuple[bool, str | None]:
    """Publishes orders to the orders log channel, uploads the map to the archive,
    and informs players about the phase change."""
    arguments = [arg.lower() for arg in args]

    board = manager.get_previous_board(request.guild.id)
    if not board:
        return False, ErrorMessage.NO_PREVIOUS_BOARD
    success, response = await _post_orders(request, board)
    if not success:
        return False, response

    if "silent" not in arguments:
        _ = asyncio.create_task(_ping_phase_change(request.guild, board, response))

    if config.MAP_ARCHIVE_SECRET_ACCESS_KEY:
        file, _ = manager.draw_map_for_board(board, draw_moves=True)
        _ = asyncio.create_task(upload_map_to_archive(request.channel, request.guild.id, board, file))

    if board.data.get("deadline"):
        _ = asyncio.create_task(_update_deadline(request))
        #if manager.ctx_parameters.get(guild.id, {}).get("post_deadlines", "true") == "true": TODO
        #    _ = asyncio.create_task(deadline_management.post_deadline(ctx))
    return True, None


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
    request: Request,
    args: dict,
    board: Board,
    is_orders: bool,
    maps_channel_id: str | None,
    map_modes: list[str],
) -> None:
    file, file_name = manager.draw_map_for_board(board, draw_moves=is_orders, map_modes=map_modes)
    old_turn = board.turn if is_orders else board.turn.get_previous_turn()
    title = (
        f"{board.data.get('game_name')} — " if board.data.get("game_name") else ""
    ) + f"{old_turn}"

    if maps_channel_id is not None:
        map_channel = request.guild.get_channel(int(maps_channel_id))
        if not isinstance(map_channel, discord.TextChannel):
            await send_error(request.channel, ErrorMessage.INVALID_MAPS_CHANNEL)
            map_channel = None
    else:
        map_channel = None

    image_file: bytes | None = None
    image_file_name: str | None = None
    needs_png = args["return_svg"] or (args["full"] and map_channel is not None)
    if needs_png:
        image_file, image_file_name = await svg_to_png(
            file, file_name, board.data["svg config"], pacific_mode="pacific" in map_modes
        )
    await send_message_and_file(
        channel=request.channel,
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

async def adjudicate(request: Request, args: dict) -> tuple[bool, str | None]:
    """Adjudicates the game, and publishes the orders and results maps."""

    board = manager.get_board(request.guild.id)
    if not args["force"] and not args["test"] and await _is_missing_orders(board):
        return False, "Missing Orders" # TODO: Probably should be an Enum

    if args["full"]:
        lock_orders(request, lock=True)

    old_turn = board.turn
    message, new_board = manager.adjudicate(request.guild.id, test=args["test"])
    if message:
        await send_message_and_file(
            channel=request.channel,
            title="Additional adjudication information",
            message=message,
        )

    # We draw the board from the DB to apply failed and DP orders that we want to hide from players
    draw_board = manager.get_board_from_db(request.guild.id, old_turn)
    manager.apply_adjudication_results(request.guild.id, draw_board)
    title = (
        f"{board.data.get('game_name')} — " if board.data.get("game_name") else ""
    ) + f"{old_turn}"

    if args["full"]:
        map_channels = dict(manager.ctx_parameters.get(request.guild.id, {}).get("maps_channel", {}))
    else:
        map_channels = {}
    default_maps_channel = discord.utils.get(request.guild.text_channels, name=CHANNEL_DEFAULTS[ChannelName.MAPS_CHANNEL])
    if default_maps_channel and default_maps_channel not in map_channels:
        map_channels[str(default_maps_channel.id)] = "standard"
    if args.get("map_modes") is not None and default_maps_channel:
        map_channels[str(default_maps_channel.id)] = args["map_modes"]
    if len(map_channels.items()) == 0:
        logger.warning("Map channel not found in guild %s", request.guild.id)
        await send_error(request.channel, ErrorMessage.NO_MAPS_CHANNEL)
        await _upload_maps(request, args, draw_board, True, None, ["standard"])
        await _upload_maps(request, args, new_board, False, None, ["standard"])
    for map_channel, map_modes in map_channels.items():
        map_modes = map_modes.split(" ") if isinstance(map_modes, str) else map_modes
        await _upload_maps(request, args, draw_board, True, map_channel, map_modes)
        await _upload_maps(request, args, new_board, False, map_channel, map_modes)

    if args["movement"]:
        file, file_name = manager.draw_map_for_board(
            draw_board,
            draw_moves=True,
            map_modes=args["map_modes"],
            movement_only=True,
        )
        await send_message_and_file(
            channel=request.channel,
            title=f"{title} Movement Map",
            message="Test adjudication" if args["test"] else "",
            file=file,
            file_name=file_name,
        )

    if args["full"]:
        success, response = await publish_orders(request)
        if not success and response:
            await send_error(request.channel, response)
        lock_orders(request, lock=False)
#        if board.data.get("fow", "disabled") == "enabled" and (fow_cog := ctx.bot.get_cog("FogOfWarCog")) is not None: TODO
#            await fow_cog.publish_fow_order_logs(ctx)
#            await fow_cog.publish_fow_moves(ctx)

    return True, None
