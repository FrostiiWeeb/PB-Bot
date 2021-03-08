import discord
import wavelink
import humanize
import datetime
import random

from discord.ext import commands, menus
from contextlib import suppress
from typing import Union

from utils import utils
from utils.classes import PB_Bot, CustomContext
from config import config

DEFAULT_VOLUME = 40
QUEUE_LIMIT = 100


class Track(wavelink.Track):
    """
    Custom track object with a requester attribute.
    """
    __slots__ = ("requester",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args)

        self.requester = kwargs.get("requester")


class Player(wavelink.Player):
    """
    Custom player class.
    """
    bot: PB_Bot

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.now_playing = None
        self.session_started = False
        self.session_chan = None
        self.is_locked = False
        self.dj = None

        self.repeat = False
        self.loop = False

        self.queue = []
        self.menus = []
        self.volume = DEFAULT_VOLUME
        self.queue_position = 0

    async def start(self, ctx: CustomContext, song: Union[wavelink.TrackPlaylist, list]):
        # connect to voice
        try:
            voice_channel = ctx.author.voice.channel
        except AttributeError:
            return await ctx.send("Couldn't find a channel to join. Please join one.")
        await self.connect(voice_channel.id)

        # add the first song
        if isinstance(song, wavelink.TrackPlaylist):
            for track in song.tracks:
                track = Track(track.id, track.info, requester=ctx.author)
                self.queue.append(track)
            now_playing = song.tracks[0]
        else:
            track = Track(song[0].id, song[0].info, requester=ctx.author)
            self.queue.append(track)
            now_playing = track

        # embed
        duration = datetime.timedelta(milliseconds=now_playing.length)

        embed = discord.Embed(
            title=f"Music Session started in `{voice_channel.name}`",
            description=f"**Now Playing:** {now_playing}\n"
                        f"**DJ:** {ctx.author}\n"
                        f"**Duration:** {humanize.precisedelta(duration)}\n"
                        f"**Volume:** `{self.volume}`\n"
                        f"**YT Link:** [Click Here!]({now_playing.uri})\n",
            timestamp=datetime.datetime.now(),
            colour=ctx.bot.embed_colour)
        await ctx.send(embed=embed)

        # start playing
        self.queue_position += 1
        await self.play(now_playing)

        # finalise
        self.session_chan = ctx.channel
        self.dj = ctx.author.id
        self.session_started = True

    async def do_next(self):
        with suppress((discord.Forbidden, discord.HTTPException, AttributeError)):
            await self.now_playing.delete()

        if self.repeat:
            self.queue_position -= 1

        try:
            song = self.queue[self.queue_position]
        except IndexError:  # There are no more songs in the queue.
            if self.loop:
                self.queue_position = 0
                song = self.queue[self.queue_position]
            else:
                await self.destroy()
                return

        self.queue_position += 1

        embed = discord.Embed(title="Now Playing:", description=f"{song}", colour=self.bot.embed_colour)
        embed.set_footer(text=f"Requested by {song.requester}")
        self.now_playing = await self.session_chan.send(embed=embed)
        await self.play(song)

    async def do_previous(self):
        self.queue_position -= 2
        await self.stop()

    async def destroy(self):
        with suppress((discord.Forbidden, discord.HTTPException, AttributeError)):
            await self.now_playing.delete()

        menus_ = self.menus.copy()
        for menu in menus_:
            menu.stop()

        await super().destroy()


# def dj_check():
#     async def predicate(ctx):
#         if ctx.controller.current_dj is None:  # no dj yet
#             ctx.controller.current_dj = ctx.author
#             return True
#         if ctx.controller.current_dj == ctx.author:
#             return True
#         await ctx.send(f"Only the current DJ ({ctx.controller.current_dj}) can control the current guild's player.")
#         return False
#     return commands.check(predicate)


def is_playing():
    async def predicate(ctx: CustomContext):
        if not ctx.player.is_playing:
            await ctx.send("I am not currently playing anything.")
            return False
        return True
    return commands.check(predicate)


