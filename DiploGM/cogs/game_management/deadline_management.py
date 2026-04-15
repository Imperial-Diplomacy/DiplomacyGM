"""Game management commands related to deadlines and pinging players."""
import logging
import re
from datetime import timedelta
from time import time

from discord import Member, Role
from discord.ext import commands

from DiploGM import config
from DiploGM.db.database import get_connection
from DiploGM.models.board import Board
from DiploGM import perms
from DiploGM.utils import (
    log_command,
    send_message_and_file,
)

from DiploGM.models.order import Disband, Build
from DiploGM.models.player import Player
from DiploGM.manager import Manager
from DiploGM.utils.sanitise import find_discord_role, remove_prefix
from DiploGM.utils.send_message import ErrorMessage, send_error

logger = logging.getLogger(__name__)
manager = Manager()
# Regex for parsing time deltas, e.g. "2 days 3h 15m"
# Currently supports days, hours, minutes, and seconds and negative values
# We could do more with this if need be, but this should hopefully work for now
_TIMEDELTA_RE = re.compile(
    r"(?:(-?\d+)\s*d(?:ays?)?)?\s*"
    r"(?:(-?\d+)\s*h(?:(?:ou)?rs?)?)?\s*"
    r"(?:(-?\d+)\s*m(?:in(?:ute)?s?)?)?\s*"
    r"(?:(-?\d+)\s*s(?:ec(?:ond)?s?)?)?\s*$"
)

def _parse_timedelta(s: str) -> timedelta:
    m = _TIMEDELTA_RE.fullmatch(s.strip())
    if m and any(m.groups()):
        return timedelta(
            days=int(m.group(1) or 0),
            hours=int(m.group(2) or 0),
            minutes=int(m.group(3) or 0),
            seconds=int(m.group(4) or 0),
        )
    raise ValueError(f"Cannot parse time duration: {s!r}")

async def set_deadline(ctx: commands.Context) -> None:
    """Manages the deadline for the current phase."""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)
    content = remove_prefix(ctx)
    adjust = content.startswith("adjust")
    cancel = content.startswith("cancel")
    if adjust:
        content = content.removeprefix("adjust").strip()
        deadline = int(board.data.get("deadline", time()))
        try:
            parsed_time = _parse_timedelta(content)
        except ValueError as e:
            await send_message_and_file(
                channel=ctx.channel,
                message=str(e),
                embed_colour=config.ERROR_COLOUR,
            )
            return
        new_deadline = deadline + int(parsed_time.total_seconds())
        board.data["deadline"] = new_deadline
        logger.info(f"Adjusted deadline by {parsed_time} to {new_deadline}")
        await send_message_and_file(
            channel=ctx.channel,
            message=f"Adjusted deadline by {parsed_time}. New deadline is <t:{int(new_deadline)}:R>.",
        )
    elif cancel:
        board.data.pop("deadline", None)
        new_deadline = None
        logger.info("Removed deadline")
        await send_message_and_file(
            channel=ctx.channel,
            message="Successfully removed deadline.",
        )
    else:
        timestamp_match = re.search(r"(\d+)", content)
        if not timestamp_match:
            await send_message_and_file(
                channel=ctx.channel,
                message="Invalid timestamp format. Please provide a Unix timestamp.",
                embed_colour=config.ERROR_COLOUR,
            )
            return
        new_deadline = int(timestamp_match.group(1))
        board.data["deadline"] = new_deadline
        logger.info(f"Set new deadline: {new_deadline}")
        await send_message_and_file(
            channel=ctx.channel,
            message=f"Set new deadline: <t:{new_deadline}:R>.",
        )
    if new_deadline is not None:
        get_connection().execute_arbitrary_sql(
            "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
            (board.board_id, "deadline", new_deadline)
        )
    else:
        get_connection().execute_arbitrary_sql(
            "DELETE FROM board_parameters WHERE board_id = ? AND parameter_key = ?",
            (board.board_id, "deadline")
        )

