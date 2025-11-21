import logging

from discord.ext import commands

from discord.ext.commands import (
    ExtensionNotFound,
    ExtensionNotLoaded,
    ExtensionAlreadyLoaded,
    NoEntryPointError,
    ExtensionFailed,
)

from DiploGM.config import (
    ERROR_COLOUR,
    PARTIAL_ERROR_COLOUR,
)
from DiploGM.bot import DiploGM
from DiploGM import perms
from DiploGM.utils import send_message_and_file
from DiploGM.manager import Manager

logger = logging.getLogger(__name__)
manager = Manager()


class ExtensionManagementCog(commands.Cog):
    """
    Superuser features for managing active extensions of the bot.
    .extension_unload
    .extension_load
    .extension_reload
    """

    bot: DiploGM

    def __init__(self, bot: DiploGM):
        self.bot = bot

    @commands.command(hidden=True)
    @perms.superuser_only("unloaded extension")
    async def extension_unload(self, ctx: commands.Context, extension: str):
        try:
            await self.bot.unload_diplogm_extension(extension)
        except ExtensionNotFound:
            status=f"Extension was not found"
            colour=ERROR_COLOUR
        except ExtensionNotLoaded:
            status = f"Extension was not loaded"
            colour=PARTIAL_ERROR_COLOUR
        else:
            status = f"Unloaded Extension"
            colour = None
        finally:
            await send_message_and_file(
                channel=ctx.channel,
                embed_colour=colour,
                title=f"{status}: {extension}"
            )

    @commands.command(hidden=True)
    @perms.superuser_only("load extension")
    async def extension_load(self, ctx: commands.Context, extension: str):
        try:
            await self.bot.load_diplogm_extension(extension)
        except ExtensionNotFound:
            status = "Extension was not found"
            colour = ERROR_COLOUR
        except ExtensionAlreadyLoaded:
            status = "Extension was already loaded"
            colour = PARTIAL_ERROR_COLOUR
        except NoEntryPointError:
            status = "Extension has no setup function"
            colour = ERROR_COLOUR
        except ExtensionFailed:
            status = "Extension failed to load"
            colour = ERROR_COLOUR
        else:
            status = "Loaded extension"
            colour = None
        finally:
            await send_message_and_file(
                channel=ctx.channel,
                embed_colour=colour,
                title=f"{status}: {extension}"
            )

    @commands.command(hidden=True)
    @perms.superuser_only("reload extension")
    async def extension_reload(self, ctx: commands.Context, extension: str):
        try:
            await self.bot.reload_diplogm_extension(extension)
        except ExtensionNotFound:
            status=f"Extension was not found"
            colour=ERROR_COLOUR
        except ExtensionNotLoaded:
            status=f"Extension was not loaded",
            colour=PARTIAL_ERROR_COLOUR
        except ExtensionAlreadyLoaded:
            status=f"Extension was unload but could not be loaded as it was already loaded",
            colour=PARTIAL_ERROR_COLOUR
        except NoEntryPointError:
            status=f"Extension was unloaded but now has no setup function",
            colour=ERROR_COLOUR
        except ExtensionFailed:
            status=f"Extension failed to load",
            colour=ERROR_COLOUR
        else:
            status=f"Reloaded Extension"
            colour=None
        finally:
            await send_message_and_file(
                channel=ctx.channel,
                embed_colour=colour,
                title=f"{status}: {extension}"
            )

async def setup(bot: DiploGM):
    cog = ExtensionManagementCog(bot)
    await bot.add_cog(cog)


async def teardown(bot: DiploGM):
    pass
