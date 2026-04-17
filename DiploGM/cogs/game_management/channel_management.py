"""Game management commands related to channel management."""
import logging

import discord
from discord import (
    CategoryChannel,
    PermissionOverwrite,
    Role
)
from discord.ext import commands
from DiploGM import config
from DiploGM.utils import log_command, send_message_and_file
from DiploGM.models.player import Player
from DiploGM.manager import Manager

logger = logging.getLogger(__name__)
manager = Manager()

async def archive(ctx: commands.Context) -> None:
    """Set all channels within a category to read-only, during game close"""
    assert ctx.guild is not None
    categories = [channel.category for channel in ctx.message.channel_mentions if channel.category is not None]
    if not categories:
        await send_message_and_file(
            channel=ctx.channel,
            message="This channel is not part of a category.",
            embed_colour=config.ERROR_COLOUR,
        )
        return

    for category in categories:
        for channel in category.channels:
            overwrites = channel.overwrites

            # Remove all permissions except for everyone
            overwrites.clear()
            overwrites[ctx.guild.default_role] = PermissionOverwrite(
                read_messages=True, send_messages=False
            )

            # Apply the updated overwrites
            await channel.edit(overwrites=overwrites)

    message = f"The following categories have been archived: {' '.join([category.name for category in categories])}"
    log_command(logger, ctx, message=f"Archived {len(categories)} Channels")
    await send_message_and_file(channel=ctx.channel, message=message)

async def blitz(ctx: commands.Context) -> None:
    """Creates all pairwise press channels between players in a game"""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)
    cs = []
    pla = sorted(board.get_players(), key=lambda p: p.get_name())
    for p1 in pla:
        for p2 in pla:
            if p1.name < p2.name:
                c = f"{p1.name}-{p2.name}"
                cs.append((c, p1, p2))

    cos: list[CategoryChannel] = [category for category in ctx.guild.categories
                                    if category.name.lower().startswith("comms")]

    guild = ctx.guild

    available = 0
    for cat in cos:
        available += 50 - len(cat.channels)

    # if available < len(cs):
    #     await send_message_and_file(channel=ctx.channel, message="Not enough available comms")
    #     return

    name_to_player: dict[str, Player] = dict()
    player_to_role: dict[Player | None, Role] = dict()
    for player in board.get_players():
        name_to_player[player.get_name().lower()] = player

    spectator_role = None

    for role in guild.roles:
        if role.name.lower() == "spectator":
            spectator_role = role

        player = name_to_player.get(role.name.lower())
        if player:
            player_to_role[player] = role

    if spectator_role is None:
        await send_message_and_file(
            channel=ctx.channel, message="Missing spectator role"
        )
        return

    for player in board.get_players():
        if not player_to_role.get(player):
            await send_message_and_file(
                channel=ctx.channel,
                message=f"Missing player role for {player.get_name()}",
            )
            return

    current_cat = cos.pop(0)
    available = 50 - len(current_cat.channels)
    while len(cs) > 0:
        while available == 0:
            current_cat = cos.pop(0)
            available = 50 - len(current_cat.channels)

        assert available > 0

        name, p1, p2 = cs.pop(0)

        overwrites: dict[discord.Role | discord.Member | discord.Object, PermissionOverwrite] = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            spectator_role: PermissionOverwrite(view_channel=True),
            player_to_role[p1]: PermissionOverwrite(view_channel=True),
            player_to_role[p2]: PermissionOverwrite(view_channel=True),
        }

        await current_cat.create_text_channel(name, overwrites=overwrites)

        available -= 1

async def last_message(ctx: commands.Context) -> None:
    """Gets the last time each player sent a message."""
    assert ctx.guild is not None

    last_message_dict = manager.last_activity.get(ctx.guild.id, {})
    last_message_times: list[tuple[str, float]] = []
    for player in manager.get_board(ctx.guild.id).get_players():
        last_message_times.append((player.get_name(), last_message_dict.get(player.name, 0.0)))
    last_message_times.sort(key=lambda x: x[1], reverse=True)
    message = "\n".join([f"{player}: <t:{int(last)}:R>"
                            if last != 0.0
                            else f"{player}: No messages seen"
                            for player, last in last_message_times])
    await send_message_and_file(channel=ctx.channel, title="Last Message Times", message=message)
