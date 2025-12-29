from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.adjudicator.adjudicator import Adjudicator

def make_adjudicator(board: Board) -> Adjudicator:
    if board.turn.is_moves():
        from DiploGM.adjudicator.moves_adjudicator import MovesAdjudicator
        return MovesAdjudicator(board)
    elif board.turn.is_retreats():
        from DiploGM.adjudicator.retreats_adjudicator import RetreatsAdjudicator
        return RetreatsAdjudicator(board)
    elif board.turn.is_builds():
        from DiploGM.adjudicator.builds_adjudicator import BuildsAdjudicator
        return BuildsAdjudicator(board)
    else:
        raise ValueError("Board is in invalid phase")