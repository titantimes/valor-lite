import discord, datetime

from discord.ext import commands
from discord import app_commands

from core.antispam import rate_limit_check
from database import Database
from core.settings import SettingsManager
from util.embeds import ErrorEmbed, TextTableEmbed, PaginatedTextTableEmbed, PaginatedFieldedTextTableEmbed
from util.guilds import guild_name_from_tag
from util.mappings import RANK_SYMBOL_MAP
from util.requests import request



async def get_data(guild: str, interaction: discord.Interaction):
    if not guild:
        guild_name = SettingsManager("guild", interaction.guild.id).get("guild_name")
        guild_tag = SettingsManager("guild", interaction.guild.id).get("guild_tag")

        if not (guild_name and guild_tag):
            return "warn"
        return await request(f"https://api.wynncraft.com/v3/guild/{guild_name}")

    name = await guild_name_from_tag(guild) or guild
    res = await request(f"https://api.wynncraft.com/v3/guild/{name}")
    if not res:
        res = await request(f"https://api.wynncraft.com/v3/guild/prefix/{guild}")

    return res


async def get_online(data):
    if "members" not in data:
        return None

    online_members = [
        (name, RANK_SYMBOL_MAP.get(rank, rank), member["server"])
        for rank, v in data["members"].items()
        if rank != "total"
        for name, member in v.items()
        if member["online"]
    ]
    
    hidden_players = data["online"] - len(online_members)

    if not online_members and not hidden_players:
        return "```isbl\nThere are no members online.\n```"
    

    embed = TextTableEmbed(
        ["Name", "Rank", "World"],
        sorted(online_members, key=lambda x: len(x[1]), reverse=True),
    )

    description = embed.description

    if len(online_members) == 0 and hidden_players:
        return f"```isbl\n{hidden_players} players are hidden.\n```"

    if hidden_players:
        description = description[:-3] + f"\n{hidden_players} players are hidden.\n```"

    return description


def m_section(data):
    sections = {}
    for rank, players in data["members"].items():
        if rank == "total":
            continue

        rows = []
        for name, details in players.items():
            joined = datetime.datetime.fromisoformat(details["joined"][:-1]).strftime("%m/%d/%Y")
            rows.append([name, joined])

        sections[f"{rank.capitalize()} ({len(rows)})"] = rows

    return sections


def gxps(data):
    rows = [
        (player, player_data["contributed"])
        for rank, players in data["members"].items()
        if rank != "total"
        for player, player_data in players.items()
    ]
    rows.sort(key=lambda row: row[1], reverse=True)
    return [[player, f"{contributed:,} "] for player, contributed in rows]


class GuildOverviewView(discord.ui.View):
    def __init__(self, overview_embed, data):
        super().__init__(timeout=120)
        self.overview_embed = overview_embed
        self.member_pages = PaginatedFieldedTextTableEmbed(
            ["Name", "Joined"],
            m_section(data),
            title=f"{data['name']}: Members",
            color=discord.Color.blue(),
            rows_per_page=20,
        )
        self.gxp_pages = PaginatedTextTableEmbed(
            ["Name", "XP"],
            gxps(data),
            title=f"{data['name']}: GXP Contributions",
            color=discord.Color.blue(),
            rows_per_page=20,
        )
        self.member_page_count = max(self.member_pages.total_pages, 1)
        self.gxp_page_count = max(self.gxp_pages.total_pages, 1)
        self.total_pages = 1 + self.member_page_count + self.gxp_page_count
        self.page = 0

        self.previous_button = discord.ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.gray, disabled=True
        )
        self.previous_button.callback = self.back
        self.next_button = discord.ui.Button(emoji="➡️", style=discord.ButtonStyle.gray)
        self.next_button.callback = self.forward
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    def format(self, page):
        if page == 0:
            embed = self.overview_embed.copy()
            section = "Overview"
        elif page <= self.member_page_count:
            embed = self.member_pages.format_page(page - 1)
            section = "Members"
        else:
            embed = self.gxp_pages.format_page(page - 1 - self.member_page_count)
            section = "GXP Contributions"

        embed.set_footer(text=f"{section} | Page {page + 1}/{self.total_pages}")
        return embed

    async def cpag(self, interaction, page):
        self.page = page
        self.previous_button.disabled = page == 0
        self.next_button.disabled = page == self.total_pages - 1
        await interaction.response.edit_message(embed=self.format(page), view=self)

    async def back(self, interaction):
        if self.page > 0:
            await self.cpag(interaction, self.page - 1)

    async def forward(self, interaction):
        if self.page < self.total_pages - 1:
            await self.cpag(interaction, self.page + 1)



