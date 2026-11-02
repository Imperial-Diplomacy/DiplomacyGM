"""Handles uploading maps to the archive.
Currently only works with Azure and isn't really meant for public use, but it could be in the future."""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING
import boto3
from botocore.config import Config
from discord.ext import commands
from DiploGM.utils.image import svg_to_png
from DiploGM.config import MAP_ARCHIVE_ACCESS_KEY_ID, MAP_ARCHIVE_ACCOUNT_ID, MAP_ARCHIVE_BUCKET_NAME, MAP_ARCHIVE_SECRET_ACCESS_KEY
from DiploGM.models.turn import Turn
from DiploGM.utils import send_message_and_file

if TYPE_CHECKING:
    from DiploGM.models.board import Board


logger = logging.getLogger(__name__)
s3 = boto3.client(
    service_name="s3",
    endpoint_url=f"https://{MAP_ARCHIVE_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=MAP_ARCHIVE_ACCESS_KEY_ID,
    aws_secret_access_key=MAP_ARCHIVE_SECRET_ACCESS_KEY,
    config=Config(
        signature_version="s3v4",
        response_checksum_validation="WHEN_SUPPORTED"
    ),
)

async def upload_map_to_archive(
    ctx: commands.Context,
    server_id: int,
    board: Board,
    game_map: bytes,
    turn: Turn | None = None,
    draw_moves: bool = True,
) -> None:
    """Uploads a map to the archive given a server ID and the map as a PNG."""
    if not MAP_ARCHIVE_SECRET_ACCESS_KEY:
        return
    if turn is None:
        turn = board.turn
    if not draw_moves:
        turn = turn.get_previous_turn()
    turnstr = format(turn, "%y%s")
    key = None
    with open("gamelist.tsv", "r", encoding="utf-8") as gamefile:
        for server in gamefile:
            server_info = server.strip().split("\t")
            if str(server_id) == server_info[0]:
                key = f"{server_info[1]}/{server_info[2]}/{turnstr}{'m' if draw_moves else 'r'}.png"
                break
    if key is None:
        return
    png_map, _ = await svg_to_png(game_map, key, board.data["svg config"])
    s3.put_object(
        Bucket=MAP_ARCHIVE_BUCKET_NAME,
        Key=key,
        Body=png_map,
        ContentType="image/png",
    )
    await send_message_and_file(
        channel=ctx.channel,
        title=f"Uploaded {turn} {'moves' if draw_moves else 'results'} map to archive",
    )
