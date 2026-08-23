"""Cog for player commands. Each commands contains a parameter determinging which player sent
the command, or None if it was done by a GM."""

import logging
from io import BytesIO
from typing import Callable, Iterable

import discord
import numpy as np
from discord.ext import commands
from PIL import Image

from DiploGM import config
from DiploGM import perms
from DiploGM.db.database import get_connection
from DiploGM.errors import MapRenderError
from DiploGM.parse_order import parse_order, parse_remove_order
from DiploGM.utils import get_orders, log_command, parse_season, send_message_and_file
from DiploGM.utils.image import svg_to_png
from DiploGM.utils.open_cores import get_open_core_text
from DiploGM.utils.sanitise import find_discord_role, get_colour_option, remove_prefix
from DiploGM.manager import Manager
from DiploGM.models.player import (
    ForcedDisbandOption,
    Player,
    ViewOpenCoresTags,
    ViewOrdersTags,
    OrdersSubsetOption,
)
from DiploGM.utils.send_message import (
    ErrorMessage,
    send_error,
    send_orders_locked_error,
)

logger = logging.getLogger(__name__)
manager = Manager()

MISSING_ALIASES = ["missing", "miss", "m"]
SUBMITTED_ALIASES = ["submitted", "submit", "sub", "s"]
BLIND_ALIASES = ["blind", "b"]
FORCED_RETREAT_ALIASES = ["forced-disband", "forced", "force", "disband", "pop", "f"]
FREE_RETREAT_ALIASES = [
    "free-retreats",
    "free-retreat",
    "free",
    "retreats",
    "retreat",
    "r",
]
OPEN_CORES_ALIASES = ["open-cores", "open", "cores", "core", "c"]
EXPLAIN = ["explain"]


