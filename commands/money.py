from discord.ext import commands
from database import WhoWillWin_db

class Money(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='money')
    async def money(self, ctx):
        users = WhoWillWin_db['users']
        user = users.find_one({'userid': ctx.author.id})
        if user is None:
            await ctx.send('You are not in the users collection.')
            return
        await ctx.send(f'You have {user["money"]} dollars.')

    @commands.command(name='pay')
    async def pay(self, ctx, userid: int = None, amount: int = 0):
        users = WhoWillWin_db['users']
        user = users.find_one({'userid': ctx.author.id})
        if user is None or not user['isadmin']:
            await ctx.send('Only admins can use this command.')
            return

        if userid is None:
            users.update_many({}, {'$inc': {'money': amount}})
            await ctx.send(f'Added {amount} dollars to all users.')

            # Add transaction log
            transactions = WhoWillWin_db['transactions']
            for user in users.find():
                transaction = {
                    'userid': user['userid'],
                    'amount': amount,
                    'note': 'Payout from admin'
                }
                transactions.insert_one(transaction)
        else:
            user = users.find_one({'userid': userid})
            if user is None:
                await ctx.send('User not found.')
                return
            users.update_one({'userid': userid}, {'$inc': {'money': amount}})
            await ctx.send(f'Added {amount} dollars to user with id {userid}.')

            # Add transaction log
            transactions = WhoWillWin_db['transactions']
            transaction = {
                'userid': userid,
                'amount': amount,
                'note': f'Payout from {ctx.author.id}'
            }
            transactions.insert_one(transaction)


    @commands.command(name='history')
    async def history(self, ctx):
        user_bets = WhoWillWin_db['user_bets'].find({'userid': ctx.author.id})
        ufc_status = WhoWillWin_db['ufc_status']
        
        if not user_bets:
            await ctx.send('You have no betting history.')
            return

        for bet in user_bets:
            bet_info_str = []
            for info in bet['betting_info']:
                # Get the fight details based on the fighthash
                fight_doc = ufc_status.find_one({'fighthash': info['fighthash']})
                if fight_doc:
                    fighter_name = fight_doc['fighter_name_1'] if info['outcome'] == 1 else fight_doc['fighter_name_2']
                    bet_info_str.append(fighter_name)

            bet_info_str = ", ".join(bet_info_str)
            result_str = "Won" if bet['bet_status'] == 1 else "Lost" if bet['bet_status'] == 2 else "Pending"
            message = f"""
**Bet Amount:** {bet['bet_amount']}
**Total Odds:** {bet['total_odds']}
**Betting Info:** {bet_info_str}
**Result:** {result_str}
------------------
"""
            await ctx.send(message)

    @commands.command(name='leaderboard')
    async def leaderboard(self, ctx):
        users = WhoWillWin_db['users'].find().sort('money', -1)  # Sort by money in descending order
        leaderboard_str = "Leaderboard:\n"
        for i, user in enumerate(users):
            leaderboard_str += f"{i + 1}. {user['userid']}: ${user['money']}\n"

        await ctx.send(leaderboard_str)

    @commands.command(name='next_fight_bets')
    async def next_fight_bets(self, ctx):
        # Find the current fight
        ufc_status = WhoWillWin_db['ufc_status']
        current_fight = ufc_status.find_one({'fight_status': 0})
        if not current_fight:
            await ctx.send('There is no current fight.')
            return

        # Find the next fight
        next_fight = ufc_status.find_one({'event': current_fight['event'], 'slot': current_fight['slot'] - 1})
        if not next_fight:
            await ctx.send('There is no next fight available for the current event.')
            return

        # Find all bets for the next fight
        user_bets = WhoWillWin_db['user_bets'].find({'betting_info.fighthash': next_fight['fighthash']})
        
        if not user_bets:
            await ctx.send('There are no bets for the next fight yet.')
            return

        message = "Bets for the next fight:\n"
        for bet in user_bets:
            bet_info = next((info for info in bet['betting_info'] if info['fighthash'] == next_fight['fighthash']), None)
            if bet_info:
                fighter_name = next_fight['fighter_name_1'] if bet_info['outcome'] == 1 else next_fight['fighter_name_2']
                message += f"User {bet['userid']} bet ${bet['bet_amount']} on {fighter_name}\n"

        await ctx.send(message)