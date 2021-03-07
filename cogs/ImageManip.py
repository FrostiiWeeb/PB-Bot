import discord
import polaroid
import typing

from discord.ext import commands
from io import BytesIO

from utils import utils
from utils.classes import CustomContext


class ImageManip(commands.Cog):
    """
    Image manipulation commands. Powered by [polaroid](https://github.com/Daggy1234/polaroid).
    **Note:** The image defaults to your avatar if it can't convert.
    """
    async def do_polaroid_image_manip(self, ctx: CustomContext, image: bytes, func: str, filename: str, *args, **kwargs):
        async with ctx.typing():
            with utils.StopWatch() as sw:
                image = polaroid.Image(image)
                func = getattr(image, func)
                await ctx.bot.loop.run_in_executor(None, func, *args, **kwargs)
            embed, file = self.build_embed(ctx, image, filename=filename, elapsed=sw.elapsed)
            await ctx.send(embed=embed, file=file)

    @staticmethod
    def build_embed(ctx: CustomContext, image, *, filename: str, elapsed: int):
        file = discord.File(BytesIO(await ctx.bot.loop.run_in_executor(None, image.save_bytes())), filename=f"{filename}.png")
        embed = discord.Embed(colour=ctx.bot.embed_colour)
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        embed.set_image(url=f"attachment://{filename}.png")
        embed.set_footer(text=f"Finished in {elapsed:.3f} seconds")
        return embed, file

    @commands.command()
    async def solarize(self, ctx: CustomContext, *, image=None):
        """
        Solarize an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="solarize", filename="solarize")

    @commands.command()
    async def greyscale(self, ctx: CustomContext, *, image=None):
        """
        Greyscale an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="grayscale", filename="greyscale")

    @commands.command(aliases=["colorize"])
    async def colourize(self, ctx: CustomContext, *, image=None):
        """
        Enhances the colour in an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="colorize", filename="colourize")

    @commands.command()
    async def noise(self, ctx: CustomContext, *, image=None):
        """
        Adds noise to an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="add_noise_rand", filename="noise")

    @commands.command()
    async def rainbow(self, ctx: CustomContext, *, image=None):
        """
        🌈

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="apply_gradient", filename="rainbow")

    @commands.command()
    async def desaturate(self, ctx: CustomContext, *, image=None):
        """
        Desaturates an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="desaturate", filename="desaturate")

    @commands.command()
    async def edges(self, ctx: CustomContext, *, image=None):
        """
        Enhances the edges in an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="edge_detection", filename="edges")

    @commands.command()
    async def emboss(self, ctx: CustomContext, *, image=None):
        """
        Adds an emboss-like effect to an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="emboss", filename="emboss")

    @commands.command()
    async def invert(self, ctx: CustomContext, *, image=None):
        """
        Inverts the colours in an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="invert", filename="invert")

    @commands.command(aliases=["pinknoise", "pink-noise"])
    async def pink_noise(self, ctx: CustomContext, *, image=None):
        """
        Adds pink noise to an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="pink_noise", filename="pink-noise")

    @commands.command()
    async def sepia(self, ctx: CustomContext, *, image=None):
        """
        Adds a brown tint to an image.

        `image` - The image.
        """
        image = await utils.ImageConverter(ctx.bot).convert(ctx, image)
        await self.do_polaroid_image_manip(ctx, image, func="sepia", filename="sepia")


def setup(bot):
    bot.add_cog(ImageManip())
