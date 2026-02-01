import os
from datetime import datetime

import discord
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Define deadlines: (name, date, description)
DEADLINES = [
    ("Metabit Contract", datetime(2026, 3, 10), "March 10th, 2026"),
    ("Pear.vc Demo Day", datetime(2026, 4, 2), "April 2nd, 2026"),
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

    lines = ["Good morning! Here's your countdown:\n"]

    for name, deadline_date, description in DEADLINES:
        days_remaining = (deadline_date.date() - today).days

        if days_remaining > 0:
            lines.append(f"📅 {name}: {days_remaining} days remaining ({description})")
        elif days_remaining == 0:
            lines.append(f"📅 {name}: Today is the day! ({description})")
        else:
            lines.append(f"📅 {name}: Deadline passed! ({description})")

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

    # Schedule daily reminder at 9:00 AM ET
    scheduler.add_job(
        send_daily_reminder,
        CronTrigger(hour=9, minute=0, timezone=ET),
        id="daily_reminder",
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduler started - daily reminders at 9:00 AM ET")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not found in environment variables")
        print("Please create a .env file with your Discord bot token")
        exit(1)

    if not CHANNEL_ID:
        print("Warning: CHANNEL_ID not found in environment variables")
        print("The bot will start but won't send reminders until configured")

    client.run(DISCORD_TOKEN)
