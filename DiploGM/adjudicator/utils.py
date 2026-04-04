"""Utility functions that handle image conversion."""
import asyncio
import logging
import os
from subprocess import PIPE
from DiploGM.config import SIMULATRANEOUS_SVG_EXPORT_LIMIT

logger = logging.getLogger(__name__)

LIMIT = SIMULATRANEOUS_SVG_EXPORT_LIMIT

if LIMIT is None:
    LIMIT = 4
external_task_limit = asyncio.Semaphore(int(LIMIT))


async def svg_to_png(svg: bytes, file_name: str) -> tuple[bytes, str]:
    """Convert an SVG to a PNG using Inkscape.
    This is by far the most intensive part of the bot, so if there's any way we could speed this up,
    it would make a huge difference."""
    async with external_task_limit:
        # https://gitlab.com/inkscape/inkscape/-/issues/4716
        os_env = os.environ.copy()
        os_env["SELF_CALL"] = "xxx"
        p = await asyncio.create_subprocess_shell(
            "inkscape --pipe --export-type=png --export-dpi=200",
            stdout=PIPE,
            stdin=PIPE,
            stderr=PIPE,
            env=os_env,
        )
        data, _ = await p.communicate(input=svg)

        # Stupid inkscape error fix, not good but works
        # Inkscape can throw warnings in stdout, this should remove those warnings, leaving us with a valid png

        # This should indicate the start of the png, see https://www.w3.org/TR/2003/REC-PNG-20031110/#5PNG-file-signature
        png_start = b"\x89PNG\r\n\x1a\n"

        if data[:8] != png_start:
#            logger.critical(f"failed to assert png code: {png_start}")
#            logger.critical(data[:30])

            data = data[data.find(png_start) :]

            if data[:8] != png_start:
                logger.critical(data[:30])
                raise RuntimeError("Something went wrong with making the png.")

        base = os.path.splitext(file_name)[0]
        return bytes(data), base + ".png"


async def png_to_jpg(png: bytes, file_name: str) -> tuple[bytes, str, bytes]:
    """Convert a PNG to a JPG using ImageMagick."""
    async with external_task_limit:
        p = await asyncio.create_subprocess_shell(
            "convert png:- jpg:-", stdout=PIPE, stdin=PIPE, stderr=PIPE
        )
        data, error = await p.communicate(input=png)
        base = os.path.splitext(file_name)[0]
        return bytes(data), base + ".jpg", error
