import discord

from discord.ext import commands
from discord import app_commands, Interaction

from core.config import config
from util.embeds import ErrorEmbed


ACCESS_ROLES = [
    535609000193163274,
    703695379853606952,
]

RAID_PING_ROLES = {
    "raid1": {
        "name": "NOTG",
        "description": "Nest of The Grootslang",
        "emoji": "🪱",
        "role_id": 1331594711852650507,
    },
    "raid2": {
        "name": "NOL",
        "description": "Orphion's Nexus of Light",
        "emoji": "🌞",
        "role_id": 1331594539756158976,
    },
    "raid3": {
        "name": "TCC",
        "description": "The Canyon Colossus",
        "emoji": "🪨",
        "role_id": 1331594234544918569,
    },
    "raid4": {
        "name": "TNA",
        "description": "The Nameless Anomaly",
        "emoji": "💀",
        "role_id": 1331445256645775410,
    },
    "raid5": {
        "name": "TWP",
        "description": "The Wartorn Palace",
        "emoji": "🦋",
        "role_id": 1495438345202041032,
    },
}


def hasAccess(user_roles: list[discord.Role]) -> bool:
    if config.TESTING:
        return True

    urID = {role.id for role in user_roles}
    return not urID.isdisjoint(ACCESS_ROLES)


class PingRaidButton(discord.ui.Button):
    def __init__(self, ping_id: str, author_id: int):
        self.ping_id = ping_id
        self.author_id = author_id
        data = RAID_PING_ROLES[ping_id]
        super().__init__(emoji=data["emoji"], style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the user who used the command can interact with these buttons.",
                ephemeral=True,
            )

        if not hasAccess(interaction.user.roles):
            return await interaction.response.send_message(
                embed=ErrorEmbed("No Permissions"),
                ephemeral=True,
            )

        data = RAID_PING_ROLES[self.ping_id]
        await interaction.response.send_message(f"<@&{data['role_id']}>", ephemeral=False)


class PingRaidButtonView(discord.ui.View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=30)
        for key in RAID_PING_ROLES:
            self.add_item(PingRaidButton(key, author.id))


class PingRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pingraid", description="Send a raid ping using buttons.")
    async def pingraid(self, interaction: Interaction):
        if not hasAccess(interaction.user.roles):
            return await interaction.response.send_message(
                embed=ErrorEmbed("No Permissions"),
                ephemeral=True,
            )

        embed = discord.Embed(
            title="Available Raid Pings:",
            description=(
                "\n".join(
                    f"{data['emoji']} **|     {data['name']}** — {data['description']}"
                    for data in RAID_PING_ROLES.values()
                ) + "\n\n**Click a button to ping the role:**"
            ),
            color=0x00FFFF,
        )

        view = PingRaidButtonView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    cog = PingRaid(bot)
    await bot.add_cog(cog)

    existing_global = bot.tree.get_command("pingraid")
    if existing_global:
        bot.tree.remove_command("pingraid")

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.pingraid, guild=guild)