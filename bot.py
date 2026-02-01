import os
import random
from datetime import datetime

import anthropic
import discord
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize Anthropic client
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

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
intents.message_content = True  # Required to read message content
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
async def on_message(message):
    """Handle incoming messages - respond when bot is mentioned."""
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Check if the bot is mentioned
    if client.user not in message.mentions:
        return

    # Check if Anthropic client is configured
    if not claude_client:
        await message.channel.send("Sorry, I'm not configured to chat yet. Please add an Anthropic API key.")
        return

    # Show typing indicator while processing
    async with message.channel.typing():
        # Fetch recent messages for context (last 25 messages)
        history = []
        async for msg in message.channel.history(limit=25):
            # Build context from recent messages
            author_name = msg.author.display_name
            content = msg.content
            # Remove bot mention from the current message for cleaner context
            if msg.id == message.id:
                content = content.replace(f"<@{client.user.id}>", "").strip()
            history.append(f"{author_name}: {content}")

        # Reverse to chronological order
        history.reverse()
        conversation_context = "\n".join(history)

        # Get the user's question (remove the bot mention)
        user_question = message.content.replace(f"<@{client.user.id}>", "").strip()

        # Build the prompt for Claude
        system_prompt = """You are a helpful assistant in a Discord server. You have access to recent conversation history for context.
Keep your responses concise and friendly - this is a chat, not an essay.
If someone asks about deadlines, the team has two coming up:
- Metabit Contract: March 10th, 2026
- Pear Demo Day: April 2nd, 2026"""

        user_prompt = f"""Here's the recent conversation in this channel:

{conversation_context}

The user is asking you: {user_question}

Please respond helpfully and concisely."""

        try:
            # Call Claude API
            response = claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            reply = response.content[0].text

            # Send the response (split if too long for Discord)
            if len(reply) <= 2000:
                await message.reply(reply)
            else:
                # Split into chunks
                for i in range(0, len(reply), 2000):
                    chunk = reply[i : i + 2000]
                    if i == 0:
                        await message.reply(chunk)
                    else:
                        await message.channel.send(chunk)

        except Exception as e:
            print(f"Error calling Claude API: {e}")
            await message.reply("Sorry, I encountered an error trying to respond. Please try again.")


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

    if not ANTHROPIC_API_KEY:
        print("Warning: ANTHROPIC_API_KEY not found in environment variables")
        print("The bot will start but won't respond to @mentions until configured")

    client.run(DISCORD_TOKEN)
