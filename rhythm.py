import asyncio
import discord
import yt_dlp
from discord.ext import commands
import asyncio
import random

yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile' : 'YOUR_COOKIE_FILE'
}

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10",
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.thumbnail = data.get('thumbnail')
        self.webpage = data.get('webpage_url')
        self.duration = data.get('duration')
        self.uploader = data.get('uploader')
        self.parsedDuration = self.parse_duration(data.get('duration'))

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    async def from_playlist(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            list = []
            for i in data['entries']:
                filename = i['url'] if stream else ytdl.prepare_filename(i)
                player = cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=i)
                list.append(player)
            return list
        else:
            filename = data['url'] if stream else ytdl.prepare_filename(data)
            return [cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)]

    @classmethod
    def new_video(cls, url, stream=False):
        data = ytdl.extract_info(url, download=not stream)
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @staticmethod
    def parse_duration(duration: int):
        if not duration is None:
            minutes, seconds = divmod(duration, 60)
            hours, minutes = divmod(minutes, 60)
            days, hours = divmod(hours, 24)
            duration = []
            if days > 0:
                duration.append(f'{days} 日')
            if hours > 0:
                duration.append(f'{hours} 時間')
            if minutes > 0:
                duration.append(f'{minutes} 分')
            if seconds > 0:
                duration.append(f'{seconds} 秒')
            return '再生時間： ' + ' '.join(duration)
        else:
            return "再生時間： ライブ"

class VideoInfo:
    def __init__(self, ctx, player: YTDLSource, searchWords):
        self.title = player.title
        self.url = player.webpage
        self.thumbnail = player.thumbnail
        self.ctx = ctx
        self.player = player
        self.searchWords = searchWords
        self.duration = player.duration
        self.uploader = player.uploader
        self.parsedDuration = player.parsedDuration
        self.requester = ctx.author.display_name

    def updatePlayer(self):
        self.player = YTDLSource.new_video(self.url, stream=True)

class Queue:
    def __init__(self):
        self.queue = []

    def isEmpty(self):
        if len(self.queue) == 0:
            return True
        else:
            return False

    def size(self):
        return len(self.queue)
    
    def show(self):
        if self.size() > 0:
            n = 1
            text = "`予約一覧\n"
            for i in self.queue:
                text += str(n) + ". " + i.title + "\n"
                n += 1
            text += "`"
            return text
        else:
            return "予約はありません。"

    def enqueue(self, video):
        self.queue.append(video)

    def dequeue(self):
        if self.isEmpty():
            return None
        else:
            a = self.queue.pop(0)
            return a

    def getFirst(self):
        return self.queue[0]

    def setFirst(self, video):
        self.queue.insert(0, video)

    def delete(self,n: int):
        if self.isEmpty():
            return False
        elif n < 1 or n > self.size():
            #print("無効な数値です。")
            return False
        else:
            a = self.queue.pop(n-1)
            return True

    def clear(self):
        self.queue.clear()

    def shuffle(self):
        random.shuffle(self.queue)

bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"))

