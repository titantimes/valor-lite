import discord

from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from database import Database
from util.board import BoardView, build_board, format_board_table_text
from util.embeds import ErrorEmbed
from util.guilds import guild_names_from_tags
from util.ranges import get_range_from_string


RAID_ORDER = ["tcc", "onol", "notg", "tna", "twp"]

RAID_DEFS = {
    "tcc": {
        "cumu_col": "tcc",
        "delta_name": "The Canyon Colossus",
        "short": "TCC",
    },
    "onol": {
        "cumu_col": "onol",
        "delta_name": "Orphion's Nexus of Light",
        "short": "ONOL",
    },
    "notg": {
        "cumu_col": "notg",
        "delta_name": "Nest of the Grootslangs",
        "short": "NOTG",
    },
    "tna": {
        "cumu_col": "tna",
        "delta_name": "The Nameless Anomaly",
        "short": "TNA",
    },
    "twp": {
        "cumu_col": "twp",
        "delta_name": "The Wartorn Palace",
        "short": "TWP",
    },
}

RAID_ALIASES = {
    "tcc": "tcc",
    "the canyon colossus": "tcc",
    "canyon colossus": "tcc",
    "onol": "onol",
    "nol": "onol",
    "orphion": "onol",
    "orphion's nexus of light": "onol",
    "nexus of light": "onol",
    "notg": "notg",
    "nog": "notg",
    "nest of the grootslangs": "notg",
    "grootslangs": "notg",
    "tna": "tna",
    "the nameless anomaly": "tna",
    "nameless anomaly": "tna",
    "twp": "twp",
    "the wartorn palace": "twp",
    "wartorn palace": "twp",
}


def normaliserf(raid_input: str | None) -> tuple[list[str], list[str]]:
    if not raid_input:
        return [], []

    normalised = []
    invalid = []

    for raw in [x.strip() for x in raid_input.split(",") if x.strip()]:
        key = RAID_ALIASES.get(raw.lower())
        if not key:
            invalid.append(raw)
            continue
        if key not in normalised:
            normalised.append(key)

    return normalised, invalid


def sql_quote(value: str) -> str:
    return value.replace("'", "''")


