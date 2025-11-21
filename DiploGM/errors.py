from discord.ext import commands

class CommandPermissionError(commands.CheckFailure):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