class GuildCommands(commands.GroupCog, name="guild"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(name="overview", description="View basic guild info")
    @app_commands.describe(guild="The guild name or prefix of the target guild")
    @rate_limit_check()
    @app_commands.guild_only()
    async def overview(self, interaction: discord.Interaction, guild: str = None):
        await interaction.response.defer()

        data = await get_data(guild, interaction)
        if data == "warn":
            return await interaction.followup.send(embed=ErrorEmbed("Default guild name and tag have not been set. Please get an admin to run `/guild_settings` and set it."))
        if not data:
            return await interaction.followup.send(embed=ErrorEmbed("Error fetching guild data"))

        desc = f"""```properties
Name: {data["name"]} [{data["prefix"]}]
Level: {data["level"]} ({data["xpPercent"]}%)
Owner: {list(data["members"]["owner"])[0]}
Members: {data["members"]["total"]}
Territories: {data["territories"]}
War Count: {data["wars"]}
Created: {datetime.datetime.fromisoformat(data["created"][:-1]).strftime("%m/%d/%Y  %H:%M")}
```"""
        online_desc = await get_online(data)

        embed = discord.Embed(title=f"{data['name']}: Overview", description=desc, color=0x7785cc)
        embed.add_field(name=f"Online Members ({data["online"]})", value=online_desc)

        view = GuildOverviewView(embed, data)
        return await interaction.followup.send(embed=view.format(0), view=view)


    @app_commands.command(name="online", description="View online players of the guild")
    @app_commands.describe(guild="The guild name or prefix of the target guild")
    @app_commands.guild_only()
    async def online(self, interaction: discord.Interaction, guild: str = None):
        await interaction.response.defer()

        data = await get_data(guild, interaction)
        if data == "warn":
            return await interaction.followup.send(embed=ErrorEmbed("Default guild name and tag have not been set. Please get an admin to run `/guild_settings` and set it."))
        if not data:
            return await interaction.followup.send(embed=ErrorEmbed("Error fetching guild data"))
        description = await get_online(data)
        embed = discord.Embed(
                title=f"Members of {data['name']} online ({data["online"]})",
                description=description,
                color=0x7785cc
            )

        await interaction.followup.send(embed=embed)


    @app_commands.command(name="members", description="View a list of all players in a guild")
    @app_commands.describe(guild="The guild name or prefix of the target guild")
    @rate_limit_check()
    @app_commands.guild_only()
    async def members(self, interaction: discord.Interaction, guild: str = None):
        await interaction.response.defer()

        data = await get_data(guild, interaction)
        if data == "warn":
            return await interaction.followup.send(embed=ErrorEmbed("Default guild name and tag have not been set. Please get an admin to run `/guild_settings` and set it."))
        if not data:
            return await interaction.followup.send(embed=ErrorEmbed("Error fetching guild data"))
        await PaginatedFieldedTextTableEmbed.send(
            interaction,
            ["Name", "Joined"],
            m_section(data),
            title=f"{data['name']}: Members",
            color=discord.Color.blue(),
            rows_per_page=20
        )


    @app_commands.command(name="gxp", description="View the GXP contributions of each player in a guild")
    @app_commands.describe(guild="The guild name or prefix of the target guild")
    @rate_limit_check()
    @app_commands.guild_only()
    async def gxp(self, interaction: discord.Interaction, guild: str = None):
        await interaction.response.defer()

        data = await get_data(guild, interaction)
        if data == "warn":
            return await interaction.followup.send(embed=ErrorEmbed("Default guild name and tag have not been set. Please get an admin to run `/guild_settings` and set it."))
        if not data:
            return await interaction.followup.send(embed=ErrorEmbed("Error fetching guild data"))
        await PaginatedTextTableEmbed.send(
            interaction,
            ["Name", "XP"],
            gxps(data),
            title=f"{data['name']}: GXP Contributions",
            color=discord.Color.blue(),
            rows_per_page=20
        )


    @app_commands.command(name="activity", description="Show last join times for all players in a guild")
    @app_commands.describe(guild="The guild name or prefix of the target guild", order="The order to sort in (descending by default)")
    @app_commands.choices(order=[
        app_commands.Choice(name="Ascending", value="asc"),
        app_commands.Choice(name="Descending", value="desc")
    ])
    @rate_limit_check()
    @app_commands.guild_only()
    async def activity(self, interaction: discord.Interaction, guild: str = None, order: app_commands.Choice[str] = "desc"):
        await interaction.response.defer()

        try:
            order = order.value
        except (ValueError, AttributeError):
            pass

        data = await get_data(guild, interaction)
        if data == "warn":
            return await interaction.followup.send(embed=ErrorEmbed("Default guild name and tag have not been set. Please get an admin to run `/guild_settings` and set it."))
        if not data:
            return await interaction.followup.send(embed=ErrorEmbed("Error fetching guild data"))
        members_data = data["members"]

        member_set = set()
        for rank in members_data:
            if isinstance(members_data[rank], dict):
                member_set.update(members_data[rank])

        members_list = list(member_set)
        if not members_list:
            return await interaction.followup.send(embed=ErrorEmbed("Guild has no members."))

        placeholders = ','.join(['%s'] * len(members_list))
        query = f"SELECT name, lastjoin FROM player_last_join WHERE name IN ({placeholders})"
        res = await Database.fetch(query, members_list)
        last_join_times = {result["name"]: result["lastjoin"] for result in res}

        now = datetime.datetime.utcnow()
        rows = []
        for name in members_list:
            try:
                stamp = last_join_times[name]
            except KeyError:
                continue

            if stamp:
                delta = now - datetime.datetime.utcfromtimestamp(stamp)
                display = f"{delta.days}d {delta.seconds // 3600}h"
            else:
                display = "30d+"
            rows.append((name, display))

        rows.sort(
            key=lambda r: (r[1] != "30d+", *map(int, (r[1].rstrip("dh").replace("d", " ").split() + ["0"])[:2])),
            reverse=(order == "desc")
        )

        await PaginatedTextTableEmbed.send(
            interaction,
            ["Name", "Last Join"],
            rows,
            title=f"Member Activity of {data['name']}: ({len(rows)})",
            rows_per_page=20
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildCommands(bot))
