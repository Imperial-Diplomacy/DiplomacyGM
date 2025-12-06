import logging

from discord import TextChannel
from discord.ext import commands
import random

from DiploGM.config import (
    IMPDIP_SERVER_ID,
    IMPDIP_BOT_WIZARD_ROLE,
    IMPDIP_SERVER_BOT_STATUS_CHANNEL_ID,
)
from DiploGM.bot import DiploGM
from DiploGM import perms
from DiploGM.utils import send_message_and_file
from DiploGM.manager import Manager

logger = logging.getLogger(__name__)
manager = Manager()


class DevelopmentCog(commands.Cog):
    """
    Superuser features primarily used for Development of the bot
    .su_dashboard
    .shutdown_the_bot_yes_i_want_to_do_this
    """

    bot: DiploGM

    def __init__(self, bot: DiploGM):
        self.bot = bot

    @commands.command(hidden=True)
    @perms.superuser_only("show the superuser dashboard")
    async def su_dashboard(self, ctx: commands.Context):

        extensions_body = ""
        for extension in sorted(self.bot.get_all_extensions()):
            if extension in self.bot.extensions.keys():
                extensions_body += "- :white_check_mark: "
            else:
                extensions_body += "- :x: "
            extensions_body += f"{extension}\n"

        cogs_body = ""
        for cog in self.bot.cogs.keys():
            cogs_body += f"- {cog}\n"

        guild = self.bot.get_guild(IMPDIP_SERVER_ID)
        bot_wizard_role = guild.get_role(IMPDIP_BOT_WIZARD_ROLE) if guild else None
        bot_wizards = bot_wizard_role.members if bot_wizard_role else []
        footer = random.choice(
            [f"Rather upset at {bot_wizard.nick} >:(" for bot_wizard in bot_wizards]
            + [
                f"eolhc keeps {random.choice(['murdering', 'stabbing'])} me",
                f"aahoughton, I don't recognise your union!",
            ]
        )

        await send_message_and_file(
            channel=ctx.channel,
            title=f"DiplomacyGM Dashboard",
            fields=[("Extensions", extensions_body), ("Loaded Cogs", cogs_body)],
            footer_content=footer,
        )

    @commands.command(hidden=True)
    @perms.superuser_only("shutdown the bot")
    async def shutdown_the_bot_yes_i_want_to_do_this(self, ctx: commands.Context):
        await send_message_and_file(
            channel=ctx.channel, title=f"Why would you do this to me?", message=f"Shutting down"
        )
        channel = self.bot.get_channel(IMPDIP_SERVER_BOT_STATUS_CHANNEL_ID)
        if channel and isinstance(channel, TextChannel):
            await channel.send(f"{ctx.author.mention} stabbed me")
        await self.bot.close()


async def setup(bot: DiploGM):
    cog = DevelopmentCog(bot)
    await bot.add_cog(cog)


async def teardown(bot: DiploGM):
    pass
