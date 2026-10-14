import discord, logging
from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from database import Database
from util.board import BoardView, build_board
from util.embeds import ErrorEmbed, TextTableEmbed
from util.ranges import get_current_season
from util.requests import request
from util.uuid import get_name_from_uuid


LEADERBOARD_STATS = ["sand_swept_tomb", "galleons_graveyard", "firstjoin", "scribing", "chests_found", "woodcutting", "tailoring", "fishing", "eldritch_outlook", "alchemism", "logins", "deaths", "corrupted_decrepit_sewers", "armouring", "corrupted_undergrowth_ruins", "items_identified", "nest_of_the_grootslangs", "blocks_walked", "lost_sanctuary", "mining", "the_canyon_colossus", "undergrowth_ruins", "corrupted_ice_barrows", "jeweling", "woodworking", "uuid", "underworld_crypt", "fallen_factory", "mobs_killed", "infested_pit", "decrepit_sewers", "corrupted_sand_swept_tomb", "corrupted_infested_pit", "farming", "corrupted_lost_sanctuary", "cooking", "guild", "combat", "weaponsmithing", "playtime", "corrupted_underworld_crypt", "ice_barrows", "nexus_of_light", "guild_rank", "the_nameless_anomaly", "raids", "corrupted_galleons_graveyard", "timelost_sanctum", "dungeons"]
LEADERBOARD_STAT_NAMES = ["Sand-Swept Tomb Completions", "Galleon's Graveyard Completions", "First Join Date", "Scribing Level", "Chests Found", "Woodcutting Level", "Tailoring Level", "Fishing Level", "Eldritch Outlook Completions", "Alchemism Level", "Total Logins", "Total Deaths", "Corrupted Decrepit Sewers Completions", "Armouring Level", "Corrupted Undergrowth Ruins Completions", "Total Items Identified", "Nest Of The Grootslangs Completions", "Total Blocks Walked", "Lost Sanctuary Completions", "Mining Level", "The Canyon Colossus Completions", "Undergrowth Ruins Completions", "Corrupted Ice Barrows Completions", "Jeweling Level", "Woodworking Level", "UUID", "Underworld Crypt Completions", "Fallen Factory Completions", "Total Mobs Killed", "Infested Pit Completions", "Decrepit Sewers Completions", "Corrupted Sand-Swept Tomb Completions", "Corrupted Infested Pit Completions", "Farming Level", "Corrupted Lost Sanctuary Completions", "Cooking Level", "Guild", "Combat", "Weaponsmithing Level", "Total Playtime", "Corrupted Underworld Crypt Completions", "Ice Barrows Completions", "Nexus Of Light Completions", "Guild rank", "The Nameless Anomaly Completions", "Total raid Completions", "Corrupted Galleons Graveyard Completions", "Timelost Sanctum Completions", "Total Dungeon Completions"]

STATS = {
    "dungeons": {
        "stats": [
            "dungeons", "decrepit_sewers", "corrupted_decrepit_sewers", "infested_pit", "corrupted_infested_pit",
            "underworld_crypt", "corrupted_underworld_crypt", "lost_sanctuary", "corrupted_lost_sanctuary",
            "ice_barrows", "corrupted_ice_barrows", "undergrowth_ruins", "corrupted_undergrowth_ruins",
            "galleons_graveyard", "corrupted_galleons_graveyard", "sand_swept_tomb", "corrupted_sand_swept_tomb",
            "eldritch_outlook", "fallen_factory", "timelost_sanctum"
        ],
        "names": [
            "Total Dungeons", "Decrepit Sewers", "Corrupted Decrepit Sewers", "Infested Pit", "Corrupted Infested Pit",
            "Underworld Crypt", "Corrupted Underworld Crypt", "Lost Sanctuary", "Corrupted Lost Sanctuary",
            "Ice Barrows", "Corrupted Ice Barrows", "Undergrowth Ruins", "Corrupted Undergrowth Ruins",
            "Galleon's Graveyard", "Corrupted Galleon's Graveyard", "Sand-Swept Tomb", "Corrupted Sand-Swept Tomb",
            "Eldritch Outlook", "Fallen Factory", "Timelost Sanctum"
        ]
    },
    "raids": {
        "stats": ["raids", "the_canyon_colossus", "nexus_of_light", "the_nameless_anomaly", "nest_of_the_grootslangs"],
        "names": ["Total Raids", "The Canyon Colossus", "Nexus of Light", "The Nameless Anomaly", "Nest of the Grootslangs"]
    },
    "professions": {
        "stats": [
            "woodcutting", "mining", "farming", "fishing", "cooking", "scribing", "alchemism",
            "jeweling", "armouring", "tailoring", "weaponsmithing", "woodworking"
        ],
        "names": [
            "Woodcutting Level", "Mining Level", "Farming Level", "Fishing Level", "Cooking Level",
            "Scribing Level", "Alchemism Level", "Jeweling Level", "Armouring Level", "Tailoring Level",
            "Weaponsmithing Level", "Woodworking Level"
        ]
    },
    "player_stats": {
        "stats": [
            "chests_found", "items_identified", "logins", "deaths", "blocks_walked", "playtime", "firstjoin",
            "combat", "mobs_killed"
        ],
        "names": [
            "Chests Found", "Items Identified", "Total Logins", "Total Deaths", "Blocks Walked", "Playtime",
            "First Join Date", "Combat Level", "Mobs Killed"
        ]
    }
}

