import discord
from discord.ext import commands, tasks
from discord import app_commands, Intents, Client, Interaction
import sqlite3
import datetime

conn = sqlite3.connect('accounts.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS accounts
             (name TEXT PRIMARY KEY, ban_expiry DATETIME, premier_rating INTEGER, added_by TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS settings
             (name TEXT PRIMARY KEY, value TEXT)''')

conn.commit()

class Autism(Client):
    channel_id = None

    def __init__(self, *, intents: Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()

client = Autism(intents=Intents.none())

def format_time(time):
    return time.strftime("%Y-%m-%d %H:%M:%S")

@client.event
async def update_list():
    c.execute("SELECT value FROM settings WHERE name=?", ("channel_id",))
    row = c.fetchone()
    if row:
        channel_id = int(row[0])
        print(f'[Readifier] Channel ID: {channel_id}')
        channel = await client.fetch_channel(channel_id)
        if channel:
            embed = discord.Embed(title="Accounts with cooldown", color=discord.Color.red())
            c.execute("SELECT name, ban_expiry, premier_rating FROM accounts")
            accounts = c.fetchall()

            for account in accounts:
                name, ban_expiry, premier_rating = account
                embed.add_field(name=name, value=f"Ban Expires: {ban_expiry}\nPremier Rating: {premier_rating}", inline=False)
            
            editable_message = None
            async for message in channel.history(limit=1):
                if message.author == client.user and isinstance(message, discord.Message):
                    editable_message = message
                    break

            if editable_message:
                print('[Readifier] Embed found, updating...')
                await editable_message.edit(embed=embed)
            else:
                print('[Readifier] No embed found, sending...')
                await channel.send(embed=embed)
        else:
            print('[Readifier] Channel not found.')
    else:
        print('[Readifier] Channel ID not found in settings.')

@client.tree.command()
async def setup(interaction: Interaction):
    channel_id = interaction.channel.id
    Autism.channel_id = channel_id

    await interaction.response.send_message(ephemeral=True, content=f"List channel set to <#{channel_id}>.")

    c.execute("INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?)", ("channel_id", str(channel_id)))
    conn.commit()

    await update_list()

# thank you chatgpt
async def parse_ban_duration(ban_duration: str) -> datetime.timedelta: 
    unit = ban_duration[-1].lower()
    value = int(ban_duration[:-1])
    if unit == 'm':
        return datetime.timedelta(minutes=value)
    elif unit == 'h':
        return datetime.timedelta(hours=value)
    elif unit == 'd':
        return datetime.timedelta(days=value)
    elif unit == 'y':
        return datetime.timedelta(days=value * 365)
    else:
        raise ValueError("Invalid ban duration unit. Use 'm' for minutes, 'h' for hours, 'd' for days, or 'y' for years.") #todo: add notification for the user

@client.tree.command()
async def add(interaction: Interaction, account_name: str, ban_duration: str, premier_rating: int = None):
    current_time = datetime.datetime.now() # yes its only viable for the host's timezone but i dont care
    ban_expiry = current_time + await parse_ban_duration(ban_duration)
    added_by = interaction.user.id
    
    c.execute("INSERT OR REPLACE INTO accounts (name, ban_expiry, premier_rating, added_by) VALUES (?, ?, ?, ?)", (account_name, format_time(ban_expiry), premier_rating, added_by))
    conn.commit()
    
    await interaction.response.send_message(ephemeral=True, content=f"Account '{account_name}' added successfully.")
    await update_list()

@client.tree.command()
async def rm(interaction: Interaction, account_name: str):
    c.execute("DELETE FROM accounts WHERE name=?", (account_name,))
    conn.commit()
    await interaction.response.send_message(ephemeral=True, content=f"Account '{account_name}' removed successfully.")
    await update_list()



@tasks.loop(minutes=1)
async def check_bans():
    current_time = datetime.datetime.now()
    c.execute("SELECT * FROM accounts WHERE ban_expiry <= ?", (format_time(current_time),))

    expired_accounts = c.fetchall()
    if expired_accounts:
        print(f"[Readifier] Expired account: {expired_accounts}")
    else:
        print(f"[Readifier] No expired accounts at this moment")

    for account in expired_accounts:
        user_id = account[3]  #todo: fix shit code
        user = await client.fetch_user(user_id)
        if user:
            try:
                await user.send(f"Your ban for account '{account[0]}' has expired.")
                print(f"[Readifier] Sent expiration message to {user}")
            except Exception as e:
                print(f"[Readifier] Failed to send expiration message to {user}: {e}")
        c.execute("DELETE FROM accounts WHERE name=?", (account[0],))
        conn.commit()
    await update_list()

@client.event
async def on_ready():
    print(f'[Readifier] Logged in as {client.user}')
    check_bans.start()

client.run('YOUR_BOT_TOKEN')
