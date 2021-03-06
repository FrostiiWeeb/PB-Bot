import discord
import random
import asyncio
import time
import humanize
import datetime

from discord.ext import commands

from utils import utils
from utils.classes import CustomContext


class Fun(commands.Cog):
    """
    Fun commands.
    """
    @commands.command()
    async def coinflip(self, ctx: CustomContext):
        """
        Returns heads, tails or ???.
        """
        result = random.choices(population=["heads", "tails", "side"], weights=[0.45, 0.45, 0.01], k=1)[0]
        if result == "side":
            return await ctx.send("You flipped a coin and it landed on it's `side`!")
        await ctx.send(f"You flipped a coin and got `{result}`!")

    @commands.command()
    async def reddit(self, ctx: CustomContext, *, subreddit: str):
        """
        Gets a random post from a subreddit.

        `subreddit` - The subreddit.
        """
        async with ctx.bot.session.get(f"https://www.reddit.com/r/{subreddit}/new.json") as resp:
            r = await resp.json()
        if r.get("error", None) is not None:
            return await ctx.send("Couldn't find a subreddit with that name.")

        posts = r["data"]["children"]
        if not posts:
            return await ctx.send("Apparently there are no posts in this subreddit...")
        random_post = random.choice(posts)["data"]
        posted_when = datetime.datetime.now() - datetime.datetime.fromtimestamp(random_post["created"])

        embed = discord.Embed(
            title=random_post["title"], url=random_post["url"],
            description=f"Posted by `u/{random_post['author']}` {humanize.naturaldelta(posted_when)} ago\n"
            f"{ctx.bot.emoji_dict['upvote']} {random_post['ups']} {ctx.bot.emoji_dict['downvote']} {random_post['downs']}",
            colour=ctx.bot.embed_colour)
        embed.set_author(name=random_post["subreddit_name_prefixed"])
        embed.set_image(url=random_post["url"])
        embed.set_footer(text=f"{random_post['num_comments']} comment{'' if random_post['num_comments'] == 1 else 's'} • {random_post['upvote_ratio'] * 100}% upvote ratio")

        if random_post["over_18"]:
            cembed = discord.Embed(
                title="This post has been marked as nsfw. Are you sure that you want to view it?",
                description="If you agree, it will be sent to your dms.", colour=ctx.bot.embed_colour)
            confirm = await utils.EmbedConfirm(cembed).prompt(ctx)
            if confirm:
                await ctx.author.send(embed=embed)
            return
        await ctx.send(embed=embed)

    @commands.max_concurrency(1, per=commands.BucketType.channel)
    @commands.command(aliases=["c"])
    async def cookie(self, ctx: CustomContext):
        """
        Yum yum.
        """
        cookies = ["🍪", "🥠"]
        reaction = random.choices(cookies, weights=[0.9, 0.1], k=1)[0]
        embed = discord.Embed(description=f"First one to eat the {reaction} wins!", colour=ctx.bot.embed_colour)
        message = await ctx.send(embed=embed)
        await asyncio.sleep(4)
        for i in reversed(range(1, 4)):
            await message.edit(embed=discord.Embed(description=str(i), colour=ctx.bot.embed_colour))
            await asyncio.sleep(1)
        await asyncio.sleep(random.randint(0, 3))  # for extra challenge :)
        await message.edit(embed=discord.Embed(description="Eat the cookie!", colour=ctx.bot.embed_colour))
        await message.add_reaction(reaction)
        start = time.perf_counter()
        try:
            _, user = await ctx.bot.wait_for(
                "reaction_add",
                check=lambda _reaction, user: _reaction.message.guild == ctx.guild
                and _reaction.message.channel == ctx.message.channel
                and _reaction.message == message and str(_reaction.emoji) == reaction and user != ctx.bot.user
                and not user.bot,
                timeout=60)
        except asyncio.TimeoutError:
            return await message.edit(embed=discord.Embed(
                description="No one ate the cookie...",
                colour=ctx.bot.embed_colour))
        end = time.perf_counter()
        await message.edit(embed=discord.Embed(
            description=f"**{user}** ate the cookie in `{end - start:.3f}` seconds!",
            colour=ctx.bot.embed_colour))

    @commands.command(aliases=["ttt", "tic-tac-toe"])
    async def tictactoe(self, ctx: CustomContext, *, player2: discord.Member):
        """
        Challenge someone to a game of tic-tac-toe!

        **How to Play**
        Each reaction corresponds to a place on the board:
        ↖️⬆️↗️
        ⬅️⏺️➡️
        ↙️⬇️↘️

        Simply click on a reaction to make your move.

        `player2` - The user to challenge.
        """
        if player2 == ctx.author:
            return await ctx.send(f"You can't challenge yourself {ctx.author.mention}.")
        if player2.bot:
            return await ctx.send(f"You can't challenge bots {ctx.author.mention}.")
        msg = await ctx.send(f"{player2.mention}, **{ctx.author}** has challenged you to a game of tic tac toe! Do you accept their challenge?")
        await msg.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        await msg.add_reaction("\N{CROSS MARK}")
        try:
            response, _ = await ctx.bot.wait_for(
                "reaction_add",
                check=lambda reaction, user: reaction.message.guild == ctx.guild
                and reaction.message.channel == ctx.message.channel
                and reaction.message == msg
                and str(reaction.emoji) in ["\N{WHITE HEAVY CHECK MARK}", "\N{CROSS MARK}"]
                and user == player2,
                timeout=300)
        except asyncio.TimeoutError:
            return await ctx.send(f"**{player2}** took too long to respond. {msg.jump_url}")
        if response.emoji == "\N{CROSS MARK}":
            return await ctx.send(f"**{player2}** has declined your challenge {ctx.author.mention}.")
        ttt = utils.TicTacToe(ctx, ctx.author, player2)
        await ttt.start()

    @commands.max_concurrency(1, per=commands.BucketType.channel)
    @commands.command()
    async def snake(self, ctx: CustomContext, *args):
        """
        Play a game of snake by yourself or with others.

        **How to Play**
        Click on the reactions to control the game:

        ⬆️ - Changes the snakes direction to `up`.
        ⬇️ - Changes the snakes direction to `down`.
        ⬅️ - Changes the snakes direction to `left`.
        ➡️ - Changes the snakes direction to `right`.
        ⏹️ - Ends the game.

        `args` - The users who can control the game. Set this to `--public` to allow anyone to control the game.
        """
        async with ctx.typing():
            if "--public" in args:
                player_ids = []
            else:
                player_ids = set()
                for arg in args:
                    player = await commands.MemberConverter().convert(ctx, arg)
                    if not player.bot:
                        player_ids.add(player.id)
                player_ids.add(ctx.author.id)
            menu = utils.SnakeMenu(player_ids, clear_reactions_after=True)
        await menu.start(ctx, wait=True)  # end typing

    @commands.command(aliases=["rps"])
    async def rockpaperscissors(self, ctx):
        """
        Play a game of rock paper scissors with the bot.
        """
        rps = utils.RockPaperScissors()
        await rps.start(ctx)


def setup(bot):
    bot.add_cog(Fun())
