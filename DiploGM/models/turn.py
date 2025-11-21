from __future__ import annotations

class Turn:
    def __init__(self, year: int = 1642, phase: str = "Spring Moves", start_year: int = 1642):
        self.phase_names = ["Spring Moves", "Spring Retreats", "Fall Moves", "Fall Retreats", "Winter Builds"]
        self.short_names = ["sm", "sr", "fm", "fr", "wa"]
        self.year = year
        self.phase = self.phase_names.index(phase) if phase in self.phase_names else 0
        self.start_year = start_year
    
    def __str__(self):
        return f"{str(self.year)} {self.phase_names[self.phase]}"
        
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
        if self.phase == len(self.phase_names) - 1:
            return Turn(self.year + 1, self.phase_names[0], self.start_year)
        return Turn(self.year, self.phase_names[self.phase + 1], self.start_year)
    
    def get_previous_turn(self):
        if self.phase == 0:
            return Turn(self.year - 1, self.phase_names[-1], self.start_year)
        return Turn(self.year, self.phase_names[self.phase - 1], self.start_year)

    def is_moves(self) -> bool:
        return "Moves" in self.phase_names[self.phase]
        
    def is_retreats(self) -> bool:
        return "Retreats" in self.phase_names[self.phase]
        
    def is_builds(self) -> bool:
        return "Builds" in self.phase_names[self.phase]
        
    def is_fall(self) -> bool:
        return "Fall" in self.phase_names[self.phase]