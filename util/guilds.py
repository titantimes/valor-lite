import asyncio
from database import Database
from typing import List, Tuple, MutableSet
from util.requests import request


async def guild_name_from_tag(tag: str) -> str:
    """
    Retrieve the guild name corresponding to a given guild tag.
    
    Args:
        tag (str): The guild tag to look up.
        
    Returns:
        str | None: The name of the guild, or None if not found or invalid.
    
    Notes:
        - Tags containing "--" or ";" are considered invalid and return None.
        - If multiple entries have the same priority, this function queries the Wynncraft API
          to determine the one with the highest member count.
    """
    if "--" in tag or ";" in tag:
        return None  # Skip invalid tags
    
    guilds = await Database.fetch(
        f"SELECT * FROM guild_tag_name WHERE LOWER(tag)='{tag.lower()}' ORDER BY priority DESC"
    )
    
    if not len(guilds):
        return None  # No guild found in DB
        
    # If there are ties in priority, break tie by member count
    if len(guilds) >= 2 and guilds[0]["priority"] == guilds[1]["priority"]:
        revisions = []
        for g, tag, _ in guilds:
            res = request(f"https://api.wynncraft.com/v3/guild/{g}")
            n_members = res["members"]["total"]
            revisions.append(f"('{g}','{tag}',{n_members})")

        # Update DB with member counts
        await Database.fetch(f"REPLACE INTO guild_tag_name VALUES " + ','.join(revisions))
        # Sort by member count (descending)
        revisions.sort(key=lambda x: x[2], reverse=True)
        
        return revisions[0]["guild"]
    
    return guilds[0]["guild"]


async def guild_tag_from_name(name: str) -> str:
    """
    Retrieve the guild tag corresponding to a given guild name.
    
    Args:
        name (str): The full guild name to look up.
        
    Returns:
        str | None: The guild tag, or None if not found or invalid.
    
    Notes:
        - Names containing "-" or ";" are considered invalid.
        - If multiple entries have the same priority, the Wynncraft API is used
          to select the guild with the highest member count.
    """
    if "-" in name or ";" in name:
        return None  # Skip invalid names
    
    guilds = await Database.fetch(
        "SELECT * FROM guild_tag_name WHERE LOWER(guild)=%s ORDER BY priority DESC",
        (name.lower())
    )
    
    if not len(guilds):
        return None  # No guild found
    
    if len(guilds) >= 2 and guilds[0]["priority"] == guilds[1]["priority"]:
        revisions = []
        for g, tag, _ in guilds:
            res = request(f"https://api.wynncraft.com/v3/guild/{g}")
            n_members = res["members"]["total"]
            revisions.append(f"('{g}','{tag}',{n_members})")

        await Database.fetch(f"REPLACE INTO guild_tag_name VALUES " + ','.join(revisions))
        revisions.sort(key=lambda x: x[2], reverse=True)
        
        return revisions[0]["tag"]
    
    return guilds[0]["tag"]


async def guild_names_from_tags(tags: List[str]) -> Tuple[list[str], list[str]]:
    """
    Convert a list of guild tags into their corresponding guild names.
    
    Args:
        tags (List[str]): A list of guild tags.
        
    Returns:
        Tuple[list[str], list[str]]:
            - List of guild names (matching order of input list, None if not found)
            - List of unidentified tags that couldn't be resolved
    """
    name_map: dict[str, str] = {}
    unidentified: list[str] = []

    # Clean input (skip obviously invalid tags)
    valid_tags = [t for t in tags if "--" not in t and ";" not in t]
    if not valid_tags:
        return [None] * len(tags), tags  # All tags invalid

    # Batch DB lookup for efficiency
    placeholders = ",".join(["%s"] * len(valid_tags))
    query = f"""
        SELECT tag, guild
        FROM guild_tag_name
        WHERE LOWER(tag) IN ({placeholders})
        ORDER BY priority DESC
    """
    rows = await Database.fetch(query, tuple(t.lower() for t in valid_tags))

    # Choose first occurrence (highest priority due to ORDER BY)
    for row in rows:
        t = row["tag"].lower()
        if t not in name_map:
            name_map[t] = row["guild"]

    # Identify tags not found in DB
    db_identified = set(name_map.keys())
    missing = [t for t in valid_tags if t.lower() not in db_identified]

    # Fallback: Try individual API-based lookups
    if missing:
        fallback_results = await asyncio.gather(*(guild_name_from_tag(t) for t in missing))
        for tag, name in zip(missing, fallback_results):
            ltag = tag.lower()
            if name:
                name_map[ltag] = name
            else:
                unidentified.append(tag)

    # Preserve original input order, keep casing
    final_names = []
    for tag in tags:
        ltag = tag.lower()
        name = name_map.get(ltag)
        final_names.append(name if name else None)
        if ltag not in name_map and tag not in unidentified:
            unidentified.append(tag)

    return final_names, unidentified


