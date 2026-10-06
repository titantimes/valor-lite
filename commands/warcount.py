import discord

from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from database import Database
from util.board import BoardView, build_board, WarcountBoardView, build_warcount_board
from util.embeds import ErrorEmbed, PaginatedTextTableEmbed
from util.guilds import guild_names_from_tags
from util.mappings import CLASS_RESKINS_MAP
from util.ranges import get_range_from_string, range_alt


class Warcount(commands.Cog):
    """
    Cog providing /warcount command to get warcounts of players and guilds.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(name="warcount", description="War count leaderboard.")
    @app_commands.describe(
        guilds="Filter by guild tags (comma-separated)",
        range="Number of days ago, or a range like '0,7', or season name like 'season26' (defaults to all time)",
        players="Filter by player usernames (comma-separated)",
        classes="Filter by classes (comma-separated)",
        guild_wise="Show wars total per guild instead of individual players"
    )
    @rate_limit_check()
    async def warcount(
        self,
        interaction: discord.Interaction,
        guilds: str = None,
        range: str = None,
        players: str = None,
        classes: str = None,
        guild_wise: bool = False
    ):
        await interaction.response.defer()

        # Prevent combining guild-wise aggregation with player/guild/class filters (mutually exclusive)
        if guild_wise and (players or classes or guilds):
            return await interaction.followup.send(embed=ErrorEmbed(
                "You cannot use `guild_wise` together with `players` or `guilds` or `classes`."
            ))

        # Parse and validate the 'range' argument if provided
        if range:
            if range.strip().lower() == "all":
                range = None # Uses rangeless logic to be correct
            else:
                range = await get_range_from_string(range, max_allowed_range=None)
                if not range:
                    return await interaction.followup.send(embed=ErrorEmbed("Invalid range input"))
                left, right = range

        # Parse filters from comma-separated strings into lists
        guild_filter = [g.strip() for g in guilds.split(",")] if guilds else []
        names = [x.strip().lower() for x in players.split(",")] if players else None
        # Default classes to all 5 valid classes if none specified
        listed_classes = [c.strip().upper() for c in classes.split(",")] if classes else ["ARCHER", "WARRIOR", "MAGE", "ASSASSIN", "SHAMAN"]

        # If guild-wise aggregation is requested, query aggregated wars per guild directly
        if guild_wise:
            query = f"""
SELECT guild, SUM(delta) AS wars
FROM player_delta_record
WHERE label = 'g_wars' AND guild IS NOT NULL {"AND time BETWEEN %s AND %s" if range else ""}
GROUP BY guild
ORDER BY wars DESC
LIMIT 100;
"""
            
            res = await Database.fetch(query, (left, right) if range else ())

            # Prepare header and rows for leaderboard table
            headers = ["Guild", "Wars"]
            rows = []
            for result in res:
                rows.append((
                    result["guild"],
                    int(result["wars"])
                ))

            # Initialize BoardView with guild data
            view = BoardView(interaction.user.id, rows, is_guild_board=True, headers=headers)

            if view.is_fancy:
                # If user supports "fancy" boards, send graphical leaderboard
                board = await build_board(view.data, view.page, view.is_guild_board)
                return await interaction.followup.send(view=view, file=board)
            else:
                # Otherwise, send a simple paginated text table
                start = view.page * 10
                end = start + 10
                sliced = view.data[start:end]
                # Add ranking number to each row
                for i in range_alt(len(sliced)):
                    sliced[i] = [f"{i+start+1}.", sliced[i][0], sliced[i][1]]

                return await PaginatedTextTableEmbed.send(interaction, headers, rows, "Warcount sum for guilds")

        # Player warcount logic below

        # Choose correct database table and column based on whether range filtering is used
        table_type = "cumu_warcounts" if not range else "delta_warcounts"
        table_count_column = "warcount" if not range else "warcount_diff"

        # Prepare SQL parts to sum warcounts for each selected class, accounting for class reskins
        class_column_count_parts = []
        select_class_in_parts = []

        for real_class in listed_classes:
            inv = CLASS_RESKINS_MAP.get(real_class, "")
            class_column_count_parts.append(
                f"SUM(CASE WHEN UPPER({table_type}.class_type)='{real_class}' OR UPPER({table_type}.class_type)='{inv}' THEN {table_type}.{table_count_column} ELSE 0 END) AS {real_class}_count"
            )
            select_class_in_parts.append(f"'{real_class}', '{inv}'")

        # Build main query to get warcount per player grouped by UUID, including guild
        query = f"""SELECT uuid_name.name,
    {','.join(class_column_count_parts)},
    SUM({table_type}.{table_count_column}) as all_wars,
    player_stats.guild
