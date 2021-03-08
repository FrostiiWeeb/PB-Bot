import discord
from discord.ext import menus
import re
from discord.ext import commands
import datetime
import time
import random
from collections import deque
import asyncio
import dateparser
import humanize
import typing
import textwrap

from contextlib import suppress
from aiohttp import InvalidURL


# helper functions


def owoify(text: str):
    """
    Owofies text.
    """
    return text.replace("l", "w").replace("L", "W").replace("r", "w").replace("R", "W")


def padding(d: dict, *, separator: str):
    return "\n".join(f"{k.rjust(len(max(d.keys(), key=len)))}{separator}{v}" for k, v in d.items())


def humanize_list(li: list):
    """
    "Humanizes" a list.
    """
    if not li:
        return li
    if len(li) == 1:
        return li[0]
    if len(li) == 2:
        return " and ".join(li)
    return f"{', '.join(str(item) for item in li[:-1])} and {li[-1]}"


class StopWatch:
    __slots__ = ("start_time", "end_time")

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def start(self):
        self.start_time = time.perf_counter()

    def stop(self):
        self.end_time = time.perf_counter()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.stop()

    @property
    def elapsed(self):
        return self.end_time - self.start_time


# page sources


class RawPageSource(menus.ListPageSource):
    def __init__(self, data, *, per_page=1):
        super().__init__(data, per_page=per_page)

    async def format_page(self, menu, page):
        return page


class PaginatorSource(menus.ListPageSource):
    def format_page(self, menu: menus.MenuPages, page):
        return f"```{page}```\nPage {menu.current_page + 1}/{self.get_max_pages()}"


class ErrorSource(menus.ListPageSource):
    async def format_page(self, menu: menus.MenuPages, page):
        if isinstance(page, list):
            page = page[0]
        traceback = f"```py\n{page['traceback']}```" if len(page["traceback"]) < 1991 else await menu.ctx.bot.mystbin(
            page["traceback"])
        embed = discord.Embed(title=f"Error Number {page['err_num']}", description=traceback)
        for k, v in list(page.items()):
            if k in ("err_num", "traceback"):
                continue
            value = f"`{v}`" if len(v) < 1000 else await menu.ctx.bot.mystbin(v)
            embed.add_field(name=k.replace("_", " ").title(), value=value)
        return embed


def command_tree(cmds):
    lines = []

    for number, command in enumerate(cmds, start=1):
        prefix = "└── " if number == len(cmds) else "├── "
        lines.append(f"{prefix}{command.name}")

        if isinstance(command, commands.Group):
            indent = "\t" if number == len(cmds) else "|\t"
            subcommands = textwrap.indent(command_tree(command.commands), prefix=indent)
            lines.append(subcommands)

    return "\n".join(lines)


class HelpSource(menus.ListPageSource):
    """
    Page Source for paginated help command.
    """
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, menu: menus.MenuPages, page):
        embed = discord.Embed(title="PB Bot Help",
                              description=f"Page {menu.current_page + 1}/{self.get_max_pages()}",
                              colour=menu.ctx.bot.embed_colour)
        embed.set_thumbnail(url=menu.ctx.bot.user.avatar_url)
        embed.set_footer(text=f"Type {menu.ctx.clean_prefix}help (command) for more info on a command.\n"
                              f"You can also type {menu.ctx.clean_prefix}help (category) for more info on a category.")
        if menu.current_page == 0:
            embed.add_field(name="About", value=f"```yaml\n{menu.ctx.bot.description}```", inline=False)

            embed.add_field(name="Useful Links",
                            value=f"[Invite Link]({menu.ctx.bot.invite_url})\n"
                                  f"[Support Server Invite]({menu.ctx.bot.support_server_invite})\n"
                                  f"[Source Code]({menu.ctx.bot.github_url})", inline=False)

            embed.add_field(name="Vote", value=f"[top.gg]({menu.ctx.bot.top_gg_url})", inline=False)
        else:
            _commands = page[1].get_commands()
            embed.add_field(name=page[0], value=f"```yaml\n{command_tree(_commands)}```")
        return embed


class DiscordStatusSource(menus.ListPageSource):
    def format_page(self, menu: menus.MenuPages, page):
        page.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return page


