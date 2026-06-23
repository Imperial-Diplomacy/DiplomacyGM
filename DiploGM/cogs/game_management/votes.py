"""Game management commands related to votes to surrender/draw."""

import logging

from discord import TextChannel
from discord.ext import commands

from DiploGM.manager import Manager
from DiploGM.utils import send_message
from DiploGM.utils.sanitise import remove_prefix
manager = Manager()
logger = logging.getLogger(__name__)


async def tally_reactions(ctx: commands.Context, message_id: int) -> None:
    """Given a link to a Discord message, output which powers have reacted to each reaction on the message."""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)
    content = remove_prefix(ctx)

    # Need a real way to find draw votes channel
    draw_votes_channel_name = "draw-votes"
    draw_votes_channel = next(c for c in ctx.guild.channels if c.name == draw_votes_channel_name and isinstance(c, TextChannel))
    if draw_votes_channel is None:
            await send_message.send_message_and_file(
                channel=ctx.channel,
                title=f"No channel named {draw_votes_channel_name}",
            )
            return

    message = await draw_votes_channel.fetch_message(message_id)

    reacts: dict[str, dict[str, set[str]]] = {}
    for react in message.reactions:
        emoji = str(react.emoji)
        reacts[emoji] = {
            "player": set(),
            "non_player": set(),
        }
        async for user in react.users():
            try:
                player = board.get_player(user.name)
                if player is not None:
                    reacts[emoji]["player"].add(player.name)
            except ValueError:
                reacts[emoji]["non_player"].add(user.name)
    
    player_output = ""
    nonplayer_output = ""

    for react, usersets in reacts.items():
        players, nonplayers = usersets["player"], usersets["non_player"]
        logger.info(f"Tallying reacts for {react}, {len(players) + len(nonplayers)} total")
        player_output += f"{react}: {' '.join(f'@{name}' for name in sorted(players))}\n"
        nonplayer_output += f"{react}: {' '.join(f'@{name} ' for name in sorted(nonplayers))}\n"

    await send_message.send_message_and_file(
        channel=ctx.channel,
        title="Tallied votes",
        message=f"**Players**\n{player_output}\n**Non-players**\n{nonplayer_output}"
    )
