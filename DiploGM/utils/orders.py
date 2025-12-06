from typing import List, Tuple

from DiploGM.models.order import PlayerOrder
from discord.ext.commands import Context

from DiploGM.models.board import Board
from DiploGM.models.player import Player

def get_build_orders(player: Player, player_restriction: Player | None, ctx: Context, subset: str | None, blind: bool) -> tuple[str | None, str | None]:
    if (not player_restriction and
        (len(player.centers) + len(player.units) == 0)):
        return None, None
    
    if player_restriction and player != player_restriction:
        return None, None

    if (subset == "missing" and
        abs(len(player.centers) - len(player.units) - player.waived_orders) == len(player.build_orders)):
        return None, None

    if (subset == "submitted"
        and len(player.build_orders) == 0
        and player.waived_orders == 0):
        return None, None
        
    if (player_role := player.find_discord_role(ctx.guild.roles)) is not None:
        player_name = player_role.mention
    else:
        player_name = player.name


    title = f"**{player_name}**: ({len(player.centers)}) ({'+' if len(player.centers) - len(player.units) >= 0 else ''}{len(player.centers) - len(player.units)})"
    body = ""
    if blind:
        return title, f" ({len(player.build_orders) + player.waived_orders})"
    
    for unit in player.build_orders | set(
        player.vassal_orders.values()
    ):
        body += f"\n{unit}"
    if player.waived_orders > 0:
        body += f"\nWaive {player.waived_orders}"
    return title, body

def get_move_orders(player: Player, player_restriction: Player | None, ctx: Context, subset: str | None, blind: bool, is_retreats: bool) -> tuple[str | None, str | None]:
    if (not player_restriction
        and len(player.centers) + len(player.units) == 0):
        return None, None

    if is_retreats:
        in_moves = lambda u: u == u.province.dislodged_unit
    else:
        in_moves = lambda _: True
    moving_units = [unit for unit in player.units if in_moves(unit)]
    ordered = [unit for unit in moving_units if unit.order is not None]
    missing = [unit for unit in moving_units if unit.order is None]

    if subset == "missing" and not missing:
        return None, None
    if subset == "submitted" and not ordered:
        return None, None

    if (player_role := player.find_discord_role(ctx.guild.roles)) is not None:
        player_name = player_role.mention
    else:
        player_name = player.name

    title = f"**{player_name}** ({len(ordered)}/{len(moving_units)})"
    body = ""
    if blind:
        return title, ""

    if missing and subset != "submitted":
        body += f"__Missing Orders:__\n"
        for unit in sorted(missing, key=lambda _unit: _unit.province.name):
            body += f"{unit}\n"
    if ordered and subset != "missing":
        body += f"__Submitted Orders:__\n"
        for unit in sorted(ordered, key=lambda _unit: _unit.province.name):
            body += f"{unit} {unit.order}\n"
    return title, body

def get_orders(
    board: Board,
    player_restriction: Player | None,
    ctx: Context,
    fields: bool = False,
    subset: str | None = None,
    blind: bool = False,
) -> str | List[Tuple[str, str]]:
    if fields:
        response = []
    else:
        response = ""
    #TODO: Lots of duplicated code here
    if board.turn.is_builds():
        for player in sorted(board.players, key=lambda sort_player: sort_player.name):
            title, body = get_build_orders(player, player_restriction, ctx, subset, blind)
            if title is None:
                continue
            if isinstance(response, list):
                response.append((f"", f"{title}{body}"))
            else:
                response += f"\n{title}{body}"
        return response
    else:

        if player_restriction is None:
            players = board.players
        else:
            players = {player_restriction}

        for player in sorted(players, key=lambda p: p.name):
            title, body = get_move_orders(player, player_restriction, ctx, subset, blind, board.turn.is_retreats())
            if title is None:
                continue
            if isinstance(response, list):
                response.append((f"", f"{title}\n{body}"))
            else:
                response += f"{title}\n{body}"

        return response


def get_filtered_orders(board: Board, player_restriction: Player) -> str:
    visible = board.get_visible_provinces(player_restriction)
    if board.turn.is_builds():
        response = ""
        for player in sorted(board.players, key=lambda sort_player: sort_player.name):
            if not player_restriction or player == player_restriction:
                visible = [
                    order
                    for order in player.build_orders
                    if isinstance(order, PlayerOrder) and order.province.name in visible
                ]

                if len(visible) > 0:
                    response += f"\n**{player.name}**: ({len(player.centers)}) ({'+' if len(player.centers) - len(player.units) >= 0 else ''}{len(player.centers) - len(player.units)})"
                    for unit in visible:
                        response += f"\n{unit}"
        return response
    else:
        response = ""

        for player in board.players:
            if board.turn.is_retreats():
                in_moves = lambda u: u == u.province.dislodged_unit
            else:
                in_moves = lambda _: True
            moving_units = [
                unit
                for unit in player.units
                if in_moves(unit) and unit.province in visible
            ]

            if len(moving_units) > 0:
                ordered = [unit for unit in moving_units if unit.order is not None]
                missing = [unit for unit in moving_units if unit.order is None]

                response += f"**{player.name}** ({len(ordered)}/{len(moving_units)})\n"
                if missing:
                    response += f"__Missing Orders:__\n"
                    for unit in sorted(missing, key=lambda _unit: _unit.province.name):
                        response += f"{unit}\n"
                if ordered:
                    response += f"__Submitted Orders:__\n"
                    for unit in sorted(ordered, key=lambda _unit: _unit.province.name):
                        response += f"{unit} {unit.order}\n"

        return response
