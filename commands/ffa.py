import discord, os

from discord.ext import commands
from discord import app_commands, File

from core.config import config

FFA_MAPS_DIR = "assets/ffa_maps"



def format_label(filename: str) -> str:
    name, _ = os.path.splitext(filename)
    return name.replace("_", " ").title()


class FFAMapSelect(discord.ui.Select):

    def __init__(self, author: discord.User):
        self.author = author
        files = [f for f in os.listdir(FFA_MAPS_DIR)]
        options = [discord.SelectOption(label=format_label(f), value=f) for f in files]

        super().__init__(
            placeholder="Select an FFA map to view...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(
                "Only the command user can use this menu.", ephemeral=True
            )

        selected_file = self.values[0]
        file_path = os.path.join(FFA_MAPS_DIR, selected_file)

        if not os.path.isfile(file_path):
            return await interaction.response.send_message("Map not found.", ephemeral=True)

        label = format_label(selected_file)
        with open(file_path, "rb") as f:
            file = File(f, filename=selected_file)

        embed = discord.Embed(
            title=f"{label} FFA Map",
            color=discord.Color.blue()
        )
        embed.set_image(url=f"attachment://{selected_file}")

        await interaction.response.edit_message(
            embed=embed,
            attachments=[file],
            view=self.view
        )



class FFAMapView(discord.ui.View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=60)
        self.add_item(FFAMapSelect(author))

class FFA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(name="ffa", description="Browse and view FFA maps.")
    async def ffa(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Select a map",
            description="Use the dropdown below to view an FFA map",
            color=discord.Color.blue()
        )
        view = FFAMapView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot: commands.Bot):
    cog = FFA(bot)
    await bot.add_cog(cog)

    existing_global = bot.tree.get_command("ffa")
    if existing_global:
        bot.tree.remove_command("ffa")

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.ffa, guild=guild)
