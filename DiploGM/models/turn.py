from __future__ import annotations
from enum import Enum

class PhaseName(Enum):
    SPRING_MOVES = 0
    SPRING_RETREATS = 1
    FALL_MOVES = 2
    FALL_RETREATS = 3
    WINTER_BUILDS = 4

class Turn:
    def __init__(self, year: int = 1642, phase: PhaseName = PhaseName.SPRING_MOVES, start_year: int = 1642):
        self.phase_names: dict[PhaseName, str] = {
            PhaseName.SPRING_MOVES: "Spring Moves",
            PhaseName.SPRING_RETREATS: "Spring Retreats",
            PhaseName.FALL_MOVES: "Fall Moves",
            PhaseName.FALL_RETREATS: "Fall Retreats",
            PhaseName.WINTER_BUILDS: "Winter Builds"
        }
        self.short_names: dict[PhaseName, str] = {
            PhaseName.SPRING_MOVES: "sm",
            PhaseName.SPRING_RETREATS: "sr",
            PhaseName.FALL_MOVES: "fm",
            PhaseName.FALL_RETREATS: "fr",
            PhaseName.WINTER_BUILDS: "wa"
        }
        self.year: int = year
        self.phase: PhaseName = phase if phase in PhaseName else PhaseName.SPRING_MOVES
        self.start_year: int = start_year
    
    def __str__(self):
        if self.year <= 0:
            year_str =  f"{str(1-self.year)} BCE"
        else:
            year_str = str(self.year)
        return f"{year_str} {self.phase_names[self.phase]}"

    def get_indexed_name(self) -> str:
        return f"{self.get_year_index()} {self.phase_names[self.phase]}"
    
    def get_short_name(self) -> str:
        return f"{str(self.year % 100)}{self.short_names[self.phase]}"
        
    def get_phase(self) -> str:
        return self.phase_names[self.phase]
    
    def get_short_phase(self) -> str:
        return self.short_names[self.phase]
    
    def get_year_index(self) -> int:
        return self.year - self.start_year
    
    def get_next_turn(self) -> Turn:
        if self.phase == PhaseName.WINTER_BUILDS:
            return Turn(self.year + 1, PhaseName.SPRING_MOVES, self.start_year)
        return Turn(self.year, PhaseName(self.phase.value + 1), self.start_year)
    
    def get_previous_turn(self):
        if self.phase == PhaseName.SPRING_MOVES:
            return Turn(self.year - 1, PhaseName.WINTER_BUILDS, self.start_year)
        return Turn(self.year, PhaseName(self.phase.value - 1), self.start_year)

    def is_moves(self) -> bool:
        return "Moves" in self.phase_names[self.phase]
        
    def is_retreats(self) -> bool:
        return "Retreats" in self.phase_names[self.phase]
        
    def is_builds(self) -> bool:
        return "Builds" in self.phase_names[self.phase]
        
    def is_fall(self) -> bool:
        return "Fall" in self.phase_names[self.phase]

    @staticmethod
    def turn_from_string(turn_str: str) -> Turn | None:
        split_index = turn_str.index(" ")
        year = int(turn_str[:split_index])
        phase_name = turn_str[split_index:].strip()
        current_turn = Turn(year)
        while current_turn.get_phase() != phase_name and current_turn.year == year:
            current_turn = current_turn.get_next_turn()
        if current_turn.year != year:
            return None
        return current_turn