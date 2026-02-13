import json
import os
import random
import re
from datetime import datetime

import aiohttp
import anthropic
import discord
import pytz
from bs4 import BeautifulSoup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# URL regex pattern
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ATTIO_API_KEY = os.getenv("ATTIO_API_KEY")

# Initialize Anthropic client
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# Define deadlines: (name, date)
DEADLINES = [
    ("Metabit Contract", datetime(2026, 3, 10)),
    ("Pear Demo Day", datetime(2026, 4, 2)),
]

# Fallback quotes in case API fails
FALLBACK_QUOTES = [
    "The way to get started is to quit talking and begin doing. – Walt Disney",
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


async def generate_business_quote() -> str:
    """Generate a business quote using Claude API."""
    if not claude_client:
        return random.choice(FALLBACK_QUOTES)

    topics = [
        "startup growth", "leadership", "perseverance", "innovation",
        "teamwork", "taking risks", "focus and discipline", "customer obsession",
        "learning from failure", "building culture", "ambition", "creativity",
        "execution over ideas", "resilience", "thinking big",
    ]
    topic = random.choice(topics)
    today = datetime.now().strftime("%A, %B %d")

    try:
        response = claude_client.messages.create(
            model="claude-opus-4-6",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": f"Today is {today}. Generate a single inspiring quote about {topic} from a famous entrepreneur or business leader (with attribution). Pick someone unexpected — avoid the most overused quotes. Keep it to 1-2 sentences. Return ONLY the quote, nothing else."
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Error generating quote: {e}")
        return random.choice(FALLBACK_QUOTES)


async def fetch_article_content(url: str) -> str | None:
    """Fetch and extract text content from a URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    return None
                html = await response.text()

        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
            element.decompose()

        # Try to find the main article content
        article = soup.find("article") or soup.find("main") or soup.find("body")
        if not article:
            return None

        # Get text and clean it up
        text = article.get_text(separator="\n", strip=True)

        # Limit to first ~8000 chars to avoid token limits
        if len(text) > 8000:
            text = text[:8000] + "..."

        return text
    except Exception as e:
        print(f"Error fetching article: {e}")
        return None


async def summarize_article(url: str) -> str:
    """Fetch an article and summarize it using Claude."""
    if not claude_client:
        return "Sorry, I can't summarize articles without an Anthropic API key configured."

    content = await fetch_article_content(url)
    if not content:
        return f"Sorry, I couldn't fetch the content from that URL. It might be paywalled, require login, or block bots."

    try:
        response = claude_client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""Please summarize this article concisely. Include:
- The main topic/thesis
- Key points (3-5 bullet points)
- Any important conclusions or takeaways

Article content:
{content}"""
            }],
        )
        return response.content[0].text
    except Exception as e:
        print(f"Error summarizing article: {e}")
        return "Sorry, I encountered an error trying to summarize the article."


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    return URL_PATTERN.findall(text)


# Attio API base URL
ATTIO_API_BASE = "https://api.attio.com/v2"

