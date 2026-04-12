"""Helper functions for getting text representations of orders with specific criteria."""
from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING
from discord.ext.commands import Context

from DiploGM.utils.sanitise import find_discord_role
from DiploGM.models.order import PlayerOrder
from DiploGM.models.player import ForcedDisbandOption, Player, ViewOrdersTags, OrdersSubsetOption

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.models.unit import Unit

def get_build_orders(player: Player,
                     player_restriction: Player | None,
                     ctx: Context,
                     tags: ViewOrdersTags) -> tuple[str | None, str | None]:
    """Returns a text representation of a player's build orders with the specific criteria.
    If no build orders match the criteria, returns (None, None) to indicate the player should be hidden.
    Tag options are currently Missing and Submitted."""
    assert ctx.guild is not None
    if (not player_restriction and
        (len(player.centers) + len(player.units) == 0)):
        return None, None

    if player_restriction and player != player_restriction:
        return None, None

    if (tags.subset == OrdersSubsetOption.MISSING and
        abs(len(player.centers) - len(player.units) - player.waived_orders) == len(player.build_orders)):
        return None, None

    if (tags.subset == OrdersSubsetOption.SUBMITTED
        and len(player.build_orders) == 0
        and player.waived_orders == 0):
        return None, None

    if (player_role := find_discord_role(player, ctx.guild.roles)) is not None:
        player_name = player_role.mention
    else:
        player_name = player.get_name()

    build_count = len(player.centers) - len(player.units)
    order_count = len(player.build_orders) + player.waived_orders

    title = f"**{player_name}**: ({len(player.centers)}) " + \
            f"({'+' if build_count >= 0 else ''}" + \
            f"{build_count})" + f" ({order_count})"
    body = ""
    if tags.blind:
        return title, ""

    for unit in player.build_orders | set(
        player.vassal_orders.values()
    ):
        body += f"\n{unit}"
    if player.waived_orders > 0:
        body += f"\nWaive {player.waived_orders}"
    return title, body

def _get_move_orders(board: Board,
                    player: Player,
                    player_restriction: Player | None,
                    ctx: Context,
                    tags: ViewOrdersTags,
                    is_retreats: bool) -> tuple[str | None, str | None]:
    """Returns a text representation of a player's move orders with the specific criteria.
    If no move orders match the criteria, returns (None, None) to indicate the player should be hidden.
    Tag options are currently Missing, Submitted, as well as Force Disband options."""

    assert ctx.guild is not None
    if (not player_restriction
        and len(player.centers) + len(player.units) == 0):
        return None, None

    def in_moves(u: Unit) -> bool:
        return u == u.province.dislodged_unit if is_retreats else True

    moving_units = [unit for unit in player.units if in_moves(unit)]
    ordered = [unit for unit in moving_units if unit.order is not None]
    missing = [unit for unit in moving_units if unit.order is None]

    dp_orders = board.get_player_dp_orders(player)
    match tags.subset:
        case OrdersSubsetOption.MISSING:
            if not missing:
                return (None, None)
        case OrdersSubsetOption.SUBMITTED:
            if not ordered and not dp_orders:
                return (None, None)

    if (player_role := find_discord_role(player, ctx.guild.roles)) is not None:
        player_name = player_role.mention
    else:
        player_name = player.get_name()

    forced_disband_count = sum(unit.retreat_options is None or len(unit.retreat_options) == 0 for unit in missing)
    total_unit_count = len(moving_units)

    if tags.forced == ForcedDisbandOption.ONLY_FREE:
        total_unit_count -= forced_disband_count
        if total_unit_count == len(ordered):
            return None, None

    title = f"**{player_name}** ({len(ordered)}/{total_unit_count})"
    if board.data.get("dp", "False").lower() in ("true", "enabled"):
        title += f" ({board.get_dp_spent(player)}/{player.dp_max} DP)"

    if is_retreats and tags.forced == ForcedDisbandOption.MARK_FORCED and forced_disband_count > 0:
        title += rf" ({forced_disband_count} \*)"

    body = ""
    if tags.blind:
        return title, body

    if missing and tags.subset != OrdersSubsetOption.SUBMITTED:
        body += "__Missing Orders:__\n"
        for unit in sorted(missing, key=lambda _unit: _unit.province.name):
            unit_is_forced = is_retreats and not unit.retreat_options
            if unit_is_forced and tags.forced == ForcedDisbandOption.ONLY_FREE:
                continue
            body += f"{unit}"
            if unit_is_forced and tags.forced == ForcedDisbandOption.MARK_FORCED:
                body += r" \*"
            body += "\n"
    if (ordered or dp_orders) and tags.subset != OrdersSubsetOption.MISSING:
        body += "__Submitted Orders:__\n"
        for unit in sorted(ordered, key=lambda _unit: _unit.province.name):
            body += f"{unit} {unit.order}\n"
        for unit, allocation in dp_orders.items():
            body += f"DP {allocation.points}: {unit} {allocation.order}\n"
    return title, body

