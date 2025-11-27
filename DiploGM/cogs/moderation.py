import datetime

import discord.utils
from discord import Member, User
from discord.ext import commands

from DiploGM import perms
from DiploGM.config import IMPDIP_SERVER_ID
from DiploGM.utils import send_message_and_file

NEW_ACCOUNT_WARNING = datetime.timedelta(weeks=2)

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help="Returns all shared guilds between DiploGM and user.")
    @perms.mod_only("find mutuals with user")
    async def membership(self, ctx: commands.Context, user: User) -> None:
        guild = ctx.guild
        if not guild:
            return

        out = f"""
    User: {user.mention} [{user.name}]
    Number of Mutual Servers: {len(user.mutual_guilds)}
    ----
    """

        for shared in sorted(user.mutual_guilds, key=lambda g: g.name):
            out += f"{shared.name}\n"

        await send_message_and_file(
            channel=ctx.channel, title="User Membership Results", message=out
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        guild = member.guild
        hub = self.bot.get_guild(IMPDIP_SERVER_ID)
        if not hub:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        problems = []

        # FRESH ACCOUNT
        age = member.created_at.replace(tzinfo=datetime.timezone.utc) - now
        if age < NEW_ACCOUNT_WARNING:
            msg = f"Fresh account: {age.days} days old"
            problems.append(msg)

        # NOT HUB
        if guild.id != IMPDIP_SERVER_ID:
            hub_member = discord.utils.find(lambda m: m.name == member.name, hub.members)
            if not hub_member:
                msg = "Not a member of the hub server!"
                problems.append(msg)
            elif not discord.utils.find(lambda r: r.name == "ImpDip Verified", hub_member.roles):
                msg = "Not verified on the hub server!"
                problems.append(msg)

        if len(problems) == 0:
            return

        modchannel = discord.utils.find(lambda c: c.name == "mod-log", hub.text_channels)
        modrole = discord.utils.find(lambda r: r.name == "Moderator", hub.roles)
        msg = (
            f"{modrole.mention} - Somebody to watch/interrogate:\n"
            f"User: {member} (ID: {member.id})\n"
            f"Joined: {guild.name} [ID: {guild.id}]\n"
            f"**Problems:**\n"
        )
        for p in problems:
            msg += f"- {p}\n"

        await modchannel.send(msg)

async def setup(bot):
    cog = ModerationCog(bot)
    await bot.add_cog(cog)