async def guild_tags_from_names(names: List[str]) -> Tuple[MutableSet[str], List[str]]:
    """
    Convert a list of guild names into their corresponding tags.
    
    Args:
        names (List[str]): A list of guild names.
        
    Returns:
        Tuple[list[str], list[str]]:
            - List of guild tags (matching order of input list, None if not found)
            - List of unidentified names that couldn't be resolved
    """
    tag_map = {}
    unidentified = []

    # Clean input (skip invalid names)
    valid_names = [n for n in names if n and "-" not in n and ";" not in n]
    if not valid_names:
        return [None] * len(names), names  # All invalid

    # Batch DB lookup
    placeholders = ",".join(["%s"] * len(valid_names))
    query = f"""
        SELECT guild, tag
        FROM guild_tag_name
        WHERE LOWER(guild) IN ({placeholders})
        ORDER BY priority DESC
    """
    rows = await Database.fetch(query, tuple(n.lower() for n in valid_names))

    # Choose first occurrence (highest priority)
    for row in rows:
        gname = row["guild"].lower()
        if gname not in tag_map:
            tag_map[gname] = row["tag"]

    # Identify names missing in DB
    db_identified = set(tag_map.keys())
    missing = [n for n in valid_names if n.lower() not in db_identified]

    # Fallback: Try API-based resolution
    if missing:
        fallback_results = await asyncio.gather(*(guild_tag_from_name(n) for n in missing))
        for name, tag in zip(missing, fallback_results):
            lname = name.lower()
            if tag:
                tag_map[lname] = tag
            else:
                unidentified.append(name)

    # Preserve order, keep casing
    final_tags = []
    for name in names:
        lname = name.lower() if name else None
        tag = tag_map.get(lname)
        final_tags.append(tag if tag else None)
        if lname not in tag_map and name not in unidentified:
            unidentified.append(name)

    return final_tags, unidentified


async def player_guild_from_uuid(uuid: str) -> str:
    """
    Get the latest guild a player has joined using their UUID.
    
    Args:
        uuid (str): The player's UUID.
        
    Returns:
        str | None: The guild name, or None if the player has no recorded guild.
    """
    result = await Database.fetch(
        "SELECT joined FROM guild_join_log WHERE uuid=%s ORDER BY date DESC LIMIT 1", (uuid)
    )
    guild = None if not result else result[0]["joined"]
    return guild


async def player_guilds_from_uuids(uuids: list[str]) -> dict[str, str]:
    """
    Get the latest guilds for multiple players.
    
    Args:
        uuids (list[str]): List of player UUIDs.
        
    Returns:
        dict[str, str]: A mapping of UUID -> latest joined guild.
    """
    if not uuids:
        return {}

    placeholders = ",".join(["%s"] * len(uuids))
    query = f"""
        SELECT uuid, joined
        FROM guild_join_log
        WHERE uuid IN ({placeholders})
        ORDER BY date DESC
    """
    rows = await Database.fetch(query, tuple(uuids))

    player_guilds = {}
    for row in rows:
        if row["uuid"] not in player_guilds:  # Keep first occurrence (latest due to ORDER BY)
            player_guilds[row["uuid"]] = row["joined"]

    return player_guilds

