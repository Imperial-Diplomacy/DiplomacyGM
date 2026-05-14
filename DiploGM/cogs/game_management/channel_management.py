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
    assert ctx.guild is not None
    gametype = remove_prefix(ctx) or "classic"
    try:
        board = get_parser(gametype).parse()
    except ValueError as e:
        message = str(e)
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)
        return

    players = sorted(list(board.players), key=lambda p: p.get_name())
    player_roles = {}
    order_roles = {}

    if (country_spectator_role := discord.utils.get(ctx.guild.roles, name="Country Spectator")) is None:
        country_spectator_role = await ctx.guild.create_role(name = "Country Spectator",
                                                             color=discord.Color.from_str("#96dfff"))
    for player in players:
        if (cur_player_role := discord.utils.get(ctx.guild.roles, name = player.get_name())) is None:
            color = discord.Color.from_str(f"#{player.default_color}")
            cur_player_role = await ctx.guild.create_role(name = player.get_name(), color = color,
                                                          mentionable = True, hoist = True)
        player_roles[player.name] = cur_player_role
    if not discord.utils.get(ctx.guild.roles, name="Dead"):
        await ctx.guild.create_role(name = "Dead", color = discord.Color.from_str("#0b2f68"), hoist = True)
    if (player_role := discord.utils.get(ctx.guild.roles, name="Player")) is None:
        player_role = await ctx.guild.create_role(name = "Player",
                                                  permissions = discord.Permissions(send_messages=True,
                                                                                    add_reactions=True))
    for player in players:
        role_name = f"orders-{player.get_name().lower()}"
        if (cur_order_role := discord.utils.get(ctx.guild.roles, name=role_name)) is None:
            cur_order_role = await ctx.guild.create_role(name = role_name)
        order_roles[player.name] = cur_order_role
    if (spectator_role := discord.utils.get(ctx.guild.roles, name="Spectator")) is None:
        spectator_role = await ctx.guild.create_role(name = "Spectator",
                                                     color = discord.Color.from_str("#2ecc71"), hoist = True)
    log_command(logger, ctx, message="Created roles for all players and spectators")
    await send_message_and_file(channel=ctx.channel, message="Roles created for all players and spectators")

    categories = {category.name for category in ctx.guild.categories}
    if (gm_channel_category := discord.utils.get(ctx.guild.categories, name="GM Channels")) is None:
        gm_channel_category = await ctx.guild.create_category(name = "GM Channels",
            overwrites = {ctx.guild.default_role: PermissionOverwrite(send_messages = False)})
    if (orders_category := discord.utils.get(ctx.guild.categories, name="Orders")) is None:
        orders_category = await ctx.guild.create_category(name = "Orders",
            overwrites = {ctx.guild.default_role: PermissionOverwrite(view_channel = False)})
    if (voids_category := discord.utils.get(ctx.guild.categories, name="Voids")) is None:
        voids_category = await ctx.guild.create_category(name = "Voids")
    for i in range(1, ceil(1.5 * len(players) * (len(players) - 1) / 100) + 1):
        if f"Comms {i}" not in categories:
            await ctx.guild.create_category(name = f"Comms {i}",
                overwrites = {player_role: PermissionOverwrite(manage_channels = True)})

    gm_channel_names = {channel.name for channel in gm_channel_category.text_channels}
    for channel_name in "announcements", "orders-log", "maps":
        if channel_name not in gm_channel_names:
            await gm_channel_category.create_text_channel(name = channel_name,
                overwrites = {ctx.guild.default_role: PermissionOverwrite(send_messages = False)})
    order_channel_names = {channel.name for channel in orders_category.text_channels}
    for player in players:
        if (order_channel := f"{player.get_name().lower()}-orders") not in order_channel_names:
            await orders_category.create_text_channel(name = order_channel,
                overwrites = {ctx.guild.default_role: PermissionOverwrite(view_channel = False),
                              order_roles[player.name]: PermissionOverwrite(view_channel = True)})
    void_channel_names = {channel.name for channel in voids_category.text_channels}
    for player in players:
        if (void_channel := f"{player.get_name().lower()}-void") not in void_channel_names:
            await voids_category.create_text_channel(name = void_channel,
                overwrites = {ctx.guild.default_role: PermissionOverwrite(view_channel = False),
                              spectator_role: PermissionOverwrite(view_channel = True, send_messages = False),
                              player_roles[player.name]: PermissionOverwrite(view_channel = True, pin_messages = True),
                              country_spectator_role: PermissionOverwrite(send_messages = False, add_reactions = True)})

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
