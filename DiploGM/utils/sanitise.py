"""Module to sanitise string inputs to stuff that the bot likes."""
import os
import re

from DiploGM.models.turn import PhaseName, Turn
from DiploGM.models.unit import UnitType
from discord.ext import commands

coast_dict = {
    "nc": ["nc", "north coast", "(nc)"],
    "sc": ["sc", "south coast", "(sc)"],
    "ec": ["ec", "east coast", "(ec)"],
    "wc": ["wc", "west coast", "(wc)"],
}

ARMY = "army"
FLEET = "fleet"

unit_dict = {
    ARMY: ["a", "army", "cannon"],
    FLEET: ["f", "fleet", "boat", "ship"],
}

def sanitise_name(name: str) -> str:
    """Removes apostrophes and replaces hyphens with spaces."""
    name = re.sub(r"[‘’`´′‛.']", "", name)
    name = re.sub(r"-", " ", name)
    return name


# I'm sorry this is a bad function name. I couldn't think of anything better and I'm in a rush
def simple_player_name(name: str) -> str:
    """Returns a player name without hyphens, apostrophes or periods and in lowercase."""
    return name.lower().replace("-", " ").replace("'", "").replace(".", "")


def get_keywords(command: str) -> list[str]:
    """Command is split by whitespace with '_' representing whitespace in a concept to be stuck in one word.
    e.g. 'A New_York - Boston' becomes ['A', 'New York', '-', 'Boston']"""
    keywords = command.split(" ")
    for i, _ in enumerate(keywords):
        for j, _ in enumerate(keywords[i]):
            if keywords[i][j] == "_":
                keywords[i] = keywords[i][:j] + " " + keywords[i][j + 1 :]

    for i, keyword in enumerate(keywords):
        keywords[i] = _manage_coast_signature(keyword)

    return keywords


def _manage_coast_signature(keyword: str) -> str:
    for coast_key, coast_val in coast_dict.items():
        # we want to make sure this was a separate word like "zapotec ec" and not part of a word like "zapotec"
        suffix = f" {coast_val}"
        if keyword.endswith(suffix):
            # remove the suffix
            keyword = keyword[: len(keyword) - len(suffix)]
            # replace the suffix with the one we expect
            new_suffix = f" {coast_key}"
            keyword += f" {new_suffix}"
    return keyword


def get_unit_type(command: str) -> UnitType | None:
    """Gets the unit type from its string."""
    command = command.strip()
    if command in unit_dict[ARMY]:
        return UnitType.ARMY
    if command in unit_dict[FLEET]:
        return UnitType.FLEET
    return None


def parse_season(
    arguments: list[str], default_turn: Turn
) -> Turn:
    """Given a string, attempts to parse it into a Turn.
    The result should be at latest default_turn, and that is used if year is not given."""
    year, season, retreat = None, None, False
    for s in arguments:
        if s.isnumeric() and int(s) >= default_turn.start_year:
            year = int(s)

        if s.lower() in ["spring", "s", "sm", "sr"]:
            season = PhaseName.SPRING_MOVES
        elif s.lower() in ["fall", "f", "fm", "fr"]:
            season = PhaseName.FALL_MOVES
        elif s.lower() in ["winter", "w", "wa"]:
            season = PhaseName.WINTER_BUILDS

        retreat = retreat or s.lower() in ["retreat", "retreats", "r", "sr", "fr"]

    if year is None:
        if season is None:
            return default_turn
        year = default_turn.year
    season = season or PhaseName.SPRING_MOVES

    if retreat and season != PhaseName.WINTER_BUILDS:
        season = PhaseName(season.value + 1)

    new_turn = Turn(year, season, default_turn.start_year)
    new_turn.year = min(new_turn.year, default_turn.year)
    if new_turn.year == default_turn.year and new_turn.phase.value > default_turn.phase.value:
        if new_turn.year == default_turn.start_year:
            return default_turn
        return Turn(new_turn.year - 1, season, default_turn.start_year)
    return new_turn


def get_value_from_timestamp(timestamp: str) -> int | None:
    """Gets the value from a timestamp string."""
    if len(timestamp) == 10 and timestamp.isnumeric():
        return int(timestamp)

    match = re.match(r"<t:(\d{10}):\w>", timestamp)
    if match:
        return int(match.group(1))

    return None

def parse_variant_path(variant: str, as_filename: bool = True, return_parent: bool = False) -> str:
    """Parses the variant path to get the correct path for the parser."""
    if os.path.isdir(f"variants/{variant}"):
        if return_parent:
            return f"variants/{variant}"
        if os.path.isfile(f"variants/{variant}/config.json"):
            return f"variants/{variant}" if as_filename else variant
        variant_list = sorted(os.listdir(f"variants/{variant}"), reverse=True)
        for v in variant_list:
            if os.path.isdir(f"variants/{variant}/{v}") and os.path.isfile(f"variants/{variant}/{v}/config.json"):
                return f"variants/{variant}/{v}" if as_filename else v
    else:
        variant_name, _ = variant.split(".", 1)
        variant_path = f"variants/{variant_name}/{variant}"
        if os.path.isdir(variant_path) and os.path.isfile(f"{variant_path}/config.json"):
            if return_parent:
                return f"variants/{variant_name}"
            return variant_path if as_filename else variant
    raise ValueError(f"Variant {variant} does not exist or is missing a config file.")

def remove_prefix(ctx: commands.Context) -> str:
    """Removes the command prefix from the message content."""
    return ctx.message.content.removeprefix(f"{ctx.prefix}{ctx.invoked_with}").strip()