# Attio tools definition for Claude
ATTIO_TOOLS = [
    {
        "name": "list_deals",
        "description": "List deals from the Attio CRM sales pipeline. Can filter by stage. Returns deal names, values, stages, sources, and other key information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {
                    "type": "string",
                    "description": "Filter by pipeline stage. Valid stages: Lead, Qualified, Demo, Contract Out, Won, Lost, Revisit"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of deals to return (default 20, max 100)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "get_deal",
        "description": "Get detailed information about a specific deal by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {
                    "type": "string",
                    "description": "The unique ID of the deal to retrieve"
                }
            },
            "required": ["deal_id"]
        }
    },
    {
        "name": "search_deals",
        "description": "Search for deals in Attio CRM by company/deal name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The company or deal name to search for"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_pipeline_stages",
        "description": "List all available pipeline stages/statuses to understand the sales process.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_pipeline_summary",
        "description": "Get a summary of the entire pipeline showing deal counts and total values by stage.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


async def attio_request(endpoint: str, method: str = "GET", json_data: dict = None) -> dict | None:
    """Make an authenticated request to the Attio API."""
    if not ATTIO_API_KEY:
        return {"error": "Attio API key not configured"}

    headers = {
        "Authorization": f"Bearer {ATTIO_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{ATTIO_API_BASE}{endpoint}"
            async with session.request(
                method,
                url,
                headers=headers,
                json=json_data,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    print(f"Attio API error {response.status}: {error_text}")
                    return {"error": f"API returned status {response.status}"}
    except Exception as e:
        print(f"Attio request error: {e}")
        return {"error": str(e)}


async def attio_list_deals(limit: int = 20, stage: str = None) -> dict:
    """List deals from Attio CRM, optionally filtered by stage."""
    query_data = {"limit": min(limit, 100)}

    if stage:
        query_data["filter"] = {"stage": stage}

    result = await attio_request(
        "/objects/deals/records/query",
        method="POST",
        json_data=query_data
    )
    return result or {"error": "Failed to fetch deals"}


async def attio_get_deal(deal_id: str) -> dict:
    """Get a specific deal by ID using query filter."""
    result = await attio_request(
        "/objects/deals/records/query",
        method="POST",
        json_data={
            "filter": {"record_id": deal_id}
        }
    )
    return result or {"error": "Failed to fetch deal"}


async def attio_search_deals(query: str) -> dict:
    """Search for deals by name."""
    result = await attio_request(
        "/objects/deals/records/query",
        method="POST",
        json_data={
            "filter": {"name": {"$contains": query}}
        }
    )
    return result or {"error": "Search failed"}


async def attio_list_pipeline_stages() -> dict:
    """Get unique pipeline stages from all deals."""
    result = await attio_request(
        "/objects/deals/records/query",
        method="POST",
        json_data={"limit": 100}
    )
    if not result or "data" not in result:
        return {"error": "Failed to fetch pipeline info"}

    # Extract unique stages
    stages = {}
    for deal in result.get("data", []):
        stage_data = deal.get("values", {}).get("stage", [])
        if stage_data and len(stage_data) > 0:
            status = stage_data[0].get("status", {})
            stage_id = status.get("id", {}).get("status_id")
            stage_title = status.get("title")
            if stage_id and stage_title and stage_id not in stages:
                stages[stage_id] = stage_title

    return {"stages": list(stages.values())}


async def attio_get_pipeline_summary() -> dict:
    """Get a summary of the pipeline with counts and values by stage."""
    result = await attio_request(
        "/objects/deals/records/query",
        method="POST",
        json_data={"limit": 100}
    )
    if not result or "data" not in result:
        return {"error": "Failed to fetch pipeline data"}

    # Aggregate by stage
    summary = {}
    for deal in result.get("data", []):
        stage_data = deal.get("values", {}).get("stage", [])
        stage_title = "Unknown"
        if stage_data and len(stage_data) > 0:
            stage_title = stage_data[0].get("status", {}).get("title", "Unknown")

        value_data = deal.get("values", {}).get("value", [])
        deal_value = value_data[0].get("currency_value", 0) if value_data else 0

        if stage_title not in summary:
            summary[stage_title] = {"count": 0, "total_value": 0, "deals": []}

        deal_name = deal.get("values", {}).get("name", [{}])[0].get("value", "Unknown")
        summary[stage_title]["count"] += 1
        summary[stage_title]["total_value"] += deal_value
        summary[stage_title]["deals"].append({"name": deal_name, "value": deal_value})

    return {"pipeline_summary": summary}


async def execute_attio_tool(tool_name: str, tool_input: dict) -> str:
    """Execute an Attio tool and return the result as a string."""
    if tool_name == "list_deals":
        result = await attio_list_deals(
            limit=tool_input.get("limit", 20),
            stage=tool_input.get("stage")
        )
    elif tool_name == "get_deal":
        result = await attio_get_deal(tool_input["deal_id"])
    elif tool_name == "search_deals":
        result = await attio_search_deals(tool_input["query"])
    elif tool_name == "list_pipeline_stages":
        result = await attio_list_pipeline_stages()
    elif tool_name == "get_pipeline_summary":
        result = await attio_get_pipeline_summary()
    else:
        result = {"error": f"Unknown tool: {tool_name}"}

    return json.dumps(result, indent=2, default=str)


async def get_countdown_message() -> str:
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

    # Generate a quote using Claude
    quote = await generate_business_quote()
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

    message = await get_countdown_message()
    await channel.send(message)
    print(f"Sent daily reminder at {datetime.now(ET)}")


async def check_and_send_missed_reminder():
    """Check if today's reminder was missed and send it if needed."""
    if not CHANNEL_ID:
        return

    now = datetime.now(ET)
    today = now.date()
    reminder_hour = 8  # 8:00 AM ET

    # Only check if it's past the reminder time
    if now.hour < reminder_hour:
        print(f"It's before {reminder_hour}:00 AM ET, no need to check for missed reminder")
        return

    channel = client.get_channel(int(CHANNEL_ID))
    if channel is None:
        print(f"Error: Could not find channel with ID {CHANNEL_ID}")
        return

    # Check recent messages to see if we already sent today's reminder
    try:
        async for msg in channel.history(limit=50):
            # Only check messages from our bot
            if msg.author == client.user:
                # Check if message was sent today and contains the reminder format
                msg_date = msg.created_at.astimezone(ET).date()
                if msg_date == today and "Hey Gents, here's the deadline:" in msg.content:
                    print(f"Today's reminder was already sent at {msg.created_at}")
                    return

        # If we get here, no reminder was sent today - send it now
        print(f"Missed reminder detected! Sending now at {now}")
        await send_daily_reminder()

    except Exception as e:
        print(f"Error checking for missed reminder: {e}")


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

    # Get the user's message (remove the bot mention)
    user_message = message.content.replace(f"<@{client.user.id}>", "").strip().lower()

    # Check if user wants to summarize an article
    summarize_keywords = ["summarize", "summary", "tldr", "tl;dr", "sum up", "what does this say", "what's this about"]
    wants_summary = any(keyword in user_message for keyword in summarize_keywords)

    if wants_summary:
        # Show typing indicator while processing
        async with message.channel.typing():
            # First check for URLs in the current message
            urls = extract_urls(message.content)

            # If no URLs in current message, check if replying to a message with URLs
            if not urls and message.reference:
                try:
                    replied_msg = await message.channel.fetch_message(message.reference.message_id)
                    urls = extract_urls(replied_msg.content)
                except:
                    pass

            # If still no URLs, check recent messages for URLs
            if not urls:
                async for msg in message.channel.history(limit=10):
                    if msg.id != message.id:
                        found_urls = extract_urls(msg.content)
                        if found_urls:
                            urls = found_urls
                            break

            if not urls:
                await message.reply("I couldn't find any URLs to summarize. Share a link or reply to a message with a link!")
                return

            # Summarize the first URL found
            url = urls[0]
            await message.reply(f"Let me read that article for you...")
            summary = await summarize_article(url)

            # Send the summary (split if too long for Discord)
            if len(summary) <= 2000:
                await message.channel.send(summary)
            else:
                for i in range(0, len(summary), 2000):
                    await message.channel.send(summary[i : i + 2000])
        return

    # Regular chat response
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
- Pear Demo Day: April 2nd, 2026

You can also summarize articles if someone shares a URL and asks you to summarize it.

You have access to Attio CRM tools to look up deals, search for companies/contacts, and check the sales pipeline. Use these tools when users ask about deals, pipeline, CRM data, sales, prospects, or specific companies/contacts."""

        user_prompt = f"""Here's the recent conversation in this channel:

{conversation_context}

The user is asking you: {user_question}

Please respond helpfully and concisely."""

        try:
            # Determine if we should include Attio tools
            tools = ATTIO_TOOLS if ATTIO_API_KEY else None

            # Call Claude API with tools if available
            response = claude_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=tools,
            )

            # Handle tool use responses
            messages = [{"role": "user", "content": user_prompt}]
            while response.stop_reason == "tool_use":
                # Extract tool calls from response
                tool_results = []
                assistant_content = response.content

                for block in response.content:
                    if block.type == "tool_use":
                        print(f"Executing Attio tool: {block.name}")
                        result = await execute_attio_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

                # Get next response from Claude
                response = claude_client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=1024,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                )

            # Extract text response
            reply = ""
            for block in response.content:
                if hasattr(block, "text"):
                    reply += block.text

            if not reply:
                reply = "I processed your request but couldn't generate a response."

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

    # Schedule daily reminder at 8:00 AM ET
    scheduler.add_job(
        send_daily_reminder,
        CronTrigger(hour=8, minute=0, timezone=ET),
        id="daily_reminder",
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduler started - daily reminders at 8:00 AM ET")

    # Check if we missed today's reminder (e.g., due to restart)
    await check_and_send_missed_reminder()


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

    if not ATTIO_API_KEY:
        print("Warning: ATTIO_API_KEY not found in environment variables")
        print("The bot will start but won't have CRM access until configured")

    client.run(DISCORD_TOKEN)
