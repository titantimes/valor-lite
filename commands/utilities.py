import discord

from datetime import datetime, timedelta, timezone
from discord import app_commands
from discord.ext import commands

from util.embeds import ErrorEmbed
from util.mappings import TERRITORY_DAMAGE_VALUES, TERRITORY_ATTACK_VALUES, TERRITORY_HEALTH_VALUES, TERRITORY_DEFENCE_VALUES


class Utilities(commands.GroupCog, name="utilities"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @app_commands.command(
        name="calculate_territory_defences",
        description="Calculate tower stats based on buffs and HQ status."
    )
    @app_commands.describe(
        buffs="Four upgrade levels separated by commas (e.g. 4,8,2,11 or 4x11)",
        conns="Number of connections (default 0)",
        exts="Number of externals (default 0)",
        is_hq="Is this an HQ territory? (default True)"
    )
    async def calculate_territory_defences(
        self,
        interaction: discord.Interaction,
        conns: int = 0,
        exts: int = 0,
        buffs: str = "4x11",
        is_hq: bool = True
    ):
        try:
            if buffs.strip().startswith("4x"):
                parts = buffs.split("x")
                if len(parts) != 2:
                    raise ValueError()
                buffs_list = [int(parts[1])] * 4
            else:
                buffs_list = list(map(int, buffs.split(",")))
                if len(buffs_list) != 4:
                    raise ValueError()
        except Exception:
            return await interaction.response.send_message(
                embed=ErrorEmbed("Please use either `4x11` or `4,8,2,11` format."),
                ephemeral=True
            )

        dmg_lvl, atk_lvl, hp_lvl, def_lvl = buffs_list

        if not all(0 <= b <= 11 for b in buffs_list):
            return await interaction.response.send_message(
                embed=ErrorEmbed("Each buff level must be between 0 and 11."),
                ephemeral=True
            )

        damage = TERRITORY_DAMAGE_VALUES[dmg_lvl]
        atk_speed = TERRITORY_ATTACK_VALUES[atk_lvl]
        base_hp = TERRITORY_HEALTH_VALUES[hp_lvl]
        def_percent = TERRITORY_DEFENCE_VALUES[def_lvl]

        if is_hq:
            hp = round(base_hp * (1.5 + 0.25 * (conns + exts)) * (1 + 0.3 * conns))
            damage = round(damage * (1.5 + 0.25 * (conns + exts)) * (1 + 0.3 * conns))
        else:
            hp = base_hp
            damage = damage

        damage_high = round(damage * 1.5)

        dps = round(damage * atk_speed)

        ehp = round(hp / (1 - def_percent))

        embed = discord.Embed(
            title="Territory Defence Calculator",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="Inputs",
            value=(
                f"**Conns:** `{conns}` | **Exts:** `{exts}` | **HQ:** `{is_hq}` \n"
                f"**Buffs:** \n- Damage `{dmg_lvl}` \n- Atk Speed `{atk_lvl}` \n- HP `{hp_lvl}` \n- Defence `{def_lvl}`\n"
            ),
            inline=True
        )

        embed.add_field(
            name="Calculated Stats",
            value=(
                f"**HP:** `{hp:,}`\n"
                f"**Damage:** `{damage:,} - {damage_high:,}`\n"
                f"**Defence:** `{int(def_percent * 100)}%`\n"
                f"**Attack Speed:** `{atk_speed:.2f}x`\n\n"
                f"**EHP:** `{int(ehp):,}`\n"
                f"**DPS:** `{dps:,}`"
            ),
            inline=True
        )

        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="reset_timers", description="Show upcoming reset times for various events.")
    async def reset_timers(self, interaction: discord.Interaction):
        await interaction.response.defer()

        now = datetime.now(timezone.utc)

        # ------------------------
        # Helper functions
        # ------------------------

        def next_weekly_reset(hour: int, minute: int, weekday: int):
            days_ahead = (weekday - now.weekday()) % 7
            if days_ahead == 0 and (now.hour > hour or (now.hour == hour and now.minute >= minute)):
                days_ahead = 7
            reset_dt = (now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return reset_dt

        def next_daily_reset(hour: int, minute: int):
            reset_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now >= reset_dt:
                reset_dt += timedelta(days=1)
            return reset_dt

        events = [
            ("Loot pool reset", next_weekly_reset(18, 0, 4)),                   # Friday 6pm UTC
            ("Aspect pool reset", next_weekly_reset(17, 0, 4)),                 # Friday 5pm UTC
            ("", ""),                                                           # Separator field
            ("Daily objectives reset", next_daily_reset(4, 0)),                 # Daily 5am UTC
            ("Guild objectives reset", next_weekly_reset(4, 0, 0)),             # Mondays 4am UTC
            ("", ""),                                                           # Separator field
            ("Daily crates (for ranked players)", next_daily_reset(4, 0)),      # Daily 5am UTC
        ]

        embed = discord.Embed(
            title="Upcoming Reset Times",
            color=0x32CFC4
        )

        for name, dt in events:
            if name == "":
                embed.add_field(name=" ", value=" ")
                continue

            ts_unix = int(dt.timestamp())
            embed.add_field(
                name=name,
                value=f"<t:{ts_unix}:f> (<t:{ts_unix}:R>)",
                inline=False
            )

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utilities(bot))
