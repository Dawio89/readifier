import discord
from discord.ext import commands, tasks
from discord import app_commands, Intents, Client, Interaction
import sqlite3
import datetime

conn = sqlite3.connect('accounts.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS accounts
             (name TEXT PRIMARY KEY, ban_expiry DATETIME, premier_rating INTEGER, added_by TEXT, notes TEXT)''')

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
    if time:
        return time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return ""

async def get_username(user_id):
    user = await client.fetch_user(user_id)
    return user.name

@client.event
async def update_list():
    c.execute("SELECT value FROM settings WHERE name=?", ("channel_id",))
    row = c.fetchone()
    if row:
        channel_id = int(row[0])
        print(f'[Readifier] Channel ID: {channel_id}')
        channel = await client.fetch_channel(channel_id)
        if channel:
            embed = discord.Embed(title="List of accounts", color=discord.Color.red())
            c.execute("SELECT name, ban_expiry, premier_rating, notes FROM accounts")
            accounts = c.fetchall()

            for account in accounts:
                name, ban_expiry, premier_rating, notes = account
                if ban_expiry:
                    embed.add_field(name=name, value=f"Ban Expires: {ban_expiry}\n" +
                                                     (f"Premier Rating: {premier_rating}\n" if premier_rating else "") +
                                                     (f"Notes: {notes}" if notes else ""),inline=False)
                else:
                    embed.add_field(name=name, value=(f"Premier Rating: {premier_rating}\n" if premier_rating else "") +
                                                     (f"Notes: {notes}" if notes else ""),inline=False)
            
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
async def add(interaction: Interaction, account_name: str, ban_duration: str = None, premier_rating: str = None, notes: str = None):
    current_time = datetime.datetime.now()
    
    if not all(char.isalnum() or char in "_- " for char in account_name):
        await interaction.response.send_message(ephemeral=True, content="Invalid characters are not allowed >:(")
        return

    if notes:
        if len(notes) > 100:
            await interaction.response.send_message(ephemeral=True, content="Notes must contain 100 characters or fewer.")
            return

    if ban_duration:
        if len(ban_duration) > 6:
            await interaction.response.send_message(ephemeral=True, content="Ban duration should not be this long.")
            return

    if len(account_name) > 32:
        await interaction.response.send_message(ephemeral=True, content="Account name must be 32 characters or fewer.")
        return

    user_id = interaction.user.id
    username = await get_username(user_id)

    print(f"[Readifier] {username} sent:'{str(account_name)}', '{str(ban_duration)}', '{str(premier_rating)}', '{str(notes)}'")

    if ban_duration:
        ban_expiry = current_time + await parse_ban_duration(ban_duration)
    else:
        ban_expiry = None

    if premier_rating:
        try:
            premier_rating = int(premier_rating)
            if not 0 <= premier_rating <= 35000:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(ephemeral=True, content="Premier rating must be an integer between 0 and 35000.")
            return
    else:
        premier_rating = None
        
    added_by = interaction.user.id
    
    try:
        c.execute("INSERT OR REPLACE INTO accounts (name, ban_expiry, premier_rating, added_by, notes) VALUES (?, ?, ?, ?, ?)", (account_name, format_time(ban_expiry), premier_rating, added_by, notes))
        conn.commit()
        await interaction.response.send_message(ephemeral=True, content=f"Account '{account_name}' added successfully.")
        await update_list()
    except Exception:
        print(f"[Readifier] Error adding account")
        await interaction.response.send_message(ephemeral=True, content="Not nice.")


@client.tree.command()
async def rm(interaction: Interaction, account_name: str):

    if not all(char.isalnum() or char in "_- " for char in account_name):
        await interaction.response.send_message(ephemeral=True, content="Invalid characters are not allowed >:(")
        return

    if len(account_name) > 32:
        await interaction.response.send_message(ephemeral=True, content="Account name must be 32 characters or fewer.")
        return

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
        for account in expired_accounts:
            user_id = account[3]  #todo: fix shit code////nvm add more shit code
            user = await client.fetch_user(user_id)
            if user and account[1]:
                try:
                    await user.send(f"Your ban for account '{account[0]}' has expired.")
                    print(f"[Readifier] Sent expiration message to {user}")
                except Exception:
                    print(f"[Readifier] Failed to send expiration message to {user}")
            c.execute("UPDATE accounts SET ban_expiry=NULL WHERE name=?", (account[0],))
            conn.commit()
        await update_list()
    else:
        print(f"[Readifier] No expired accounts at this moment")

@client.event
async def on_ready():
    print(f'[Readifier] Logged in as {client.user}')
    check_bans.start()

client.run('YOUR_BOT_TOKEN')
