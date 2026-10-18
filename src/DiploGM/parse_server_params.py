"""Module to parse commands to edit the board parameters."""

import re

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.manager import Manager
from DiploGM.utils import get_keywords
from DiploGM.models.board import Board


def parse_server_params(
    server_id: int, message: str, board: Board
) -> tuple[str, str, str | None]:
    """Parses a message containing commands to edit server settings,
    executes those commands, and returns a response message."""
    invalid: list[tuple[str, RuntimeError | ValueError]] = []
    commands = str.splitlines(message)
    for command in commands:
        try:
            _parse_command(server_id, command, board)
        except (RuntimeError, ValueError) as error:
            invalid.append((command, error))

    embed_colour: str | None = None
    if invalid:
        response_title = "Error"
        response_body = "The following commands were invalid:"
        for command in invalid:
            response_body += f"\n`{command[0]}` with error: {command[1]}"

        if len(invalid) == len(commands):
            embed_colour = ERROR_COLOUR
        else:
            embed_colour = PARTIAL_ERROR_COLOUR
    else:
        response_title = "Commands validated successfully.."
        response_body = ""

    return (
        response_title,
        response_body,
        embed_colour,
    )


def _set_maps_channel(
    _, keywords: list[str], board: Board
) -> tuple[str | None, str | None]:
    maps_channel_matches = re.findall(r"\d{10,}", keywords[0])
    if not maps_channel_matches:
        raise ValueError("Invalid maps channel.")
    color_mode = keywords[1].lower() if len(keywords) > 1 else "standard"
    if color_mode == "none":
        color_mode = None
        return f"maps_channel/{maps_channel_matches[-1]}", None
    else:
        valid_color_modes = board.data["svg config"].get("color_options", []) + [
            "standard", "custom", "random", "pacific", "oil", "clean", "invert"
        ]
        for color_mode in keywords[1:]:
            if color_mode.lower() not in valid_color_modes:
                raise ValueError(f"Unknown color mode: {color_mode}")
    return f"maps_channel/{maps_channel_matches[-1]}", " ".join(keywords[1:]).lower()

function_list = {"maps channel": _set_maps_channel}


def _parse_command(server_id: int, command: str, board: Board) -> None:
    command_list: list[str] = get_keywords(command)
    command_type = command_list[0].lower()
    keywords = command_list[1:]

    if command_type not in function_list:
        raise RuntimeError("No command key phrases found")
    if len(keywords) < 1:
        raise RuntimeError("Missing command keywords")
    new_key, new_value = function_list[command_type](command_type, keywords, board)
    if new_key is not None and new_value is not None:
        Manager().save_ctx_parameter(server_id, new_key, new_value)
    elif new_key is not None:
        Manager().delete_ctx_parameter(server_id, new_key)
