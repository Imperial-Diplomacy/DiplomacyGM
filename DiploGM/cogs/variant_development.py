"""Cog to handle variant development and management."""
import logging
import os

from discord.ext import commands

from DiploGM import perms
from DiploGM.map_parser.adjacencies import verify_adjacencies
from DiploGM.map_parser.vector.vector import get_parser
from DiploGM.models.board import Board
from DiploGM.utils import log_command, send_message_and_file
from DiploGM.manager import Manager
from DiploGM.utils.sanitise import parse_variant_path
logger = logging.getLogger(__name__)
manager = Manager()

class VariantDevelopmentCog(commands.Cog):
    """Bot administration commands, to be used by superusers only."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(brief="Checks the adjacencies of a variant to find potential issues")
    @perms.superuser_only("Checks the adjacencies of a variant to find potential issues")
    async def verify_adjacencies(self, ctx: commands.Context, arg) -> None:
        """Checks the adjacencies of a variant to find potential issues."""
        assert ctx.guild is not None
        gametype = arg if arg else "classic"

        message = verify_adjacencies(gametype)
        log_command(logger, ctx, message=message)
        await send_message_and_file(channel=ctx.channel, message=message)

    @commands.command(brief="Reloads the map parser for a given variant. Useful if a map has been updated.")
    @perms.superuser_only("Reloads the map parser for a given variant. Useful if a map has been updated.")
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


async def setup(bot):
    cog = VariantDevelopmentCog(bot)
    await bot.add_cog(cog)