class HistorySource(menus.ListPageSource):
    async def format_page(self, menu: menus.MenuPages, page):
        embed = discord.Embed(
            title="Discord Status\nHistorical Data",
            description="```yaml\n"
                        f"Name: {page['name']}\n"
                        f"Status: {page['status'].title()}\n"
                        f"Created: {humanize.naturaldate(dateparser.parse(page['created_at'])).title()}\n"
                        f"Impact: {page['impact'].title()}" 
                        f"```")
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class DefineSource(menus.ListPageSource):
    def __init__(self, data, response):
        super().__init__(data, per_page=1)
        self.response = response

    async def format_page(self, menu: menus.MenuPages, page):
        embed = discord.Embed(
            title=f"Definitions for word `{self.response['word']}`",
            description=f"{self.response['phonetics'][0]['text']}\n"
                        f"[audio]({self.response['phonetics'][0]['audio']})",
            colour=menu.ctx.bot.embed_colour)
        defs = []
        for definition in page["definitions"]:
            defs.append(f"**Definition:** {definition['definition']}\n**Example:** {definition.get('example', 'None')}")
        embed.add_field(name=f"`{page['partOfSpeech']}`", value="\n\n".join(defs))
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class TodoSource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=5)

    async def format_page(self, menu: menus.MenuPages, page):
        embed = discord.Embed(
            title=f"Todo List for `{menu.ctx.author}`",
            description="\n".join(f"**{number}.** {item}" for number, item in page) or "Nothing here!",
            colour=menu.ctx.bot.embed_colour)
        return embed


class QueueSource(menus.ListPageSource):
    def __init__(self, data, player):
        super().__init__(data, per_page=5)

        self.player = player

    async def format_page(self, menu: menus.MenuPages, page):
        embed = discord.Embed(
            title="Song Queue",
            description="\n".join(
                f"**{number}.** {item}" if number != self.player.queue_position else f"*current song* ﹁\n**{number}.** {item}\n﹂ *current song*"
                for number, item in page) or "Nothing in the queue!",
            colour=menu.ctx.bot.embed_colour)
        if self.get_max_pages() > 0:
            embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class BlacklistSource(menus.ListPageSource):
    async def format_page(self, menu: menus.MenuPages, page):
        embed = discord.Embed(
            title="Blacklisted Users",
            description="```yaml\n" + ("\n".join(
                f"{user_id} - {reason}" for user_id, reason in page) or "No users in the blacklist.") + "```",
            colour=menu.ctx.bot.embed_colour)
        if self.get_max_pages() > 0:
            embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class SocketStatsSource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=15)

    async def format_page(self, menu: menus.MenuPages, page):
        table = PrettyTable.fancy(["Event Name", "Total"])
        for entry in page:
            table.add_row((entry[0], f"{entry[1]:,}"))
        return (f"```\n{table.build_table(autoscale=True)}```"
                f"\nPage {menu.current_page + 1}/{self.get_max_pages()}" if self.get_max_pages() > 0 else "")


# menus


class Confirm(menus.Menu):
    def __init__(self, msg: str, *, timeout: int = 120.0, delete_message_after: bool = True, clear_reactions_after: bool = False):
        super().__init__(
            timeout=timeout, delete_message_after=delete_message_after, clear_reactions_after=clear_reactions_after)
        self.msg = msg
        self.result = None

    async def send_initial_message(self, ctx: commands.Context, channel: discord.TextChannel):
        return await channel.send(self.msg)

    @menus.button('\N{WHITE HEAVY CHECK MARK}')
    async def do_confirm(self, _):
        self.result = True
        self.stop()

    @menus.button('\N{CROSS MARK}')
    async def do_deny(self, _):
        self.result = False
        self.stop()

    async def prompt(self, ctx: commands.Context):
        await self.start(ctx, wait=True)
        return self.result


class EmbedConfirm(menus.Menu):
    def __init__(self, embed: discord.Embed, *, timeout: int = 120.0, delete_message_after: bool = True, clear_reactions_after: bool = False):
        super().__init__(
            timeout=timeout, delete_message_after=delete_message_after, clear_reactions_after=clear_reactions_after)
        self.embed = embed
        self.result = None

    async def send_initial_message(self, ctx: commands.Context, channel: discord.TextChannel):
        return await channel.send(embed=self.embed)

    @menus.button('\N{WHITE HEAVY CHECK MARK}')
    async def do_confirm(self, _):
        self.result = True
        self.stop()

    @menus.button('\N{CROSS MARK}')
    async def do_deny(self, _):
        self.result = False
        self.stop()

    async def prompt(self, ctx: commands.Context):
        await self.start(ctx, wait=True)
        return self.result


