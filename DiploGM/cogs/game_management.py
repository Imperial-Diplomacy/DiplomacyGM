import asyncio
import logging
import random
import re
from typing import Optional

import discord.utils
from discord import (
    CategoryChannel,
    Member,
    User,
    PermissionOverwrite,
    Role,
    TextChannel,
    Thread,
    Guild,
)
from discord.abc import GuildChannel
from discord.ext import commands

from DiploGM import config
from DiploGM.config import ERROR_COLOUR, MAP_ARCHIVE_SAS_TOKEN
from DiploGM.models.board import Board
from DiploGM.parse_edit_state import parse_edit_state
from DiploGM.parse_board_params import parse_board_params
from DiploGM import perms
from DiploGM.utils import (
    get_orders,
    log_command,
    send_message_and_file,
    upload_map_to_archive,
)

from DiploGM.perms import is_gm
from DiploGM.db.database import get_connection
from DiploGM.models.extension import ExtensionEvent, SQLiteExtensionEventRepository
from DiploGM.models.order import Disband, Build
from DiploGM.models.player import Player
from DiploGM.manager import Manager, SEVERENCE_A_ID, SEVERENCE_B_ID

logger = logging.getLogger(__name__)
manager = Manager()


class GameManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.grace_repo = SQLiteExtensionEventRepository()

    @commands.command(
        brief="Create a game of Imp Dip and output the map.",
        description="Create a game of Imp Dip and output the map. (there are no other variant options at this time)",
    )
    @perms.gm_only("create a game")
    async def create_game(self, ctx: commands.Context) -> None:
        """Create a new initial game state tied to the server of invocation.

        Usage: 
            Used as `.create_game <gametype>`

        Note: 
            Limited to the server of command invocation
            Default for <gametype> is "impdip" (A2/B1)
            Valid <gametype> values can be found as folders in https://github.com/Imperial-Diplomacy/DiplomacyGM-Variants/tree/main

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """
        assert ctx.guild is not None
        gametype = ctx.message.content.removeprefix(f"{ctx.prefix}{ctx.invoked_with}")
        if gametype == "":
            gametype = "impdip"
        else:
            gametype = gametype.removeprefix(" ")

        message = manager.create_game(ctx.guild.id, gametype)
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)

    @commands.command(brief="permanently deletes a game, cannot be undone")
    @perms.gm_only("delete the game")
    async def delete_game(self, ctx: commands.Context) -> None:
        """Deletes all references to the game within the database

        Usage: 
            Used as `.delete_game`

        Note: 

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        manager.total_delete(ctx.guild.id)
        log_command(logger, ctx, message="Deleted game")
        await send_message_and_file(channel=ctx.channel, title="Deleted game")

    @commands.command(brief="lists all variants currently supported")
    @perms.gm_only("lists variants")
    async def list_variants(self, ctx: commands.Context) -> None:
        """Lists all variants currently loaded into the bot. To create a game of a specific variant, use `.create_game <variant>`

        Usage: 
            Used as `.list_variants`

        Note: 

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        message = manager.list_variants()
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, title="Currently loaded variants", message=message)

    @commands.command(brief="")
    @perms.gm_only("archive the category")
    async def archive(self, ctx: commands.Context) -> None:
        """Set all channels within a category to read-only, during game close

        Usage: 
            Used as `.archive #<channel_mention>`

        Note: 
            Removes all permission overwrites and sets "send_messages" to false
            Does not apply to Administrator roles

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
                This channel is not part of a category
        """

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

    def ping_player_builds(self, player: Player, users: set[discord.Member | discord.Role], build_anywhere: bool) -> str:
        user_str = ''.join([u.mention for u in users])

        count = len(player.centers) - len(player.units)
        current = player.waived_orders
        has_disbands = False
        has_builds = player.waived_orders > 0
        for order in player.build_orders:
            if isinstance(order, Disband):
                current -= 1
                has_disbands = True
            elif isinstance(order, Build):
                current += 1
                has_builds = True

        difference = abs(current - count)
        order_text = f"order{'s' if difference != 1 else ''}"

        if has_builds and has_disbands:
            return f"Hey {user_str}, you have both build and disband orders. Please get this looked at."

        if count < 0:
            if current < count:
                return f"Hey {user_str}, you have {difference} more disband {order_text} than necessary. Please get this looked at."
            elif current > count:
                return f"Hey {user_str}, you have {difference} less disband {order_text} than required. Please get this looked at."
            return ""

        available_centers = [
            center
            for center in player.centers
            if center.unit is None
            and (center.core == player or build_anywhere)
        ]
        available = min(len(available_centers), count)

        difference = abs(current - available)
        # We use count here in case someone waives builds
        if current > count:
            return f"Hey {user_str}, you have {difference} more build {order_text} than possible. Please get this looked at."
        elif current < available:
            return f"Hey {user_str}, you have {difference} less build {order_text} than necessary. Make sure that you want to waive."
        return ""

    @commands.command(
        brief="pings players who don't have the expected number of orders.",
        description="""Pings all players in their orders channel that satisfy the following constraints:
        1. They have too many build orders, or too little or too many disband orders. As of now, waiving builds doesn't lead to a ping.
        2. They are missing move orders or retreat orders.
        You may also specify a timestamp to send a deadline to the players.
        * .ping_players <timestamp>
        """,
        aliases=["pp"]
    )
    @perms.gm_only("ping players")
    async def ping_players(self, ctx: commands.Context) -> None:
        """Pings all players with withstanding orders, listing number of needed orders and which units require them

        Usage: 
            Used as `.ping_players <timestamp?>`

        Note: 
            Timestamp optional, will be formatted to "in XX hours" when displayed

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
                No player category found / No player role found
                No user found for player X
        """

        guild = ctx.guild
        assert guild is not None
        board = manager.get_board(guild.id)

        # extract deadline argument
        timestamp = re.match(
            r"<t:(\d+):[a-zA-Z]>",
            ctx.message.content.removeprefix(f"{ctx.prefix}{ctx.invoked_with}").strip(),
        )
        if timestamp:
            timestamp = f"<t:{timestamp.group(1)}:R>"

        # get abstract player information
        player_roles: set[Role] = set()
        for r in guild.roles:
            if config.is_player_role(r):
                player_roles.add(r)

        if len(player_roles) == 0:
            log_command(logger, ctx, message="No player role found")
            await send_message_and_file(
                channel=ctx.channel,
                message="No player category found",
                embed_colour=config.ERROR_COLOUR,
            )
            return

        player_categories: list[CategoryChannel] = []
        for c in guild.categories:
            if config.is_player_category(c):
                player_categories.append(c)

        if len(player_categories) == 0:
            log_command(logger, ctx, message="No player category found")
            await send_message_and_file(
                channel=ctx.channel,
                message="No player category found",
                embed_colour=config.ERROR_COLOUR,
            )
            return

        # ping required players
        pinged_players = 0
        failed_players = []
        response = ""
        for category in player_categories:
            for channel in category.text_channels:
                player = board.get_player_by_channel(channel)
                if player is None:
                    await ctx.send(f"No Player for {channel.name}")
                    continue

                role = player.find_discord_role(guild.roles)
                if role is None:
                    await ctx.send(f"No Role for {player.get_name()}")
                    continue

                if not board.is_chaos():
                    # Find users which have a player role to not ping spectators
                    users: set[Member | Role] = set(
                        filter(
                            lambda m: len(set(m.roles) & player_roles) > 0, role.members
                        )
                    )
                else:
                    users = {overwritter for overwritter, permission
                             in channel.overwrites.items()
                             if isinstance(overwritter, Member) and permission.view_channel}

                if len(users) == 0:
                    failed_players.append(player)

                    # HACK: ping role in case of no players
                    users.add(role)

                if board.turn.is_builds():
                    response = self.ping_player_builds(player, users, board.data.get("build_options") == "anywhere")
                else:
                    in_moves = lambda u: (u == u.province.dislodged_unit and len(u.retreat_options) > 0) or board.turn.is_moves()

                    missing = [
                        unit
                        for unit in player.units
                        if unit.order is None and in_moves(unit)
                    ]
                    unit_text = f"unit{'s' if len(missing) != 1 else ''}"
                    if not missing:
                        continue

                    response = f"Hey **{''.join([u.mention for u in users])}**, you are missing moves for the following {len(missing)} {unit_text}:"
                    for unit in sorted(
                        missing, key=lambda _unit: _unit.province.name
                    ):
                        response += f"\n{unit}"

                if response:
                    pinged_players += 1
                    if timestamp:
                        response += f"\n The orders deadline is {timestamp}."
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

    @commands.command(
        brief="disables orders until .unlock_orders is run.",
        description="""disables orders until .enable_orders is run.
                 Note: Currently does not persist after the bot is restarted""",
        aliases=["lock"],
    )
    @perms.gm_only("lock orders")
    async def lock_orders(self, ctx: commands.Context) -> None:
        """Sets board flag to prevent new order submissions

        Usage: 
            Used as `.lock_orders`

        Note: 

        Args:

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)
        board.orders_enabled = False
        log_command(logger, ctx, message="Locked orders")
        await send_message_and_file(
            channel=ctx.channel,
            title="Locked orders",
            message=f"{board.turn}",
        )

    @commands.command(brief="re-enables orders", aliases=["unlock"])
    @perms.gm_only("unlock orders")
    async def unlock_orders(self, ctx: commands.Context) -> None:
        """Sets board flag to enable new order submissions

        Usage: 
            Used as `.unlock_orders`

        Note: 

        Args:

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)
        board.orders_enabled = True
        log_command(logger, ctx, message="Unlocked orders")
        await send_message_and_file(
            channel=ctx.channel,
            title="Unlocked orders",
            message=f"{board.turn}",
        )

    @commands.group(name="grace", brief="", invoke_without_command=True)
    @perms.gm_only("handle graces")
    async def grace(self, ctx: commands.Context) -> None:
        """Entry point for Grace logging command group

        Usage: 
            Used as `.grace`

        Note: 
            # TODO: could maybe be made into a cog

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """
        await send_message_and_file(channel=ctx.channel, message="Valid commands are: *log*, *delete*, and *view*")

    @grace.command(name="log", brief="log grace", description="Usage: .grace <user> <hours> <reason>")
    @perms.gm_only("record a grace")
    async def grace_log(self, ctx: commands.Context, user: User, hours: int, *, reason: str = "Unspecified") -> None:
        """Store a record of grace in a game, grace can be NMR or Extension and should be detailed in the reason

        Usage: 
            Used as `.grace log <user> <hours> <reason>`

        Note: 
            Can't log for bots
            Can log for any discord user

        Args:
            ctx (commands.Context): Context from discord regarding command invocation
            user (discord.User): User that has committed the grace
            hours (int): Time grace lasted/set to last
            reason (str): Why was the grace stored

        Returns:
            None

        Raises:
            None:
            Messages:
                User is a bot!
        """
        assert ctx.guild is not None

        if user.bot:
            await send_message_and_file(channel=ctx.channel, message="Can't log grace for a bot", embed_colour=ERROR_COLOUR)
            return

        event = ExtensionEvent(
            user_id=user.id,
            server_id=ctx.guild.id,
            hours=hours,
            reason=reason
        )

        self.grace_repo.save(event)
        await send_message_and_file(channel=ctx.channel, title=f"Grace (No. {event.id}) logged!", message=f"Logged under: {user.mention}\nHours: {hours}")

    @grace.command(name="delete")
    @perms.gm_only("delete a recorded grace")
    async def grace_delete(self, ctx: commands.Context, id: int) -> None:
        """Delete a record of grace from the database

        Usage: 
            Used as `.grace delete <id>`

        Note: 
            Will return positive message even if no record for ID

        Args:
            ctx (commands.Context): Context from discord regarding command invocation
            id (int): Target Grace ID -> PK in Table

        Returns:
            None

        Raises:
            None:
            Messages:
        """
        self.grace_repo.delete(id)
        await send_message_and_file(channel=ctx.channel, message=f"If a grace with ID {id} existed, it exists no longer :fire:")

    @grace.group(name="view", invoke_without_command=True)
    async def grace_view(self, ctx: commands.Context) -> None:
        """Entry point for Grace log viewing command group

        Usage: 
            Used as `.grace view`

        Note: 

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """
        await send_message_and_file(channel=ctx.channel, message="Valid commands are: *user* and *server*")

    @grace_view.command(name="user", brief="View the grace history of a user")
    @perms.gm_only("view graces made by a user")
    async def grace_view_user(self, ctx: commands.Context, user: User) -> None:
        """View the grace record for a specific user

        Usage: 
            Used as `.grace view user <user>`

        Note: 
            Groups by server graces are logged in
            Records sorted by server_id (newer servers?) then creation datetime

        Args:
            ctx (commands.Context): Context from discord regarding command invocation
            user (discord.User): User to check

        Returns:
            None

        Raises:
            None:
            Messages:
        """
        events = self.grace_repo.load_by_user(user.id)

        handled_servers = set()
        out = ""
        for e in sorted(events, key=lambda e: (e.server_id, e.created_at), reverse=True):
            if e.server_id not in handled_servers:
                server = self.bot.get_guild(e.server_id)
                identifier = server.name if server else f"Guild {e.server_id}"
                out += f"### For: {identifier}\n"
                handled_servers.add(e.server_id)

            out += f"ID({e.id}):  {user.mention}\n"
            out += f"- Hours: {e.hours}\n"
            out += f"- Reason: {e.reason}\n"
            out += f"- Time: {e.created_at}\n"

        if len(events) == 0:
            out = "None logged, this is a good user!"

        await send_message_and_file(channel=ctx.channel, title=f"Graces caused by {user.name}", message=out)

    @grace_view.command(name="server", brief="View the grace history of a server")
    @perms.gm_only("view graces that have occurred in a server")
    async def grace_view_server(self, ctx: commands.Context, id: Optional[int] = None) -> None:
        """View the grace record for the current server

        Usage: 
            Used as `.grace view server <id>`

        Note: 
            Groups by server graces are logged in
            Records sorted by server_id (newer servers?) then creation datetime

        Args:
            ctx (commands.Context): Context from discord regarding command invocation
            id (Optional[int], default=None): ID of the server to view

        Returns:
            None

        Raises:
            None:
            Messages:
                Invalid guild ID
        """
        assert ctx.guild is not None

        gname = ctx.guild.name
        guildid = ctx.guild.id
        if id is not None:
            try:
                guild = self.bot.fetch_guild(id)
                gname = guild.name
                guildid = id
            except discord.HTTPException:
                gname = str(id)
                await send_message_and_file(channel=ctx.channel, message="Could not find that guild object", embed_colour=ERROR_COLOUR)

        events = self.grace_repo.load_by_server(guildid)
        out = ""
        if len(events) == 0:
            out = "This server is yet to have a grace! Congratulations!"
        else:
            for e in sorted(events, key=lambda e: e.created_at, reverse=True):
                user = self.bot.get_user(e.user_id)
                out += f"ID({e.id}):  {user.mention}\n"
                out += f"- Hours: {e.hours}\n"
                out += f"- Reason: {e.reason}\n"
                out += f"- Time: {e.created_at}\n"

        await send_message_and_file(channel=ctx.channel, title=f"Graces in {gname}", message=out)

    @commands.command(brief="Clears all players orders.")
    @perms.gm_only("remove all orders")
    async def remove_all(self, ctx: commands.Context) -> None:
        """Remove all currently submitted orders from the board

        Usage: 
            Used as `.remove_all`

        Note: 
            Removes first from the board object and then from the database

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)
        for unit in board.units:
            unit.order = None

        database = get_connection()
        database.save_order_for_units(board, board.units)
        log_command(logger, ctx, message="Removed all Orders")
        await send_message_and_file(channel=ctx.channel, title="Removed all Orders")

    async def _post_orders(self, ctx: commands.Context, board: Board) -> str:
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
            await send_message_and_file(
                channel=ctx.channel,
                title="Unknown Error: Please contact your local bot dev",
                embed_colour=config.ERROR_COLOUR,
            )
            return
        orders_log_channel = get_orders_log(ctx.guild)
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
            return

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

    async def _ping_phase_change(self, guild: Guild, board: Board, log_url: str) -> None:
        curr_board = manager.get_board(guild.id)

        extra_info = {}
        if curr_board.turn.is_retreats():
            for player in curr_board.players:
                units_to_retreat = sorted([str(u) for u in player.units if len(u.retreat_options or []) > 0])
                if len(units_to_retreat) > 0:
                    extra_info[player.name] = "**Units to retreat**:\n" + '\n'.join(units_to_retreat)
        elif (curr_board.turn.is_builds()
              and (old_board := manager._database.get_old_board(board, board.turn.get_previous_turn())) is not None):
            for player in curr_board.players:
                old_player = old_board.get_player(player.name)
                if not old_player:
                    continue
                extra_info[player.name] = ""
                current_centers = {str(c) for c in player.centers}
                old_centers = {str(c) for c in old_player.centers}
                centers_gained = current_centers - old_centers
                if len(centers_gained) > 0:
                    centers_gained = sorted([str(c) for c in centers_gained])
                    extra_info[player.name] = "**Centers gained**:\n" + '\n'.join(centers_gained)
                centers_lost = old_centers - current_centers
                if len(centers_lost) > 0:
                    centers_lost = sorted([str(c) for c in centers_lost])
                    extra_info[player.name] += "\n**Centers lost**:\n" + '\n'.join(centers_lost)

        player_categories = [c for c in guild.categories if config.is_player_category(c)]

        for c in player_categories:
            for ch in c.text_channels:
                player = board.get_player_by_channel(ch)
                if not player or (len(player.units) + len(player.centers) == 0):
                    continue

                additional_info = extra_info.get(player.name, "")
                out = "The game has adjudicated!\n"
                await ch.send(out, silent=True)
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

    @commands.command(
        brief="Sends all previous orders",
        description="For GM: Sends orders from previous phase to #orders-log",
    )
    @perms.gm_only("publish orders")
    async def publish_orders(self, ctx: commands.Context, *args) -> None:
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
        log_url = await self._post_orders(ctx, board)

        # HACK: Lifted from .ping_players
        # Should really work its way into a util function
        if "silent" not in arguments:
            _ = asyncio.create_task(self._ping_phase_change(guild, board, log_url))

        if MAP_ARCHIVE_SAS_TOKEN:
            file, _ = manager.draw_map_for_board(board, draw_moves=True)
            _ = asyncio.create_task(upload_map_to_archive(ctx, guild.id, board, file))

    @commands.command(
        brief="Adjudicates the game and outputs the moves and results maps.",
        description="""
        GMs may append true as an argument to this command to instead get the base svg file.
        * adjudicate {arguments}
        Arguments: 
        * pass true|t|svg|s to return an svg
        * pass standard, dark, blue, or pink for different color modes if present
        * pass test to view maps without doing an actual adjudication
        * pass full to automatically publish orders and maps
        """,
        aliases=["adju", "adjudication"]
    )
    @perms.gm_only("adjudicate")
    async def adjudicate(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        assert guild is not None

        board = manager.get_board(guild.id)

        arguments = (
            ctx.message.content.removeprefix(f"{ctx.prefix}{ctx.invoked_with}")
            .strip()
            .lower()
            .split()
        )
        return_svg = not ({"true", "t", "svg", "s"} & set(arguments))
        color_arguments = list(config.color_options & set(arguments))
        color_mode = color_arguments[0] if color_arguments else None
        test_adjudicate = "test" in arguments
        full_adjudicate = "full" in arguments
        movement_adjudicate = "movement" in arguments

        if test_adjudicate and full_adjudicate:
            await send_message_and_file(
                channel=ctx.channel,
                title="Test and full adjudications are incompatable. Defaulting to test adjudication.",
                embed_colour=config.PARTIAL_ERROR_COLOUR,
            )
            full_adjudicate = False

        if full_adjudicate:
            await self.lock_orders(ctx)

        old_turn = board.turn
        new_board = manager.adjudicate(guild.id, test=test_adjudicate)

        log_command(
            logger,
            ctx,
            message=f"Adjudication Successful for {board.turn}",
        )
        file, file_name = manager.draw_map(
            guild.id,
            draw_moves=True,
            player_restriction=None,
            color_mode=color_mode,
            turn=old_turn,
        )
        title = f"{board.name} — " if board.name else ""
        title += f"{old_turn}"
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{title} Orders Map",
            message="Test adjudication" if test_adjudicate else "",
            file=file,
            file_name=file_name,
            convert_svg=return_svg,
        )
        if full_adjudicate and (map_channel := get_maps_channel(guild)):
            map_message = await send_message_and_file(
                channel=map_channel,
                title=f"{title} Orders Map",
                file=file,
                file_name=file_name,
                convert_svg=True,
            )
            try:
                await map_message.publish()
            except:
                pass

        if movement_adjudicate:
            file, file_name = manager.draw_map(
                guild.id,
                draw_moves=True,
                player_restriction=None,
                color_mode=color_mode,
                turn=old_turn,
                movement_only=True,
            )
            title = f"{board.name} — " if board.name else ""
            title += f"{old_turn}"
            await send_message_and_file(
                channel=ctx.channel,
                title=f"{title} Movement Map",
                message="Test adjudication" if test_adjudicate else "",
                file=file,
                file_name=file_name,
                convert_svg=return_svg,
            )

        file, file_name = manager.draw_map_for_board(new_board, color_mode=color_mode)
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{title} Results Map",
            message="Test adjudication results" if test_adjudicate else "",
            file=file,
            file_name=file_name,
            convert_svg=return_svg,
        )

        if full_adjudicate and (map_channel := get_maps_channel(guild)):
            map_message = await send_message_and_file(
                channel=map_channel,
                title=f"{title} Results Map",
                file=file,
                file_name=file_name,
                convert_svg=True,
            )      
            try:
                await map_message.publish()
            except:
                pass
        
        if full_adjudicate:
            await self.publish_orders(ctx)
            await self.unlock_orders(ctx)

        # NOTE: Temporary for Meme's Severence Diplomacy Event
        if guild.id in [SEVERENCE_A_ID, SEVERENCE_B_ID]:
            seva = self.bot.get_guild(SEVERENCE_A_ID)
            sevb = self.bot.get_guild(SEVERENCE_B_ID)
            
            seva_player = discord.utils.find(lambda r: r.name == "Player", seva.roles)
            aperms = seva_player.permissions
            sevb_player = discord.utils.find(lambda r: r.name == "Player", sevb.roles)
            bperms = sevb_player.permissions

            a_allowed = ("Spring" in new_board.turn.get_phase()
                        or ("Winter" in new_board.turn.get_phase()
                            and random.choice([0, 1]) == 0))
            await send_message_and_file(channel=ctx.channel, message=f"Game {'A' if a_allowed else 'B'} is permitted to play.")
            aperms.update(send_messages=a_allowed)
            bperms.update(send_messages=(not a_allowed))

        # AUTOMATIC SCOREBOARD OUTPUT FOR DATA SPREADSHEET
        if new_board.turn.is_builds() and (guild.id != config.BOT_DEV_SERVER_ID and guild.name.startswith("Imperial Diplomacy")) and not test_adjudicate:
            channel = self.bot.get_channel(config.IMPDIP_SERVER_WINTER_SCOREBOARD_OUTPUT_CHANNEL_ID)
            if not channel:
                await send_message_and_file(channel=ctx.channel, message="Couldn't automatically send off the Winter Scoreboard data", embed_colour=config.ERROR_COLOUR)
                return
            title = f"### {guild.name} Centre Counts (alphabetical order) | {new_board.turn}"

            players = sorted(new_board.players, key=lambda p: p.get_name())
            counts = "\n".join(map(lambda p: str(len(p.centers)), players))

            await channel.send(title)
            await channel.send(counts)

    @commands.command(brief="Rolls back to the previous game state.")
    @perms.gm_only("rollback")
    async def rollback(self, ctx: commands.Context) -> None:
        """Rolls back the game board to the previous phase

        Usage: 
            Used as `.rollback`

        Note: 
            Limited to the server of command invocation

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
                No board for the previous phase
        """

        assert ctx.guild is not None
        message, file, file_name = manager.rollback(ctx.guild.id)
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message, file=file, file_name=file_name)

    @commands.command(brief="Reloads the current board with what is in the DB")
    @perms.gm_only("reload")
    async def reload(self, ctx: commands.Context) -> None:
        """Reloads the board state currently saved in the database

        Usage: 
            Used as `.reload`

        Note: 
            Limited to the server of command invocation

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        message, file, file_name = manager.reload(ctx.guild.id)
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message, file=file, file_name=file_name)

    @commands.command(
        brief="Edits the game state and outputs the results map.",
        description="""Edits the game state and outputs the results map. 
        There must be one and only one command per line.
        Note: you cannot edit immalleable map state (eg. province adjacency).
        The following are the supported sub-commands:
        * set_phase {spring, fall, winter}_{moves, retreats, builds}
        * set_core <province_name> <player_name>
        * set_half_core <province_name> <player_name>
        * set_province_owner <province_name> <player_name>
        * set_player_color <player_name> <hex_code>
        * create_unit {A, F} <player_name> <province_name>
        * create_dislodged_unit {A, F} <player_name> <province_name> <retreat_option1> <retreat_option2>...
        * delete_dislodged_unit <province_name>
        * delete_unit <province_name>
        * move_unit <province_name> <province_name>
        * dislodge_unit <province_name> <retreat_option1> <retreat_option2>...
        * make_units_claim_provinces {True|(False) - whether or not to claim SCs}
        * .create_player <player_name> <color_code> <win_type> <vscc> <iscc> {extends into the game's history, no starting centres/units}
        * .delete_player <player_name>
        * set_player_points <player_name> <integer>
        * set_player_vassal <liege> <vassal>
        * remove_relationship <player1> <player2>
        * set_game_name <game_name>
        * load_state <server_id> <spring, fall, winter}_{moves, retreats, builds> <year>
        * apocalypse {all OR army, fleet, core, province} !!! deletes everything specified !!!
        * bulk <command> {<player_name> | nothing if you're using delete_units} <list_of_province_names> {use with commands like set_total_owner to use it repeatedly}
        * bulk_create_units <player_name> {A, F} <list_of_province_names>
        """,
    )
    @perms.gm_only("edit")
    async def edit(self, ctx: commands.Context) -> None:
        """God edit the board state

        Usage: 
            Used as `.edit <commands>`

        Note: 
            Outsources to `parse_edit_state.py`

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """
        assert ctx.guild is not None
        edit_commands = ctx.message.content.removeprefix(
            f"{ctx.prefix}{ctx.invoked_with}"
        ).strip()
        title, message, file, file_name, embed_colour = parse_edit_state(edit_commands, manager.get_board(ctx.guild.id))
        log_command(logger, ctx, message=title)
        await send_message_and_file(channel=ctx.channel, title=title, message=message, file=file, file_name=file_name, embed_colour=embed_colour)

    @commands.command(
        brief="blitz",
        description="Creates all possible channels between two players for blitz in available comms channels.",
    )
    @perms.gm_only("create blitz comms channels")
    async def blitz(self, ctx: commands.Context) -> None:
        """Creates all pairwise press channels between players in a game

        Usage: 
            Used as `.botsay #channel message`

        Note: 
            Uses the board.players list (which is read from the config)

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)
        cs = []
        pla = sorted(board.players, key=lambda p: p.get_name())
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
        for player in board.players:
            name_to_player[player.get_name().lower()] = player

        spectator_role = None

        for role in guild.roles:
            if role.name.lower() == "spectator":
                spectator_role = role

            player = name_to_player.get(role.name.lower())
            if player:
                player_to_role[player] = role

        if spectator_role == None:
            await send_message_and_file(
                channel=ctx.channel, message="Missing spectator role"
            )
            return

        for player in board.players:
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

            overwrites = {
                guild.default_role: PermissionOverwrite(view_channel=False),
                spectator_role: PermissionOverwrite(view_channel=True),
                player_to_role[p1]: PermissionOverwrite(view_channel=True),
                player_to_role[p2]: PermissionOverwrite(view_channel=True),
            }

            await current_cat.create_text_channel(name, overwrites=overwrites)

            available -= 1

    @commands.command(brief="publicize void for chaos")
    async def publicize(self, ctx: commands.Context) -> None:
        """Opens a channel (usually a void) to the spectator role

        Usage: 
            Used as `.publicize`

        Note: 
            Used exclusively for the World of Chaos event

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
                You are not a GM
                This is not a chaos game
                Could not find applicable user
        """
        assert ctx.guild is not None
        if not is_gm(ctx.message.author):
            raise PermissionError(
                "You cannot publicize a void because you are not a GM."
            )

        channel = ctx.channel
        assert isinstance(channel, TextChannel)
        board = manager.get_board(ctx.guild.id)

        if not board.is_chaos():
            await send_message_and_file(
                channel=channel,
                message="This command only works for chaos games.",
                embed_colour=config.ERROR_COLOUR,
            )

        player = board.get_player_by_channel(
            channel, ignore_category=True
        )

        # TODO hacky
        users = []
        user_permissions: list[tuple[Member, PermissionOverwrite]] = []
        # Find users with access to this channel
        for overwritter, user_permission in channel.overwrites.items():
            if isinstance(overwritter, Member) and user_permission.view_channel:
                users.append(overwritter)
                user_permissions.append((overwritter, user_permission))

        # TODO don't hardcode
        staff_role = None
        spectator_role = None
        for role in ctx.guild.roles:
            if role.name == "World Chaos Staff":
                staff_role = role
            elif role.name == "Spectators":
                spectator_role = role

        if not staff_role or not spectator_role:
            return

        if not player or len(users) == 0:
            await send_message_and_file(
                channel=ctx.channel,
                message="Can't find the applicable user.",
                embed_colour=config.ERROR_COLOUR,
            )
            return

        # Create Thread
        thread: Thread = await channel.create_thread(
            name=f"{player.get_name().capitalize()} Orders",
            reason=f"Creating Orders for {player.get_name()}",
            invitable=False,
        )
        await thread.send(
            f"{''.join([u.mention for u in users])} | {staff_role.mention}"
        )

        # Allow for sending messages in thread
        for user, permission in user_permissions:
            permission.send_messages_in_threads = True
            await channel.set_permissions(target=user, overwrite=permission)

        # Add spectators
        spectator_permissions = PermissionOverwrite(
            view_channel=True, send_messages=False
        )
        await channel.set_permissions(
            target=spectator_role, overwrite=spectator_permissions
        )

        # Update name
        await channel.edit(name=channel.name.replace("orders", "void"))

        await send_message_and_file(
            channel=channel, message="Finished publicizing void."
        )

    @commands.command(
        brief="edit_game",
        description="""Modifies a game parameter to a certain value.
        There must be one and only one command per line.
        Note: you cannot edit immalleable map state (eg. province adjacency, players).
        The following are the supported parameters and possible values:
        * building ['classic', 'cores', 'anywhere']
        * victory_conditions ['classic', 'vscc']
        * victory_count [number] (only used with classic victory conditions)
        * iscc [player] [starting scs]
        * vscc [player] [victory scs] (only used with vscc victory conditions)
        * player_name [original name] [new name]
        * hide_player [player] ['true', 'false']
        * add_player [player] [color] (Once added, a player cannot be removed)
        """,
    )
    @perms.gm_only("edit game")
    async def edit_game(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        param_commands = ctx.message.content.removeprefix(
            f"{ctx.prefix}{ctx.invoked_with}"
        ).strip()
        title, message, file, file_name, embed_colour = parse_board_params(param_commands, manager.get_board(ctx.guild.id))
        log_command(logger, ctx, message=title)
        await send_message_and_file(channel=ctx.channel, title=title, message=message, file=file, file_name=file_name, embed_colour=embed_colour)

async def setup(bot):
    cog = GameManagementCog(bot)
    await bot.add_cog(cog)


def get_maps_channel(guild: Guild) -> TextChannel | None:
    for channel in guild.channels:
        if (
            channel.name.lower() == "maps"
            and channel.category is not None
            and channel.category.name.lower() == "gm channels"
            and isinstance(channel, TextChannel)
        ):
            return channel
    return None


def get_orders_log(guild: Guild) -> TextChannel | None:
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
