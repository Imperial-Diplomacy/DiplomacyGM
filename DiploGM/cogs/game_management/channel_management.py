"""Game management commands related to channel management."""
import logging
from math import ceil

import discord
from discord import (
    CategoryChannel,
    PermissionOverwrite,
    Role
)
from discord.ext import commands
from DiploGM import config
from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.utils import log_command, send_message_and_file
from DiploGM.models.player import Player
from DiploGM.manager import Manager
from DiploGM.utils.sanitise import remove_prefix

logger = logging.getLogger(__name__)
manager = Manager()

async def setup_server(ctx: commands.Context) -> None:
    """Sets up the server for a game, creating categories, channels, and roles as needed."""
    async def _create_role(name: str, **kwargs) -> Role:
        assert ctx.guild is not None
        if (role := discord.utils.get(ctx.guild.roles, name=name)) is None:
            role = await ctx.guild.create_role(name=name, **kwargs)
        return role

    async def _create_category(name: str, **kwargs) -> CategoryChannel:
        assert ctx.guild is not None
        if (category := discord.utils.get(ctx.guild.categories, name=name)) is None:
            category = await ctx.guild.create_category(name=name, **kwargs)
        return category

    async def _create_channel(name: str, category: CategoryChannel, **kwargs):
        if discord.utils.get(category.channels, name=name) is None:
            await category.create_text_channel(name=name, **kwargs)

    assert ctx.guild is not None
    gametype = remove_prefix(ctx) or "classic"
    try:
        parser_result = get_parser(gametype)
        if isinstance(parser_result, str):
            message = parser_result
            log_command(logger, ctx, message=message)
            await send_message_and_file(channel=ctx.channel, message=message)
            return
        board = parser_result.parse()
    except ValueError as e:
        message = str(e)
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)
        return

    players = sorted(list(board.players), key=lambda p: p.get_name())
    roles = {}

    roles["cspec"] = await _create_role(name = "Country Spectator", color = discord.Color.from_str("#96dfff"))
    for player in players:
        roles[player.name] = await _create_role(name = player.get_name(),
                                                color = discord.Color.from_str(f"#{player.default_color}"),
                                                mentionable = True, hoist = True)
    await _create_role(name = "Dead", color = discord.Color.from_str("#0b2f68"), hoist = True)
    roles["Player"] = await _create_role(name = "Player",
                                     permissions = discord.Permissions(send_messages=True, add_reactions=True))
    for player in players:
        roles[f"orders-{player.name.lower()}"] = await _create_role(name = f"orders-{player.name.lower()}")
    roles["Spectator"] = await _create_role(name = "Spectator",
                                        color = discord.Color.from_str("#2ecc71"), hoist = True)
    log_command(logger, ctx, message="Created roles for all players and spectators")
    await send_message_and_file(channel=ctx.channel, message="Roles created for all players and spectators")

    gm_channel_category = await _create_category(name="GM Channels",
        overwrites={ctx.guild.default_role: PermissionOverwrite(send_messages=False)})

    for channel_name in "announcements", "orders-log", "maps":
        await _create_channel(name = channel_name, category=gm_channel_category,
            overwrites = {ctx.guild.default_role: PermissionOverwrite(send_messages = False)})

    orders_category = await _create_category(name="Orders",
        overwrites={ctx.guild.default_role: PermissionOverwrite(view_channel=False)})
    voids_category = await _create_category(name="Voids")
    for player in players:
        await _create_channel(name = f"{player.get_name().lower()}-orders", category=orders_category,
            overwrites = {ctx.guild.default_role: PermissionOverwrite(view_channel = False),
                          roles[f"orders-{player.name.lower()}"]: PermissionOverwrite(view_channel = True)})
        await _create_channel(name = f"{player.get_name().lower()}-void", category=voids_category,
            overwrites = {ctx.guild.default_role: PermissionOverwrite(view_channel = False),
                          roles["Spectator"]: PermissionOverwrite(view_channel = True, send_messages = False),
                          roles[player.name]: PermissionOverwrite(view_channel = True, pin_messages = True),
                          roles["cspec"]: PermissionOverwrite(send_messages = True, add_reactions = True)})

    for i in range(1, ceil(1.5 * len(players) * (len(players) - 1) / 100) + 1):
        comms_category = await _create_category(name=f"Comms {i}",
            overwrites = {roles["Player"]: PermissionOverwrite(manage_channels = True)})
        await _create_channel(name = f"comms-{i}", category=comms_category)

    log_command(logger, ctx, message="Categories and channels created")
    await send_message_and_file(channel=ctx.channel, message="Categories and channels created")
    await send_message_and_file(channel=ctx.channel, message="Server setup complete")

async def reset_server(ctx: commands.Context) -> None:
    """Resets roles and channels. Very dangerous and thus is superuser only."""
    assert ctx.guild is not None
    if "confirm" not in remove_prefix(ctx).lower():
        return

    player_names = {c.name[:-7] for c in ctx.guild.channels if c.name.endswith("-orders")}
    for category in ctx.guild.categories:
        if category.name.lower().startswith("comms ") or category.name.lower() in ("orders", "voids"):
            for channel in category.channels:
                await channel.delete()
            await category.delete()

    for role in ctx.guild.roles:
        if role.name.lower().replace("orders-", "") in player_names:
            await role.delete()
    log_command(logger, ctx, message="Deleted roles and channels")
    await send_message_and_file(channel=ctx.channel, message="Server reset complete")

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
