import logging

from discord.ext.commands import Paginator
from lark import Lark, Transformer, UnexpectedEOF, UnexpectedCharacters
from lark.exceptions import VisitError

from DiploGM.config import ERROR_COLOUR, PARTIAL_ERROR_COLOUR
from DiploGM.utils import get_unit_type, _manage_coast_signature
from DiploGM.models import turn
from DiploGM.models import order
from DiploGM.models.board import Board
from DiploGM.db.database import get_connection
from DiploGM.models.player import Player
from DiploGM.models.province import Province
from DiploGM.models.unit import Unit, UnitType

logger = logging.getLogger(__name__)

class TreeToOrder(Transformer):
    def set_state(self, board: Board, player_restriction: Player | None):
        self.board = board
        self.flags = board.data.get("adju flags", [])
        self.player_restriction = player_restriction
        
    def province(self, s) -> tuple[Province, str | None]:
        name = " ".join(s[::2]).replace("_", " ").strip()
        name = _manage_coast_signature(name)
        return self.board.get_province_and_coast(name)

    # used for supports, specifically FoW
    def l_unit(self, s) -> Province:
        # ignore the fleet/army signifier, if exists
        loc = s[-1][0]
        if loc is not None and not self.board.fow:
            unit = loc.unit
            if unit is None:
                raise ValueError(f"No unit in {s[-1][0]}")

        return loc

    def unit(self, s) -> Unit:
        # ignore the fleet/army signifier, if exists
        unit = s[-1][0].unit
        if unit is None:
            raise ValueError(f"No unit in {s[-1][0]}")

        return unit

    def retreat_unit(self, s) -> Unit:
        # ignore the fleet/army signifier, if exists
        unit = s[-1][0].dislodged_unit
        if unit is None:
            raise ValueError(f"No dislodged unit in {s[-1]}")

        return unit

    def hold_order(self, s) -> tuple[Unit, order.Hold]:
        return s[0], order.Hold()

    def core_order(self, s) -> tuple[Province, order.Core]:
        if "no coring" in self.flags:
            raise Exception("Coring is disabled in this gamemode")
        return s[0], order.Core()
    
    def build_unit(self, s) -> tuple[Province, Player, order.Build]:
        if isinstance(s[2], tuple):
            province, coast = s[2]
            unit_type = s[3]
        else:
            province, coast = s[3]
            unit_type = s[2]

        unit_type = get_unit_type(unit_type)

        if not province.has_supply_center:
                raise ValueError(f"{province} does not have a supply center.")  
        elif self.player_restriction:
            if province.owner != self.player_restriction:
                raise ValueError(f"You do not own {province}.")
            if province.core != self.player_restriction and not "build anywhere" in self.board.data.get("adju flags", []):
                raise ValueError(f"You haven't cored {province}.")

        return province, province.owner, order.Build(province, unit_type, coast)
    
    def disband_unit(self, s) -> tuple[Province, Player, order.Disband]:
        if isinstance(s[0], Unit):
            u = s[0]
        else:
            u = s[2]
        return u.province, u.player, order.Disband(u.province)
    
    def waive_order(self, s) -> tuple[None, Player, order.Waive]:
        if self.player_restriction is None:
            raise ValueError(f"Please order waives in the appropriate player's orders channel.")
        return None, self.player_restriction, order.Waive(int(s[2]))
        
    def vassal_order(self, s) -> tuple[Player, Player, order.Vassal]:
        if isinstance(s[0], Province):
            l = s[0]
        else:
            l = s[2]
        referenced_player = None
        for player in self.board.players:
            if player.name == l.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{l.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError(f"A vassal_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.Vassal(referenced_player)

    def liege_order(self, s) -> tuple[Player, Player, order.Liege]:
        if isinstance(s[0], Province):
            l = s[0]
        else:
            l = s[2]
        referenced_player = None
        for player in self.board.players:
            if player.name == l.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{l.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError(f"A vassal_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.Liege(referenced_player)

    def monarchy_order(self, s) -> tuple[Player, Player, order.DualMonarchy]:
        if isinstance(s[0], Province):
            l = s[0]
        else:
            l = s[2]
        referenced_player = None
        for player in self.board.players:
            if player.name == l.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{l.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError(f"A vassal_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.DualMonarchy(referenced_player)

    def disown_order(self, s) -> tuple[Player, Player, order.Disown]:
        if isinstance(s[0], Province):
            l = s[0]
        else:
            l = s[2]
        referenced_player = None
        for player in self.board.players:
            if player.name == l.name:
                referenced_player = player
        if referenced_player is None:
            raise ValueError(f"{l.name} doesn't match the name of any player")
        if self.player_restriction is None:
            raise ValueError(f"A vassal_order currently must be made in a orders channel due to ambiguity")
        return referenced_player, self.player_restriction, order.Disown(referenced_player)

    def build(self, s):
        build_order = s[0]
        if self.player_restriction is not None and self.player_restriction != build_order[1]:
            raise Exception(f"Cannot issue order for {build_order[0].name} as you do not control it")
        if isinstance(build_order[2], order.Waive):
            build_order[1].waived_orders = build_order[2].quantity
        elif isinstance(build_order[2], order.PlayerOrder):
            remove_player_order_for_province(self.board, build_order[1], build_order[0])
            build_order[1].build_orders.add(build_order[2])
        else:
            remove_relationship_order(self.board, build_order[2], build_order[1])
            build_order[1].vassal_orders[build_order[0]] = build_order[2]
        return build_order[0]

    def defect_order(self, s):
        if not self.player_restriction or self.player_restriction.liege:
            raise Exception("No liege to defect from!")
        return self.player_restriction.liege, self.player_restriction, order.Defect(self.player_restriction.liege)

    def non_build_order(self, s):
        raise Exception("This type of order cannot be issued during build phases")

    # format for all of these is (unit, order)
    def l_hold_order(self, s) -> tuple[Unit, order.Hold]:
        return s[0], order.Hold()
    
    def l_move_order(self, s) -> tuple[Unit, order.Move]:
        return s[0], order.Move(s[-1][0], s[-1][1])

    def move_order(self, s) -> tuple[Unit, order.Move]:
        return s[0], order.Move(s[-1][0], s[-1][1])

    def convoy_order(self, s) -> tuple[Unit, order.ConvoyTransport]:
        return s[0], order.ConvoyTransport(s[-1][0], s[-1][1].destination)

    def support_order(self, s) -> tuple[Unit, order.Support]:
        if isinstance(s[-1], Province):
            loc = s[-1]
            unit_order = order.Hold()
        else:
            loc = s[-1][0]
            unit_order = s[-1][1]

        if isinstance(unit_order, order.Move):
            return s[0], order.Support(loc, unit_order.destination, unit_order.destination_coast)
        elif isinstance(unit_order, order.Hold):
            return s[0], order.Support(loc, loc)
        else:
            raise ValueError("Unknown type of support. Something has broken in the bot. Please report this")

    def retreat_order(self, s) -> tuple[Unit, order.RetreatMove]:
        return s[0], order.RetreatMove(s[-1][0], s[-1][1])

    def disband_order(self, s) -> tuple[Unit, order.RetreatDisband]:
        return s[0], order.RetreatDisband()

    def non_retreat_order(self, s):
        raise Exception("This type of order cannot be issued during retreat phases")
        
    def order(self, order) -> Unit:
        command = order[0]
        unit, order = command
        if self.player_restriction is not None and unit.player != self.player_restriction:
            raise PermissionError(
                f"{self.player_restriction.name} does not control the unit in {unit.province.name}, it belongs to {unit.player.name}"
            )
        unit.order = order
        return unit

    def retreat(self, order) -> Unit:
        command = order[0]
        unit, order = command
        if self.player_restriction is not None and unit.player != self.player_restriction:
            raise PermissionError(
                f"{self.player_restriction.name} does not control the unit in {unit.province.name}, it belongs to {unit.player.name}"
            )
        unit.order = order
        return unit


generator = TreeToOrder()


with open("DiploGM/orders.ebnf", "r") as f:
    ebnf = f.read()

movement_parser = Lark(ebnf, start="order", parser="earley")
retreats_parser = Lark(ebnf, start="retreat", parser="earley")
builds_parser   = Lark(ebnf, start="build", parser="earley")

def parse_order(message: str, player_restriction: Player | None, board: Board) -> dict[str, ...]:
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
    errors = []
    if board.turn.is_builds():
        generator.set_state(board, player_restriction)
        for order in orderlist:
            if not order.strip():
                continue
            try:
                cmd = builds_parser.parse(order.strip().lower() + " ")
                generator.transform(cmd)
                orderoutput.append(f"\u001b[0;32m{order}")
            except VisitError as e:
                orderoutput.append(f"\u001b[0;31m{order}")
                errors.append(f"`{order}`: {str(e).splitlines()[-1]}")
            except UnexpectedEOF as e:
                orderoutput.append(f"\u001b[0;31m{order}")
                errors.append(f"`{order}`: Please fix this order and try again")
            except UnexpectedCharacters as e:
                orderoutput.append(f"\u001b[0;31m{order}")
                errors.append(f"`{order}`: Please fix this order and try again")
        database = get_connection()
        database.save_build_orders_for_players(board, player_restriction)
    elif board.turn.is_moves() or board.turn.is_retreats():
        if board.turn.is_moves():
            parser = movement_parser
        else:
            parser = retreats_parser

        generator.set_state(board, player_restriction)
        for order in orderlist:
            if not order.strip():
                continue
            try:
                logger.debug(order)
                cmd = parser.parse(order.strip().lower() + " ")
                ordered_unit = generator.transform(cmd)
                movement.append(ordered_unit)
                orderoutput.append(f"\u001b[0;32m{ordered_unit} {ordered_unit.order}")
            except VisitError as e:
                orderoutput.append(f"\u001b[0;31m{order}")
                errors.append(f"`{order}`: {str(e).splitlines()[-1]}")
                errors.append(f"`{order}`: {str(e)}")
            except UnexpectedEOF as e:
                orderoutput.append(f"\u001b[0;31m{order}")
                errors.append(f"`{order}`: Please fix this order and try again")
            except UnexpectedCharacters as e:
                orderoutput.append(f"\u001b[0;31m{order}")
                errors.append(f"`{order}`: Please fix this order and try again")
        database = get_connection()
        database.save_order_for_units(board, movement)
    else:
        return {
            "message": "The game is in an unknown phase. "
                       "Something has gone very wrong with the bot. "
                       "Please report this to a gm",
            "embed_colour": ERROR_COLOUR,
        }
        

    paginator = Paginator(prefix="```ansi\n", suffix="```", max_size=4096)
    for line in orderoutput:
        paginator.add_line(line)

    output = paginator.pages
    if errors:
        output[-1] += "\n" + "\n".join(errors)
        if len(movement) > 0:
            embed_colour = PARTIAL_ERROR_COLOUR
        else:
            embed_colour = ERROR_COLOUR
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
            else:
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


def _parse_remove_order(command: str, player_restriction: Player, board: Board) -> Unit | str:
    command = command.lower().strip()
    province, coast = board.get_province_and_coast(command)
    if command.startswith("relationship"):
        command = command.split(" ", 1)[1]
        target_player = None
        for player in board.players:
            if player.name.lower() == command.lower().strip():
                target_player = player
        if target_player == None:
            raise RuntimeError(f"No such player: {command}")
        if not target_player in player_restriction.vassal_orders:
            raise RuntimeError(f"No relationship order with {target_player}")
        remove_relationship_order(board, player_restriction.vassal_orders[target_player], player_restriction)


    elif board.turn.is_builds():
        # remove build order
        player = province.owner
        if player_restriction is not None and player != player_restriction:
            raise PermissionError(
                f"{player_restriction.name} does not control the unit in {command} which belongs to {player.name}"
            )

        remove_player_order_for_province(board, player, province)

        return province.get_name(coast)
    else:
        # remove unit's order
        # assert that the command user is authorized to order this unit
        unit = province.unit
        if unit is not None:
            player = unit.player
            if player_restriction is None or player == player_restriction:
                unit.order = None
                return unit
        unit = province.dislodged_unit
        if unit is not None:
            player = unit.player
            if player_restriction is None or player == player_restriction:
                unit.order = None
                return unit
        raise Exception(f"You control neither a unit nor a dislodged unit in {province.name}")


def remove_player_order_for_province(board: Board, player: Player, province: Province) -> bool:
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

def remove_relationship_order(board: Board, order: order.RelationshipOrder, player: Player):
    if order.player in player.vassal_orders:
        del player.vassal_orders[order.player]
    database = get_connection()
    database.execute_arbitrary_sql(
        "DELETE FROM vassal_orders WHERE board_id=? and phase=? and player=? and target_player=?",
        (board.board_id, board.turn.get_indexed_name(), player.name, order.player.name)
    )
