import logging
import tomllib
from typing import List, Tuple, Any

def merge_toml(main: dict[str, Any], default: dict[str, Any], current_path: str = "") -> Tuple[
    List[Tuple[int, str]], dict[str, Any]]:
    output = {}
    errors = []
    for key in default:
        if key in main:
            if type(main[key]) is type(default[key]):
                if isinstance(main[key], dict):
                    new_errors, output[key] = merge_toml(main[key], default[key], current_path=key)
                    errors.extend(new_errors)
                else:
                    output[key] = main[key]
            else:
                errors.append((logging.ERROR, f"Mismatched config types: {current_path}"))
        else:
            output[key] = default[key]
    return errors, output


def output_config_logs(logger=None):
    if logger is None:
        logger = logging.getLogger(__name__)
    for error in toml_errors:
        logger.log(error[0], error[1])


class ConfigException(Exception):
    pass


with open("config_defaults.toml", "rb") as toml_file:
    _default_toml = tomllib.load(toml_file)

with open("config.toml", "rb") as toml_file:
    _toml = tomllib.load(toml_file)


toml_errors, all_config = merge_toml(_toml, _default_toml)

# BOT CONFIG
DISCORD_TOKEN = all_config["bot"]["discord_token"]
LOGGING_LEVEL = all_config["bot"]["log_level"]
COMMAND_PREFIX = all_config["bot"]["command_prefix"]


# ARCHIVE WEBSITE
MAP_ARCHIVE_SAS_TOKEN = all_config["archive_website"]["sas_token"]
MAP_ARCHIVE_UPLOAD_URL = all_config["archive_website"]["upload_url"]
MAP_ARCHIVE_URL = all_config["archive_website"]["url"]


# DEVELOPMENT SERVER HUB
BOT_DEV_SERVER_ID = all_config["dev_hub"]["id"]
BOT_DEV_UNHANDLED_ERRORS_CHANNEL_ID = all_config["dev_hub"]["unhandled_errors_channel"]

# IMPERIAL DIPLOMACY HUB
IMPDIP_SERVER_ID = all_config["hub"]["id"]
## Channels
IMPDIP_SERVER_BOT_STATUS_CHANNEL_ID = all_config["hub"]["status_channel"]
IMPDIP_SERVER_SUBSTITUTE_TICKET_CHANNEL_ID = all_config["hub"]["substitute_ticket_channel"]
IMPDIP_SERVER_SUBSTITUTE_ADVERTISE_CHANNEL_ID = all_config["hub"]["substitute_advertise_channel"]
IMPDIP_SERVER_SUBSTITUTE_LOG_CHANNEL_ID = all_config["hub"]["substitute_log_channel"]
IMPDIP_SERVER_WINTER_SCOREBOARD_OUTPUT_CHANNEL_ID = all_config["hub"]["winter_scoreboard_output_channel"]
## Roles
IMPDIP_BOT_WIZARD_ROLE: int = all_config["hub"]["bot_wizard"]
IMPDIP_MOD_ROLES: List[int] = all_config["hub"]["moderation_team_roles"]

# GAME SERVERS
GAME_SERVER_MODERATOR_ROLE_NAMES: List[str] = all_config["game_servers"]["game_server_moderator_role_names"]
GM_PERMISSION_ROLE_NAMES: List[str] = all_config["game_servers"]["gm_permission_role_names"]
GM_CATEGORY_NAMES: List[str] = all_config["game_servers"]["gm_category_names"]
GM_CHANNEL_NAMES: List[str] = all_config["game_servers"]["gm_channel_names"]
PLAYER_PERMISSION_ROLE_NAMES: List[str] = all_config["game_servers"]["player_permission_role_names"]
PLAYER_ORDER_CATEGORY_NAMES: List[str] = all_config["game_servers"]["player_permission_role_names"]
PLAYER_ORDER_CHANNEL_SUFFIX: str = all_config["game_servers"]["player_permission_role_names"]


# PERMISSIONS
SUPERUSERS = all_config["permissions"]["superusers"]

# EXTENSIONS
EXTENSIONS_TO_LOAD_ON_STARTUP = all_config["extensions"]["load_on_startup"]

# COLOURS
EMBED_STANDARD_COLOUR = all_config["colours"]["embed_standard"]
PARTIAL_ERROR_COLOUR = all_config["colours"]["embed_partial_success"]
ERROR_COLOUR = all_config["colours"]["embed_error"]

# TODO: move to config_defaults.toml if applicable or elsewhere
color_options = {"standard", "dark", "pink", "blue", "kingdoms", "empires"}

# INKSCAPE
SIMULATRANEOUS_SVG_EXPORT_LIMIT = all_config["inkscape"]["simultaneous_svg_exports_limit"]

# PARTY
BUMBLE_ID = all_config["party"]["bumble_id"]
EOLHC_ID = all_config["party"]["eolhc_id"]
AAHOUGHTON_ID = all_config["party"]["aahoughton_id"]
