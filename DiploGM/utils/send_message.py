import datetime
from enum import Enum
import io
import re
from typing import List, Tuple
import logging

import discord
from discord import Message, Embed, Colour
from discord.abc import Messageable

from DiploGM import config
from DiploGM.adjudicator.utils import svg_to_png, png_to_jpg
from .logging import log_command_no_ctx


logger = logging.getLogger(__name__)

DISCORD_MESSAGE_LIMIT = 2000
DISCORD_FILE_LIMIT = 10 * (2**20)
DISCORD_EMBED_DESCRIPTION_LIMIT = 4096
DISCORD_EMBED_TOTAL_LIMIT = 6000


class ErrorMessage(Enum):
    """Enum that gives a common set of error messages for send_error()."""
    CHANNEL_NOT_GIVEN = "No channel given."
    COMMAND_IN_PAST = "Don't schedule a command to occur in the past."
    IMPROPER_TIMESTAMP = "Did not give a proper timestamp."
    MESSAGE_NOT_GIVEN = "No message given."
    NO_PLAYER_CATEGORY = "No player category found."
    NO_PLAYER_ROLE = "No player role found."
    NO_ROLES_SUPPLIED = "No roles were supplied to allocate. Please include a role mention in the command."
    NOT_MESSAGEABLE = "Channel is not messageable."
    POWER_NOT_MENTIONED = "Did not mention a nation."
    USER_NOT_MENTIONED = "Did not mention a user."
    UNKNOWN_ERROR = "Unknown Error: Please contact your local bot dev."


async def send_error(channel: Messageable, error_message: ErrorMessage) -> Message:
    """Sends an error message to the specified channel based on the provided ErrorMessage enum."""
    return await send_message_and_file(
        channel=channel,
        title=error_message.value,
        message=error_message.value,
        embed_colour=config.ERROR_COLOUR,
    )

async def send_orders_locked_error(channel: Messageable) -> Message:
    """Sends an 'Orders locked' error message to the specified channel."""
    return await send_message_and_file(
                    channel=channel,
                    title="Orders locked!",
                    message="If you think this is an error, contact a GM.",
                    embed_colour=config.ERROR_COLOUR,
                )

async def send_message_and_file(
    *,
    channel: Messageable,
    title: str | None = None,
    message: str | None = None,
    messages: list[str] | None = None,
    embed_colour: str | None = None,
    file: bytes | None = None,
    file_name: str | None = None,
    file_in_embed: bool | None = None,
    footer_content: str | None = None,
    footer_datetime: datetime.datetime | None = None,
    fields: List[Tuple[str, str]] | None = None,
    convert_svg: bool = False,
    **_,
) -> Message:

    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        raise ValueError("Can only send messages to text channels")
    if embed_colour is None:
        embed_colour = config.EMBED_STANDARD_COLOUR
    assert embed_colour is not None

    if convert_svg and file and file_name:
        file, file_name = await svg_to_png(file, file_name)

    # Checks embed title and bodies are within limits.
    if fields:
        for i, field in reversed(list(enumerate(fields))):
            if len(field[0]) > 256 or len(field[1]) > 1024:
                field_title, field_body = fields.pop(i)
                if not message:
                    message = ""
                message += (
                    f"\n" f"### {field_title}\n"
                    if field_title.strip()
                    else f"{field_title}\n" f"{field_body}"
                )

    if message and messages:
        messages = [message] + messages
    elif message:
        messages = [message]

    embeds = []
    while messages:
        message = messages.pop()
        while message:
            cutoff = -1
            if len(message) <= DISCORD_EMBED_DESCRIPTION_LIMIT:
                cutoff = len(message)
            # Try to find an even line break to split the long messages on
            if cutoff == -1:
                cutoff = message.rfind("\n", 0, DISCORD_EMBED_DESCRIPTION_LIMIT)
            if cutoff == -1:
                cutoff = message.rfind(" ", 0, DISCORD_EMBED_DESCRIPTION_LIMIT)
            # otherwise split at limit
            if cutoff == -1:
                cutoff = DISCORD_EMBED_DESCRIPTION_LIMIT

            embed = Embed(
                title=title,
                description=message[:cutoff],
                colour=Colour.from_str(embed_colour),
            )
            # ensure only first embed has title
            title = None

            # check that embed totals aren't over the total message embed character limit.
            if (
                sum(map(len, embeds)) + len(embed) > DISCORD_EMBED_TOTAL_LIMIT
                or len(embeds) == 10
            ):
                await channel.send(embeds=embeds)
                embeds = []

            embeds.append(embed)

            message = message[cutoff:].strip()

    if not embeds:
        embeds = [Embed(title=title, colour=Colour.from_str(embed_colour))]
        title = ""

    for field in fields or []:
        if (
            len(embeds[-1].fields) == 25
            or sum(map(len, embeds)) + sum(map(len, field))
            > DISCORD_EMBED_TOTAL_LIMIT
            or len(embeds) == 10
        ):
            await channel.send(embeds=embeds)
            embeds = [
                Embed(
                    title=title,
                    colour=Colour.from_str(embed_colour),
                )
            ]
            title = ""

        embeds[-1].add_field(name=field[0], value=field[1], inline=True)

    discord_file = None
    if file is not None and file_name is not None:
        if file_name.lower().endswith(".png") and len(file) > DISCORD_FILE_LIMIT:
            log_command_no_ctx(
                logger,
                "?",
                channel.guild.name,
                channel.name,
                "?",
                f"png is too big ({len(file)}); converting to jpg",
            )
            file, file_name, error = await png_to_jpg(file, file_name)
            error = re.sub("\\s+", " ", str(error)[2:-1])
            if len(error) > 0:
                log_command_no_ctx(
                    logger,
                    "?",
                    channel.guild.name,
                    channel.name,
                    "?",
                    f"png to jpeg conversion errors: {error}",
                )
            if len(file) > DISCORD_FILE_LIMIT or len(file) == 0:
                log_command_no_ctx(
                    logger,
                    "?",
                    channel.guild.name,
                    channel.name,
                    "?",
                    f"jpg is too big ({len(file)})",
                )
                if False: #TODO: redo this: is_gm_channel(channel):
                    message = "Try `.vm true` to get an svg"
                else:
                    message = "Please contact your GM"
                await send_message_and_file(
                    channel=channel, title="File too large", message=message
                )
                file = None
                file_name = None
                discord_file = None

    if file is not None and file_name is not None:
        with io.BytesIO(file) as vfile:
            discord_file = discord.File(fp=vfile, filename=file_name)

        if file_in_embed or (
            file_in_embed is None
            and any(
                file_name.lower().endswith(x)
                for x in (
                    ".png",
                    ".jpg",
                    ".jpeg",  # , ".gif", ".gifv", ".webm", ".mp4", "wav", ".mp3", ".ogg"
                )
            )
        ):
            embeds[-1].set_image(
                url=f"attachment://{discord_file.filename.replace(' ', '_')}"
            )

    if footer_datetime or footer_content:
        embeds[-1].set_footer(
            text=footer_content,
            icon_url="https://cdn.discordapp.com/icons/1201167737163104376/f78e67edebfdefad8f3ee057ad658acd.webp"
            "?size=96&quality=lossless",
        )

        embeds[-1].timestamp = footer_datetime

    if discord_file is not None:
        return await channel.send(embeds=embeds, file=discord_file)
    return await channel.send(embeds=embeds)
