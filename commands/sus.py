import discord,  datetime, time, uuid
from discord import app_commands, Embed
from discord.ext import commands

from core.antispam import rate_limit_check
from core.config import config
from database import Database
from util.embeds import ErrorEmbed
from util.requests import request
from util.uuid import get_uuid_from_name, detect_uuid_or_name, get_name_from_uuid


class Sus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sus", description="Checks if a Wynncraft player is suspicious.")
    @rate_limit_check()
    async def sus(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()
        input_type = detect_uuid_or_name(username)
        if input_type == "uuid":
            id = username
            name = await get_name_from_uuid(username)
        elif input_type == "name":
            id = await get_uuid_from_name(username, interaction)
            name = username
        else:
            return await interaction.followup.send(embed=ErrorEmbed("Invalid input."))

        if not id:
            return await interaction.followup.send(embed=ErrorEmbed("Player not found."))

        dashed_uuid = str(uuid.UUID(hex=id))
        hypixel_data = await request(f"https://api.hypixel.net/player?uuid={id}", headers={"API-Key": config.HYPIXEL_API_KEY})
        hypixel_join = None
        try:
            if hypixel_data and hypixel_data["success"] and hypixel_data["player"] and hypixel_data["player"]["firstLogin"]:
                hypixel_join = float(int(hypixel_data["player"]["firstLogin"] / 1000))
            else:
                hypixel_join = time.time()
        except KeyError:
            hypixel_join = time.time()

        wynn_data = await request(f"https://api.wynncraft.com/v3/player/{dashed_uuid}?fullResult", use_wynn_auth=True)

        try:
            if "username" not in wynn_data:
                return await interaction.followup.send(embed=ErrorEmbed("Wynn API Issue"))
        except TypeError:
            return await interaction.followup.send(embed=ErrorEmbed("Player has never logged onto Wynncraft."))

        try:
            wynn_join = wynn_data["firstJoin"].split("T")[0]

            wynn_join_timestamp = time.mktime(datetime.datetime.strptime(wynn_join, "%Y-%m-%d").timetuple())

            wynn_rank = wynn_data["supportRank"]

            try:
                wynn_level = sum([character["level"] for _, character in wynn_data["characters"].items()])
            except AttributeError:
                wynn_level = "API Hidden"

            wynn_playtime = wynn_data["playtime"]

            wynn_quest = wynn_data["globalData"]["completedQuests"]
        except KeyError:
            return await interaction.followup.send(embed=ErrorEmbed("Hidden player profile."))

        first_seen = min(hypixel_join, wynn_join_timestamp) if hypixel_join else wynn_join_timestamp

        first_seen_time = datetime.date.fromtimestamp(first_seen).strftime("%Y-%m-%d")
        first_seen_sus = round(max(0, (time.time() - first_seen - 94672800) * -1) * 100 / 94672800, 1)

        wynn_join_sus = round(max(0, (time.time() - wynn_join_timestamp - 63072000) * -1) * 100 / 63072000, 1)

        try:
            wynn_level_sus = round(max(0, (wynn_level - 210) * -1) * 100 / 210, 1)
        except:
            wynn_level_sus = 100.0

        wynn_playtime_sus = round(max(0, (wynn_playtime - 800) * -1) * 100 / 800, 1)

        wynn_quest_sus = round(max(0, (wynn_quest - 150) * -1) * 100 / 150, 1)

        query = "SELECT * FROM player_blacklist WHERE uuid=%s"
        blacklisted = await Database.fetch(query, (dashed_uuid))
        if blacklisted:
            blacklisted = "**BLACKLISTED**"
            blacklisted_sus = 100.0
        else:
            blacklisted = "False"
            blacklisted_sus = 0

        if wynn_rank in ["veteran", "champion", "hero", "heroplus", "vipplus"]:
            wynn_rank_sus = 0.0 
        elif wynn_rank == "vip":
            wynn_rank_sus = 25.0
        else:
            wynn_rank_sus = 50.0

        overall_sus = round(
            (first_seen_sus + wynn_join_sus + wynn_level_sus + wynn_playtime_sus + wynn_quest_sus + wynn_rank_sus) / 6, 2
        )

        embed = Embed(
            title=f"Suspiciousness of {name}: {overall_sus}%",
            description="The rating is based on the following components:",
            color=discord.Color.green()
        )

        embed.set_thumbnail(url=f"https://visage.surgeplay.com/bust/512/{id}.png?y=-40")

        embed.add_field(name="Wynncraft Join Date", value=f"{wynn_join}\n{wynn_join_sus}%", inline=True)
        embed.add_field(name="Wynncraft Playtime", value=f"{wynn_playtime} hours\n{wynn_playtime_sus}%", inline=True)
        embed.add_field(name="Wynncraft Level", value=f"{wynn_level}\n{wynn_level_sus}%", inline=True)
        embed.add_field(name="Wynncraft Quests", value=f"{wynn_quest}\n{wynn_quest_sus}%", inline=True)
        embed.add_field(name="Wynncraft Rank", value=f"{wynn_rank}\n{wynn_rank_sus}%", inline=True)
        embed.add_field(name="Minecraft First Seen", value=f"{first_seen_time}\n{first_seen_sus}%", inline=True)

        if blacklisted != "False":
            overall_sus = 100.0
            embed.color = discord.Color.red()
            embed.title = f"Suspiciousness of {name}: {overall_sus}% \n ⚠ Player is blacklisted ⚠"
            embed.add_field(name="Blacklisted?", value=f"{blacklisted}\n{blacklisted_sus}%", inline=True)

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Sus(bot))
