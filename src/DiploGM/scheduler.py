from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
import json
import logging
import random
import re
from typing import TYPE_CHECKING
import uuid

from discord.ext import commands, tasks
from discord import Message, TextChannel, User, utils

from DiploGM.utils.singleton import SingletonMeta
from DiploGM.config import ERROR_COLOUR
from DiploGM.db.database import get_connection
from DiploGM.errors import NoGameError
from DiploGM.models.board import Board
from DiploGM.utils import (
    get_value_from_timestamp,
    send_message_and_file,
    log_command_no_ctx
)
from DiploGM.manager import Manager
from DiploGM.utils.send_message import ErrorMessage

if TYPE_CHECKING:
    from DiploGM.bot import DiploGM
    from DiploGM.utils.request import Request
    from discord.types.member import UserWithMember
    from discord.types.message import Message as MessagePayload
    from discord.types.snowflake import SnowflakeList

logger = logging.getLogger(__name__)
manager = Manager()

LOOP_FREQUENCY_SECONDS = 30
MAX_DELAY = datetime.timedelta(minutes=5)
IMPOSSIBLE_COMMANDS = ["schedule", "create_game", "delete_game"]

@dataclass
class Task:
    """Information about a specific Task. Most of these fields will get passed into the command to be executed."""
    invoking_user_id: int
    invoking_user_name: str
    invoking_msg_id: int
    guild_id: int
    channel_id: int
    created_at: datetime.datetime
    execute_at: datetime.datetime
    command: str
    args: str
    full_command: str
    mentions: list[int]
    role_mentions: list[int]


