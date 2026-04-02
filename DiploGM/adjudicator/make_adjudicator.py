"""Factory function for creating an adjudicator for the current phase."""
from __future__ import annotations
from typing import TYPE_CHECKING

from DiploGM.adjudicator.builds_adjudicator import BuildsAdjudicator
from DiploGM.adjudicator.moves_adjudicator import MovesAdjudicator
from DiploGM.adjudicator.retreats_adjudicator import RetreatsAdjudicator

if TYPE_CHECKING:
    from DiploGM.models.board import Board
    from DiploGM.adjudicator.adjudicator import Adjudicator

def make_adjudicator(board: Board) -> Adjudicator:
    """Factory function for creating an adjudicator for the current phase."""
    if board.turn.is_moves():
        return MovesAdjudicator(board)
    if board.turn.is_retreats():
        return RetreatsAdjudicator(board)
    if board.turn.is_builds():
        return BuildsAdjudicator(board)
    else:
        raise ValueError("Board is in invalid phase")
