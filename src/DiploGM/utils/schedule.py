import datetime
import logging
import random
import re
import uuid

import discord
from discord.ext import commands

from DiploGM.utils.request import Request
from DiploGM.utils import get_value_from_timestamp, send_message_and_file
from DiploGM.manager import Manager
from DiploGM.utils.send_message import ErrorMessage

logger = logging.getLogger(__name__)
manager = Manager()

IMPOSSIBLE_COMMANDS = ["schedule", "create_game", "delete_game"]


async def schedule(request: Request,
                   timestamp: str,
                   command_name: str,
                   content: str = "") -> tuple[bool, str | None]:
    now = datetime.datetime.now(datetime.timezone.utc)
    scheduled_time = get_value_from_timestamp(timestamp)
    if not scheduled_time:
        return False, ErrorMessage.IMPROPER_TIMESTAMP

    # check schedule time is in the future
    scheduled_time = datetime.datetime.fromtimestamp(scheduled_time, tz=datetime.timezone.utc)
    if scheduled_time <= now:
        return False, ErrorMessage.COMMAND_IN_PAST

    # check command is real and prevent recursive scheduling
    command_name = command_name.removeprefix(str(self.bot.command_prefix))
    cmd: commands.Command | None = self.bot.get_command(command_name)
    if cmd is None:
        return False, ErrorMessage.UNKNOWN_COMMAND
    if command_name in IMPOSSIBLE_COMMANDS:
        return False, ErrorMessage.UNSCHEDULABLE_COMMAND
    user_mentions = [int(m) for m in re.findall(r"<@!?(\d+)>", content)]
    role_mentions = [int(m) for m in re.findall(r"<@&(\d+)>", content)]

    scheduled_task = {
        "invoking_user_id": request.author.id,
        "invoking_user_name": request.author.name,
        "invoking_msg_id": discord.utils.time_snowflake(scheduled_time) | random.getrandbits(22),
        "guild_id": request.guild.id,
        "channel_id": request.channel.id,
        "created_at": now,
        "execute_at": scheduled_time,
        "command": command_name,
        "args": content,
        "full_command": f"{self.bot.command_prefix}{command_name} {content}",
        "mentions": user_mentions,
        "role_mentions": role_mentions,
    }

    out = (
        f"Scheduled command: `{command_name}`\n"
        f"Arguments: {content}\n"
        f"To occur at: {timestamp}"
    )
    await send_message_and_file(
        channel=request.channel, title="Schedule successful!", message=out
    )

    task_id = uuid.uuid4().hex[:8]
    self.scheduled_tasks[task_id] = scheduled_task
    await self.save_scheduled_tasks()
    return True, task_id

async def refresh_repeated_tasks(request: Request):
    """Schedules all stored repeated tasks from a given server.
    Primarily used to refresh tasks after an adjudication."""
    board = manager.get_board(request.guild.id)
    now = datetime.datetime.now(datetime.timezone.utc)
    if not (deadline_str := board.data.get("deadline")):
        logger.warning("No deadline found in game %s", request.guild.id)
        return
    deadline = datetime.datetime.fromtimestamp(int(deadline_str), tz=datetime.timezone.utc)
    task_list = board.data.get("scheduled_repeated", {})
    for task_id, task_details in task_list.items():
        if task_id in self.scheduled_tasks:
            del self.scheduled_tasks[task_id]
        seconds_before, command_name, content = task_details.split(":", 2)
        new_timstamp = deadline - datetime.timedelta(seconds=int(seconds_before))
        if new_timstamp <= now:
            continue
        new_task_id = await self.schedule(request, str(new_timstamp.timestamp()), command_name, content=content)
        if new_task_id is None:
            logger.warning("Failed to schedule task")
            continue
        self.scheduled_tasks[task_id] = self.scheduled_tasks.pop(new_task_id)
