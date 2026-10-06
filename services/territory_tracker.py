import asyncio, logging, discord, requests

from datetime import datetime, timedelta
from discord.ext import commands, tasks

from core.config import Config
from util.mappings import FFA_TERRITORIES


WYNN_API_URL = "https://api.wynncraft.com/v3/guild/list/territory"
ATHENA_API_URL = "https://athena.wynntils.com/cache/get/territoryList"



def format_timedelta(td: timedelta) -> str:
    seconds = int(td.total_seconds())
    periods = [
        ('d', 86400),
        ('h', 3600),
        ('m', 60),
        ('s', 1)
    ]
    
    parts = []
    for name, size in periods:
        if seconds >= size:
            value, seconds = divmod(seconds, size)
            parts.append(f"{value}{name}")
            
    return " ".join(parts[:2])



def normalize_territories(data: dict) -> dict:
    if isinstance(data.get("territories"), dict):
        data = data["territories"]

    output = {}
    for territory, info in data.items():
        if not isinstance(info, dict) or "acquired" not in info:
            continue
        guild = info.get("guild")
        if isinstance(guild, dict):
            name, prefix = guild.get("name"), guild.get("prefix")
        else:
            name, prefix = guild, info.get("guildPrefix")
        output[territory] = {
            "territory": territory,
            "guild": name or "None",
            "guildPrefix": prefix or "None",
            "acquired": info["acquired"],
        }
    return output


def fetch_territory_data() -> dict:
    for source, url in (("Athena", ATHENA_API_URL), ("Wynn", WYNN_API_URL)):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = normalize_territories(response.json())
            if data:
                return data
            logging.warning(f"Territory Tracker: {source} API returned no territories")
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Error fetching territory data from {source} API: {e}")
    return {}


def create_terrchange_embed(old_territory, new_territory, for_ano: bool = False):
    embed = discord.Embed(
        title=f"Territory Captured: {new_territory['territory']}", 
        color=0x007bff  
    )
    embed.add_field(name="Previous Owner", value=f"{old_territory['guild']} ({old_territory['guildPrefix']})", inline=True)
    embed.add_field(name="New Owner", value=f"{new_territory['guild']} ({new_territory['guildPrefix']})", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    held_time = datetime.fromisoformat(new_territory["acquired"]) - datetime.fromisoformat(old_territory["acquired"])
    held_time_str = format_timedelta(held_time)
    embed.add_field(name="Held for", value=held_time_str, inline=True)
    embed.add_field(name="FFA Territory", value="Yes" if new_territory["territory"] in FFA_TERRITORIES else "No", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.set_footer(text=f"Acquired on: {datetime.fromisoformat(new_territory['acquired']).strftime('%d/%m/%Y %I:%M %p')}")
    return embed



class TerritoryTrackerService(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.territory_data = fetch_territory_data()  # Store the latest territory data
        self.terryitory_tracker_loop.start()


    def cog_unload(self):
        self.terryitory_tracker_loop.cancel()


    @tasks.loop(minutes=1)  # Repeat every minute to check for updates
    async def terryitory_tracker_loop(self):
        try:
            await self._track_once()
        except Exception:
            logging.exception("Territory Tracker: iteration failed")


    async def _track_once(self):
        updated_data = await asyncio.to_thread(fetch_territory_data)
        if not updated_data:
            logging.warning("Territory Tracker: no data fetched, keeping previous snapshot")
            return

        if not self.territory_data:
            self.territory_data = updated_data
            return

        changed_territories = []
        for territory, info in updated_data.items():
            old = self.territory_data.get(territory)
            if old is not None and old.get("guild") != info.get("guild"):
                changed_territories.append(info)

        if changed_territories:
            channel = self.bot.get_channel(Config.TERRITORY_TRACKER_CHANNEL_ID)
            ano_channel = self.bot.get_channel(Config.ANO_TERRITORY_TRACKER_CHANNEL_ID)
            for territory in changed_territories:
                old = self.territory_data[territory["territory"]]
                try:
                    for_ano = territory.get("guildPrefix") == "ANO" or old.get("guildPrefix") == "ANO"
                    embed = create_terrchange_embed(old, territory, for_ano)
                    if for_ano and ano_channel:
                        await ano_channel.send(embed=embed)
                    if channel:
                        await channel.send(embed=embed)
                except Exception:
                    logging.exception(f"Territory Tracker: failed to post change for {territory.get('territory')}")

        self.territory_data = updated_data  # Update the stored data for the next loop iteration


    @terryitory_tracker_loop.before_loop
    async def before_ticket_post_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(TerritoryTrackerService(bot))
