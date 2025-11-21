import os

os.environ["simultaneous_svg_exports_limit"] = "1"

from DiploGM.manager import Manager
from DiploGM.adjudicator.mapper import Mapper

manager = Manager()

try:
    manager.total_delete(0)
except KeyError:
    pass

game_type = "impdipfow.json"

manager.create_game(0, game_type)

board = manager.get_board(0)
board.fow = False
mapper = Mapper(board)

# miwok = board.name_to_province["miwok"].coast()
# import pdb
# pdb.set_trace()
# x = miwok.get_adjacent_coasts()
# print(x)