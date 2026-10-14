import discord, time, logging

from discord.ext import commands
from discord import app_commands

from database import Database


class CommandLogger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command
    ):
        try:
            server_id = str(interaction.guild.id) if interaction.guild else 0
            server_name = interaction.guild.name if interaction.guild else "DMs"
            discord_id = str(interaction.user.id)
            discord_name = str(interaction.user)

            cmd_name = command.qualified_name  # e.g. "utilities reset_times"
            options = vars(interaction.namespace) if interaction.namespace else {}

            full_command = f"/{cmd_name} " + " ".join(
                f"{k}={v}" for k, v in options.items() if v is not None
            )

            ts = int(time.time())

            # Insert into DB
            await Database.fetch(
                """
                INSERT INTO command_queries 
                    (server_id, server_name, discord_id, discord_name, command, full_command, time)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    server_id,
                    server_name,
                    discord_id,
                    discord_name,
                    cmd_name,
                    full_command,
                    ts,
                )
            )

        except Exception as e:
            logging.warning(f"Failed to log command: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(CommandLogger(bot))
