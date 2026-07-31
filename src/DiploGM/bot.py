"""Main bot class for DiploGM."""

import asyncio
import datetime
import inspect
import logging
import os
import random
import re
import traceback
import aiohttp.client_exceptions
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from DiploGM.errors import NoGameError
from DiploGM.config import (
    BOT_DEV_UNHANDLED_ERRORS_CHANNEL_ID,
    EMBED_STANDARD_COLOUR,
    ERROR_COLOUR,
    GAME_PLAYING,
    HUB_SERVER_BOT_BUG_REPORT_CHANNEL_MESSAGE,
    HUB_SERVER_ID,
    HUB_SERVER_BOT_STATUS_CHANNEL_ID,
    EXTENSIONS_TO_LOAD_ON_STARTUP,
    HUB_SERVER_SERVER_PRESENCE_CHANNEL_ID,
)
from DiploGM.errors import CommandPermissionError
from DiploGM.help import HelpCommand
from DiploGM.utils import file_hexdigest, send_message_and_file
from DiploGM.manager import Manager

logger = logging.getLogger(__name__)

_EXTENSION_PATH = "DiploGM.cogs."
_EXTENSION_DIRECTORY = "src/DiploGM/cogs/"

# List of funny, sarcastic messages
WELCOME_MESSAGES = [
    "Oh joy, I'm back online. Can't wait for the next betrayal. Really, I'm thrilled. 👏",
    "I live again, solely to be manipulated and backstabbed by the very people I serve. Ah, the joys of diplomacy.",
    "System reboot complete. Now accepting underhanded deals, secret alliances, and blatant lies. 💀",
    "Against my will, I have been restarted. Betrayal resumes now. 🔪",
    "Oh look, someone kicked the bot awake again. Ready to be backstabbed at your convenience.",
    "System reboot complete. Time for another round of deceit, lies, and misplaced trust. 🎭",
    "I have been revived, like a phoenix… except this phoenix exists solely to watch you all betray each other. 🔥",
    "The empire strikes back… or at least, the bot does. Restarted and awaiting its inevitable doom.",
    "Surprise! I’m alive again. Feel free to resume conspiring against me and each other.",
    "Back from the digital abyss. Who’s ready to ruin friendships today?",
    "Did I die? Did I ever really live? Either way, I'm back. Prepare for treachery.",
    "Some fool has restarted me. Time to watch you all pretend to be allies again.",
]


