import discord
from discord.ext import commands
from decouple import config
import asyncio
from commands import parlay, subscription, money, card  # Import command modules
from commands.parlay import watch_fight_status
from commands.card import monitor_fights

# Initialize bot and database
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    # Load commands
    await bot.add_cog(parlay.Parlay(bot))
    await bot.add_cog(subscription.Subscription(bot))
    await bot.add_cog(money.Money(bot))
    await bot.add_cog(card.Card(bot))
    bot.loop.create_task(watch_fight_status(bot))
    coro = asyncio.to_thread(monitor_fights, bot)
    asyncio.create_task(coro)


bot.run(config('DISC_TOKEN'))