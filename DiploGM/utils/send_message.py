import datetime
import io
import re
from typing import List, Tuple
import logging

import discord
from discord import Message, Embed, Colour
from discord.ext import commands

from DiploGM import config
from .logging import log_command_no_ctx
from DiploGM.adjudicator.utils import svg_to_png, png_to_jpg


logger = logging.getLogger(__name__)

discord_message_limit = 2000
discord_file_limit = 10 * (2**20)
discord_embed_description_limit = 4096
discord_embed_total_limit = 6000


async def send_message_and_file(
    *,
    channel: commands.Context.channel,
    title: str | None = None,
    message: str | None = None,
    messages: list[str] | None = None,
    embed_colour: str | None = None,
    file: str | None = None,
    file_name: str | None = None,
    file_in_embed: bool | None = None,
    footer_content: str | None = None,
    footer_datetime: datetime.datetime | None = None,
    fields: List[Tuple[str, str]] | None = None,
    convert_svg: bool = False,
    **_,
) -> Message:

    if not embed_colour:
        embed_colour = config.EMBED_STANDARD_COLOUR

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
    if messages:
        while messages:
            message = messages.pop()
            while message:
                cutoff = -1
                if len(message) <= discord_embed_description_limit:
                    cutoff = len(message)
                # Try to find an even line break to split the long messages on
                if cutoff == -1:
                    cutoff = message.rfind("\n", 0, discord_embed_description_limit)
                if cutoff == -1:
                    cutoff = message.rfind(" ", 0, discord_embed_description_limit)
                # otherwise split at limit
                if cutoff == -1:
                    cutoff = discord_embed_description_limit

                embed = Embed(
                    title=title,
                    description=message[:cutoff],
                    colour=Colour.from_str(embed_colour),
                )
                # ensure only first embed has title
                title = None

                # check that embed totals aren't over the total message embed character limit.
                if (
                    sum(map(len, embeds)) + len(embed) > discord_embed_total_limit
                    or len(embeds) == 10
                ):
                    await channel.send(embeds=embeds)
                    embeds = []

                embeds.append(embed)

                message = message[cutoff:].strip()

    if not embeds:
        embeds = [Embed(title=title, colour=Colour.from_str(embed_colour))]
        title = ""

    if fields:
        for field in fields:
            if (
                len(embeds[-1].fields) == 25
                or sum(map(len, embeds)) + sum(map(len, field))
                > discord_embed_total_limit
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
    if file is not None:
        if file_name[-4:].lower() == ".png" and len(file) > discord_file_limit:
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
            if len(file) > discord_file_limit or len(file) == 0:
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

    if file is not None:
        with io.BytesIO(file) as vfile:
            discord_file = discord.File(fp=vfile, filename=file_name)

        if file_in_embed or (
            file_in_embed is None
            and any(
                map(
                    lambda x: file_name.lower().endswith(x),
                    (
                        ".png",
                        ".jpg",
                        ".jpeg",  # , ".gif", ".gifv", ".webm", ".mp4", "wav", ".mp3", ".ogg"
                    ),
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

    return await channel.send(embeds=embeds, file=discord_file)