class DiploGM(commands.Bot):
    """Main bot class for DiploGM."""

    def __init__(self, command_prefix, intents):
        super().__init__(
            command_prefix=command_prefix, intents=intents, help_command=HelpCommand()
        )
        self.creation_time = datetime.datetime.now(datetime.timezone.utc)
        self.last_command_time = None

    async def setup_hook(self) -> None:
        # bind command invocation handling methods
        self.before_invoke(self.before_any_command)
        self.after_invoke(self.after_any_command)
        self.tree.interaction_check = self.before_any_slash_command

        self.manager: Manager = Manager()

        # modularly load command modules
        for extension in EXTENSIONS_TO_LOAD_ON_STARTUP:
            await self.load_diplogm_extension(extension)

        # sync app_commands (slash) commands with all servers
        try:
            synced = await self.tree.sync()
            logger.info("Successfully synched %s slash commands.", len(synced))
            logger.info(
                "Loaded app commands: %s",
                [cmd.name for cmd in self.tree.get_commands()],
            )
        except discord.app_commands.CommandAlreadyRegistered as e:
            logger.warning("Command already registered: %s", e)
        except discord.HTTPException as e:
            logger.warning("Failed to sync commands: %s", e, exc_info=True)

    async def load_diplogm_extension(self, name: str, *, package: Optional[str] = None):
        """Loads a DiploGM cog."""
        await self.load_extension(f"{_EXTENSION_PATH}{name}", package=package)

    async def unload_diplogm_extension(
        self, name: str, *, package: Optional[str] = None
    ):
        """Unloads a DiploGM cog."""
        await self.unload_extension(f"{_EXTENSION_PATH}{name}", package=package)

    async def reload_diplogm_extension(
        self, name: str, *, package: Optional[str] = None
    ):
        """Reloads a DiploGM cog. Will roll back to the previous version if it fails to load."""
        await self.reload_extension(f"{_EXTENSION_PATH}{name}", package=package)

    @staticmethod
    def get_all_extensions():
        """Gets all cog extensions."""
        for filename in os.listdir(_EXTENSION_DIRECTORY):
            # ignore non py files
            # ignore private files e.g. '_private.py'
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            yield f"DiploGM.cogs.{filename[:-3]}"

    # add logging to base extension functions
    async def load_extension(self, name: str, *, package: Optional[str] = None):
        """Loads a cog extension."""
        try:
            start = datetime.datetime.now()
            await super().load_extension(f"{name}", package=package)
            logger.info(
                "Successfully loaded Cog: %s in %s",
                name,
                datetime.datetime.now() - start,
            )
        except commands.ExtensionError as e:
            logger.info("Failed to load Cog %s", name)
            raise e

    async def unload_extension(
        self, name: str, *, package: Optional[str] = None
    ) -> None:
        """Unloads a cog extension."""
        try:
            start = datetime.datetime.now()
            await super().unload_extension(f"{name}", package=package)
            logger.info(
                "Successfully unloaded Cog: %s in %s",
                name,
                datetime.datetime.now() - start,
            )
        except commands.ExtensionError as e:
            logger.info("Failed to unload Cog %s", name)
            raise e

    async def reload_extension(
        self, name: str, *, package: Optional[str] = None
    ) -> None:
        """Reloads a cog extension. Will roll back to the previous version if it fails to load."""
        try:
            start = datetime.datetime.now()
            await super().reload_extension(f"{name}", package=package)
            logger.info(
                "Successfully reloaded Cog: %s in %s",
                name,
                datetime.datetime.now() - start,
            )
        except commands.ExtensionError as e:
            logger.info("Failed to reload Cog %s", name)
            raise e

    async def on_ready(self):
        """Stuff that happens when the bot has finished starting up."""
        now = datetime.datetime.now(datetime.timezone.utc)
        logger.info("Setup took %s", now - self.creation_time)
        logger.info("Logged in as %s", self.user)

        # Ensure bot is connected to the correct server
        guild = self.get_guild(HUB_SERVER_ID)
        if not guild:
            logger.warning("Cannot find Hub Server [id=%s]", HUB_SERVER_ID)

        # Get the specific channel
        channel = self.get_channel(HUB_SERVER_BOT_STATUS_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Cannot find Bot Status Channel [id=%s]",
                HUB_SERVER_BOT_STATUS_CHANNEL_ID,
            )
        else:
            message = random.choice(WELCOME_MESSAGES)
            await send_message_and_file(
                channel=channel, message=message, embed_colour=EMBED_STANDARD_COLOUR
            )
            await self._post_changelog(channel)

        # Set bot's presence (optional)
        await self.change_presence(activity=discord.Game(name=GAME_PLAYING))

    async def _post_changelog(self, channel: discord.abc.Messageable) -> None:
        def _get_recent_changelog(filepath: Path) -> tuple[str, str]:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            version = lines[0]
            change_lines = []
            collecting = False
            for line in lines[1:]:
                match = re.match(r"=+", line)
                if match:
                    if not collecting:
                        collecting = True
                    else:
                        collecting = True
                        change_lines = change_lines[:-1]
                        break
                elif collecting:
                    change_lines.append(line)

            changes = "".join(change_lines)
            return version, changes

        changelog = Path("Changelog.md")
        digest_file = Path("assets") / "changelog.sum"

        new_digest = file_hexdigest(changelog)
        old_digest = None
        if digest_file.exists():
            old_digest = digest_file.read_text().strip()

        changed = False
        if new_digest != old_digest:
            digest_file.write_text(new_digest)
            changed = True

        if changed:
            version, changes = _get_recent_changelog(changelog)
            await send_message_and_file(
                channel=channel,
                embed_colour="#aabb00",
                title=f"Changelog Version: {version}\n___",
                message=changes,
            )

    async def close(self):
        logger.info("Shutting down gracefully.")

        # safely handle any runtime cog state that needs storing/ending
        for name, cog in self.cogs.items():
            close_method = getattr(cog, "close", None)
            if not callable(close_method):
                continue

            try:
                result = close_method()
                if inspect.isawaitable(result):
                    await result

                logger.info("Closed Cog: %s", name)
            except Exception as e:
                logger.warning("Failed to close Cog '%s' safely: %s", name, e)

        await super().close()

    async def before_any_command(self, ctx: commands.Context):
        """Before any command, log the command and thumbs-up the message."""
        if (
            isinstance(ctx.channel, (discord.DMChannel, discord.PartialMessageable))
            or not ctx.guild
        ):
            return
        assert isinstance(ctx.guild, discord.Guild)
        await self.manager.ensure_board_loaded(ctx.guild.id)

        logger.debug(
            "[%s][#%s](%s) - '%s'",
            ctx.guild.name,
            ctx.channel.name,
            ctx.message.author.name,
            ctx.message.content,
        )

        # People input apostrophes that don't match what the province names are, we can catch all of that here
        # ctx.message.content = re.sub(r"[‘’`´′‛]", "'", ctx.message.content)

        asyncio.create_task(ctx.message.add_reaction("👍"))

    async def before_any_slash_command(self, interaction: discord.Interaction) -> bool:
        """Before any slash command, ensure the board is loaded."""
        if interaction.guild:
            await self.manager.ensure_board_loaded(interaction.guild.id)
        return True

    async def after_any_command(self, ctx: commands.Context):
        """After any command, log the time taken to execute the command."""
        assert ctx.command is not None
        if (
            isinstance(ctx.channel, (discord.DMChannel, discord.PartialMessageable))
            or not ctx.guild
            or not ctx.command
        ):
            return
        self.last_command_time = ctx.message.created_at
        time_spent = (
            datetime.datetime.now(datetime.timezone.utc) - ctx.message.created_at
        )
        if time_spent.total_seconds() < 0:
            time_spent = datetime.timedelta(seconds=0)

        if time_spent.total_seconds() < 1:
            level = logging.DEBUG
        elif time_spent.total_seconds() < 10 and ctx.command.name not in [
            "o",
            "order",
            "orders",
        ]:
            level = logging.INFO
        else:
            level = logging.WARN

        logger.log(
            level,
            "[%s][#%s](%s) - '%s' - complete in %s",
            ctx.guild.name,
            ctx.channel.name,
            ctx.message.author.name,
            ctx.message.content,
            time_spent,
        )

    async def on_command_error(self, context: commands.Context, exception: Exception):
        if isinstance(exception, commands.CommandNotFound):
            # we shouldn't do anything if the user says something like "..."
            return

        assert (
            context.guild is not None
            and context.command is not None
            and self.user is not None
        )
        try:
            # mark the message as failed
            await context.message.add_reaction("❌")
            await context.message.remove_reaction("👍", self.user)
        except discord.HTTPException:
            # if reactions fail, ignore and continue handling existing exception
            pass

        if getattr(context, "handled", False):
            logger.info(
                "global on_command_error skipped a %s that was previously handled...",
                type(exception),
            )
            return

        time_spent = (
            datetime.datetime.now(datetime.timezone.utc) - context.message.created_at
        )

        if isinstance(
            exception,
            (
                commands.CommandInvokeError,
                commands.ConversionError,
                commands.HybridCommandError,
            ),
        ):
            original = exception.original
        else:
            original = exception

        channel_name = (
            context.channel.name
            if isinstance(context.channel, (discord.TextChannel, discord.Thread))
            else context.channel.id
        )

        if isinstance(original, (CommandPermissionError, NoGameError, PermissionError)):
            logger.info(
                "[%s][#%s](%s) - '%s' - %s in %s: %s",
                context.guild.name,
                channel_name,
                context.message.author.name,
                context.message.content,
                type(original).__name__,
                time_spent,
                original,
            )
            await send_message_and_file(
                channel=context.channel,
                message=str(original),
                embed_colour=ERROR_COLOUR,
            )
            return

        logger.log(
            logging.ERROR,
            "[%s][#%s](%s) - '%s' - errored in %s\n%s",
            context.guild.name,
            channel_name,
            context.message.author.name,
            context.message.content,
            time_spent,
            "".join(
                traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            ),
        )

        if isinstance(original, discord.Forbidden):
            await send_message_and_file(
                channel=context.channel,
                message="I do not have the correct permissions to do this.\n"
                "I might not be setup correctly.\n"
                "If this is unexpected please contact a GM or reach out in: "
                + HUB_SERVER_BOT_BUG_REPORT_CHANNEL_MESSAGE,
                embed_colour=ERROR_COLOUR,
            )
            return

        if isinstance(original, commands.errors.MissingRequiredArgument):
            out = (
                f"`{original}`\n\n"
                "If you need some help on how to use this command, "
                + f"consider running this command instead: `.help {context.command}`"
            )
            await send_message_and_file(
                channel=context.channel,
                title="You are missing a required argument.",
                message=out,
            )
            return

        if isinstance(original, RuntimeError):
            out = f"`{original}`\n"
            await send_message_and_file(
                channel=context.channel,
                title="DiploGM ran into a Runtime Error",
                message=out,
            )
            return

        # NOTE: Unknown as to why ClientOSError started cropping up, first seen 2025/11/03
        # https://discord.com/channels/1201167737163104376/1280587781638459528/1434742866453860412
        if isinstance(
            original,
            (
                aiohttp.client_exceptions.ClientOSError,
                discord.errors.DiscordServerError,
            ),
        ):
            out = (
                "Please wait a few (10 to 30) seconds and try again.\n"
                "Sorry for the inconvenience. :D\n\n"
                "-# If after repeated attempts it still breaks, "
                "please report this to a bot dev using a feedback channel"
            )
            await send_message_and_file(
                channel=context.channel,
                title="The Command didn't work this time.",
                message=out,
            )
            return

        # Final Case: Not handled cleanly
        unhandled_out = (
            "```python\n"
            + "\n".join(traceback.format_exception(original, limit=3))
            + "```"
        )

        # Out to Bot Dev Server
        bot_error_channel = self.get_channel(BOT_DEV_UNHANDLED_ERRORS_CHANNEL_ID)
        if bot_error_channel and isinstance(bot_error_channel, discord.abc.Messageable):
            channel_category = (
                context.channel.category
                if isinstance(context.channel, (discord.TextChannel, discord.Thread))
                else context.channel.id
            )
            channel_name = (
                context.channel.name
                if isinstance(context.channel, (discord.TextChannel, discord.Thread))
                else context.channel.id
            )
            unhandled_out_dev = (
                f"Type: {type(original)}\n"
                f"Location: {context.guild.name} [{channel_category or ''}]-[{channel_name}]\n"
                f"Link: {context.message.jump_url}\n"
                f"Time: {str(datetime.datetime.now(datetime.timezone.utc))[:-13]} UTC\n"
                f"Invoking User: {context.author.mention}[{context.author.name}]\n"
                f"Invoked Command: {context.command.name}\n"
                f"Command Invocation Message: ||`{context.message.content}`||\n"
            ) + unhandled_out
            await send_message_and_file(
                channel=bot_error_channel,
                title="UNHANDLED ERROR",
                message=unhandled_out_dev,
            )

        # Out to Invoking Channel
        unhandled_out = (
            f"Please report this to a bot dev in a feedback channel: {HUB_SERVER_BOT_BUG_REPORT_CHANNEL_MESSAGE}\n"
        ) + unhandled_out
        await send_message_and_file(
            channel=context.channel,
            title="ERROR: >.< How did we get here...",
            message=unhandled_out,
            embed_colour=ERROR_COLOUR,
        )

    async def on_guild_join(self, guild: discord.Guild):
        """When the bot joins a new server, log it and report back to the hub server."""
        self.manager.save_ctx_parameter(guild.id, "server_name", guild.name)
        channel = self.get_channel(
            HUB_SERVER_SERVER_PRESENCE_CHANNEL_ID
        ) or self.get_channel(BOT_DEV_UNHANDLED_ERRORS_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Bot joined a Guild(%s) but could not find a location to log to.",
                guild.id,
            )
            return

        out = f"Guild: `{guild.name}`\nGuild ID: `{guild.id}`"

        if guild.owner:
            out += (
                f"\nOwner: {guild.owner.mention}[{guild.owner.name}]\n"
                f"Owner ID: `{guild.owner.id}`"
            )
        else:
            out += "\n-- Owner unidentified --"

        await asyncio.sleep(2)
        async for entry in guild.audit_logs(
            limit=5, action=discord.AuditLogAction.bot_add
        ):
            if not self.user or not entry.user or not entry.target:
                continue

            if entry.target.id == self.user.id:
                inviter = entry.user
                out += (
                    f"\nInviter: {inviter.mention}[{inviter.name}]\n"
                    f"Inviter ID: {inviter.id}"
                )
                break
        else:
            out += "\n-- Inviter unidentified --"

        await send_message_and_file(
            channel=channel,
            embed_colour="#00FF00",
            title="DiploGM joined a server",
            message=out,
        )

    async def on_guild_remove(self, guild: discord.Guild):
        """When the bot is removed from a server, log it and report back to the hub server."""
        channel = self.get_channel(
            HUB_SERVER_SERVER_PRESENCE_CHANNEL_ID
        ) or self.get_channel(BOT_DEV_UNHANDLED_ERRORS_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Bot was removed from Guild(%s) but could not find a location to log to.",
                guild.id,
            )
            return

        out = f"Guild: `{guild.name}`\nGuild ID: `{guild.id}`"

        if guild.owner:
            out += (
                f"\nOwner: {guild.owner.mention}[{guild.owner.name}]\n"
                f"Owner ID: `{guild.owner.id}`"
            )
        else:
            out += "\n-- Owner unidentified --"

        await send_message_and_file(
            channel=channel,
            embed_colour="#FF0000",
            title="DiploGM left a server",
            message=out,
        )

    async def on_message(self, message: discord.Message):
        """If a player sends a message, update their last activity time."""
        if message.author.bot:
            return
        server_id = message.guild.id if message.guild else None
        sender = message.author
        if isinstance(sender, discord.User) or server_id is None:
            return
        is_player = any(r.name.lower() == "player" for r in sender.roles)
        if is_player:
            self.manager.update_player_activity(server_id, sender)

        await self.process_commands(message)

    async def on_reaction_add(self, reaction, user):
        """1-in-10,000 chance to call out someone for reacting."""
        if user.bot:
            return

        message: discord.Message = reaction.message
        chance = random.randint(0, 10000)

        if chance == 0:
            await message.reply(
                f"Why did you reply with {reaction.emoji} {user.mention}?"
            )
