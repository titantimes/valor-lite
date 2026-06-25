import discord, logging
from discord.ext import commands

from core.config import config
from core.logging import setup_logging
from database import Database



class ValorBot(commands.Bot):
    """
    Custom Discord bot class for the Valor project.
    
    This bot is designed to use slash commands only (no text commands) 
    and manages multiple extensions (cogs) for modular command organization.
    
    Responsibilities:
    - Initialize with required Discord intents.
    - Load and manage extensions.
    - Sync slash commands to configured guilds.
    - Handle database connection pooling.
    """

    def __init__(self):
        """
        Initialize the ValorBot with no Discord intents and no default help command.
        """
        intents = discord.Intents.none()
        intents.guilds = True  # Required for getting user roles

        super().__init__(
            command_prefix=None,  # Slash-only, no text prefix at all
            intents=intents,
            help_command=None,  # Disables the default text help command
            log_handler=None,   # Logging handled externally
            allowed_mentions=discord.AllowedMentions(roles=True)  # Only allow role mentions
        )


    async def setup_hook(self):
        """
        Discord.py lifecycle hook.
        
        Called once before the bot is ready:
        - Loads all extensions (command modules and listeners).
        - Syncs slash commands globally.
        - Initializes the database connection pool.
        """
        await self.load_extensions()
        await self.tree.sync()
        await Database.init_pool()


    async def load_extensions(self):
        """
        Loads all bot extensions (modules containing commands, listeners, or services).
        
        If an extension fails to load, the error is logged but does not stop other extensions from loading.
        """
        extensions = [
            # Command modules
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
                # Logs the specific error without crashing the bot startup
                logging.error(f"Failed to load extension {ext}: {e}")


    async def on_ready(self):
        """
        Event called when the bot has connected and is ready.
        
        - Logs the bot's identity.
        - Syncs slash commands to specific guilds from config.
        - Handles guild sync permission errors gracefully.
        """
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
        """
        Gracefully closes the bot.
        
        - Closes the database pool before shutting down the bot.
        """
        await Database.close_pool()
        await super().close()



def run_bot():
    """
    Initializes logging and runs the bot.
    
    Uses the testing token if in TESTING mode, otherwise the production token.
    """
    setup_logging()  # Set up log formatting and handlers

    bot = ValorBot()

    # Run with or without log handler depending on whether bot is in testing mode
    if config.TESTING:
        bot.run(config.TOKEN)
    else:
        bot.run(config.TOKEN, log_handler=None)
