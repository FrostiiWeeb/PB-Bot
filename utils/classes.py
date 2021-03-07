import discord
import datetime
import aiohttp
import wavelink
import os
import re
import asyncio
import asyncpg
import json
import aioredis
import typing

from collections import Counter
from discord.ext import commands, tasks
from copy import deepcopy
from pyfiglet import Figlet

from .utils import StopWatch
from config import config

# constants

EMPTY_GUILD_CACHE = {"prefixes": []}
DEFAULT_PREFIXES = ["pb"]
EMBED_COLOUR = 0x01ad98
BOT_ID = "719907834120110182"
PERMISSIONS = 104189127
DESCRIPTION = "An easy to use, multipurpose discord bot written in Python by PB#4162."
COMMITS_URL = "https://api.github.com/repos/PB4162/PB-Bot/commits"


async def get_prefix(bot, message: discord.Message):
    """
    Get prefix function.
    """
    if not message.guild or (cache := await bot.cache.get_guild_info(message.guild.id)) is None:
        prefixes = DEFAULT_PREFIXES
    else:
        prefixes = cache["prefixes"]
        if not prefixes:
            prefixes = DEFAULT_PREFIXES
    prefixes = sorted(prefixes, key=len)
    for prefix in prefixes:
        match = re.match(rf"^({prefix}\s*).*", message.content, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    # fallback
    return commands.when_mentioned(bot, message)


class PB_Bot(commands.Bot):
    """
    Subclassed bot.
    """
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(
            command_prefix=get_prefix,
            case_insensitive=True,
            intents=intents,
            owner_id=config["owner_id"],
            description=DESCRIPTION
        )

        # case-insensitive cogs
        self._BotBase__cogs = commands.core._CaseInsensitiveDict()

        # general stuff
        self.start_time = datetime.datetime.now()
        self.session = aiohttp.ClientSession()
        self.wavelink = wavelink.Client(bot=self)
        self.coglist = [f"cogs.{item[:-3]}" for item in os.listdir("cogs") if item != "__pycache__"] + ["jishaku"]
        self.command_list = []
        self.figlet = Figlet()
        self.embed_colour = EMBED_COLOUR

        # database connections
        self.pool = self.loop.run_until_complete(asyncpg.create_pool(**config["postgresql"]))
        self.redis = self.loop.run_until_complete(aioredis.create_redis_pool(config["redis"]))

        # cache
        self.cache = Cache(self)

        # links
        self.github_url = "https://github.com/PB4162/PB-Bot"
        self.invite_url = discord.utils.oauth_url(BOT_ID, permissions=discord.Permissions(PERMISSIONS))
        self.support_server_invite = "https://discord.gg/qQVDqXvmVt"
        self.top_gg_url = "https://top.gg/bot/719907834120110182"

        # global ratelimit
        self.global_cooldown = commands.CooldownMapping.from_cooldown(rate=5, per=5, type=commands.BucketType.user)

        # global check
        @self.check
        async def global_check(ctx: CustomContext):
            # check if blacklisted
            if await ctx.bot.cache.is_blacklisted(ctx.author.id):
                embed = discord.Embed(
                    description=f"{ctx.author.mention}, you have been blacklisted from this bot. If you think that this"
                                f" was a mistake, please report it in the "
                                f"[support server]({ctx.bot.support_server_invite}).",
                    colour=ctx.bot.embed_colour)
                await ctx.send(embed=embed)
                return False

            # check if ratelimited
            bucket = self.global_cooldown.get_bucket(ctx.message)
            retry_after = bucket.update_rate_limit()
            if retry_after:
                raise StopSpammingMe()
            return True

        # emojis
        self.emoji_dict = {
            "red_line": "<:red_line:799429087352717322>",
            "white_line": "<:white_line:799429050061946881>",
            "blue_button": "<:blue_button:806550473645490230>",
            "voice_channel": "<:voice_channel:799429142902603877>",
            "text_channel": "<:text_channel:799429180109750312>",
            "red_tick": "<:red_tick:799429329372971049>",
            "green_tick": "<:green_tick:799429375719899139>",
            "online": "<:online:799429451771150386>",
            "offline": "<:offline:799429511199850546>",
            "idle": "<:idle:799429473611153409>",
            "dnd": "<:dnd:799429487749103627>",
            "tickon": "<:tickon:799429228415156294>",
            "tickoff": "<:tickoff:799429264188637184>",
            "xon": "<:xon:799428912195174442>",
            "xoff": "<:xoff:799428963775807489>",
            "upvote": "<:upvote:799432692595687514>",
            "downvote": "<:downvote:799432736892911646>",
        }

    # custom context

    async def get_context(self, message: discord.Message, *, cls=None):
        return await super().get_context(message, cls=cls or CustomContext)

    # events

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.id == self.owner_id and after.content != before.content:
            await self.process_commands(after)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if re.fullmatch(f"^(<@!?{self.user.id}>)\s*", message.content):
            ctx = await self.get_context(message)
            return await ctx.invoke(self.get_command("prefix"))
        await self.process_commands(message)

    async def on_guild_leave(self, guild: discord.Guild):
        await self.cache.delete_guild_info(guild.id)

    async def on_command(self, ctx):
        self.cache.command_stats["top_commands_today"].update({ctx.command.qualified_name: 1})
        self.cache.command_stats["top_commands_overall"].update({ctx.command.qualified_name: 1})

        self.cache.command_stats["top_users_today"].update({str(ctx.author.id): 1})
        self.cache.command_stats["top_users_overall"].update({str(ctx.author.id): 1})

    # ping helpers

    @staticmethod
    async def api_ping(ctx):
        with StopWatch() as sw:
            await ctx.trigger_typing()
        return sw.elapsed

    async def postgresql_ping(self):
        with StopWatch() as sw:
            await self.pool.fetch("SELECT 1")
        return sw.elapsed

    async def redis_ping(self):
        with StopWatch() as sw:
            await self.redis.ping()
        return sw.elapsed

    # loops

    @tasks.loop(minutes=30)
    async def presence_update(self):
        await self.change_presence(
            status=discord.Status.idle,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers and {len(self.users)} users")
        )

    @presence_update.before_loop
    async def before_presence(self):
        await self.wait_until_ready()

    @tasks.loop(hours=24)
    async def clear_cmd_stats(self):
        await self.cache.clear_cmd_stats()

    @clear_cmd_stats.before_loop
    async def clear_command_stats_before(self):
        # wait until midnight to start the loop
        tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
        midnight = datetime.datetime(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)
        dt = midnight - datetime.datetime.now()
        await asyncio.sleep(dt.total_seconds())

    @tasks.loop(minutes=5)
    async def dump_cmd_stats(self):
        await self.cache.dump_cmd_stats()

    # pastebin

    async def mystbin(self, data):
        async with self.session.post("https://mystb.in/documents", data=data) as r:
            return f"https://mystb.in/{(await r.json())['key']}"

    async def hastebin(self, data):
        async with self.session.post("https://hastebin.com/documents", data=data) as r:
            return f"https://hastebin.com/{(await r.json())['key']}"

    # other

    def beta_command(self):
        async def predicate(ctx: CustomContext):
            if ctx.author.id != self.owner_id:
                await ctx.send(f"The `{ctx.command}` command is currently in beta. Only my owner can use it.")
                return False
            return True
        return commands.check(predicate)

    async def get_recent_commits(self, limit: int = 4):
        async with self.session.get(COMMITS_URL) as r:
            commits = await r.json()
        return commits[:limit]

    async def schemas(self):
        with open("schemas.sql") as f:
            await self.pool.execute(f.read())

    def get_all_subcommands(self, command):
        subcommands = []
        for cmd in command.commands:
            subcommands.append(str(cmd))
            subcommands.extend([f"{command} {alias}" for alias in cmd.aliases])
            if isinstance(cmd, commands.Group):
                subcommands.extend(self.get_all_subcommands(cmd))
        return subcommands

    def refresh_command_list(self):
        for command in self.commands:
            self.command_list.append(str(command))
            self.command_list.extend([alias for alias in command.aliases])
            if isinstance(command, commands.Group):
                self.command_list.extend(self.get_all_subcommands(command))

    async def close(self):
        await self.cache.dump_all()
        await super().close()

    def run(self, *args, **kwargs):
        for cog in self.coglist:
            self.load_extension(cog)

        self.loop.run_until_complete(self.schemas())
        self.loop.run_until_complete(self.cache.load_all())

        self.refresh_command_list()

        self.presence_update.start()
        self.dump_cmd_stats.start()
        self.clear_cmd_stats.start()
        super().run(*args, **kwargs)


class Cache:
    def __init__(self, bot: PB_Bot):
        self.bot = bot

        self.guild_cache = {}
        self.command_stats = {"top_commands_today": Counter(), "top_commands_overall": Counter(),
                              "top_users_today": Counter(), "top_users_overall": Counter()}
        self.blacklist = []
        self.todos = {}
        self.socketstats = Counter()

    async def load_all(self):
        await self.load_guild_info()
        await self.load_cmd_stats()
        await self.load_blacklist()      # todo add spam violation counter
        await self.load_todos()

    async def dump_all(self):
        await self.dump_guild_info()
        await self.dump_cmd_stats()
        await self.dump_todos()

    # guild info

    async def load_guild_info(self):
        data = await self.bot.pool.fetch("SELECT * FROM guild_info")
        for entry in data:
            self.guild_cache[entry["guild_id"]] = {k: v for k, v in list(entry.items())[1:]}  # skip the guild_id

    async def dump_guild_info(self):
        items = deepcopy(self.guild_cache).items()
        for guild_id, data in items:
            await self.bot.pool.execute("UPDATE guild_info SET prefixes = $1 WHERE guild_id = $2", data["prefixes"], guild_id)
            # idk how to make this dynamic

    async def create_guild_info(self, guild_id: int):
        await self.bot.pool.execute("INSERT INTO guild_info VALUES ($1)", guild_id)
        self.guild_cache[guild_id] = deepcopy(EMPTY_GUILD_CACHE)
        return self.guild_cache[guild_id]

    async def delete_guild_info(self, guild_id: int):
        await self.bot.pool.execute("DELETE FROM guild_info WHERE guild_id = $1", guild_id)
        self.guild_cache.pop(guild_id, None)

    async def get_guild_info(self, guild_id: int):
        return self.guild_cache.get(guild_id, None)

    async def cleanup_guild_info(self, guild_id: int):
        cache = await self.get_guild_info(guild_id)
        if cache == EMPTY_GUILD_CACHE:
            await self.delete_guild_info(guild_id)

    async def add_prefix(self, guild_id: int, prefix: str):
        await self.bot.pool.execute("UPDATE guild_info SET prefixes = array_append(prefixes, $1) WHERE guild_id = $2", prefix, guild_id)
        (await self.get_guild_info(guild_id))["prefixes"].append(prefix)

    async def remove_prefix(self, guild_id: int, prefix: str):
        await self.bot.pool.execute("UPDATE guild_info SET prefixes = array_remove(prefixes, $1) WHERE guild_id = $2", prefix, guild_id)
        (await self.get_guild_info(guild_id))["prefixes"].remove(prefix)

        await self.cleanup_guild_info(guild_id)

    async def clear_prefixes(self, guild_id: int):
        await self.bot.pool.execute("UPDATE guild_info SET prefixes = '{}' WHERE guild_id = $1", guild_id)
        (await self.get_guild_info(guild_id))["prefixes"].clear()

        await self.cleanup_guild_info(guild_id)

    # command stats

    async def load_cmd_stats(self):
        top_cmds_today = await self.bot.redis.hgetall("top_commands_today", encoding="utf-8")
        top_users_today = await self.bot.redis.hgetall("top_users_today", encoding="utf-8")
        top_cmds_overall = await self.bot.redis.hgetall("top_commands_overall", encoding="utf-8")
        top_users_overall = await self.bot.redis.hgetall("top_users_overall", encoding="utf-8")
        self.command_stats["top_commands_today"].update({k: int(v) for k, v in top_cmds_today.items()})
        self.command_stats["top_users_today"].update({k: int(v) for k, v in top_users_today.items()})
        self.command_stats["top_commands_overall"].update({k: int(v) for k, v in top_cmds_overall.items()})
        self.command_stats["top_users_overall"].update({k: int(v) for k, v in top_users_overall.items()})

    async def dump_cmd_stats(self):
        top_cmds_today = dict(self.command_stats["top_commands_today"])
        top_users_today = dict(self.command_stats["top_users_today"])
        top_cmds_overall = dict(self.command_stats["top_commands_overall"])
        top_users_overall = dict(self.command_stats["top_users_overall"])
        if top_cmds_today:  # will error if it's empty
            await self.bot.redis.hmset_dict("top_commands_today", top_cmds_today)
        if top_users_today:
            await self.bot.redis.hmset_dict("top_users_today", top_users_today)
        if top_cmds_overall:
            await self.bot.redis.hmset_dict("top_commands_overall", top_cmds_overall)
        if top_users_overall:
            await self.bot.redis.hmset_dict("top_users_overall", top_users_overall)

    async def clear_cmd_stats(self):
        # dump
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        cmds = json.dumps(dict(self.command_stats["top_commands_today"]))
        users = json.dumps(dict(self.command_stats["top_users_today"]))
        await self.bot.pool.execute("INSERT INTO command_stats VALUES ($1, $2, $3)", yesterday, cmds, users)

        # clear
        self.command_stats["top_commands_today"].clear()
        self.command_stats["top_users_today"].clear()

    # blacklist

    async def load_blacklist(self):
        self.blacklist = [entry["user_id"] for entry in await self.bot.pool.fetch("SELECT user_id FROM blacklisted_users")]

    # async def dump_blacklist(self):
    #     pass

    async def add_blacklist(self, user_id: int, *, reason: str):
        await self.bot.pool.execute("INSERT INTO blacklisted_users VALUES ($1, $2)", user_id, reason)
        self.blacklist.append(user_id)

    async def remove_blacklist(self, user_id: int):
        await self.bot.pool.execute("DELETE FROM blacklisted_users WHERE user_id = $1", user_id)
        self.blacklist.remove(user_id)

    async def is_blacklisted(self, user_id: int):
        return user_id in self.blacklist

    # todos

    async def load_todos(self):
        data = await self.bot.pool.fetch("SELECT * FROM todos")
        for entry in data:
            self.todos[entry["user_id"]] = entry["tasks"]

    async def dump_todos(self):
        items = deepcopy(self.todos).items()
        for user_id, tasks_ in items:
            await self.bot.pool.execute("UPDATE todos SET tasks = $1 WHERE user_id = $2", tasks_, user_id)

    async def create_todo(self, user_id: int):
        await self.bot.pool.execute("INSERT INTO todos VALUES ($1)", user_id)
        self.todos[user_id] = []
        return self.todos[user_id]

    async def delete_todo(self, user_id: int):
        await self.bot.pool.execute("DELETE FROM todos WHERE user_id = $1", user_id)
        self.todos.pop(user_id)

    async def get_todo(self, user_id: int):
        return self.todos.get(user_id, None)

    async def cleanup_todo(self, user_id: int):
        todo = await self.get_todo(user_id)
        if not todo:
            await self.delete_todo(user_id)

    async def add_todo(self, user_id: int, task: str):
        await self.bot.pool.execute("UPDATE todos SET tasks = array_append(tasks, $1) WHERE user_id = $2", task, user_id)
        (await self.get_todo(user_id)).append(task)

    async def remove_todo(self, user_id: int, task: str):
        await self.bot.pool.execute("UPDATE todos SET tasks = array_remove(tasks, $1) WHERE user_id = $2", task, user_id)
        (await self.get_todo(user_id)).remove(task)

        await self.cleanup_todo(user_id)

    async def clear_todos(self, user_id: int):
        await self.bot.pool.execute("UPDATE todos SET tasks = '{}' WHERE user_id = $1", user_id)
        (await self.get_todo(user_id)).clear()

        await self.cleanup_todo(user_id)


class CustomContext(commands.Context):
    """
    Custom context class.
    """
    bot: PB_Bot
    player: typing.Any

    @property
    def clean_prefix(self):
        prefix = re.sub(f"<@!?{self.bot.user.id}>", "@PB Bot", self.prefix)
        if prefix.endswith("  "):
            prefix = f"{prefix.strip()} "
        return prefix

    async def send(self, content=None, **kwargs):
        if "reply" in kwargs and not kwargs.pop("reply"):
            return await super().send(content, **kwargs)
        try:
            return await self.reply(content, **kwargs, mention_author=False)
        except discord.HTTPException:
            return await super().send(content, **kwargs)

    async def quote(self, content=None, **kwargs):
        if content is None:
            content = ""
        mention_author = kwargs.get("mention_author", "")
        if mention_author:
            mention_author = f"{self.author.mention} "
        quote = "\n".join(f"> {string}" for string in self.message.content.split("\n"))
        quote_msg = f"{quote}\n{mention_author}{content}"
        return await super().send(quote_msg, **kwargs)

    async def cache(self):
        return await self.bot.cache.get_guild_info(self.guild.id)


class StopSpammingMe(commands.CheckFailure):
    pass
