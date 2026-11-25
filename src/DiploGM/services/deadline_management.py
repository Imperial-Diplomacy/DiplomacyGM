"""Game management commands related to deadlines and pinging players."""

import logging
import re
from time import time
from datetime import datetime, timezone
from dateparser import parse

from discord import Member, Role

from DiploGM import config, perms
from DiploGM.config import ChannelName
from DiploGM.db.database import get_connection
from DiploGM.models.board import Board
from DiploGM.utils import send_message_and_file

from DiploGM.models.order import Disband, Build
from DiploGM.models.player import Player
from DiploGM.manager import Manager
from DiploGM.scheduler import Scheduler
from DiploGM.utils.channels import get_guild_channel
from DiploGM.utils.request import Request
from DiploGM.utils.sanitise import find_discord_role
from DiploGM.utils.send_message import ErrorMessage

logger = logging.getLogger(__name__)
manager = Manager()

async def set_deadline(request: Request, deadline: str) -> tuple[bool, str]:
    board = manager.get_board(request.guild.id)
    timestamp_match = re.search(r"(\d{10})", deadline)
    if timestamp_match is None:
        return False, "Invalid timestamp format. Please provide a Unix timestamp."
    new_deadline = int(timestamp_match.group(1))
    current_deadline = int(board.data.get("deadline", time()))
    time_delta = (datetime.fromtimestamp(new_deadline, tz=timezone.utc)
                - datetime.fromtimestamp(current_deadline, tz=timezone.utc))
    await Scheduler().adjust_repeated_tasks(board, time_delta)
    board.set_data("deadline", new_deadline)
    get_connection().execute_arbitrary_sql(
        "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
        (board.board_id, "deadline", new_deadline),
    )
    logger.info("Set new deadline: %s", new_deadline)
    return True, f"Set new deadline: <t:{new_deadline}:R>."

async def adjust_deadline(request: Request, deadline: str) -> tuple[bool, str]:
    board = manager.get_board(request.guild.id)
    current_deadline = int(board.data.get("deadline", time()))
    new_deadline = parse(deadline, settings={
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": datetime.fromtimestamp(current_deadline, tz=timezone.utc)
    })
    if new_deadline is None:
        return False, "Invalid time format. Please provide a valid time."

    new_deadline = new_deadline.replace(tzinfo=timezone.utc)
    time_delta = new_deadline - datetime.fromtimestamp(current_deadline, tz=timezone.utc)
    await Scheduler().adjust_repeated_tasks(board, time_delta)
    board.set_data("deadline", int(new_deadline.timestamp()))
    get_connection().execute_arbitrary_sql(
        "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
        (board.board_id, "deadline", int(new_deadline.timestamp())),
    )
    logger.info("Adjusted deadline to %s", new_deadline)
    return True, f"Adjusted deadline to <t:{int(new_deadline.timestamp())}:f>."

def cancel_deadline(request: Request) -> tuple[bool, str]:
    """Manages the deadline for the current phase."""
    board = manager.get_board(request.guild.id)
    board.custom_data.pop("deadline", None)
    board.data.pop("deadline", None)
    get_connection().execute_arbitrary_sql(
        "DELETE FROM board_parameters WHERE board_id = ? AND parameter_key = ?",
        (board.board_id, "deadline"),
    )
    logger.info("Removed deadline")
    return True, "Successfully removed deadline."

async def set_phase_length(request: Request, phase_strs: tuple[str, str, str]) -> tuple[bool, str]:
    """Sets the default phase length for movement, retreat, and adjustment phases."""
    board = manager.get_board(request.guild.id)
    phase_names = ["moves", "retreats", "builds"]
    phase_lengths = []
    if len(phase_strs) < 3:
        return False, "Please provide movement, retreat, and adjustment phase lengths."

    for phase_str in phase_strs:
        if phase_str.isnumeric():
            phase_lengths.append(60*60*int(phase_str))
            continue
        time_match = re.fullmatch(r"((\d+)h)?((\d+)m)?", phase_str)
        if time_match:
            hours = int(time_match.group(2)) if time_match.group(2) else 0
            minutes = int(time_match.group(4)) if time_match.group(4) else 0
            if hours == 0 and minutes == 0:
                return False, "Please provide a nonzero phase length."
            phase_lengths.append(60 * 60 * hours + 60 * minutes)
            continue
        return False, f"Invalid phase length: {phase_str}."

    for phase_name, phase_length in zip(phase_names, phase_lengths):
        board.set_data(["phase_length", phase_name], phase_length)
        get_connection().execute_arbitrary_sql(
            "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
            (board.board_id, f"phase_length/{phase_name}", phase_length),
        )
    return True, (f"Set phase lengths: Moves: {phase_lengths[0]//3600}h {(phase_lengths[0]%3600)//60}m, "
                  f"Retreats: {phase_lengths[1]//3600}h {(phase_lengths[1]%3600)//60}m, "
                  f"Builds: {phase_lengths[2]//3600}h {(phase_lengths[2]%3600)//60}m."
    )