class GRaids2(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(name="graids2", description="Guild raid count leaderboard (new data model)")
    @app_commands.describe(
        guilds="Filter by guild tags (comma-separated)",
        range="Number of days ago, range like '0,7', or season name (omit for all-time)",
        players="Filter by player usernames (comma-separated)",
        raid="Filter by raid(s), e.g. 'tcc', 'onol', 'notg', 'tna', 'twp'",
        guild_wise="Show raid totals per guild instead of individual players",
    )
    @rate_limit_check()
    async def graids2(
        self,
        interaction: discord.Interaction,
        guilds: str = None,
        range: str = None,
        players: str = None,
        raid: str = None,
        guild_wise: bool = False,
    ):
        await interaction.response.defer()

        if guild_wise and (players or guilds):
            return await interaction.followup.send(
                embed=ErrorEmbed("You cannot use `guild_wise` together with `players` or `guilds`.")
            )

        if guilds and players:
            return await interaction.followup.send(
                embed=ErrorEmbed("You cannot use `players` and `guilds` together.")
            )

        selected_raids, invalid_raids = normaliserf(raid)
        if invalid_raids:
            valid_keys = ", ".join(RAID_ORDER)
            return await interaction.followup.send(
                embed=ErrorEmbed(f"Invalid raid filter(s): {', '.join(invalid_raids)}. Valid keys: {valid_keys}.")
            )

        active_raids = selected_raids if selected_raids else list(RAID_ORDER)
        active_short = [RAID_DEFS[key]["short"] for key in active_raids]

        using_range = False
        left = None
        right = None
        if range and range.strip().lower() != "all":
            parsed_range = await get_range_from_string(range, max_allowed_range=None)
            if not parsed_range:
                return await interaction.followup.send(embed=ErrorEmbed("Invalid range input"))
            left, right = parsed_range
            using_range = True

        uuid_filters = []
        if players:
            names = [n.strip() for n in players.split(",") if n.strip()]
            res = await Database.fetch(
                "SELECT uuid FROM uuid_name WHERE name IN (" + ",".join(["%s"] * len(names)) + ")",
                names,
            )
            if not res:
                return await interaction.followup.send(
                    embed=ErrorEmbed(f"No UUIDs found for: {players}"),
                    ephemeral=True,
                )

            uuid_filters = [entry["uuid"] for entry in res]
            if not uuid_filters:
                return await interaction.followup.send(
                    embed=ErrorEmbed("No valid UUIDs provided."),
                    ephemeral=True,
                )

        guild_names = []
        if guilds:
            tags = [tag.strip() for tag in guilds.split(",") if tag.strip()]
            guild_names, _ = await guild_names_from_tags(tags)

        if using_range:
            row_result = await self.deltaq(
                left,
                right,
                active_raids,
                uuid_filters,
                guild_names,
                guild_wise,
            )
        else:
            row_result = await self.cumuq(
                active_raids,
                uuid_filters,
                guild_names,
                guild_wise,
            )

        if not row_result:
            return await interaction.followup.send(
                embed=ErrorEmbed("No results for the specified parameters."),
                ephemeral=True,
            )

        rank_values = None
        if not guild_wise:
            if using_range:
                global_rows = await self.deltaq(
                    left,
                    right,
                    active_raids,
                    [],
                    [],
                    False,
                    limit=None,
                )
            else:
                global_rows = await self.cumuq(
                    active_raids,
                    [],
                    [],
                    False,
                    limit=None,
                )

            rank_map = {}
            for idx, row in enumerate(global_rows):
                uuid = row.get("uuid")
                if uuid and uuid not in rank_map:
                    rank_map[uuid] = idx + 1
            rank_values = [rank_map.get(row.get("uuid"), idx + 1) for idx, row in enumerate(row_result)]

        if guild_wise:
            image_rows = [[row["guild"], *[str(row[k]) for k in active_raids], str(row["total"])] for row in row_result]
            text_rows = image_rows
            text_headers = ["Guild", *active_short, "Total"]
        elif players:
            image_rows = [[row["name"] or "Unknown", *[str(row[k]) for k in active_raids], str(row["total"])] for row in row_result]
            text_rows = [[row["name"] or "Unknown", row["guild"], *[str(row[k]) for k in active_raids], str(row["total"])] for row in row_result]
            text_headers = ["Name", "Guild", *active_short, "Total"]
        else:
            image_rows = [[row["name"] or "Unknown", *[str(row[k]) for k in active_raids], str(row["total"])] for row in row_result]
            text_rows = image_rows
            text_headers = ["Name", *active_short, "Total"]

        selected_raid_labels = ", ".join(active_short)
        range_label = "All-Time" if not using_range else (range or "Custom")
        title = f"Raids [{selected_raid_labels}] ({range_label})"

        hide_rank = bool(players) and len(image_rows) == 1

        view = BoardView(
            interaction.user.id,
            image_rows,
            title=title,
            stat_counter="Raids",
            is_guild_board=guild_wise,
            use_text_embed=False,
            show_rank=not hide_rank,
            text_data=text_rows,
            text_headers=text_headers,
            image_value_headers=[*active_short, "Total"],
            rank_values=rank_values,
        )

        if view.is_fancy:
            board = await build_board(
                view.data,
                view.page,
                is_guild_board=guild_wise,
                show_rank=not hide_rank,
                value_headers=view.image_value_headers,
                rank_values=view.rank_values,
            )
            await interaction.followup.send(view=view, file=board)
        else:
            table = format_board_table_text(
                view.text_headers,
                view.text_data,
                view.page,
                title=view.title,
                show_rank=not hide_rank,
                rank_values=view.rank_values,
            )
            await interaction.followup.send(table, view=view)


    async def cumuq(
        self,
        active_raids: list[str],
        uuid_filters: list[str],
        guild_names: list[str],
        guild_wise: bool,
        limit: int | None = 50,
    ) -> list[dict]:
        sum_columns = [f"SUM(COALESCE(A.{RAID_DEFS[key]['cumu_col']}, 0)) AS {key}" for key in active_raids]
        total_expr = " + ".join([f"SUM(COALESCE(A.{RAID_DEFS[key]['cumu_col']}, 0))" for key in active_raids])

        base_join = """
FROM cumu_graids A
JOIN (
    SELECT uuid, MAX(time) AS latest_time
    FROM cumu_graids
    GROUP BY uuid
) latest ON latest.uuid = A.uuid AND latest.latest_time = A.time
"""

        if uuid_filters:
            placeholders = ",".join(["%s"] * len(uuid_filters))
            query = f"""
SELECT
    A.uuid,
    B.name,
    A.guild,
    {", ".join(sum_columns)},
    ({total_expr}) AS total
{base_join}
LEFT JOIN uuid_name B ON A.uuid = B.uuid
WHERE A.uuid IN ({placeholders})
GROUP BY A.uuid, A.guild
ORDER BY total DESC
{"LIMIT " + str(limit) if limit else ""};
"""
            return await Database.fetch(query, uuid_filters)

        if guild_wise:
            query = f"""
SELECT
    A.guild,
    {", ".join(sum_columns)},
    ({total_expr}) AS total
{base_join}
GROUP BY A.guild
ORDER BY total DESC
LIMIT 50;
"""
            return await Database.fetch(query)

        where_clause = ""
        args = []
        if guild_names:
            placeholders = ",".join(["%s"] * len(guild_names))
            where_clause = f"WHERE A.guild IN ({placeholders})"
            args.extend(guild_names)

        query = f"""
SELECT
    A.uuid,
    B.name,
    {", ".join(sum_columns)},
    ({total_expr}) AS total
{base_join}
LEFT JOIN uuid_name B ON A.uuid = B.uuid
{where_clause}
GROUP BY A.uuid
ORDER BY total DESC
{"LIMIT " + str(limit) if limit else ""};
"""
        return await Database.fetch(query, args)


    async def deltaq(
        self,
        left: float,
        right: float,
        active_raids: list[str],
        uuid_filters: list[str],
        guild_names: list[str],
        guild_wise: bool,
        limit: int | None = 50,
    ) -> list[dict]:
        raid_cases = []
        for key in active_raids:
            quoted_name = sql_quote(RAID_DEFS[key]["delta_name"])
            raid_cases.append(
                f"SUM(CASE WHEN A.raid_type = '{quoted_name}' THEN A.graidcount_diff ELSE 0 END) AS {key}"
            )

        total_expr = " + ".join([
            f"SUM(CASE WHEN A.raid_type = '{sql_quote(RAID_DEFS[key]['delta_name'])}' THEN A.graidcount_diff ELSE 0 END)"
            for key in active_raids
        ])

        infilv = [RAID_DEFS[key]["delta_name"] for key in active_raids]
        raidw = ""
        raidwargs = []
        if infilv:
            placeholders = ",".join(["%s"] * len(infilv))
            raidw = f" AND A.raid_type IN ({placeholders})"
            raidwargs.extend(infilv)

        if uuid_filters:
            placeholders = ",".join(["%s"] * len(uuid_filters))
            query = f"""
SELECT
    A.uuid,
    B.name,
    A.guild,
    {", ".join(raid_cases)},
    ({total_expr}) AS total
FROM delta_graids A
LEFT JOIN uuid_name B ON A.uuid = B.uuid
WHERE A.time > %s
  AND A.time <= %s
  {raidw}
  AND A.uuid IN ({placeholders})
GROUP BY A.uuid, A.guild
ORDER BY total DESC
{"LIMIT " + str(limit) if limit else ""};
"""
            return await Database.fetch(query, [left, right, *raidwargs, *uuid_filters])

        if guild_wise:
            query = f"""
SELECT
    A.guild,
    {", ".join(raid_cases)},
    ({total_expr}) AS total
FROM delta_graids A
WHERE A.time > %s
  AND A.time <= %s
  {raidw}
GROUP BY A.guild
ORDER BY total DESC
LIMIT 50;
"""
            return await Database.fetch(query, [left, right, *raidwargs])

        g_where = ""
        guild_args = []
        if guild_names:
            placeholders = ",".join(["%s"] * len(guild_names))
            g_where = f" AND A.guild IN ({placeholders})"
            guild_args.extend(guild_names)

        query = f"""
SELECT
    A.uuid,
    B.name,
    {", ".join(raid_cases)},
    ({total_expr}) AS total
FROM delta_graids A
LEFT JOIN uuid_name B ON A.uuid = B.uuid
WHERE A.time > %s
  AND A.time <= %s
  {raidw}
  {g_where}
GROUP BY A.uuid
ORDER BY total DESC
{"LIMIT " + str(limit) if limit else ""};
"""
        return await Database.fetch(query, [left, right, *raidwargs, *guild_args])


async def setup(bot: commands.Bot):
    await bot.add_cog(GRaids2(bot))
