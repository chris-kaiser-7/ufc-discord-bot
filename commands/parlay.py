from discord.ext import commands
from database import WhoWillWin_db, UFCodds_db
from utils import parlay_fighter_map, subscribed_channels, fight_status_map
import asyncio


class Parlay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='start')
    async def start(self, ctx, type='all'):
        channel_id = ctx.channel.id
        if channel_id not in subscribed_channels:
            await ctx.send('This channel is not subscribed to receive UFC event updates.')
            return

        ufc_status = WhoWillWin_db['ufc_status']
        draftkings = UFCodds_db['draftkings']

        # Reset the parlay fighter map
        parlay_fighter_map.clear()

        # Get all unique fighthashes from ufc_status
        if type == 'all':
            fighthashes = ufc_status.distinct('fighthash')
        else:
            fighthashes = ufc_status.distinct('fighthash', {'card': type})

        parlay_fights = []
        for i, fighthash in enumerate(fighthashes):
            ufc_status_doc = ufc_status.find_one({'fighthash': fighthash})
            fighter_name_1 = ufc_status_doc['fighter_name_1']
            fighter_name_2 = ufc_status_doc['fighter_name_2']
            slot = ufc_status_doc['slot']

            # Find the most recent draftkings document with the matching fighthash
            draftkings_doc = draftkings.find_one({'fighthash': fighthash}, sort=[('timestamp', -1)])
            
            odds1 = draftkings_doc['odds1'] if draftkings_doc else 1
            odds2 = draftkings_doc['odds2'] if draftkings_doc else 1

            # Assign an index to each fighter
            fighter_index_1 = 2 * (slot-1) + 1
            fighter_index_2 = 2 * (slot-1) + 2

            parlay_fighter_map[fighter_index_1] = (fighthash, 1)  
            parlay_fighter_map[fighter_index_2] = (fighthash, 2) 

            parlay_fights.append((slot, f'{fighter_name_1} ({odds1}) ({fighter_index_1}) vs {fighter_name_2} ({odds2}) ({fighter_index_2})'))

        parlay_fights.sort()

        parlay_message = '\n'.join(map(lambda x: x[1], parlay_fights))
        print(parlay_message)
        await ctx.send(parlay_message)
        
    @commands.command(name='bet')
    async def bet_parlay(self, ctx, bet_amount: int, *, bet):
        channel_id = ctx.channel.id
        if channel_id not in subscribed_channels:
            await ctx.send('This channel is not subscribed to receive UFC event updates.')
            return

        ufc_status = WhoWillWin_db['ufc_status']
        draftkings = UFCodds_db['draftkings']

        # Split the bet into individual indexes
        indexes = [int(i) for i in bet.split(',')]

        # Check for invalid indexes
        for i in indexes:
            if i not in parlay_fighter_map:
                await ctx.send('Invalid index.')
                return

        # Check if any of the fights have already started
        for i in indexes:
            fighthash = parlay_fighter_map[i][0]
            ufc_status_doc = ufc_status.find_one({'fighthash': fighthash})
            if ufc_status_doc['fight_status'] != 0:
                await ctx.send(f'Fight between {ufc_status_doc["fighter_name_1"]} and {ufc_status_doc["fighter_name_2"]} has already started. Bets are no longer accepted.')
                return

        # Check for duplicate fights
        current_fight_hashs = set()
        for i in indexes:
            fighthash = parlay_fighter_map[i][0]
            if fighthash not in current_fight_hashs:
                current_fight_hashs.add(fighthash)
            else:
                await ctx.send('Error: You have selected multiple fights with the same fighthash.')
                return

        # Calculate total odds
        total_odds = 1
        odds_list = []
        for i in indexes:
            fighthash, outcome = parlay_fighter_map[i]
            draftkings_doc = draftkings.find_one({'fighthash': fighthash}, sort=[('timestamp', -1)])
            if not draftkings_doc:
                draftkings_doc = {'odds1':1, 'odds2':1}
            odds = draftkings_doc['odds1'] if parlay_fighter_map[i][1] == 1 else draftkings_doc['odds2']
            total_odds *= odds
            odds_list.append({'odds': odds, 'fighthash': fighthash, 'outcome': outcome})

        # Check if user has enough money
        users = WhoWillWin_db['users']
        user = users.find_one({'userid': ctx.author.id})
        if user is None:
            user = {
                'userid': ctx.author.id,
                'money': 100,
                'isadmin': False
            }
            users.insert_one(user)

        if user['money'] < bet_amount:
            await ctx.send('You do not have enough money to make this bet.')
            return

        # Subtract bet amount from user's money
        users.update_one({'userid': ctx.author.id}, {'$inc': {'money': -bet_amount}})

        # Add transaction log
        transactions = WhoWillWin_db['transactions']
        transaction = {
            'userid': ctx.author.id,
            'amount': -bet_amount,
            'note': f'Spent on bet {", ".join(str(parlay_fighter_map[i]) for i in indexes)} with total odds: {total_odds}'
        }
        transactions.insert_one(transaction)

        # Store the bet in the database
        user_bets = WhoWillWin_db['user_bets']
        user_bet = {
            'userid': ctx.author.id,
            'betting_info': odds_list,
            'total_odds': total_odds,
            'bet_amount': bet_amount,
            'bet_status': 0
        }
        user_bets.insert_one(user_bet)

        await ctx.send('Bet placed.')
        
    @commands.command(name='check_bet')
    async def check_bet(self, ctx):
        channel_id = ctx.channel.id
        if channel_id not in subscribed_channels:
            await ctx.send('This channel is not subscribed to receive UFC event updates.')
            return

        user_bets = WhoWillWin_db['user_bets']
        user_bets_docs = user_bets.find({'userid': ctx.author.id, 'bet_status': 0}) # Only get ongoing bets

        if not user_bets_docs:
            await ctx.send('You do not have any current bets.')
            return

        ufc_status = WhoWillWin_db['ufc_status']
        for user_bet_doc in user_bets_docs:
            results = []
            for bet_info in user_bet_doc['betting_info']:
                fighthash = bet_info['fighthash']
                fighter = bet_info['outcome']
                ufc_status_doc = ufc_status.find_one({'fighthash': fighthash})
                fighter_name = ufc_status_doc['fighter_name_1'] if fighter == 1 else ufc_status_doc['fighter_name_2']
                opponent_name = ufc_status_doc['fighter_name_2'] if fighter == 1 else ufc_status_doc['fighter_name_1']
                fight_status = fight_status_map[ufc_status_doc['fight_status']].format(fighter_name if ufc_status_doc['fight_status'] == 1 else opponent_name)
                results.append(f'{opponent_name} vs {fighter_name} | {fighter_name} to win | {fight_status}')
            total_odds = user_bet_doc['total_odds']
            results.append(f'Total odds: {total_odds}\n')

            result_message = '\n'.join(results)
            await ctx.send(result_message)

