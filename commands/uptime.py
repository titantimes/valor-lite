import discord, time

from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from util.embeds import TextTableEmbed
from util.requests import request


UPTIME_API_URL = "https://athena.wynntils.com/cache/get/serverList"



class Uptime(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(name="uptime", description="Shows the uptime of all active Wynncraft worlds.")
    @rate_limit_check()
    async def uptime(self, interaction: discord.Interaction):
        await interaction.response.defer()

        data = await request(UPTIME_API_URL)

        servers = data.get("servers", {})

        now = int(time.time() * 1000)

        result = []
        for server, info in servers.items():
            ts = info.get("firstSeen")
            if not ts:
                continue

            uptime_ms = now - ts
            uptime_s = uptime_ms // 1000

            hours, minutes = divmod(uptime_s // 60, 60)
            uptime_str = f"{hours}h {minutes}m"

            player_count = len(info.get("players", []))
            players_str = f"{player_count}/55"

            result.append([server, uptime_str, players_str])

        result.sort(key=lambda x: int(x[1].split("h")[0]) * 60 + int(x[1].split("h")[1].split("m")[0]), reverse=True)

        headers = ["World", "Uptime", "Players"]

        embed = TextTableEmbed(headers, result, title="Wynncraft World Uptimes", footer=f"{len(result)} worlds are currently online.")

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Uptime(bot))
