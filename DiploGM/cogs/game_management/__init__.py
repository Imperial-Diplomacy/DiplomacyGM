from .game_management import GameManagementCog


async def setup(bot):
    cog = GameManagementCog(bot)
    await bot.add_cog(cog)
