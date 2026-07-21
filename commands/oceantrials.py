import discord

from discord import app_commands
from discord.ext import commands
from typing import Literal

from core.config import config
from database import Database
from util.embeds import ErrorEmbed, PaginatedTextTableEmbed
from util.ranges import get_range_from_string, get_current_season


class OceanTrials(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    #arbitrary now i left them there fromw hen i had default pots
    WAR_POT = 500.0
    RAID_POT = 600.0
    WAR_TYPE_WEIGHTS = {
        "big": 1.3,
        "small": 1.0,
        "snipe": 1.7,
        "wipe": 2.3,
        "snake": 1.3,
        "reclaim": 2.3,
    }

    def lesharec(self, pointsname: dict[str, float], pot: float) -> dict[str, float]:
        totpoint = sum(pointsname.values())
        if totpoint <= 0:
            return {name: 0.0 for name in pointsname}

        return {
            name: (points / totpoint) * pot
            for name, points in pointsname.items()
        }

    def pctsharec(self, pointsname: dict[str, float]) -> dict[str, float]:
        totpoint = sum(pointsname.values())
        if totpoint <= 0:
            return {name: 0.0 for name in pointsname}

        raw_bp = {name: (points / totpoint) * 10000.0 for name, points in pointsname.items()}
        floor_bp = {name: int(value) for name, value in raw_bp.items()}
        remaining = 10000 - sum(floor_bp.values())

        if remaining > 0 and floor_bp:
            order = sorted(
                raw_bp.keys(),
                key=lambda name: (raw_bp[name] - floor_bp[name]),
                reverse=True,
            )
            for i in range(remaining):
                floor_bp[order[i % len(order)]] += 1

        return {name: floor_bp[name] / 100.0 for name in pointsname}

    def fmt(self, value: float) -> str:
        text = f"{value:.1f}"
        return text.rstrip("0").rstrip(".")

    def shorta(self, name: str, max_len: int = 12) -> str:
        if len(name) <= max_len:
            return name
        return name[: max_len - 3] + "..." #should fix everything up with tables 

    async def Fwarpoints(self, left: float, right: float) -> dict[str, float]:
        query = """
            WITH normalised_records AS (
                SELECT
                    A.uuid,
                    CASE
                        WHEN A.raid_type = 'eco' AND A.contribution = 0 THEN COALESCE(
                            (
                                SELECT R.contribution
                                FROM ano_reclaim_records R
                                WHERE R.time BETWEEN A.time - 3600 AND A.time + 3600
                                  AND NOT (R.raid_type = 'eco' AND R.contribution = 0)
                                ORDER BY R.contribution DESC, ABS(R.time - A.time) ASC
                                LIMIT 1
                            ),
                            0
                        )
                        ELSE A.contribution
                    END AS effective_contribution,
                    CASE
                        WHEN A.raid_type = 'eco' AND A.contribution = 0 THEN COALESCE(
                            (
                                SELECT R.raid_type
                                FROM ano_reclaim_records R
                                WHERE R.time BETWEEN A.time - 3600 AND A.time + 3600
                                  AND NOT (R.raid_type = 'eco' AND R.contribution = 0)
                                ORDER BY R.contribution DESC, ABS(R.time - A.time) ASC
                                LIMIT 1
                            ),
                            A.raid_type
                        )
                        ELSE A.raid_type
                    END AS effective_raid_type
                FROM ano_reclaim_records A
                WHERE A.time BETWEEN %s AND %s
            )
            SELECT U.name AS name,
                   SUM(N.effective_contribution * CASE N.effective_raid_type
                       WHEN 'big' THEN %s
                       WHEN 'small' THEN %s
                       WHEN 'snipe' THEN %s
                       WHEN 'wipe' THEN %s
                       WHEN 'snake' THEN %s
                       WHEN 'reclaim' THEN %s
                       ELSE 1.0
                   END) AS points
            FROM normalised_records N
            LEFT JOIN uuid_name U ON U.uuid = N.uuid
            GROUP BY N.uuid, U.name
            HAVING points > 0
        """

        weights = self.WAR_TYPE_WEIGHTS
        rows = await Database.fetch(
            query,
            (
                left,
                right,
                weights["big"],
                weights["small"],
                weights["snipe"],
                weights["wipe"],
                weights["snake"],
                weights["reclaim"],
            ),
        )

        result: dict[str, float] = {}
        for row in rows or []:
            if not row.get("name"):
                continue
            result[row["name"]] = float(row["points"] or 0)

        return result

    async def Fraidpoints(self, left: float, right: float) -> dict[str, float]:
        query = """
            WITH minute_player AS (
                SELECT FLOOR(A.time / 60) AS minute_bucket,
                       A.uuid,
                       SUM(A.num_raids) AS raids_in_bucket
                FROM guild_raid_records A
                WHERE A.guild = 'Titans Valor'
                  AND A.time BETWEEN %s AND %s
                GROUP BY FLOOR(A.time / 60), A.uuid
            ),
            minute_participants AS (
                SELECT minute_bucket,
                       COUNT(*) AS participant_count
                FROM minute_player
                GROUP BY minute_bucket
            )
            SELECT U.name AS name,
                   SUM(
                       P.raids_in_bucket *
                       CASE
                           WHEN C.participant_count = 1 THEN 1.0
                           WHEN C.participant_count = 2 THEN 1.0
                           WHEN C.participant_count = 3 THEN 1.0
                           WHEN C.participant_count = 4 THEN 2.5
                           ELSE 2.5
                       END
                   ) AS points
            FROM minute_player P
            JOIN minute_participants C ON C.minute_bucket = P.minute_bucket
            LEFT JOIN uuid_name U ON U.uuid = P.uuid
            GROUP BY P.uuid, U.name
            HAVING points > 0
        """

        rows = await Database.fetch(query, (left, right))

        result: dict[str, float] = {}
        for row in rows or []:
            if not row.get("name"):
                continue
            result[row["name"]] = float(row["points"] or 0)

        return result

    @app_commands.command(name="oceantrials", description="Ocean Trials points.")
    @app_commands.describe(
        mode="Which payout leaderboard to show: war, graid, or both",
        season="Season number (e.g., 31, 32) Reclaim data only recorded post 31",
        pot="Theoretical pot, if using both do X,Y"
    )
    async def oceantrials(
        self,
        interaction: discord.Interaction,
        mode: Literal["war", "graid", "both"] = "both",
        season: str = None,
        pot: str = None,
    ):
        await interaction.response.defer()

        if not season:
            current_season = await get_current_season()
            if not current_season:
                return await interaction.followup.send(embed=ErrorEmbed("No active season was found."))
            season = current_season[6:]

        try:
            seasonrang = int(season)
        except (TypeError, ValueError):
            return await interaction.followup.send(embed=ErrorEmbed("Invalid season number"))
        range_result = await get_range_from_string(f"season{season}", max_allowed_range=None)
        if not range_result:
            return await interaction.followup.send(embed=ErrorEmbed("Error with range"))
        left, right = range_result

        war_points = await self.Fwarpoints(left, right)
        raid_points = await self.Fraidpoints(left, right)

        show_le = bool(pot)
        war_pot = None
        raid_pot = None

        if show_le:
            parts = [part.strip() for part in pot.split(",") if part.strip()]
            try:
                if mode == "both":
                    if len(parts) != 2:
                        return await interaction.followup.send(
                            embed=ErrorEmbed("if both use X,Y where its war,raid")
                        )
                    war_pot = float(parts[0])
                    raid_pot = float(parts[1])
                    if war_pot <= 0 or raid_pot <= 0:
                        return await interaction.followup.send(embed=ErrorEmbed("Both pot values must be greater than 0"))
                else:
                    if len(parts) != 1:
                        return await interaction.followup.send(
                            embed=ErrorEmbed("1 mode selected, pot must be a one number.")
                        )
                    single_pot = float(parts[0])
                    if single_pot <= 0:
                        return await interaction.followup.send(embed=ErrorEmbed("Pot must be greater than 0."))

                    if mode == "war":
                        war_pot = single_pot
                    else:
                        raid_pot = single_pot
            except ValueError:
                return await interaction.followup.send(embed=ErrorEmbed("Number sonly"))

        if mode == "war":
            if not war_points:
                return await interaction.followup.send(embed=ErrorEmbed("No war data in the selected season."))

            if show_le:
                war_le = self.lesharec(war_points, war_pot)
                rows = [
                    [name, f"{points:.1f}", f"{war_le.get(name, 0.0):.2f}"]
                    for name, points in sorted(war_points.items(), key=lambda x: x[1], reverse=True)
                ]
                title = f"Ocean Trials War Payouts - Season {seasonrang}"
                footer = f"Hypothetical war pot: {war_pot:.2f} LE"
                headers = ["Name", "War Points", "War LE"]
            else:
                war_pct = self.pctsharec(war_points)
                rows = [
                    [name, f"{points:.1f}", f"{war_pct.get(name, 0.0):.2f}%"]
                    for name, points in sorted(war_points.items(), key=lambda x: x[1], reverse=True)
                ]
                title = f"Ocean Trials War Share - Season {seasonrang}"
                footer = "Set 'pot' to convert shares into LE payouts"
                headers = ["Name", "War Points", "War %"]
        elif mode == "graid":
            if not raid_points:
                return await interaction.followup.send(embed=ErrorEmbed("No guild raid data in the selected season."))

            if show_le:
                raid_le = self.lesharec(raid_points, raid_pot)
                rows = [
                    [name, f"{points:.1f}", f"{raid_le.get(name, 0.0):.2f}"]
                    for name, points in sorted(raid_points.items(), key=lambda x: x[1], reverse=True)
                ]
                title = f"Ocean Trials Guild Raid Payouts - Season {seasonrang}"
                footer = f"Hypothetical raid pot: {raid_pot:.2f} LE | Guild: Titans Valor"
                headers = ["Name", "Raid Points", "Raid LE"]
            else:
                raid_pct = self.pctsharec(raid_points)
                rows = [
                    [name, f"{points:.1f}", f"{raid_pct.get(name, 0.0):.2f}%"]
                    for name, points in sorted(raid_points.items(), key=lambda x: x[1], reverse=True)
                ]
                title = f"Ocean Trials Guild Raid Share - Season {seasonrang}"
                footer = "Guild: Titans Valor | Set 'pot' to see LE payouts"
                headers = ["Name", "Raid Points", "Raid %"]
        else:
            combined_names = set(war_points.keys()) | set(raid_points.keys())
            if not combined_names:
                return await interaction.followup.send(embed=ErrorEmbed("No war or guild raid data in the selected season."))

            rows = []
            if show_le:
                war_le = self.lesharec(war_points, war_pot)
                raid_le = self.lesharec(raid_points, raid_pot)
                for name in combined_names:
                    w_points = war_points.get(name, 0.0)
                    r_points = raid_points.get(name, 0.0)
                    w_le = war_le.get(name, 0.0)
                    r_le = raid_le.get(name, 0.0)
                    rows.append([
                        self.shorta(name),
                        self.fmt(w_points),
                        f"{w_le:.2f}",
                        self.fmt(r_points),
                        f"{r_le:.2f}",
                    ])

                rows.sort(key=lambda row: (float(row[2]) + float(row[4])), reverse=True)
                title = f"Ocean Trials Combined Payout Shares - Season {seasonrang}"
                footer = f"Hypothetical war pot: {war_pot:.2f} LE | Hypothetical raid pot: {raid_pot:.2f} LE"
                headers = ["Name", "War Pts", "War LE", "Raid Pts", "Raid LE"]
            else:
                war_pct = self.pctsharec(war_points)
                raid_pct = self.pctsharec(raid_points)
                for name in combined_names:
                    w_points = war_points.get(name, 0.0)
                    r_points = raid_points.get(name, 0.0)
                    w_pct = war_pct.get(name, 0.0)
                    r_pct = raid_pct.get(name, 0.0)
                    rows.append([
                        self.shorta(name),
                        self.fmt(w_points),
                        f"{w_pct:.1f}%",
                        self.fmt(r_points),
                        f"{r_pct:.1f}%",
                    ])

                rows.sort(
                    key=lambda row: (
                        (float(row[2].rstrip('%')) / 100.0) * self.WAR_POT
                        + (float(row[4].rstrip('%')) / 100.0) * self.RAID_POT
                    ),
                    reverse=True,
                )
                title = f"Ocean Trials Combined Share - Season {seasonrang}"
                footer = "Guild: Titans Valor | Set 'pot' to 'warPot,raidPot' for projected LE"
                headers = ["Name", "War Pts", "War %", "Raid Pts", "Raid %"]

        await PaginatedTextTableEmbed.send(
            interaction,
            headers,
            rows,
            title=title,
            footer=footer,
            color=discord.Color.teal(),
            rows_per_page=20,
        )


async def setup(bot: commands.Bot):
    cog = OceanTrials(bot)
    await bot.add_cog(cog)

    existing_global = bot.tree.get_command("oceantrials")
    if existing_global:
        bot.tree.remove_command("oceantrials")

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.oceantrials, guild=guild)
