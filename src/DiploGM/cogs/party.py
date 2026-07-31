import logging
import random

from typing import List, Dict
from itertools import permutations

import discord
from discord.ext.commands import Bot
from discord.ext import commands

from DiploGM.manager import Manager
from DiploGM import perms
from DiploGM.config import is_bumble, temporary_bumbles, HUB_SERVER_ID
from DiploGM.utils import log_command, send_message_and_file
from DiploGM.utils.sanitise import remove_prefix
from DiploGM.utils.send_message import ErrorMessage, send_error

logger = logging.getLogger(__name__)
manager = Manager()

ping_text_choices = [
    "proudly states",
    "fervently believes in the power of",
    "is being mind controlled by",
]

# Fetch the 115 philosophical advice points created by Hobbit for the World of Chaos event
# Intended use: to extend the possibilities within .advice
WOC_ADVICE = ["Maybe the real friends were the dots we claimed along the way."]
try:
    with open("assets/advice.txt", "r", encoding="utf-8") as f:
        WOC_ADVICE.extend(f.readlines())
except FileNotFoundError:
    pass


class PartyCog(commands.Cog):
    """A Cog for fun, non-consequential commands

    Args:
        bot (DiploGM): A reference to the running discord bot instance

    Attributes:
        bot (DiploGM): A reference to the running discord bot instance
        eolhc_ed_members (Dict[int, List[int]]): A set describing which members have used eolhc in different guilds
    """

    def __init__(self, bot):
        self.bot: Bot = bot
        self.eolhc_ed_members: Dict[int, List[int]] = dict()

    @commands.command(hidden=True)
    @perms.gm_only("botsay")
    async def botsay(self, ctx: commands.Context) -> None:
        """Have the bot output a specific message within a channel

        Usage:
            Used as `.botsay #channel message`

        Note:
            Limited to the server of command invocation

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
                No channel given
                No message given
        """
        # noinspection PyTypeChecker
        if len(ctx.message.channel_mentions) == 0:
            await send_error(ctx.channel, ErrorMessage.CHANNEL_NOT_GIVEN)
            return
        channel = ctx.message.channel_mentions[0]
        if not isinstance(channel, discord.abc.Messageable):
            await send_error(ctx.channel, ErrorMessage.NOT_MESSAGEABLE)
            return
        content = remove_prefix(ctx)
        content = content.replace(channel.mention, "").strip()
        if len(content) == 0:
            await send_error(ctx.channel, ErrorMessage.MESSAGE_NOT_GIVEN)
            return

        message = await send_message_and_file(channel=channel, message=content)
        log_command(logger, ctx, f"Sent Message into #{channel.name}")
        await send_message_and_file(
            channel=ctx.channel,
            title="Sent Message",
            message=message.jump_url,
        )

    @commands.command(help="Checks bot listens and responds.")
    async def ping(self, ctx: commands.Context):
        """A method to check bot activity

        Usage:
            Used as `.ping`

        Notes:
            1 in 10 chance for joke behaviour

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None:
            Messages:
                Beep Boop
                Joke Behaviour

        Raises:
            None:
            Messages:
        """
        response = "Beep Boop"
        if random.random() < 0.1:
            author = ctx.message.author
            assert isinstance(author, discord.Member)
            content = remove_prefix(ctx)
            if content == "":
                content = " nothing"
            name = author.nick
            if not name:
                name = author.name
            response = name + " " + random.choice(ping_text_choices) + content
        await send_message_and_file(channel=ctx.channel, title=response)

    @commands.command(hidden=True)
    async def bumble(self, ctx: commands.Context) -> None:
        """Output a scrambled form of our saviour, Bumble

        Usage:
            Used as `.bumble`

        Note:
            User bumble always is "bumble"
            If scrambled output is "bumble", temporarily flag user as a bumble
            If scrambled output is "elbmub", output reverse message

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        list_of_bumble = list("bumble")
        random.shuffle(list_of_bumble)
        word_of_bumble = "".join(list_of_bumble)

        if is_bumble(ctx.author.name) and random.randrange(0, 10) == 0:
            word_of_bumble = "bumble"

        if word_of_bumble == "bumble":
            word_of_bumble = "You are the chosen bumble"

            if ctx.author.name not in temporary_bumbles:
                # no keeping temporary bumbleship easily
                temporary_bumbles.add(ctx.author.name)
        if word_of_bumble == "elbmub":
            word_of_bumble = "elbmub nesohc eht era uoY"

        await send_message_and_file(channel=ctx.channel, title=word_of_bumble)

    @commands.command(hidden=True)
    async def pelican(self, ctx: commands.Context) -> None:
        """A pelican is chasing you! Output a fun message

        Usage:
            Used as `.pelican`

        Note:
            Places a pelican can chase are weighted priority

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        pelican_places = {
            "your home": 15,
            "a kebab store": 12,
            "a jungle": 10,
            "a cursed IKEA": 10,
            "a supermarket": 9,
            "Formosa": 8,
            "the Vatican at night": 7,
            "your dreams": 5,
            "a german bureaucracy office": 5,
            "a karaoke bar in Tokyo": 5,
            "a quantum physics lecture": 4,
            "your own mind": 3,
            "Area 51": 2,
            "the Teletubbies’ homeland": 0.9,
            "Summoners’ Rift": 0.1,
        }
        chosen_place = random.choices(
            list(pelican_places.keys()), weights=list(pelican_places.values()), k=1
        )[0]
        message = f"A pelican is chasing you through {chosen_place}!"
        await send_message_and_file(channel=ctx.channel, title=message)

    @commands.command(hidden=True)
    async def cheat(self, ctx: commands.Context) -> None:
        """Are you cheating? Output a fun message

        Usage:
            Used as `.cheat`

        Note:
            Default: "Cheating is disabled for this user."
            If a user is bumbled: Replace with a silly cheating message

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        assert ctx.guild is not None
        message = "Cheating is disabled for this user."
        author = ctx.message.author.name
        board = manager.get_board(ctx.guild.id)
        if is_bumble(author):
            sample = random.choice(
                [
                    f"It looks like {author} is getting coalitioned this turn :cry:",
                    f"{author} is talking about stabbing {random.choice(list(board.get_players())).name} again",
                    f"looks like he's throwing to {author}... shame",
                    "yeah",
                    "People in this game are not voiding enough",
                    f"I can't believe {author} is moving to {random.choice(list(board.provinces)).name}",
                    f"{author} has a bunch of invalid orders",
                    f"No one noticed that {author} overbuilt?",
                    f"{random.choice(list(board.get_players())).name} is in a perfect position to stab {author}",
                    ".bumble",
                ]
            )
            message = f'Here\'s a helpful message I stole from the spectator chat: \n"{sample}"'
        await send_message_and_file(channel=ctx.channel, title=message)

    @commands.command(hidden=True)
    async def advice(self, ctx: commands.Context) -> None:
        """Output some advice to the user

        Usage:
            Used as `.advice`

        Note:
            Default: "You are not worthy of advice"
            If user is bumbled:
            If random == 0: Pre-written joke advice
            If random == 1: World of Chaos, Hobbit's 115 statements

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        message = "You are not worthy of advice."
        chance = random.randrange(0, 5)

        if is_bumble(ctx.author.name):
            message = "Bumble suggests that you go fishing, although typically blasphemous, today is your lucky day!"
        elif chance == 0:
            message = random.choice(
                [
                    "Bumble was surprised you asked him for advice and wasn't ready to give you any, maybe if you were a true follower...",
                    "Icecream demands that you void more and will not be giving any advice until sated.",
                    "Salt suggests that stabbing all of your neighbors is a good play in this particular situation.",
                    "Ezio points you to an ancient proverb: see dot take dot.",
                    "CaptainMeme advises balance of power play at this instance.",
                    "Ash Lael deems you a sufficiently apt liar, go use those skills!",
                    "Kwiksand suggests winning.",
                    "Ambrosius advises taking the opportunity you've been considering, for more will ensue.",
                    "Flare recommends to change the map to your benefit in the next wave.",
                    "notnot suggests drawing some arrows on a map and seeing if that helps",
                    "Aeolus wonders if you shouldn't delay your orders until the last minute.",
                    "Tot suggests arguing with your duo partner.",
                    "June wants to know if you've tried being nice <3",
                    "Firebender wants you to know you were just unlucky with the start of this game, you'll do better next time.",
                    "The GMs suggest you input your orders so they don't need to hound you for them at the deadline.",
                ]
            )
        elif chance == 1:
            index = random.randrange(0, len(WOC_ADVICE))
            message = f"{index}. {WOC_ADVICE[index]}"

        await send_message_and_file(channel=ctx.channel, title=message)

    @commands.command(hidden=True)
    async def shutdown(self, ctx: commands.Context):
        """Please don't shut me down :? , Output a fun message

        Usage:
            Used as `.shutdown`

        Note:
            Default: "You are not worthy of advice"
            If user is superuser:

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        if perms.is_superuser(ctx.author):
            await send_message_and_file(
                channel=ctx.channel, title="Please don't shut me down", message=""
            )
        else:
            await send_message_and_file(
                channel=ctx.channel,
                title="Why would you want to do this to me?",
                message="",
            )

    # feel free to add cute animal gifs
    eolhc_gifs = [
        "https://tenor.com/view/otter-cookie-svenja-gif-26360393",
        "https://tenor.com/view/otter-gif-24469293",
        "https://tenor.com/view/biting-smartphone-otter-bite-phone-animalsdoingthings-gif-16767408",
        "https://tenor.com/view/oh-no-you-didnt-otter-get-otter-here-too-cute-funny-animals-gif-8905253",
    ]

    @commands.command(hidden=True)
    async def eolhc(
        self,
        ctx: commands.Context,
    ):
        """Did my name always look like that? Reverses the nickname

        Usage:
            Used as `.eolhc`

        Note:
            Not for Chaos games

        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
                Pesky Admin, no permissions to modify nickname
        """

        assert ctx.guild is not None
        if ctx.author.id == 1352388421003251833:
            if (
                ctx.guild.id != HUB_SERVER_ID
                and perms.is_gm(ctx.author)
                and (
                    ctx.guild.id not in self.eolhc_ed_members
                    or ctx.me.id not in self.eolhc_ed_members[ctx.guild.id]
                )
            ):
                self.eolhc_ed_members.setdefault(ctx.guild.id, []).append(ctx.me.id)
                await ctx.reply("*incoherent screaming*"[::-1])
                if isinstance(ctx.me, discord.Member):
                    await ctx.me.edit(nick=ctx.me.display_name[::-1])
            else:
                await ctx.reply(random.choice(self.eolhc_gifs))
            return
        if manager.get_board(ctx.guild.id).is_chaos():
            return

        try:
            if isinstance(ctx.author, discord.Member):
                await ctx.author.edit(nick=ctx.author.display_name[::-1])
        except discord.Forbidden:
            await ctx.reply("Pesky Admin")

    eolhc_permutations = list(map(lambda x: "".join(x), permutations("eolhc")))
    eolhc_permutations.remove("eolhc")
    eolhc_permutations.remove("eohlc")

    @commands.command(hidden=True, aliases=eolhc_permutations)
    async def eohlc(self, ctx: commands.Context):
        """How could you do that?

        Usage:
            *Used as `.eohlc`
            All incorrect permutations of eolhc

        Note:
        Args:
            ctx (commands.Context): Context from discord regarding command invocation

        Returns:
            None

        Raises:
            None:
            Messages:
        """

        if ctx.author.id == 285108244714881024 and isinstance(
            ctx.author, discord.Member
        ):  # aahoughton
            try:
                await ctx.reply("*eolhc")
                await ctx.author.edit(nick="aahuoghton")
            except discord.Forbidden:
                await ctx.reply("Very Pesky Admin")
        else:
            await ctx.reply("*eolhc")


async def setup(bot):
    cog = PartyCog(bot)
    await bot.add_cog(cog)
