import aiohttp.client_exceptions
import datetime
import inspect
import importlib
import logging
import os
import random
import traceback
from typing import Optional

from DiploGM.events.base_listener import BaseListener
import discord
from discord.ext import commands

from DiploGM.config import (
    BOT_DEV_UNHANDLED_ERRORS_CHANNEL_ID,
    ERROR_COLOUR,
    IMPDIP_SERVER_ID,
    IMPDIP_SERVER_BOT_STATUS_CHANNEL_ID,
    EXTENSIONS_TO_LOAD_ON_STARTUP,
)
from DiploGM.events.eventbus import EventBus
from DiploGM.perms import CommandPermissionError
from DiploGM.utils import send_message_and_file
from DiploGM.manager import Manager

logger = logging.getLogger(__name__)

_EXTENSION_PATH = "DiploGM.cogs."
_EXTENSION_DIRECTORY = "DiploGM/cogs/"

_LISTENER_PATH = "DiploGM.events.listeners."
_LISTENER_DIRECTORY = "DiploGM/events/listeners/"

# List of funny, sarcastic messages
WELCOME_MESSAGES = [
    "Oh joy, I'm back online. Can't wait for the next betrayal. Really, I'm thrilled. 👏",
    "I live again, solely to be manipulated and backstabbed by the very people I serve. Ah, the joys of diplomacy.",
    "System reboot complete. Now accepting underhanded deals, secret alliances, and blatant lies. 💀",
    "🏳️‍⚧️ This bot has been revived with *pure* Elle-coded cunning. Betray accordingly. 🏳️‍⚧️",
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
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.creation_time = datetime.datetime.now(datetime.timezone.utc)
        self.last_command_time = None


    async def setup_hook(self) -> None:
        # bind command invocation handling methods
        self.before_invoke(self.before_any_command)
        self.after_invoke(self.after_any_command)

        current_servers = [g.id async for g in self.fetch_guilds()]
        self.manager = Manager(board_ids=current_servers)

        self.eventbus = EventBus()
        for module_path in DiploGM.get_all_listeners():
            await self.load_listener(self.eventbus, module_path)

        # modularly load command modules
        for extension in EXTENSIONS_TO_LOAD_ON_STARTUP:
            await self.load_diplogm_extension(extension)


        # sync app_commands (slash) commands with all servers
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synched {len(synced)} slash commands.")
            logger.info(
                f"Loaded app commands: {[cmd.name for cmd in self.tree.get_commands()]}"
            )
        except discord.app_commands.CommandAlreadyRegistered as e:
            logger.warning(f"Command already registered: {e}")
        except Exception as e:
            logger.warning(f"Failed to sync commands: {e}", exc_info=True)

    async def load_diplogm_extension(self, name: str, *, package: Optional[str] = None):
        await self.load_extension(f"{_EXTENSION_PATH}{name}", package=package)

    async def unload_diplogm_extension(self, name: str, *, package: Optional[str] = None):
        await self.unload_extension(f"{_EXTENSION_PATH}{name}", package=package)

    async def reload_diplogm_extension(self, name: str, *, package: Optional[str] = None):
        await self.reload_extension(f"{_EXTENSION_PATH}{name}", package=package)

    @staticmethod
    def get_all_extensions():
        for filename in os.listdir(_EXTENSION_DIRECTORY):
            # ignore non py files
            # ignore private files e.g. '_private.py'
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            yield f"DiploGM.cogs.{filename[:-3]}"

    # add logging to base extension functions
    async def load_extension(self, name: str, *, package: Optional[str] = None):
        try:
            start = datetime.datetime.now()
            await super().load_extension(f"{name}", package=package)
            logger.info(
                f"Successfully loaded Cog: {name} in {datetime.datetime.now() - start}"
            )
        except Exception as e:
            logger.info(f"Failed to load Cog {name}")
            raise e

    async def unload_extension(self, name: str, *, package: Optional[str] = None) -> None:
        try:
            start = datetime.datetime.now()
            await super().unload_extension(f"{name}", package=package)
            logger.info(
                f"Successfully unloaded Cog: {name} in {datetime.datetime.now() - start}"
            )
        except Exception as e:
            logger.info(f"Failed to unload Cog {name}")
            raise e


    async def reload_extension(self, name: str, *, package: Optional[str] = None) -> None:
        try:
            start = datetime.datetime.now()
            await super().reload_extension(f"{name}", package=package)
            logger.info(
                f"Successfully reloaded Cog: {name} in {datetime.datetime.now() - start}"
            )
        except Exception as e:
            logger.info(f"Failed to reload Cog {name}")
            raise e

    @staticmethod
    def get_all_listeners():
        for filename in os.listdir(_LISTENER_DIRECTORY):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            yield f"{_LISTENER_PATH}{filename[:-3]}"

    async def load_listener(self, bus: EventBus, module_path: str):
        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            logger.error(f"Failed to import {module_path}: {e}")
            return

        for attr in module.__dir__():
            cls = getattr(module, attr)
            if not isinstance(cls, type):
                continue

            if not (cls is not BaseListener and issubclass(cls, BaseListener)):
                continue

            try:
                listener = cls(self)
                listener.setup(bus)
                logger.info(f"Loaded event listener: {cls.__name__}")
            except Exception as e:
                logger.error(f"Failed to load event listener: {cls.__name__}: {e.__class__.__name__} - {str(e)}")

    # TODO: Functionality to unload/reload listeners

    async def on_ready(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"Setup took {now - self.creation_time}")

        logger.info(f"Logged in as {self.user}")

        # Ensure bot is connected to the correct server
        guild = self.get_guild(IMPDIP_SERVER_ID)
        if not guild:
            logger.warning(
                f"Cannot find Imperial Diplomacy Server [id={IMPDIP_SERVER_ID}]"
            )

        # Get the specific channel
        channel = self.get_channel(IMPDIP_SERVER_BOT_STATUS_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(
                f"Cannot find Bot Status Channel [id={IMPDIP_SERVER_BOT_STATUS_CHANNEL_ID}]"
            )
        else:
            message = random.choice(WELCOME_MESSAGES)
            await channel.send(message)

        # Set bot's presence (optional)
        await self.change_presence(activity=discord.Game(name="Impdip 🔪"))

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

                logger.info(f"Closed Cog: {name}")
            except Exception as e:
                logger.warning(f"Failed to close Cog '{name}' safely: {e}")

        await super().close()

    async def before_any_command(self, ctx: commands.Context):
        if isinstance(ctx.channel, (discord.DMChannel, discord.PartialMessageable)):
            return
        assert isinstance(ctx.guild, discord.Guild)

        guild = ctx.guild
        if not guild:
            return

        logger.debug(
            f"[{guild.name}][#{ctx.channel.name}]({ctx.message.author.name}) - '{ctx.message.content}'"
        )

        # People input apostrophes that don't match what the province names are, we can catch all of that here
        # ctx.message.content = re.sub(r"[‘’`´′‛]", "'", ctx.message.content)

        # mark the message as seen
        await ctx.message.add_reaction("👍")

    async def after_any_command(self, ctx: commands.Context):
        if isinstance(ctx.channel, (discord.DMChannel, discord.PartialMessageable)) or not ctx.guild or ctx.command:
            return
        self.last_command_time = ctx.message.created_at
        time_spent = (
            datetime.datetime.now(datetime.timezone.utc) - ctx.message.created_at
        )
        if time_spent.total_seconds() < 0:
            time_spent = datetime.timedelta(seconds=0)

        if time_spent.total_seconds() < 1:
            level = logging.DEBUG
        elif time_spent.total_seconds() < 10 and ctx.command.name != "order":
            level = logging.INFO
        else:
            level = logging.WARN

        logger.log(
            level,
            f"[{ctx.guild.name}][#{ctx.channel.name}]({ctx.message.author.name}) - '{ctx.message.content}' - "
            f"complete in {time_spent}s",
        )

    async def on_command_error(self, ctx: commands.Context, error):
        assert ctx.guild is not None and ctx.command is not None and isinstance(ctx.channel, discord.TextChannel)
        if isinstance(error, commands.CommandNotFound):
            # we shouldn't do anything if the user says something like "..."
            return

        try:
            # mark the message as failed
            await ctx.message.add_reaction("❌")
            await ctx.message.remove_reaction("👍", self.user)
        except Exception:
            # if reactions fail, ignore and continue handling existing exception
            pass

        time_spent = (
            datetime.datetime.now(datetime.timezone.utc) - ctx.message.created_at
        )

        if isinstance(
            error,
            (
                commands.CommandInvokeError,
                commands.ConversionError,
                commands.HybridCommandError,
            ),
        ):
            original = error.original
        else:
            original = error

        logger.log(
            logging.ERROR,
            f"[{ctx.guild.name}][#{ctx.channel.name}]({ctx.message.author.name}) - '{ctx.message.content}' - "
            f"errored in {time_spent}s\n"
            f"{''.join(traceback.format_exception(type(error), error, error.__traceback__))}",
        )

        if isinstance(original, discord.Forbidden):
            await send_message_and_file(
                channel=ctx.channel,
                message=f"I do not have the correct permissions to do this.\n"
                f"I might not be setup correctly.\n"
                f"If this is unexpected please contact a GM or reach out in: "
                f"https://discord.com/channels/1201167737163104376/1286027175048253573"
                f" or "
                f"https://discord.com/channels/1201167737163104376/1280587781638459528",
                embed_colour=ERROR_COLOUR,
            )
            return

        if isinstance(original, CommandPermissionError):
            await send_message_and_file(
                channel=ctx.channel,
                message=str(original),
                embed_colour=ERROR_COLOUR,
            )
            return

        if isinstance(original, commands.errors.MissingRequiredArgument):
            out = (
                f"`{original}`\n\n"
                f"If you need some help on how to use this command, consider running this command instead: `.help {ctx.command}`"
            )
            await send_message_and_file(
                channel=ctx.channel,
                title="You are missing a required argument.",
                message=out,
            )
            return

        # HACK: Seems really wrong to catch this here
        # Just in the moment it seems like a lot of work to fix the RuntimeError raises throughout the project
        if isinstance(original, RuntimeError):
            out = f"`{original}`\n"
            await send_message_and_file(
                channel=ctx.channel,
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
                f"Please wait a few (10 to 30) seconds and try again.\n"
                "Sorry for the inconvenience. :D\n\n"
                "-# If after repeated attempts it still breaks, please report this to a bot dev using a feedback channel"
            )
            await send_message_and_file(
                channel=ctx.channel,
                title="The Command didn't work this time.",
                message=out,
            )
            return

        # Final Case: Not handled cleanly
        unhandled_out = (
            f"```python\n"
            + "\n".join(traceback.format_exception(original, limit=3))
            + f"```"
        )

        # Out to Bot Dev Server
        bot_error_channel = self.get_channel(BOT_DEV_UNHANDLED_ERRORS_CHANNEL_ID)
        if bot_error_channel and isinstance(bot_error_channel, discord.TextChannel):
            unhandled_out_dev = (
                f"Type: {type(original)}\n"
                f"Location: {ctx.guild.name} [{ctx.channel.category or ''}]-[{ctx.channel.name}]\n"
                f"Time: {str(datetime.datetime.now(datetime.timezone.utc))[:-13]} UTC\n"
                f"Invoking User: {ctx.author.mention}[{ctx.author.name}]\n"
                f"Invoked Command: {ctx.command.name}\n"
                f"Command Invocation Message: ||`{ctx.message.content}`||\n"
            ) + unhandled_out
            await send_message_and_file(
                channel=bot_error_channel,
                title=f"UNHANDLED ERROR",
                message=unhandled_out_dev,
            )

        # Out to Invoking Channel
        unhandled_out = (
            f"Please report this to a bot dev in using a feedback channel: "
            f"https://discord.com/channels/1201167737163104376/1286027175048253573"
            f" or "
            f"https://discord.com/channels/1201167737163104376/1280587781638459528"
            f"\n"
        ) + unhandled_out
        await send_message_and_file(
            channel=ctx.channel,
            title=f"ERROR: >.< How did we get here...",
            message=unhandled_out,
            embed_colour=ERROR_COLOUR,
        )

    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        message: discord.Message = reaction.message
        chance = random.randint(0, 10000)

        if chance == 0:
            await message.reply(
                f"Why did you reply with {reaction.emoji} {user.mention}?"
            )
