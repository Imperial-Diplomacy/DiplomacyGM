"""Handles uploading maps to the archive.
Currently only works with Azure and isn't really meant for public use, but it could be in the future."""
from __future__ import annotations

import asyncio
import logging

from subprocess import PIPE
from typing import TYPE_CHECKING
from discord.ext import commands
from DiploGM.utils.image import svg_to_png
from DiploGM.config import MAP_ARCHIVE_SAS_TOKEN, MAP_ARCHIVE_UPLOAD_URL
from DiploGM.models.turn import Turn
from DiploGM.utils import log_command, send_message_and_file

if TYPE_CHECKING:
    from DiploGM.models.board import Board


logger = logging.getLogger(__name__)


async def upload_map_to_archive(ctx: commands.Context,
                                server_id: int,
                                board: Board,
                                game_map: bytes,
                                turn: Turn | None = None) -> None:
    """Uploads a map to the archive given a server ID and the map as a PNG."""
    if not MAP_ARCHIVE_SAS_TOKEN:
        return
    turnstr = board.turn.get_short_name() if turn is None else turn.get_short_name()
    url = None
    with open("gamelist.tsv", "r", encoding="utf-8") as gamefile:
        for server in gamefile:
            server_info = server.strip().split("\t")
            if str(server_id) == server_info[0]:
                url = f"{MAP_ARCHIVE_UPLOAD_URL}/{server_info[1]}/{server_info[2]}/" + \
                      f"{turnstr}m.png{MAP_ARCHIVE_SAS_TOKEN}"
                break
    if url is None:
        return
    png_map, _ = await svg_to_png(game_map, url)
    p = await asyncio.create_subprocess_shell(
        f'azcopy copy "{url}" --from-to PipeBlob --content-type image/png',
        stdout=PIPE,
        stdin=PIPE,
        stderr=PIPE,
    )
    _, error = await p.communicate(input=png_map)
    error = error.decode()
    await send_message_and_file(
        channel=ctx.channel,
        title="Uploaded map to archive",
    )
    log_command(
        logger,
        ctx,
        message=(
            f"Map uploading failed: {error}"
            if len(error) > 0
            else "Uploaded map to archive"
        ),
    )
