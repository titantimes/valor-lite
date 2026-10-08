import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from core.antispam import rate_limit_check
from database import Database
from util.embeds import ErrorEmbed, PaginatedTextTable
from util.requests import request
from util.uuid import get_uuid_from_name

MERGE_WINDOW_SECONDS = 3600

def gname(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return None if value.casefold() in {"", "none", "null"} else value

def gkey(value):
    return value.casefold() if value else None

def rankv(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return None if value.casefold() in {"", "none", "null", "n/a"} else value #these tables suck

def capitalrank(value):
    rank = rankv(value)
    return rank.title() if rank else "N/A"

def latestrecord(join_logs, activity_logs):
    timestamps = []
    for entries, key in ((join_logs, "date"), (activity_logs, "timestamp")):
        for entry in entries:
            try:
                timestamps.append(int(entry[key]))
            except (KeyError, TypeError, ValueError):
                continue
    return max(timestamps, default=None)

def builderh(join_logs, activity_logs):
    transitions = []
    activities = []
    rank_evidence = []
    for entry in join_logs:
        try:
            timestamp = int(entry["date"])
            old_guild = gname(entry.get("old"))
            joined_guild = gname(entry.get("joined"))
            old_rank = rankv(entry.get("old_rank"))
        except (KeyError, TypeError, ValueError):
            continue

        transition = {
            "timestamp": timestamp,
            "old": old_guild,
            "old_rank": old_rank,
            "joined": joined_guild,
        }
        transitions.append(transition)
        if old_guild and old_rank:
            rank_evidence.append((old_guild, old_rank, timestamp))

    for entry in activity_logs:
        try:
            timestamp = int(entry["timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        guild = gname(entry.get("guild"))
        if guild:
            activities.append({"timestamp": timestamp, "guild": guild})

    records = [
        (event["timestamp"], "transition", event) for event in transitions
    ] + [
        (event["timestamp"], "activity", event) for event in activities
    ]
    records.sort(key=lambda record: record[0])

    clusters = []
    for record in records:
        if not clusters or record[0] - clusters[-1][0][0] >= MERGE_WINDOW_SECONDS:
            clusters.append([record])
        else:
            clusters[-1].append(record)
    points = []

    def pointed(guild, rank, timestamp, priority):
        if guild is None:
            points.append((None, None, timestamp, priority))
            return
        if not rank:
            candidates = [
                (abs(evidence_timestamp - timestamp), evidence_rank)
                for evidence_guild, evidence_rank, evidence_timestamp in rank_evidence
                if gkey(evidence_guild) == gkey(guild)
                and abs(evidence_timestamp - timestamp) < MERGE_WINDOW_SECONDS
            ]
            rank = min(candidates, default=(None, None))[1]
        points.append((guild, rank, timestamp, priority))

    for cluster in clusters:
        cluster_transitions = sorted(
            (event for _, kind, event in cluster if kind == "transition"),
            key=lambda event: event["timestamp"],
        )
        cluster_activities = sorted(
            (event for _, kind, event in cluster if kind == "activity"),
            key=lambda event: event["timestamp"],
        )

        if not cluster_transitions:
            latest_activity = cluster_activities[-1]
            pointed(latest_activity["guild"], None, latest_activity["timestamp"], 1)
            continue

        first_transition = cluster_transitions[0]
        last_transition = cluster_transitions[-1]
        old_guild = first_transition["old"]
        old_rank = first_transition["old_rank"]
        before_transition = [
            event for event in cluster_activities
            if event["timestamp"] <= first_transition["timestamp"]
        ]
        if before_transition:
            old_guild = before_transition[-1]["guild"]
            old_rank = None

        joined_guild = last_transition["joined"]
        after_transition = [
            event for event in cluster_activities
            if event["timestamp"] >= last_transition["timestamp"]
        ]
        if after_transition:
            joined_guild = after_transition[-1]["guild"]

        boundary = last_transition["timestamp"]
        if after_transition and after_transition[-1]["timestamp"] > boundary:
            boundary = after_transition[-1]["timestamp"]

        if gkey(old_guild) == gkey(joined_guild):
            pointed(joined_guild or old_guild, old_rank, boundary, 1)
            continue

        pointed(joined_guild, None, boundary, 2)
        if old_guild:
            pointed(old_guild, old_rank, boundary, 1)
            if before_transition:
                pointed(old_guild, None, before_transition[-1]["timestamp"], 0)

    points.sort(key=lambda point: (point[2], point[3]), reverse=True)

    states = []
    for guild, rank, timestamp, _ in points:
        if states and gkey(states[-1][0]) == gkey(guild):
            if not states[-1][1] and rank:
                states[-1][1] = rank
            states[-1][3] = min(states[-1][3], timestamp)
            continue
        states.append([guild, rank, timestamp, timestamp])

    history = []
    for index, (guild, rank, latest_timestamp, earliest_timestamp) in enumerate(states):
        join_timestamp = earliest_timestamp
        leave_timestamp = latest_timestamp if index > 0 else None
        history.append([guild, rank or "N/A", join_timestamp, leave_timestamp])

    return [row for row in history if row[0]]


class History(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(name="history", description="Shows the guild membership history of a player.")
    @app_commands.describe(username="The player's username")
    @rate_limit_check()
    async def history(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        uuid = await get_uuid_from_name(username, interaction)
        if not uuid:
            return await interaction.followup.send(embed=ErrorEmbed("Player not found."))

        join_logs = await Database.fetch(
            "SELECT * FROM guild_join_log WHERE uuid=%s ORDER BY date DESC", (uuid)
        )
        activity_logs = await Database.fetch(
            "SELECT * FROM activity_members WHERE uuid=%s ORDER BY timestamp DESC", (uuid)
        )

        history = builderh(join_logs, activity_logs)

        try:
            api_data = await request(f"https://api.wynncraft.com/v3/player/{username}?fullResult", use_wynn_auth=True)
            guild_info = api_data.get("guild")
            if guild_info:
                api_guild = gname(guild_info.get("name"))
                api_rank = rankv(guild_info.get("rank")) or "N/A"
                if api_guild and history and gkey(history[0][0]) != gkey(api_guild):
                    boundary = latestrecord(join_logs, activity_logs)
                    history[0][3] = boundary
                    history.insert(0, [api_guild, api_rank, boundary, None])
                elif api_guild and history:
                    history[0][1] = api_rank
                elif api_guild:
                    history.append([api_guild, api_rank, None, None])
        except Exception:
            pass

        if not history:
            return await interaction.followup.send(embed=ErrorEmbed("No guild history found for this player."))

        rows = []
        for guild, rank, join, leave in history:
            join_str = datetime.fromtimestamp(join).strftime("%d %b %Y %H:%M") if join else "N/A"
            leave_str = datetime.fromtimestamp(leave).strftime("%d %b %Y %H:%M") if leave else "N/A"
            rows.append([guild, capitalrank(rank), join_str, leave_str])

        await PaginatedTextTable.send(
            interaction,
            ["Guild", "Rank", "Join Date", "Leave Date"],
            rows,
            title=f"Guild History of {username}",
            footer="Membership tracking updated 29 Sep 2026. Most entries at this date will be prior to it.",
            rows_per_page=15
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(History(bot))
