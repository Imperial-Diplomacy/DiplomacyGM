import logging

import discord
from discord.ext import commands

from DiploGM.models.rep_delta import ReputationDelta, SQLiteReputationDeltaRepository
from DiploGM.perms import is_moderator, mod_only
from DiploGM.utils.send_message import send_message_and_file

logger = logging.getLogger(__name__)


class ReputationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rep_repo = SQLiteReputationDeltaRepository()

    @commands.group(name="rep")
    async def rep(self, ctx: commands.Context):
        await send_message_and_file(channel=ctx.channel, message="Valid commands are: *add*, *delete*, and *view*")

    @rep.command(
        name="add", 
        brief="Add a reputation delta",
        description="",
        help="Usage: .rep add <user> <hours> <reason>"
    )
    @mod_only("add a reputation delta")
    async def rep_add(self, ctx: commands.Context, user: discord.User, amount: int, *, reason: str = "unspecified"):
        delta = ReputationDelta(user.id, amount, reason=reason)
        self.rep_repo.save(delta)

        out = (
            f"ID: {delta.id}\n"
            f"User: {user.mention}\n"
            f"Change: {amount}\n"
        )
        await send_message_and_file(channel=ctx.channel, title="Reputation Logged!", message=out)

    @rep.command(
        name="delete", 
        brief="Delete a reputation delta",
        description="Provide a rep delta id to delete.",
        help="Usage: .rep delete <id>"
    )
    @mod_only("delete a reputation delta")
    async def rep_delete(self, ctx: commands.Context, id: int):
        self.rep_repo.delete(id)
        await send_message_and_file(channel=ctx.channel, message=f"Deleted Reputation Delta with ID of {id}")

    @rep.command(
        name="view",
        brief="View a user's rep history",
        description="",
        help="Usage: .rep view <user> <history_check>\nHistory check default = 'none', Moderators can use 'all' to fetch reasons"
    )
    async def rep_view(self, ctx: commands.Context, user: discord.User, history_check: str = "none"):
        history = list(self.rep_repo.find_by(lambda d: d.user_id == user.id))
    
        out = f"### Overall Value: {sum(d.delta for d in history)}\n"
        for delta in history:
            out += f"({delta.id}): {delta.created_at}\n"
            out += f"- Change: {delta.delta}\n"
            if is_moderator(ctx.author) and history_check == "all":
                out += f"- Reason: {delta.reason}\n"

        await send_message_and_file(channel=ctx.channel, title=f"{user.name} reputation history", message=out)


async def setup(bot):
    cog = ReputationCog(bot)
    await bot.add_cog(cog)
