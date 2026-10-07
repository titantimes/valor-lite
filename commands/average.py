import discord

from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from database import Database
from util.embeds import ErrorEmbed, PaginatedTextTableEmbed
from util.guilds import guild_names_from_tags
from util.ranges import RangeTooLargeError, get_range_from_string


class AvgCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(
        name="average",
        description="Averages of guild members online over a time range."
    )
    @app_commands.describe(
        guilds="Filter by guild tags (comma-separated)",
        range="Number of days ago, or a range like '0,7'",
    )
    @rate_limit_check()
    async def average(
        self,
        interaction: discord.Interaction,
        guilds: str = None,
        range: str = "7"
    ):
        await interaction.response.defer()

        try:
            range_values = await get_range_from_string(range)
        except RangeTooLargeError:
            return await interaction.followup.send(
                embed=ErrorEmbed("Range exceeds maximum range of 50 days.")
            )

        if not range_values:
            return await interaction.followup.send(
                embed=ErrorEmbed("Invalid range input")
            )
        
        left_days, right_days = range_values

        query = (
            "SELECT guild, ROUND(AVG(count), 1) AS avg_count "
            "FROM guild_member_count "
            "WHERE time >= %s AND time <= %s"
        )
        params = [int(left_days), int(right_days)]
        unidentified = []

        if guilds:
            tags = [tag.strip() for tag in guilds.split(",") if tag.strip()]
            names, _ = await guild_names_from_tags(tags)

            if not names:
                return await interaction.followup.send(
                    embed=ErrorEmbed(f"Unknown guilds: {' '.join(unidentified)}")
                )

            query += f" AND guild IN ({','.join(['%s'] * len(names))})"
            params.extend(names)

        query += " GROUP BY guild ORDER BY avg_count DESC LIMIT 50"

        rows = await Database.fetch(query, params)

        if not rows:
            return await interaction.followup.send(
                embed=ErrorEmbed("No data available in the given range.")
            )

        table = [[row["guild"], f"{row['avg_count']:.1f}"] for row in rows]

        await PaginatedTextTableEmbed.send(
            interaction,
            ["Guild", "Avg Players Online"],
            table,
            title=f"Average Member Count ({range or '7 days'})",
            rows_per_page=25
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AvgCog(bot))
