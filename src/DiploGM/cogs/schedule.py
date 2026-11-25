"""The Schedule cog. Many of the functions here call the Scheduler."""
import datetime
import logging

from discord.ext import commands
from discord import TextChannel

from DiploGM.bot import DiploGM
from DiploGM import perms
from DiploGM.scheduler import Task
from DiploGM.utils import send_message_and_file
from DiploGM.manager import Manager
from DiploGM.utils.request import Request
from DiploGM.utils.send_message import send_error

logger = logging.getLogger(__name__)
manager = Manager()

LOOP_FREQUENCY_SECONDS = 30
MAX_DELAY = datetime.timedelta(minutes=5)
IMPOSSIBLE_COMMANDS = ["schedule", "create_game", "delete_game"]


class ScheduleCog(commands.Cog):
    bot: DiploGM

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="schedule",
        brief="Schedule a time for command execution",
        aliases=["s", "sched"],
        help="""
    Usage:
    .schedule <timestamp> <command> <args>
    .schedule <timestamp> view_map dark
    .schedule <timestamp> ping_players <timestamp> <message>
        """,
    )
    @perms.gm_only("schedule a command")
    async def schedule(self,
                       ctx: commands.Context,
                       timestamp: str,
                       command_name: str,
                       *,
                       content: str = "") -> str | None:
        """Schedule a command for execution at a time in the future

        Usage: 
            Used as `.schedule <timestamp> <command_name> <content>`

        Note:
            List of commands that can't be scheduled: "schedule", "create_game", "delete_game"
            Scheduling saved to json file for persistent storage in case of bot restart
            Schedulings identified by the unique message ID of the invoking message

        Args:
            ctx (commands.Context): Context from discord regarding command invocation
            timestamp (str): Discord formatted timestamp UNIXEPOCH code
            command_name (str): Name of command to schedule execution
            content (str): Arguments of the regular command that is being scheduled

        Returns:
            None

        Raises:
            None:
            Messages:
                Did not give a timestamp
                Don't schedule a command in the past
                Command could not be understood (not found)
                Command can't be scheduled (in IMPOSSIBLE_COMMANDS)
        """

        assert ctx.guild is not None and isinstance(ctx.channel, TextChannel)
        if "\n" in content:
            for i, line in enumerate(content.split("\n")):
                if i == 0:
                    line = f"{timestamp} {command_name} {line}"
                params = line.split(maxsplit=2)
                await self.schedule(ctx, params[0], params[1], content=params[2] if len(params) > 2 else "")
            return
        request = Request(ctx.guild, ctx.channel, ctx.author)
        success, message = await self.bot.scheduler.schedule(request, timestamp, command_name, content)
        if not success and message:
            await send_error(ctx.channel, message)

    @commands.command(
        name="schedule_repeating",
        brief="Schedule a time for command execution that occurs every phase",
    )
    @perms.gm_only("schedule a repeating command")
    async def schedule_repeating(
        self,
        ctx: commands.Context,
        time_delta: str,
        command_name: str,
        *,
        content: str = "",
    ):
        assert ctx.guild is not None and isinstance(ctx.channel, TextChannel)
        if "\n" in content:
            for i, line in enumerate(content.split("\n")):
                if i == 0:
                    line = f"{time_delta} {command_name} {line}"
                params = line.split(maxsplit=2)
                await self.schedule_repeating(ctx, params[0], params[1], content=params[2] if len(params) > 2 else "")
            return

        request = Request(ctx.guild, ctx.channel, ctx.author)
        success, message = await self.bot.scheduler.schedule_repeating(request, time_delta, command_name, content)
        if not success and message:
            await send_error(ctx.channel, message)

    @commands.command(
        name="unschedule",
        brief="Unschedule a scheduled command",
        aliases=["us", "unsched"],
        help="""
    Usage:
    .unschedule <task_id>
    .unschedule all - remove all scheduled tasks
        """,
    )
    @perms.gm_only("unschedule a command")
    async def unschedule(self, ctx: commands.Context, task_id: str):
        """Unschedule a currently scheduled command execution

        Usage: 
            Used as `.unschedule <task_id>`

        Note:

        Args:
            ctx (commands.Context): Context from discord regarding command invocation
            task_id (str): "all" or unique message ID for task

        Returns:
            None

        Raises:
            None:
            Messages:
                No task correlates to the given ID
        """

        assert ctx.guild is not None and isinstance(ctx.channel, TextChannel)
        request = Request(ctx.guild, ctx.channel, ctx.author)
        await self.bot.scheduler.unschedule(request, task_id)

    @commands.command(
        name="view_schedule",
        brief="View scheduled commands.",
        aliases=["vs", "vsched", "viewsched"]
    )
    @perms.gm_only("view command schedule")
    async def view_schedule(self, ctx: commands.Context):
        """View all currently scheduled commands for the server

        Usage: 
            Used as `.view_schedule`

        Note:
            Limited to the current server

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None and isinstance(ctx.channel, TextChannel)
        request = Request(ctx.guild, ctx.channel, ctx.author)
        guild_tasks: dict[str, Task] = await self.bot.scheduler.view_schedule(request)

        guild_tasks = dict(
            sorted(guild_tasks.items(), key=lambda pair: pair[1].execute_at)
        )

        out = ["(sorted by soonest)"]
        for task_id, task in guild_tasks.items():
            user = self.bot.get_user(task.invoking_user_id)
            s = f"Task ID = `{task_id}`:\n- [{user.mention if user else task.invoking_user_name}] " + \
                f"-> `{task.command}` at <t:{int(task.execute_at.timestamp())}:f>"
            if len(task.args) != 0:
                s += f"\n  - Arguments: {task.args}"

            out.append(s)

        out = "\n".join(out)

        await send_message_and_file(
            channel=ctx.channel, title=f"Scheduled tasks for {request.guild.name}", message=out
        )

async def setup(bot):
    cog = ScheduleCog(bot)
    await bot.add_cog(cog)
