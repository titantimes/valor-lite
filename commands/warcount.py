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

        if guild_wise and (players or classes or guilds):
            return await interaction.followup.send(embed=ErrorEmbed(
                "You cannot use `guild_wise` together with `players` or `guilds` or `classes`."
            ))

        if range:
            if range.strip().lower() == "all":
                range = None
            else:
                range = await get_range_from_string(range, max_allowed_range=None)
                if not range:
                    return await interaction.followup.send(embed=ErrorEmbed("Invalid range input"))
                left, right = range

        guild_filter = [g.strip() for g in guilds.split(",")] if guilds else []
        names = [x.strip().lower() for x in players.split(",")] if players else None
        listed_classes = [c.strip().upper() for c in classes.split(",")] if classes else ["ARCHER", "WARRIOR", "MAGE", "ASSASSIN", "SHAMAN"]

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

            headers = ["Guild", "Wars"]
            rows = []
            for result in res:
                rows.append((
                    result["guild"],
                    int(result["wars"])
                ))

            view = BoardView(interaction.user.id, rows, is_guild_board=True, headers=headers)

            if view.is_fancy:
                board = await build_board(view.data, view.page, view.is_guild_board)
                return await interaction.followup.send(view=view, file=board)
            else:
                start = view.page * 10
                end = start + 10
                sliced = view.data[start:end]
                for i in range_alt(len(sliced)):
                    sliced[i] = [f"{i+start+1}.", sliced[i][0], sliced[i][1]]

                return await PaginatedTextTableEmbed.send(interaction, headers, rows, "Warcount sum for guilds")


        table_type = "cumu_warcounts" if not range else "delta_warcounts"
        table_count_column = "warcount" if not range else "warcount_diff"

        class_column_count_parts = []
        select_class_in_parts = []

        for real_class in listed_classes:
            inv = CLASS_RESKINS_MAP.get(real_class, "")
            class_column_count_parts.append(
                f"SUM(CASE WHEN UPPER({table_type}.class_type)='{real_class}' OR UPPER({table_type}.class_type)='{inv}' THEN {table_type}.{table_count_column} ELSE 0 END) AS {real_class}_count"
            )
            select_class_in_parts.append(f"'{real_class}', '{inv}'")

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
        
        if range:
            query = query.replace(
                "GROUP BY",
                f"AND {table_type}.time >= {left} AND {table_type}.time <= {right} GROUP BY"
            )

        res = await Database.fetch(query)

        guild_names, _ = await guild_names_from_tags(guild_filter)

        name_to_ranking = {}
        player_to_guild = {}
        player_warcounts = {}

        for rank, row in enumerate(res):
            name, total, guild = row["name"], row["all_wars"], row["guild"]
            if not name: continue
            classes_count = [row[f"{c}_count"] for c in listed_classes]
            
            if guild_filter and (guild not in guild_names):
                continue
            if names and ((name.lower() if name else None) not in names):
                continue

            name_to_ranking[name] = rank + 1
            player_to_guild[name] = guild
            player_warcounts[name] = classes_count

        if not player_warcounts:
            return await interaction.followup.send(embed=ErrorEmbed("No matching players found or no wars in specified range."))

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

        headers = ["Rank", "Name", "Guild", *[f"{x}" for x in listed_classes], "Total"]
        rows = []

        for name in player_warcounts:
            row = (
                name_to_ranking[name],
                name,
                guild_to_tag.get(player_to_guild[name], ("None", -1))[0],
                *player_warcounts[name],
                sum(player_warcounts[name])
            )
            rows.append(row)

        rows.sort(key=lambda x: x[-1], reverse=True)

        view = WarcountBoardView(interaction.user.id, headers, rows, listed_classes)

        if view.is_fancy:
            content = await build_warcount_board(view.data, view.page, view.listed_classes)
            await interaction.followup.send(view=view, file=content)
        else:
            start, end = view.page * 10, (view.page + 1) * 10
            sliced = view.data[start:end]

            widths = [len(h) for h in view.headers]
            fmt = ' ┃ '.join(f'%{w}s' for w in widths)

            lines = [fmt % tuple(view.headers)]
            separator = ''.join('╋' if c == '┃' else '━' for c in lines[0])
            lines.append(separator)

            for row in sliced:
                lines.append(' ┃ '.join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
            lines.append(separator)
            content = '```isbl\n' + '\n'.join(lines) + '```'
            await interaction.followup.send(content=content, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Warcount(bot))
