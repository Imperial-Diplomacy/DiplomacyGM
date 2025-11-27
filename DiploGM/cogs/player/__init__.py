from .player_cog import PlayerCog


async def setup(bot):
    cog = PlayerCog(bot)
    await bot.add_cog(cog)