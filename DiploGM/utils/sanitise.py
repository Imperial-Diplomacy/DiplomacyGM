
import re

from DiploGM.models.turn import Turn
from DiploGM.models.unit import UnitType


_north_coast = "nc"
_south_coast = "sc"
_east_coast = "ec"
_west_coast = "wc"

coast_dict = {
    _north_coast: ["nc", "north coast", "(nc)"],
    _south_coast: ["sc", "south coast", "(sc)"],
    _east_coast: ["ec", "east coast", "(ec)"],
    _west_coast: ["wc", "west coast", "(wc)"],
}

_army = "army"
_fleet = "fleet"

unit_dict = {
    _army: ["a", "army", "cannon"],
    _fleet: ["f", "fleet", "boat", "ship"],
}

def sanitise_name(str):
    str = re.sub(r"[‘’`´′‛.']", "", str)
    str = re.sub(r"-", " ", str)
    return str


# I'm sorry this is a bad function name. I couldn't think of anything better and I'm in a rush
def simple_player_name(name: str):
    return name.lower().replace("-", " ").replace("'", "").replace(".", "")


def get_keywords(command: str) -> list[str]:
    """Command is split by whitespace with '_' representing whitespace in a concept to be stuck in one word.
    e.g. 'A New_York - Boston' becomes ['A', 'New York', '-', 'Boston']"""
    keywords = command.split(" ")
    for i in range(len(keywords)):
        for j in range(len(keywords[i])):
            if keywords[i][j] == "_":
                keywords[i] = keywords[i][:j] + " " + keywords[i][j + 1 :]

    for i in range(len(keywords)):
        keywords[i] = _manage_coast_signature(keywords[i])

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
    command = command.strip()
    if command in unit_dict[_army]:
        return UnitType.ARMY
    if command in unit_dict[_fleet]:
        return UnitType.FLEET
    return None


def parse_season(
    arguments: list[str], default_year: int
) -> Turn | None:
    year, season, retreat = default_year, None, False
    for s in arguments:
        if s.isnumeric() and int(s) > 1640:
            year = int(s)

        if s.lower() in ["spring", "s", "sm", "sr"]:
            season = "Spring"
        elif s.lower() in ["fall", "f", "fm", "fr"]:
            season = "Fall"
        elif s.lower() in ["winter", "w", "wa"]:
            season = "Winter"

        if s.lower() in ["retreat", "retreats", "r", "sr", "fr"]:
            retreat = True

    if season is None:
        return None
    if season == "Winter":
        return Turn(year, "Winter Builds")
    else:
        return Turn(year, season + " " + ("Retreats" if retreat else "Moves"))


def get_value_from_timestamp(timestamp: str) -> int | None:
    if len(timestamp) == 10 and timestamp.isnumeric():
        return int(timestamp)

    match = re.match(r"<t:(\d{10}):\w>", timestamp)
    if match:
        return int(match.group(1))

    return None
