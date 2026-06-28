import discord, math

from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from core.config import config
from database import Database
from util.embeds import ErrorEmbed, PaginatedTextTableEmbed



def do_ticket_math(value: float, base: float) -> int:
    """
    Converts a raw stat value into a ticket score using a logarithmic scale.
    The formula applies a base-1.05 logarithm after normalizing the input,
    then floors the result to produce an integer ticket value.

    Args:
        value (float): The raw gain value (e.g., wars gained, gxp gained).
        base (float): The scaling base used for normalization.

    Returns:
        int: The calculated ticket score.
    """
    return math.floor(math.log((math.floor(float(value) + 0.5) / base) + 1, 1.05) + 0.5)


async def get_tickets():
    """
    Queries the database to compute ticket leaderboard entries for Titans Valor guild members.

    Args:
        start_timestamp (float, optional): Unix timestamp filter to limit data to after this time.
                                           Defaults to None (no filter).

    Returns:
        list: Sorted list of tuples containing player ticket stats and totals.
              Each tuple: (name, war tickets, gxp tickets, raid tickets, bonus tickets, total tickets)
    """

    # SQL query to aggregate gains for wars, guild xp, raids, and bonuses per player this week
    query = f"""
SELECT 
    GMC.name,
    SUM(CASE WHEN PDR.label = 'g_wars' THEN PDR.delta ELSE 0 END) AS wars_gain,
    SUM(CASE WHEN PDR.label = 'gu_gxp' THEN PDR.delta ELSE 0 END) AS gxp_gain,
    SUM(CASE WHEN PDR.label IN ('g_The Canyon Colossus', "g_Orphion's Nexus of Light",'g_The Wartorn Palace', 'g_Nest of the Grootslangs', "g_The Nameless Anomaly") THEN PDR.delta ELSE 0 END) AS raids_gain,
    COALESCE(MAX(TB.ticket_bonus), 0) AS ticket_bonus
FROM 
    guild_member_cache GMC
JOIN 
    uuid_name UN ON GMC.name = UN.name
JOIN 
    player_delta_record PDR ON UN.uuid = PDR.uuid
LEFT JOIN 
    (SELECT uuid, SUM(ticket_bonus) AS ticket_bonus
     FROM ticket_bonuses
     WHERE YEARWEEK(FROM_UNIXTIME(timestamp), 1) = YEARWEEK(CURDATE(), 1)
     GROUP BY uuid) TB ON UN.uuid = TB.uuid
WHERE 
    GMC.guild = "Titans Valor"
    AND YEARWEEK(FROM_UNIXTIME(PDR.time), 1) = YEARWEEK(CURDATE(), 1)
GROUP BY 
    GMC.name
"""

    # Execute the query
    res = await Database.fetch(query)

    data = []

    # Process each player's raw gains into ticket values using logarithmic scaling
    for entry in res:
        name = entry["name"]

        # Convert raw gains to ticket values using appropriate bases
        war = do_ticket_math(entry["wars_gain"], 10)                  # Wars base = 10
        gxp = do_ticket_math(entry["gxp_gain"], 100_000_000)          # Guild XP base = 100 million
        raids = do_ticket_math(entry["raids_gain"], 35)               # Raids base = 35
        bonus = int(entry["ticket_bonus"])                            # Bonus tickets from DB
        total = war + gxp + raids + bonus                             # Total ticket count

        # Only include players who earned tickets this week
        if total != 0:
            data.append((name, str(war), str(gxp), str(raids), bonus, total))

    # Sort leaderboard descending by total tickets
    data.sort(key=lambda x: x[-1], reverse=True)

    # Format rows for embed table: add rank, and convert numbers to strings for display
    rows = [[f"{i+1})", name, war, gxp, raids, bonus, total] for i, (name, war, gxp, raids, bonus, total) in enumerate(data)]

    return rows



class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="tickets", description="View or update this week's ticket leaderboard.")
    @rate_limit_check() # Prevent spam by rate limiting command usage per user
    async def tickets(self, interaction: discord.Interaction):
        """
        Slash command handler for viewing the Titans Valor ticket leaderboard.

        Args:
            interaction (discord.Interaction): The interaction object from Discord.
            range (str, optional): Time range filter (currently disabled).
        """
        # Defer response as this database query takes some time
        await interaction.response.defer()

        # Fetch ticket data with optional start timestamp filter
        rows = await get_tickets()

        # If no ticket data found, notify user
        if not rows:
            return await interaction.followup.send(embed=ErrorEmbed("No ticket data found."))

        # Send paginated embed with ticket leaderboard
        await PaginatedTextTableEmbed.send(
            interaction,
            ["", "Name", "War", "GXP", "Raid", "Bonus", "Total"],
            rows,
            title="Titans Valor Ticket Leaderboard",
            rows_per_page=20
        )



# Cog setup function for bot
async def setup(bot: commands.Bot):
    cog = Tickets(bot)
    await bot.add_cog(cog)

    # Remove existing global command to avoid duplicates
    existing_global = bot.tree.get_command("tickets")
    if existing_global:
        bot.tree.remove_command("tickets")

    # Manually register the command only for guilds that receive ANO commands
    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.tickets, guild=guild)
