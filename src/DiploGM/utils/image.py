"""Utility functions that handle image conversion."""

import asyncio
import logging
from io import BytesIO
import os
from subprocess import PIPE
import numpy as np
from PIL import Image

import cairosvg

from DiploGM.config import SIMULATRANEOUS_SVG_EXPORT_LIMIT

logger = logging.getLogger(__name__)

LIMIT = SIMULATRANEOUS_SVG_EXPORT_LIMIT

if LIMIT is None:
    LIMIT = 4
external_task_limit = asyncio.Semaphore(int(LIMIT))

def rearrange_pacific_map(file: bytes, split_pixel_ratio, map_edge_pixel_ratio) -> bytes:
    img = Image.open(BytesIO(file))
    arr = np.array(img)

    # scale for DPI
    split_pixel = int(split_pixel_ratio * img.width)
    map_edge_pixel = int(map_edge_pixel_ratio * img.width)

    # cut map section of image in two pieces
    left = arr[:, :split_pixel]
    right = arr[:, split_pixel:map_edge_pixel]

    # reorder and stitch together
    reordered = np.concatenate([right, left], axis=1)
    arr[:, :map_edge_pixel] = reordered

    output = BytesIO()
    Image.fromarray(arr).save(output, format="PNG")
    return output.getvalue()

async def svg_to_png(svg: bytes, file_name: str, svg_data: dict, pacific_mode: bool = False) -> tuple[bytes, str]:
    """Convert an SVG to a PNG using Inkscape.
    This is by far the most intensive part of the bot, so if there's any way we could speed this up,
    it would make a huge difference."""
    data = b""

    try:
        data = cairosvg.svg2png(
            bytestring=svg,
            dpi=svg_data.get("dpi", 200)
        )
    except Exception as e:
        logger.warning("Failed to convert using cairosvg: %s", e)

    if not data:
        async with external_task_limit:
            # https://gitlab.com/inkscape/inkscape/-/issues/4716
            os_env = os.environ.copy()
            os_env["SELF_CALL"] = "xxx"
            process = await asyncio.create_subprocess_exec(
                "inkscape", 
                "--pipe",
                "--export-type=png",
                f"--export-dpi={svg_data.get('dpi', 200)}",
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
                env=os_env,
            )
            data, stderr = await process.communicate(input=svg)
            if process.returncode != 0:
                raise RuntimeError(
                    f"Inkscape failed with exit code {process.returncode}: "
                    f"{stderr.decode(errors='replace')[:500]}"
                )

    if not data:
        raise RuntimeError("No bytes were received from SVG renderer.")

    # This should indicate the start of the png, see https://www.w3.org/TR/2003/REC-PNG-20031110/#5PNG-file-signature
    png_start = b"\x89PNG\r\n\x1a\n"
    if data[:8] != png_start:
        start = data.find(png_start)

        if start == -1:
            logger.critical(data[:30])

            raise RuntimeError("Failed to produce a valid PNG.")

        data = data[start:]

    base = os.path.splitext(file_name)[0]
    if pacific_mode and svg_data.get("pacific_center_line"):
        data = rearrange_pacific_map(data, svg_data["pacific_center_line"], svg_data.get("pacific_map_edge", 1.0))
    return data, base + ".png"


async def png_to_jpg(png: bytes, file_name: str) -> tuple[bytes, str, bytes]:
    """Convert a PNG to a JPG using ImageMagick."""
    async with external_task_limit:
        p = await asyncio.create_subprocess_shell(
            "convert png:- jpg:-", stdout=PIPE, stdin=PIPE, stderr=PIPE
        )
        data, error = await p.communicate(input=png)
        base = os.path.splitext(file_name)[0]
        return bytes(data), base + ".jpg", error
