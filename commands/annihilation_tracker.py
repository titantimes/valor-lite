import discord, time, json, os, re, logging
from discord import app_commands, Interaction, ButtonStyle, Message
from discord.ext import commands, tasks
from discord.ui import View, Button

from core.config import config
from util.embeds import ErrorEmbed
from util.roles import is_ANO_high_rank


# Previous anni reported storage
ANNI_FILE = "storages/annihilation_tracker.json"
# Nice red embed
ANNI_EMBED_COLOR = 0x7A1507

class AnnihilationTracker(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot


    async def cog_load(self):
        self.reminderLoo.start()
    def cog_unload(self):
        self.reminderLoo.cancel()

    @tasks.loop(seconds=30)
    async def reminderLoo(self):
        try:
            await self.checkRemind()
        except Exception:
            logging.exception("Annihilation reminder check failed")

    @reminderLoo.before_loop
    async def reminderLoo_b(self):
        await self.bot.wait_until_ready()


    async def checkRemind(self):
        data = self.load_annihilation()
        timestamp = data.get("timestamp", 0)
        if not 0 < timestamp - time.time() <= 3600:
            return

        for guild_id, reminder in data.get("reminders", {}).items():
            if reminder.get("notified_timestamp") == timestamp:
                continue
            try:
                guild = self.bot.get_guild(int(guild_id))
                if guild is None:
                    continue
                channel = guild.get_channel(reminder["channel_id"])
                role = guild.get_role(reminder["role_id"])
                if channel is None or role is None or role.is_default():
                    continue
                permissions = channel.permissions_for(guild.me)
                if not (permissions.view_channel and permissions.send_messages):
                    continue
                if not role.mentionable and not permissions.mention_everyone:
                    continue
                await channel.send(
                    f"{role.mention} Annihilation starts <t:{timestamp}:R> (<t:{timestamp}:f>)!",
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False, users=False, roles=[role], replied_user=False
                    ),
                )
                latest = self.load_annihilation()
                current = latest.get("reminders", {}).get(guild_id)
                if current == reminder:
                    current["notified_timestamp"] = timestamp
                    self.save_tracker_data(latest)
            except Exception:
                logging.exception("Annihilation reminder failed for guild %s", guild_id)


    @app_commands.command(name="annihilation_reminder", description="Set the channel and role for Annihilation reminder.")
    @app_commands.guild_only()
    @app_commands.describe(
        channel="Channel where the reminder will be",
        role="Set the role to be pinged",
        enabled="Set to false to remove reminders",
    )
    async def annihilation_reminder(
        self, interaction: discord.Interaction,
        channel: discord.TextChannel = None, role: discord.Role = None, enabled: bool = True,
    ):
        if not is_ANO_high_rank(interaction.user.roles):
            return await interaction.response.send_message(
                embed=ErrorEmbed("You do not have permission to configure Annihilation reminders."),
                ephemeral=True,
            )
        data = self.load_annihilation()
        reminders = data.setdefault("reminders", {})
        guild_id = str(interaction.guild_id)
        if not enabled:
            reminders.pop(guild_id, None)
            self.save_tracker_data(data)
            return await interaction.response.send_message("Annihilation reminders disabled in this server.", ephemeral=True)
        if channel is None and role is None:
            reminder = reminders.get(guild_id)
            message = (
                f"Annihilation reminders: <#{reminder['channel_id']}> with <@&{reminder['role_id']}>."
                if reminder else "No Annihilation reminder is configured in this server. Select a channel and role to enable it."
            )
            return await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        if channel is None or role is None:
            return await interaction.response.send_message("Select both a channel and a role.", ephemeral=True)
        if channel.guild.id != interaction.guild_id or role.guild.id != interaction.guild_id or role.is_default():
            return await interaction.response.send_message("Select a channel and a role", ephemeral=True)
        permissions = channel.permissions_for(interaction.guild.me)
        if not (permissions.view_channel and permissions.send_messages):
            return await interaction.response.send_message("needs View Channel and Send Messages permissions.", ephemeral=True)
        if not role.mentionable and not permissions.mention_everyone:
            return await interaction.response.send_message("Role must be mentionable or grant Mention Everyone permission in that channel.", ephemeral=True)
        previous = reminders.get(guild_id, {})
        reminders[guild_id] = {
            "channel_id": channel.id,
            "role_id": role.id,
            "notified_timestamp": previous.get("notified_timestamp", 0),
        }
        self.save_tracker_data(data)
        await interaction.response.send_message(
            f"Annihilation reminders in {channel.mention}, pinging {role.mention}.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )


    def load_annihilation(self):
        if not os.path.exists(ANNI_FILE):
            return {}
        try:
            with open(ANNI_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Something wrong with the file — return empty data
            return {}

    def save_annihilation(self, timestamp: int):
        data = self.load_annihilation()
        data["timestamp"] = timestamp
        self.save_tracker_data(data)

    def save_tracker_data(self, data: dict):
        os.makedirs(os.path.dirname(ANNI_FILE), exist_ok=True)
        with open(ANNI_FILE, "w") as f:
            json.dump(data, f)

    @app_commands.command(name="annihilation", description="Check the next reported Annihilation World Event time.")
    async def annihilation(self, interaction: discord.Interaction):
        data = self.load_annihilation()
        now = int(time.time())
        timestamp = data.get("timestamp", 0)

        if not data or data.get("timestamp", 0) < now:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="Annihilation Tracker",
                    description=(
                        f"There is currently no Annihilation reported.\n\n"
                        f"Most recent Annie was at <t:{timestamp}:f> (<t:{timestamp}:R>)"
                    ),
                    color=ANNI_EMBED_COLOR
                ).set_footer(text=f"Did Annie wake up? Ask an ANO high rank to report it!")
            )

        return await interaction.response.send_message(
            embed=discord.Embed(
                title="Annihilation Tracker",
                description=f"Next Annihilation is at <t:{timestamp}:f> (<t:{timestamp}:R>)",
                color=ANNI_EMBED_COLOR
            ).set_footer(text=f"Is that time inaccurate? Report it to an ANO high rank!")
        )


    @app_commands.command(
        name="report_annihilation",
        description="Report or update the time of the next Annihilation event."
    )
    @app_commands.describe(
        time_until="Time until next Annihilation (e.g. '2h30m', '1h 45m') or 'none'"
    )
    async def report_annihilation(self, interaction: discord.Interaction, time_until: str):
        await interaction.response.defer()

        if not is_ANO_high_rank(interaction.user.roles):
            return await interaction.followup.send(
                embed=ErrorEmbed("You do not have permission to report an Annihilation time."),
                ephemeral=True
            )

        if time_until.lower() == "none":
            self.save_annihilation(0)
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="Annihilation Time Deleted",
                    description="Annihilation time has been deleted.",
                    color=ANNI_EMBED_COLOR
                )
            )

        match = re.match(
            r"(?:(\d+)h)?\s*(?:(\d+)m)?",
            time_until.replace(" ", ""),
            re.IGNORECASE
        )
        if not match:
            return await interaction.followup.send(
                embed=ErrorEmbed("Invalid format. Use `2h30m`, `1h 45m`, `1h`, or `30m`"),
                ephemeral=True
            )

        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0

        if hours == 0 and minutes == 0:
            return await interaction.followup.send(
                embed=ErrorEmbed("Duration must be greater than zero."),
                ephemeral=True
            )

        new_ts = int(time.time()) + (hours * 3600) + (minutes * 60)
        existing = self.load_annihilation()

        if existing and existing["timestamp"] > int(time.time()):
            old_ts = existing["timestamp"]
            embed = discord.Embed(
                title="Annihilation Already Reported",
                description=(
                    f"Annihilation is already set for <t:{old_ts}:f> (<t:{old_ts}:R>). "
                    f"Confirm within 30s to overwrite with `{time_until}`."
                ),
                color=ANNI_EMBED_COLOR
            )

            return await interaction.followup.send(
                embed=embed,
                view=ReportAnnihilationView(interaction.user, new_ts, self.save_annihilation)
            )

        self.save_annihilation(new_ts)
        await interaction.followup.send(
            embed=discord.Embed(
                title="Annihilation Time Reported",
                description=f"Next Annihilation is set for <t:{new_ts}:f> (<t:{new_ts}:R>)",
                color=ANNI_EMBED_COLOR
            )
        )



class ReportAnnihilationView(View):
    def __init__(self, author: discord.User, new_timestamp: int, func, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.new_timestamp = new_timestamp
        self.function = func
        self.confirmed = False
        self.message: Message = None


    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Only the user who initiated this command can confirm it.",
                ephemeral=True
            )
            return False
        return True


    @discord.ui.button(label="Confirm", style=ButtonStyle.success)
    async def confirm(self, interaction: Interaction, button: Button):
        self.confirmed = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Annihilation Time Overwritten",
                description=(
                    f"Annihilation time has been updated to <t:{self.new_timestamp}:f> "
                    f"(<t:{self.new_timestamp}:R>)"
                ),
                color=ANNI_EMBED_COLOR
            ),
            view=None
        )
        self.function(self.new_timestamp)
        self.stop()



async def setup(bot: commands.Bot):
    cog = AnnihilationTracker(bot)
    await bot.add_cog(cog)

    for command in (cog.report_annihilation, cog.annihilation_reminder):
        if bot.tree.get_command(command.name):
            bot.tree.remove_command(command.name)

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.report_annihilation, guild=guild)
        bot.tree.add_command(cog.annihilation_reminder, guild=guild)
