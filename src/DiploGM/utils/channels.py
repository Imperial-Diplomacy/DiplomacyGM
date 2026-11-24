import discord

from DiploGM.config import ChannelName, CHANNEL_DEFAULTS, is_gm_category, is_gm_channel
from DiploGM.manager import Manager

def get_gm_channel(guild: discord.Guild) -> discord.TextChannel | None:
    """Returns the GM channel for the given guild."""
    for category in guild.categories:
        if is_gm_category(category):
            for channel in category.channels:
                if isinstance(channel, discord.TextChannel) and is_gm_channel(channel):
                    return channel
    return None

def get_guild_channel(guild: discord.Guild, manager: Manager, channel_id: ChannelName) -> discord.TextChannel | None:
    custom_name = manager.get_ctx_parameter(guild.id, ["channel_names", channel_id.value])
    if not isinstance(custom_name, str):
        custom_name = CHANNEL_DEFAULTS[channel_id]
    return discord.utils.get(guild.text_channels, name=custom_name)
