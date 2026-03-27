"""Parser for typed-in orders. Will turn a text order into Order objects with associated unit/provinces/players."""
from __future__ import annotations

import logging

from discord.ext.commands import Paginator
from lark import Lark, Transformer, UnexpectedEOF, UnexpectedCharacters, v_args
from lark.exceptions import VisitError

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.utils import get_unit_type, _manage_coast_signature
from DiploGM.models import order
from DiploGM.models.board import Board
from DiploGM.db.database import get_connection
from DiploGM.models.player import Player
from DiploGM.models.province import Province
from DiploGM.models.unit import DPAllocation, Unit, UnitType

logger = logging.getLogger(__name__)

@v_args(inline=True)
class TreeToOrder(Transformer):
    """The order parser. Each function takes in tokens (sans whitespace) as arguments."""
    def set_state(self, board: Board, player_restriction: Player | None):
        """Passes the board information into the parser."""
        self.board = board
        self.build_options = board.data.get("build_options", "classic")
        self.transform_options = board.data.get("transformation", "disabled")
        self.player_restriction = player_restriction

    @v_args(inline=False)
    def province(self, s) -> tuple[Province, str | None]:
        """Provinces are 1-4 words long, sometimes including a coast."""
        name = " ".join(s).replace("_", " ").strip()
        name = _manage_coast_signature(name)
        return self.board.get_province_and_coast(name)

    # used for supports, specifically FoW
    @v_args(inline=False)
    def l_unit(self, s) -> Province:
        """Turns a Unit into its associated provines.
        Handy for stuff like FoW where you don't know if there's a unit where you're trying to support/convoy."""
        # ignore the fleet/army signifier, if exists
        loc = s[-1][0]
        if loc is not None and not self.board.fow:
            unit = loc.unit
            if unit is None:
                raise ValueError(f"No unit in {s[-1][0]}")

        return loc

    @v_args(inline=False)
    def unit(self, s) -> Unit:
        """Gets the Unit located in a Province."""
        # ignore the fleet/army signifier, if exists
        unit = s[-1][0].unit
        if unit is None:
            raise ValueError(f"No unit in {s[-1][0]}")

        return unit

    @v_args(inline=False)
    def retreat_unit(self, s) -> Unit:
        """Gets the dislodged Unit located in a Province."""
        # ignore the fleet/army signifier, if exists
        unit = s[-1][0].dislodged_unit
        if unit is None:
            raise ValueError(f"No dislodged unit in {s[-1][0]}")

        return unit

    def hold_order(self, unit: Unit, _) -> tuple[Unit, order.Hold]:
        """Hold order, of the form [Unit] Hold."""
        return unit, order.Hold()

    def core_order(self, unit: Unit, _) -> tuple[Unit, order.Core]:
        """Core order, of the form [Unit] Core."""
        if self.build_options != "cores":
            raise ValueError("Coring is disabled in this gamemode")
        return unit, order.Core()

    def transform_order(self, unit: Unit, _, coast: str | None = None) -> tuple[Unit, order.Transform]:
        """Transform order, of the form [Unit] Transform [Coast?]."""
        if self.transform_options not in ["moves", "all"]:
            raise ValueError("Transforming during moves is disabled in this gamemode")
        return unit, order.Transform(coast)

    def dp_order(self, _, points: str, dp_order: tuple[Unit, order.UnitOrder]) -> tuple[Unit, None]:
        """DP allocation order, of the form DP [Points] [Unit Order]."""
        if self.player_restriction is None:
            raise ValueError("DP allocation orders must be made in a player's orders channel.")
        unit, unit_order = dp_order
        if unit.player is not None:
            raise ValueError(f"{unit.province} has an owner and cannot be assigned DP.")
        if points.endswith(":"):
            points = points[:-1]
        if int(points) <= 0:
            unit.dp_allocations.pop(self.player_restriction.name, None)
        else:
            unit.dp_allocations[self.player_restriction.name] = DPAllocation(int(points), unit_order)
        return unit, None

    def build_unit(self, _,
                   a: str | tuple[Province, str | None],
                   b: str | tuple[Province, str | None]) -> tuple[Province, Player | None, order.Build]:
        """Build order, of the form Build [Unit Type] [Province] or Build [Province] [Unit Type]."""
        if isinstance(a, tuple) and isinstance(b, str):
            province, coast = a
            unit_type = b
        elif isinstance(a, str) and isinstance(b, tuple):
            province, coast = b
            unit_type = a
        else:
            raise ValueError("Invalid build order format")

        unit_type = get_unit_type(unit_type)
        if unit_type is None:
            raise ValueError(f"{unit_type} isn't a valid unit type")

        if not province.has_supply_center:
            raise ValueError(f"{province} does not have a supply center.")
        if (unit_type == UnitType.FLEET
            and province.get_multiple_coasts()
            and coast not in province.get_multiple_coasts()):
            raise ValueError(f"You did not specify a coast for {province}")
        if self.player_restriction:
            if province.owner != self.player_restriction:
                raise ValueError(f"You do not own {province}.")
            if not province.can_build(self.build_options):
                raise ValueError(f"You cannot build in {province}.")

        return province, province.owner, order.Build(province, unit_type, coast)

    def disband_unit(self, a: Unit | str, b: Unit | str) -> tuple[Province, Player | None, order.Disband]:
        """Disband order, of the form Disband [Unit] or [Unit] Disband."""
        if isinstance(a, Unit) and isinstance(b, str):
            unit = a
        elif isinstance(a, str) and isinstance(b, Unit):
            unit = b
        else:
            raise ValueError("Invalid disband order format")
        return unit.province, unit.player, order.Disband(unit.province)

    def transform_unit(self,
                       a: Unit | str,
                       b: Unit | str,
                       coast: str | None = None) -> tuple[Province, Player | None, order.TransformBuild]:
        """Transform order, of the form Transform [Unit] [Coast?] or [Unit] Transform [Coast?]."""
        if self.transform_options not in ["builds", "all"]:
            raise ValueError("Transforming during builds is disabled in this gamemode")
        if isinstance(a, Unit) and isinstance(b, str):
            unit = a
        elif isinstance(a, str) and isinstance(b, Unit):
            unit = b
        else:
            raise ValueError("Invalid transform order format")
        return unit.province, unit.player, order.TransformBuild(unit.province, coast)

    def waive_order(self, _, waive_num: str) -> tuple[None, Player, order.Waive]:
        """Waive order, of the form Waive [Number]."""
        if self.player_restriction is None:
            raise ValueError("Please order waives in the appropriate player's orders channel.")
        return None, self.player_restriction, order.Waive(int(waive_num))

    def vassal_order(self, a: Province | str, b: Province | str) -> tuple[Player, Player, order.Vassal]:
        """Vassal order, of the form Vassalize [Province] or [Province] Vassalize."""
        if isinstance(a, Province) and isinstance(b, str):
            province = a
        elif isinstance(a, str) and isinstance(b, Province):
            province = b
        else:
            raise ValueError("Invalid vassal order format")
        referenced_player = None
        for player in self.board.players:
            if player.name == province.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{province.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError("A vassal_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.Vassal(referenced_player)

    def liege_order(self, a: Province | str, b: Province | str) -> tuple[Player, Player, order.Liege]:
        """Liege order, of the form Allegiance [Province] or [Province] Allegiance."""
        if isinstance(a, Province) and isinstance(b, str):
            province = a
        elif isinstance(a, str) and isinstance(b, Province):
            province = b
        else:
            raise ValueError("Invalid liege order format")
        referenced_player = None
        for player in self.board.players:
            if player.name == province.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{province.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError("A liege_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.Liege(referenced_player)

    def monarchy_order(self, a: Province | str, b: Province | str) -> tuple[Player, Player, order.DualMonarchy]:
        """Dual Monarchy order, of the form Monarchy [Province] or [Province] Monarchy."""
        if isinstance(a, Province) and isinstance(b, str):
            province = a
        elif isinstance(a, str) and isinstance(b, Province):
            province = b
        else:
            raise ValueError("Invalid dual monarchy order format")
        referenced_player = None
        for player in self.board.players:
            if player.name == province.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{province.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError("A dual_monarchy_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.DualMonarchy(referenced_player)

    def disown_order(self, a: Province | str, b: Province | str) -> tuple[Player, Player, order.Disown]:
        """Disown order, of the form Disown [Province] or [Province] Disown."""
        if isinstance(a, Province) and isinstance(b, str):
            province = a
        elif isinstance(a, str) and isinstance(b, Province):
            province = b
        else:
            raise ValueError("Invalid disown order format")
        referenced_player = None
        for player in self.board.players:
            if player.name == province.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{province.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError("A disown_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.Disown(referenced_player)

    def build(self, order_data: tuple[Province | Player, Player, order.Order]) -> Province | Player:
        """Handles winter builds orders, taking in a tuple of what was returned by the above."""
        target, player, player_order = order_data
        if self.player_restriction is not None and self.player_restriction != player:
            raise ValueError(f"Cannot issue order for {target.name} as you do not control it")
        if isinstance(player_order, order.Waive):
            player.waived_orders = player_order.quantity
        elif isinstance(player_order, order.PlayerOrder) and isinstance(target, Province):
            remove_player_order_for_province(self.board, player, target)
            player.build_orders.add(player_order)
        elif isinstance(player_order, order.RelationshipOrder) and isinstance(target, Player):
            remove_relationship_order(self.board, player_order, player)
            player.vassal_orders[target] = player_order
        else:
            raise ValueError("Invalid build order data")
        return target

    def defect_order(self, _) -> tuple[Player, Player, order.Defect]:
        """Defect order, which doesn't need any arguments."""
        if self.player_restriction is None or self.player_restriction.liege is None:
            raise ValueError("No liege to defect from!")
        return self.player_restriction.liege, self.player_restriction, order.Defect(self.player_restriction.liege)

    def non_build_order(self, _) -> None:
        """Handles when someone tries to issue a non-build order during builds."""
        raise ValueError("This type of order cannot be issued during build phases")

    # format for all of these is (province, order)
    def l_hold_order(self, province: Province, _) -> tuple[Province, order.Hold]:
        """Hold order, of the form [Province] Hold."""
        return province, order.Hold()

    def l_move_order(self, province: Province, _, destination: tuple[Province, str | None]) -> tuple[Province, order.Move]:
        """Move order, of the form [Province] Move [Destination]."""
        return province, order.Move(destination[0], destination[1])

    def move_order(self, unit: Unit, _, destination: tuple[Province, str | None]) -> tuple[Unit, order.Move]:
        """Move order, of the form [Unit] Move [Destination]."""
        return unit, order.Move(destination[0], destination[1])

    def convoy_order(self, unit: Unit, _, move: tuple[Province, order.Move]) -> tuple[Unit, order.ConvoyTransport]:
        """Convoy order, of the form [Unit] Convoy [Move]."""
        return unit, order.ConvoyTransport(move[0], move[1].destination)

    def support_order(self,
                      unit: Unit, _,
                      target: tuple[Province, order.Move | order.Hold] | Province) -> tuple[Unit, order.Support]:
        """Support order, of the form [Unit] Support [Province], [Unit] Support [Hold], or [Unit] Support [Move]."""
        if isinstance(target, Province):
            loc = target
            unit_order = order.Hold()
        else:
            loc = target[0]
            unit_order = target[1]

        if isinstance(unit_order, order.Move):
            return unit, order.Support(loc, unit_order.destination, unit_order.destination_coast)
        if isinstance(unit_order, order.Hold):
            return unit, order.Support(loc, loc)
        raise ValueError("Unknown type of support. Something has broken in the bot. Please report this")

    def retreat_order(self, unit: Unit, _, destination: tuple[Province, str | None]) -> tuple[Unit, order.RetreatMove]:
        """Retreat order, of the form [Unit] Retreat [Destination]."""
        return unit, order.RetreatMove(destination[0], destination[1])

    def disband_order(self, unit: Unit, _) -> tuple[Unit, order.RetreatDisband]:
        """Disband order, of the form [Unit] Disband."""
        return unit, order.RetreatDisband()

    def non_retreat_order(self, _) -> None:
        """Handles when someone tries to issue a non-retreat order during retreats."""
        raise ValueError("This type of order cannot be issued during retreat phases")

    def order(self, unit_order: tuple[Unit, order.UnitOrder]) -> Unit:
        """Processes orders done in Movement phases, taking in a tuple of what was returned by the above."""
        unit, movement_order = unit_order
        if self.player_restriction is not None and unit.player != self.player_restriction:
            if unit.player is None and movement_order is None:
                return unit
            raise PermissionError(
                f"{self.player_restriction.name} does not control the unit in {unit.province.name}, " +
                f"it belongs to {unit.player.name if unit.player else 'no one'}"
            )
        unit.order = movement_order
        return unit

    def retreat(self, unit_order: tuple[Unit, order.UnitOrder]) -> Unit:
        """Processes orders done in Retreat phases, taking in a tuple of what was returned by the above."""
        unit, retreat_order = unit_order
        if self.player_restriction is not None and unit.player != self.player_restriction:
            raise PermissionError(
                f"{self.player_restriction.name} does not control the unit in {unit.province.name}, " +
                f"it belongs to {unit.player.name if unit.player else 'no one'}"
            )
        unit.order = retreat_order
        return unit

generator = TreeToOrder()

with open("DiploGM/orders.ebnf", "r", encoding="utf-8") as f:
    ebnf = f.read()

movement_parser = Lark(ebnf, start="order", parser="earley")
retreats_parser = Lark(ebnf, start="retreat", parser="earley")
builds_parser   = Lark(ebnf, start="build", parser="earley")

def _check_for_warnings(unit: Unit) -> str | None:
    if isinstance(unit.order, (order.Move, order.RetreatMove)):
        if unit.order.destination not in unit.province.adjacency_data.adjacent:
            return "This move is not to an adjacent province. This will fail unless there is a convoy."
        if (unit.unit_type == UnitType.FLEET
            and unit.order.destination.get_multiple_coasts()
            and not unit.order.destination_coast):
            return "Destination province has multiple coasts. " + \
                   "This might cause your order to fail if the fleet can reach more than one."
    if isinstance(unit.order, order.Support):
        if unit.order.destination not in unit.province.adjacency_data.adjacent:
            return "This support is not to an adjacent province and will fail."
        if (unit.order.source != unit.order.destination
            and unit.order.destination not in unit.order.source.adjacency_data.adjacent):
            return "This support is is between two non-adjacent provinces, and will fail unless there is a convoy."
    return None

def parse_order(message: str, player_restriction: Player | None, board: Board) -> dict[str, ...]:
    """Parses the order commands, adds the orders as necessary, and returns a message of the results."""
    ordertext = message.split(maxsplit=1)
    if len(ordertext) == 1:
        return {
            "message": "For information about entering orders, please use the "
                       "[player guide](https://docs.google.com/document/d/1SNZgzDViPB-7M27dTF0SdmlVuu_KYlqqzX0FQ4tWc2M/"
                       "edit#heading=h.7u3tx93dufet) for examples and syntax.",
            "embed_colour": ERROR_COLOUR
        }
    orderlist = ordertext[1].strip().splitlines()
    movement = []
    orderoutput = []
    warnings = []
    errors = []
    if board.turn.is_moves():
        parser = movement_parser
    elif board.turn.is_retreats():
        parser = retreats_parser
    elif board.turn.is_builds():
        parser = builds_parser
    else:
        return {
            "message": "The game is in an unknown phase. "
                       "Something has gone very wrong with the bot. "
                       "Please report this to a gm",
            "embed_colour": ERROR_COLOUR,
        }

    generator.set_state(board, player_restriction)
    for current_order in orderlist:
        if not current_order.strip():
            continue
        try:
            logger.debug(current_order)
            cmd = parser.parse(current_order.strip().lower() + " ")
            ordered_unit: Unit = generator.transform(cmd)
            if board.turn.is_builds():
                orderoutput.append(f"\u001b[0;32m{current_order}")
            else:
                movement.append(ordered_unit)
                if (warning:= _check_for_warnings(ordered_unit)) is not None:
                    warnings.append(f"`{current_order}`: {warning}")
                    color = "\u001b[0;33m"
                else:
                    color = "\u001b[0;32m"
                if ordered_unit.player is None and player_restriction is not None:
                    if (dp_order := ordered_unit.dp_allocations.get(player_restriction.name)) is not None:
                        orderoutput.append(f"{color}DP {dp_order.points}: {ordered_unit} {dp_order.order}")
                    else:
                        orderoutput.append(f"{color}Removed DP bid for {ordered_unit}")
                else:
                    orderoutput.append(f"{color}{ordered_unit} {ordered_unit.order}")
        except VisitError as e:
            orderoutput.append(f"\u001b[0;31m{current_order}")
            errors.append(f"`{current_order}`: {str(e).splitlines()[-1]}")
        except (UnexpectedEOF, UnexpectedCharacters):
            orderoutput.append(f"\u001b[0;31m{current_order}")
            errors.append(f"`{current_order}`: Please fix this order and try again")

    database = get_connection()
    if board.turn.is_builds():
        database.save_build_orders_for_players(board, player_restriction)
    else:
        database.save_order_for_units(board, movement)

    if board.turn.is_builds() and player_restriction is not None:
        expected_builds = len(player_restriction.centers) - len(player_restriction.units)
        build_difference = player_restriction.get_number_of_builds() - expected_builds
        if (expected_builds < 0 and build_difference < 0) or (expected_builds > 0 and build_difference > 0):
            errors.append(f"You have inputted {abs(build_difference)} more " +
                          f"{'build' if expected_builds > 0 else 'disband'} " +
                          f"order{'' if abs(build_difference) == 1 else 's'} than necessary. " +
                          "Please use .remove_order to fix this.")

    paginator = Paginator(prefix="```ansi\n", suffix="```", max_size=4096)
    for line in orderoutput:
        paginator.add_line(line)

    output = paginator.pages
    if warnings:
        output[-1] += "\n**Warnings (Orders validated, but might fail):**\n" + "\n".join(warnings)
        output[-1] += "\n" if errors else ""
    if errors:
        output[-1] += "\n**Unable to validate the following orders:**\n" + "\n".join(errors)
        embed_colour = PARTIAL_ERROR_COLOUR if len(movement) > 0 else ERROR_COLOUR
        return {
            "messages": output,
            "embed_colour": embed_colour,
        }
    else:
        return {
                "title": "**Orders validated successfully.**",
                "messages": output,
        }

def parse_remove_order(message: str, player_restriction: Player | None, board: Board) -> dict[str, ...]:
    """Parses the .remove_order command and removes the specified orders."""
    invalid: list[tuple[str, Exception]] = []
    commands = message.splitlines()
    updated_units: set[Unit] = set()
    provinces_with_removed_builds: set[str] = set()
    for command in commands:
        if not command.strip():
            continue
        try:
            removed = _parse_remove_order(command, player_restriction, board)
            if isinstance(removed, Unit):
                updated_units.add(removed)
            elif isinstance(removed, str):
                provinces_with_removed_builds.add(removed)
        except Exception as error:
            invalid.append((command, error))

    database = get_connection()
    database.save_order_for_units(board, list(updated_units))
    for province in provinces_with_removed_builds:
        database.execute_arbitrary_sql(
            "DELETE FROM builds WHERE board_id=? and phase=? and location=?",
            (board.board_id, board.turn.get_indexed_name(), province),
        )

    if invalid:
        response = "The following order removals were invalid:"
        response_colour = ERROR_COLOUR
        for command in invalid:
            response += f"\n- {command[0]} - {command[1]}"
        if updated_units:
            response += "\nOrders for the following units were removed:"
            response_colour = PARTIAL_ERROR_COLOUR
            for unit in updated_units:
                response += f"\n- {unit.province}"
        return {"message": response, "embed_colour": response_colour}
    else:
        return {"message": "Orders removed successfully."}

def _parse_remove_order(command: str, player_restriction: Player | None, board: Board) -> Player | Unit | str:
    command = command.lower().strip()
    components = command.split(" ")
    if components[0] in ["a", "f", "army", "fleet"]:
        command = " ".join(components[1:])

    province, _ = board.get_province_and_coast(command)
    if command.startswith("relationship"):
        if player_restriction is None:
            raise RuntimeError("Relationship orders can only be removed in a player's orders channel")
        command = command.split(" ", 1)[1]
        target_player = None
        for player in board.players:
            if player.name.lower() == command.lower().strip() or player.get_name().lower() == command.lower().strip():
                target_player = player
        if target_player is None:
            raise RuntimeError(f"No such player: {command}")
        if target_player not in player_restriction.vassal_orders:
            raise RuntimeError(f"No relationship order with {target_player}")
        remove_relationship_order(board, player_restriction.vassal_orders[target_player], player_restriction)
        return target_player

    elif board.turn.is_builds():
        # remove build order
        player = province.owner
        if player is None or (player_restriction is not None and player != player_restriction):
            raise PermissionError(
                f"{player_restriction.name if player_restriction else 'Someone'} " +
                f"does not control the unit in {command} which belongs to {player.name if player else 'no one'}"
            )

        remove_player_order_for_province(board, player, province)

        return province.get_name()
    else:
        # remove unit's order
        # assert that the command user is authorized to order this unit
        unit = province.unit
        if (unit is not None
            and (player_restriction is None or unit.player == player_restriction)):
            unit.order = None
            return unit
        unit = province.dislodged_unit
        if (unit is not None
            and (player_restriction is None or unit.player == player_restriction)):
            unit.order = None
            return unit
        raise ValueError(f"You control neither a unit nor a dislodged unit in {province.name}")

def remove_player_order_for_province(board: Board, player: Player, province: Province) -> bool:
    """Removes a player order (build/disband/transform) for a province."""
    if province is None:
        return False
    for player_order in player.build_orders:
        if not isinstance(player_order, order.PlayerOrder):
            continue
        if player_order.province == province:
            player.build_orders.remove(player_order)
            database = get_connection()
            database.execute_arbitrary_sql(
                "DELETE FROM builds WHERE board_id=? and phase=? and location=?",
                (board.board_id, board.turn.get_indexed_name(), player_order.province.name),
            )
            return True
    return False

def remove_relationship_order(board: Board, old_order: order.RelationshipOrder, player: Player):
    """Removes a relationship order (vassal/liege/monarchy/disown) for a player."""
    if old_order.player in player.vassal_orders:
        del player.vassal_orders[old_order.player]
    database = get_connection()
    database.execute_arbitrary_sql(
        "DELETE FROM vassal_orders WHERE board_id=? and phase=? and player=? and target_player=?",
        (board.board_id, board.turn.get_indexed_name(), player.name, old_order.player.name)
    )