async def watch_fight_status(bot):
    while True:
        await asyncio.sleep(1)
        user_bets = WhoWillWin_db['user_bets']
        ufc_status = WhoWillWin_db['ufc_status']
        ongoing_bets = user_bets.find({'bet_status': 0})  # Only get ongoing bets

        for user_bet in ongoing_bets:
            bets = user_bet['betting_info']
            fight_statuses = [ufc_status.find_one({'fighthash': bet['fighthash']})['fight_status'] for bet in bets]

            if 0 in fight_statuses:  
                continue

            all_won = all(bet['outcome'] == status for bet, status in zip(bets, fight_statuses))
            if all_won:
                winnings = user_bet['bet_amount'] * user_bet['total_odds']
                users = WhoWillWin_db['users']
                users.update_one({'userid': user_bet['userid']}, {'$inc': {'money': winnings}})

                channel_id = next((channel_id for channel_id, subscribed in subscribed_channels.items() if subscribed), None)
                if channel_id:  # Make sure we found a subscribed channel
                    channel = bot.get_channel(channel_id)
                    if channel:  # Make sure the channel exists (it could have been deleted)
                        await channel.send(f'User {user_bet["userid"]} won {winnings} on their parlay!')
            else:
                channel_id = next((channel_id for channel_id, subscribed in subscribed_channels.items() if subscribed), None)
                if channel_id:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.send(f'User {user_bet["userid"]} lost on their parlay!')

            user_bets.update_one({'_id': user_bet['_id']}, {'$set': {'bet_status': 1 if all_won else 2}})  # Update bet status: 1 for won, 2 for lost