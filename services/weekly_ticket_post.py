import logging, asyncio, datetime

from discord.ext import commands, tasks

from core.config import config
from util.embeds import PaginatedTextTableEmbed


TARGET_WEEKDAY = 6  # Sunday (0 = Monday, 6 = Sunday)
TARGET_HOUR = 17    # 5 PM
TARGET_MINUTE = 0



class WeeklyTicketPostService(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ticket_post_loop.start()


    def cog_unload(self):
        self.ticket_post_loop.cancel()


    @tasks.loop(hours=168)
    async def ticket_post_loop(self):
        from commands.tickets import get_tickets

        channel = self.bot.get_channel(config.TITAN_CHAT_CHANNEL_ID)
        if channel is None:
            return logging.error("WeeklyTicketPostService: Channel not found for posting tickets.")

        rows = await get_tickets()

        if not rows:
            await channel.send("No ticket data found this week.")
            return

        headers = ["", "Name", "War", "GXP", "Raid", "Bonus", "Total"]

        view = PaginatedTextTableEmbed(
            headers,
            rows,
            title="Titans Valor Ticket Leaderboard",
            rows_per_page=20,
            timeout=3600
        )
        embed = view.format_page(0)

        view.message = await channel.send(embed=embed, view=view)


    @ticket_post_loop.before_loop
    async def before_ticket_post_loop(self):
        await self.bot.wait_until_ready()

        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        target = now.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)

        days_ahead = (TARGET_WEEKDAY - now.weekday()) % 7
        if days_ahead == 0 and now >= target:
            days_ahead = 7

        target += datetime.timedelta(days=days_ahead)
        wait_seconds = (target - now).total_seconds()

        logging.info(f"Ticket Post Service - Waiting {wait_seconds / 60:.2f} minutes until next scheduled run.")
        await asyncio.sleep(wait_seconds)

async def setup(bot: commands.Bot):
    await bot.add_cog(WeeklyTicketPostService(bot))
