import discord
from discord import app_commands
from discord.ext import commands

from core.antispam import rate_limit_check
from util.embeds import ErrorEmbed
from util.mappings import EMOJI_MAP, ITEM_TO_EMOJI_MAP, ASPECT_TO_EMOJI_MAP, WARD_TO_EMOJI_MAP
from util.requests import request_with_csrf


class Pools(commands.Cog):
    """
    Cog providing commands for viewing Wynncraft Loot Pools and Aspect Pools with interactive select menus.
    Fetches data from the nori.fish API with CSRF token support.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Constants for mapping pool keys to human-readable names and API keys ---

    LOOT_POOL_NAME_MAP = {
        "silent_expanse": "Silent Expanse",
        "canyon_of_the_lost": "Canyon of the Lost",
        "corkus": "Corkus",
        "sky_islands": "Sky Islands",
        "molten_heights": "Molten Heights",
        "fruma_east": "Fruma East",
        "fruma_west": "Fruma West"
    }

    LOOT_POOL_API_MAP = {
        "silent_expanse": "SE",
        "canyon_of_the_lost": "Canyon",
        "corkus": "Corkus",
        "sky_islands": "Sky",
        "molten_heights": "Molten",
        "fruma_east": "FrumaEast",
        "fruma_west": "FrumaWest"
    }

    ASPECT_POOL_NAME_MAP = {
        "tna": "The Nameless Anomaly",
        "tcc": "The Canyon Colossus",
        "nol": "Nexus of Light",
        "notg": "Nest of The Grootslangs",
        "twp": "The Wartorn Palace"
    }

    ASPECT_POOL_API_MAP = {
        "tna": "TNA",
        "tcc": "TCC",
        "nol": "NOL",
        "notg": "NOTG",
        "twp": "TWP"
    }

    # Base API URLs and resource URLs
    BASE_URL = "https://nori.fish"
    TOKEN_URL = f"{BASE_URL}/api/tokens"
    LOOTPOOL_URL = f"{BASE_URL}/api/lootpool"
    ASPECTPOOL_URL = f"{BASE_URL}/api/aspects"
    LOOTRUN_ICON_URL = "https://wynncraft.wiki.gg/images/LootrunUpdateIcon.png?d4bc04"
    ASPECT_ICON_URL = "https://nori.fish/resources/aspect.gif"


    # === Loot Pool Section ===

    async def build_loot_embed(self, pool_key: str | None = None) -> discord.Embed | ErrorEmbed:
        """
        Builds an embed showing loot pool information.

        If pool_key is None, show overview of all loot pools.
        Otherwise, show detailed mythics and rarities for the selected loot pool.
        """
        # Fetch loot pool data with CSRF token support
        data = (await request_with_csrf(self.TOKEN_URL, self.LOOTPOOL_URL))["Loot"]

        # Overview embed for all loot pools
        if pool_key is None:
            embed = discord.Embed(
                title="Loot Pool Overview",
                color=discord.Colour.from_rgb(74, 86, 219)
            )

            for key, name in self.LOOT_POOL_NAME_MAP.items():
                api_name = self.LOOT_POOL_API_MAP[key]
                pool = data.get(api_name)
                if not pool:
                    continue

                # Build field listing shiny and mythic items
                field = ""
                shiny = pool.get("Shiny")
                mythics = pool.get("Mythic", [])

                if shiny:
                    icon = EMOJI_MAP.get(ITEM_TO_EMOJI_MAP.get(shiny['Item']), "")
                    field += f"- {EMOJI_MAP['shiny']}{icon} **Shiny** {shiny['Item']} (Tracker: {shiny['Tracker']})\n"

                for item in mythics:
                    emoji_id = ITEM_TO_EMOJI_MAP.get(item) or WARD_TO_EMOJI_MAP.get(item) or ""
                    icon = EMOJI_MAP.get(emoji_id, "")
                    field += f"- {icon} {item}\n"

                embed.add_field(name=f"{name} Mythics", value=field or "None", inline=False)

            embed.set_thumbnail(url=self.LOOTRUN_ICON_URL)
            return embed

        # Detailed embed for specific loot pool key
        api_name = self.LOOT_POOL_API_MAP[pool_key]
        pool = data.get(api_name)
        if not pool:
            return ErrorEmbed(f"Loot pool data for {api_name} not found.")

        embed = discord.Embed(
            title=f"Loot Pool: {api_name}",
            color=discord.Colour.from_rgb(74, 86, 219)
        )

        # Extract and remove shiny and mythics from pool dict so we can handle rarities separately
        shiny = pool.pop("Shiny", None)
        mythics = pool.pop("Mythic", [])

        # Format shiny and mythics
        text = ""
        if shiny:
            icon = EMOJI_MAP.get(ITEM_TO_EMOJI_MAP.get(shiny['Item']), "")
            text += f"- {EMOJI_MAP['shiny']}{icon} **Shiny** {shiny['Item']} (Tracker: {shiny['Tracker']})\n"
        for item in mythics:
            emoji_id = ITEM_TO_EMOJI_MAP.get(item) or WARD_TO_EMOJI_MAP.get(item) or ""
            icon = EMOJI_MAP.get(emoji_id, "")
            text += f"- {icon} {item}\n"
        embed.add_field(name="Mythics", value=text or "None", inline=False)

        # Add remaining rarities with their items
        for rarity, items in pool.items():
            field = "\n".join(f"- {item}" for item in items)
            embed.add_field(name=rarity, value=field or "None", inline=False)

        embed.set_thumbnail(url=self.LOOTRUN_ICON_URL)
        return embed


    class LootPoolSelect(discord.ui.Select):
        """
        Select menu for choosing a loot pool.
        """

        def __init__(self, cog: "Pools"):
            self.cog = cog
            options = [
                discord.SelectOption(label=name, value=key)
                for key, name in cog.LOOT_POOL_NAME_MAP.items()
            ]
            super().__init__(placeholder="Choose a loot pool...", options=options)

        async def callback(self, interaction: discord.Interaction):
            """
            When a loot pool is selected, build and display the corresponding embed.
            """
            embed = await self.cog.build_loot_embed(self.values[0])
            await interaction.response.edit_message(embed=embed, view=self.view)


    class LootPoolView(discord.ui.View):
        """
        View containing the LootPoolSelect select menu.
        """

        def __init__(self, cog: "Pools"):
            super().__init__()
            self.add_item(Pools.LootPoolSelect(cog))


    @app_commands.command(name="lootpool", description="View the current loot pool for lootrun camps")
    @rate_limit_check()
    async def lootpool(self, interaction: discord.Interaction):
        """
        Slash command to display loot pool overview with interactive select menu.
        """
        embed = await self.build_loot_embed()
        view = self.LootPoolView(self)
        await interaction.response.send_message(embed=embed, view=view)



    # === Aspect Pool Section ===

    async def build_aspect_embed(self, raid_key: str | None = None) -> discord.Embed | ErrorEmbed:
        """
        Builds an embed showing aspect pool information.

        If raid_key is None, show overview of all aspect pools.
        Otherwise, show detailed mythic/fabled/legendary aspects for the selected raid.
        """
        # Fetch aspect pool data with CSRF token support
        data = await request_with_csrf(self.TOKEN_URL, self.ASPECTPOOL_URL)

        # Overview embed for all aspect pools
        if raid_key is None:
            embed = discord.Embed(
                title="Aspect Pool Overview",
                color=discord.Colour.from_rgb(255, 71, 77)
            )

            for key, name in self.ASPECT_POOL_NAME_MAP.items():
                raid = data["Loot"][self.ASPECT_POOL_API_MAP[key]]
                text = ""
                for item in raid.get("Mythic", []):
                    emoji_id = ASPECT_TO_EMOJI_MAP.get(data['Icon'][item]) or WARD_TO_EMOJI_MAP.get(item) or ""
                    icon = EMOJI_MAP.get(emoji_id, "")
                    text += f"- {icon} {item}\n"

                embed.add_field(name=f"{name} Mythic Aspects", value=text or "None", inline=False)

            embed.set_thumbnail(url=self.ASPECT_ICON_URL)
            return embed

        # Detailed embed for specific aspect pool key
        pool_key = self.ASPECT_POOL_API_MAP[raid_key]
        raid_data = data["Loot"].get(pool_key)
        if not raid_data:
            return ErrorEmbed(f"Aspect data for {pool_key} not found.")

        embed = discord.Embed(
            title=f"Aspect Pool: {self.ASPECT_POOL_NAME_MAP[raid_key]}",
            color=discord.Colour.from_rgb(255, 71, 77)
        )

        # Add fields for each rarity type with formatted items
        for rarity in ("Mythic", "Fabled", "Legendary"):
            items = raid_data.get(rarity, [])
            field = ""
            for item in items:
                emoji_id = ASPECT_TO_EMOJI_MAP.get(data['Icon'][item]) or WARD_TO_EMOJI_MAP.get(item) or ""
                field += f"- {EMOJI_MAP.get(emoji_id, '')} {item}\n"
            embed.add_field(name=f"{rarity} Aspects", value=field or "None", inline=False)

        embed.set_thumbnail(url=self.ASPECT_ICON_URL)
        return embed


    class AspectPoolSelect(discord.ui.Select):
        """
        Select menu for choosing an aspect pool.
        """

        def __init__(self, cog: "Pools"):
            self.cog = cog
            options = [
                discord.SelectOption(label=name, value=key)
                for key, name in cog.ASPECT_POOL_NAME_MAP.items()
            ]
            super().__init__(placeholder="Choose an aspect pool...", options=options)

        async def callback(self, interaction: discord.Interaction):
            """
            When an aspect pool is selected, build and display the corresponding embed.
            """
            embed = await self.cog.build_aspect_embed(self.values[0])
            await interaction.response.edit_message(embed=embed, view=self.view)


    class AspectPoolView(discord.ui.View):
        """
        View containing the AspectPoolSelect select menu.
        """
        def __init__(self, cog: "Pools"):
            super().__init__()
            self.add_item(Pools.AspectPoolSelect(cog))


    @app_commands.command(name="aspectpool", description="View current aspect pool for raids")
    @rate_limit_check()
    async def aspectpool(self, interaction: discord.Interaction):
        """
        Slash command to display aspect pool overview with interactive select menu.
        """
        embed = await self.build_aspect_embed()
        view = self.AspectPoolView(self)
        await interaction.response.send_message(embed=embed, view=view)



# Cog setup function for bot
async def setup(bot: commands.Bot):
    await bot.add_cog(Pools(bot))