def _ping_player_builds(player: Player,
                        users: set[Member | Role],
                        build_options: str) -> str:
    user_str = ''.join([u.mention for u in users])

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
        return f"Hey {user_str}, you have {difference} {'less' if current > count else 'more'} " + \
            f"disband {order_text} than necessary. Please get this looked at."

    available_centers = [center for center in player.centers if center.can_build(build_options)]
    available = min(len(available_centers), count)

    difference = abs(current - available)
    # We use count here in case someone waives builds
    if current > count:
        return f"Hey {user_str}, you have {difference} more build {order_text} than possible. " + \
            "Please get this looked at."
    if current < available:
        return f"Hey {user_str}, you have {difference} less build {order_text} than necessary. " + \
                f"Please use `.order waive {difference}` if you wish to waive."
    return ""

def _ping_player_moves(board: Board,
                       player: Player,
                       users: set[Member | Role]) -> str:
    missing = [
        unit
        for unit in player.units
        if unit.order is None and
            (board.turn.is_moves() or (unit == unit.province.dislodged_unit and unit.retreat_options))
    ]
    missing_dp = 0
    if board.data.get("dp", "False").lower() in ("true", "enabled"):
        missing_dp = player.dp_max - board.get_dp_spent(player)

    if not missing and missing_dp == 0:
        return ""

    unit_text = f"unit{'s' if len(missing) != 1 else ''}"
    response = f"Hey **{''.join([u.mention for u in users])}**, "
    if missing:
        response += f"you are missing moves for the following {len(missing)} {unit_text}:"
        for unit in sorted(
            missing, key=lambda _unit: _unit.province.name
        ):
            response += f"\n{unit}"
    if missing_dp > 0:
        response += ('\nY' if missing else 'y') + f"ou have {missing_dp} unspent DP."
    elif missing_dp < 0:
        response += ('\nY' if missing else 'y') + f"ou have spent {-missing_dp} too much DP."
    return response

async def ping_players(ctx: commands.Context) -> None:
    """Pings all players with withstanding orders"""

    guild = ctx.guild
    assert guild is not None
    board = manager.get_board(guild.id)
    timestamp = board.data.get("deadline")

    # extract deadline argument
    if (parsed_timestamp := re.match(r"<t:(\d+):[a-zA-Z]>", remove_prefix(ctx))):
        timestamp = parsed_timestamp.group(1)

    # get abstract player information
    player_roles: set[Role] = {r for r in guild.roles if config.is_player_role(r)}
    if len(player_roles) == 0:
        log_command(logger, ctx, message="No player role found")
        await send_error(ctx.channel, ErrorMessage.NO_PLAYER_ROLE)
        return

    player_categories = [c for c in guild.categories if config.is_player_category(c)]
    if len(player_categories) == 0:
        log_command(logger, ctx, message="No player category found")
        await send_error(ctx.channel, ErrorMessage.NO_PLAYER_CATEGORY)
        return

    # ping required players
    pinged_players = 0
    failed_players = []
    response = ""
    for channel in [ch for category in player_categories for ch in category.text_channels]:
        if (player := perms.get_player_by_channel(board, channel)) is None:
            await ctx.send(f"No Player for {channel.name}")
            continue

        # player is completely dead, not worth pinging
        if len(player.centers) + len(player.units) == 0:
            continue

        if (role := find_discord_role(player, guild.roles)) is None:
            await ctx.send(f"No Role for {player.get_name()}")
            continue

        if not board.is_chaos():
            # Find users which have a player role to not ping spectators
            users: set[Member | Role] = {m for m in role.members if set(m.roles) & player_roles}
        else:
            users = {overwritter for overwritter, permission
                        in channel.overwrites.items()
                        if isinstance(overwritter, Member) and permission.view_channel}

        if len(users) == 0:
            failed_players.append(player)
            # Ping role in case of no players
            users.add(role)

        if board.turn.is_builds():
            response = _ping_player_builds(player, users, board.data.get("build_options", "classic"))
        else:
            response = _ping_player_moves(board, player, users)

        if response:
            pinged_players += 1
            if timestamp:
                response += f"\n The orders deadline is <t:{timestamp}:R>."
            await channel.send(response)
            response = None

    log_command(logger, ctx, message=f"Pinged {pinged_players} players")
    await send_message_and_file(
        channel=ctx.channel, title=f"Pinged {pinged_players} players"
    )

    if len(failed_players) > 0:
        failed_players_str = "\n- ".join([player.get_name() for player in failed_players])
        await send_message_and_file(
            channel=ctx.channel,
            title="Failed to find a player for the following:",
            message=f"- {failed_players_str}",
        )