class PaginatedHelpCommand(menus.MenuPages):
    """
    Paginated help command.
    """
    @menus.button('\U00002139', position=menus.Last(2))
    async def on_info(self, _):
        embed = discord.Embed(title="Paginator Help",
                              description="➡️ next page\n"
                                          "⬅️ previous page\n"
                                          "⏮️ first page\n"
                                          "⏭️ last page\n"
                                          "ℹ️ shows this message\n"
                                          "❔    shows reading help and using the bot\n"
                                          "⏹️ closes the paginator",
                              colour=self.ctx.bot.embed_colour)
        embed.set_thumbnail(url=self.ctx.bot.user.avatar_url)
        embed.set_footer(text=f"You were on page {self.current_page + 1} before this message.")
        await self.message.edit(embed=embed)

    @menus.button('\U00002754', position=menus.Last(3))
    async def on_question_mark(self, _):
        description = (
            "<> - required argument\n"
            "[] - optional argument\n"
            "argument... - multiple values can be passed to this argument\n"
            "{} - required flag\n"
            "() - optional flag\n"
            "a|b - either a or b\n\n"
            "**Do not include the <>, [], () or {} when using a command!**\n\n"
            'Arguments are delimited by a whitespace (" "). If you would like to provide an argument with whitespace, '
            'use quotes (""). Some arguments have "consume rest" behaviour, meaning that you don\'t have to use quotes.'
            "\n\n"
            "**Examples:**\n"
            "signature: `command <argument>`\n\n"
            "without consume rest:\n"
            '`command a b c` - "argument" will be set to `a`.\n'
            '`command "a b c"` - "argument" will be set to `a b c`.\n\n'
            "with consume rest:\n"
            '`command a b c` - "argument" will be set to `a b c`.\n'
            '`command "a b c"` - "argument" will be set to `"a b c"`.\n\n'
            "**Flag Examples:**\n"
            "signature: `command {--flag|-f}`\n\n"
            "`command --flag=a`\n"
            "`command --flag a`\n"
            '`command --flag="a b c"`\n'
            "`command -f=a`"
        )

        embed = discord.Embed(
            title="Reading Help and using the Bot",
            description=description,
            colour=self.ctx.bot.embed_colour)

        embed.set_thumbnail(url=self.ctx.bot.user.avatar_url)
        embed.set_footer(text=f"You were on page {self.current_page + 1} before this message.")
        await self.message.edit(embed=embed)

    @menus.button('\N{BLACK SQUARE FOR STOP}\ufe0f', position=menus.Last(4))
    async def end_menu(self, _):
        self.stop()


