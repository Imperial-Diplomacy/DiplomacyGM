import asyncio
import os
import logging

from subprocess import PIPE
from discord.ext import commands
from DiploGM.adjudicator.utils import svg_to_png
from DiploGM.config import MAP_ARCHIVE_SAS_TOKEN, MAP_ARCHIVE_UPLOAD_URL
from DiploGM.models.turn import Turn
from DiploGM.models.board import Board

from DiploGM.utils import log_command, send_message_and_file


logger = logging.getLogger(__name__)


async def upload_map_to_archive(ctx: commands.Context, server_id: int, board: Board, map: bytes, turn: Turn | None = None) -> None:
    if not MAP_ARCHIVE_SAS_TOKEN:
        return
    turnstr = board.turn.get_short_name() if turn is None else turn.get_short_name()
    url = None
    with open("gamelist.tsv", "r") as gamefile:
        for server in gamefile:
            server_info = server.strip().split("\t")
            if str(server_id) == server_info[0]:
                url = f"{MAP_ARCHIVE_UPLOAD_URL}/{server_info[1]}/{server_info[2]}/{turnstr}m.png{MAP_ARCHIVE_SAS_TOKEN}"
                break
    if url is None:
        return
    png_map, _ = await svg_to_png(map, url)
    p = await asyncio.create_subprocess_shell(
        f'azcopy copy "{url}" --from-to PipeBlob --content-type image/png',
        stdout=PIPE,
        stdin=PIPE,
        stderr=PIPE,
    )
    data, error = await p.communicate(input=png_map)
    error = error.decode()
    await send_message_and_file(
        channel=ctx.channel,
        title=f"Uploaded map to archive",
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