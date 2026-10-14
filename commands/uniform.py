import discord, ast, base64
from discord import app_commands, File
from discord.ext import commands
from PIL import Image

from core.config import config
from util.embeds import ErrorEmbed
from util.roles import is_ANO_member
from util.requests import request


class Uniform(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @app_commands.command(
        name="uniform",
        description="Generates skin with ANO uniform based on the provided username."
    )
    @app_commands.choices(
        skin_variant=[
            app_commands.Choice(name="Male", value="male"),
            app_commands.Choice(name="Female", value="female")
        ]
    )
    async def uniform(self, interaction: discord.Interaction, username: str, skin_variant: app_commands.Choice[str]):
        await interaction.response.defer()

        if not is_ANO_member(interaction.user.roles):
            return await interaction.followup.send(
                embed=ErrorEmbed("Only ANO members can wear this uniform!")
            )

        uuid = (await request(f"https://api.mojang.com/users/profiles/minecraft/{username}")).get("id", "")
        if not uuid:
            return await interaction.followup.send(embed=ErrorEmbed("Player not found."))

        data = await request(f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}")
        skindata = ast.literal_eval(base64.b64decode(data["properties"][0]["value"]).decode("UTF-8"))

        player_skin = Image.open(await request(skindata["textures"]["SKIN"]["url"], return_type="stream"))

        if player_skin.height == 32:
            leg = player_skin.crop((0, 16, 16, 32))
            arm = player_skin.crop((40, 16, 56, 32))
            body = player_skin.crop((16, 16, 40, 32))
            head = player_skin.crop((0, 0, 64, 16))

            player_skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))

            player_skin.paste(leg, (16, 48))
            player_skin.paste(leg, (0, 16))
            player_skin.paste(arm, (40, 16))
            player_skin.paste(arm, (32, 48))
            player_skin.paste(body, (16, 16))
            player_skin.paste(head, (0, 0))

        rect1 = Image.new("RGBA", (64, 16), (0, 0, 0, 0))
        rect2 = Image.new("RGBA", (16, 16), (0, 0, 0, 0))

        player_skin.paste(rect1, (0, 32))
        player_skin.paste(rect2, (0, 48))
        player_skin.paste(rect2, (48, 48))

        if skin_variant.value == "male":
            uniform_skin = Image.open("assets/male_uniform_overlay.png").convert("RGBA")
        elif skin_variant.value == "female":
            uniform_skin = Image.open("assets/female_uniform_overlay.png").convert("RGBA")
        else:
            await interaction.followup.send(embed=ErrorEmbed("Invalid skin variant"), ephemeral=True)
            return

        final_skin = Image.alpha_composite(player_skin, uniform_skin)

        final_skin.save("/tmp/uniform_skin.png")

        file = File("/tmp/uniform_skin.png", filename="uniform_skin.png")

        await interaction.followup.send(file=file)



async def setup(bot: commands.Bot):
    cog = Uniform(bot)
    await bot.add_cog(cog)

    existing_global = bot.tree.get_command("uniform")
    if existing_global:
        bot.tree.remove_command("uniform")

    for guild_id in config.ANO_COMMANDS_GUILD_IDS:
        guild = discord.Object(id=int(guild_id))
        bot.tree.add_command(cog.uniform, guild=guild)
