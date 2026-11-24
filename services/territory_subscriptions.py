import asyncio
import logging
from urllib.parse import quote
import aiohttp
import aiomysql
import discord
from discord import app_commands
from discord.ext import commands, tasks
from database import Database
from services.territory_tracker import create_terrchange_embed

class TerritorySubscriptions(commands.Cog):
    tracker = app_commands.Group(
        name="tracker", description="Manage territory trackers", guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )
    #topdown
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue = asyncio.Queue(maxsize=1000)
        self.pending = set()

    async def cog_load(self):
        self.delivery.start()
        self.expiry.start()
    def cog_unload(self):
        self.delivery.cancel()
        self.expiry.cancel()

    async def getRows(self, query, values=()):
        async with Database._pool.acquire() as connection:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, values)
                return await cursor.fetchall()

    async def resolveGuild(self, guild):
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for path in (quote(guild, safe=""), "prefix/" + quote(guild, safe="")):
                async with session.get(f"https://api.wynncraft.com/v3/guild/{path}") as response:
                    if response.status == 404:
                        continue
                    response.raise_for_status()
                    data = await response.json()
                    if isinstance(data, dict) and isinstance(data.get("name"), str):
                        return data["name"]
        return None

    async def publishChanges(self, changes, previous):
        rows = await self.getRows(
            "SELECT id, serverid, channelid, guildname FROM territorytrackers "
            "WHERE expires > UTC_TIMESTAMP()"
        )
        events = []
        for territory in changes:
            old = previous[territory["territory"]]
            try:
                events.append((old, territory, create_terrchange_embed(old, territory)))
            except (KeyError, TypeError, ValueError):
                logging.exception("Territory tracks: invalid transfer for %s", territory.get("territory"))
        dropped = 0
        for row in rows:
            if self.queue.full():
                logging.error("Territory tracks: rate queue full")
                break
            matches = []
            guild = row["guildname"]
            for old, territory, embed in events:
                if guild and guild.casefold() not in (
                    old["guild"].casefold(), territory["guild"].casefold()
                ):
                    continue
                matches.append(embed)
            for index in range(0, len(matches), 10):
                try:
                    self.queue.put_nowait((row, matches[index:index + 10], False))
                except asyncio.QueueFull:
                    dropped += len(matches[index:index + 10])
        if dropped:
            logging.error("Territory tracks: queue full")

    @tasks.loop(seconds=1)
    async def delivery(self):
        try:
            row, embeds, expired = self.queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            operator = "<=" if expired else ">"
            current = await Database.fetchrow(
                f"SELECT id FROM territorytrackers WHERE id=%s AND channelid=%s "
                f"AND expires {operator} UTC_TIMESTAMP()",
                (row["id"], row["channelid"]),
            )
            if not current:
                return
            guild = self.bot.get_guild(row["serverid"])
            channel = guild.get_channel(row["channelid"]) if guild else None
            if channel is None:
                raise LookupError(f"Channel {row['channelid']} is unavailable")
            if expired:
                await channel.send(
                    "A territory tracker has expired. An admin can refresh it with `/tracker refresh`.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                await Database.execute(
                    "UPDATE territorytrackers SET notified=TRUE "
                    "WHERE id=%s AND expires <= UTC_TIMESTAMP()", (row["id"],)
                )
            else:
                await channel.send(embeds=embeds, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            logging.exception("Territory tracks %s: delivery failed", row["id"])
            if expired:
                try:
                    await Database.execute(
                        "UPDATE territorytrackers SET retry=DATE_ADD(UTC_TIMESTAMP(), INTERVAL 1 HOUR) "
                        "WHERE id=%s AND expires <= UTC_TIMESTAMP()", (row["id"],)
                    )
                except Exception:
                    logging.exception("Territory tracks %s: failed to defer expiry notice", row["id"])
        finally:
            if expired:
                self.pending.discard(row["id"])
            self.queue.task_done()

    @delivery.before_loop
    async def beforeDelivery(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def expiry(self):
        try:
            rows = await self.getRows(
                "SELECT id, serverid, channelid FROM territorytrackers "
                "WHERE expires <= UTC_TIMESTAMP() AND notified=FALSE "
                "AND (retry IS NULL OR retry <= UTC_TIMESTAMP())"
            )
            for row in rows:
                if row["id"] in self.pending:
                    continue
                try:
                    self.queue.put_nowait((row, [], True))
                except asyncio.QueueFull:
                    logging.warning("Territory tracks: queue full")
                    break
                self.pending.add(row["id"])
        except Exception:
            logging.exception("Territory tracks: expiry check failed")

    @expiry.before_loop
    async def beforeExpiry(self):
        await self.bot.wait_until_ready()

    @tracker.command(name="add", description="Add a full or guild specific territory tracker")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(channel="Channel for transfers", guild="Wynncraft guild name or prefix, dont use if you want all")
    async def addTracker(self, interaction: discord.Interaction, channel: discord.TextChannel, guild: str = None):
        await interaction.response.defer(ephemeral=True)
        if channel.guild.id != interaction.guild_id:
            return await interaction.followup.send("Choose a channel in this server.", ephemeral=True)
        permissions = channel.permissions_for(interaction.guild.me)
        if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            return await interaction.followup.send(
                "Needs View Channel, Send Messages and Embed Links in that channel.", ephemeral=True
            )
        guildname = None
        if guild is not None:
            guild = guild.strip()
            if not guild or len(guild) > 128:
                return await interaction.followup.send("Enter a valid Wynncraft guild name or prefix.", ephemeral=True)
            try:
                guildname = await self.resolveGuild(guild)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                logging.exception("Territory tracks: guild lookup failed for %s", guild)
                return await interaction.followup.send("Can't find guild or timedout", ephemeral=True)
            if not guildname:
                return await interaction.followup.send("Wynncraft guild not found.", ephemeral=True)

        async with Database._pool.acquire() as connection:
            await connection.begin()
            try:
                async with connection.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        "INSERT IGNORE INTO territorytrackerservers (serverid) VALUES (%s)",
                        (interaction.guild_id,),
                    )
                    await cursor.execute(
                        "SELECT serverid FROM territorytrackerservers WHERE serverid=%s FOR UPDATE",
                        (interaction.guild_id,),
                    )
                    await cursor.execute(
                        "SELECT slot FROM territorytrackers WHERE serverid=%s", (interaction.guild_id,)
                    )
                    used = {row["slot"] for row in await cursor.fetchall()}
                    slot = next((value for value in range(1, 16) if value not in used), None) if guildname else 0
                    if slot is None or slot in used:
                        await connection.rollback()
                        return await interaction.followup.send(
                            "This server has hit the limit of one full tracker and 15 guild trackers. "
                            "Remove a tracker with `/tracker remove` first.", ephemeral=True
                        )
                    await cursor.execute(
                        "INSERT INTO territorytrackers (serverid, slot, channelid, guildname, expires) "
                        "VALUES (%s, %s, %s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL 6 MONTH))",
                        (interaction.guild_id, slot, channel.id, guildname),
                    )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
        label = guildname or "All territories"
        await interaction.followup.send(
            f"Tracker {slot} ({label}) added to {channel.mention}", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @tracker.command(name="list", description="List this server's territory trackers")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def listTrackers(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self.getRows(
            "SELECT slot, channelid, guildname, "
            "TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', expires) AS expiry, "
            "expires <= UTC_TIMESTAMP() AS expired FROM territorytrackers WHERE serverid=%s ORDER BY slot",
            (interaction.guild_id,),
        )
        if not rows:
            return await interaction.followup.send("No territory trackers are configured.", ephemeral=True)
        lines = [
            f"`{row['slot']}` {row['guildname'] or 'All territories'}: <#{row['channelid']}> "
            f"({'expired' if row['expired'] else 'expires'} <t:{int(row['expiry'])}:R>)"
            for row in rows
        ]
        await interaction.followup.send(
            "\n".join(lines), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @tracker.command(name="remove", description="Remove a territory tracker by its number")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(number="Tracker number from /tracker list")
    async def removeTracker(self, interaction: discord.Interaction, number: app_commands.Range[int, 0, 15]):
        await interaction.response.defer(ephemeral=True)
        async with Database._pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM territorytrackers WHERE serverid=%s AND slot=%s",
                    (interaction.guild_id, number),
                )
                removed = cursor.rowcount
        await interaction.followup.send(
            "Tracker removed." if removed else "Tracker not found.", ephemeral=True
        )

    @tracker.command(name="refresh", description="Renew this server's territory trackers")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def refreshTrackers(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with Database._pool.acquire() as connection:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    "SELECT COUNT(*) AS count FROM territorytrackers WHERE serverid=%s",
                    (interaction.guild_id,),
                )
                count = (await cursor.fetchone())["count"]
                await cursor.execute(
                    "UPDATE territorytrackers SET expires=DATE_ADD(UTC_TIMESTAMP(), INTERVAL 6 MONTH), "
                    "notified=FALSE, retry=NULL WHERE serverid=%s", (interaction.guild_id,)
                )
        await interaction.followup.send(
            f"Refreshed {count} tracker(s)" if count else "No territory trackers to refresh.",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(TerritorySubscriptions(bot))
