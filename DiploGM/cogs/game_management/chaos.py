"""Chaos-related game management commands. Might be removed in the future."""
import logging
from discord import Member, PermissionOverwrite, TextChannel, Thread
from discord.ext import commands
from DiploGM import config
from DiploGM import perms
from DiploGM.perms import is_gm
from DiploGM.utils import send_message_and_file
from DiploGM.manager import Manager

logger = logging.getLogger(__name__)
manager = Manager()

async def publicize(ctx: commands.Context) -> None:
    """Opens a channel (usually a void) to the spectator role"""
    assert ctx.guild is not None
    if not is_gm(ctx.message.author):
        raise PermissionError(
            "You cannot publicize a void because you are not a GM."
        )

    channel = ctx.channel
    assert isinstance(channel, TextChannel)
    board = manager.get_board(ctx.guild.id)

    if not board.is_chaos():
        await send_message_and_file(
            channel=channel,
            message="This command only works for chaos games.",
            embed_colour=config.ERROR_COLOUR,
        )

    player = perms.get_player_by_channel(board, channel, ignore_category=True)

    # TODO hacky
    users = []
    user_permissions: list[tuple[Member, PermissionOverwrite]] = []
    # Find users with access to this channel
    for overwritter, user_permission in channel.overwrites.items():
        if isinstance(overwritter, Member) and user_permission.view_channel:
            users.append(overwritter)
            user_permissions.append((overwritter, user_permission))

    # TODO don't hardcode
    staff_role = None
    spectator_role = None
    for role in ctx.guild.roles:
        if role.name == "World Chaos Staff":
            staff_role = role
        elif role.name == "Spectators":
            spectator_role = role

    if not staff_role or not spectator_role:
        return

    if not player or len(users) == 0:
        await send_message_and_file(
            channel=ctx.channel,
            message="Can't find the applicable user.",
            embed_colour=config.ERROR_COLOUR,
        )
        return

    # Create Thread
    thread: Thread = await channel.create_thread(
        name=f"{player.get_name().capitalize()} Orders",
        reason=f"Creating Orders for {player.get_name()}",
        invitable=False,
    )
    await thread.send(
        f"{''.join([u.mention for u in users])} | {staff_role.mention}"
    )

    # Allow for sending messages in thread
    for user, permission in user_permissions:
        permission.send_messages_in_threads = True
        await channel.set_permissions(target=user, overwrite=permission)

    # Add spectators
    spectator_permissions = PermissionOverwrite(
        view_channel=True, send_messages=False
    )
    await channel.set_permissions(
        target=spectator_role, overwrite=spectator_permissions
    )

    # Update name
    await channel.edit(name=channel.name.replace("orders", "void"))

    await send_message_and_file(
        channel=channel, message="Finished publicizing void."
    )
