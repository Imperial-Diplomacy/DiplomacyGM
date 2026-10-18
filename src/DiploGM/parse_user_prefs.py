"""Module to parse commands to edit the board parameters."""

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.utils import get_keywords
from DiploGM.models.board import Board
from DiploGM.manager import Manager


def parse_user_prefs(
    user_id: int, message: str, board: Board | None
) -> tuple[str, str, str | None]:
    """Parses a message containing commands to edit user preferences,
    executes those commands, and returns a response message."""
    invalid: list[tuple[str, RuntimeError | ValueError]] = []
    commands = str.splitlines(message)
    for command in commands:
        try:
            _parse_command(user_id, command, board)
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


def _set_color_mode(
    _, keywords: list[str], board: Board | None
) -> tuple[str | None, str | None]:
    if board is None:
        raise ValueError("Setting a color mode requires an existing game")
    valid_color_modes = board.data["svg config"].get("color_options", []) + [
        "standard", "custom", "random", "pacific", "oil spill", "clean", "invert"
    ]
    for color_mode in keywords:
        if color_mode.lower() not in valid_color_modes:
            raise ValueError(f"Unknown color mode: {color_mode}")
    return f"{board.datafile}/color_mode", " ".join(keywords).lower()


def _set_pronouns(
    _, keywords: list[str], board: Board | None
) -> tuple[str | None, str | None]:
    content = " ".join(keywords).lower()
    return "pronouns", content


def _set_timezone(
    _, keywords: list[str], board: Board | None
) -> tuple[str | None, str | None]:
    content = " ".join(keywords).upper()
    return "timezone", content


function_list = {
    "color mode": _set_color_mode,
    "pronouns": _set_pronouns,
    "timezone": _set_timezone,
}


def _parse_command(user_id: int, command: str, board: Board | None) -> None:
    command_list: list[str] = get_keywords(command)
    command_type = command_list[0].lower()
    keywords = command_list[1:]

    if command_type not in function_list:
        raise RuntimeError("No command key phrases found")
    if len(keywords) < 1:
        raise RuntimeError("Missing command keywords")
    new_key, new_value = function_list[command_type](command_type, keywords, board)
    if new_key is not None and new_value is not None:
        Manager().save_ctx_parameter(user_id, new_key, new_value)
