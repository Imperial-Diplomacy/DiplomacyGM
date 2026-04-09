import logging
from typing import Callable, Iterable

import discord
from discord.ext import commands

from DiploGM import config
from DiploGM import perms
from DiploGM.db.database import get_connection
from DiploGM.parse_order import parse_order, parse_remove_order
from DiploGM.utils import get_orders, log_command, parse_season, send_message_and_file
from DiploGM.utils.sanitise import get_colour_option, remove_prefix
from DiploGM.manager import Manager, SEVERENCE_A_ID, SEVERENCE_B_ID
from DiploGM.models.player import ForcedDisbandOption, Player, ViewOrdersTags, OrdersSubsetOption
from DiploGM.utils.send_message import ErrorMessage, send_error, send_orders_locked_error

logger = logging.getLogger(__name__)
manager = Manager()

MISSING_ALIASES = ["missing", "miss", "m"]
SUBMITTED_ALIASES = ["submitted", "submit", "sub", "s"]
BLIND_ALIASES = ["blind", "b"]
FORCED_RETREAT_ALIASES = ["forced-disband", "forced", "force", "disband", "pop", "f"]
FREE_RETREAT_ALIASES = ["free-retreats", "free-retreat", "free", "retreats", "retreat", "r"]

class PlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        brief="Submits orders; there must be one and only one order per line.",
        description="""Submits orders:
    There must be one and only one order per line.
    A variety of keywords are supported: e.g. '-', '->', 'move', and 'm' are all supported for a move command.
    Supplying the unit type is fine but not required: e.g. 'A Ghent -> Normandy' and 'Ghent -> Normandy' are the same
    If anything in the command errors, we recommend resubmitting the whole order message.
    *During Build phases only*, you have to specify multi-word provinces with underscores; e.g. Somali Basin would be Somali_Basin (we use a different parser during build phases)
    If you would like to use something that is not currently supported please inform your GM and we can add it.""",
        aliases=["o", "orders"],
    )
    @perms.player("order")
    async def order(
        self,
        ctx: commands.Context,
        player: Player | None,
    ) -> None:
        """Submits orders; there must be one and only one order per line."""
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        if player and not board.orders_enabled:
            log_command(logger, ctx, "Orders locked - not processing")
            await send_orders_locked_error(ctx.channel)
            return

        message = parse_order(ctx.message.content, player, board)
        if "title" in message:
            log_command(logger, ctx, message=message["title"], level=logging.DEBUG)
        elif "message" in message:
            log_command(
                logger, ctx, message=message["message"][:100], level=logging.DEBUG
            )
        elif "messages" in message and len(message["messages"]) > 0:
            log_command(
                logger, ctx, message=message["messages"][0][:100], level=logging.DEBUG
            )
        await send_message_and_file(channel=ctx.channel, **message)

    @commands.command(
        brief="Removes orders for given units.",
        description="Removes orders for given units (required for removing builds/disbands). "
        "There must be one and only one order per line.",
        aliases=["remove", "rm", "removeorders"],
    )
    @perms.player("remove orders")
    async def remove_order(self, ctx: commands.Context, player: Player | None) -> None:
        """Removes orders for given units; there must be one and only one order per line."""
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        if player and not board.orders_enabled:
            log_command(logger, ctx, "Orders locked - not processing")
            await send_orders_locked_error(ctx.channel)
            return

        content = remove_prefix(ctx)

        message = parse_remove_order(content, player, board)
        log_command(logger, ctx, message=message["message"])
        await send_message_and_file(channel=ctx.channel, **message)

    @commands.command(brief="Clears all players orders.")
    @perms.player("remove all orders")
    async def remove_all(self, ctx: commands.Context, player: Player | None) -> None:
        """Remove all currently submitted orders from the board

        Usage: 
            Used as `.remove_all`

        Note: 
            Removes first from the board object and then from the database
            Use in a GM Channel will remove all orders globally
            Use in a Player Channel will remove all orders for that player

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

        if player is None:
            for unit in board.units:
                unit.order = None
        else:
            for unit in filter(lambda u: u.player == player, board.units):
                unit.order = None

        database = get_connection()
        database.save_order_for_units(board, board.units)
        log_command(logger, ctx, message="Removed all Orders")
        await send_message_and_file(channel=ctx.channel, title="Removed all Orders")

    @commands.command(
        brief="Outputs your current submitted orders.",
        description=f"""Outputs your current submitted orders.
        Use .view_map to view a sample moves map of your orders. 
        Use the 'missing' or 'submitted' argument to view only units without orders or only submitted orders. 
        \tAliases: {MISSING_ALIASES}; {SUBMITTED_ALIASES}
        Use the 'blind' argument to view only the number of orders submitted.
        \tAliases: {BLIND_ALIASES}
        Use the 'forced-disband' argument to view how many dislodged units have no valid retreat locations and must disband. (Only in retreat phases)
        \t Aliases: {FORCED_RETREAT_ALIASES}
        Alternatively, use the 'free-retreat' argument to view only dislodged units which are able to retreat. (Only in retreat phases)
        \tAliases: {FREE_RETREAT_ALIASES}""",
        aliases=["v", "view", "vieworders", "view-orders"],
    )
    @perms.player("view orders")
    async def view_orders(self, ctx: commands.Context, player: Player | None) -> None:
        """Outputs your current submitted orders."""
        assert ctx.guild is not None
        arguments = remove_prefix(ctx).lower().split()

        any_alias_in_args: Callable[[Iterable[str]], bool] = lambda aliases: 0 < len(set(arguments).intersection(set(aliases)))

        tags = ViewOrdersTags(
            subset=OrdersSubsetOption.MISSING if any_alias_in_args(MISSING_ALIASES)
                else OrdersSubsetOption.SUBMITTED if any_alias_in_args(SUBMITTED_ALIASES)
                else OrdersSubsetOption.FULL,
            blind=any_alias_in_args(BLIND_ALIASES),
            forced=ForcedDisbandOption.MARK_FORCED if any_alias_in_args(FORCED_RETREAT_ALIASES)
                else ForcedDisbandOption.ONLY_FREE if any_alias_in_args(FREE_RETREAT_ALIASES)
                else ForcedDisbandOption.UNMARKED,
        )

        try:
            board = manager.get_board(ctx.guild.id)
            order_text = get_orders(board, player, ctx, tags=tags)

        except RuntimeError as err:
            logger.error(err, exc_info=True)
            log_command(
                logger,
                ctx,
                message="Failed for an unknown reason",
                level=logging.ERROR,
            )
            await send_error(ctx.channel, ErrorMessage.UNKNOWN_ERROR)
            return
        log_command(
            logger,
            ctx,
            message=f"Success - generated orders for {board.turn}",
        )
        assert isinstance(order_text, str)
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{board.turn}",
            message=order_text,
        )

    async def _fetch_maps(self, ctx: commands.Context, player: Player | None, show_moves: bool = False):
        assert ctx.guild is not None
        arguments = remove_prefix(ctx).lower().split()
        convert_svg = (player is not None) or not (
            {"true", "t", "svg", "s"} & set(arguments)
        )   
        board = manager.get_board(ctx.guild.id)
        args = {"color_mode": get_colour_option(board, arguments),
                "movement_only": "movement" in arguments,
                "turn": parse_season(arguments, board.turn),
                "is_severance": ctx.guild.id in [SEVERENCE_A_ID, SEVERENCE_B_ID]}

        if player and show_moves and not board.orders_enabled:
            log_command(logger, ctx, "Orders locked - not processing")
            await send_orders_locked_error(ctx.channel)
            return

        try:
            if board.data.get("fow", "disabled") != "enabled":
                file, file_name = manager.draw_map(
                    ctx.guild.id,
                    draw_moves = show_moves,
                    player_restriction = player,
                    args = args,
                )
            elif show_moves:
                file, file_name = manager.draw_fow_players_moves_map(
                    ctx.guild.id, player, args=args
                )
            else:
                file, file_name = manager.draw_fow_current_map(
                    ctx.guild.id, player, args=args
                )
        except Exception as err:
            logger.error(err, exc_info=True)
            log_command(
                logger,
                ctx,
                message="Failed to generate map for an unknown reason",
                level=logging.ERROR,
            )
            await send_error(ctx.channel, ErrorMessage.UNKNOWN_ERROR)
            return

        message = None
        if {"true", "t"} & set(arguments):
            message = ("`.vm true` and `.vm t` have been deprecated and will soon be disabled.\n"
                       "Please use `.vm svg` instead")

        log_command(
            logger,
            ctx,
            message=f"Generated {'moves' if show_moves else 'current'} map for {args.get('turn', board.turn)}",
        )
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{args.get('turn', board.turn)} {'Orders' if show_moves else 'Current'} Map",
            message=message,
            file=file,
            file_name=file_name,
            convert_svg=convert_svg,
            file_in_embed=False,
        )

    @commands.command(
        brief="Outputs the current map with submitted orders.",
        description="""
        For GMs, all submitted orders are displayed. For a player, only their own orders are displayed.
        GMs may append true as an argument to this to instead get the svg.
        * view_map {arguments}
        Arguments: 
        * pass true|t|svg|s to return an svg
        * pass standard, dark, blue, or pink for different color modes if present, or custom for manually configured colours
        * pass season and optionally year for older maps
        """,
        aliases=["viewmap", "vm"],
    )
    @perms.player("view map")
    async def view_map(self, ctx: commands.Context, player: Player | None):
        """Outputs the current map with submitted orders."""
        await self._fetch_maps(ctx, player, show_moves=True)

    @commands.command(
        brief="Outputs the current map without any orders.",
        description="""
        * view_current {arguments}
        Arguments: 
        * pass true|t|svg|s to return an svg
        * pass standard, dark, blue, or pink for different color modes if present
        """,
        aliases=["viewcurrent", "vc"],
    )
    @perms.player("view current")
    async def view_current(self, ctx: commands.Context, player: Player | None) -> None:
        """Outputs the current map without any orders."""
        await self._fetch_maps(ctx, player, show_moves=False)

    @commands.command(
        brief="Outputs an interactive svg that you can issue orders in",
        aliases=["g"],
    )
    @perms.player("view gui")
    async def view_gui(self, ctx: commands.Context, player: Player | None) -> None:
        """Outputs an interactive svg that you can issue orders in."""
        assert ctx.guild is not None
        arguments = remove_prefix(ctx).lower().split()
        board = manager.get_board(ctx.guild.id)
        color_mode = get_colour_option(board, arguments)

        if player and not board.orders_enabled:
            log_command(logger, ctx, "Orders locked - not processing")
            await send_orders_locked_error(ctx.channel)
            return

        try:
            if board.data.get("fow", "disabled") != "enabled":
                file, file_name = manager.draw_gui_map(
                    ctx.guild.id, color_mode=color_mode
                )
            else:
                file, file_name = manager.draw_fow_gui_map(
                    ctx.guild.id, player_restriction=player, color_mode=color_mode
                )
        except Exception as err:
            log_command(
                logger,
                ctx,
                message="Failed to generate map for an unknown reason",
                level=logging.ERROR,
            )
            await send_error(ctx.channel, ErrorMessage.UNKNOWN_ERROR)
            raise err
        log_command(
            logger,
            ctx,
            message=f"Generated current map for {board.turn}",
        )
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{board.turn}",
            file=file,
            file_name=file_name,
            convert_svg=False,
            file_in_embed=False,
        )

    @commands.command(brief="outputs the provinces you can see")
    @perms.player("view visible provinces")
    async def visible_provinces(
        self, ctx: commands.Context, player: Player | None
    ) -> None:
        """Outputs the provinces you can see. Used for FoW games."""
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        if not player or board.data.get("fow", "disabled") != "enabled":
            log_command(logger, ctx, message="No fog of war game")
            await send_message_and_file(
                channel=ctx.channel,
                message="This command only works for players in fog of war games.",
                embed_colour=config.ERROR_COLOUR,
            )
            return

        visible_provinces = board.get_visible_provinces(player)
        log_command(
            logger, ctx, message=f"There are {len(visible_provinces)} visible provinces"
        )
        await send_message_and_file(
            channel=ctx.channel, message=", ".join([p.name for p in visible_provinces])
        )

    @commands.command(brief="creates a new private press channel",
        description="""
        * create_press_channel {category} {name} {@country1} {@country2} ...
        Arguments: 
        * category: the category to create the channel in (#comms-1, #comms-2, etc.)
        * name: the name of the channel to create (e.g. england-france)
        * @country1, @country2, ... : the roles of the other countries that should have access to the channel
        """,)
    @perms.player("create a private press channel")
    async def create_press_channel(self, ctx: commands.Context, player: Player | None) -> None:
        """Creates a new private press channel."""
        def send_creation_error(message: str):
            assert isinstance(ctx.channel, discord.TextChannel)
            return send_message_and_file(
                channel=ctx.channel,
                title="Error creating press channel",
                message=message,
                embed_colour=config.ERROR_COLOUR,
            )
        assert ctx.guild is not None
        if player is None:
            await send_creation_error("Only players can create press channels.")
            return
        arguments = remove_prefix(ctx).lower().split()

        if len(arguments) < 3:
            await send_creation_error("Invalid command format. " +
                "Please use `.create_press_channel {category} {name} {@country1} {@country2} ...`")
            return
        seed_channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
        channel_name = arguments[1]
        roles = ctx.message.role_mentions

        board = manager.get_board(ctx.guild.id)
        comms_category_prefix = "comms-"
        if not seed_channel or not (category:= seed_channel.category):
            await send_creation_error("You must select a channel in a press category (e.g. #comms-1, #comms-2, etc.).")
            return
        has_comms_category = False
        for channel in category.channels:
            if channel.name.startswith(comms_category_prefix):
                has_comms_category = True
                break
        if not has_comms_category:
            await send_creation_error("You must select a channel in a press category (e.g. #comms-1, #comms-2, etc.).")
            return
        for role in roles:
            try:
                board.get_player(role.name)
            except ValueError:
                await send_creation_error(f"{role.mention} does not correspond to a player in this game.")
                return

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            player.find_discord_role(ctx.guild.roles): discord.PermissionOverwrite(view_channel=True)
        }
        for role in roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        try:
            channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        except discord.Forbidden:
            await send_creation_error("Bot does not have permission to create channels in this category. " +
                                      "Please contact the GM Team.")
            return
        except discord.HTTPException:
            await send_creation_error("Failed to create channel, probably because the category is full. " +
                                      "If you keep seeing this error, please contact the GM Team.")
            return

        message = f"Created press channel {channel_name}"
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)

    @commands.command(name="press_directory", brief="outputs a list of press channels")
    @perms.player("generate a press directory")
    async def press_directory(self, ctx: commands.Context, player: Player | None) -> None:
        """Outputs a list of press channels."""
        assert ctx.guild is not None
        guild = ctx.guild
        gm_arguments = {"global"}
        arguments = remove_prefix(ctx).lower().split()


        if len(set(arguments).intersection(gm_arguments)) != 0:
            perms.assert_gm_only(ctx, "use a gm argument for .press_directory")

        board = manager.get_board(ctx.guild.id)
        power_roles = set(map(lambda p: p.find_discord_role(guild.roles), board.get_players()))

        if player is None:
            if "global" in arguments:
                for player in board.get_players():
                    order_channel_name = player.get_name().lower().replace(" ", "-") + config.PLAYER_CHANNEL_SUFFIX

                    order_channel = discord.utils.find(lambda c: c.name == order_channel_name, ctx.guild.text_channels)
                    if order_channel:
                        await self._player_press_directory(ctx,
                                                           channel=order_channel,
                                                           player=player,
                                                           power_roles=power_roles)

                await send_message_and_file(channel=ctx.channel, message="Created press directories for all players")
                return
            elif len(ctx.message.role_mentions) > 0:
                for player in board.get_players():
                    role = player.find_discord_role(guild.roles)
                    if role is None or role not in ctx.message.role_mentions:
                        continue

                    await self._player_press_directory(ctx,
                                                       channel=ctx.channel,
                                                       player=player,
                                                       power_roles=power_roles)

                out = " ".join(map(lambda r: r.mention, ctx.message.role_mentions))
                await send_message_and_file(channel=ctx.channel, message=f"Created press directories for players: {out}")
                return

            await send_message_and_file(channel=ctx.channel,
                                        message=f"Please provide a GM argument: {gm_arguments}",
                                        embed_colour=config.PARTIAL_ERROR_COLOUR)
            return

        if player is not None:
            await self._player_press_directory(ctx, channel=ctx.channel, player=player, power_roles=power_roles)


    async def _player_press_directory(self, ctx: commands.Context, *, channel, player, power_roles):
        assert ctx.guild is not None
        void_channels = [] # channels where the only perms are the calling country
        direct_channels = [] # channels where the only perms are the calling country +1
        group_channels = [] # channels where the only perms are the calling country + >1

        player_role = player.find_discord_role(ctx.guild.roles)
        if player_role is None:
            await send_message_and_file(
                channel=ctx.channel,
                message=f"Could not find the role for {player.name}",
                embed_colour=config.ERROR_COLOUR,
            )
            return

        for ch in ctx.guild.text_channels:
            # evaluate player access to channels
            allowed_roles = []
            for target, overwrite in ch.overwrites.items():
                if isinstance(target, discord.Role):
                    if overwrite.view_channel:
                        allowed_roles.append(target)

            if player_role not in allowed_roles:
                continue

            # remove non-player roles
            allowed_roles = list(set(allowed_roles) & power_roles)
            allowed_roles.remove(player_role)
            if len(allowed_roles) == 0:
                info = (ch, None)
                void_channels.append(info)
            elif len(allowed_roles) == 1:
                info = (ch, f"{allowed_roles[0].mention}")
                direct_channels.append(info)
            elif len(allowed_roles) > 1:
                info = (ch, " ".join(map(lambda r: r.mention, sorted(allowed_roles, key=lambda r: r.name))))
                group_channels.append(info)
            else:
                continue

        void_out = "\n".join([f"- {c.mention}" for c, _ in void_channels])
        direct_out = ("\n".join([f"- {c.mention} - {r_mentions}" for c, r_mentions in direct_channels])
                      if len(direct_channels) > 0 else "")
        group_out = ("\n".join([f"- {c.mention} - {r_mentions}" for c, r_mentions in group_channels])
                     if len(group_channels) > 0 else "")
        out = (
            "Void\n"
            f"{void_out}\n"
            "Press\n"
            f"{direct_out}\n"
            "Group\n"
            f"{group_out}"
        )
        await send_message_and_file(
            channel=channel,
            title=f"{player_role.name} Press Channel Directory",
            message=out
        )

async def setup(bot):
    """Setup for the player cog."""
    cog = PlayerCog(bot)
    await bot.add_cog(cog)
