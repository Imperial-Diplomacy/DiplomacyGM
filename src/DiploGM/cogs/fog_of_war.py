import asyncio
import logging

from discord import TextChannel
from discord.ext import commands

from DiploGM import config
from DiploGM import perms
from DiploGM.models.board import Board
from DiploGM.utils import (
    get_orders,
    send_message_and_file,
)
from DiploGM.manager import Manager
from DiploGM.models.player import (
    ForcedDisbandOption,
    OrdersSubsetOption,
    Player,
    ViewOrdersTags,
)
from DiploGM.utils.image import svg_to_png
from DiploGM.utils.send_message import ErrorMessage, send_error

logger = logging.getLogger(__name__)
manager = Manager()

# if possible save one svg slot for others
fow_export_limit = asyncio.Semaphore(
    max(int(config.SIMULATRANEOUS_SVG_EXPORT_LIMIT) - 1, 1)
)


class FogOfWarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_player_list(
        self, ctx: commands.Context, board: Board
    ) -> set[tuple[Player, TextChannel]]:
        assert ctx.guild is not None

        if board.data.get("fow", "disabled") != "enabled":
            await send_error(ctx.channel, ErrorMessage.FOW_DISABLED)
            return set()

        player_category = next(
            (c for c in ctx.guild.categories if config.is_player_category(c)), None
        )
        if not player_category:
            await send_error(ctx.channel, ErrorMessage.NO_PLAYER_CATEGORY)
            return set()

        player_list = set()

        for channel in player_category.channels:
            if not isinstance(channel, TextChannel):
                continue
            if not (player := perms.get_player_by_channel(board, channel)):
                continue
            if (len(player.units) + len(player.centers) == 0) or not player.is_active:
                continue
            player_list.add((player, channel))

        return player_list

    @commands.command(
        brief="Sends fog of war maps",
    )
    @perms.gm_only("publish fow moves")
    async def publish_fow_moves(self, ctx: commands.Context):
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        player_list = await self._get_player_list(ctx, board)
        if not player_list:
            return

        dpi = board.data["svg config"].get("dpi", 200)
        prev_turn = board.turn.get_previous_turn()

        for player, channel in player_list:
            file, file_name = manager.draw_map(
                server_id=ctx.guild.id,
                draw_moves=True,
                turn=prev_turn,
                fow_player=player,
            )
            file, file_name = await svg_to_png(file, file_name, board.data["svg config"])
            await send_message_and_file(
                channel=channel,
                title=f"{prev_turn} Orders Map",
                message=f"Here is the {prev_turn} orders map for {player.name}",
                file=file,
                file_name=file_name,
                file_in_embed=False,
            )
            await asyncio.sleep(0)

            file, file_name = manager.draw_map(
                server_id=ctx.guild.id,
                draw_moves=False,
                turn=board.turn,
                fow_player=player,
            )
            file, file_name = await svg_to_png(file, file_name, board.data["svg config"])
            await send_message_and_file(
                channel=channel,
                title=f"{prev_turn} Results Map",
                message=f"Here is the {prev_turn} results map for {player.name}",
                file=file,
                file_name=file_name,
                file_in_embed=False,
            )
            await asyncio.sleep(0)

        await send_message_and_file(
            channel=ctx.channel,
            title="Published maps to order channels",
        )

    @commands.command(
        brief="Sends fog of war orders",
    )
    @perms.gm_only("send fow order logs")
    async def publish_fow_order_logs(self, ctx: commands.Context):
        assert ctx.guild is not None
        board = manager.get_board(ctx.guild.id)

        player_list = await self._get_player_list(ctx, board)
        if not player_list:
            return
        assert ctx.guild is not None

        guild = ctx.guild
        guild_id = guild.id
        board = manager.get_previous_board(guild_id)
        tags = ViewOrdersTags(
            subset=OrdersSubsetOption.FULL,
            forced=ForcedDisbandOption.MARK_FORCED,
            blind=False,
            open_cores=False,
            explain=False,
        )
        if board is None:
            await send_error(ctx.channel, ErrorMessage.NO_PREVIOUS_BOARD)
            return

        for player, channel in player_list:
            prev_player = board.get_player(player.name)
            if not prev_player:
                continue
            message = get_orders(
                board=board,
                player_restriction=None,
                ctx=ctx,
                tags=tags,
                fields=False,
                fow_restriction=prev_player,
            )
            if not isinstance(message, str) or not message:
                continue
            title = f"{board.turn} Order Log"
            await send_message_and_file(channel=channel, title=title, message=message)

        await send_message_and_file(
            channel=ctx.channel,
            title="Published order logs to order channels",
        )


async def setup(bot):
    cog = FogOfWarCog(bot)
    await bot.add_cog(cog)