def _ping_player_builds(board: Board, player: Player, user_str: str) -> str:
    build_options = board.data.get("build_options", "classic")

    count = len(player.centers) - len(player.units)
    num_builds = len([o for o in player.build_orders if isinstance(o, Build)])
    num_disbands = len([o for o in player.build_orders if isinstance(o, Disband)])
    current = player.waived_orders + num_builds - num_disbands

    difference = abs(current - count)
    order_text = f"order{'s' if difference != 1 else ''}"

    if (player.waived_orders + num_builds) > 0 and num_disbands > 0:
        return f"Hey {user_str}, you have both build and disband orders. Please get this looked at."

    if count < 0:
        if current == count:
            return ""
        return (
            f"Hey {user_str}, you have {difference} {'less' if current > count else 'more'} "
            + f"disband {order_text} than necessary. Please get this looked at."
        )

    available_centers = [
        center for center in player.centers if center.can_build(build_options)
    ]
    available = min(len(available_centers), count)

    difference = abs(current - available)
    # We use count here in case someone waives builds
    if current > count:
        return (
            f"Hey {user_str}, you have {difference} more build {order_text} than possible. "
            + "Please get this looked at."
        )
    if current < available:
        return (
            f"Hey {user_str}, you have {difference} less build {order_text} than necessary. "
            + f"Please use `.order waive {difference}` if you wish to waive."
        )
    return ""


def _ping_player_moves(board: Board, player: Player, user_str: str) -> str:
    missing = [
        unit
        for unit in player.units
        if unit.order is None
        and (
            board.turn.is_moves()
            or (unit == unit.province.dislodged_unit and unit.retreat_options)
        )
    ]
    missing_dp = 0
    if board.data.get("dp", "False").lower() in ("true", "enabled"):
        missing_dp = player.dp_max - board.get_dp_spent(player)

    if not missing and missing_dp == 0:
        return ""

    unit_text = f"unit{'s' if len(missing) != 1 else ''}"
    response = f"Hey **{user_str}**, "

    if missing:
        response += (
            f"you are missing moves for the following {len(missing)} {unit_text}:"
        )
        for unit in sorted(missing, key=lambda _unit: _unit.province.name):
            response += f"\n{unit}"
    if missing_dp > 0:
        response += ("\nY" if missing else "y") + f"ou have {missing_dp} unspent DP."
    elif missing_dp < 0:
        response += (
            "\nY" if missing else "y"
        ) + f"ou have spent {-missing_dp} too much DP."
    return response


async def ping_players(request: Request, timestamp: str | None = None, message: str = '') -> tuple[bool, str]:
    """Pings all players with withstanding orders"""

    board = manager.get_board(request.guild.id)
    timestamp = timestamp or board.data.get("deadline")

    # get abstract player information
    player_roles: set[Role] = {r for r in request.guild.roles if config.is_player_role(r)}
    if len(player_roles) == 0:
        return False, ErrorMessage.NO_PLAYER_ROLE

    player_categories = [c for c in request.guild.categories if config.is_player_category(c)]
    if len(player_categories) == 0:
        return False, ErrorMessage.NO_PLAYER_CATEGORY

    # ping required players
    pinged_players = 0
    failed_players = []
    for channel in [ch for category in player_categories for ch in category.text_channels]:
        if (player := perms.get_player_by_channel(board, channel)) is None:
            continue

        # player is completely dead, not worth pinging
        if len(player.centers) + len(player.units) == 0:
            continue

        if (role := find_discord_role(player, request.guild.roles)) is None:
            await send_message_and_file(channel=request.channel, message=f"No Role for {player.get_name()}")
            continue

        if not board.is_chaos():
            # Find users which have a player role to not ping spectators
            users: set[Member | Role] = {m for m in role.members if set(m.roles) & player_roles}
        else:
            users = {
                overwritter
                for overwritter, permission in channel.overwrites.items()
                if isinstance(overwritter, Member) and permission.view_channel
            }

        if len(users) == 0:
            failed_players.append(player)
            # Ping role in case of no players
            users.add(role)

        ping_function = (_ping_player_builds if board.turn.is_builds() else _ping_player_moves)
        user_mention = ''.join([u.mention for u in users])
        user_str = ', '.join([u.nick if (isinstance(u, Member) and u.nick is not None) else str(u) for u in users]) if message else user_mention
        response = ping_function(board, player, user_str)
        if not response:
            continue
        pinged_players += 1
        if timestamp:
            response += f"\n The orders deadline is <t:{timestamp}:R>."
            message = message.replace("%F", f"<t:{timestamp}:F>").replace("%f", f"<t:{timestamp}:f>")
            message = message.replace("%D", f"<t:{timestamp}:D>").replace("%d", f"<t:{timestamp}:d>")
            message = message.replace("%T", f"<t:{timestamp}:T>").replace("%t", f"<t:{timestamp}:t>")
            message = message.replace("%R", f"<t:{timestamp}:R>")
        if message:
            if (message := message.replace("%p", user_mention)) == message:
                message = f"{user_mention}, {message}"
            await channel.send(message)
        await channel.send(response)

    message = f"Pinged {pinged_players} players"
    if len(failed_players) > 0:
        failed_players_str = "\n- ".join([player.get_name() for player in failed_players])
        message += f"\nFailed to find a player for the following:\n- {failed_players_str}"
    return True, message

async def post_deadline(request: Request) -> tuple[bool, str | None]:
    """Posts the current deadline to the deadlines channel."""
    board = manager.get_board(request.guild.id)
    if (deadline := board.data.get("deadline")) is None:
        return False, ErrorMessage.NO_DEADLINE
    deadlines_channel = get_guild_channel(request.guild, manager, ChannelName.DEADLINES)
    if deadlines_channel is None:
        return False, ErrorMessage.NO_DEADLINES_CHANNEL
    last_message = deadlines_channel.last_message
    if last_message is not None and str(board.turn) in last_message.content:
        await last_message.delete()
    message = f"The {board.turn} deadline is <t:{deadline}:R>, at <t:{deadline}:F>."
    await send_message_and_file(
        channel=deadlines_channel,
        message=message
    )
    return True, None
