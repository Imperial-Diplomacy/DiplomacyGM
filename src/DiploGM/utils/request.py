from dataclasses import dataclass
from discord import Guild, Member, TextChannel, User

@dataclass
class Request:
    """Class for storing information about a request"""
    guild: Guild
    channel: TextChannel
    author: User | Member
