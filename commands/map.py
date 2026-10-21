import asyncio, discord, json, logging, io, shlex

from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from core.antispam import rate_limit_check
from util.embeds import ErrorEmbed
from util.guilds import guild_names_from_tags
from util.requests import request


with open("assets/map_regions.json") as f:
    map_regions = json.load(f)

zone_label_to_key = {data["label"].lower(): key for key, data in map_regions.items()}

class Map(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.render_lock = asyncio.Lock()


    def normalize_zone(self, zone_input: str) -> str | None:
        zone_lower = zone_input.lower()
        if zone_lower in map_regions:
            return zone_lower
        return zone_label_to_key.get(zone_lower)

    def to_full_map_coord(self, x_ingame, y_ingame, map_width, map_height):
        x_canvas = (x_ingame + 2480) * (map_width - 1) / 4130
        y_canvas = (y_ingame + 6578) * (map_height - 1) / 6419
        return x_canvas, y_canvas

    def draw_text_with_outline(self, draw, position, text, font, fill, outline_color=(0, 0, 0), outline_width=1):
        x, y = position
        y_pad = -2
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy + y_pad), text, font=font, fill=outline_color)
        draw.text((x, y + y_pad), text, font=font, fill=fill)

    def crown(self, draw, bounds):
        left, top, right, bottom = bounds
        width = min(32, (right - left) * 0.45, (bottom - top) * 0.4)
        height = width * 0.65
        if width < 3:
            return 0
        cleft = (left + right - width) / 2
        ctop = top + (bottom - top) * 0.12
        points = [
            (0, 0.15), (0.25, 0.45), (0.5, 0), (0.65, 0.45),
            (1, 0.15), (0.85, 1), (0.15, 1),
        ]
        draw.polygon(
            [(cleft + horizontal * width, ctop + vertical * height)
                for horizontal, vertical in points],
            fill=(255, 211, 64, 255), outline=(0, 0, 0, 255),
            width=max(1, round(width / 16)),
        )
        return height

    def hex_to_rgb(self, hex_color, fallback=(136, 136, 136)):
        try:
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 6:
                return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            elif len(hex_color) == 3:
                return tuple(int(hex_color[i]*2, 16) for i in range(3))
            elif len(hex_color) < 6:
                padded = (hex_color + "0"*6)[:6]
                return tuple(int(padded[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            logging.warning(f"Invalid color code: #{hex_color}")
        return fallback


    @app_commands.command(name="map", description="Show the live Wynncraft territory map, optionally filtered by guild or zone.")
    @app_commands.describe(guild="Filter by guild tags (comma-separated)", zone="Optional region/zone names to crop to (comma-separated)")
    @rate_limit_check()
    async def map(self, interaction: discord.Interaction, guild: str = None, zone: str = None):
        await interaction.response.defer()

        async with self.render_lock:
            image, error = await self._render_map(guild, zone)

        if error:
            return await interaction.followup.send(embed=ErrorEmbed(error), ephemeral=True)

        try:
            await interaction.followup.send(file=discord.File(fp=image, filename="map.png"))
        finally:
            image.close()


    @commands.command(name="map", aliases=["m"])
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def prefixmap(self, ctx: commands.Context, *, options: str = ""):
        try:
            tokens = shlex.split(options)
            guild_tags = []
            zones = []
            index = 0

            while index < len(tokens):
                option = tokens[index].lower()
                if option in {"-g", "--guild"}:
                    index += 1
                    found_value = False
                    while index < len(tokens) and not tokens[index].startswith("-"):
                        guild_tags.extend(tag for tag in tokens[index].split(",") if tag)
                        found_value = True
                        index += 1
                    if not found_value:
                        raise ValueError("Provide one or more guild tags after `-g`.")
                elif option in {"-z", "--zone"}:
                    index += 1
                    if index >= len(tokens) or tokens[index].startswith("-"):
                        raise ValueError("Provide one or more zones after `-z`.")
                    zones.extend(zone.strip() for zone in tokens[index].split(",") if zone.strip())
                    index += 1
                else:
                    raise ValueError(f"Unrecognized option: `{tokens[index]}`.")

            guild = ",".join(guild_tags) or None
            zone = ",".join(zones) or None
        except ValueError as error:
            return await ctx.send(embed=ErrorEmbed(
                f"{error}\nUsage: `-map [-g TAG [TAG ...]] [-z ZONE[,ZONE...]]`"
            ))

        async with self.render_lock:
            image, error = await self._render_map(guild, zone)

        if error:
            return await ctx.send(embed=ErrorEmbed(error))

        try:
            await ctx.send(file=discord.File(fp=image, filename="map.png"))
        finally:
            image.close()


    @prefixmap.error
    async def prefixmap_e(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(embed=ErrorEmbed(
                f"Try again in {error.retry_after:.1f} seconds."
            ))

        logging.error(
            "Prefix map failed: %s",
            error,
            exc_info=(type(error), error, error.__traceback__)
        )
        await ctx.send(embed=ErrorEmbed("Map generation failed. Please try again later."))


    async def _render_map(self, guild: str = None, zone: str = None):

        guild_tags = [tag.strip().lower() for tag in guild.split(",")] if guild else []
        zones = [z.strip() for z in zone.split(",")] if zone else []
        if zones:
            normalized_zones = []
            invalid_zones = []
            
            for z in zones:
                normalized = self.normalize_zone(z)
                if normalized:
                    normalized_zones.append(normalized)
                else:
                    invalid_zones.append(z)
            
            if invalid_zones:
                return None, f"Invalid zone(s): {', '.join(invalid_zones)}"
            
            zones = normalized_zones

        try:
            terr_res = await request("https://api.wynncraft.com/v3/guild/list/territory")
            if not isinstance(terr_res, dict) or not terr_res:
                terr_res = await request("https://athena.wynntils.com/cache/get/territoryList")
            guilds_res = await request("https://athena.wynntils.com/cache/get/guildList")
            guild_color_lookup = {}
            if isinstance(guilds_res, list):
                for entry in guilds_res:
                    try:
                        color = entry.get("color") or ""
                        gid = entry.get("_id") or entry.get("id")
                        prefix = entry.get("prefix")
                        if gid:
                            guild_color_lookup[gid] = color
                        if prefix:
                            guild_color_lookup[prefix.lower()] = color
                    except Exception:
                        continue
        except Exception:
            return None, "Map data is currently unavailable."

        territories = None
        if isinstance(terr_res, dict):
            if "territories" in terr_res and isinstance(terr_res["territories"], dict):
                territories = terr_res["territories"]
            elif "data" in terr_res and isinstance(terr_res["data"], dict) and "territories" in terr_res["data"]:
                territories = terr_res["data"]["territories"]
            else:
                if all(isinstance(v, dict) and ("location" in v or "acquired" in v) for v in terr_res.values()):
                    territories = terr_res
        elif isinstance(terr_res, list):
            for item in terr_res:
                if isinstance(item, dict) and "territories" in item:
                    territories = item["territories"]
                    break

        if not territories or not isinstance(territories, dict):
            logging.error("Unexpected map territory response: %s", terr_res)
            return None, "Territory data is currently unavailable."

        with open("assets/terr_conns.json") as f:
            terr_conns = json.load(f)

        main_map = Image.open("assets/main_map.png")
        font = ImageFont.truetype("assets/MinecraftRegular.ttf", 16)
        map_width, map_height = main_map.size

        base = Image.new("RGBA", main_map.size)
        terr_layer = Image.new("RGBA", main_map.size)
        label_layer = Image.new("RGBA", main_map.size)
        draw_base = ImageDraw.Draw(base)
        draw_territory = ImageDraw.Draw(terr_layer)
        draw_label = ImageDraw.Draw(label_layer)

        centers = {}      #for conns
        terr_owners = {}  #for filtering conns

        def extract_coords(loc: dict):
            if not isinstance(loc, dict):
                raise ValueError("Invalid location")
            if "startX" in loc or "startZ" in loc:
                sx = loc.get("startX")
                sz = loc.get("startZ")
                ex = loc.get("endX")
                ez = loc.get("endZ")
                return sx, sz, ex, ez
            if "start" in loc and isinstance(loc["start"], (list, tuple)):
                sx, sz = loc["start"][0], loc["start"][1]
                ex, ez = loc["end"][0], loc["end"][1]
                return sx, sz, ex, ez
            raise ValueError("Unsupported location format")

        def extract_prefix(data: dict):
            if "guildPrefix" in data and data.get("guildPrefix"):
                return data.get("guildPrefix")
            g = data.get("guild")
            if isinstance(g, dict):
                return g.get("prefix") or g.get("name")
            return None

        for name, data in territories.items():
            loc = data.get("location") or data
            try:
                sx, sz, ex, ez = extract_coords(loc)
            except Exception:
                continue
            x1, y1 = self.to_full_map_coord(sx, sz, map_width, map_height)
            x2, y2 = self.to_full_map_coord(ex, ez, map_width, map_height)
            cx = (min(x1, x2) + max(x1, x2)) / 2
            cy = (min(y1, y2) + max(y1, y2)) / 2
            centers[name] = (cx, cy)
        

        if guild_tags:
            min_x, min_y = float("inf"), float("inf")
            max_x, max_y = float("-inf"), float("-inf")

        for name, data in territories.items():
            loc = data.get("location") or data
            prefix = extract_prefix(data) or ""

            if guild_tags and prefix.lower() not in guild_tags:
                continue

            terr_owners[name] = prefix

            color = None
            if data.get("guildColor"):
                color = data.get("guildColor")
            elif isinstance(data.get("guild"), dict):
                color = data.get("guild", {}).get("color")
            guild_id = None
            g = data.get("guild")
            if isinstance(g, dict):
                guild_id = g.get("uuid") or g.get("_id")
            elif isinstance(g, str):
                guild_id = g
            if not color and guild_id:
                color = guild_color_lookup.get(guild_id)
            if not color and prefix:
                color = guild_color_lookup.get(prefix.lower())
            if not color:
                color = "#888888"

            rgb = self.hex_to_rgb(color) if prefix else (255, 255, 255)
            fill = rgb + (90,)      
            border = rgb + (255,)   

            try:
                sx, sz, ex, ez = extract_coords(loc)
            except Exception:
                continue
            x1, y1 = self.to_full_map_coord(sx, sz, map_width, map_height)
            x2, y2 = self.to_full_map_coord(ex, ez, map_width, map_height)
            left, right = sorted([x1, x2])
            top, bottom = sorted([y1, y2])
            cx, cy = (left + right) / 2, (top + bottom) / 2

            if guild_tags:
                min_x = min(min_x, left)
                min_y = min(min_y, top)
                max_x = max(max_x, right)
                max_y = max(max_y, bottom)

            draw_territory.rectangle([left, top, right, bottom], fill=fill)
            draw_label.rectangle([left-1, top-1, right+1, bottom+1], outline=(0, 0, 0), width=3)
            draw_label.rectangle([left, top, right, bottom], outline=border, width=2)

            bbox = draw_label.textbbox((0, 0), prefix or "None", font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            crown_height = 0
            if data.get("hq") is True:
                crown_height = self.crown(draw_label, (left, top, right, bottom))
            self.draw_text_with_outline(draw_label, (cx - tw/2, cy - th/2 + crown_height/2), prefix or "None", font, fill=border)

        for start, targets in terr_conns.items():
            center_start = centers.get(start)
            if not center_start:
                continue
            for target in targets.get("Trading Routes", []):
                if target not in centers:
                    continue

                if guild_tags and (terr_owners.get(start) not in guild_tags or terr_owners.get(target) not in guild_tags):
                    continue

                draw_base.line([center_start, centers[target]], fill=(20, 20, 20), width=2)

        composed = Image.alpha_composite(main_map.convert("RGBA"), base)
        composed = Image.alpha_composite(composed, terr_layer)
        final = Image.alpha_composite(composed, label_layer)

        if guild_tags and not zones:
            if min_x != float("inf"):
                final = final.crop((min_x - 50, min_y - 50, max_x + 50, max_y + 50))
            else:
                plural = "s are" if len(guild_tags) > 1 else " is"
                return None, f"Specified guild{plural} not currently on the map."

        if zones:
            crop_min_x, crop_min_y = float("inf"), float("inf")
            crop_max_x, crop_max_y = float("-inf"), float("-inf")
            
            for zone_name in zones:
                reg = map_regions[zone_name]["pos"]
                x1, y1 = self.to_full_map_coord(reg[0], reg[1], map_width, map_height)
                x2, y2 = self.to_full_map_coord(reg[2], reg[3], map_width, map_height)
                
                crop_min_x = min(crop_min_x, x1, x2)
                crop_min_y = min(crop_min_y, y1, y2)
                crop_max_x = max(crop_max_x, x1, x2)
                crop_max_y = max(crop_max_y, y1, y2)
            
            final = final.crop((crop_min_x - 50, crop_min_y - 50, crop_max_x + 50, crop_max_y + 50))

        
        img_binary = io.BytesIO()
        final.save(img_binary, 'PNG')
        img_binary.seek(0)
        return img_binary, None


    @map.autocomplete("zone")
    async def guild_settings_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        parts = current.split(",")
        current_zone = parts[-1].strip().lower()
        
        already_entered = set()
        if len(parts) > 1:
            for entered in parts[:-1]:
                normalized = self.normalize_zone(entered.strip())
                if normalized:
                    already_entered.add(normalized)
        
        prefix = ",".join(parts[:-1])
        value_prefix = prefix + "," if prefix else ""
        display_prefix = prefix + ", " if prefix else ""

        autocomplete = []
        for zone_key, zone_data in map_regions.items():
            if zone_key in already_entered:
                continue

            zone_label = zone_data["label"]
            if current_zone in zone_key or current_zone in zone_label.lower():
                autocomplete.append(app_commands.Choice(
                    name=display_prefix + zone_label.title(),
                    value=value_prefix + zone_key
                ))

        return autocomplete

async def setup(bot: commands.Bot):
    await bot.add_cog(Map(bot))
