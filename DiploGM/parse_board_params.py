"""Module to parse commands to edit the board parameters."""
from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.utils import get_keywords
from DiploGM.mapper.mapper import Mapper
from DiploGM.models.board import Board
from DiploGM.db.database import get_connection

def parse_board_params(message: str, board: Board) -> tuple[str, str, bytes | None, str | None, str | None]:
    """Parses a message containing commands to edit the board parameters,
    executes those commands, and returns a response message and an updated map if applicable."""
    invalid: list[tuple[str, RuntimeError | ValueError]] = []
    commands = str.splitlines(message)
    for command in commands:
        try:
            _parse_command(command, board)
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
        response_title = "Commands validated successfully. Results map updated."
        response_body = ""

    if len(invalid) < len(commands):
        file, file_name = Mapper(board).draw_current_map()
    else:
        file, file_name = None, None

    return (
        response_title,
        response_body,
        file,
        file_name,
        embed_colour,
    )

def _set_build_options(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    key_name = "build_options"
    valid_options = "classic", "cores", "control", "anywhere"
    new_value = keywords[0].lower()
    if new_value not in valid_options:
        raise ValueError(f"{new_value} is not a valid build option")
    board.data[key_name] = new_value
    board.custom_data[key_name] = new_value
    return key_name, new_value

def _set_transformation(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    key_name = "transformation"
    valid_options = "disabled", "moves", "builds", "all"
    new_value = keywords[0].lower()
    if new_value not in valid_options:
        raise ValueError(f"{new_value} is not a valid transformation option")
    board.data[key_name] = new_value
    board.custom_data[key_name] = new_value
    return key_name, new_value

def _set_victory_conditions(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    key_name = "victory_conditions"
    valid_options = "classic", "vscc"
    new_value = keywords[0].lower()
    if new_value not in valid_options:
        raise ValueError(f"{new_value} is not a valid victory condition option")
    board.data[key_name] = new_value
    board.custom_data[key_name] = new_value
    return key_name, new_value

def _set_victory_count(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    key_name = "victory_count"
    new_value = keywords[0].lower()
    if not new_value.isdigit():
        raise ValueError(f"{new_value} is not a whole number of victory SCs")
    board.data[key_name] = new_value
    board.custom_data[key_name] = new_value
    return key_name, new_value

def _set_iscc(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    player_name, new_iscc = (keywords[0].lower(), keywords[1])
    if not (player := board.get_player(player_name)):
        raise ValueError(f"{player_name} was not found in the board")
    key_name = f"players/{player.name}/iscc"
    if not new_iscc.isdigit():
        raise ValueError(f"{new_iscc} is not a whole number of starting SCs")
    board.data["players"][player.name]["iscc"] = new_iscc
    board.custom_data.setdefault("players", {}).setdefault(player.name, {})["iscc"] = new_iscc
    return key_name, new_iscc

def _set_vscc(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    player_name, new_vscc = (keywords[0].lower(), keywords[1])
    if not (player := board.get_player(player_name)):
        raise ValueError(f"{player_name} was not found in the board")
    key_name = f"players/{player.name}/vscc"
    if not new_vscc.isdigit():
        raise ValueError(f"{new_vscc} is not a whole number of starting SCs")
    board.data["players"][player.name]["vscc"] = new_vscc
    board.custom_data.setdefault("players", {}).setdefault(player.name, {})["vscc"] = new_vscc
    return key_name, new_vscc

def _set_capital(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    player_name, new_capital = (keywords[0].lower(), keywords[1])
    if not (player := board.get_player(player_name)):
        raise ValueError(f"{player_name} was not found in the board")
    key_name = f"players/{player.name}/capital"
    board.get_province(new_capital)
    board.data["players"][player.name]["capital"] = new_capital
    return key_name, new_capital

def _set_player_name(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    player_name, new_name = (keywords[0].lower(), ' '.join(keywords[1:]))
    if not (player := board.get_player(player_name)):
        raise ValueError(f"{player_name} was not found in the board")
    key_name = f"players/{player.name}/nickname"
    board.add_nickname(player, new_name)
    return key_name, new_name

def _hide_player(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    player_name, is_hidden = (keywords[0].lower(), keywords[1].lower())
    if not (player := board.get_player(player_name)):
        raise ValueError(f"{player_name} was not found in the board")
    key_name = f"players/{player.name}/hidden"
    if is_hidden not in ["true", "false"]:
        raise ValueError(f"{is_hidden} needs to be true or false")
    board.data["players"][player.name]["hidden"] = is_hidden
    board.custom_data.setdefault("players", {}).setdefault(player.name, {})["hidden"] = is_hidden
    return key_name, is_hidden

def _add_player(_, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    player_name, player_color = (' '.join(keywords[:-1]), keywords[-1].lower())
    if player_name in board.name_to_player:
        raise ValueError(f"{player_name} is already a player")
    key_name = f"players/{player_name}/color"
    player_data = {
        "color": player_color,
        "iscc" : 1,
        "vscc" : board.data["victory_count"]
    }
    board.data["players"][player_name] = player_data
    board.custom_data.setdefault("players", {})[player_name] = dict(player_data)
    board.add_new_player(player_name, player_color)
    get_connection().execute_arbitrary_sql(
        "INSERT INTO players (board_id, player_name, color, liege, points) VALUES (?, ?, ?, ?, ?)",
        (board.board_id, player_name, player_color, None, 0)
    )
    return key_name, player_color

# Several options are enabled/disabled toggles, so let's combine them.
def _toggle_game_option(command: str, keywords: list[str], board: Board) -> tuple[str | None, str | None]:
    key_name = str.replace(command, " ", "_")
    valid_options = "true", "false", "enabled", "disabled"
    new_value = keywords[0].lower()
    if new_value not in valid_options:
        raise ValueError(f"{new_value} is not a valid option. Please use true/false or enabled/disabled.")
    board.data[key_name] = new_value
    return key_name, new_value

function_list = {
    "building": _set_build_options,
    "convoyable islands": _toggle_game_option,
    "supportable cores": _toggle_game_option,
    "transformation": _set_transformation,
    "dp": _toggle_game_option,
    "victory conditions": _set_victory_conditions,
    "victory count": _set_victory_count,
    "iscc": _set_iscc,
    "vscc": _set_vscc,
    "capital": _set_capital,
    "player name": _set_player_name,
    "hide player": _hide_player,
    "add player": _add_player
}

def _parse_command(command: str, board: Board) -> None:
    command_list: list[str] = get_keywords(command)
    command_type = command_list[0].lower()
    keywords = command_list[1:]

    if command_type not in function_list:
        raise RuntimeError("No command key phrases found")
    if len(keywords) < 2:
        raise RuntimeError("Missing command keywords")
    new_key, new_value = function_list[command_type](command_type, keywords, board)
    if new_key is not None:
        get_connection().execute_arbitrary_sql(
            "INSERT OR REPLACE INTO board_parameters (board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
            (board.board_id, new_key, new_value)
        )
