from __future__ import annotations
from black.trans import defaultdict
import inspect
import logging
from typing import TYPE_CHECKING

from discord import Member
from discord.ext import commands

from DiploGM.config import ERROR_COLOUR
from DiploGM import perms
from DiploGM.utils import (
    send_message_and_file,
    log_command,
)
from DiploGM.manager import Manager, SEVERENCE_A_ID, SEVERENCE_B_ID
from DiploGM.models.player import Player
from DiploGM.models.province import ProvinceType
from DiploGM.models.turn import PhaseName
from DiploGM.utils.sanitise import parse_season

if TYPE_CHECKING:
    from DiploGM.models.board import Board


logger = logging.getLogger(__name__)
manager = Manager()


class CommandCog(commands.Cog):
    """This is a Cog for general-purpose commands!"""

    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.command(brief="How long has the bot been online?")
    async def uptime(self, ctx: commands.Context) -> None:
        uptime = ctx.message.created_at - self.bot.creation_time

        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        seconds = int((uptime.total_seconds() % 3600) % 60)
        awake_since = f"{hours} hours {minutes} minutes {seconds} seconds"

        since_last = (
            ctx.message.created_at - self.bot.last_command_time
            if self.bot.last_command_time
            else -1
        )
        if since_last == -1:
            since_last = "None so far in this uptime."
        else:
            hours = int(since_last.total_seconds() // 3600)
            minutes = int((since_last.total_seconds() % 3600) // 60)
            seconds = int((since_last.total_seconds() % 3600) % 60)
            since_last = f"{hours} hours {minutes} minutes {seconds} seconds ago"

        await send_message_and_file(
            channel=ctx.channel,
            title="Uptime",
            message=(
                f"DiploGM has been awake for: {awake_since}\n"
                f"Last processed command was: {since_last}"
            ),
        )

    def generate_chaos_scoreboard(self, board: Board, ctx) -> str:
        response = ""
        the_player = perms.get_player_by_context(ctx)
        scoreboard_rows = []

        latest_index = -1
        latest_points = float("inf")

        for i, player in enumerate(board.get_players_sorted_by_points()):
            points = player.points

            if points < latest_points:
                latest_index = i
                latest_points = points

            if i <= 25 or player == the_player:
                scoreboard_rows.append((latest_index + 1, player))
            elif the_player == None:
                break
            elif the_player == player:
                scoreboard_rows.append((latest_index + 1, player))
                break

        index_length = len(str(scoreboard_rows[-1][0]))
        points_length = len(str(scoreboard_rows[0][1]))

        for index, player in scoreboard_rows:
            if board.data["players"][player.name].get("hidden", "false") == "true":
                continue
            response += (
                f"\n\\#{index: >{index_length}} | {player.points: <{points_length}} | **{player.get_name()}**: "
                f"{len(player.centers)} ({'+' if len(player.centers) - len(player.units) >= 0 else ''}"
                f"{len(player.centers) - len(player.units)})"
            )
        return response

    def generate_scoreboard(self, board: Board, ctx: commands.Context, alphabetical: bool) -> str:
        assert ctx.guild is not None
        response = ""
        old_board = manager._database.get_board(
            board.board_id,
            parse_season(["Fall"], board.turn.get_previous_turn()),
            board.fish,
            board.name,
            board.datafile,
        )
        player_list = (
            sorted(board.players, key=lambda p: p.get_name())
            if alphabetical
            else board.get_players_sorted_by_score()
        )
        for player in player_list:
            if (
                player_role := player.find_discord_role(ctx.guild.roles)
            ) is not None:
                player_name = player_role.mention
            else:
                player_name = player.get_name()

            if board.data["players"][player.name].get("hidden", "false") == "true":
                continue
            response += (
                f"\n**{player_name}**: "
                f"{len(player.centers)} ({'+' if len(player.centers) - len(player.units) >= 0 else ''}"
                f"{len(player.centers) - len(player.units)}) ")

            if old_board is not None:
                old_player = old_board.get_player(player.name)
                assert old_player is not None
                sc_diff = len(player.centers) - len(old_player.centers)
                response += (
                    f"({'+' if sc_diff >= 0 else ''}"
                    f"{sc_diff} SC{'s' if abs(sc_diff) != 1 else ''}) ")
            
            response += f"[{round(board.get_score(player) * 100, 1)}%]"
        return response

    @commands.command(
        brief="Outputs the scoreboard.",
        description="""Outputs the scoreboard.
        In Chaos, is shortened and sorted by points, unless "standard" is an argument
        * Use `csv` to obtain a raw list of sc counts (in alphabetical order)""",
        aliases=["leaderboard", "sb"],
    )
    async def scoreboard(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        arguments = (
            ctx.message.content.removeprefix(f"{ctx.prefix}{ctx.invoked_with}")
            .strip()
            .lower()
            .split()
        )
        csv = "csv" in arguments
        alphabetical = len({"a", "alpha", "alphabetical"} & set(arguments)) > 0

        board = manager.get_board(ctx.guild.id)

        if board.fow:
            perms.assert_gm_only(ctx, "get scoreboard")

        if csv and not board.is_chaos():
            players = sorted(board.players, key=lambda p: p.name)
            counts = map(lambda p: str(len(p.centers)), players)
            counts = "\n".join(counts)
            await ctx.send(counts)
            return

        if board.is_chaos() and "standard" not in ctx.message.content:
            response = self.generate_chaos_scoreboard(board, ctx)
        else:
            response = self.generate_scoreboard(board, ctx, alphabetical)

        log_command(logger, ctx, message="Generated scoreboard")
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{board.turn}",
            message=response,
        )

    @commands.command(brief="outputs information about the current game", aliases=["i"])
    async def info(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        try:
            board = manager.get_board(ctx.guild.id)
        except RuntimeError:
            log_command(logger, ctx, message="No game this this server.")
            await send_message_and_file(
                channel=ctx.channel, title="There is no game this this server."
            )
            return
        log_command(
            logger,
            ctx,
            message=f"Displayed info - {board.turn}|{str(board.datafile)}|"
            f"{'Open' if board.orders_enabled else 'Locked'}",
        )
        await send_message_and_file(
            channel=ctx.channel,
            message=(
                f"Turn: {board.turn}\n"
                f"Orders are {'Open' if board.orders_enabled else 'Locked'}\n"
                f"Game Type: {str(board.datafile)}\n"
                f"Chaos: {':white_check_mark:' if board.is_chaos() else ':x:'}\n"
                f"Fog of War: {':white_check_mark:' if board.fow else ':x:'}"
            ),
        )

    @commands.command(
        brief="Returns developer information",
        help="""
        Provide the name of a command to obtain the Python docstrings for the method.

        Usage:
            .dev <cmd>
            .dev dev
            .dev create_game
            .dev view_orders
        """,
    )
    async def dev(self, ctx: commands.Context, cmd_name: str) -> None:
        """
        Return docstring information to the user, give a high-level insight into how the bot might work.

        Process:
            1. Fetch Command (error on NotFound)
            2. Collect Command information
                a. Method definition
                b. Method docstrings

        Parameters
        ----------
        ctx (commands.Context): Invoking message context
        cmd_name (str | None): Name of the command to obtain docstring information from

        Returns
        -------
        None
        """
        cmd = self.bot.get_command(cmd_name)
        if not cmd:
            await send_message_and_file(
                channel=ctx.channel,
                message=f"No command found for name: {cmd_name}",
                embed_colour=ERROR_COLOUR,
            )
            return

        funcdef = f"async def {cmd.callback.__name__}{inspect.signature(cmd.callback)}:"
        docs = inspect.getdoc(cmd.callback) or "No docstring available..."

        out = (
            "**Command Definition:**\n"
            "```python\n"
            f"{funcdef}```"
            f"**Developer Documentation:**\n"
            f"```{docs}```"
        )
        out = (out[:1021] + "...") if len(out) >= 1024 else out

        await send_message_and_file(
            channel=ctx.channel, title=f"Developer Info for {cmd_name}", message=out
        )

    @commands.command(
        brief="outputs information about a specific province",
        aliases=["province"],
    )
    async def province_info(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        if not board.orders_enabled:
            perms.assert_gm_only(
                ctx,
                "You cannot use .province_info in a non-GM channel while orders are locked.",
                non_gm_alt="Orders locked! If you think this is an error, contact a GM.",
            )
            return

        # NOTE: Temporary for Meme's Severance event
        if guild.id in [SEVERENCE_A_ID, SEVERENCE_B_ID]:
            await send_message_and_file(
                channel=ctx.channel,
                title="Can't be doing that now, can we?",
                message="No information for you.",
            )
            return
            
        province_name = ctx.message.content.removeprefix(
            f"{ctx.prefix}{ctx.invoked_with}"
        ).strip()
        if not province_name:
            log_command(logger, ctx, message=f"No province given")
            await send_message_and_file(
                channel=ctx.channel,
                title="No province given",
                message="Usage: .province_info <province>",
            )
            return
        try:
            province = board.get_province(province_name)
        except:
            log_command(logger, ctx, message=f"Province `{province_name}` not found")
            await send_message_and_file(
                channel=ctx.channel, title=f"Could not find province {province_name}"
            )
            return

        # FOW permissions
        if board.fow:
            player = perms.require_player_by_context(ctx, "get province info")
            if player and not province in board.get_visible_provinces(player):
                log_command(
                    logger,
                    ctx,
                    message=f"Province `{province_name}` hidden by fow to player",
                )
                await send_message_and_file(
                    channel=ctx.channel,
                    title=f"Province {province.name} is not visible to you",
                )
                return

        # fmt: off
        coasts = province.get_multiple_coasts()
        coast_info = ""
        adjacent_coasts = ""
        if coasts:
            coast_info = f"Coasts: {len(coasts)}\n"
            for c in coasts:
                adjacent_coasts += f"Adjacent Coastal Provinces ({c}):\n- "
                adjacent_list = []
                for adj in province.get_coastal_adjacent(c):
                    adjacent_list.append(f"{adj[0] if isinstance(adj, tuple) else adj}")
                adjacent_coasts += "\n- ".join(sorted(adjacent_list))
                adjacent_coasts += "\n"
        elif province.type == ProvinceType.LAND and province.get_coastal_adjacent():
            adjacent_coasts = "Adjacent Coastal Provinces:\n- "
            adjacent_list = []
            for adj in province.get_coastal_adjacent():
                adjacent_list.append(f"{adj[0] if isinstance(adj, tuple) else adj}")
            adjacent_coasts += "\n- ".join(sorted(adjacent_list))
            adjacent_coasts += "\n"
        out = f"Type: {province.type.name}\n" + \
            f"{coast_info}" + \
            f"Owner: {province.owner.name if province.owner else 'None'}\n" + \
            f"Unit: {(province.unit.player.get_name() + ' ' + province.unit.unit_type.name) if province.unit else 'None'}\n" + \
            f"Center: {province.has_supply_center}\n" + \
            f"Core: {province.core.name if province.core else 'None'}\n" + \
            f"Half-Core: {province.half_core.name if province.half_core else 'None'}\n" + \
            f"Adjacent Provinces:\n- " + "\n- ".join(sorted([adjacent.name for adjacent in province.adjacent | province.impassible_adjacent])) + "\n" + \
            f"{adjacent_coasts}"
        # fmt: on
        log_command(logger, ctx, message=f"Got info for {province_name}")

        await send_message_and_file(
            channel=ctx.channel, title=province.name, message=out
        )

    @commands.command(
        brief="outputs information about a specific player",
        aliases=["player"],
    )
    async def player_info(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not guild:
            return

        board = manager.get_board(guild.id)

        if not board.orders_enabled:
            perms.assert_gm_only(
                ctx,
                "You cannot use .player_info in a non-GM channel while orders are locked.",
                non_gm_alt="Orders locked! If you think this is an error, contact a GM.",
            )
            return

        # NOTE: Temporary for Meme's Severance event
        if guild.id in [SEVERENCE_A_ID, SEVERENCE_B_ID]:
            await send_message_and_file(
                channel=ctx.channel,
                title="Can't be doing that now, can we?",
                message="No information for you.",
            )
            return

        player_name = ctx.message.content.removeprefix(
            f"{ctx.prefix}{ctx.invoked_with}"
        ).strip()
        if not player_name:
            log_command(logger, ctx, message=f"No player given")
            await send_message_and_file(
                channel=ctx.channel,
                title="No player given",
                message="Usage: .player_info <player>",
            )
            return

        variant = "standard"
        player: Player | None = None
        if board.is_chaos():
            # HACK: chaos has same name of players as provinces so we exploit that
            province, _ = board.get_province_and_coast(player_name)
            player = board.get_player(province.name.lower())
            variant = "chaos"

        elif board.fow:
            await send_message_and_file(
                channel=ctx.channel,
                title=f"Gametype Error!",
                message="This command does not work with FoW",
                embed_colour=ERROR_COLOUR,
            )
            return

        else:
            try:
                player = board.get_player(player_name)
            except ValueError:
                player = None

        # f"Initial/Current/Victory SC Count [Score]: {player.iscc}/{len(player.centers)}/{player.vscc} [{player.score()}%]\n" + \

        if player is None:
            log_command(logger, ctx, message=f"Player `{player}` not found")
            await send_message_and_file(
                channel=ctx.channel, title=f"Could not find player {player_name}"
            )
            return

        out = player.info(board)
        log_command(logger, ctx, message=f"Got info for player {player}")

        # FIXME title should probably include what coast it is.
        await send_message_and_file(channel=ctx.channel, title=player.get_name(), message=out)

    @commands.command(brief="outputs all provinces per owner")
    async def all_province_data(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        if not board.orders_enabled:
            perms.assert_gm_only(
                ctx, "call .all_province_data while orders are locked"
            )
            
        # NOTE: Temporary for Meme's Severance event
        if guild.id in [SEVERENCE_A_ID, SEVERENCE_B_ID]:
            await send_message_and_file(
                channel=ctx.channel,
                title="Can't be doing that now, can we?",
                message="No information for you.",
            )
            return
            
        province_by_owner = defaultdict(list)
        for province in board.provinces:
            owner = province.owner
            if not owner:
                owner = None
            province_by_owner[owner].append(province.name)

        message = ""
        for owner, provinces in province_by_owner.items():
            if owner is None:
                player_name = "None"
            elif (
                player_role := owner.find_discord_role(ctx.guild.roles)
            ) is not None:
                player_name = player_role.mention
            else:
                player_name = owner

            message += f"{player_name}: "
            for province in provinces:
                message += f"{province}, "
            message += "\n\n"

        log_command(
            logger,
            ctx,
            message=f"Found {sum(map(len, province_by_owner.values()))} provinces",
        )
        await send_message_and_file(channel=ctx.channel, message=message)

    # @commands.command(
    #     brief="wipe",
    # )
    # async def wipe(self, ctx: commands.Context) -> None:
    #     board = manager.get_board(ctx.guild.id)
    #     cs = []
    #     pla = sorted(board.players, key=lambda p: p.name)
    #     for p1 in pla:
    #         for p2 in pla:
    #             if p1.name < p2.name:
    #                 c = f"{p1.name}-{p2.name}"
    #                 cs.append(c.lower())

    #     guild = ctx.guild

    #     for channel in guild.channels:
    #         if channel.name in cs:
    #             await channel.delete()

    @commands.command(brief="Changes your nickname")
    async def nick(self, ctx: commands.Context) -> None:
        assert isinstance(ctx.author, Member)
        name = ctx.author.nick
        if name == None:
            name = ctx.author.name
        if "]" in name:
            prefix = name.split("] ", 1)[0]
            prefix = prefix + "] "
        else:
            prefix = ""
        name = ctx.message.content.removeprefix(f"{ctx.prefix}{ctx.invoked_with}").strip()
        if name == "":
            await send_message_and_file(
                channel=ctx.channel,
                embed_colour=ERROR_COLOUR,
                message=f"A nickname must be at least 1 character",
            )
            return
        if len(prefix + name) > 32:
            await send_message_and_file(
                channel=ctx.channel,
                embed_colour=ERROR_COLOUR,
                message=f"A nickname must be at less than 32 total characters.\n Yours is {len(prefix + name)}",
            )
            return
        await ctx.author.edit(nick=prefix + name)
        await send_message_and_file(
            channel=ctx.channel, message=f"Nickname updated to `{prefix + name}`"
        )


async def setup(bot):
    cog = CommandCog(bot)
    await bot.add_cog(cog)