FROM {table_type}
LEFT JOIN uuid_name ON uuid_name.uuid={table_type}.uuid
LEFT JOIN player_stats ON player_stats.uuid={table_type}.uuid
WHERE UPPER({table_type}.class_type) IN ({','.join(select_class_in_parts)})
GROUP BY uuid_name.uuid, player_stats.guild
ORDER BY all_wars DESC;"""
        
        # Parse and validate the 'range' argument if provided
        if range:
            query = query.replace(
                "GROUP BY",
                f"AND {table_type}.time >= {left} AND {table_type}.time <= {right} GROUP BY"
            )

        # Execute the query
        res = await Database.fetch(query)

        # Map guild tags to guild names for filtering
        guild_names, _ = await guild_names_from_tags(guild_filter)

        name_to_ranking = {}
        player_to_guild = {}
        player_warcounts = {}

        # Filter and collect player warcount data according to input filters
        for rank, row in enumerate(res):
            name, total, guild = row["name"], row["all_wars"], row["guild"]
            if not name: continue  # Skip entries with no name
            classes_count = [row[f"{c}_count"] for c in listed_classes]
            
            if guild_filter and (guild not in guild_names):
                continue  # Skip players whose guild isn't in filter
            if names and ((name.lower() if name else None) not in names):
                continue  # Skip players not in specified names list

            name_to_ranking[name] = rank + 1
            player_to_guild[name] = guild
            player_warcounts[name] = classes_count

        # Return early if no matching players found
        if not player_warcounts:
            return await interaction.followup.send(embed=ErrorEmbed("No matching players found or no wars in specified range."))

        # Fetch guild tags for display, resolving priority if multiple tags per guild
        guild_to_tag = {}

        if player_to_guild:
            guilds_seen = set(player_to_guild.values())
            expanded_guilds_str = ','.join(f"'{g}'" for g in guilds_seen)
            res = await Database.fetch(
                f"SELECT guild, tag, priority FROM guild_tag_name WHERE guild IN ({expanded_guilds_str})"
            )
            for entry in res:
                current_priority = guild_to_tag.get(entry["guild"], ("", -1))[1]
                if entry["priority"] > current_priority:
                    guild_to_tag[entry["guild"]] = (entry["tag"], entry["priority"])

        # Prepare headers and rows for the leaderboard display
        headers = ["Rank", "Name", "Guild", *[f"{x}" for x in listed_classes], "Total"]
        rows = []

        # Assemble rows with rank, player name, guild tag, class warcounts, and total warcount
        for name in player_warcounts:
            row = (
                name_to_ranking[name],
                name,
                guild_to_tag.get(player_to_guild[name], ("None", -1))[0],
                *player_warcounts[name],
                sum(player_warcounts[name])
            )
            rows.append(row)

        # Sort rows descending by total warcount
        rows.sort(key=lambda x: x[-1], reverse=True)

        # Initialize WarcountBoardView for interactive pagination and display
        view = WarcountBoardView(interaction.user.id, headers, rows, listed_classes)

        if view.is_fancy:
            # If user supports "fancy" boards, send graphical leaderboard
            content = await build_warcount_board(view.data, view.page, view.listed_classes)
            await interaction.followup.send(view=view, file=content)
        else:
            # Otherwise, send a nicely formatted paginated text table with separators
            start, end = view.page * 10, (view.page + 1) * 10
            sliced = view.data[start:end]

            widths = [len(h) for h in view.headers]
            fmt = ' ┃ '.join(f'%{w}s' for w in widths)

            lines = [fmt % tuple(view.headers)]
            separator = ''.join('╋' if c == '┃' else '━' for c in lines[0])
            lines.append(separator)

            # Format each row, left-justifying cells to column widths
            for row in sliced:
                lines.append(' ┃ '.join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))

            lines.append(separator)

            # Send formatted text table inside a code block with syntax highlighting
            content = '```isbl\n' + '\n'.join(lines) + '```'
            await interaction.followup.send(content=content, view=view)



# Cog setup function for bot
async def setup(bot: commands.Bot):
    await bot.add_cog(Warcount(bot))
