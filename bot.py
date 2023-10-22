import discord, json, os, sqlite3, requests
from discord import app_commands

con = sqlite3.connect('payments.db')
con.row_factory = sqlite3.Row

bot = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(bot)
config = json.load(open('./config.json'))
access_token = None

async def updateAccessToken():
    global access_token
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    auth = (config['paypal-client-id'],config['paypal-secret'])
    data = {
        "grant_type": "client_credentials"
    }
    retdata = requests.post(url='https://api-m.paypal.com/v1/oauth2/token', headers=headers, auth=auth, data=data)
    access_token = (retdata.json())['access_token']
    return

async def getOrderDetails(orderid):
    if not access_token:
        await updateAccessToken()
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + str(access_token)
    }
    
    retdata = requests.get(f'https://api-m.paypal.com/v2/payments/captures/{orderid}', headers=headers)
    return retdata.json()

async def dbfunc(userid, orderid):
    cur = con.cursor()
    
    # checks if the valid orderid is already in the database
    cur.execute('SELECT discordid FROM users WHERE orderid = :orderid', {"orderid": str(orderid)})
    orderid_user = cur.fetchone()
    
    # checks if discordid is already in db
    cur.execute('SELECT orderid FROM users WHERE discordid = :discordid', {"discordid": str(userid)})
    userid_user = cur.fetchone()
    
    # if discordid and orderid are not in database
    if not orderid_user and not userid_user:
        values=(userid,orderid)
        cur.execute("INSERT INTO users(discordid, orderid) VALUES(?,?)",values)
        con.commit()
        cur.close()
        return (True,None)
    
    # if orderid isn't attached with a user but discordid is in database 
    elif not orderid_user and userid_user:
        # return and dont put anything in database because
        # they've already used a valid id before.
        return (True,None)
    elif orderid_user and not userid_user:
        # the orderid has already been claimed by someone else
        return (False,orderid_user['discordid'])
    else:
        cur.close()
        return (False,orderid_user['discordid'])

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=config["guild-id"]))
    con.execute('CREATE TABLE IF NOT EXISTS users(discordid TEXT NOT NULL, orderid TEXT NOT NULL)')
    print("Logged in as {0.user}".format(bot))

def cooldown(interaction: discord.Interaction):
    if interaction.user.id in config['admins']:
        return None
    else:
        return app_commands.Cooldown(1, 10)

@tree.command(name = "verify", description = "Verify your order.", guild=discord.Object(id=config["guild-id"]))
@app_commands.checks.dynamic_cooldown(cooldown)
async def verification(interaction: discord.Interaction, orderid: str):
    try:
    # check if the user already has premium
        hasRole = interaction.user.get_role(int(config["premium-role"]))
        
        if not hasRole:
            data = await getOrderDetails(str(orderid))
            print(data)
            try:
                status = str(data["status"]) 
            except:
                status = str(data['name'])
            if status == 'COMPLETED':
                amount = float(data['amount']['value'])
                if amount >= config["minimum-payment-amount"]:
                    currency = str(data['amount']['currency_code'])
                    if currency in config["accepted-currency"]:
                        # check the database for duplicates
                        success, user = await dbfunc(str(interaction.user.id), orderid)
                        
                        if success:
                            # give user the premium role.
                            premrole = interaction.guild.get_role(int(config['premium-role']))
                            try:
                                await interaction.user.add_roles(premrole)
                            except discord.Forbidden:
                                embed=discord.Embed(title='',description=f":neutral_face:  I dont have permission to give out roles.",color=16713025)
                                return await interaction.response.send_message(embed=embed, ephemeral=True) 
                            embed=discord.Embed(title='',description=f"Confirmed payment of **{str(amount)} {currency}**.",color=1288807)
                        elif not success and user == str(interaction.user.id):
                            premrole = interaction.guild.get_role(int(config['premium-role']))
                            try:
                                await interaction.user.add_roles(premrole)
                            except discord.Forbidden:
                                embed=discord.Embed(title='',description=f":neutral_face:  I dont have permission to give out roles.",color=16713025)
                                return await interaction.response.send_message(embed=embed, ephemeral=True) 
                            embed=discord.Embed(title='',description=f"Welcome back, confirmed payment of **{str(amount)} {currency}**.",color=1288807)
                        else:
                            embed=discord.Embed(title='',description=f"ORDERID is already claimed by <@{user}>\nIf this is an error contact an administrator.",color=16713025)
                    else:
                        embed=discord.Embed(title='',description=f"**{currency}** is not an accepted currency, if you think this is a mistake contact an administrator.",color=16713025)
                else:
                    embed=discord.Embed(title='',description=f"The amount given is lower than the minimum payment amount.",color=16713025)
            
            elif status == 'REFUNDED':
                embed=discord.Embed(title='ORDER {0}'.format(status),description="You're not eligble for premium.",color=16713025)
            elif status == 'NOT_AUTHORIZED':
                embed=discord.Embed(title='INVALID ORDERID',description="Please make sure your orderid is correct.",color=16713025)
            elif status == 'RESOURCE_NOT_FOUND':
                embed=discord.Embed(title='INVALID ORDERID',description="Please make sure your orderid is correct.",color=16713025)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed=discord.Embed(title='',description="You already have premium.",color=1288807)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        embed=discord.Embed(title='Error',description=f"Please contact an administrator\n```rust\n{e}```",color=16713025)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

@verification.error
async def gencmd_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        embd=discord.Embed(title="",description=f':no_entry_sign: This command is on cooldown, try again in {(error.retry_after):.0f} seconds.',color=16713025)
        await interaction.response.send_message(embed=embd, ephemeral=False)

@tree.command(name = "updtoken", description = "Update access token.", guild=discord.Object(id=config["guild-id"]))
async def updtoken(interaction: discord.Interaction):
    if not interaction.user.id in config['admins']:
        return await interaction.response.send_message(':neutral_face: ', ephemeral=True)
    await updateAccessToken()
    return await interaction.response.send_message('Access token has been updated', ephemeral=True)

bot.run(config['token'])