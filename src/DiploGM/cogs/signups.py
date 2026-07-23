import enum
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from DiploGM.manager import Manager
from DiploGM.models.signup import PlayerSignup
from DiploGM.services.signups import signup_service
from DiploGM.utils import send_message_and_file

logger = logging.getLogger(__name__)
manager = Manager()

class Powers(enum.Enum):
    ABYSSINIA = "Abyssinia"
    AJUURAAN = "Ajuuraan"
    ATHAPASCA = "Athapasca"
    AUSTRIA = "Austria"
    AYMARA = "Aymara"
    AYUTTHAYA = "Ayutthaya"
    ENGLAND = "England"
    FRANCE = "France"
    GUARANI = "Guarani"
    INUIT = "Inuit"
    KONGO = "Kongo"
    MAPUCHE = "Mapuche"
    MING = "Ming"
    MUGHAL = "Mughal"
    NETHERLANDS = "Netherlands"
    OTTOMAN = "Ottoman"
    POLAND = "Poland-Lithuania"
    PORTUGAL = "Portugal"
    QING = "Qing"
    RUSSIA = "Russia"
    SAFAVID = "Safavid"
    SPAIN = "Spain"
    SWEDEN = "Sweden"
    TOKUGAWA = "Tokugawa"
    UTE = "Ute-Shoshone"


class SignupsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = signup_service

    @commands.group()
    async def signups(self, ctx: commands.Context):
        if ctx.invoked_subcommand is not None:
            return

        wave = self.service.data['metadata']['wave']
        message = (
            f"Wave: {wave}\n"
            f"Accepting: {self.service.data['metadata']['accepting_responses']}\n"
            f"Count: {len(self.service.data[wave])}\n"
        )
        await send_message_and_file(channel=ctx.channel, message=message)

    @signups.command()
    async def open(self, ctx: commands.Context):
        self.service.open_wave()
        await send_message_and_file(channel=ctx.channel, message="Accepting Responses")

    @signups.command()
    async def close(self, ctx: commands.Context):
        self.service.close_wave()
        await send_message_and_file(channel=ctx.channel, message="No longer accepting Responses")

    @signups.command()
    async def create(self, ctx: commands.Context, name: str):
        self.service.define_wave(name)
        await send_message_and_file(channel=ctx.channel, message=f"Started new set of allocations, labelled: '{name}'")

    @signups.command()
    async def delete(self, ctx: commands.Context, name: str):
        self.service.clear_wave(name)
        await send_message_and_file(channel=ctx.channel, message=f"Removed set of allocations, labelled: '{name}'")

    @signups.command()
    async def remove(self, ctx: commands.Context, name: str):
        self.service.delete_signup(name)
        await send_message_and_file(channel=ctx.channel, message=f"Removed signup for user: '{name}'")

    @signups.command()
    async def export(self, ctx: commands.Context):
        wave = self.service.data["metadata"]["wave"]
        wave_signups = self.service.data[wave]

        title = f"Signups for Wave: '{wave}'"
        message = json.dumps(wave_signups, indent=4)
        await send_message_and_file(channel=ctx.channel, title=title, message=message)

    @app_commands.command(
        name="signup",
        description="Signup to a game of Imperial Diplomacy!",
        extras={}
    )
    async def signup(self, interaction: discord.Interaction, 
         scrapper: bool = False, 
         first: Powers | None = None, 
         second: Powers | None = None,
         third: Powers | None = None,
         fourth: Powers | None = None,
         fifth: Powers | None = None
    ):
        signup = PlayerSignup(
            scrapper,
            str(first),
            str(second),
            str(third),
            str(fourth),
            str(fifth)
        )
        signup_service.record_signup(interaction.user.name, signup)

async def setup(bot):
    cog = SignupsCog(bot)
    await bot.add_cog(cog)
