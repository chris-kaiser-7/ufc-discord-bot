from discord.ext import commands
from utils import subscribed_channels

class Subscription(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='sub')
    async def subscribe(self, ctx):
        channel_id = ctx.channel.id
        subscribed_channels[channel_id] = True
        await ctx.send('This channel has been subscribed to receive UFC event updates.')

    @commands.command(name='unsub')
    async def unsubscribe(self, ctx):
        channel_id = ctx.channel.id
        if channel_id in subscribed_channels:
            del subscribed_channels[channel_id]
        await ctx.send('This channel has been unsubscribed from receiving UFC event updates.')