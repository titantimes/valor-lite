import discord
from discord import app_commands
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="help",
        description="Get information about the bot and where to find support."
    )
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Embed setup
        embed = discord.Embed(
            title="⚔️ Valor Lite",
            url="https://titansvalor.org/",
            description=(
                "Valor Lite is the lightweight, distributable version of "
                "**Titans Valor's original Valor bot**.\n\n"
                "While some advanced features remain exclusive to the "
                "[Titans Valor Discord](https://discord.gg/h8XUHkR), "
                "Valor Lite brings many of the core tools to everyone."
            ),
            colour=discord.Color.blurple()
        )

        embed.set_thumbnail(
            url="https://media.discordapp.net/stickers/861507133232250940.webp?size=320&quality=lossless"
        )

        embed.add_field(
            name="📢 Updates & Announcements",
            value="Join our discord server "
                  "for the latest news and feature updates.",
            inline=False
        )
        embed.add_field(
            name="🛠️ Support",
            value="Need help or found an issue? Report it [here](https://discordapp.com/channels/535603929598394389/733842585931481138). (<#733842585931481138>)",
            inline=False
        )

        embed.set_footer(
            text="Made and powered by Titans Valor",
            icon_url="https://media.discordapp.net/stickers/861507133232250940.webp?size=320&quality=lossless"
        )

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
