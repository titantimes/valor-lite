from dotenv import load_dotenv
import os, json


load_dotenv()


class Config:
    TOKEN = os.getenv("DISCORD_TOKEN")

    OWNER_ID = int(os.getenv("OWNER_ID", 0))

    TESTING = os.getenv("TESTING", "false").lower() == "true"

    DB_HOST = os.getenv("DATABASE_HOST")
    DB_PORT = int(os.getenv("DATABASE_PORT", 3306))  # default MySQL port
    DB_USER = os.getenv("DATABASE_USER")
    DB_PASSWORD = os.getenv("DATABASE_PASSWORD")
    DB_NAME = os.getenv("DATABASE_NAME")

    HYPIXEL_API_KEY = os.getenv("HYPIXEL_API_KEY")
    WYNN_API_KEY = os.getenv("WYNN_API_KEY")

    #json array in .env
    ANO_COMMANDS_GUILD_IDS = json.loads(os.getenv("ANO_COMMANDS_GUILD_IDS"))

    ANO_MEMBER_ROLES = {int(role) for role in json.loads(os.getenv("ANO_MEMBER_ROLES"))}
    ANO_MILITARY_ROLES = {int(role) for role in json.loads(os.getenv("ANO_MILITARY_ROLES"))}

    ANO_HIGH_RANK_ROLES = {int(role) for role in json.loads(os.getenv("ANO_HIGH_RANK_ROLES"))}
    ANO_TITAN_ROLES = {int(role) for role in json.loads(os.getenv("ANO_TITAN_ROLES"))}
    ANO_CHIEF_ROLES = {int(role) for role in json.loads(os.getenv("ANO_CHIEF_ROLES"))}

    TITAN_CHAT_CHANNEL_ID = json.loads(os.getenv("TITAN_CHAT_CHANNEL_ID"))
    TERRITORY_TRACKER_CHANNEL_ID = json.loads(os.getenv("TERRITORY_TRACKER_CHANNEL_ID"))
    ANO_TERRITORY_TRACKER_CHANNEL_ID = json.loads(os.getenv("ANO_TERRITORY_TRACKER_CHANNEL_ID"))

config = Config()