def is_privileged():
    async def predicate(ctx: CustomContext):
        if not ctx.player.is_locked or not ctx.player.dj:
            return True
        if ctx.author.id != ctx.player.dj and not ctx.author.guild_permissions.administrator:
            await ctx.send("Only admins and the DJ can use this command.")
            return False
        return True
    return commands.check(predicate)


def has_to_be_privileged_even_if_not_locked():
    async def predicate(ctx: CustomContext):
        if not ctx.player.dj:
            return True
        if ctx.author.id != ctx.player.dj and not ctx.author.guild_permissions.administrator:
            await ctx.send("Only admins and the DJ can use this command.")
            return False
        return True
    return commands.check(predicate)


# Controls:

# skip/previous
# play/pause
# volume up/down
# songqueue add/remove
# fastforward
# rewind


class Music(commands.Cog):
    """
    Music commands.
    """
    def __init__(self, bot: PB_Bot):
        CustomContext.player = property(lambda ctx: bot.wavelink.get_player(ctx.guild.id, cls=Player))
        self.bot = bot
        bot.loop.create_task(self.start_nodes())

    async def cog_check(self, ctx: CustomContext):
        if not ctx.guild:
            raise commands.NoPrivateMessage
        if not ctx.bot.wavelink.nodes:
            await ctx.send("Music commands aren't ready yet. Try again in a bit.")
            return False
        if not ctx.player.is_connected:  # anyone can use commands if the bot isn't connected to a voice channel
            return True
        if not ctx.author.voice:  # not in a voice channel
            await ctx.send("You must be in a voice channel to use this command.")
            return False
        if ctx.author.voice.channel.id != ctx.player.channel_id:  # in a voice channel, but not in the same one as the bot
            await ctx.send("You must be in the same voice channel as me to use this command.")
            return False
        return True

    async def start_nodes(self):
        await self.bot.wait_until_ready()

        if self.bot.wavelink.nodes:
            previous_nodes = self.bot.wavelink.nodes.copy()
            for node in previous_nodes.values():
                await node.destroy()

        node = await self.bot.wavelink.initiate_node(**config["wavelink_node"])
        node.set_hook(self.on_node_event)

    async def on_node_event(self, event):
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            await event.player.do_next()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel and not after.channel:  # the member was in a vc and the member left the vc
            player = self.bot.wavelink.get_player(member.guild.id, cls=Player)
            if member.id == player.dj:
                player.dj = None

    @commands.command()
    async def connect(self, ctx: CustomContext, *, voice_channel: discord.VoiceChannel = None):
        """
        Connects the bot to a voice channel.

        `voice_channel` - The voice channel to connect to. If no voice channel is provided, the bot will try to connect to the voice channel the user is currently in.
        """
        if not voice_channel:
            try:
                voice_channel = ctx.author.voice.channel
            except AttributeError:
                return await ctx.send("Couldn't find a channel to join. Please specify a valid channel or join one.")
        await ctx.player.connect(voice_channel.id)
        await ctx.send(f"Connected to **`{voice_channel.name}`**.")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def player(self, ctx: CustomContext):
        """
        Opens up the player menu.
        """
        await utils.PlayerMenu(delete_message_after=True).start(ctx)

    @is_playing()
    @has_to_be_privileged_even_if_not_locked()
    @commands.command()
    async def djlock(self, ctx: CustomContext):
        """
        Locks or unlocks the player.
        """
        if ctx.player.is_locked:
            ctx.player.is_locked = False
            return await ctx.send("Unlocked music. Anyone can control the player.")
        ctx.player.is_locked = True
        await ctx.send("Locked music. Only admins and the DJ can control the player.")

    @is_playing()
    @has_to_be_privileged_even_if_not_locked()
    @commands.command()
    async def swapdj(self, ctx: CustomContext, member: discord.Member):
        """
        Swaps the DJ to someone else in the voice channel.

        `member` - The member.
        """
        if member.bot:
            return await ctx.send("You cannot swap the DJ to a bot.")
        if member.id == ctx.player.dj:
            return await ctx.send("This person is already the DJ.")
        if not member.voice:
            return await ctx.send("This person isn't in a voice channel.")
        if member.voice.channel.id != ctx.player.channel_id:
            return await ctx.send("This person isn't in the same voice channel as me.")

        ctx.player.dj = member.id
        await ctx.send(f"{member.mention} is now the DJ.")

    @commands.group(invoke_without_command=True, aliases=["sq"])
    async def songqueue(self, ctx: CustomContext, limit: int = None):
        """
        View the songqueue.

        `limit` - The amount of songs to get from the queue. Fetches all songs if this is not provided.
        """
        if limit is None:
            source = [(number, track) for number, track in enumerate(ctx.player.queue, start=1)]
        else:
            source = [(number, track) for number, track in enumerate(ctx.player.queue[:limit], start=1)]
        await menus.MenuPages(utils.QueueSource(source, ctx.player)).start(ctx)

    @is_privileged()
    @songqueue.command()
    async def add(self, ctx: CustomContext, *, query: str):
        """
        Alias to `play`.
        """
        await ctx.invoke(ctx.bot.get_command("play"), query=query)

    @is_privileged()
    @songqueue.command()
    async def remove(self, ctx: CustomContext, *, query: str):
        """
        Removes a song from the queue.

        `query` - The song to remove from the queue.
        """
        query_results = await ctx.bot.wavelink.get_tracks(f"ytsearch:{query}")
        if not query_results:
            return await ctx.send(f"Could not find any songs with that query.")
        track = Track(query_results[0].id, query_results[0].info, requester=ctx.author)
        for track_, position in enumerate(ctx.player.queue):
            if str(track_) == str(track):
                ctx.player.queue.remove(track_)
                if position < ctx.player.queue_position:
                    ctx.player.queue_position -= 1
        await ctx.send(f"Removed all songs with the name `{track}` from the queue. Queue length: `{len(ctx.player.queue)}`")

    @is_privileged()
    @commands.command()
    async def play(self, ctx: CustomContext, *, query: str):
        """
        Adds a song to the queue.

        `query` - The song to add to the queue.
        """
        if len(ctx.player.queue) >= QUEUE_LIMIT:
            return await ctx.send(f"Sorry, only `{QUEUE_LIMIT}` songs can be in the queue at a time.")

        query_results = await ctx.bot.wavelink.get_tracks(f"ytsearch:{query}")
        if not query_results:
            return await ctx.send(f"Could not find any songs with that query.")

        if not ctx.player.session_started:
            return await ctx.player.start(ctx, query_results)

        if isinstance(query_results, wavelink.TrackPlaylist):
            for track in query_results.tracks:
                track = Track(track.id, track.info, requester=ctx.author)
                ctx.player.queue.append(track)
            playlist_name = query_results.data['playlistInfo']['name']
            await ctx.send(f"Added playlist `{playlist_name}` with `{len(query_results.tracks)}` songs to the queue. "
                           f"Queue length: `{len(ctx.player.queue)}`")
        else:
            track = Track(query_results[0].id, query_results[0].info, requester=ctx.author)
            ctx.player.queue.append(track)
            await ctx.send(f"Added `{track}` to the queue. Queue length: `{len(ctx.player.queue)}`")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def resume(self, ctx: CustomContext):
        """
        Resumes the player.
        """
        if not ctx.player.is_paused:
            return await ctx.send("I am already playing!")
        await ctx.player.set_pause(False)
        await ctx.send("Resuming...")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def pause(self, ctx: CustomContext):
        """
        Pauses the player.
        """
        if ctx.player.is_paused:
            return await ctx.send("I am already paused!")
        await ctx.player.set_pause(True)
        await ctx.send("Paused the player.")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def skip(self, ctx: CustomContext):
        """
        Skips the currently playing song.
        """
        await ctx.player.stop()
        await ctx.message.add_reaction("✅")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def previous(self, ctx: CustomContext):
        """
        Stops the currently playing song and plays the previous one.
        """
        await ctx.player.do_previous()
        await ctx.message.add_reaction("✅")

    @is_privileged()
    @commands.command()
    async def volume(self, ctx: CustomContext, volume: int = None):
        """
        Adjusts the players volume.

        `volume` - The new volume.
        """
        if volume is None:
            return await utils.VolumeMenu(delete_message_after=True).start(ctx)
        volume = max(min(volume, 1000), 0)
        await ctx.player.set_volume(volume)
        await ctx.send(f"Set the volume to `{volume}`.")

    @is_playing()
    @is_privileged()
    @commands.command(aliases=["eq", "setequalizer", "seteq"])
    async def equalizer(self, ctx: CustomContext, *, equalizer: str):
        """
        Change the players equalizer.

        `equalizer` - The new equalizer. Available equalizers:

        `flat` - Resets the equalizer to flat.
        `boost` - Boost equalizer. This equalizer emphasizes punchy bass and crisp mid-high tones. Not suitable for tracks with deep/low bass.
        `metal` - Experimental metal/rock equalizer. Expect clipping on bassy songs.
        `piano` - Piano equalizer. Suitable for piano tracks, or tacks with an emphasis on female vocals. Could also be used as a bass cutoff.
        **Source:** https://wavelink.readthedocs.io/en/latest/wavelink.html#equalizer
        """
        equalizers = {
            "flat": wavelink.Equalizer.flat(),
            "boost": wavelink.Equalizer.boost(),
            "metal": wavelink.Equalizer.metal(),
            "piano": wavelink.Equalizer.piano()
        }
        equalizer = equalizer.lower()
        try:
            eq = equalizers[equalizer]
        except KeyError:
            eqs = "\n".join(equalizers)
            return await ctx.send(f"Invalid equalizer provided. Available equalizers:\n\n{eqs}")
        await ctx.player.set_eq(eq)
        await ctx.send(f"Set the equalizer to `{equalizer}`.")

    @is_playing()
    @is_privileged()
    @commands.command(aliases=["mix"])
    async def shuffle(self, ctx):
        """
        Shuffles the queue.
        """
        random.shuffle(ctx.player.queue)
        with suppress(discord.HTTPException):
            await ctx.message.add_reaction("✅")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def repeat(self, ctx):
        """
        Repeats the current song when finished.
        """
        if ctx.player.repeat:
            ctx.player.repeat = False
            return await ctx.send("Repeat is now set to OFF.")
        ctx.player.repeat = True
        await ctx.send("Repeat is now set to ON.")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def loop(self, ctx):
        """
        Loops the queue.
        """
        if ctx.player.loop:
            ctx.player.loop = False
            return await ctx.send("Stopped looping the queue.")
        ctx.player.loop = True
        await ctx.send("Started looping the queue.")

    @is_playing()
    @is_privileged()
    @commands.command(aliases=["fastfwd"])
    async def fastforward(self, ctx: CustomContext, seconds: int):
        """
        Fast forward `x` seconds into the current song.

        `seconds` - The amount of seconds to fast forward.
        """
        seek_position = ctx.player.position + (seconds * 1000)
        await ctx.player.seek(seek_position)
        await ctx.send(f"Fast forwarded `{seconds}` seconds. Current position: `{humanize.precisedelta(datetime.timedelta(milliseconds=seek_position))}`")

    @is_playing()
    @is_privileged()
    @commands.command()
    async def rewind(self, ctx: CustomContext, seconds: int):
        """
        Rewind `n` seconds.

        `seconds` - The amount of seconds to rewind.
        """
        seek_position = ctx.player.position - (seconds * 1000)
        await ctx.player.seek(seek_position)
        await ctx.send(f"Rewinded `{seconds}` seconds. Current position: `{humanize.precisedelta(datetime.timedelta(milliseconds=seek_position))}`")

    @is_privileged()
    @commands.command(aliases=["dc"])
    async def disconnect(self, ctx: CustomContext):
        """
        Disconnects the bot from the voice channel and stops the player.
        """
        channel = ctx.guild.get_channel(ctx.player.channel_id)
        await ctx.player.destroy()
        await ctx.send(f"Disconnected from **`{channel}`**.")


def setup(bot):
    bot.add_cog(Music(bot))
