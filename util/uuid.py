import asyncio, re, discord

from database import Database
from util.requests import request
from pymysql.err import IntegrityError



def format_uuid(raw: str) -> str:
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"



async def get_uuid_from_name(player: str, interaction: discord.Interaction | None = None) -> str | None:
    if "-" in player:
        return None

    result = await Database.fetch("SELECT uuid FROM uuid_name WHERE name=%s", (player,))
    if result and interaction and len(result) > 1:
        select_view = discord.ui.View()
        select = discord.ui.Select(
            placeholder=f"Multiple matches found for {player}. Pick one...",
            options=[discord.SelectOption(label=result[i]["uuid"]) for i in range(len(result))]
        )

        uuid = ""
        async def callback(select_interaction: discord.Interaction):
            nonlocal uuid
            uuid = select.values[0]
            await select_interaction.response.defer()
            await select_interaction.message.delete()
            select_view.stop()

        select.callback = callback
        select_view.add_item(select)

        await interaction.followup.send(f"Multiple UUIDs found for '{player}'. Please select one:", view=select_view, ephemeral=True)

        await select_view.wait()
        return uuid

    if result:
        return result[0]["uuid"]

    res = await request(f"https://api.mojang.com/users/profiles/minecraft/{player}")
    if not res:
        return None

    formatted = format_uuid(res["id"])

    try:
        await Database.fetch("INSERT INTO uuid_name (uuid, name) VALUES (%s, %s)", (formatted, player))
    except IntegrityError as e:
        if e.args[0] == 1062:
            await Database.fetch("UPDATE uuid_name SET name=%s WHERE uuid=%s", (player, formatted))
        else:
            raise
    return formatted



async def get_name_from_uuid(uuid: str) -> str | None:
    res = await Database.fetch("SELECT * FROM uuid_name WHERE uuid=%s LIMIT 1", (uuid,))
    if res:
        return res[0]["name"]

    res = await request(f"https://api.mojang.com/user/profile/{uuid.replace('-', '')}")
    if not res:
        return None

    await Database.fetch("INSERT INTO uuid_name VALUES (%s, %s)", (uuid, res["name"]))
    return res["name"]



async def get_names_from_uuids(uuids: list[str]) -> dict[str, str]:
    if not uuids:
        return {}

    placeholders = ",".join(["%s"] * len(uuids))
    query = f"SELECT uuid, name FROM uuid_name WHERE uuid IN ({placeholders})"

    rows = await Database.fetch(query, tuple(uuids))
    names: dict[str, str] = {row["uuid"]: row["name"] for row in rows}
    missing = [uuid for uuid in uuids if uuid not in names]

    if missing:
        fetched = await asyncio.gather(
            *(request(f"https://api.mojang.com/user/profile/{uuid.replace('-', '')}") for uuid in missing)
        )

        inserts = []
        for uuid, res in zip(missing, fetched):
            if res and "name" in res:
                names[uuid] = res["name"]
                inserts.append((uuid, res["name"]))

        if inserts:
            for insert in inserts:
                await Database.fetch("INSERT INTO uuid_name (uuid, name) VALUES (%s, %s)", insert)

    return names



def detect_uuid_or_name(value: str) -> str:
    uuid_regex = re.compile(
        r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )

    username_regex = re.compile(r"^[a-zA-Z0-9_]{3,16}$")
    if uuid_regex.match(value):
        return "uuid"
    elif username_regex.match(value):
        return "name"
    else:
        return "invalid"


