import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from core.antispam import rate_limit_check
from database import Database
from util.embeds import ErrorEmbed, PaginatedTextTable
from util.requests import request
from util.uuid import get_uuid_from_name


class History(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(name="history", description="Shows the guild membership history of a player.")
    @app_commands.describe(username="The player's username")
    @rate_limit_check()
    async def history(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        uuid = await get_uuid_from_name(username, interaction)
        if not uuid:
            return await interaction.followup.send(embed=ErrorEmbed("Player not found."))

        join_logs = await Database.fetch(
            "SELECT * FROM guild_join_log WHERE uuid=%s ORDER BY date DESC", (uuid)
        )
        activity_logs = await Database.fetch(
            "SELECT * FROM activity_members WHERE uuid=%s ORDER BY timestamp DESC", (uuid)
        )

        if not join_logs and not activity_logs:
            return await interaction.followup.send(embed=ErrorEmbed("No guild history found for this player."))

        combined = []
        for entry in join_logs:
            try:
                combined.append((entry["old"], entry["old_rank"] or 'N/A', int(entry["date"]), True))  # True = joined log
            except:
                pass
        for entry in activity_logs:
            try:
                combined.append((entry["guild"], 'N/A', int(entry["timestamp"]), False))
            except:
                pass

        combined.sort(key=lambda x: x[2], reverse=True)

        merged = []
        seen = set()
        for i, entry in enumerate(combined):
            if i in seen:
                continue
            for j in range(i+1, len(combined)):
                if abs(entry[2] - combined[j][2]) < 3600:
                    seen.add(j)
            merged.append(entry)
        
        history = []
        current_guild = None
        earliest = float("inf")

        for guild, rank, timestamp, is_joined in merged:
            earliest = min(earliest, timestamp)

            if current_guild is None:
                history.append([guild, rank, None, None])
                current_guild = guild
            elif guild != current_guild:
                if history:
                    history[-1][3] = timestamp
                history.append([guild, rank, timestamp, None])
                current_guild = guild

        if history and history[-1][3] is None:
            history[-1][3] = earliest

        try:
            api_data = await request(f"https://api.wynncraft.com/v3/player/{username}?fullResult", use_wynn_auth=True)
            guild_info = api_data.get("guild")
            if guild_info:
                api_guild = guild_info.get("name")
                api_rank = guild_info.get("rank", "N/A")
                if history and history[0][0] != api_guild:
                    history.insert(0, [api_guild, api_rank, None, history[0][2]])
                elif history and history[0][0] == api_guild:
                    history[0][1] = api_rank
        except Exception:
            pass

        rows = []
        for guild, rank, leave, join in history:
            join_str = datetime.fromtimestamp(join).strftime("%d %b %Y %H:%M") if join else "N/A"
            leave_str = datetime.fromtimestamp(leave).strftime("%d %b %Y %H:%M") if leave else "N/A"
            rows.append([guild, rank, join_str, leave_str])

        await PaginatedTextTable.send(
            interaction,
            ["Guild", "Rank", "Join Date", "Leave Date"],
            rows,
            title=f"Guild History of {username}",
            footer="Membership tracking updated 29 Sep 2026. Most entries at this date will be prior to it.",
            rows_per_page=15
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(History(bot))