class PlayerCog(commands.Cog):
    """Cog for player commands. Each commands contains a parameter determinging which player sent
    the command, or None if it was done by a GM."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        brief="Submits orders; there must be one and only one order per line.",
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
        database = get_connection()
        if board.turn.is_builds():
            database.save_build_orders_for_players(board, player)
        else:
            database.save_order_for_units(board, message["units"])
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
        database = get_connection()
        if board.turn.is_builds():
            database.save_build_orders_for_players(board, player)
        else:
            database.save_order_for_units(board, message["units"])
        log_command(logger, ctx, message=message["message"])
        await send_message_and_file(channel=ctx.channel, **message)

    @commands.command(brief="Clears all players orders.")
    @perms.player("remove all orders")
    async def remove_all(self, ctx: commands.Context, player: Player | None) -> None:
        """Remove all currently submitted orders from the board"""

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
        aliases=["v", "view", "vieworders", "view-orders"],
    )
    @perms.player("view orders")
    async def view_orders(self, ctx: commands.Context, player: Player | None) -> None:
        """Outputs your current submitted orders."""
        assert ctx.guild is not None
        arguments = remove_prefix(ctx).lower().split()

        any_alias_in_args: Callable[[Iterable[str]], bool] = lambda aliases: (
            0 < len(set(arguments).intersection(set(aliases)))
        )

        tags = ViewOrdersTags(
            subset=OrdersSubsetOption.MISSING
            if any_alias_in_args(MISSING_ALIASES)
            else OrdersSubsetOption.SUBMITTED
            if any_alias_in_args(SUBMITTED_ALIASES)
            else OrdersSubsetOption.FULL,
            blind=any_alias_in_args(BLIND_ALIASES),
            forced=ForcedDisbandOption.MARK_FORCED
            if any_alias_in_args(FORCED_RETREAT_ALIASES)
            else ForcedDisbandOption.ONLY_FREE
            if any_alias_in_args(FREE_RETREAT_ALIASES)
            else ForcedDisbandOption.UNMARKED,
            open_cores=any_alias_in_args(OPEN_CORES_ALIASES),
            explain=any_alias_in_args(EXPLAIN),
        )

        board = manager.get_board(ctx.guild.id)
        order_text = get_orders(board, player, ctx, tags=tags)

        log_command(
            logger,
            ctx,
            message=f"Success - generated orders for {board.turn}",
        )
        assert isinstance(order_text, str)
        await send_message_and_file(
            channel=ctx.channel, title=f"{board.turn}", message=order_text
        )

    @commands.command(
        brief="Outputs a list of your open cores.",
        aliases=["voc", "open-cores", "opencores", "view-open-cores"],
    )
    @perms.player(description="view open cores")
    async def view_open_cores(
        self, ctx: commands.Context, player: Player | None
    ) -> None:
        """Outputs a list of your open cores."""
        assert ctx.guild is not None

        arguments = remove_prefix(ctx).lower().split()
        any_alias_in_args: Callable[[Iterable[str]], bool] = lambda aliases: (
            0 < len(set(arguments).intersection(set(aliases)))
        )

        tags = ViewOpenCoresTags(
            blind=any_alias_in_args(BLIND_ALIASES),
        )

        board = manager.get_board(ctx.guild.id)
        message_text = get_open_core_text(ctx, board, player, tags)

        log_command(
            logger,
            ctx,
            message="Success - discovered open cores for "
            + f"{'all players' if player is None else player.name} - {board.turn}",
        )

        await send_message_and_file(
            channel=ctx.channel, title=f"{board.turn} Open Cores", message=message_text
        )

    async def _fetch_maps(
        self, ctx: commands.Context, player: Player | None, show_moves: bool = False
    ):
        assert ctx.guild is not None
        arguments = remove_prefix(ctx).lower().split()
        board = manager.get_board(ctx.guild.id)
        season = parse_season(arguments, board.turn)

        color_mode = get_colour_option(board, arguments)
        if color_mode is None:
            color_mode = (
                manager.ctx_parameters.get(ctx.author.id, {})
                .get(board.datafile, {})
                .get("color_mode", "standard")
            )

        if player and show_moves and not board.orders_enabled:
            log_command(logger, ctx, "Orders locked - not processing")
            await send_orders_locked_error(ctx.channel)
            return

        try:
            file, file_name = manager.draw_map(
                ctx.guild.id,
                draw_moves=show_moves,
                player_restriction=player,
                color_mode=color_mode,
                oil_spill_mode="oil" in set(arguments),
                invert_color_mode="invert" in set(arguments),
                clean_map_mode="clean" in set(arguments),
                movement_only="movement" in arguments,
                turn=season,
                fow_player=player
                if board.data.get("fow", "disabled") == "enabled"
                else None,
            )
        except MapRenderError as err:
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
            message = (
                "`.vm true` and `.vm t` have been deprecated and will soon be disabled.\n"
                "Please use `.vm svg` instead"
            )

        dpi = board.data["svg config"].get("dpi", 200)
        convert_svg = not ({"true", "t", "svg", "s"} & set(arguments))
        if convert_svg and file and file_name:
            file, file_name = await svg_to_png(file, file_name, dpi=dpi)
        
            # cutup map png output for pacific center line
            pacific_map_mode="pacific" in set(arguments)
            if "impdip" in board.datafile and pacific_map_mode and dpi == 200:
                img = Image.open(BytesIO(file))
                arr = np.array(img)

                # cutoff lines (assuming 200 DPI)
                split_pixel_ratio = 3570 / 11047
                map_edge_pixel_ratio = 9100 / 11047

                # scale for DPI
                split_pixel = int(split_pixel_ratio * img.width)
                map_edge_pixel = int(map_edge_pixel_ratio * img.width)
                
                # cut map section of image in two pieces
                left = arr[:, :split_pixel]
                right = arr[:, split_pixel:map_edge_pixel]

                # reorder and stitch together
                reordered = np.concatenate([right, left], axis=1)
                arr[:, :map_edge_pixel] = reordered

                output = BytesIO()
                Image.fromarray(arr).save(output, format="PNG")
                file = output.getvalue()

        display_season = season or board.turn
        log_command(
            logger,
            ctx,
            message=f"Generated {'moves' if show_moves else 'current'} map for {display_season}",
        )
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{display_season} {'Orders' if show_moves else 'Current'} Map",
            message=message,
            file=file,
            file_name=file_name,
            file_in_embed=False,
        )

    @commands.command(
        brief="Outputs the current map with submitted orders.",
        aliases=["viewmap", "vm"],
    )
    @perms.player("view map")
    async def view_map(self, ctx: commands.Context, player: Player | None):
        """Outputs the current map with submitted orders."""
        await self._fetch_maps(ctx, player, show_moves=True)

    @commands.command(
        brief="Outputs the current map without any orders.",
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
        fow_player = player if board.data.get("fow", "disabled") == "enabled" else None

        color_mode = get_colour_option(board, arguments)
        if color_mode is None:
            color_mode = (
                manager.ctx_parameters.get(ctx.author.id, {})
                .get(board.datafile, {})
                .get("color_mode", "standard")
            )

        if player and not board.orders_enabled:
            log_command(logger, ctx, "Orders locked - not processing")
            await send_orders_locked_error(ctx.channel)
            return

        try:
            file, file_name = manager.draw_gui_map(
                ctx.guild.id, color_mode=color_mode, fow_player=fow_player
            )
        except MapRenderError as err:
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

    @commands.command(brief="creates a new private press channel")
    @perms.player("create a private press channel")
    async def create_press_channel(
        self, ctx: commands.Context, player: Player | None
    ) -> None:
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
            await send_creation_error(
                "Invalid command format. "
                + "Please use `.create_press_channel {category} {name} {@country1} {@country2} ...`"
            )
            return
        seed_channel = (
            ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
        )
        channel_name = arguments[1]
        roles = ctx.message.role_mentions

        board = manager.get_board(ctx.guild.id)
        comms_category_prefix = "comms-"
        if not seed_channel or not (category := seed_channel.category):
            await send_creation_error(
                "You must select a channel in a press category (e.g. #comms-1, #comms-2, etc.)."
            )
            return
        has_comms_category = False
        for channel in category.channels:
            if channel.name.startswith(comms_category_prefix):
                has_comms_category = True
                break
        if not has_comms_category:
            await send_creation_error(
                "You must select a channel in a press category (e.g. #comms-1, #comms-2, etc.)."
            )
            return
        for role in roles:
            try:
                board.get_player(role.name)
            except ValueError:
                await send_creation_error(
                    f"{role.mention} does not correspond to a player in this game."
                )
                return

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            find_discord_role(player, ctx.guild.roles): discord.PermissionOverwrite(
                view_channel=True
            ),
        }
        for role in roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        try:
            channel = await category.create_text_channel(
                channel_name, overwrites=overwrites
            )
        except discord.Forbidden:
            await send_creation_error(
                "Bot does not have permission to create channels in this category. "
                + "Please contact the GM Team."
            )
            return
        except discord.HTTPException:
            await send_creation_error(
                "Failed to create channel, probably because the category is full. "
                + "If you keep seeing this error, please contact the GM Team."
            )
            return

        message = f"Created press channel {channel_name}"
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)

    @commands.command(name="press_directory", brief="outputs a list of press channels")
    async def press_directory(self, ctx: commands.Context) -> None:
        """Outputs a list of press channels."""
        assert ctx.guild is not None
        assert isinstance(ctx.channel, (discord.TextChannel, discord.Thread))
        guild = ctx.guild
        gm_arguments = {"global"}
        arguments = remove_prefix(ctx).lower().split()

        board = manager.get_board(ctx.guild.id)
        power_roles = set(
            map(lambda p: find_discord_role(p, guild.roles), board.get_players())
        )

        if len(set(arguments).intersection(gm_arguments)) != 0:
            perms.assert_gm_only(ctx, "use a gm argument for .press_directory")
            player = None
        else:
            channel_name: str = ctx.channel.name
            if not channel_name.endswith(
                config.PLAYER_CHANNEL_SUFFIX
            ) and not channel_name.endswith(config.PLAYER_VOID_CHANNEL_SUFFIX):
                await send_message_and_file(
                    channel=ctx.channel,
                    message="You may not create a press directory here.",
                    embed_colour=config.ERROR_COLOUR,
                )
                return

            player_name = channel_name.removesuffix(config.PLAYER_CHANNEL_SUFFIX)
            player_name = player_name.removesuffix(config.PLAYER_VOID_CHANNEL_SUFFIX)

            try:
                player = board.get_player(player_name)
            except ValueError:
                await send_message_and_file(
                    channel=ctx.channel,
                    message="No player in this game is attached to this channel.",
                    embed_colour=config.ERROR_COLOUR,
                )
                return

        if player is not None:
            await self._player_press_directory(
                ctx, channel=ctx.channel, player=player, power_roles=power_roles
            )
            return

        if "global" in arguments:
            for player in board.get_players():
                order_channel_name = (
                    player.get_name().lower().replace(" ", "-")
                    + config.PLAYER_CHANNEL_SUFFIX
                )

                order_channel = discord.utils.find(
                    lambda c, name=order_channel_name: c.name == name,
                    ctx.guild.text_channels,
                )
                if order_channel:
                    await self._player_press_directory(
                        ctx,
                        channel=order_channel,
                        player=player,
                        power_roles=power_roles,
                    )

            await send_message_and_file(
                channel=ctx.channel, message="Created press directories for all players"
            )
            return
        if len(ctx.message.role_mentions) > 0:
            for player in board.get_players():
                role = find_discord_role(player, guild.roles)
                if role is None or role not in ctx.message.role_mentions:
                    continue

                await self._player_press_directory(
                    ctx, channel=ctx.channel, player=player, power_roles=power_roles
                )

            out = " ".join(map(lambda r: r.mention, ctx.message.role_mentions))
            await send_message_and_file(
                channel=ctx.channel,
                message=f"Created press directories for players: {out}",
            )
            return

        await send_message_and_file(
            channel=ctx.channel,
            message=f"Please provide a GM argument: {gm_arguments}",
            embed_colour=config.PARTIAL_ERROR_COLOUR,
        )

    async def _player_press_directory(
        self, ctx: commands.Context, *, channel, player, power_roles
    ):
        assert ctx.guild is not None
        channels = [[], [], []]
        labels = ["Void", "Press", "Group"]

        player_role = find_discord_role(player, ctx.guild.roles)
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
                if isinstance(target, discord.Role) and overwrite.view_channel:
                    allowed_roles.append(target)

            if player_role not in allowed_roles:
                continue

            # remove non-player roles
            allowed_roles = list(set(allowed_roles) & power_roles)
            allowed_roles.remove(player_role)
            mentions = (
                None
                if not allowed_roles
                else " ".join(
                    r.mention for r in sorted(allowed_roles, key=lambda r: r.name)
                )
            )
            channels[min(2, len(allowed_roles))].append((ch, mentions))

        out = ""
        for i in range(3):
            if len(channels[i]) > 0:
                out += f"{labels[i]}\n"
                out += "\n".join(
                    [f"- {c.mention} - {r_mentions}" for c, r_mentions in channels[i]]
                )
                out += "\n"
        await send_message_and_file(
            channel=channel,
            title=f"{player_role.name} Press Channel Directory",
            message=out,
        )


async def setup(bot):
    """Setup for the player cog."""
    cog = PlayerCog(bot)
    await bot.add_cog(cog)
