import discord
from discord.ext import commands
from database import WhoWillWin_db, UFCodds_db
from utils import subscribed_channels, fight_status_map
from PIL import Image
from io import BytesIO
import requests
import asyncio

class Card(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='show_card')
    async def show_card(self, ctx, type='all'):
        channel_id = ctx.channel.id
        if channel_id not in subscribed_channels:
            await ctx.send('This channel is not subscribed to receive UFC event updates.')
            return

        # Get all unique fighthashes from ufc_status
        if type == 'all':
            fighthashes = WhoWillWin_db['ufc_status'].distinct('fighthash')
        else:
            fighthashes = WhoWillWin_db['ufc_status'].distinct('fighthash', {'card': type})

        for fighthash in fighthashes:
            embed, file = get_fight_embed_by_fighthash(fighthash)
            await ctx.send(embed=embed, file=file)


    @commands.command(name='show_fight')
    async def show_fight(self, ctx, type='current'):
        channel_id = ctx.channel.id
        if channel_id not in subscribed_channels:
            await ctx.send('This channel is not subscribed to receive UFC event updates.')
            return

        current_fight = WhoWillWin_db['ufc_status'].find_one({'fight_status': 0}) 
        if not current_fight:
            await ctx.send('There is no current fight.')
            return
            
        # Show either the current or next fight depending on type argument
        if type == 'current':
            fighthash = current_fight['fighthash']
        else:
            next_fight = WhoWillWin_db['ufc_status'].find_one({
                'event': current_fight['event'],
                'slot': current_fight['slot'] - 1 
            })
            if not next_fight:
                await ctx.send('There is no next fight available for the current event.')
                return
            fighthash = next_fight['fighthash']
            
        embed, file = get_fight_embed_by_fighthash(fighthash)
        await ctx.send(embed=embed, file=file)


def get_fight_embed_by_fighthash(fighthash):
    ufc_status_doc = WhoWillWin_db['ufc_status'].find_one({'fighthash': fighthash})
    draftkings_doc = UFCodds_db['draftkings'].find_one({'fighthash': fighthash})

    fighter_name_1 = ufc_status_doc['fighter_name_1']
    fighter_name_2 = ufc_status_doc['fighter_name_2']
    fight_status = fight_status_map[ufc_status_doc['fight_status']].format(fighter_name_1 if ufc_status_doc['fight_status'] == 1 else fighter_name_2)

    if draftkings_doc:
        odds_percent1 = draftkings_doc['odds_percent1']
        odds_percent2 = draftkings_doc['odds_percent2']
    else:
        print(f"No matching fighthash found for {fighter_name_1} vs {fighter_name_2}")
        return (None, None)

    red_image_src = ufc_status_doc.get('red_image_src')  # Use get method to avoid KeyError
    blue_image_src = ufc_status_doc.get('blue_image_src')

    if red_image_src and blue_image_src:
        red_image_response = requests.get(red_image_src)
        blue_image_response = requests.get(blue_image_src)

        red_image = Image.open(BytesIO(red_image_response.content)).convert('RGBA')
        blue_image = Image.open(BytesIO(blue_image_response.content)).convert('RGBA')

        combined_image_width = red_image.width + blue_image.width
        combined_image_height = max(red_image.height, blue_image.height)

        combined_image = Image.new('RGBA', (combined_image_width, combined_image_height), (255, 255, 255, 0))
        combined_image.paste(red_image, (0, 0), mask=red_image)
        combined_image.paste(blue_image, (red_image.width, 0), mask=blue_image)

        with BytesIO() as image_binary:
            combined_image.save(image_binary, 'PNG')
            image_binary.seek(0)

            file = discord.File(fp=image_binary, filename='combined_image.png')

            embed = discord.Embed(title='UFC Event Update', description=f'Fighters: {fighter_name_1} vs {fighter_name_2}')
            embed.add_field(name='Fight Status', value=fight_status)
            embed.add_field(name='Odds', value=f'{fighter_name_1}: {odds_percent1}%\n{fighter_name_2}: {odds_percent2}%')
            embed.set_image(url='attachment://combined_image.png')

            return (embed, file)
    elif red_image_src:
        red_image_response = requests.get(red_image_src)
        red_image = Image.open(BytesIO(red_image_response.content)).convert('RGBA')

        with BytesIO() as image_binary:
            red_image.save(image_binary, 'PNG')
            image_binary.seek(0)

            file = discord.File(fp=image_binary, filename='red_image.png')

            embed = discord.Embed(title='UFC Event Update', description=f'Fighters: {fighter_name_1} vs {fighter_name_2}')
            embed.add_field(name='Fight Status', value=fight_status)
            embed.add_field(name='Odds', value=f'{fighter_name_1}: {odds_percent1}%\n{fighter_name_2}: {odds_percent2}%')
            embed.set_image(url='attachment://red_image.png')

            return (embed, file)
    elif blue_image_src:
        blue_image_response = requests.get(blue_image_src)
        blue_image = Image.open(BytesIO(blue_image_response.content)).convert('RGBA')

        with BytesIO() as image_binary:
            blue_image.save(image_binary, 'PNG')
            image_binary.seek(0)

            file = discord.File(fp=image_binary, filename='blue_image.png')

            embed = discord.Embed(title='UFC Event Update', description=f'Fighters: {fighter_name_1} vs {fighter_name_2}')
            embed.add_field(name='Fight Status', value=fight_status)
            embed.add_field(name='Odds', value=f'{fighter_name_1}: {odds_percent1}%\n{fighter_name_2}: {odds_percent2}%')
            embed.set_image(url='attachment://blue_image.png')

            return (embed, file)
    else:
        embed = discord.Embed(title='UFC Event Update', description=f'Fighters: {fighter_name_1} vs {fighter_name_2}')
        embed.add_field(name='Fight Status', value=fight_status)
        embed.add_field(name='Odds', value=f'{fighter_name_1}: {odds_percent1}%\n{fighter_name_2}: {odds_percent2}%')

        return (embed, None)

def monitor_fights(bot):
    # Create a change stream to watch for changes to the ufc_status collection
    ufc_status = WhoWillWin_db['ufc_status']
    change_stream = ufc_status.watch()
    
    for change in change_stream:
        # Check if the change is an update
        if change["operationType"] == "update":
            # Get the updated document
            change_key = change['documentKey'] #['_id']
            field_changes = change['updateDescription']['updatedFields']
            if 'fight_status' in field_changes and field_changes['fight_status'] != 0 :
                change_doc = ufc_status.find_one(change_key)
                # Get next fight
                next_fight = ufc_status.find_one({"event": change_doc["event"], "slot": change_doc["slot"] - 1})
                
                # Check if next fight exists
                if next_fight:
                    # Create embeds for fighters
                    embed, file = get_fight_embed_by_fighthash(next_fight["fighthash"])

                    # Post embeds to subscribed channels
                    for channel_id in subscribed_channels:
                        channel = bot.get_channel(channel_id)
                        asyncio.run_coroutine_threadsafe(channel.send(embed=embed, file=file), bot.loop)