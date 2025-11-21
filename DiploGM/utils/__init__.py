import re
import logging

import discord
from discord import Guild, Thread
from discord.abc import GuildChannel
from discord.ext import commands

from DiploGM import config
from DiploGM.models.turn import Turn
from DiploGM.manager import Manager
from DiploGM.models.player import Player
from DiploGM.models.unit import UnitType



logger = logging.getLogger(__name__)

whitespace_dict = {
    "_",
}

_north_coast = "nc"
_south_coast = "sc"
_east_coast = "ec"
_west_coast = "wc"

coast_dict = {
    _north_coast: ["nc", "north coast", "(nc)"],
    _south_coast: ["sc", "south coast", "(sc)"],
    _east_coast: ["ec", "east coast", "(ec)"],
    _west_coast: ["wc", "west coast", "(wc)"],
}

_army = "army"
_fleet = "fleet"

unit_dict = {
    _army: ["a", "army", "cannon"],
    _fleet: ["f", "fleet", "boat", "ship"],
}


def get_player_by_role(
    author: commands.Context.author, manager: Manager, server_id: int
) -> Player | None:
    for role in author.roles:
        for player in manager.get_board(server_id).players:
            if simple_player_name(player.name) == simple_player_name(role.name):
                return player
    return None


def get_role_by_player(player: Player, roles: Guild.roles) -> discord.Role | None:
    for role in roles:
        if simple_player_name(role.name) == simple_player_name(player.name):
            return role
    return None


def get_player_by_channel(
    channel: commands.Context.channel,
    manager: Manager,
    server_id: int,
    ignore_category=False,
) -> Player | None:
    # thread -> main channel
    if isinstance(channel, Thread):
        channel = channel.parent

    board = manager.get_board(server_id)
    name = channel.name
    if (not ignore_category) and not config.is_player_category(channel.category.name):
        return None

    if board.is_chaos() and name.endswith("-void"):
        name = name[:-5]
    else:
        if not name.endswith(config.player_channel_suffix):
            return None

        name = name[: -(len(config.player_channel_suffix))]

    try:
        return board.get_cleaned_player(name)
    except ValueError:
        pass
    try:
        return board.get_cleaned_player(simple_player_name(name))
    except ValueError:
        return None

    return None


# FIXME this is done pretty poorly
async def get_channel_by_player(
    player: Player, ctx: commands.Context, manager: Manager
) -> GuildChannel:
    guild = ctx.guild
    guild_id = guild.id
    board = manager.get_board(guild_id)

    channel_name = simple_player_name(player.name) + config.player_channel_suffix

    for category in guild.categories:
        if not config.is_player_category(category.name) and not board.is_chaos():
            continue

        for channel in category.channels:
            if channel.name == channel_name:
                return channel

    return None


# I'm sorry this is a bad function name. I couldn't think of anything better and I'm in a rush
def simple_player_name(name: str):
    return name.lower().replace("-", " ").replace("'", "").replace(".", "")


def get_player_by_name(name: str, manager: Manager, server_id: int) -> Player | None:
    for player in manager.get_board(server_id).players:
        if simple_player_name(player.name) == simple_player_name(name):
            return player
    return None


def get_maps_channel(guild: Guild) -> GuildChannel | None:
    for channel in guild.channels:
        if (
            channel.name.lower() == "maps"
            and channel.category is not None
            and channel.category.name.lower() == "gm channels"
        ):
            return channel
    return None


def get_orders_log(guild: Guild) -> GuildChannel | None:
    for channel in guild.channels:
        # FIXME move "orders" and "gm channels" to bot.config
        if (
            channel.name.lower() == "orders-log"
            and channel.category is not None
            and channel.category.name.lower() == "gm channels"
        ):
            return channel
    return None


def is_player_channel(player_role: str, channel: commands.Context.channel) -> bool:
    player_channel = player_role + config.player_channel_suffix
    return simple_player_name(player_channel) == simple_player_name(
        channel.name
    ) and config.is_player_category(channel.category.name)


def get_keywords(command: str) -> list[str]:
    """Command is split by whitespace with '_' representing whitespace in a concept to be stuck in one word.
    e.g. 'A New_York - Boston' becomes ['A', 'New York', '-', 'Boston']"""
    keywords = command.split(" ")
    for i in range(len(keywords)):
        for j in range(len(keywords[i])):
            if keywords[i][j] in whitespace_dict:
                keywords[i] = keywords[i][:j] + " " + keywords[i][j + 1 :]

    for i in range(len(keywords)):
        keywords[i] = _manage_coast_signature(keywords[i])

    return keywords


def _manage_coast_signature(keyword: str) -> str:
    for coast_key, coast_val in coast_dict.items():
        # we want to make sure this was a separate word like "zapotec ec" and not part of a word like "zapotec"
        suffix = f" {coast_val}"
        if keyword.endswith(suffix):
            # remove the suffix
            keyword = keyword[: len(keyword) - len(suffix)]
            # replace the suffix with the one we expect
            new_suffix = f" {coast_key}"
            keyword += f" {new_suffix}"
    return keyword


def get_unit_type(command: str) -> UnitType | None:
    command = command.strip()
    if command in unit_dict[_army]:
        return UnitType.ARMY
    if command in unit_dict[_fleet]:
        return UnitType.FLEET
    return None


def parse_season(
    arguments: list[str], default_year: str
) -> Turn | None:
    year, season, retreat = default_year, None, False
    for s in arguments:
        if s.isnumeric() and int(s) > 1640:
            year = s

        if s.lower() in ["spring", "s", "sm", "sr"]:
            season = "Spring"
        elif s.lower() in ["fall", "f", "fm", "fr"]:
            season = "Fall"
        elif s.lower() in ["winter", "w", "wa"]:
            season = "Winter"

        if s.lower() in ["retreat", "retreats", "r", "sr", "fr"]:
            retreat = True

    if season is None:
        return None
    if season == "Winter":
        return Turn(year, "Winter Builds")
    else:
        return Turn(year, season + " " + ("Retreats" if retreat else "Moves"))

def get_value_from_timestamp(timestamp: str) -> int | None:
    if len(timestamp) == 10 and timestamp.isnumeric():
        return int(timestamp)

    match = re.match(r"<t:(\d{10}):\w>", timestamp)
    if match:
        return int(match.group(1))

    return None

from .logging import log_command, log_command_no_ctx
from .send_message import send_message_and_file
from .orders import get_orders, get_filtered_orders
from .map_archive import upload_map_to_archive
from .sanitise import sanitise_name