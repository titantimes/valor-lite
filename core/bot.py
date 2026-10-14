import discord, logging
from discord.ext import commands

from core.config import config
from core.logging import setup_logging
from database import Database



class ValorBot(commands.Bot):
    def __init__(self):

        intents = discord.Intents.none()
        intents.guilds = True

        super().__init__(
            command_prefix=None,  #make prefix ver at some point
            intents=intents,
            help_command=None,
            log_handler=None,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )


    async def setup_hook(self):
        await self.load_extensions()
        await self.tree.sync()
        await Database.init_pool()


    async def load_extensions(self):
        extensions = [
            #Commands
            "commands.admin",
            "commands.annihilation_tracker",
            "commands.average",
            "commands.blacklist",
            "commands.completion",
            "commands.coolness",
            "commands.ffa",
            "commands.graids",
            "commands.graids2",
            "commands.guild",
            "commands.help",
            "commands.history",
            "commands.leaderboard",
            "commands.map",
            "commands.oceantrials",
            "commands.pings",
            "commands.pingraid",
            "commands.pools",
            "commands.profile",
            "commands.settings",
            "commands.sus",
            "commands.tickets",
            "commands.uniform",
            "commands.uptime",
            "commands.utilities",
            "commands.warcount",
            # Event listeners
            "listeners.command_logger",
            "listeners.errors",
            # Background services
            "services.weekly_ticket_post",
            "services.territory_tracker"
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                logging.info(f"Loaded extension: {ext}")
            except Exception as e:
                logging.error(f"Failed to load extension {ext}: {e}")


    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")

        for guild_id in config.ANO_COMMANDS_GUILD_IDS:
            guild = discord.Object(id=int(guild_id))
            try:
                await self.tree.sync(guild=guild)
                logging.info(f"Synced commands to guild {guild.id}")
            except discord.Forbidden:
                logging.warning(f"Missing access to sync commands in guild {guild.id}")

        logging.info("Successfully synced all slash commands")
        logging.info("Bot is ready")


    async def close(self):
        await Database.close_pool()
        await super().close()



def run_bot():
    setup_logging()
    bot = ValorBot()
    if config.TESTING:
        bot.run(config.TOKEN)
    else:
        bot.run(config.TOKEN, log_handler=None)
