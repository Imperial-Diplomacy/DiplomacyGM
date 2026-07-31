"""Cog to handle variant development and management."""

import asyncio
import colorsys
import logging
import os
from subprocess import PIPE

from discord.ext import commands

from DiploGM import perms
from DiploGM.map_parser.adjacencies import verify_adjacencies
from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.utils import log_command, send_message_and_file
from DiploGM.manager import Manager
from DiploGM.models.player import Player
from DiploGM.models.province import Province
from DiploGM.utils.sanitise import parse_variant_path

logger = logging.getLogger(__name__)
manager = Manager()


class VariantDevelopmentCog(commands.Cog):
    """Bot administration commands, to be used by superusers only."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        brief="Checks the adjacencies of a variant to find potential issues"
    )
    @perms.variant_dev_only("verify adjacencies")
    async def verify_adjacencies(self, ctx: commands.Context, arg) -> None:
        """Checks the adjacencies of a variant to find potential issues."""
        assert ctx.guild is not None
        gametype = arg if arg else "classic"

        message = verify_adjacencies(gametype)
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)

    @commands.command(
        brief="Reloads the map parser for a given variant. Useful if a map has been updated."
    )
    @perms.variant_dev_only("reload the map parser")
    async def reload_variant(self, ctx: commands.Context, arg) -> None:
        """Reloads the map parser for a given variant. Useful if a map has been updated."""
        assert ctx.guild is not None
        try:
            variant_path = parse_variant_path(arg)
            if not os.path.isdir(variant_path):
                message = f"Variant {arg} does not exist."
            # Remove adjacency cache to force a reload
            if os.path.isfile(f"assets/{arg}_adjacencies.txt"):
                os.remove(f"assets/{arg}_adjacencies.txt")

            parser_result = get_parser(arg, force_refresh=True)
            if isinstance(parser_result, str):
                message = parser_result
            else:
                parser_result.parse()
                message = manager.reload_variant(arg)
        except ValueError as e:
            message = str(e)

        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)

    @commands.command(brief="Pulls changes from the Git repository.")
    @perms.variant_dev_only("pull changes from the Git repository")
    async def update_variant(
        self, ctx: commands.Context, variant: str, branch: str = "main"
    ) -> None:
        """Pulls changes from the Git repository."""
        assert ctx.guild is not None

        try:
            variant_dir = parse_variant_path(variant, return_parent=True)
        except ValueError as e:
            message = str(e)
            log_command(logger, ctx, message=message)
            await send_message_and_file(channel=ctx.channel, message=message)
            return

        async def run_command(*args) -> bool:
            process = await asyncio.create_subprocess_exec(
                "git", *args, stdout=PIPE, stderr=PIPE, cwd=variant_dir
            )
            _, err = await process.communicate()
            if process.returncode == 0:
                return True
            message = f"git {' '.join(args)} failed: {err.decode().strip()}"
            log_command(logger, ctx, message=message)
            await send_message_and_file(channel=ctx.channel, message=message)
            return False

        if not await run_command("fetch"):
            return
        if not await run_command("checkout", branch):
            return
        if not await run_command("pull"):
            return

        message = f"Updated `{variant}` on branch `{branch}`"
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)

    @commands.command(brief="Views each power's influence.")
    @perms.variant_dev_only("view influence")
    async def view_influence(self, ctx: commands.Context, variant: str) -> None:
        """Generates maps showing influence for each power"""
        assert ctx.guild is not None
        success, message = manager.create_game(ctx.message.id, variant, save_board = False)
        if not success:
            log_command(logger, ctx, message=message)
            await send_message_and_file(channel=ctx.channel, message=message)
            return

        board = manager.get_board(ctx.message.id)
        board.delete_all_units()
        starting_scs: dict[Player, set[Province]] = {p: set() for p in board.players}
        for province in board.provinces:
            if province.has_supply_center and (owner := province.owner) is not None:
                starting_scs[owner].add(province)
        distance_to_players: dict[int, Player | None] = {5: None}
        for i in range(1, 5):
            board.add_new_player(f"Distance {i}", "FF0000")
            distance_to_players[i] = board.get_player(f"Distance {i}")

        for player, start in starting_scs.items():
            color = player.default_color
            hsv = colorsys.rgb_to_hsv(int(color[0:2], 16)/256, int(color[2:4], 16)/256, int(color[4:6], 16)/256)
            r, g, b = colorsys.hsv_to_rgb(hsv[0], hsv[1], 0.2)
            board.set_data(["players", player.name, "custom_color"], f"{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
            for i in range(1, 5):
                r, g, b = colorsys.hsv_to_rgb(hsv[0], hsv[1], 0.2 + 0.15 * i)
                board.set_data(["players", f"Distance {i}", "custom_color"], f"{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")

            distance_to_players[0] = player
            distances = dict.fromkeys(board.provinces, 5)
            for province in start:
                distances[province] = 0
                for comp_province in distances:
                    distances[comp_province] = min(distances[comp_province], province.get_distance(comp_province, 4))
            for province in board.provinces:
                province.owner = distance_to_players[distances[province]]
            file, file_name = manager.draw_map(ctx.message.id, color_mode="custom")
            await send_message_and_file(
                channel=ctx.channel,
                title=f"{player.name}",
                message=f"Influence map for {player.name}",
                file=file,
                file_name=file_name,
                convert_svg=True,
                file_in_embed=False,
                dpi=board.data["svg config"].get("dpi", 200),
            )
            await asyncio.sleep(0)
            board.set_data(["players", player.name, "custom_color"], player.default_color)
        manager.total_delete(ctx.message.id)

async def setup(bot):
    cog = VariantDevelopmentCog(bot)
    await bot.add_cog(cog)
