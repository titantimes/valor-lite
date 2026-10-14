import discord, math

from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from core.config import config
from database import Database
from util.embeds import ErrorEmbed, PaginatedTextTableEmbed



def do_ticket_math(value: float, base: float) -> int:
    return math.floor(math.log((math.floor(float(value) + 0.5) / base) + 1, 1.05) + 0.5)


async def get_tickets():
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
    res = await Database.fetch(query)

    data = []

    for entry in res:
        name = entry["name"]

        war = do_ticket_math(entry["wars_gain"], 10)                  # Wars base = 10
        gxp = do_ticket_math(entry["gxp_gain"], 100_000_000)          # Guild XP base = 100 million
        raids = do_ticket_math(entry["raids_gain"], 35)               # Raids base = 35
        bonus = int(entry["ticket_bonus"])                            # Bonus tickets from DB
        total = war + gxp + raids + bonus                             # Total ticket count

        if total != 0:
            data.append((name, str(war), str(gxp), str(raids), bonus, total))

    data.sort(key=lambda x: x[-1], reverse=True)
    rows = [[f"{i+1})", name, war, gxp, raids, bonus, total] for i, (name, war, gxp, raids, bonus, total) in enumerate(data)]

    return rows



class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="tickets", description="View or update this week's ticket leaderboard.")
    @rate_limit_check()
    async def tickets(self, interaction: discord.Interaction):

        await interaction.response.defer()
        rows = await get_tickets()
        if not rows:
            return await interaction.followup.send(embed=ErrorEmbed("No ticket data found."))

        await PaginatedTextTableEmbed.send(
            interaction,
            ["", "Name", "War", "GXP", "Raid", "Bonus", "Total"],
            rows,
            title="Titans Valor Ticket Leaderboard",
            rows_per_page=20
        )



async def setup(bot: commands.Bot):
    cog = Tickets(bot)
    await bot.add_cog(cog)
    existing_global = bot.tree.get_command("tickets")
    if existing_global:
        bot.tree.remove_command("tickets")

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.tickets, guild=guild)