class Leaderboard(commands.GroupCog, name="leaderboard"):
    """
    Group cog for all leaderboard related commands.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    async def display_leaderboard(self, interaction: discord.Interaction, category: str, statistic: str):
        await interaction.response.defer()

        if statistic in STATS[category]["names"]:
            stat_index = STATS[category]["names"].index(statistic)
            statistic = STATS[category]["stats"][stat_index]
        elif statistic in STATS[category]["stats"]:
            stat_index = STATS[category]["stats"].index(statistic)
        else:
            return await interaction.followup.send(embed=ErrorEmbed("Invalid statistic"))

        try:
            if statistic == "raids":
                res = await Database.fetch(
                    "SELECT uuid_name.name, uuid_name.uuid, "
                    "player_stats.the_canyon_colossus + player_stats.nexus_of_light + "
                    "player_stats.the_nameless_anomaly + player_stats.nest_of_the_grootslangs as total "
                    "FROM player_stats LEFT JOIN uuid_name ON uuid_name.uuid=player_stats.uuid "
                    "ORDER BY total DESC LIMIT 50"
                )
            elif statistic == "dungeons":
                res = await Database.fetch(
                    "SELECT uuid_name.name, uuid_name.uuid, "
                    "player_stats.decrepit_sewers + player_stats.corrupted_decrepit_sewers + "
                    "player_stats.infested_pit + player_stats.corrupted_infested_pit + "
                    "player_stats.corrupted_underworld_crypt + player_stats.underworld_crypt + "
                    "player_stats.lost_sanctuary + player_stats.corrupted_lost_sanctuary + "
                    "player_stats.ice_barrows + player_stats.corrupted_ice_barrows + "
                    "player_stats.corrupted_undergrowth_ruins + player_stats.undergrowth_ruins + "
                    "player_stats.corrupted_galleons_graveyard + player_stats.galleons_graveyard + "
                    "player_stats.fallen_factory + player_stats.eldritch_outlook + "
                    "player_stats.corrupted_sand_swept_tomb + player_stats.sand_swept_tomb + "
                    "player_stats.timelost_sanctum as total "
                    "FROM player_stats LEFT JOIN uuid_name ON uuid_name.uuid=player_stats.uuid "
                    "ORDER BY total DESC LIMIT 50"
                )
            else:
                res = await Database.fetch(
                    f"SELECT uuid_name.name, uuid_name.uuid, player_stats.{statistic} as total "
                    f"FROM player_stats LEFT JOIN uuid_name ON uuid_name.uuid=player_stats.uuid "
                    f"ORDER BY {statistic} DESC LIMIT 50"
                )
            stats = [(m["name"] or await get_name_from_uuid(m["uuid"]), m["total"]) for m in res]
        except Exception as e:
            return await interaction.followup.send(f"Error retrieving leaderboard: {e}", ephemeral=True)
        view = BoardView(interaction.user.id, stats, title=f"Leaderboard for {STATS[category]['names'][stat_index]}")
        if view.is_fancy:
            board = await build_board(view.data, view.page)
            await interaction.followup.send(view=view, file=board)
        else:
            start = view.page * 10
            end = start + 10
            sliced = view.data[start:end]

            for i in range(len(sliced)):
                sliced[i] = [f"{i+start+1}.", sliced[i][0], sliced[i][1]]

            embed = TextTableEmbed(["Rank", "Name", "Value"], sliced, title=view.title, color=0x333333)
            await interaction.followup.send(embed=embed, view=view)



    @app_commands.command(name="dungeons", description="Dungeon leaderboards")
    @app_commands.describe(stat="Choose a dungeon to see its leaderboard")
    @rate_limit_check()
    async def leaderboard_dungeons(self, interaction: discord.Interaction, stat: str):
        """Show dungeon leaderboard for a chosen dungeon stat."""
        await self.display_leaderboard(interaction, "dungeons", stat)

    @leaderboard_dungeons.autocomplete("stat")
    async def dungeons_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete dungeon stat names."""
        return [discord.app_commands.Choice(name=name, value=name) for name in STATS["dungeons"]["names"] if current.lower() in name.lower()]


    @app_commands.command(name="raids", description="Raid leaderboards")
    @app_commands.describe(stat="Choose a raid to see its leaderboard")
    @rate_limit_check()
    async def leaderboard_raids(self, interaction: discord.Interaction, stat: str):
        await self.display_leaderboard(interaction, "raids", stat)

    @leaderboard_raids.autocomplete("stat")
    async def raids_autocomplete(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=name, value=name) for name in STATS["raids"]["names"] if current.lower() in name.lower()]


    @app_commands.command(name="professions", description="Profession leaderboards")
    @app_commands.describe(stat="Choose a profession to see its leaderboard")
    @rate_limit_check()
    async def leaderboard_professions(self, interaction: discord.Interaction, stat: str):
        await self.display_leaderboard(interaction, "professions", stat)

    @leaderboard_professions.autocomplete("stat")
    async def professions_autocomplete(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=name, value=name) for name in STATS["professions"]["names"] if current.lower() in name.lower()]


    @app_commands.command(name="player_stats", description="General player stat leaderboards")
    @app_commands.describe(stat="Choose a player stat to see its leaderboard")
    @rate_limit_check()
    async def leaderboard_misc(self, interaction: discord.Interaction, stat: str):
        await self.display_leaderboard(interaction, "player_stats", stat)

    @leaderboard_misc.autocomplete("stat")
    async def misc_autocomplete(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=name, value=name) for name in STATS["player_stats"]["names"] if current.lower() in name.lower()]


    @app_commands.command(name="season_rating", description="Guild Season rating leaderboard")
    @rate_limit_check()
    async def season_ratings(self, interaction: discord.Interaction):
        await interaction.response.defer()

        season = await get_current_season()
        if not season:
            return await interaction.followup.send(embed=ErrorEmbed("Could not determine the current season."))

        season_num = season[6:]

        res = await request("https://nori.fish/api/database/guild")
        if not res:
            return await interaction.followup.send(embed=ErrorEmbed("Could not fetch season rating data."))

        ratings = []
        for guild, data in res.items():
            ratings.append({
                "guild": data.get("name", "Unknown Guild"),
                "rating": data.get("sr", 0)
            })

        ratings.sort(key=lambda x: x["rating"], reverse=True)

        rows = [(r["guild"], f"{r['rating']:,}") for r in ratings]
        view = BoardView(
            interaction.user.id,
            rows,
            title=f"Season Rating Leaderboard for Season {season_num}",
            is_guild_board=True,
            headers=["Guild", "Rating"]
        )

        if view.is_fancy:
            board = await build_board(view.data, view.page, is_guild_board=True)
            await interaction.followup.send(view=view, file=board)
        else:
            start = view.page * 10
            end = start + 10
            sliced = view.data[start:end]

            for i in range(len(sliced)):
                sliced[i] = [f"{i+start+1}.", sliced[i][0], sliced[i][1]]

            embed = TextTableEmbed(
                ["Rank", "Guild", "Rating"], 
                sliced, 
                title=view.title, 
                color=0x333333
            )
            await interaction.followup.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
