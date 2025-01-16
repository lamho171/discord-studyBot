import ssl
import certifi
import aiohttp
import asyncio

async def test_ssl():
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    url = "https://discord.com/api/v10/users/@me"  # Discord API endpoint
    headers = {
        "Authorization": f"Bot {YOUR_BOT_TOKEN}",
        "User-Agent": "DiscordBot (https://example.com, v1.0)",
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, ssl=ssl_context, headers=headers) as response:
                print(f"Response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print("Response data:", data)
                else:
                    print("Failed to fetch:", await response.text())
        except Exception as e:
            print(f"SSL test failed: {e}")

YOUR_BOT_TOKEN = "MTMyNTI1NjEzNDgwMTYyMTAwNQ.GwN1hH.uPV-2f4ugt6FdNZj4_b7Aq9e3B5OWmM-v_nb_k"

asyncio.run(test_ssl())
