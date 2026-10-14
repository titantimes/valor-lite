import discord

from discord.ext import commands
from discord import app_commands, Interaction

from core.config import config
from util.embeds import ErrorEmbed
from util.roles import is_ANO_military_member


PING_ROLES = {
    "ffa": {
        "name": "FFA",
        "description": "FFA run",
        "emoji": "⚔️",
        "role_id": 892884695199666187
    },
    "dps": {
        "name": "DPS",
        "description": "DPS players needed",
        "emoji": "💥",
        "role_id": 892885182300954624
    },
    "guardian": {
        "name": "Guardian",
        "description": "Guardian needed",
        "emoji": "🛡️",
        "role_id": 892884953996591164
    },
    "healer": {
        "name": "Healer",
        "description": "Healer needed",
        "emoji": "❤️",
        "role_id": 892885381744320532
    },
    "trg": {
        "name": "Royal Guard",
        "description": "Royal Guard Ping",
        "emoji": "👑",
        "role_id": 683785435117256939
    },
}



class PingsButton(discord.ui.Button):
    def __init__(self, ping_id: str, author_id: int):
        self.ping_id = ping_id
        self.author_id = author_id
        data = PING_ROLES[ping_id]
        super().__init__(emoji=data["emoji"], style=discord.ButtonStyle.secondary)


    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the user who used the command can interact with these buttons.",
                ephemeral=True
            )

        if not is_ANO_military_member(interaction.user.roles):
            return await interaction.response.send_message(
                embed=ErrorEmbed("No Permissions"), ephemeral=True
            )

        data = PING_ROLES[self.ping_id]
        await interaction.response.send_message(f"<@&{data['role_id']}>", ephemeral=False)



class PingsButtonView(discord.ui.View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=30)
        for key in PING_ROLES:
            self.add_item(PingsButton(key, author.id))



class Pings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pings", description="Send a role ping using buttons.")
    async def pings(self, interaction: Interaction):
        if not is_ANO_military_member(interaction.user.roles):
            return await interaction.response.send_message(
                embed=ErrorEmbed("No Permissions"),
                ephemeral=True
            )

        embed = discord.Embed(
            title="Available Role Pings:",
            description=(
                "\n".join(
                    f"{data['emoji']} **|     {data['name']}** — {data['description']}"
                    for data in PING_ROLES.values()
                ) + "\n\n**Click a button to ping the role:**"
            ),
            color=0x00FFFF
        )

        view = PingsButtonView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)



async def setup(bot: commands.Bot):
    cog = Pings(bot)
    await bot.add_cog(cog)
    existing_global = bot.tree.get_command("pings")
    if existing_global:
        bot.tree.remove_command("pings")

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.pings, guild=guild)