class Scheduler(metaclass=SingletonMeta):
    """The Scheduler singleton class. This stores tasks and will execute them at the given time."""
    bot: DiploGM

    def __init__(self, bot):
        self.bot = bot
        self.scheduled_storage = "assets/schedule.json"
        self.scheduled_tasks: dict[str, Task] = {}

        try:
            logger.info("Reading stored scheduled tasks")
            with open(self.scheduled_storage, "r", encoding="utf-8") as f:
                read_tasks = json.load(f)
                for task_id, task in read_tasks.items():
                    task["created_at"] = datetime.datetime.fromisoformat(task["created_at"])
                    task["execute_at"] = datetime.datetime.fromisoformat(task["execute_at"])
                    self.scheduled_tasks[task_id] = Task(**task)
            logger.info("Obtained %s stored scheduled tasks", len(self.scheduled_tasks))

        except FileNotFoundError:
            logger.warning(
                "Could not load previous store of scheduled tasks because it does not exist: " +
                "should be located at 'DiploGM/assets/schedule.json'"
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Could not load previous store of scheduled tasks: %s", e)
            raise e

        self.process_scheduled_tasks.start()

    def close(self):
        """Saves the scheduled tasks on shutdown."""
        self.process_scheduled_tasks.cancel()
        with open(self.scheduled_storage, "w", encoding="utf-8") as f:
            task_dict: dict[str, dict] = {}
            for task_id, task in self.scheduled_tasks.items():
                cur_task = asdict(task)
                cur_task["created_at"] = cur_task["created_at"].isoformat()
                cur_task["execute_at"] = cur_task["execute_at"].isoformat()
                task_dict[task_id] = cur_task

            json.dump(task_dict, f)

    async def schedule(self,
                       request: Request,
                       timestamp: str,
                       command_name: str,
                       arguments: str = "") -> tuple[bool, str | None]:
        """Schedules a command to take place at the specified timestamp, with optional arguments.
        Returns True and the task_id on success, and False and the error message on failure."""
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
        user_mentions = [int(m) for m in re.findall(r"<@!?(\d+)>", arguments)]
        role_mentions = [int(m) for m in re.findall(r"<@&(\d+)>", arguments)]

        scheduled_task = Task(
            invoking_user_id=request.author.id,
            invoking_user_name=request.author.name,
            invoking_msg_id=utils.time_snowflake(scheduled_time) | random.getrandbits(22),
            guild_id=request.guild.id,
            channel_id=request.channel.id,
            created_at=now,
            execute_at=scheduled_time,
            command=command_name,
            args=arguments,
            full_command=f"{self.bot.command_prefix}{command_name} {arguments}",
            mentions=user_mentions,
            role_mentions=role_mentions,
        )

        out = (
            f"Scheduled command: `{command_name}`\n"
            f"Arguments: {arguments}\n"
            f"To occur at: {timestamp}"
        )
        await send_message_and_file(
            channel=request.channel, title="Schedule successful!", message=out
        )

        task_id = uuid.uuid4().hex[:8]
        self.scheduled_tasks[task_id] = scheduled_task
        await self.save_scheduled_tasks()
        return True, task_id

    async def schedule_repeating(self,
                                 request: Request,
                                 time_delta: str,
                                 command_name: str,
                                 arguments: str = "") -> tuple[bool, str | None]:
        """Schedules a task to take place time_delta before each deadline.
        Returns True and the task_id on success, or False and the error message on failure."""
        board = manager.get_board(request.guild.id)
        if not (deadline := board.data.get("deadline")):
            return False, ErrorMessage.NO_DEADLINE

        sign = 1
        if time_delta.startswith("-"):
            sign = -1
            time_delta = time_delta[1:]
        if time_delta.isnumeric(): # If it's just a number, assume it's in hours
            hours, minutes = int(time_delta), 0
        else:
            time_match = re.search(r"^((\d+)h)?((\d+)m)?$", time_delta)
            if not time_match or not (time_match.group(2) or time_match.group(4)):
                return False, ErrorMessage.IMPROPER_TIME_LENGTH
            hours = int(time_match.group(2)) if time_match.group(2) else 0
            minutes = int(time_match.group(4)) if time_match.group(4) else 0
        seconds_before = sign * (60 * 60 * hours + 60 * minutes)
        timestamp = deadline - seconds_before

        success, task_id = await self.schedule(request, str(timestamp), command_name, arguments)
        if not task_id:
            return False, ErrorMessage.UNKNOWN_ERROR
        if not success:
            return False, task_id
        board.set_data(["scheduled_repeated", task_id], f"{seconds_before}:{command_name}:{arguments}")
        get_connection().execute_arbitrary_sql(
            "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
            (board.board_id, f"scheduled_repeated/{task_id}", f"{seconds_before}:{command_name}:{arguments}"),
        )
        return True, task_id

    async def unschedule(self, request: Request, task_id: str):
        """Removes a task from the schedule."""
        task_id = task_id.strip()

        if task_id == "all":
            ids = [
                id
                for id, task in self.scheduled_tasks.items()
                if task.guild_id == request.guild.id
            ]
            for cur_task_id in ids:
                del self.scheduled_tasks[cur_task_id]
                await self.save_scheduled_tasks()

            try:
                board = manager.get_board(request.guild.id)
                for cur_task_id in ids:
                    board.set_data(["scheduled_repeated", cur_task_id], None)
                    get_connection().execute_arbitrary_sql(
                        "DELETE FROM board_parameters WHERE board_id = ? AND parameter_key = ?",
                        (board.board_id, f"scheduled_repeated/{cur_task_id}"),
                    )
            except NoGameError:
                pass

            await send_message_and_file(
                channel=request.channel,
                message=f"Deleted all {len(ids)} scheduled tasks for this guild.",
            )
            return

        try:
            task = self.scheduled_tasks[task_id]
            if task.guild_id != request.guild.id:
                raise KeyError
            del self.scheduled_tasks[task_id]
            await self.save_scheduled_tasks()
            await send_message_and_file(
                channel=request.channel,
                message=f"Deleted scheduled task: {task.command} for {int(task.execute_at.timestamp())}",
            )
        except KeyError:
            await send_message_and_file(
                channel=request.channel,
                title="Error!",
                message=f"No scheduled task correlates with the ID: {task_id}",
                embed_colour=ERROR_COLOUR,
            )

        try:
            board = manager.get_board(request.guild.id)
            board.set_data(["scheduled_repeated", task_id], None)
            get_connection().execute_arbitrary_sql(
                "DELETE FROM board_parameters WHERE board_id = ? AND parameter_key = ?",
                (board.board_id, f"scheduled_repeated/{task_id}"),
            )
        except NoGameError:
            pass

    async def view_schedule(self, request: Request) -> dict[str, Task]:
        """Returns a Dict of all tasks and task IDs for the server."""
        return {
            id: task
            for id, task in self.scheduled_tasks.items()
            if task.guild_id == request.guild.id
        }

    async def adjust_repeated_tasks(self, board: Board, delayed_deadline: datetime.timedelta):
        """Adjusts all repeated tasks for a board to the new deadline.

        Args:
            board (Board): Board object to adjust repeated tasks for
            delayed_deadline (int): Amount the deadline has been delayed by in seconds
        """

        repeated_tasks = board.data.get("scheduled_repeated", {})
        for task_id in repeated_tasks.keys():
            if task_id not in self.scheduled_tasks:
                continue
            self.scheduled_tasks[task_id].execute_at += delayed_deadline
        await self.save_scheduled_tasks()

    async def refresh_repeated_tasks(self, request: Request) -> tuple[bool, str | None]:
        """Schedules all stored repeated tasks from a given server.
        Primarily used to refresh tasks after an adjudication."""
        board = manager.get_board(request.guild.id)
        now = datetime.datetime.now(datetime.timezone.utc)
        if not (deadline_str := board.data.get("deadline")):
            return False, "No deadline found in game %s"

        deadline = datetime.datetime.fromtimestamp(int(deadline_str), tz=datetime.timezone.utc)
        task_list = board.data.get("scheduled_repeated", {})
        for task_id, task_details in task_list.items():
            if task_id in self.scheduled_tasks:
                del self.scheduled_tasks[task_id]
            seconds_before, command_name, content = task_details.split(":", 2)
            new_timstamp = deadline - datetime.timedelta(seconds=int(seconds_before))
            if new_timstamp <= now:
                continue
            success, new_task_id = await self.schedule(request, str(new_timstamp.timestamp()), command_name, content)
            if new_task_id is None or not success:
                logger.warning("Failed to schedule task")
                continue
            self.scheduled_tasks[task_id] = self.scheduled_tasks.pop(new_task_id)
            await self.save_scheduled_tasks()
        return True, None

    async def _process_task(self, task_id: str, task: Task, now: datetime.datetime):
        channel = self.bot.get_channel(task.channel_id)
        if not channel or not isinstance(channel, TextChannel):
            del self.scheduled_tasks[task_id]
            await self.save_scheduled_tasks()
            return

        # skip over stale tasks, suspected change of state not worthy of continuing automatic behaviour
        # guard in case bot goes down for extended periods
        delta = now - task.execute_at
        if delta > MAX_DELAY:
            logger.warning(
                "Skipping stale task %s: Could not handle on time. " +
                "(missed by '%s') which is greater than maximum allowed time '%s'",
                task_id,
                now - task.execute_at,
                MAX_DELAY
            )
            await send_message_and_file(
                channel=channel,
                message=f"Skipping stale task {task_id}: Could not handle on time " +
                        f"(Expected: <t:{int(task.created_at.timestamp())}:f>)\nTask: {task.full_command}",
                embed_colour=ERROR_COLOUR,
            )
            del self.scheduled_tasks[task_id]
            await self.save_scheduled_tasks()
            return

        user = self.bot.get_user(task.invoking_user_id)
        if user is None:
            await send_message_and_file(
                channel=channel,
                message=f"Skipping task {task_id}: Could not find invoking user\nTask: {task.full_command}",
                embed_colour=ERROR_COLOUR,
            )
            del self.scheduled_tasks[task_id]
            await self.save_scheduled_tasks()
            return

        out = (
            f"Command: {task.command}\n"
            f"Invoking: {task.full_command}\n"
            f"Scheduled by: {user.mention}\n"
            f"Scheduled at: <t:{int(task.created_at.timestamp())}:f>"
        )
        await send_message_and_file(channel=channel, title="Executing scheduled command!", message=out)

        mentions_users: list[UserWithMember] = []
        for user_id in task.mentions:
            if mentioned_user := self.bot.get_user(user_id):
                mentions_users.append(self.get_payload_user_from_user(mentioned_user))

        mention_roles: SnowflakeList = []
        mention_roles.extend(task.role_mentions)
        message_data: MessagePayload = {
            "id": task.invoking_msg_id,
            "author": self.get_payload_user_from_user(user),
            "content": task.full_command,
            "timestamp": task.execute_at.isoformat(),
            "edited_timestamp": None,
            "tts": False,
            "mention_everyone": False,
            "mentions": mentions_users,
            "mention_roles": mention_roles,
            "attachments": [],
            "embeds": [],
            "pinned": False,
            "type": 1,
            "channel_id": channel.id,
        }
        message = Message(state=self.bot._connection, channel=channel, data=message_data)

        # delete task immediately to prevent long tasks carrying over to new loops
        del self.scheduled_tasks[task_id]
        await self.save_scheduled_tasks()
        try:
            log_command_no_ctx(
                logger,
                task.full_command,
                channel,
                user.name,
                f"Executing command scheduled by '{task.invoking_user_name}' at <t:{int(task.created_at.timestamp())}:f>",
            )
            await self.bot.process_commands(message)
        except Exception as e:
            await channel.send(
                f"Failure to invoke scheduled command.\n"
                f"Command: `{task.full_command}`\n"
                f"Scheduled at: <t:{int(task.created_at.timestamp())}:f>"
            )
            user = self.bot.get_user(task.invoking_user_id)
            if user:
                await channel.send(f"Alert: {user.mention}")
            raise e

    @tasks.loop(seconds=LOOP_FREQUENCY_SECONDS)
    async def process_scheduled_tasks(self):
        """Recurring loop to process scheduled tasks on time (within a margin of error)

        Usage: 

        Note:
            Can potentially debumblify bumbled users

        Args:

        Returns:
            None

        Raises:
            None:
            Messages:
                Skipping stale task : could not handle on time
                Could not find invoking user
                Failed to invoke scheduled command
        """

        # TODO: Clean up reporting and add logging for deserialisation errors
        now = datetime.datetime.now(datetime.timezone.utc)
        due = {
            id: task
            for id, task in self.scheduled_tasks.items()
            if task.execute_at <= now
        }

        for task_id, task in due.items():
            try:
                await self._process_task(task_id, task, now)
            except Exception as e:
                logger.exception(e)


    @process_scheduled_tasks.before_loop
    async def before_process_scheduled_tasks(self):
        await self.bot.wait_until_ready()

    async def save_scheduled_tasks(self):
        logger.info("Saving %s stored scheduled tasks", len(self.scheduled_tasks))
        with open(self.scheduled_storage, "w", encoding="utf-8") as f:
            task_dict: dict[str, dict] = {}
            for task_id, task in self.scheduled_tasks.items():
                cur_task = asdict(task)
                cur_task["created_at"] = cur_task["created_at"].isoformat()
                cur_task["execute_at"] = cur_task["execute_at"].isoformat()
                task_dict[task_id] = cur_task
            json.dump(task_dict, f)

    @staticmethod
    def get_payload_user_from_user(user: User) -> UserWithMember:
        return {
            "id": user.id,
            "username": user.name,
            "discriminator": user.discriminator,
            "avatar": user.avatar.url if user.avatar else None,
            "global_name": user.global_name,
            "bot": user.bot,
            "system": user.system,
            "mfa_enabled": False,
            "locale": "",
            "verified": True,
            "email": None,
            "flags": 0,
            "premium_type": 0,
            "public_flags": user.public_flags.value,
        }