class PlayerMenu(menus.Menu):
    """
    Player menu class.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.embed = None

    async def send_initial_message(self, ctx, channel: discord.TextChannel):
        ctx.player.menus.append(self)
        self.build_embed()
        return await channel.send(embed=self.embed)

    async def build_edit(self):
        self.build_embed()
        await self.message.edit(embed=self.embed)

    def build_embed(self):
        max_song_length = float(f"{self.ctx.player.current.length / 1000:.2f}")
        current_position = float(f"{self.ctx.player.position / 1000:.2f}")
        bar_number = int((int(current_position) / int(max_song_length)) * 20)
        bar = f"\||{bar_number * self.ctx.bot.emoji_dict['red_line']}⚫{(19 - bar_number) * self.ctx.bot.emoji_dict['white_line']}||"
        try:
            coming_up = self.ctx.player.queue[self.ctx.player.queue_position]
        except IndexError:
            coming_up = "None"

        self.embed = discord.Embed(
            title=f"Player for `{self.ctx.guild}`",
            description=
            f"**Status:** `{'Paused' if self.ctx.player.is_paused else 'Playing'}`\n"
            f"**Connected To:** `{self.ctx.guild.get_channel(self.ctx.player.channel_id).name}`\n"
            f"**Volume:** `{self.ctx.player.volume}`\n"
            f"**Equalizer:** `{self.ctx.player.equalizer}`",
            colour=self.ctx.bot.embed_colour
        )
        self.embed.add_field(name="Now Playing:", value=f"{self.ctx.player.current}", inline=False)
        self.embed.add_field(name="Duration:", value=humanize.precisedelta(datetime.timedelta(milliseconds=self.ctx.player.current.length)), inline=False)
        self.embed.add_field(name="Time Elapsed:", value=humanize.precisedelta(datetime.timedelta(milliseconds=self.ctx.player.position)), inline=False)
        self.embed.add_field(name="YT Link:", value=f"[Click Here!]({self.ctx.player.current.uri})", inline=False)
        self.embed.add_field(name="Coming Up...", value=coming_up, inline=False)
        self.embed.add_field(name="Progress", value=bar, inline=False)

    @menus.button("⏮️")
    async def song_previous(self, _):
        await self.ctx.player.do_previous()
        if self.ctx.player.queue_position > len(self.ctx.player.queue) - 1:
            await self.build_edit()

    @menus.button("⏭️")
    async def song_skip(self, _):
        await self.ctx.player.stop()
        if self.ctx.player.queue_position < len(self.ctx.player.queue) - 1:
            await self.build_edit()

    @menus.button("⏯️")
    async def play_pause(self, _):
        await self.ctx.player.set_pause(False if self.ctx.player.paused else True)
        await self.build_edit()

    @menus.button("🔈")
    async def volume(self, _):
        await VolumeMenu(delete_message_after=True).start(self.ctx)
        self.stop()

    @menus.button("ℹ️")
    async def on_menu_info(self, _):
        embed = discord.Embed(
            title="How to use the Player",
            description=
            "⏮️ go back to the previous song\n"
            "⏭️  skip the current song\n" 
            "⏯️  pause and unpause the player\n"
            "🔈 opens the volume bar and closes the player\n"
            "ℹ️  shows this message\n"
            "🔁 refreshes the player\n"
            "⏹️  close the player",
            colour=self.ctx.bot.embed_colour)
        if self.embed.title == "How to use the Player":  # hide the menu info screen
            self.build_embed()
        else:
            self.embed = embed
        await self.message.edit(embed=self.embed)

    @menus.button("🔁")
    async def on_refresh(self, _):
        await self.build_edit()

    @menus.button("⏹️")
    async def on_menu_close(self, _):
        self.stop()


class VolumeMenu(menus.Menu):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.embed = None

    async def send_initial_message(self, ctx, channel: discord.TextChannel):
        ctx.player.menus.append(self)
        self.build_embed()
        return await channel.send(embed=self.embed)

    def build_embed(self):
        volume_bar_number = int(self.ctx.player.volume / 100 * 2)
        volume_bar = [(volume_bar_number - 1) * "🟦"] + [self.ctx.bot.emoji_dict["blue_button"]] + [(20 - volume_bar_number) * "⬜"]
        self.embed = discord.Embed(title="Volume Bar", description="".join(volume_bar), colour=self.ctx.bot.embed_colour)
        self.embed.set_footer(text=f"Current Volume: {self.ctx.player.volume}")

    async def build_edit(self):
        self.build_embed()
        await self.message.edit(embed=self.embed)

    @menus.button("⏮️")
    async def on_volume_down_100(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume - 100)
        await self.build_edit()

    @menus.button("⏪")
    async def on_volume_down_10(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume - 10)
        await self.build_edit()

    @menus.button("⬅️")
    async def on_volume_down(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume - 1)
        await self.build_edit()

    @menus.button("➡️")
    async def on_volume_up(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume + 1)
        await self.build_edit()

    @menus.button("⏩")
    async def on_volume_up_10(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume + 10)
        await self.build_edit()

    @menus.button("⏭️")
    async def on_volume_up_100(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume + 100)
        await self.build_edit()

    @menus.button("ℹ️")
    async def on_menu_info(self, _):
        embed = discord.Embed(
            title="How to use the Volume Bar",
            description=
            "⏮️ decrease the volume by 100\n"
            "⏪ decrease the volume by 10\n"
            "⬅️ decrease the volume by 1\n"
            "➡️ increase the volume by 1\n"
            "⏩ increase the volume by 10\n"
            "⏭️ increase the volume by 100\n"
            "ℹ️ shows this message\n"
            "🔁 refreshes the volume bar\n"
            "⏹️ closes the volume bar",
            colour=self.ctx.bot.embed_colour)
        if self.embed.title == "How to use the Volume Bar":  # hide the menu info screen
            self.build_embed()
        else:
            self.embed = embed
        await self.message.edit(embed=self.embed)

    @menus.button("🔁")
    async def on_refresh(self, _):
        await self.build_edit()

    @menus.button("⏹️")
    async def on_menu_close(self, _):
        self.stop()


# converters


class ShortTime(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        time_unit_mapping = {
            "s": "seconds",    "sec": "seconds",    "second": "seconds",   "seconds": "seconds",
            "m": "minutes",    "min": "minutes",    "minute": "minutes",   "minutes": "minutes",
            "hour": "hours",   "hours": "hours",    "h": "hours",          "hr":   "hours",      "hrs": "hours",
            "day": "days",     "days": "days",      "dys": "days",         "d":   "days",        "dy": "days",
            "week": "weeks",   "weeks": "weeks",    "wks": "weeks",        "wk": "weeks",        "w": "weeks",
        }
        argument = argument.lower()
        number = re.search(r"\d+[.]?\d*?", argument)
        time_unit = re.search(
            f"s|sec|second|seconds|m|min|minute|minutes|hour|hours|h|hr|hrs|day|days|dys|d|dy|week|weeks|wks|wk|w",
            argument)
        if not number:
            raise commands.BadArgument("Invalid duration provided.")
        if not time_unit:
            raise commands.BadArgument("Invalid time unit provided. Some time units than you can use include `min`, `s` and `wks`.")
        number = float(number.group(0))
        time_unit = time_unit_mapping[time_unit.group(0)]
        try:
            return datetime.timedelta(**{time_unit: number})
        except OverflowError:
            raise commands.BadArgument("Time is too large.")


class StripCodeblocks(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        double_codeblock = re.compile(r"```(.*\n)?(.+)```", flags=re.IGNORECASE)
        inline_codeblock = re.compile(r"`(.+)`", flags=re.IGNORECASE)
        # first, try double codeblock
        match = double_codeblock.fullmatch(argument)
        if match:
            return match.group(2)
        # try inline codeblock
        match = inline_codeblock.fullmatch(argument)
        if match:
            return match.group(1)
        # couldn't match
        return argument


class ImageConverter(commands.Converter):
    def __init__(self, bot):
        self.bot = bot

    image_regex = re.compile(r"image/.+", flags=re.IGNORECASE)

    async def _convert(self, message: discord.Message, argument: str):
        # hierarchy:
        # members
        # users
        # emojis
        # unicode emojis
        # links
        # attachments

        ctx = await self.bot.get_context(message)

        if argument:  # no need to check if x is in the message if x is nothing
            # members
            with suppress(commands.BadArgument):
                return await (await commands.MemberConverter().convert(ctx, argument)).avatar_url_as(format="png").read()

            # users
            with suppress(commands.BadArgument):
                return await (await commands.UserConverter().convert(ctx, argument)).avatar_url_as(format="png").read()

            # emojis
            with suppress(commands.BadArgument):
                return await (await commands.PartialEmojiConverter().convert(ctx, argument)).url.read()

            # unicode emojis
            url = f"https://twemoji.maxcdn.com/v/latest/72x72/{ord(argument[0]):x}.png"
            async with self.bot.session.get(url) as r:
                if r.status in range(200, 300):
                    return await r.read()

            # embedded images (links)
            with suppress(InvalidURL):
                async with self.bot.session.get(argument.strip("<>")) as r:
                    if r.status in range(200, 300) and ImageConverter.image_regex.fullmatch(r.headers["Content-Type"]):
                        return await r.read()

        # attachments
        for attachment in message.attachments:
            if attachment.height or attachment.width:  # is an image
                return await attachment.read()

        return

    async def convert(self, ctx: commands.Context, argument: str):
        # invocation message
        if image := await self._convert(ctx.message, argument):
            return image

        # message link
        if argument:
            with suppress(commands.BadArgument):
                message = await commands.MessageConverter().convert(ctx, argument)
                if image := await self._convert(message, message.content):
                    return image

        # referenced message (reply)
        if ctx.message.reference and isinstance(ctx.message.reference.resolved, discord.Message):
            if image := await self._convert(ctx.message.reference.resolved, ctx.message.reference.resolved.content):
                return image

        # fallback
        return await ctx.author.avatar_url_as(format="png").read()


# game classes


class SnakeGame:
    def __init__(self, *, snake_head: str = "🟢", snake_body: str = "🟩", apple: str = "🍎", empty: str = "⬜", border: str = "🟥"):
        self.snake_head = snake_head
        self.snake_body = snake_body
        self.apple = apple
        self.empty = empty
        self.border = border
        self.grid = [[[self.empty, self.border][i == 0 or i == 11 or j == 0 or j == 11] for i in range(12)] for j in range(12)]
        self.snake_x = random.randint(1, 10)
        self.snake_y = random.randint(1, 10)
        self.snake = deque()

        self.apple_x = None
        self.apple_y = None

        self.score = 0
        self.lose = False

        self.grid[self.snake_x][self.snake_y] = self.snake_head
        self.snake.appendleft((self.snake_x, self.snake_y))
        self.spawn_apple()

    def show_grid(self):
        li = []
        for grid_entry in self.grid:
            for item in grid_entry:
                li.append(item)
        return "\n".join(["".join([self.grid[i][j] for j in range(12)]) for i in range(12)])

    def spawn_apple(self):
        while True:
            x = random.randint(1, 10)
            y = random.randint(1, 10)
            if self.grid[x][y] == self.empty:
                self.grid[x][y] = self.apple
                self.apple_x = x
                self.apple_y = y
                break

    def move_snake(self, x: int, y: int, *, apple: bool = False):
        tail_coords = self.snake[-1]
        previous_x = self.snake_x
        previous_y = self.snake_y
        self.snake_x += x
        self.snake_y += y
        self.grid[self.snake_x][self.snake_y] = self.snake_head
        if apple:
            self.grid[previous_x][previous_y] = self.snake_body
        else:
            self.grid[tail_coords[0]][tail_coords[1]] = self.empty
            self.grid[previous_x][previous_y] = self.snake_body if self.score != 0 else self.empty
            self.snake.pop()
        self.snake.appendleft((self.snake_x, self.snake_y))

    def update(self, direction: str):
        direction = direction.lower()
        x = y = 0
        if direction == "up":
            x = -1
        elif direction == "left":
            y = -1
        elif direction == "down":
            x = 1
        elif direction == "right":
            y = 1
        else:
            return
        new_x = self.snake_x + x
        new_y = self.snake_y + y
        if self.grid[new_x][new_y] == self.border:
            self.lose = "You hit the edge of the board."
        elif self.grid[new_x][new_y] == self.snake_body:
            self.lose = "You hit your own body."
        elif self.grid[new_x][new_y] == self.apple:
            self.move_snake(x, y, apple=True)
            self.score += 1
            self.spawn_apple()
        else:
            self.move_snake(x, y)


class SnakeMenu(menus.Menu):
    """
    Menu for snake game.
    """
    def __init__(self, player_ids: typing.Union[list, tuple], **kwargs):
        super().__init__(**kwargs)
        self.game = SnakeGame(empty="⬛")
        self.player_ids = player_ids
        self.direction = None
        self.task = None
        self.embed = None
        self.is_game_start = asyncio.Event()

    async def send_initial_message(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.refresh_embed()
        self.task = ctx.bot.loop.create_task(self.loop())
        return await channel.send(embed=self.embed)

    async def get_players(self):
        if not self.player_ids:
            return "anyone can control the game"
        players = [str(await self.ctx.bot.fetch_user(player_id)) for player_id in self.player_ids]
        if len(self.player_ids) > 10:
            first10 = "\n".join(player for player in players[:10])
            return f"{first10}\nand {len(players[10:])} more..."
        return "\n".join(str(player) for player in players)

    async def refresh_embed(self):
        self.embed = discord.Embed(title=f"Snake Game", description=self.game.show_grid(), colour=self.ctx.bot.embed_colour)
        self.embed.add_field(name="Players", value=await self.get_players())
        self.embed.add_field(name="Score", value=str(self.game.score))
        self.embed.add_field(name="Current Direction", value=self.direction)

    async def loop(self):
        await self.is_game_start.wait()
        while not self.game.lose:
            await asyncio.sleep(1.5)
            self.game.update(self.direction)
            await self.refresh_embed()
            await self.message.edit(embed=self.embed)
        self.embed.add_field(name="Game Over", value=self.game.lose)
        await self.message.edit(embed=self.embed)
        self.stop()

    def reaction_check(self, payload):
        if payload.message_id != self.message.id:
            return False

        if self.player_ids:  # only specific people can access the board
            if payload.user_id not in self.player_ids:
                return False
        else:
            if payload.user_id == self.ctx.bot.user.id:
                return False
        return payload.emoji in self.buttons

    @menus.button("⬆️")
    async def up(self, _):
        self.direction = "up"
        self.is_game_start.set()

    @menus.button("⬇️")
    async def down(self, _):
        self.direction = "down"
        self.is_game_start.set()

    @menus.button("⬅️")
    async def left(self, _):
        self.direction = "left"
        self.is_game_start.set()

    @menus.button("➡️")
    async def right(self, _):
        self.direction = "right"
        self.is_game_start.set()

    @menus.button("⏹️")
    async def on_stop(self, _):
        self.stop()

    def stop(self):
        self.task.cancel()
        super().stop()


class TicTacToe:
    """
    Game class for tic-tac-toe.
    """
    __slots__ = ("player1", "player2", "ctx", "msg", "turn", "player_mapping", "x_and_o_mapping", "board")

    def __init__(self, ctx: commands.Context, player1: discord.Member, player2: discord.Member):
        self.player1 = player1
        self.player2 = player2
        self.ctx = ctx
        self.msg = None
        self.board = {"↖️": "⬜", "⬆️": "⬜", "↗️": "⬜",
                      "➡️": "⬜", "↘️": "⬜", "⬇️": "⬜",
                      "↙️": "⬜", "⬅️": "⬜", "⏺️": "⬜"}
        self.turn = random.choice([self.player1, self.player2])
        if self.turn == player1:
            self.player_mapping = {self.player1: "🇽", self.player2: "🅾️"}
            self.x_and_o_mapping = {"🇽": self.player1, "🅾️": self.player2}
            return
        self.player_mapping = {self.player2: "🇽", self.player1: "🅾️"}
        self.x_and_o_mapping = {"🇽": self.player2, "🅾️": self.player1}

    def show_board(self):
        return f"**Tic-Tac-Toe Game between `{self.player1}` and `{self.player2}`**\n\n" \
            f"🇽: `{self.x_and_o_mapping['🇽']}`\n🅾️: `{self.x_and_o_mapping['🅾️']}`\n\n" \
            f"{self.board['↖️']} {self.board['⬆️']} {self.board['↗️']}\n" \
            f"{self.board['⬅️']} {self.board['⏺️']} {self.board['➡️']}\n" \
            f"{self.board['↙️']} {self.board['⬇️']} {self.board['↘️']}\n\n"

    def switch_turn(self):
        if self.turn == self.player1:
            self.turn = self.player2
            return
        self.turn = self.player1

    async def loop(self):
        while True:
            try:
                move, user = await self.ctx.bot.wait_for(
                    "reaction_add",
                    check=lambda reaction, user: reaction.message.guild == self.ctx.guild
                    and reaction.message.channel == self.ctx.message.channel
                    and reaction.message == self.msg and str(reaction.emoji) in self.board.keys() and user == self.turn,
                    timeout=300
                )
            except asyncio.TimeoutError:
                await self.msg.edit(content=f"{self.show_board()}Game Over.\n**{self.turn}** took too long to move.")
                await self.ctx.send(f"{self.turn.mention} game over, you took too long to move. {self.msg.jump_url}")
                return
            if self.board[move.emoji] == "⬜":
                self.board[move.emoji] = self.player_mapping[self.turn]
            else:
                await self.msg.edit(content=f"{self.show_board()}**Current Turn**: `{self.turn}`\nThat place is already filled.")
                continue
            condition = (
                self.board["↖️"] == self.board["⬆️"] == self.board["↗️"] != "⬜",  # across the top
                self.board["⬅️"] == self.board["⏺️"] == self.board["➡️"] != "⬜",  # across the middle
                self.board["↙️"] == self.board["⬇️"] == self.board["↘️"] != "⬜",  # across the bottom
                self.board["↖️"] == self.board["⬅️"] == self.board["↙️"] != "⬜",  # down the left side
                self.board["⬆️"] == self.board["⏺️"] == self.board["⬇️"] != "⬜",  # down the middle
                self.board["↗️"] == self.board["➡️"] == self.board["↘️"] != "⬜",  # down the right side
                self.board["↖️"] == self.board["⏺️"] == self.board["↘️"] != "⬜",  # diagonal
                self.board["↙️"] == self.board["⏺️"] == self.board["↗️"] != "⬜",  # diagonal
            )
            if any(condition):
                await self.msg.edit(content=f"{self.show_board()}Game Over.\n**{self.turn}** won!")
                break
            if "⬜" not in self.board.values():
                await self.msg.edit(content=f"{self.show_board()}Game Over.\nIt's a Tie!")
                break
            self.switch_turn()
            await self.msg.edit(content=f"{self.show_board()}**Current Turn**: `{self.turn}`")

    async def start(self):
        self.msg = await self.ctx.send(f"{self.show_board()}Setting up the board...")
        for reaction in self.board.keys():
            await self.msg.add_reaction(reaction)
        await self.msg.edit(content=f"{self.show_board()}**Current Turn**: `{self.turn}`")
        await self.loop()


class RockPaperScissors(menus.Menu):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.embed = None

    async def send_initial_message(self, ctx, channel):
        self.embed = discord.Embed(
            title=f"Rock Paper Scissors with `{ctx.author}`",
            description="React with ✊, ✋, ✌️ or ⏹️ to end the game.",
            colour=ctx.bot.embed_colour)
        return await ctx.send(embed=self.embed)

    async def determine_winner(self, user_choice):
        rps_map = {0: "rock", 1: "paper", 2: "scissors"}
        winner_map = [
            [0, 1, -1],
            [-1, 0, 1],
            [1, -1, 0]
        ]
        messages = {
            0: "It's a draw!",
            1: "Congratulations! You won!",
            -1: "You lost! Better luck next time."
        }

        bot_choice = random.randint(0, 2)
        message = messages[winner_map[bot_choice][user_choice]]
        self.embed.description = f"You drew {rps_map[user_choice]} and I drew {rps_map[bot_choice]}.\n{message}"
        await self.message.edit(embed=self.embed)
        self.stop()

    @menus.button("✊")
    async def rock(self, _):
        await self.determine_winner(0)

    @menus.button("✋")
    async def paper(self, _):
        await self.determine_winner(1)

    @menus.button("✌")
    async def scissors(self, _):
        await self.determine_winner(2)

    @menus.button("⏹️")
    async def stop_menu(self, _):
        with suppress(discord.HTTPException):
            await self.message.delete()
        self.stop()


# misc.


class PrettyTable:
    def __init__(self, headers: typing.Union[list, tuple], **kwargs):
        self.headers = [str(x) for x in headers]
        self.rows = []

        self.top_left_corner = kwargs.pop("top_left_corner")
        self.top_right_corner = kwargs.pop("top_right_corner")
        self.bottom_left_corner = kwargs.pop("bottom_left_corner")
        self.bottom_right_corner = kwargs.pop("bottom_right_corner")
        self.horizontal_line = kwargs.pop("horizontal_line")
        self.vertical_line = kwargs.pop("vertical_line")
        self.double_vertical_and_right = kwargs.pop("double_vertical_and_right")
        self.double_vertical_and_left = kwargs.pop("double_vertical_and_left")
        self.double_up_and_horizontal = kwargs.pop("double_up_and_horizontal")
        self.double_down_and_horizontal = kwargs.pop("double_down_and_horizontal")
        self.double_vertical_and_horizontal = kwargs.pop("double_vertical_and_horizontal")

    @classmethod
    def default(cls, headers: typing.Union[list, tuple]):
        attrs = {
            "top_left_corner":                  "+",
            "top_right_corner":                 "+",
            "bottom_left_corner":               "+",
            "bottom_right_corner":              "+",
            "horizontal_line":                  "-",
            "vertical_line":                    "|",
            "double_vertical_and_right":        "+",
            "double_vertical_and_left":         "+",
            "double_up_and_horizontal":         "+",
            "double_down_and_horizontal":       "+",
            "double_vertical_and_horizontal":   "+"
        }
        return cls(headers, **attrs)

    @classmethod
    def fancy(cls, headers: typing.Union[list, tuple]):
        attrs = {
            "top_left_corner":                  "╔",
            "top_right_corner":                 "╗",
            "bottom_left_corner":               "╚",
            "bottom_right_corner":              "╝",
            "horizontal_line":                  "═",
            "vertical_line":                    "║",
            "double_vertical_and_right":        "╠",
            "double_vertical_and_left":         "╣",
            "double_up_and_horizontal":         "╩",
            "double_down_and_horizontal":       "╦",
            "double_vertical_and_horizontal":   "╬"
        }
        return cls(headers, **attrs)

    def add_row(self, items: typing.Union[list, tuple]):
        self.rows.append([str(x) for x in items])

    def build_table(self, *, autoscale: bool = False, padding: int = None):
        table = []
        padding = padding or 2
        # make the parts of the table
        if autoscale:
            entries = [
                (self.headers[i], len(max([row[i] for row in self.rows] + [self.headers[i]], key=len)))
                for i in range(len(self.headers))
            ]
        else:
            entries = [(header, len(header)) for header in self.headers]
        # debugging: remove when finished
        # entries = [(h1, len1), (h2, len2)]
        # rows = [[a, b, c], [1, 2, 3]]
        center_lines = [self.horizontal_line * (header[1] + padding) for header in entries]

        top = f"{self.top_left_corner}{self.double_down_and_horizontal.join(center_lines)}{self.top_right_corner}"
        headers = f"{self.vertical_line}{self.vertical_line.join(header.center(size + padding) for header, size in entries)}{self.vertical_line}"
        header_separator = f"{self.double_vertical_and_right}{self.double_vertical_and_horizontal.join(self.horizontal_line * (size + padding) for _, size in entries)}{self.double_vertical_and_left}"
        rows = [f"{self.vertical_line}{self.vertical_line.join(entry.center(header_info[1] + padding) for entry, header_info in zip(row, entries))}{self.vertical_line}" for row in self.rows]
        bottom = f"{self.bottom_left_corner}{self.double_up_and_horizontal.join(center_lines)}{self.bottom_right_corner}"

        # construct the table
        table.append(top)
        table.append(headers)
        table.append(header_separator)
        for row in rows:
            table.append(row)
        table.append(bottom)

        return "\n".join(table)
