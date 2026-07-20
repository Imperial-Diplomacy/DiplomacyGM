from __future__ import annotations
import inspect
import logging
import random
from typing import TYPE_CHECKING
from collections import defaultdict
from discord import Member
import discord
from discord.ext import commands

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM import perms
from DiploGM.errors import NoGameError
from DiploGM.models.adjacency import Terrain
from DiploGM.parse_user_prefs import parse_user_prefs
from DiploGM.utils import (
    send_message_and_file,
    log_command,
)
from DiploGM.manager import Manager
from DiploGM.models.player import Player
from DiploGM.models.province import ProvinceType
from DiploGM.utils.sanitise import find_discord_role, parse_season, remove_prefix

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
        """Outputs the bot's uptime and time since last command."""
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

    @commands.command(name="version", hidden=True)
    async def version(self, ctx: commands.Context) -> None:
        """Outputs the version number of the bot, read from the first line of Changelog.md"""
        with open("Changelog.md", "r", encoding="utf-8") as f:
            version = f.readline()
        await send_message_and_file(
            channel=ctx.channel, message=f"DiploGM Version: {version}"
        )

    @commands.command(name="rng", hidden=True)
    async def rng(self, ctx: commands.Context, upper: str = "1000000000") -> None:
        if not str.isnumeric(upper):
            await send_message_and_file(channel=ctx.channel, message="Please specify an integer")
            return
        upper_int = min(abs(int(upper)), 1_000_000_000)
        number = random.randint(0, upper_int)

        title = "Your selected number was..."
        out = f"Result: `{number}`\nRange: `0` to `{upper_int}`"
        await send_message_and_file(channel=ctx.channel, title=title, message=out)

    def _generate_scoreboard(
        self, board: Board, ctx: commands.Context, alphabetical: bool
    ) -> str:
        assert ctx.guild is not None
        response = ""
        try:
            old_board = manager.get_board_from_db(
                board.board_id, parse_season(["Fall"], board.turn.get_previous_turn())
            )
        except NoGameError:
            old_board = None
        player_list = (
            sorted(board.get_players(), key=lambda p: p.get_name())
            if alphabetical
            else board.get_players_sorted_by_score()
        )
        for player in player_list:
            if (player_role := find_discord_role(player, ctx.guild.roles)) is not None:
                player_name = player_role.mention
            else:
                player_name = player.get_name()

            if board.is_player_hidden(player):
                continue
            response += (
                f"\n**{player_name}**: "
                f"{len(player.centers)} ({'+' if len(player.centers) - len(player.units) >= 0 else ''}"
                f"{len(player.centers) - len(player.units)}) "
            )

            if old_board is not None:
                old_player = old_board.get_player(player.name)
                assert old_player is not None
                sc_diff = len(player.centers) - len(old_player.centers)
                response += (
                    f"({'+' if sc_diff >= 0 else ''}"
                    f"{sc_diff} SC{'s' if abs(sc_diff) != 1 else ''}) "
                )

            response += f"[{round(board.get_score(player) * 100, 1)}%]"
        return response

    @commands.command(
        brief="Outputs the scoreboard.",
        description="""Outputs the scoreboard.
        * Use `csv` to obtain a raw list of sc counts (in alphabetical order)""",
        aliases=["leaderboard", "sb"],
    )
    async def scoreboard(self, ctx: commands.Context) -> None:
        """Outputs the scoreboard. Can be optionally sorted alphabetically."""
        assert ctx.guild is not None
        arguments = remove_prefix(ctx).lower().split()
        csv = "csv" in arguments
        alphabetical = len({"a", "alpha", "alphabetical"} & set(arguments)) > 0

        board = manager.get_board(ctx.guild.id)

        if board.data.get("fow", "disabled") == "enabled":
            perms.assert_gm_only(ctx, "get scoreboard")

        if csv and not board.is_chaos():
            players = sorted(board.get_players(), key=lambda p: p.name)
            counts = map(lambda p: str(len(p.centers)), players)
            counts = "\n".join(counts)
            await ctx.send(counts)
            return

        response = self._generate_scoreboard(board, ctx, alphabetical)

        log_command(logger, ctx, message="Generated scoreboard")
        await send_message_and_file(
            channel=ctx.channel,
            title=f"{board.turn}",
            message=response,
        )

    @commands.command(brief="Outputs a history of SC control over the game")
    async def sc_history(self, ctx: commands.Context) -> None:
        """Outputs a history of SC control over the game"""
        assert ctx.guild is not None
        arguments = remove_prefix(ctx).lower().split()
        alphabetical = len({"a", "alpha", "alphabetical"} & set(arguments)) > 0

        board = manager.get_board(ctx.guild.id)
        if board.data.get("fow", "disabled") == "enabled":
            perms.assert_gm_only(ctx, "get sc history")

        player_list = (
            sorted(board.get_players(), key=lambda p: p.get_name())
            if alphabetical
            else board.get_players_sorted_by_score()
        )
        player_list = [p for p in player_list if not board.is_player_hidden(p)]
        year_range = sorted({y for p in player_list for y in p.sc_history}) # Gets all the years from all the powers
        year_length = {y: 3 if any(p.sc_history.get(y, 0) > 99 for p in player_list) else 2 for y in year_range}
        header = [f"{'Player':<8}"]
        header += [f"{str(year)[-2:]:>{year_length[year]}}" for year in year_range]
        response = [" ".join(header)]
        for player in player_list:
            player_data = [f"{player.name:<8}"] if len(player.name) <= 8 else [f"{player.name[:7]}…"]
            for year in year_range:
                sc_count = player.sc_history.get(year, "")
                sc_count = "" if sc_count == 0 else sc_count
                player_data.append(f"{sc_count:>{year_length[year]}}")
            response.append(" ".join(player_data))
        await send_message_and_file(
            channel=ctx.channel,
            title="Supply Center history",
            message = "\n".join(["```"] + response + ["```"])
        )

    @commands.command(brief="outputs information about the current game", aliases=["i"])
    async def info(self, ctx: commands.Context) -> None:
        """Outputs information about the current game."""
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)
        log_command(
            logger,
            ctx,
            message=f"Displayed info - {board.turn}|{str(board.datafile)}|"
            f"{'Open' if board.orders_enabled else 'Locked'}",
        )
        message = f"Turn: {board.turn}\n"
        message += f"Orders are {'Open' if board.orders_enabled else 'Locked'}\n"
        message += f"Game Type: {str(board.datafile)}\n"
        if board.data.get("deadline"):
            message += f"Deadline: <t:{board.data['deadline']}:f>\n"
        if board.is_chaos():
            message += "Chaos: :white_check_mark:\n"
        if board.data.get("fow", "disabled") == "enabled":
            message += "Fog of War: :white_check_mark:\n"
        await send_message_and_file(
            channel=ctx.channel,
            message=message,
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
        brief="outputs information for which user is playing which power",
        aliases=["vp"],
    )
    async def view_players(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)
        players = board.get_players()

        player_role = discord.utils.get(ctx.guild.roles, name="Player")
        if player_role is None:
            await send_message_and_file(
                channel=ctx.channel,
                message="Could not find an @Player role to search for.",
                embed_colour=PARTIAL_ERROR_COLOUR,
            )
            return

        power_roles = set(map(lambda p: find_discord_role(p, ctx.guild.roles), players))
        active_players = {role: [] for role in power_roles}

        for member in ctx.guild.members:
            if not any(r == player_role for r in member.roles):
                continue

            player_powers = power_roles & set(member.roles)
            for role in player_powers:
                active_players[role].append(member)

        active_players = dict(
            sorted(
                [(k, v) for (k, v) in active_players.items() if k is not None],
                key=lambda pair: pair[0].name,
            )
        )

        out = ""
        for role, members in active_players.items():
            out += f"{role.mention}:\n"
            for member in members:
                pronouns = manager.ctx_parameters.get(member.id, {}).get(
                    "pronouns", "?/?"
                )
                timezone = manager.ctx_parameters.get(member.id, {}).get(
                    "timezone", "UTC+?"
                )
                out += f"\\- {member.mention} PN={pronouns} TZ={timezone}\n"

        await send_message_and_file(
            channel=ctx.channel, title=f"{ctx.guild.name}\nPlayer List", message=out
        )

    @commands.command(
        brief="outputs information about a specific province",
        aliases=["province"],
    )
    async def province_info(self, ctx: commands.Context) -> None:
        """Outputs information about a specific province."""
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        if not board.orders_enabled:
            perms.assert_gm_only(
                ctx,
                "You cannot use .province_info in a non-GM channel while orders are locked.",
                non_gm_alt="Orders locked! If you think this is an error, contact a GM.",
            )

        province_name = remove_prefix(ctx)
        if not province_name:
            log_command(logger, ctx, message="No province given")
            await send_message_and_file(
                channel=ctx.channel,
                title="No province given",
                message="Usage: .province_info <province>",
            )
            return
        try:
            province = board.get_province(province_name)
        except ValueError as _:
            log_command(logger, ctx, message=f"Province `{province_name}` not found")
            await send_message_and_file(
                channel=ctx.channel, title=f"Could not find province {province_name}"
            )
            return

        # FOW permissions
        if board.data.get("fow", "disabled") == "enabled":
            player = perms.require_player_by_context(ctx, "get province info")
            if player and province not in board.get_visible_provinces(player):
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
        coasts = province.adjacencies.coasts
        coast_info = ""
        adjacent_coasts = ""
        if coasts:
            coast_info = f"Coasts: {len(coasts)}\n"
            for c in coasts:
                adjacent_coasts += f"Adjacent Coastal Provinces ({c}):\n- "
                adjacent_list = [a.name for a in province.adjacencies.get_all(coast = c)]
                adjacent_coasts += "\n- ".join(sorted(adjacent_list))
                adjacent_coasts += "\n"
        elif province.type == ProvinceType.LAND and not province.is_landlocked():
            adjacent_coasts = "Adjacent Coastal Provinces:\n- "
            adjacent_list = [a.name for a in province.adjacencies.get_all(Terrain.COAST)]
            adjacent_coasts += "\n- ".join(sorted(adjacent_list))
            adjacent_coasts += "\n"
        adjacent_sorted = sorted([adjacent.name for adjacent in province.adjacencies.get_all()])
        unit_text = ((province.unit.player.get_name() if province.unit.player is not None else '')
                        + ' ' + province.unit.unit_type.name
                        + (f" {province.unit.coast}" if province.unit.coast is not None else '')
                    if province.unit else 'None')
        out = f"Type: {province.type.name}\n" + \
            f"{coast_info}" + \
            f"Owner: {province.get_owner_name()}\n" + \
            f"Unit: {unit_text}\n" + \
            f"Center: {province.has_supply_center}\n" + \
            f"Core: {province.core_data.core.name if province.core_data.core else 'None'}\n" + \
            f"Half-Core: {province.core_data.half_core.name if province.core_data.half_core else 'None'}\n" + \
            "Adjacent Provinces:\n- " + "\n- ".join(adjacent_sorted) + "\n" + \
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
        """Outputs information about a specific player."""
        guild = ctx.guild
        if not guild:
            return
        board = manager.get_board(guild.id)

        if board.data.get("fow", "disabled") == "enabled":
            await send_message_and_file(
                channel=ctx.channel,
                title="Gametype Error!",
                message="This command does not work with FoW",
                embed_colour=ERROR_COLOUR,
            )
            return

        if not board.orders_enabled:
            perms.assert_gm_only(
                ctx,
                "You cannot use .player_info in a non-GM channel while orders are locked.",
                non_gm_alt="Orders locked! If you think this is an error, contact a GM.",
            )

        player_name = remove_prefix(ctx)
        if not player_name:
            log_command(logger, ctx, message="No player given")
            await send_message_and_file(
                channel=ctx.channel,
                title="No player given",
                message="Usage: .player_info <player>",
            )
            return

        player: Player | None = None
        if board.is_chaos():
            # HACK: chaos has same name of players as provinces so we exploit that
            player_name = board.get_province(player_name).name
        try:
            player = board.get_player(player_name)
        except ValueError:
            player = None

        if player is None:
            log_command(logger, ctx, message=f"Player `{player}` not found")
            await send_message_and_file(
                channel=ctx.channel, title=f"Could not find player {player_name}"
            )
            return

        out = player.info(board)
        log_command(logger, ctx, message=f"Got info for player {player}")

        await send_message_and_file(
            channel=ctx.channel, title=player.get_name(), message=out
        )

    @commands.command(brief="outputs all provinces per owner")
    async def all_province_data(self, ctx: commands.Context) -> None:
        """Outputs all provinces sorted by owner."""
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        if not board.orders_enabled:
            perms.assert_gm_only(ctx, "call .all_province_data while orders are locked")

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
            elif (player_role := find_discord_role(owner, ctx.guild.roles)) is not None:
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
        """Changes the user's nickname. Used for chaos games."""
        assert isinstance(ctx.author, Member)
        name = ctx.author.nick
        if name is None:
            name = ctx.author.name
        if "]" in name:
            prefix = name.split("] ", 1)[0]
            prefix = prefix + "] "
        else:
            prefix = ""
        name = remove_prefix(ctx)
        if name == "":
            await send_message_and_file(
                channel=ctx.channel,
                embed_colour=ERROR_COLOUR,
                message="A nickname must be at least 1 character",
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

    @commands.command(brief="Gets the current deadline", aliases=["deadline"])
    async def get_deadline(self, ctx: commands.Context) -> None:
        """Gets the current deadline."""
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)
        deadline = board.data.get("deadline")
        if deadline is None:
            await send_message_and_file(channel=ctx.channel, message="No deadline set")
            return
        await send_message_and_file(
            channel=ctx.channel, message=f"Current deadline: <t:{deadline}:f>"
        )

    @commands.command(brief="Changes your user preferences")
    async def edit_prefs(self, ctx: commands.Context) -> None:
        """Edits your own user preferences.

        Usage:
            `.edit_prefs <commands>`
        """
        assert ctx.guild is not None
        param_commands = remove_prefix(ctx)
        try:
            title, message, colour = parse_user_prefs(
                ctx.author.id, param_commands, manager.get_board(ctx.guild.id)
            )
        except NoGameError:
            title, message, colour = parse_user_prefs(
                ctx.author.id, param_commands, None
            )
        log_command(logger, ctx, message=title)
        await send_message_and_file(
            channel=ctx.channel, title=title, message=message, embed_colour=colour
        )


async def setup(bot):
    """Sets up the cog."""
    cog = CommandCog(bot)
    await bot.add_cog(cog)
