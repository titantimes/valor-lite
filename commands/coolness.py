import discord

from discord.ext import commands
from discord import app_commands

from core.antispam import rate_limit_check
from core.settings import SettingsManager
from database import Database
from util.embeds import ErrorEmbed, PaginatedTextTableEmbed
from util.guilds import guild_names_from_tags
from util.ranges import get_range_from_string, RangeTooLargeError



class Coolness(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(
        name="coolness",
        description="Shows your playtime in hours"
    )
    @app_commands.describe(
        guilds="Filter by guild tags (comma-separated)",
        range="Number of days ago, or a range like '0,7' (defaults to 7 days)",
        order="The order to sort in (descending by default)",
    )
    @app_commands.choices(order=[
        app_commands.Choice(name="Ascending", value="ASC"),
        app_commands.Choice(name="Descending", value="DESC"),
    ])
    @rate_limit_check()
    @app_commands.guild_only()
    async def coolness(
        self,
        interaction: discord.Interaction,
        guilds: str = None,
        range: str = "7",
        order: app_commands.Choice[str] = "DESC"
    ):
        await interaction.response.defer()

        if guilds:
            tags = [tag.strip() for tag in guilds.split(",") if tag.strip()]
            guild_names, _ = await guild_names_from_tags(tags)
        else:
            guild_name = SettingsManager("guild", interaction.guild.id).get("guild_name")
            guild_tag = SettingsManager("guild", interaction.guild.id).get("guild_tag")

            if guild_name and guild_tag:
                guild_names = [guild_name]
            else:
                return await interaction.followup.send(embed=ErrorEmbed("Default guild name and tag have not been set. Please get an admin to run `/guild_settings` and set it."))
        
        try:
            order = order.value
        except (ValueError, AttributeError):
            pass
        if not guild_names:
            return await interaction.followup.send(
                embed=ErrorEmbed("Guilds not found."),
                ephemeral=True
            )

        try:
            range = await get_range_from_string(range)
        except RangeTooLargeError:
            return await interaction.followup.send(
                embed=ErrorEmbed("Range exceeds maximum range of 50 days.")
            )

        if not range:
            return await interaction.response.send_message(
                embed=ErrorEmbed("Invalid range input"),
                ephemeral=True
            )
        
        start_ts, end_ts = range

        placeholders = "(" + ",".join(["%s"] * len(guild_names)) + ")"

        query = f'''
SELECT A.guild, B.name, A.coolness
FROM
  (SELECT guild, uuid, COUNT(*) as coolness 
  FROM 
    activity_members
    WHERE guild IN {placeholders}
    AND timestamp >= %s AND timestamp <= %s
    GROUP BY uuid, guild) A
  JOIN uuid_name B ON A.uuid=B.uuid  
ORDER BY A.coolness {order};
'''

        values = list(guild_names) + [str(start_ts), str(end_ts)]
        rows = await Database.fetch(query, values)
        if not rows:
            return await interaction.followup.send(
                embed=ErrorEmbed("No results found."),
                ephemeral=True
            )

        table_rows = [
            (entry["guild"], entry["name"], f"{entry['coolness']:,}")
            for entry in rows
        ]

        await PaginatedTextTableEmbed.send(
            interaction,
            ["Guild", "Username", "Hours Online"],
            table_rows,
            title=(
                f"Coolness Leaderboard for "
                f"{', '.join(guild_names) if len(guild_names) > 1 else guild_names[0]}"
            ),
            rows_per_page=25
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Coolness(bot))
