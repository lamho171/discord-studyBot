import discord
from discord.ext import commands, tasks
import aiosqlite
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import ssl
import aiohttp
import certifi
import logging

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("Bot token not found. Please set it in a .env file.")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create SSL context using certifi
ssl_context = ssl.create_default_context(cafile=certifi.where())

async def create_session():
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    session = aiohttp.ClientSession(connector=connector)
    return session

# Bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Cache to prevent spamming users with DMs
dm_cache = {}

async def setup_database():
    async with aiosqlite.connect("progress.db") as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS progress (
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (user_id, date)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS group_status (
                lives INTEGER NOT NULL,
                last_reset TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO group_status (lives, last_reset)
            VALUES (5, ?)
            """,
            (datetime.utcnow().date().isoformat(),)
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                user_id TEXT NOT NULL PRIMARY KEY,
                goal TEXT NOT NULL
            )    
            """
        )
        await db.commit()

@bot.event
async def on_ready():
    logger.info(f"We have logged in as {bot.user}")
    try:
        await setup_database()
        daily_check.start()
        weekly_reset.start()
        daily_goal_reminder.start()
    except Exception as e:
        logger.error(f"Error during bot initialization: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
        user_id = str(message.author.id)

        async with aiosqlite.connect("progress.db") as db:
            async with db.execute("SELECT 1 FROM goals WHERE user_id = ?", (user_id,)) as cursor:
                if not await cursor.fetchone():
                    # Save the user's reply as their goal
                    goal = message.content
                    await db.execute(
                        "INSERT INTO goals (user_id, goal) VALUES (?, ?)", (user_id, goal)
                    )
                    await db.commit()
                    await message.channel.send(f"Thanks, {message.author.name}! Your goal has been saved: `{goal}`")
                else:
                    # Handle progress updates
                    today = datetime.utcnow().date().isoformat()
                    await db.execute(
                        "INSERT OR IGNORE INTO progress (user_id, date) VALUES (?, ?)", (user_id, today)
                    )
                    await db.commit()
                    await message.channel.send("Thanks for your update! Your progress has been logged.")

    await bot.process_commands(message)

@tasks.loop(hours=24)
async def daily_goal_reminder():
    """Task to send reminders or ask users for goals."""
    guild = discord.utils.get(bot.guilds)  # Get the first server the bot is in
    if not guild:
        logger.warning("No guild found!")
        return

    async with aiosqlite.connect("progress.db") as db:
        async with db.execute("SELECT user_id FROM goals") as cursor:
            rows = await cursor.fetchall()
            users_with_goals = {row[0] for row in rows}

        for member in guild.members:
            if member.bot:
                continue

            user_id = str(member.id)
            now = datetime.utcnow()

            if user_id in dm_cache and now - dm_cache[user_id] < timedelta(hours=24):
                continue  # Skip if user was recently messaged

            if user_id not in users_with_goals:
                try:
                    await member.send(
                        f"Hi {member.name}! You haven't set a daily goal yet. "
                        "Please reply to this message with your goal for today!"
                    )
                    dm_cache[user_id] = now
                except discord.Forbidden:
                    logger.warning(f"Could not DM {member.name}. DMs might be disabled.")
            else:
                async with db.execute("SELECT goal FROM goals WHERE user_id = ?", (user_id,)) as cursor:
                    goal = (await cursor.fetchone())[0]
                try:
                    await member.send(
                        f"Hi {member.name}! Here's your daily reminder:\n**Goal:** {goal}\n"
                        "Reply to this message with an update on your progress!"
                    )
                    dm_cache[user_id] = now
                except discord.Forbidden:
                    logger.warning(f"Could not DM {member.name}. DMs might be disabled.")

@tasks.loop(hours=24)
async def daily_check():
    """Daily group progress check."""
    channel = discord.utils.get(bot.get_all_channels(), name="daily-dial")
    if not channel:
        logger.warning("Daily Dial channel not found!")
        return

    async with aiosqlite.connect("progress.db") as db:
        today = datetime.utcnow().date().isoformat()
        guild = channel.guild
        all_members = [member for member in guild.members if not member.bot]

        missing_members = []
        for member in all_members:
            async with db.execute("SELECT 1 FROM progress WHERE user_id = ? AND date = ?", (str(member.id), today)) as cursor:
                if not await cursor.fetchone():
                    missing_members.append(member)

        if missing_members:
            await db.execute("UPDATE group_status SET lives = lives - 1 WHERE lives > 0")
            await db.commit()

            async with db.execute("SELECT lives FROM group_status") as cursor:
                lives = (await cursor.fetchone())[0]

            await channel.send(
                f"The following members missed their updates today: {', '.join([member.mention for member in missing_members])}. Boo!!! "
                f"The group has lost a life. Remaining lives: {lives}"
            )

            if lives <= 0:
                await channel.send("Oh no! The group has lost all its lives for this week. You all suck! :( Better luck next time!")

@tasks.loop(hours=168)
async def weekly_reset():
    async with aiosqlite.connect("progress.db") as db:
        await db.execute("DELETE FROM progress")
        await db.execute("UPDATE group_status SET lives = 5, last_reset = ?", (datetime.utcnow().date().isoformat(),))
        await db.commit()

    channel = discord.utils.get(bot.get_all_channels(), name="daily-dial")
    if channel:
        await channel.send("A new week has started! The group has 5 lives again. Good luck buds!")

@bot.command()
async def test_reminder(ctx):
    """Test the daily reminder."""
    await daily_goal_reminder()
    await ctx.send("Daily reminder test executed.")

bot.run(TOKEN)
