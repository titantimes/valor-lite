import discord, time

from discord.ext import commands
from discord import app_commands

from core.config import config
from database import Database
from util.embeds import ErrorEmbed, InfoEmbed
from util.roles import is_ANO_chief
from util.uuid import get_uuid_from_name


class Admin(commands.GroupCog, name="admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(
        name="give_ticket_bonuses",
        description="Manually add ticket bonuses to a player."
    )
    @app_commands.describe(
        username="Player username to receive the bonus",
        value="Bonus ticket amount to assign"
    )
    async def give_ticket_bonuses(
        self,
        interaction: discord.Interaction,
        username: str,
        value: int
    ):
        if not is_ANO_chief(interaction.user.roles):
            return await interaction.response.send_message(
                embed=ErrorEmbed("You do not have permission to use this command."),
                ephemeral=True
            )

        await interaction.response.defer()

        uuid = await get_uuid_from_name(username, interaction)
        if not uuid:
            return await interaction.followup.send(
                embed=ErrorEmbed("Could not find UUID for this username.")
            )

        await Database.fetch(
            "INSERT INTO ticket_bonuses (uuid, ticket_bonus, timestamp) VALUES (%s, %s, %s)",
            (uuid, value, str(time.time()))
        )

        embed = InfoEmbed(
            title="Ticket Bonus Added",
            description=f"Successfully added **{value}** tickets to **{username}** (`{uuid}`)."
        )
        await interaction.followup.send(embed=embed)



async def setup(bot: commands.Bot):
    cog = Admin(bot)
    await bot.add_cog(cog)
    existing_global = bot.tree.get_command("admin")
    if existing_global:
        bot.tree.remove_command("admin")

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.give_ticket_bonuses, guild=guild)
