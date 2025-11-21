import logging

import discord


def log_command(
    remote_logger: logging.Logger,
    ctx: discord.ext.commands.Context,
    message: str,
    *,
    level=logging.INFO,
) -> None:
    # FIXME Should probably delete this function and use a logging formatter instead
    log_command_no_ctx(
        remote_logger,
        ctx.message.content,
        ctx.guild.name,
        ctx.channel.name,
        ctx.author.name,
        message,
        level=level,
    )


def log_command_no_ctx(
    remote_logger: logging.Logger,
    invoke_message: str,
    guild: str,
    channel: str,
    invoker: str,
    message: str,
    *,
    level=logging.INFO,
) -> None:
    # FIXME Should probably delete this function and use a logging formatter instead

    if level <= logging.DEBUG:
        command_len_limit = -1
    else:
        command_len_limit = 40

    # this might be too expensive?
    command = (
        invoke_message[:command_len_limit].encode("unicode_escape").decode("utf-8")
    )
    if len(invoke_message) > 40:
        command += "..."

    # temporary handling for bad error messages should be removed when we are nolonger passing
    # messages intended for Discord to this function. FIXME
    message = message.encode("unicode_escape").decode("utf-8")

    remote_logger.log(
        level, f"[{guild}][#{channel}]({invoker}) - " f"'{command}' -> " f"{message}"
    )
