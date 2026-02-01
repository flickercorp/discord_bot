import os
import random
from datetime import datetime

import discord
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Define deadlines: (name, date)
DEADLINES = [
    ("Metabit Contract", datetime(2026, 3, 10)),
    ("Pear Demo Day", datetime(2026, 4, 2)),
]

# Business quotes
BUSINESS_QUOTES = [
    "The way to get started is to quit talking and begin doing. – Walt Disney",
    "Success is not final, failure is not fatal: it is the courage to continue that counts. – Winston Churchill",
    "Don't be afraid to give up the good to go for the great. – John D. Rockefeller",
    "I find that the harder I work, the more luck I seem to have. – Thomas Jefferson",
    "Success usually comes to those who are too busy to be looking for it. – Henry David Thoreau",
    "Opportunities don't happen. You create them. – Chris Grosser",
    "The only place where success comes before work is in the dictionary. – Vidal Sassoon",
    "If you really look closely, most overnight successes took a long time. – Steve Jobs",
    "The road to success and the road to failure are almost exactly the same. – Colin R. Davis",
    "I have not failed. I've just found 10,000 ways that won't work. – Thomas Edison",
    "It's fine to celebrate success but it is more important to heed the lessons of failure. – Bill Gates",
    "The secret of getting ahead is getting started. – Mark Twain",
    "Risk more than others think is safe. Dream more than others think is practical. – Howard Schultz",
    "In the end, a vision without the ability to execute it is probably a hallucination. – Steve Case",
    "Your most unhappy customers are your greatest source of learning. – Bill Gates",
    "The best time to plant a tree was 20 years ago. The second best time is now. – Chinese Proverb",
    "Move fast and break things. Unless you are breaking stuff, you are not moving fast enough. – Mark Zuckerberg",
    "What would you do if you weren't afraid? – Sheryl Sandberg",
    "Stay hungry, stay foolish. – Steve Jobs",
    "Chase the vision, not the money; the money will end up following you. – Tony Hsieh",
]

# Timezone for scheduling (Eastern Time)
ET = pytz.timezone("America/New_York")

# Discord client setup
intents = discord.Intents.default()
client = discord.Client(intents=intents)

scheduler = AsyncIOScheduler()


def get_countdown_message() -> str:
    """Generate the countdown message for all deadlines."""
    today = datetime.now().date()

    lines = ["Hey Gents, here's the deadline:\n"]

    for name, deadline_date in DEADLINES:
        days_remaining = (deadline_date.date() - today).days

        if days_remaining > 0:
            lines.append(f"{name}: {days_remaining} days remaining")
        elif days_remaining == 0:
            lines.append(f"{name}: Today is the day!")
        else:
            lines.append(f"{name}: Deadline passed!")

    # Add a unique quote for each day (seeded by date so no repeats)
    day_seed = today.toordinal()
    daily_random = random.Random(day_seed)
    quote = daily_random.choice(BUSINESS_QUOTES)
    lines.append(f"\n{quote}")

    return "\n".join(lines)


async def send_daily_reminder():
    """Send the daily countdown reminder to the configured channel."""
    if not CHANNEL_ID:
        print("Error: CHANNEL_ID not configured")
        return

    channel = client.get_channel(int(CHANNEL_ID))
    if channel is None:
        print(f"Error: Could not find channel with ID {CHANNEL_ID}")
        return

    message = get_countdown_message()
    await channel.send(message)
    print(f"Sent daily reminder at {datetime.now(ET)}")


@client.event
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    print(f"Bot is ready! Logged in as {client.user}")

    # Schedule daily reminder at 11:38 PM PT (temporary for testing)
    PT = pytz.timezone("America/Los_Angeles")
    scheduler.add_job(
        send_daily_reminder,
        CronTrigger(hour=23, minute=38, timezone=PT),
        id="daily_reminder",
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduler started - daily reminders at 11:38 PM PT")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not found in environment variables")
        print("Please create a .env file with your Discord bot token")
        exit(1)

    if not CHANNEL_ID:
        print("Warning: CHANNEL_ID not found in environment variables")
        print("The bot will start but won't send reminders until configured")

    client.run(DISCORD_TOKEN)
