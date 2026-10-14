import discord

from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from util.embeds import ErrorEmbed
from util.requests import request
from util.mappings import MAX_STATS, SUPPORT_RANK_SLOTS



async def get_colored_percentage(percent: float) -> str:
    green = "\033[1;32m"
    red = "\033[0;31m"
    yellow = "\033[1;33m"
    blue = "\033[1;36m"
    stop = "\033[0m"

    percent = min(percent, 1) #Caps percent at 100%

    if percent >= 0.96:
        return f"{blue}{percent:>7.3%}{stop}"
    elif percent <= 0:
        return f"{red}{percent:>7.3%}{stop}"
    elif percent < 0.3:
        return f"{red}{percent:>7.3%}{stop}"
    elif percent < 0.8:
        return f"{yellow}{percent:>7.3%}{stop}"
    else:
        return f"{green}{percent:>7.3%}{stop}"


async def show_total_progress(stats: dict, max_characters: int) -> str:
    sections = []  
    total = 0  
    total_max = 0 

    stop = "\033[0m"
    blue = "\033[0;34m"
    green = "\033[0;32m"
    purple = "\033[0;35m"
    red = "\033[1;31m"
    async def section(label: str, value: int, max_val: int, color_code: str):
        nonlocal total, total_max
        total += value
        total_max += max_val
        return f"{color_code}{label:>24}{stop}  | {value:7,} / {max_val:6,}  | {await get_colored_percentage(value / max_val)}"

    sections.append(await section("Total Level", stats["Level"], MAX_STATS["total"] * max_characters, blue))
    sections.append(await section("Combat", stats["Combat"], MAX_STATS["combat"] * max_characters, blue))

    for prof in ["Farming", "Fishing", "Mining", "Woodcutting"]:
        sections.append(await section(prof, stats[prof], MAX_STATS["gathering"] * max_characters, purple))

    for prof in ["Alchemism", "Armouring", "Cooking", "Jeweling", "Scribing", "Tailoring", "Weaponsmithing", "Woodworking"]:
        sections.append(await section(prof, stats[prof], MAX_STATS["crafting"] * max_characters, purple))

    sections.append(await section("Main Quests", stats["Quests"], 137 * max_characters, green))
    sections.append(await section("Slaying Mini-Quests", stats["Slaying Mini-Quests"], 29 * max_characters, green))
    sections.append(await section("Gathering Mini-Quests", stats["Gathering Mini-Quests"], 96 * max_characters, green))
    sections.append(await section("Discoveries", stats["Discoveries"], (105 + 496) * max_characters, green))
    sections.append(await section("World Events", stats["World Events"], 54 * max_characters, green))
    sections.append(await section("Lootruns", stats["Lootruns"], 5 * max_characters, green))
    sections.append(await section("Caves", stats["Caves"], 172 * max_characters, green))
    sections.append(await section("Unique Dungeons", stats["Unique Dungeon Completions"], 18 * max_characters, green))
    sections.append(await section("Unique Raids", stats["Unique Raid Completions"], 4 * max_characters, green))

    sections.append(f"{red}{'Overall Total':>24}{stop}  | {total:7,} / {total_max:6,}  | {await get_colored_percentage(total / total_max)}")

    return "\n".join(sections)

class Completion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(name="completion", description="Display a profile card for a player")
    @app_commands.describe(username="The player's username")
    @rate_limit_check()
    async def completion(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        data = await request(f"https://api.wynncraft.com/v3/player/{username}?fullResult", use_wynn_auth=True)
        characters = data["characters"] 
        rank = data["supportRank"]  
        if SUPPORT_RANK_SLOTS.get(rank, 5) < len(characters): 
            max_chars = len(characters)
        else:
            max_chars = SUPPORT_RANK_SLOTS.get(rank, 5)  

        totals = {
            "Level": 0,
            "Combat": 0,
            "Farming": 0,
            "Fishing": 0,
            "Mining": 0,
            "Woodcutting": 0,
            "Alchemism": 0,
            "Armouring": 0,
            "Cooking": 0,
            "Jeweling": 0,
            "Scribing": 0,
            "Tailoring": 0,
            "Weaponsmithing": 0,
            "Woodworking": 0,
            "Quests": 0,
            "Slaying Mini-Quests": 0,
            "Gathering Mini-Quests": 0,
            "Discoveries": 0,
            "World Events": 0,
            "Lootruns": 0,
            "Caves": 0,
            "Unique Dungeon Completions": 0,
            "Dungeon Completions": 0,
            "Unique Raid Completions": 0,
            "Raid Completions": 0,
        }

        try:
            for _, char in characters.items():
                for stat in totals:
                    if stat in ["Quests", "Slaying Mini-Quests", "Gathering Mini-Quests"]:
                        quests = char.get("quests", [])
                        if stat == "Quests":
                            val = sum(1 for q in quests if "Mini-Quest" not in q)
                        elif stat == "Slaying Mini-Quests":
                            val = sum(1 for q in quests if "Mini-Quest" in q and "Gather" not in q)
                        else:
                            val = sum(1 for q in quests if "Mini-Quest - Gather" in q)
                    elif stat == "Discoveries":
                        val = char.get("discoveries", 0)
                    elif stat == "World Events":
                        val = char.get("worldEvents", 0)
                    elif stat == "Lootruns":
                        val = char.get("lootruns", 0)
                    elif stat == "Caves":
                        val = char.get("caves", 0)
                    elif stat == "Unique Dungeon Completions":
                        val = len(char.get("dungeons", {}).get("list", []))
                    elif stat == "Unique Raid Completions":
                        val = len(char.get("raids", {}).get("list", []))
                    elif stat == "Dungeon Completions":
                        names = [
                            "Skeleton", "Spider", "Decrepit", "Lost Sanctuary", "Sand-Swept", "Ice Barrows", 
                            "Undergrowth", "Galleon's", "Corrupted", "Eldritch", "Fallen Factory"
                        ]
                        val = sum(1 for d in char.get("dungeons", {}).get("list", []) if any(n in d for n in names))
                    elif stat == "Raid Completions":
                        val = len(char.get("raids", {}).get("list", []))
                    elif stat in ["Level", "Combat"]:
                        val = char["totalLevel"] + 12 if stat == "Level" else char["level"]
                    else:
                        val = char.get("professions", {}).get(stat.lower(), {}).get("level", 0)

                    totals[stat] += val
        except (KeyError, AttributeError, TypeError):
            return await interaction.followup.send(embed=ErrorEmbed("Hidden player profile."))

        body = await show_total_progress(totals, max_chars)
        bold = "\033[1m"
        stop = "\033[0m"
        await interaction.followup.send(f"```ansi\n{bold}{username}'s Completionism{stop}\n{body}\n```")

async def setup(bot: commands.Bot):
    await bot.add_cog(Completion(bot))