class View(discord.ui.View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
    
    @discord.ui.button(label="停止/再生", style=discord.ButtonStyle.primary, emoji="\u23F8\uFE0F")
    async def button_callback1(self, button, interaction):
        await Music.pause(self.ctx)
    @discord.ui.button(label="スキップ", style=discord.ButtonStyle.red, emoji="\u23ED\uFE0F")
    async def button_callback2(self, button, interaction):
        await Music.fs(self.ctx)
    @discord.ui.button(label="ループ", style=discord.ButtonStyle.green, emoji="\U0001f502")
    async def button_callback3(self, button, interaction):
        await Music.loop(self.ctx)
    
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dic = {}

    def getQueue(self, guild):
        return self.dic[guild]['queue']

    def getLoop(self, guild):
        return self.dic[guild]['loop']

    def setLoop(self, guild):
        if self.getLoop(guild):
            self.dic[guild]['loop'] = False
            return False
        else:
            self.dic[guild]['loop'] = True
            return True

    def getNowPlaying(self, guild):
        return self.dic[guild]['nowplaying']

    def setNowPlaying(self, guild, video):
        self.dic[guild]['nowplaying'] = video

    def AudioPlayer(self, ctx: commands.Context):
        queue = self.getQueue(ctx.guild.id)

        if self.getLoop(ctx.guild.id) and not self.getNowPlaying(ctx.guild.id) is None:
            video = self.getNowPlaying(ctx.guild.id)
            video.updatePlayer()
            self.getQueue(ctx.guild.id).setFirst(video)

        nextVideo: YTDLSource = queue.dequeue()

        if not nextVideo is None and not ctx.voice_client is None:
            ctx.voice_client.play(nextVideo.player, after=lambda e: self.AudioPlayer(ctx))
            ctx.voice_client.source.volume = 30 / 100
            embed = discord.Embed(title=nextVideo.title,description=nextVideo.parsedDuration+"　予約者： "+nextVideo.requester+"\nチャンネル： "+nextVideo.uploader+"\n"+nextVideo.url,color=0x2e76f6)
            embed.set_thumbnail(url=nextVideo.thumbnail)
            duration = 300 if nextVideo.duration == None or nextVideo.duration > 300 else nextVideo.duration
            asyncio._set_running_loop(self.bot.loop)
            self.bot.loop.create_task(ctx.send(embed=embed, view=View(ctx), delete_after = duration))
            #print(f'\n再生中： {nextVideo.title}')
            self.setNowPlaying(ctx.guild.id, nextVideo)
        else:
            self.setNowPlaying(ctx.guild.id, None)

    @commands.command()
    async def p(self, ctx, *, url):
        async with ctx.typing():
            if "https://youtube.com/playlist?list=" == url[:34]:
                players = await YTDLSource.from_playlist(url, loop=self.bot.loop, stream=True)
                for i in players:
                    newVideo = VideoInfo(ctx=ctx, player=i, searchWords=url)
                    self.getQueue(ctx.guild.id).enqueue(newVideo)
                if ctx.voice_client.is_playing():
                    await ctx.send(f'`再生リストを予約しました。`', delete_after = 60)
                    #print(f'\n再生リストを予約しました。')
                else:
                    self.AudioPlayer(ctx)
            else:
                player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                newVideo = VideoInfo(ctx=ctx, player=player, searchWords=url)
                self.getQueue(ctx.guild.id).enqueue(newVideo)
            
                if ctx.voice_client.is_playing():
                    await ctx.send(f'`予約： {player.title}`', delete_after = 60)
                    #print(f'\n予約： {player.title}')
                else:
                    self.AudioPlayer(ctx)
                
    @commands.command()
    async def v(self, ctx, volume: int):
        if ctx.voice_client is None:
            return await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            if 0 <= volume <= 100:
                ctx.voice_client.source.volume = volume / 100
                await ctx.send(f"音量を{volume}%に調整しました。", delete_after = 30)
            else:
                await ctx.send(f"無効な数値です。", delete_after = 30)

    @commands.command()
    async def np(self, ctx):
        if ctx.voice_client is None:
            await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            np: VideoInfo = self.getNowPlaying(ctx.guild.id)
            if not np is None:
                embed = discord.Embed(title=np.title,description=np.parsedDuration+"　予約者： "+np.requester+"\nチャンネル： "+np.uploader+"\n"+np.url,color=0x2e76f6)
                embed.set_thumbnail(url=np.thumbnail)
                await ctx.send(embed=embed, view=View(ctx), delete_after = 30)
            else:
                await ctx.send("現在再生中の音楽はありません。", delete_after = 30)

    @commands.command()
    async def loop(self, ctx):
        if ctx.voice_client is None:
            await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            lp = self.setLoop(ctx.guild.id)
            if lp:
                await ctx.send("ループ再生ON", delete_after = 60)
            else:
                await ctx.send("ループ再生OFF", delete_after = 30)

    @commands.command()
    async def d(self, ctx, num: int):
        if ctx.voice_client is None:
            await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            queue = self.getQueue(ctx.guild.id)
            if queue.delete(num):
                await ctx.send(str(num) + "番目の予約を削除しました。", delete_after = 30)
            else:
                await ctx.send("予約の削除に失敗しました。", delete_after = 30)

    @commands.command()
    async def clear(self, ctx):
        if ctx.voice_client is None:
            await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            queue = self.getQueue(ctx.guild.id)
            queue.clear()
            await ctx.send("予約をすべて削除しました。", delete_after = 30)

    @commands.command()
    async def sh(self, ctx):
        if ctx.voice_client is None:
            await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            queue = self.getQueue(ctx.guild.id)
            queue.shuffle()
            await ctx.send("予約をシャッフルしました。", delete_after = 30)

    @commands.command()
    async def list(self, ctx):
        if ctx.voice_client is None:
            await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            queue = self.getQueue(ctx.guild.id)
            text = queue.show()
            await ctx.send(text, delete_after = 30)

    @commands.command()
    async def dc(self, ctx):
        if ctx.voice_client is None:
            await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            await ctx.voice_client.disconnect()
            await ctx.send("ボイスチャンネルから切断されました。", delete_after = 30)
            await asyncio.sleep(3)
            del self.dic[ctx.guild.id]

    @commands.command()
    async def fs(self, ctx):
        if ctx.voice_client is None:
            return await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                ctx.voice_client.stop()
                self.setNowPlaying(ctx.guild.id, None)
                await ctx.send('スキップしました。', delete_after = 30)
            else:
                pass
        
    @commands.command()
    async def pause(self, ctx):
        if ctx.voice_client is None:
            return await ctx.send("ボイスチャンネルに接続されていません。", delete_after = 30)
        else:
            if ctx.voice_client.is_playing():
                ctx.voice_client.pause()
                await ctx.send('再生を一時停止しました。', delete_after = 30)
            elif ctx.voice_client.is_paused():
                ctx.voice_client.resume()
                await ctx.send('再生を再開しました。', delete_after = 30)
            else:
                await ctx.send("現在再生中の音楽はありません。", delete_after = 30)

    @p.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
                self.dic[ctx.guild.id] = {}
                self.dic[ctx.guild.id]['queue'] = Queue()
                self.dic[ctx.guild.id]['loop'] = False
                self.dic[ctx.guild.id]['nowplaying'] = None

            else:
                await ctx.send("ボイスチャンネルに参加してください。", delete_after = 30)
                raise commands.CommandError("コマンドの送信者がボイスチャンネルに参加していません。")
        elif ctx.voice_client.is_playing():
            pass
            
@bot.event
async def on_ready():
    print(f'\n{bot.user} としてログインしました。 (ID: {bot.user.id})')
    print('-------------')

bot.add_cog(Music(bot))
bot.run('YOUR_TOKEN')