def get_orders(
    board: Board,
    player_restriction: Player | None,
    ctx: Context,
    fields: bool = False,
    tags: ViewOrdersTags | None = None
) -> str | List[Tuple[str, str]]:
    """Returns a text representation of players' orders with the specific criteria.
    If no orders match the criteria for a player, that player is hidden."""
    if fields:
        response = []
    else:
        response = ""

    if tags is None:
        tags = ViewOrdersTags.get_default()

    if player_restriction is None:
        players = board.players
    else:
        players = {player_restriction}

    for player in sorted(players, key=lambda sort_player: sort_player.get_name()):
        if board.is_player_hidden(player):
            continue
        if board.turn.is_builds():
            title, body = get_build_orders(player, player_restriction, ctx, tags)
        else:
            title, body = _get_move_orders(board, player, player_restriction, ctx, tags,
                                          board.turn.is_retreats())
        if title is None:
            continue
        if isinstance(response, list):
            response.append(("", f"{title}\n{body}"))
        else:
            response += f"{title}\n{body}"
    return response

def get_filtered_orders(board: Board, player_restriction: Player) -> str:
    """Variant of get_orders used in Fog of War games.
    Might need updating."""
    visible = board.get_visible_provinces(player_restriction)
    if board.turn.is_builds():
        response = ""
        for player in sorted(board.players, key=lambda sort_player: sort_player.get_name()):
            if board.is_player_hidden(player) or (player_restriction is not None and player != player_restriction):
                continue
            visible = [
                order
                for order in player.build_orders
                if isinstance(order, PlayerOrder) and order.province.name in visible
            ]

            if len(visible) > 0:
                response += f"\n**{player.get_name()}**: ({len(player.centers)}) " + \
                    f"({'+' if len(player.centers) - len(player.units) >= 0 else ''}" + \
                    f"{len(player.centers) - len(player.units)})"
                for unit in visible:
                    response += f"\n{unit}"
        return response
    response = ""

    def in_moves(u: Unit) -> bool:
        return u == u.province.dislodged_unit if board.turn.is_retreats() else True

    for player in board.players:
        if board.is_player_hidden(player):
            continue
        moving_units = [
            unit
            for unit in player.units
            if in_moves(unit) and unit.province in visible
        ]

        if len(moving_units) > 0:
            ordered = [unit for unit in moving_units if unit.order is not None]
            missing = [unit for unit in moving_units if unit.order is None]

            response += f"**{player.get_name()}** ({len(ordered)}/{len(moving_units)})\n"
            if missing:
                response += "__Missing Orders:__\n"
                for unit in sorted(missing, key=lambda _unit: _unit.province.name):
                    response += f"{unit}\n"
            if ordered:
                response += "__Submitted Orders:__\n"
                for unit in sorted(ordered, key=lambda _unit: _unit.province.name):
                    response += f"{unit} {unit.order}\n"

    return response
