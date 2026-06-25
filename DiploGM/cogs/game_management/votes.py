"""Game management commands related to votes to surrender/draw."""

import logging
import re
from typing import Callable, Optional

from discord import Guild, Member, TextChannel, User
from discord.ext import commands
from discord.state import Channel

from DiploGM import config
from DiploGM.manager import Manager
from DiploGM.models.board import Board
from DiploGM.models.player import Player
from DiploGM.utils import send_message
from DiploGM.utils.sanitise import find_discord_role
manager = Manager()
logger = logging.getLogger(__name__)

class ReactGroup:
    players: set[Player]
    nonplayers: set[User | Member]
    
    def __init__(self):
        self.players, self.nonplayers = set(), set()

async def tally_reacts(ctx: commands.Context, message_id: Optional[int], message_link: Optional[str]) -> None:
    """Given a link to a Discord message, output which powers have reacted to each reaction on the message."""
    assert ctx.guild is not None
    board = manager.get_board(ctx.guild.id)

    draw_votes_channel: Optional[Channel] = None
    if message_id is not None:
        draw_votes_channel = _get_draw_votes_channel(ctx.guild)

    if message_link is not None:
        pattern = r"https://(?:canary\.|ptb\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)"
        match = re.match(pattern, message_link)
        
        if not match:
            raise ValueError(f"Invalid link: {message_link}")

        _guild_id = int(match.group(1))
        channel_id = int(match.group(2))
        message_id = int(match.group(3))
        draw_votes_channel = ctx.guild.get_channel(channel_id)

    if not isinstance(draw_votes_channel, TextChannel):
        raise ValueError(f"No known draw votes channel")
    if message_id is None:
        raise ValueError("No message link provided")

    try:
        message = await draw_votes_channel.fetch_message(message_id)
    except:
        raise ValueError("No such message!")

    reacts: dict[str, ReactGroup] = {}
    for react in message.reactions:
        emoji = str(react.emoji)
        react_group = ReactGroup()
        async for user in react.users():
            player = _get_player_object_for_member_with_orders(ctx.guild, board, user)
            if player is not None:
                react_group.players.add(player)
            else:
                react_group.nonplayers.add(user)

        reacts[emoji] = react_group

    player_output = ""
    nonplayer_output = ""

    for react, react_group in reacts.items():
        players, nonplayers = react_group.players, react_group.nonplayers
        logger.info(f"Tallying reacts for {react}, {len(players) + len(nonplayers)} total")

        player_mentions = []
        for player in sorted(players, key=lambda k: k.name):
            role = find_discord_role(player, ctx.guild.roles)
            if role is not None: player_mentions.append(role.mention)
            else: player_mentions.append("@" + player.name)

        if (player_count := len(players)) > 0:
            player_output += f"{react} ({player_count}): {' '.join(mention for mention in player_mentions)}\n"
        if (nonplayer_count := len(nonplayers)) > 0:
            nonplayer_output += f"{react} ({nonplayer_count}): {' '.join(f'{player.mention}' for player in sorted(nonplayers, key=lambda k: k.name))}\n"

    response = ""
    if len(player_output) > 0:
        response += f"**Players**\n{player_output}\n"
    if len(nonplayer_output) > 0:
        response += f"""**Non-players**
        {nonplayer_output}
        Note: users are only considered players if they have a role formatted like `orders-power-name` where power-name is (exactly) the name of a power, in all lowercase."""

    await send_message.send_message_and_file(
        channel=ctx.channel,
        title="Tallied votes",
        message=response
    )

def _get_draw_votes_channel(guild: Guild) -> TextChannel | None:
    for channel in guild.channels:
        if (
            channel.name.lower() == config.DRAW_VOTES_CHANNEL
            and channel.category is not None
            and isinstance(channel, TextChannel)
        ):
            return channel
    return None

def _get_player_object_for_member_with_orders(guild: Guild, board: Board, user: User | Member) -> Optional[Player]:
    """WHAT a function name"""
    if isinstance(user, User):
        member = guild.get_member(user.id)
    else:
        member = user
    if member is None:
        return None

    player: Optional[Player] = None
    attempts: list[Callable[[Member], Optional[Player]]] = [
        lambda m: board.get_player(m.name),
        lambda m: manager.get_member_player_object(m)
    ]
    for attempt in attempts:
        if player is not None:
            break
        try:
            player = attempt(member)
        except ValueError:
            pass
    if player is None:
        return None
    if f"orders-{player.name.lower()}" not in (role.name for role in member.roles):
        return None

    return player